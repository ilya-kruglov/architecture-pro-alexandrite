"""
Service A - Order Service.

This service simulates an order processing endpoint.
It receives requests and forwards them to Service B (Calculation Service)
with distributed tracing via OpenTelemetry.
"""

import os
import logging
from typing import Dict, Any

from fastapi import FastAPI
import httpx
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# OpenTelemetry configuration
JAEGER_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "http://simplest-collector.observability:4317"
)

# Create resource with service name
resource = Resource(attributes={
    SERVICE_NAME: "service-a"
})

# Setup tracer provider
provider = TracerProvider(resource=resource)
trace.set_tracer_provider(provider)

# Configure OTLP exporter for Jaeger
otlp_exporter = OTLPSpanExporter(
    endpoint=JAEGER_ENDPOINT,
    insecure=True  # Set to False in production with proper certificates
)
span_processor = BatchSpanProcessor(otlp_exporter)
provider.add_span_processor(span_processor)

# Instrument HTTPX for outgoing requests
HTTPXClientInstrumentor().instrument()

# Create FastAPI app
app = FastAPI(
    title="Service A - Order Service",
    description=(
        "Receives order requests and calls calculation service"
    ),
    version="1.0.0"
)

# Instrument FastAPI automatically
FastAPIInstrumentor.instrument_app(app)

# Service B URL
SERVICE_B_URL = os.getenv("SERVICE_B_URL", "http://service-b:8080")


@app.get("/", tags=["Health"])
async def root() -> Dict[str, str]:
    """Health check endpoint."""
    return {"service": "service-a", "status": "healthy"}


@app.get("/order", tags=["Orders"])
async def create_order() -> Dict[str, Any]:
    """
    Simulates order creation and calls Service B for price calculation.

    This endpoint creates a span and propagates the trace context to
    Service B via HTTP headers automatically (handled by instrumented httpx).
    """
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span("create_order") as span:
        span.set_attribute("order.id", "order-12345")
        span.set_attribute("order.customer", "test-customer")

        logger.info(
            "Creating new order, will call service-b for calculation"
        )

        try:
            # Call Service B with trace context propagation
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(f"{SERVICE_B_URL}/calculate")
                response.raise_for_status()
                calculation_result = response.json()

                span.set_attribute("calculation.success", True)
                span.set_attribute(
                    "calculation.price",
                    calculation_result.get("price", 0)
                )

                logger.info(
                    f"Calculation result received: {calculation_result}"
                )

                trace_id = format(
                    span.get_span_context().trace_id, '032x'
                )

                return {
                    "order_id": "order-12345",
                    "status": "created",
                    "calculation": calculation_result,
                    "trace_id": trace_id
                }

        except httpx.HTTPError as e:
            span.set_attribute("calculation.success", False)
            span.set_attribute("error", str(e))
            span.record_exception(e)
            logger.error(f"Failed to call service-b: {e}")

            trace_id = format(
                span.get_span_context().trace_id, '032x'
            )

            return {
                "order_id": "order-12345",
                "status": "error",
                "error": f"Calculation service unavailable: {str(e)}",
                "trace_id": trace_id
            }


@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, str]:
    """Kubernetes readiness/liveness probe endpoint."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
