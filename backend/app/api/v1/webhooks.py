from typing import List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from app.api.deps import get_db, require_scope
from app.core.config import settings
from app.core.security import generate_webhook_secret
from app.models.api_key import ApiKey
from app.models.webhook import WebhookSubscription, WebhookDelivery
from app.schemas.webhook import (
    WebhookSubscriptionCreate,
    WebhookSubscriptionUpdate,
    WebhookSubscriptionResponse,
    WebhookDeliveryResponse,
    SUPPORTED_EVENTS,
)
from app.services.webhook_service import (
    validate_webhook_url,
    deliver_webhook_sync,
)
from app.services.audit_service import record_audit_event

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("", response_model=WebhookSubscriptionResponse, status_code=status.HTTP_201_CREATED)
def create_subscription(
    payload: WebhookSubscriptionCreate,
    request: Request,
    api_key: ApiKey = Depends(require_scope("webhooks:manage")),
    db: Session = Depends(get_db),
):
    """Creates a new webhook subscription with SSRF validation and signing secret."""
    try:
        validate_webhook_url(payload.url, allow_local=settings.WEBHOOK_ALLOW_LOCAL_URLS)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Validate events
    invalid_events = [e for e in payload.events if e not in SUPPORTED_EVENTS and e != "*"]
    if invalid_events:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported events: {invalid_events}. Supported events are: {SUPPORTED_EVENTS}",
        )

    secret = payload.secret or generate_webhook_secret()
    sub = WebhookSubscription(
        url=payload.url,
        secret=secret,
        events=payload.events,
        is_active=True,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)

    client_ip = request.client.host if request.client else None
    record_audit_event(
        db,
        action="webhook.create",
        actor_type="api_key",
        actor_id=api_key.id,
        details={"subscription_id": sub.id, "url": sub.url, "events": sub.events},
        ip_address=client_ip,
    )

    return sub


@router.get("", response_model=List[WebhookSubscriptionResponse])
def list_subscriptions(
    api_key: ApiKey = Depends(require_scope("webhooks:manage")),
    db: Session = Depends(get_db),
):
    """Lists all configured webhook subscriptions."""
    return db.scalars(select(WebhookSubscription).order_by(WebhookSubscription.created_at.desc())).all()


@router.get("/{subscription_id}", response_model=WebhookSubscriptionResponse)
def get_subscription(
    subscription_id: str,
    api_key: ApiKey = Depends(require_scope("webhooks:manage")),
    db: Session = Depends(get_db),
):
    """Retrieves details of a webhook subscription."""
    sub = db.get(WebhookSubscription, subscription_id)
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook subscription '{subscription_id}' not found",
        )
    return sub


@router.delete("/{subscription_id}")
def delete_subscription(
    subscription_id: str,
    api_key: ApiKey = Depends(require_scope("webhooks:manage")),
    db: Session = Depends(get_db),
):
    """Deletes a webhook subscription and related deliveries."""
    sub = db.get(WebhookSubscription, subscription_id)
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook subscription '{subscription_id}' not found",
        )
    db.delete(sub)
    db.commit()
    return {"status": "success", "message": f"Webhook subscription '{subscription_id}' removed"}


@router.get("/{subscription_id}/deliveries", response_model=List[WebhookDeliveryResponse])
def get_subscription_deliveries(
    subscription_id: str,
    limit: int = 50,
    api_key: ApiKey = Depends(require_scope("webhooks:manage")),
    db: Session = Depends(get_db),
):
    """Retrieves delivery history and responses for a subscription."""
    sub = db.get(WebhookSubscription, subscription_id)
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook subscription '{subscription_id}' not found",
        )

    deliveries = db.scalars(
        select(WebhookDelivery)
        .where(WebhookDelivery.subscription_id == subscription_id)
        .order_by(desc(WebhookDelivery.created_at))
        .limit(limit)
    ).all()
    return deliveries


@router.post("/deliveries/{delivery_id}/retry", response_model=WebhookDeliveryResponse)
def retry_delivery(
    delivery_id: str,
    api_key: ApiKey = Depends(require_scope("webhooks:manage")),
    db: Session = Depends(get_db),
):
    """Manually retries delivering a specific webhook attempt immediately."""
    delivery = db.get(WebhookDelivery, delivery_id)
    if not delivery:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook delivery '{delivery_id}' not found",
        )
    return deliver_webhook_sync(db, delivery)
