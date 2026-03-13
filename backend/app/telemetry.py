"""OpenTelemetry tracing setup.

- Development: console exporter (disabled by default)
- Production: OTLP exporter when OTEL_EXPORTER_OTLP_ENDPOINT is set

Call ``setup_telemetry(app)`` from ``main.py`` once.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def setup_telemetry(app) -> None:  # noqa: ANN001 — FastAPI
    """Configure OpenTelemetry tracing for the FastAPI application."""
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    except ImportError:
        logger.debug("OpenTelemetry packages not installed — tracing disabled")
        return

    resource = Resource.create({"service.name": "graphrag-backend"})
    provider = TracerProvider(resource=resource)

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info("OTEL tracing → OTLP %s", otlp_endpoint)
        except ImportError:
            logger.warning("opentelemetry-exporter-otlp not installed — skipping OTLP")
    elif os.getenv("OTEL_CONSOLE", "").lower() in ("1", "true"):
        from opentelemetry.sdk.trace.export import (
            ConsoleSpanExporter,
            SimpleSpanProcessor,
        )

        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        logger.info("OTEL tracing → console")

    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    logger.info("OpenTelemetry FastAPI instrumentation enabled")
