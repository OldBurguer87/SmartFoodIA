from __future__ import annotations

import httpx


class WhatsAppSendError(RuntimeError):
    pass


class WhatsAppCloudClient:
    def __init__(
        self,
        *,
        access_token: str,
        graph_api_version: str,
        timeout_seconds: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.access_token = access_token
        self.graph_api_version = graph_api_version
        self.timeout_seconds = timeout_seconds
        self.client = client

    def send_text(
        self,
        *,
        phone_number_id: str,
        recipient: str,
        text: str,
    ) -> str:
        url = (
            f"https://graph.facebook.com/{self.graph_api_version}/"
            f"{phone_number_id}/messages"
        )
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
        headers = {"Authorization": f"Bearer {self.access_token}"}

        if self.client is not None:
            response = self.client.post(url, json=payload, headers=headers)
        else:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(url, json=payload, headers=headers)

        if response.is_error:
            raise WhatsAppSendError(
                f"WhatsApp respondeu HTTP {response.status_code}: {response.text[:500]}"
            )
        data = response.json()
        messages = data.get("messages") or []
        if not messages or not messages[0].get("id"):
            raise WhatsAppSendError("WhatsApp não devolveu o ID da mensagem enviada.")
        return str(messages[0]["id"])
