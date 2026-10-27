"""Gateway-Harness Unified LiteLLM Handler combining Capture, Routing, and Metrics."""

from litellm.integrations.custom_logger import CustomLogger

from gateway_harness.capture.hook import CaptureMixin
from gateway_harness.routing.hook import RoutingMixin


class GatewayHarnessHandler(CaptureMixin, RoutingMixin, CustomLogger):
    """Integrated callback handler for LiteLLM proxy."""

    def __init__(self) -> None:
        super().__init__()


# Singleton export for litellm custom callbacks
handler = GatewayHarnessHandler()
