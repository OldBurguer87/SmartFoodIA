from __future__ import annotations

import logging
import signal
import time

from app.channels.whatsapp.client import WhatsAppCloudClient
from app.channels.whatsapp.queue import WhatsAppQueueProcessor
from app.core.config import settings
from app.database.session import SessionLocal
from app.services.handoff_monitor import HumanHandoffMonitor
from app.services.conversation_media_retention import (
    ConversationMediaRetentionService,
)
from app.services.pix_review_monitor import PixReviewMonitor
from app.services.pix_receipt_retention import (
    PixReceiptRetentionService,
)
from app.services.pix_shift_closing import (
    PixShiftClosingService,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("smartfoodia.channel-worker")
_running = True


def stop_worker(*_) -> None:
    global _running
    _running = False


def make_client() -> WhatsAppCloudClient:
    if not settings.whatsapp_access_token:
        raise RuntimeError("WHATSAPP_ACCESS_TOKEN não configurado.")
    return WhatsAppCloudClient(
        access_token=settings.whatsapp_access_token,
        graph_api_version=settings.whatsapp_graph_api_version,
        timeout_seconds=settings.whatsapp_timeout_seconds,
    )


def main() -> None:
    signal.signal(signal.SIGTERM, stop_worker)
    signal.signal(signal.SIGINT, stop_worker)

    processor = WhatsAppQueueProcessor(
        client_factory=make_client,
        max_attempts=settings.channel_worker_max_attempts,
    )
    handoff_monitor = HumanHandoffMonitor()
    pix_review_monitor = PixReviewMonitor()
    pix_retention = PixReceiptRetentionService()
    conversation_media_retention = ConversationMediaRetentionService()
    pix_shift_closing = PixShiftClosingService()

    retention_interval = max(
        60,
        settings.payment_receipt_retention_interval_seconds,
    )
    next_retention_run = (
        time.monotonic() + retention_interval
    )

    conversation_media_retention_interval = max(
        60,
        settings.conversation_media_retention_interval_seconds,
    )
    next_conversation_media_retention_run = time.monotonic()

    logger.info("Worker de canais iniciado.")

    while _running:
        try:
            with SessionLocal() as db:
                handoff = handoff_monitor.run_once(
                    db,
                    limit=settings.channel_worker_batch_size,
                )
                pix_review = pix_review_monitor.run_once(
                    db,
                    limit=settings.channel_worker_batch_size,
                )

                retention = None
                now_monotonic = time.monotonic()

                if now_monotonic >= next_retention_run:
                    next_retention_run = (
                        now_monotonic + retention_interval
                    )
                    retention = pix_retention.run_once(
                        db,
                        limit=settings.channel_worker_batch_size,
                    )

                conversation_media_retention_result = None

                if (
                    now_monotonic
                    >= next_conversation_media_retention_run
                ):
                    next_conversation_media_retention_run = (
                        now_monotonic
                        + conversation_media_retention_interval
                    )
                    conversation_media_retention_result = (
                        conversation_media_retention.run_once(
                            db,
                            limit=settings.channel_worker_batch_size,
                        )
                    )

                closing = None
                try:
                    closing = pix_shift_closing.run_once(db)
                except Exception:
                    logger.exception(
                        "Falha no fechamento PIX do turno."
                    )

                result = processor.run_once(
                    db,
                    limit=settings.channel_worker_batch_size,
                )

            if handoff.reminded or handoff.resumed or handoff.failed:
                logger.info("Monitor de atendimento humano: %s", handoff)

            if (
                pix_review.notified_receipts
                or pix_review.notified_staff
            ):
                logger.info(
                    "Monitor de revisão PIX: %s",
                    pix_review,
                )

            if retention is not None and (
                retention.purged
                or retention.files_missing
                or retention.skipped_missing_secret
                or retention.skipped_invalid_path
                or retention.file_delete_errors
                or retention.file_restore_errors
                or retention.db_errors
            ):
                logger.info(
                    "Retenção de comprovantes PIX: %s",
                    retention,
                )

            if (
                conversation_media_retention_result is not None
                and (
                    conversation_media_retention_result.purged
                    or conversation_media_retention_result.files_missing
                    or conversation_media_retention_result.skipped_invalid_path
                    or conversation_media_retention_result.file_delete_errors
                    or conversation_media_retention_result.file_restore_errors
                    or conversation_media_retention_result.db_errors
                )
            ):
                logger.info(
                    "Retenção de mídias da conversa: %s",
                    conversation_media_retention_result,
                )

            if (
                closing is not None
                and closing.queued_messages
            ):
                logger.info(
                    "Fechamento PIX do turno: %s",
                    closing,
                )

            processed = (
                result.events_processed
                + result.events_retried
                + result.events_dead
                + result.outbound_sent
                + result.outbound_retried
                + result.outbound_dead
            )
            if processed:
                logger.info("Rodada concluída: %s", result)
        except Exception:
            logger.exception("Falha na rodada do worker.")

        if _running:
            time.sleep(settings.channel_worker_poll_seconds)

    logger.info("Worker de canais encerrado.")


if __name__ == "__main__":
    main()
