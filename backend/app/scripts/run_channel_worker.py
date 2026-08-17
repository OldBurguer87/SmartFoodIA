from __future__ import annotations

import logging
import signal
import time

from app.channels.whatsapp.client import WhatsAppCloudClient
from app.channels.whatsapp.queue import WhatsAppQueueProcessor
from app.core.config import settings
from app.database.session import SessionLocal
from app.services.handoff_monitor import HumanHandoffMonitor
from app.services.pix_review_monitor import PixReviewMonitor

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
