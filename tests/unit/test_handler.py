import io
import json
import urllib.error

import pytest

import handler


class FakeResponse(io.BytesIO):
    def __init__(self, body, status=200):
        super().__init__(body.encode())
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def fake_urlopen(body="", status=200, exc=None):
    def _urlopen(request, timeout):
        if exc:
            raise exc
        return FakeResponse(body, status)
    return _urlopen


def test_healthy_site(monkeypatch):
    monkeypatch.setattr(handler.urllib.request, "urlopen", fake_urlopen("<h1>Shobhin Gowrisankar</h1>"))
    result = handler.check("https://example.com", "Shobhin Gowrisankar")
    assert result["up"] is True
    assert result["status"] == 200
    assert result["error"] is None
    assert result["latency_ms"] >= 0


def test_missing_expected_text_is_down(monkeypatch):
    monkeypatch.setattr(handler.urllib.request, "urlopen", fake_urlopen("<h1>Maintenance</h1>"))
    result = handler.check("https://example.com", "Shobhin Gowrisankar")
    assert result["up"] is False
    assert result["error"] == "expected text not found"


def test_http_error_is_down(monkeypatch):
    err = urllib.error.HTTPError("https://example.com", 503, "Service Unavailable", {}, None)
    monkeypatch.setattr(handler.urllib.request, "urlopen", fake_urlopen(exc=err))
    result = handler.check("https://example.com")
    assert result["up"] is False
    assert result["status"] == 503
    assert result["error"] == "HTTP 503"


def test_network_error_is_down(monkeypatch):
    monkeypatch.setattr(handler.urllib.request, "urlopen", fake_urlopen(exc=urllib.error.URLError("timed out")))
    result = handler.check("https://example.com")
    assert result["up"] is False
    assert result["status"] is None
    assert "URLError" in result["error"]


def test_emf_record_shape():
    record = handler.emf_record(
        {"url": "https://example.com", "up": True, "status": 200, "latency_ms": 42, "error": None}, "UptimeMonitor"
    )
    directive = record["_aws"]["CloudWatchMetrics"][0]
    assert directive["Namespace"] == "UptimeMonitor"
    assert directive["Dimensions"] == [["Url"]]
    assert {m["Name"] for m in directive["Metrics"]} == {"Up", "LatencyMs"}
    assert record["Up"] == 1 and record["LatencyMs"] == 42 and record["Url"] == "https://example.com"


def test_handler_prints_emf_and_returns_result(monkeypatch, capsys):
    monkeypatch.setenv("TARGET_URL", "https://example.com")
    monkeypatch.setenv("EXPECTED_TEXT", "hello")
    monkeypatch.setattr(handler.urllib.request, "urlopen", fake_urlopen("hello world"))
    result = handler.handler({}, None)
    logged = json.loads(capsys.readouterr().out.strip())
    assert result["up"] is True
    assert logged["Up"] == 1
    assert "_aws" in logged
