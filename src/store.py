import os
import json
import time
import hashlib
import boto3

table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
CACHE_TTL = 7 * 24 * 3600  # 7 days
DAILY_LIMIT = 20


def make_hash(resume, jd):
    text = resume.strip() + "\n---\n" + jd.strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_cached(h):
    try:
        item = table.get_item(Key={"pk": f"cache#{h}"}).get("Item")
        # TTL delete can lag by hours, so check expiry ourselves
        if item and int(item["ttl"]) > int(time.time()):
            return json.loads(item["result"])
    except Exception as e:
        print(f"cache read failed: {type(e).__name__}")
    return None


def put_cached(h, result):
    try:
        table.put_item(Item={
            "pk": f"cache#{h}",
            "result": json.dumps(result),
            "ttl": int(time.time()) + CACHE_TTL,
        })
    except Exception as e:
        print(f"cache write failed: {type(e).__name__}")

def check_rate_limit(ip):
    """Returns True if this IP is still under today's limit."""
    today = time.strftime("%Y-%m-%d", time.gmtime())
    ip_hash = hashlib.sha256(ip.encode("utf-8")).hexdigest()[:16]
    try:
        resp = table.update_item(
            Key={"pk": f"rate#{today}#{ip_hash}"},
            UpdateExpression="ADD hits :one SET #t = if_not_exists(#t, :ttl)",
            ExpressionAttributeNames={"#t": "ttl"},  # ttl is a reserved word in DynamoDB
            ExpressionAttributeValues={":one": 1, ":ttl": int(time.time()) + 2 * 86400},
            ReturnValues="UPDATED_NEW",
        )
        return int(resp["Attributes"]["hits"]) <= DAILY_LIMIT
    except Exception as e:
        print(f"rate limit check failed: {type(e).__name__}")
        return True  # if DynamoDB fails, let the request through