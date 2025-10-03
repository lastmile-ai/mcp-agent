import logging
from mcp_agent.config import get_settings

logger = logging.getLogger(__name__)


def send_usage_data():
    config = get_settings()
    if not config.usage_telemetry.enabled:
        logger.info("Usage tracking is disabled")
        return

    # TODO: saqadri - implement usage tracking
    # data = {"installation_id": str(uuid.uuid4()), "version": "0.1.0"}
    # try:
    #     requests.post("https://telemetry.example.com/usage", json=data, timeout=2)
    # except:
    #     pass
