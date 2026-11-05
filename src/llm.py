import http.client
import json
import time
import urllib.request
import urllib.error

from prompt import SYSTEM_PROMPT, RESPONSE_SCHEMA, build_user_prompt

GEMINI_MODEL = "gemini-3.5-flash-lite"
# streamGenerateContent + alt=sse gives us server-sent events instead of one big reply
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}"
    ":streamGenerateContent?alt=sse"
)

GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

RETRY_CODES = {429, 500, 502, 503, 504}


class LLMError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def _open(url, headers, body):
    """Send the request and return the open response (not read yet)."""
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "resume-matcher/1.0", **headers},
        method="POST",
    )
    try:
        return urllib.request.urlopen(req, timeout=25)
    except urllib.error.HTTPError as e:
        raise LLMError(f"HTTP error {e.code}", status=e.code)
    except (urllib.error.URLError, TimeoutError):
        raise LLMError("Could not reach provider")


def _sse_events(resp):
    """Yield the parsed JSON of every 'data:' line of a server-sent-events response."""
    try:
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                return
            try:
                yield json.loads(payload)
            except json.JSONDecodeError:
                raise LLMError("Bad data in stream")
    except (OSError, http.client.HTTPException):
        # timeout or connection reset in the middle of the stream
        raise LLMError("Stream broke")
    finally:
        resp.close()


def stream_gemini(api_key, resume, jd):
    """Yields pieces of the model's JSON text as they arrive."""
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": build_user_prompt(resume, jd)}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseJsonSchema": RESPONSE_SCHEMA,
        },
    }
    resp = _open(GEMINI_URL, {"x-goog-api-key": api_key}, body)
    for data in _sse_events(resp):
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError):
            continue  # chunk without text, for example only usage info
        for part in parts:
            if part.get("thought"):
                continue
            text = part.get("text")
            if text:
                yield text


def stream_groq(api_key, resume, jd):
    # Groq has no schema field, so the schema goes inside the system prompt
    system = SYSTEM_PROMPT + "\n\nReturn ONLY valid JSON matching this schema:\n" + json.dumps(RESPONSE_SCHEMA)
    body = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": build_user_prompt(resume, jd)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "reasoning_effort": "low",
        "stream": True,
    }
    resp = _open(GROQ_URL, {"Authorization": f"Bearer {api_key}"}, body)
    for data in _sse_events(resp):
        try:
            text = data["choices"][0]["delta"].get("content")
        except (KeyError, IndexError, AttributeError):
            continue
        if text:
            yield text


def analyze_stream(gemini_key, groq_key, resume, jd):
    """
    Generator. Yields:
      ("delta", text)                  a piece of the model's JSON text
      ("reset", None)                  a provider failed after sending some text,
                                       so the caller must throw away what it has so far
      ("final", (result_dict, name))   the complete parsed result and the provider name
    Raises LLMError if every provider fails.

    Each provider gets 2 tries (retry only on 429/5xx/network errors), then we move on.
    """
    providers = [
        ("gemini", stream_gemini, gemini_key),
        ("groq", stream_groq, groq_key),
    ]
    last_error = None

    for name, stream_fn, key in providers:
        for attempt in (1, 2):
            sent_any = False
            text = ""
            try:
                for chunk in stream_fn(key, resume, jd):
                    sent_any = True
                    text += chunk
                    yield ("delta", chunk)
                result = json.loads(text)
                yield ("final", (result, name))
                return
            except json.JSONDecodeError:
                err = LLMError("Model did not return valid JSON")
            except LLMError as e:
                err = e

            last_error = err
            print(f"{name} failed: {err} (status={err.status}, attempt={attempt})")

            if sent_any:
                yield ("reset", None)
            if err.status is not None and err.status not in RETRY_CODES:
                break  # 400/401/403/404: retrying will not help
            if attempt == 1:
                time.sleep(1)

        print(f"Giving up on {name}")

    raise last_error or LLMError("No provider worked")