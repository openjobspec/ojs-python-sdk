"""
OpenTelemetry middleware for the OJS Python SDK.

Provides execution middleware that instruments job processing with
OpenTelemetry traces and metrics, following the OJS Observability spec.

Usage::

    from ojs import OJSWorker
    from ojs.otel import opentelemetry_middleware

    worker = OJSWorker(url="http://localhost:8080", queues=["default"])
    worker.add_middleware(opentelemetry_middleware())

Prerequisites::

    pip install opentelemetry-api

See: spec/ojs-observability.md
"""

from __future__ import annotations

import time
from typing import Any, Callable, Coroutine

INSTRUMENTATION_NAME = "ojs-python-sdk"


def opentelemetry_middleware(
    tracer_provider: Any | None = None,
    meter_provider: Any | None = None,
) -> Callable:
    """Create OpenTelemetry execution middleware.

    Creates a CONSUMER span for each job and records:
    - ``ojs.job.completed`` (counter)
    - ``ojs.job.failed`` (counter)
    - ``ojs.job.duration`` (histogram, seconds)

    Args:
        tracer_provider: OpenTelemetry TracerProvider. Defaults to global.
        meter_provider: OpenTelemetry MeterProvider. Defaults to global.

    Returns:
        Async execution middleware function.
    """
    try:
        from opentelemetry import trace, metrics  # type: ignore[import-untyped]
        from opentelemetry.trace import StatusCode, SpanKind  # type: ignore[import-untyped]
    except ImportError:
        raise ImportError(
            "opentelemetry-api is required for OTel middleware. "
            "Install it with: pip install opentelemetry-api"
        )

    tp = tracer_provider or trace.get_tracer_provider()
    mp = meter_provider or metrics.get_meter_provider()

    tracer = tp.get_tracer(INSTRUMENTATION_NAME)
    meter = mp.get_meter(INSTRUMENTATION_NAME)

    jobs_completed = meter.create_counter(
        "ojs.job.completed",
        description="Number of jobs completed successfully",
        unit="{job}",
    )
    jobs_failed = meter.create_counter(
        "ojs.job.failed",
        description="Number of jobs that failed",
        unit="{job}",
    )
    job_duration = meter.create_histogram(
        "ojs.job.duration",
        description="Job execution duration in seconds",
        unit="s",
    )

    async def middleware(
        ctx: Any,
        next_handler: Callable[[], Coroutine[Any, Any, Any]],
    ) -> Any:
        metric_attrs = {
            "ojs.job.type": ctx.job.type,
            "ojs.job.queue": ctx.job.queue,
        }
        span_attrs = {
            "messaging.system": "ojs",
            "messaging.operation": "process",
            "ojs.job.type": ctx.job.type,
            "ojs.job.id": ctx.job.id,
            "ojs.job.queue": ctx.job.queue,
            "ojs.job.attempt": ctx.job.attempt,
        }

        with tracer.start_as_current_span(
            f"process {ctx.job.type}",
            kind=SpanKind.CONSUMER,
            attributes=span_attrs,
        ) as span:
            start = time.monotonic()
            try:
                result = await next_handler()
                elapsed = time.monotonic() - start

                span.set_status(StatusCode.OK)
                job_duration.record(elapsed, metric_attrs)
                jobs_completed.add(1, metric_attrs)
                return result

            except Exception as exc:
                elapsed = time.monotonic() - start

                span.record_exception(exc)
                span.set_status(StatusCode.ERROR, str(exc))
                job_duration.record(elapsed, metric_attrs)
                jobs_failed.add(1, metric_attrs)
                raise

    return middleware
