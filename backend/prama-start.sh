#!/bin/sh
# Prama Monitor start wrapper for iSift.
# Put it in front of your normal start command, for example:
#   sh prama-start.sh python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
#   sh prama-start.sh gunicorn app:app --bind 0.0.0.0:${PORT:-8000}
#   sh prama-start.sh python manage.py runserver 0.0.0.0:${PORT:-8000} --noreload
# Without the Northflank variables (or without the packages) the app starts exactly as before.
if [ -n "$OTEL_EXPORTER_OTLP_ENDPOINT" ] && command -v opentelemetry-instrument >/dev/null 2>&1; then
    export OTEL_SERVICE_NAME="${OTEL_SERVICE_NAME:-isift-api}"
    export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
    export OTEL_EXPORTER_OTLP_COMPRESSION="${OTEL_EXPORTER_OTLP_COMPRESSION:-gzip}"
    export OTEL_TRACES_EXPORTER=otlp
    # Northflank already gives the monitor CPU, memory and error logs; keep within the free plan.
    export OTEL_METRICS_EXPORTER=none
    export OTEL_LOGS_EXPORTER=none
    export OTEL_PYTHON_EXCLUDED_URLS="${OTEL_PYTHON_EXCLUDED_URLS:-ready,health,healthz,static/,assets/,favicon,\.js$,\.css$,\.png$,\.svg$,\.ico$,\.woff2?$}"
    export OTEL_PYTHON_REQUESTS_EXCLUDED_URLS="${OTEL_PYTHON_REQUESTS_EXCLUDED_URLS:-monitor.prama-ai.workers.dev}"
    # Not "parentbased": Northflank's load balancer adds an unsampled trace header to requests.
    export OTEL_TRACES_SAMPLER="${OTEL_TRACES_SAMPLER:-traceidratio}"
    export OTEL_TRACES_SAMPLER_ARG="${OTEL_TRACES_SAMPLER_ARG:-1.0}"
    export OTEL_RESOURCE_ATTRIBUTES="${OTEL_RESOURCE_ATTRIBUTES:-deployment.environment=production}"
    echo "[isift] Prama Monitor tracing on (service $OTEL_SERVICE_NAME)"
    exec opentelemetry-instrument "$@"
fi
echo "[isift] Prama Monitor tracing off (OTEL_EXPORTER_OTLP_ENDPOINT not set or OpenTelemetry not installed)"
exec "$@"
