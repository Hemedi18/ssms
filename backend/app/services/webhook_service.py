import ipaddress
import json
import random
import socket
import urllib.parse
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
import httpx
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_

from app.core.config import settings
from app.core.logging import logger
from app.core.security import sign_webhook_payload
from app.models.webhook import WebhookSubscription, WebhookDelivery


def validate_webhook_url(url: str, allow_local: bool = False) -> None:
    """
    Validates webhook URL structure and enforces strict SSRF restrictions.
    Rejects private, loopback, multicast, link-local, and cloud metadata addresses unless allow_local is True.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Webhook URL must use http or https scheme")
    if not parsed.hostname:
        raise ValueError("Webhook URL has no valid host")

    if not allow_local:
        if parsed.scheme != "https":
            raise ValueError("Public webhook URLs must use HTTPS")

        # Resolve hostname to check IP range
        try:
            addr_info = socket.getaddrinfo(parsed.hostname, None)
            for item in addr_info:
                ip_str = item[4][0]
                ip_obj = ipaddress.ip_address(ip_str)
                if (
                    ip_obj.is_private
                    or ip_obj.is_loopback
                    or ip_obj.is_link_local
                    or ip_obj.is_multicast
                    or ip_obj.is_reserved
                    or ip_str == "169.254.169.254"
                ):
                    raise ValueError(f"Webhook destination resolves to a forbidden IP address: {ip_str}")
        except socket.gaierror:
            raise ValueError(f"Cannot resolve webhook host: '{parsed.hostname}'")


def queue_event(
    db: Session,
    event_type: str,
    data: Dict[str, Any],
    tenant_id: Optional[str] = None,
) -> List[WebhookDelivery]:
    """
    Finds all active subscriptions listening to event_type (scoped to tenant or global),
    creates WebhookDelivery records.
    """
    event_id = str(uuid.uuid4())
    event_payload = {
        "id": event_id,
        "type": event_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }

    query = select(WebhookSubscription).where(WebhookSubscription.is_active == True)
    if tenant_id:
        query = query.where(
            or_(
                WebhookSubscription.tenant_id == tenant_id,
                WebhookSubscription.tenant_id == None,
            )
        )

    subscriptions = db.scalars(query).all()

    deliveries = []
    for sub in subscriptions:
        if event_type in sub.events or "*" in sub.events:
            delivery = WebhookDelivery(
                subscription_id=sub.id,
                event_id=event_id,
                event_type=event_type,
                payload=event_payload,
                status="pending",
                attempts=0,
                next_retry_at=datetime.now(timezone.utc),
            )
            db.add(delivery)
            deliveries.append(delivery)

    if deliveries:
        db.commit()
        for d in deliveries:
            db.refresh(d)
        logger.info(f"Queued webhook event [{event_type}] for {len(deliveries)} subscriptions")
    return deliveries


def deliver_webhook_sync(
    db: Session, delivery: WebhookDelivery, client: Optional[httpx.Client] = None
) -> WebhookDelivery:
    """
    Performs delivery attempt of a single WebhookDelivery record.
    Enforces follow_redirects=False to mitigate SSRF DNS-rebinding or redirect pivoting.
    """
    sub = delivery.subscription
    if not sub or not sub.is_active:
        delivery.status = "failed"
        delivery.error_message = "Subscription inactive or removed"
        db.commit()
        return delivery

    payload_str = json.dumps(delivery.payload, separators=(",", ":"), ensure_ascii=False)
    payload_bytes = payload_str.encode("utf-8")
    timestamp_str = datetime.now(timezone.utc).isoformat()
    signature = sign_webhook_payload(payload_bytes, sub.secret)

    headers = {
        "Content-Type": "application/json",
        "User-Agent": f"SimSmsGateway/{settings.VERSION}",
        "X-Event-ID": delivery.event_id,
        "X-Event-Type": delivery.event_type,
        "X-Timestamp": timestamp_str,
        "X-Signature-SHA256": signature,
        "X-Gateway-Signature": f"sha256={signature}",
    }

    should_close_client = False
    if client is None:
        client = httpx.Client(timeout=settings.WEBHOOK_TIMEOUT_SECONDS, follow_redirects=False)
        should_close_client = True

    try:
        delivery.attempts += 1
        response = client.post(sub.url, content=payload_bytes, headers=headers)
        delivery.response_status_code = response.status_code
        delivery.response_body = (response.text or "")[:500]

        if 200 <= response.status_code < 300:
            delivery.status = "delivered"
            delivery.delivered_at = datetime.now(timezone.utc)
            delivery.error_message = None
            delivery.next_retry_at = None
            logger.info(
                f"Webhook [{delivery.id}] delivered to {sub.url} status={response.status_code}"
            )
        else:
            _handle_delivery_failure(
                delivery,
                f"HTTP status {response.status_code}: {(response.text or '')[:100]}",
            )
    except Exception as exc:
        _handle_delivery_failure(delivery, str(exc))
    finally:
        if should_close_client:
            client.close()

    db.commit()
    db.refresh(delivery)
    return delivery


def process_pending_webhooks(db: Session, limit: int = 25) -> int:
    """Processes overdue or pending webhook deliveries."""
    now = datetime.now(timezone.utc)
    deliveries = db.scalars(
        select(WebhookDelivery)
        .where(
            and_(
                WebhookDelivery.status == "pending",
                or_(
                    WebhookDelivery.next_retry_at == None,
                    WebhookDelivery.next_retry_at <= now,
                ),
            )
        )
        .limit(limit)
    ).all()

    if not deliveries:
        return 0

    with httpx.Client(timeout=settings.WEBHOOK_TIMEOUT_SECONDS, follow_redirects=False) as client:
        for delivery in deliveries:
            try:
                deliver_webhook_sync(db, delivery, client=client)
            except Exception as e:
                logger.error(f"Error delivering webhook {delivery.id}: {e}")

    return len(deliveries)


def _handle_delivery_failure(delivery: WebhookDelivery, error_desc: str) -> None:
    """Calculates exponential backoff for retrying webhook dispatch."""
    delivery.error_message = error_desc
    if delivery.attempts >= settings.WEBHOOK_MAX_RETRIES:
        delivery.status = "failed"
        delivery.next_retry_at = None
        logger.warning(
            f"Webhook [{delivery.id}] permanently failed after {delivery.attempts} attempts: {error_desc}"
        )
    else:
        # Exponential backoff: base_seconds * (2 ** (attempts - 1)) + jitter
        base_seconds = 10
        backoff = base_seconds * (2 ** (delivery.attempts - 1))
        jitter = random.uniform(0.5, 2.0)
        delay_seconds = backoff + jitter
        delivery.next_retry_at = datetime.now(timezone.utc) + timedelta(
            seconds=delay_seconds
        )
        logger.info(
            f"Webhook [{delivery.id}] attempt {delivery.attempts} failed. Retry in {delay_seconds:.1f}s"
        )
