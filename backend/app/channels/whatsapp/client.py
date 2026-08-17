from __future__ import annotations

from dataclasses import dataclass

import httpx


class WhatsAppSendError(RuntimeError):
    pass


@dataclass(frozen=True)
class DownloadedMedia:
    content: bytes
    mime_type: str | None
    meta_sha256: str | None
    file_size: int


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

    def download_media(
        self,
        *,
        phone_number_id: str,
        media_id: str,
    ) -> DownloadedMedia:
        metadata_url = (
            f"https://graph.facebook.com/{self.graph_api_version}/"
            f"{media_id}"
        )

        headers = {
            "Authorization": f"Bearer {self.access_token}",
        }

        params = {
            "phone_number_id": phone_number_id,
        }

        if self.client is not None:
            metadata_response = self.client.get(
                metadata_url,
                headers=headers,
                params=params,
            )
        else:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                metadata_response = client.get(
                    metadata_url,
                    headers=headers,
                    params=params,
                )

        if metadata_response.is_error:
            raise WhatsAppSendError(
                "Falha ao recuperar URL da mídia: "
                f"HTTP {metadata_response.status_code}: "
                f"{metadata_response.text[:500]}"
            )

        metadata = metadata_response.json()
        media_url = metadata.get("url")

        if not media_url:
            raise WhatsAppSendError(
                "Meta não devolveu URL para a mídia recebida."
            )

        if self.client is not None:
            media_response = self.client.get(
                media_url,
                headers=headers,
            )
        else:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                media_response = client.get(
                    media_url,
                    headers=headers,
                )

        if media_response.is_error:
            raise WhatsAppSendError(
                "Falha ao baixar mídia: "
                f"HTTP {media_response.status_code}: "
                f"{media_response.text[:500]}"
            )

        content = media_response.content

        mime_type = (
            metadata.get("mime_type")
            or media_response.headers.get("content-type")
        )

        return DownloadedMedia(
            content=content,
            mime_type=mime_type,
            meta_sha256=metadata.get("sha256"),
            file_size=len(content),
        )

    def upload_media(
        self,
        *,
        phone_number_id: str,
        file_path: str,
        mime_type: str,
        filename: str,
    ) -> str:
        url = (
            f"https://graph.facebook.com/{self.graph_api_version}/"
            f"{phone_number_id}/media"
        )

        headers = {
            "Authorization": f"Bearer {self.access_token}",
        }

        data = {
            "messaging_product": "whatsapp",
        }

        content = __import__("pathlib").Path(file_path).read_bytes()

        files = {
            "file": (
                filename,
                content,
                mime_type,
            )
        }

        if self.client is not None:
            response = self.client.post(
                url,
                headers=headers,
                data=data,
                files=files,
            )
        else:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    url,
                    headers=headers,
                    data=data,
                    files=files,
                )

        if response.is_error:
            raise WhatsAppSendError(
                "Falha no upload de mídia: "
                f"HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )

        media_id = response.json().get("id")

        if not media_id:
            raise WhatsAppSendError(
                "Meta não devolveu ID da mídia enviada."
            )

        return str(media_id)

    def send_media_by_id(
        self,
        *,
        phone_number_id: str,
        recipient: str,
        media_id: str,
        media_type: str,
        filename: str | None = None,
        caption: str | None = None,
    ) -> str:
        normalized_type = media_type.lower()

        if normalized_type not in {"image", "document"}:
            raise WhatsAppSendError(
                f"Tipo de mídia de saída não suportado: {media_type}"
            )

        url = (
            f"https://graph.facebook.com/{self.graph_api_version}/"
            f"{phone_number_id}/messages"
        )

        media = {
            "id": media_id,
        }

        if filename and normalized_type == "document":
            media["filename"] = filename

        if caption:
            media["caption"] = caption

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": normalized_type,
            normalized_type: media,
        }

        headers = {
            "Authorization": f"Bearer {self.access_token}",
        }

        if self.client is not None:
            response = self.client.post(
                url,
                json=payload,
                headers=headers,
            )
        else:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    url,
                    json=payload,
                    headers=headers,
                )

        if response.is_error:
            raise WhatsAppSendError(
                "Falha ao enviar mídia: "
                f"HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )

        messages = response.json().get("messages") or []

        if not messages or not messages[0].get("id"):
            raise WhatsAppSendError(
                "Meta não devolveu ID da mensagem de mídia."
            )

        return str(messages[0]["id"])

    def send_document(
        self,
        *,
        phone_number_id: str,
        recipient: str,
        document_url: str,
        filename: str,
        caption: str | None = None,
    ) -> str:
        url = (
            f"https://graph.facebook.com/{self.graph_api_version}/"
            f"{phone_number_id}/messages"
        )
        document = {
            "link": document_url,
            "filename": filename,
        }
        if caption:
            document["caption"] = caption

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "document",
            "document": document,
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
            raise WhatsAppSendError(
                "WhatsApp não devolveu o ID do documento enviado."
            )

        return str(messages[0]["id"])

    def send_template(
        self,
        *,
        phone_number_id: str,
        recipient: str,
        template: dict,
    ) -> str:
        url = (
            f"https://graph.facebook.com/{self.graph_api_version}/"
            f"{phone_number_id}/messages"
        )

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "template",
            "template": template,
        }

        headers = {
            "Authorization": f"Bearer {self.access_token}",
        }

        if self.client is not None:
            response = self.client.post(
                url,
                json=payload,
                headers=headers,
            )
        else:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    url,
                    json=payload,
                    headers=headers,
                )

        if response.is_error:
            raise WhatsAppSendError(
                "Falha ao enviar template WhatsApp: "
                f"HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )

        messages = response.json().get("messages") or []

        if not messages or not messages[0].get("id"):
            raise WhatsAppSendError(
                "Meta não devolveu ID da mensagem de template."
            )

        return str(messages[0]["id"])

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
