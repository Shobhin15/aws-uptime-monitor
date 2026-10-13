"""Uptime checker Lambda.

Fetches a URL, checks the status code and (optionally) that the page contains
some expected text, then writes the result as a CloudWatch Embedded Metric
Format (EMF) log line. CloudWatch turns that log line into two metrics,
Up (1 or 0) and LatencyMs, without any extra API calls or IAM permissions.
"""
import json
import os
import time
import urllib.error
import urllib.request

MAX_BODY_BYTES = 1_000_000


def check(url, expected_text="", timeout=10):
    """Return a dict describing whether `url` is healthy."""
    start = time.monotonic()
    status, up, error = None, False, None
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "aws-uptime-monitor/1.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            body = response.read(MAX_BODY_BYTES).decode("utf-8", errors="replace")
        if status != 200:
            error = f"unexpected status {status}"
        elif expected_text and expected_text not in body:
            error = "expected text not found"
        else:
            up = True
    except urllib.error.HTTPError as exc:
        status, error = exc.code, f"HTTP {exc.code}"
    except Exception as exc:  # timeouts, DNS failures, TLS errors
        error = f"{type(exc).__name__}: {exc}"
    latency_ms = round((time.monotonic() - start) * 1000)
    return {"url": url, "up": up, "status": status, "latency_ms": latency_ms, "error": error}


def emf_record(result, namespace):
    """Build an Embedded Metric Format log record for one check result."""
    return {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": namespace,
                    "Dimensions": [["Url"]],
                    "Metrics": [
                        {"Name": "Up", "Unit": "Count"},
                        {"Name": "LatencyMs", "Unit": "Milliseconds"},
                    ],
                }
            ],
        },
        "Url": result["url"],
        "Up": 1 if result["up"] else 0,
        "LatencyMs": result["latency_ms"],
        "StatusCode": result["status"],
        "Error": result["error"],
    }


def handler(event, context):
    result = check(
        url=os.environ["TARGET_URL"],
        expected_text=os.environ.get("EXPECTED_TEXT", ""),
        timeout=float(os.environ.get("TIMEOUT_SECONDS", "10")),
    )
    print(json.dumps(emf_record(result, os.environ.get("METRIC_NAMESPACE", "UptimeMonitor"))))
    return result
