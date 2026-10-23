import asyncio
import time
from app.core.database import SessionLocal
from app.core.logging import logger
from app.services.webhook_service import process_pending_webhooks
from app.services.device_service import check_and_update_offline_devices

_stop_event = asyncio.Event()


async def run_worker_loop(interval_seconds: float = 3.0):
    """
    Continuous background loop for webhook dispatch retries
    and device heartbeat timeouts.
    """
    logger.info("Webhook & liveness worker loop started.")
    while not _stop_event.is_set():
        db = SessionLocal()
        try:
            # 1. Deliver pending/retrying webhooks
            processed = process_pending_webhooks(db, limit=25)
            if processed > 0:
                logger.debug(f"Worker processed {processed} webhooks")

            # 2. Check offline devices
            check_and_update_offline_devices(db)
        except Exception as e:
            logger.error(f"Worker error in execution loop: {e}", exc_info=True)
        finally:
            db.close()

        try:
            await asyncio.wait_for(_stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            pass
    logger.info("Webhook & liveness worker loop stopped.")


def stop_worker():
    """Signals the worker loop to terminate cleanly."""
    _stop_event.set()


if __name__ == "__main__":
    logger.info("Starting standalone webhook worker process...")
    try:
        asyncio.run(run_worker_loop())
    except KeyboardInterrupt:
        logger.info("Worker process interrupted by user.")
