"""Prama Monitor helper for iSift: AI token usage reporting and a start-up check.

Settings come from the same environment variables as OpenTelemetry (set in Northflank):
  OTEL_EXPORTER_OTLP_ENDPOINT = https://monitor.prama-ai.workers.dev/api/otlp
  OTEL_EXPORTER_OTLP_HEADERS  = Authorization=Bearer <INGEST_TOKEN>
  PRAMA_APP_NAME              = isift

Use after each AI call (works with Groq, OpenAI, Anthropic and any OpenAI-compatible client):
    from prama_monitor import report_openai, report_anthropic, report_ai_usage
    resp = groq_client.chat.completions.create(...);   report_openai(resp, provider="groq")
    resp = openai_client.chat.completions.create(...); report_openai(resp, provider="openai")
    resp = anthropic_client.messages.create(...);      report_anthropic(resp)
    # raw HTTP (requests): data = r.json();            report_openai(data, provider="groq")

Reporting runs in a background thread and never raises, so it cannot slow down or break the app.
The monitor works out the cost from its own price list.
"""
import os
import threading
import time
from urllib.parse import unquote

try:
    import requests
except ImportError:  # requests is optional; urllib is used instead
    requests = None

APP_NAME = os.environ.get("PRAMA_APP_NAME", "isift")


def _settings():
    token = os.environ.get("PRAMA_INGEST_TOKEN", "").strip()
    if not token:
        for part in unquote(os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", "")).split(","):
            k, _, v = part.partition("=")
            if k.strip().lower() == "authorization" and v.strip().lower().startswith("bearer"):
                token = v.strip()[6:].strip()
    url = os.environ.get("PRAMA_AI_USAGE_URL", "").strip()
    if not url:
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip().rstrip("/")
        if endpoint.endswith("/api/otlp"):
            url = endpoint[: -len("/otlp")] + "/ingest/ai-usage"
    return url, token


def _post(url, token, body):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if requests:
        return requests.post(url, json=body, timeout=8, headers=headers).status_code
    import json, urllib.request, urllib.error
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def _trace_id():
    try:
        from opentelemetry import trace
        ctx = trace.get_current_span().get_span_context()
        return format(ctx.trace_id, "032x") if ctx and ctx.trace_id else None
    except Exception:
        return None


def report_ai_usage(provider, model, input_tokens, output_tokens, duration_ms=None, operation="chat", app=None, ratelimit=None):
    """Call after each AI request. Does nothing if Prama Monitor is not configured."""
    url, token = _settings()
    if not url or not token:
        return
    event = {"app": app or APP_NAME, "provider": provider, "model": model, "operation": operation,
             "input_tokens": int(input_tokens or 0), "output_tokens": int(output_tokens or 0),
             "duration_ms": duration_ms, "trace_id": _trace_id()}
    if ratelimit:
        event["ratelimit"] = ratelimit  # Groq's own "requests left today", shown in Prama Monitor

    def send():
        try:
            code = _post(url, token, event)
            if code != 200:
                print(f"[{APP_NAME}] Prama AI usage report: HTTP {code}", flush=True)
        except Exception as e:
            print(f"[{APP_NAME}] Prama AI usage report failed: {e}", flush=True)
    threading.Thread(target=send, daemon=True).start()


def _get(o, k, default=None):
    return o.get(k, default) if isinstance(o, dict) else getattr(o, k, default)


def report_openai(resp, provider="openai", started_at=None, operation="chat", headers=None):
    """For OpenAI-style replies (Groq, OpenAI, Together, Mistral, ...): SDK object or parsed JSON.
    headers (optional): the HTTP response headers, so the monitor shows Groq's own "requests left today".
    With raw HTTP: report_openai(r.json(), "groq", headers=r.headers). With the groq SDK:
        raw = client.chat.completions.with_raw_response.create(...); resp = raw.parse()
        report_openai(resp, "groq", headers=raw.headers)"""
    try:
        usage = _get(resp, "usage") or {}
        report_ai_usage(provider, _get(resp, "model", "unknown"), _get(usage, "prompt_tokens", 0), _get(usage, "completion_tokens", 0),
                        duration_ms=int((time.time() - started_at) * 1000) if started_at else None, operation=operation,
                        ratelimit=_ratelimit(headers))
    except Exception:
        pass


def _ratelimit(headers):
    try:
        if headers is None:
            return None
        out = {k: headers.get(f"x-ratelimit-{h}") for k, h in (("remaining_requests", "remaining-requests"), ("limit_requests", "limit-requests"),
                                                               ("remaining_tokens", "remaining-tokens"), ("limit_tokens", "limit-tokens"))}
        return out if any(v is not None for v in out.values()) else None
    except Exception:
        return None


def report_anthropic(resp, started_at=None, operation="chat"):
    """For Anthropic `messages.create` replies."""
    try:
        usage = _get(resp, "usage") or {}
        report_ai_usage("anthropic", _get(resp, "model", "unknown"), _get(usage, "input_tokens", 0), _get(usage, "output_tokens", 0),
                        duration_ms=int((time.time() - started_at) * 1000) if started_at else None, operation=operation)
    except Exception:
        pass


def log_tracing_status():
    """Prints one line in the Northflank logs saying whether everything is connected:
    "[isift] Prama Monitor check: tracing ON, test trace sent OK, AI usage reporting OK"."""
    def check():
        try:
            if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
                print(f"[{APP_NAME}] Prama Monitor check: tracing off (OTEL_EXPORTER_OTLP_ENDPOINT not set)", flush=True)
                return
            sent = "skipped (OpenTelemetry not installed)"
            active = False
            try:
                from opentelemetry import trace
                active = hasattr(trace.get_tracer_provider(), "force_flush")
                from opentelemetry.sdk.resources import Resource
                from opentelemetry.sdk.trace import TracerProvider
                from opentelemetry.sdk.trace.export import SpanExportResult
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
                span = TracerProvider(resource=Resource.create()).get_tracer("prama.startup").start_span("prama-monitor startup check")
                span.end()
                sent = "OK" if OTLPSpanExporter().export([span]) == SpanExportResult.SUCCESS else "FAILED (check the token and address)"
            except Exception as e:
                sent = f"FAILED ({e})"
            url, token = _settings()
            ai = "not set up"
            if url and token:
                try:
                    code = _post(url, token, [])   # empty list = connection test (answers 400 when the token is right)
                    ai = "OK" if code in (200, 400) else f"FAILED (HTTP {code})"
                except Exception as e:
                    ai = f"FAILED ({e})"
            print(f"[{APP_NAME}] Prama Monitor check: tracing {'ON' if active else 'OFF'}, test trace sent {sent}, AI usage reporting {ai}", flush=True)
        except Exception as e:
            print(f"[{APP_NAME}] Prama Monitor check failed: {e}", flush=True)
    threading.Thread(target=check, daemon=True).start()
