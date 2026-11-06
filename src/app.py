import json
import boto3
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from llm import analyze_stream, LLMError
from validate import clean_result
from store import make_hash, get_cached, put_cached, check_rate_limit

# Lambda Web Adapter runs this app behind the Function URL.
# No /docs or /openapi.json, since the URL is public.
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

ssm = boto3.client("ssm")
_keys = {}

NDJSON = "application/x-ndjson"
STREAM_HEADERS = {"Cache-Control": "no-store"}


def get_key(name):
    # cached across warm invocations so we do not call SSM every time
    if name not in _keys:
        resp = ssm.get_parameter(Name=name, WithDecryption=True)
        _keys[name] = resp["Parameter"]["Value"]
    return _keys[name]


def event(obj):
    """One line of newline-delimited JSON. The browser reads the stream line by line."""
    return (json.dumps(obj) + "\n").encode("utf-8")


def get_ip(request):
    # Web Adapter passes the original Lambda request context in this header
    try:
        ctx = json.loads(request.headers.get("x-amzn-request-context", "{}"))
    except json.JSONDecodeError:
        ctx = {}
    http = ctx.get("http") or {}
    identity = ctx.get("identity") or {}
    return http.get("sourceIp") or identity.get("sourceIp") or "unknown"


def stream_events(h, resume, jd):
    """Runs the LLM call and yields events: delta, reset, final or error."""
    try:
        gemini_key = get_key("/resume-matcher/gemini-api-key")
        groq_key = get_key("/resume-matcher/groq-key")

        for kind, payload in analyze_stream(gemini_key, groq_key, resume, jd):
            if kind == "delta":
                yield event({"type": "delta", "text": payload})
            elif kind == "reset":
                yield event({"type": "reset"})
            elif kind == "final":
                raw, provider = payload
                print(f"Answered by {provider}")
                result = clean_result(raw)
                put_cached(h, result)
                yield event({"type": "final", "result": result})
    except LLMError as e:
        print(f"All providers failed: status={e.status}")
        yield event({"type": "error", "message": "AI service failed. Try again."})
    except Exception as e:
        print(f"Unexpected error: {type(e).__name__}")
        yield event({"type": "error", "message": "Something went wrong. Try again."})


@app.post("/")
async def analyze(request: Request):
    # Errors found before streaming starts are normal JSON responses with a status code.
    # (The blocking boto3 calls below are fine: one Lambda instance handles one request at a time.)
    try:
        data = json.loads(await request.body() or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    if not isinstance(data, dict):
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    resume = data.get("resume", "")
    jd = data.get("jd", "")

    if not isinstance(resume, str) or not isinstance(jd, str) or not resume or not jd:
        return JSONResponse({"error": "resume and jd are required"}, status_code=400)
    MAX_CHARS = 10000
    if len(resume) > MAX_CHARS or len(jd) > MAX_CHARS:
        return JSONResponse({"error": "Text too long (max 10,000 characters each)."}, status_code=400)
    
    h = make_hash(resume, jd)
    cached = get_cached(h)
    if cached:
        print("cache hit")
        return StreamingResponse(
            iter([event({"type": "final", "result": cached})]),
            media_type=NDJSON,
            headers=STREAM_HEADERS,
        )

    ip = get_ip(request)
    print(f"ip_known={ip != 'unknown'}")  # never log the IP or the text itself
    if not check_rate_limit(ip):
        print("rate limit hit")
        return JSONResponse({"error": "Daily limit reached. Try again tomorrow."}, status_code=429)

    return StreamingResponse(
        stream_events(h, resume, jd),
        media_type=NDJSON,
        headers=STREAM_HEADERS,
    )