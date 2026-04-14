"""
Service B - Calculation Service.

This service simulates price calculation for jewelry orders.
It receives trace context from upstream services and creates child spans.
"""

import os
import logging
import random
import time
from typing import Dict, Any

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
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
    SERVICE_NAME: "service-b"
})

# Setup tracer provider
provider = TracerProvider(resource=resource)
trace.set_tracer_provider(provider)

# Configure OTLP exporter for Jaeger
otlp_exporter = OTLPSpanExporter(
    endpoint=JAEGER_ENDPOINT,
    insecure=True
)
span_processor = BatchSpanProcessor(otlp_exporter)
provider.add_span_processor(span_processor)

# Create FastAPI app
app = FastAPI(
    title="Service B - Calculation Service",
    description=(
        "Calculates jewelry manufacturing price based on 3D model complexity"
    ),
    version="1.0.0"
)

# Instrument FastAPI automatically
FastAPIInstrumentor.instrument_app(app)


def simulate_calculation() -> Dict[str, Any]:
    """Simulate complex price calculation with variable duration."""
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span("simulate_calculation") as span:
        # Simulate different calculation phases
        with tracer.start_as_current_span("parse_3d_model"):
            time.sleep(0.1)
            polygon_count = random.randint(1000, 100000)
            span.set_attribute("model.polygon_count", polygon_count)

        with tracer.start_as_current_span("calculate_material_cost"):
            time.sleep(0.15)
            material_cost = random.uniform(500, 5000)
            span.set_attribute("material.cost_rub", material_cost)

        with tracer.start_as_current_span("calculate_labor_cost"):
            time.sleep(0.2)
            labor_hours = polygon_count / 10000.0
            labor_cost = labor_hours * 1500.0
            span.set_attribute("labor.hours", labor_hours)
            span.set_attribute("labor.cost_rub", labor_cost)

        total_price = material_cost + labor_cost + 2000.0

        span.set_attribute("calculation.total_price", total_price)
        span.set_attribute("calculation.currency", "RUB")

        return {
            "price": round(total_price, 2),
            "currency": "RUB",
            "polygon_count": polygon_count,
            "estimated_hours": round(labor_hours, 2),
            "breakdown": {
                "material": round(material_cost, 2),
                "labor": round(labor_cost, 2),
                "markup": 2000.0
            }
        }


@app.get("/", tags=["Health"])
async def root() -> Dict[str, str]:
    """Health check endpoint."""
    return {"service": "service-b", "status": "healthy"}


@app.get("/calculate", tags=["Calculation"])
async def calculate_price() -> Dict[str, Any]:
    """
    Calculate the manufacturing price for a jewelry order.

    This endpoint receives trace context from upstream services
    and creates detailed child spans for each calculation step.
    """
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span("calculate_price_endpoint") as span:
        logger.info("Starting price calculation")

        try:
            result = simulate_calculation()

            span.set_attribute("calculation.success", True)
            span.set_attribute("calculation.price", result["price"])

            logger.info(
                f"Calculation completed: {result['price']} RUB"
            )

            # Include trace ID in response for debugging
            result["trace_id"] = format(
                span.get_span_context().trace_id, '032x'
            )

            return result

        except Exception as e:
            span.set_attribute("calculation.success", False)
            span.set_attribute("error", str(e))
            span.record_exception(e)
            logger.error(f"Calculation failed: {e}")

            return {
                "error": f"Calculation failed: {str(e)}",
                "trace_id": format(
                    span.get_span_context().trace_id, '032x'
                )
            }


@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, str]:
    """Kubernetes readiness/liveness probe endpoint."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
