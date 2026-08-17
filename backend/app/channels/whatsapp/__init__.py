from app.channels.whatsapp.client import WhatsAppCloudClient

__all__ = [
    "WhatsAppCloudClient",
    "WhatsAppGatewayService",
]


def __getattr__(name):
    if name == "WhatsAppGatewayService":
        from app.channels.whatsapp.service import WhatsAppGatewayService
        return WhatsAppGatewayService

    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )
