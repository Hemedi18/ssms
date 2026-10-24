from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import select, desc, and_
from app.core.logging import logger
from app.models.bundle import SmsBundle
from app.models.credit_transaction import CreditTransaction


def get_or_create_active_bundle(db: Session, tenant_id: Optional[str] = None) -> SmsBundle:
    """
    Retrieves the currently active SMS bundle for a tenant (or global fallback).
    If no bundle exists, creates an initial starter bundle of 5,000 SMS valid for 30 days.
    """
    query = select(SmsBundle).where(SmsBundle.is_active == True)
    if tenant_id:
        query = query.where(SmsBundle.tenant_id == tenant_id)

    bundle = db.scalar(query.order_by(desc(SmsBundle.created_at)).limit(1))

    if not bundle:
        now = datetime.now(timezone.utc)
        bundle = SmsBundle(
            tenant_id=tenant_id,
            plan_name="Business SMS Starter",
            total_credits=5000,
            used_credits=0,
            available_credits=5000,
            expires_at=now + timedelta(days=30),
            is_active=True,
        )
        db.add(bundle)
        db.commit()
        db.refresh(bundle)

        # Log initial credit transaction
        tx = CreditTransaction(
            tenant_id=tenant_id,
            bundle_id=bundle.id,
            tx_type="topup",
            amount=5000,
            balance_after=5000,
            reason="Starter SMS bundle initialization",
        )
        db.add(tx)
        db.commit()

        logger.info(
            f"Initialized active SMS bundle for tenant '{tenant_id}' with 5,000 credits, expires {bundle.expires_at}"
        )

    return bundle


def check_and_deduct_credits(
    db: Session,
    credits_needed: int,
    tenant_id: Optional[str] = None,
    message_id: Optional[str] = None,
    reason: Optional[str] = None,
) -> SmsBundle:
    """
    Verifies that the active bundle is not expired and has sufficient credits.
    Deducts credits atomically and records an immutable CreditTransaction.
    Raises ValueError on expired bundle or insufficient credits.
    """
    bundle = get_or_create_active_bundle(db, tenant_id=tenant_id)
    now = datetime.now(timezone.utc)

    # 1. Check expiration
    expires_at = bundle.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < now:
        raise ValueError(
            f"Bando la SMS limeisha tangu tarehe {expires_at.strftime('%d-%m-%Y %H:%M')}. "
            "Tafadhali ongeza salio (Recharge/Top-up) ili uweze kutuma ujumbe."
        )

    # 2. Check balance
    if bundle.available_credits < credits_needed:
        raise ValueError(
            f"Salio la SMS halitoshi. Salio lililopo: {bundle.available_credits} SMS, "
            f"Inahitajika: {credits_needed} SMS. Tafadhali ongeza salio."
        )

    # 3. Deduct credits
    bundle.available_credits -= credits_needed
    bundle.used_credits += credits_needed

    tx = CreditTransaction(
        tenant_id=bundle.tenant_id,
        bundle_id=bundle.id,
        message_id=message_id,
        tx_type="deduction",
        amount=-credits_needed,
        balance_after=bundle.available_credits,
        reason=reason or f"Deducted {credits_needed} SMS credits for dispatch",
    )
    db.add(tx)
    db.commit()
    db.refresh(bundle)

    logger.info(
        f"Deducted {credits_needed} SMS credits for tenant '{bundle.tenant_id}'. Remaining balance: {bundle.available_credits}"
    )
    return bundle


def refund_credits(
    db: Session,
    credits_to_refund: int,
    tenant_id: Optional[str] = None,
    bundle_id: Optional[str] = None,
    message_id: Optional[str] = None,
    reason: str = "Message dispatch failure auto-refund",
) -> SmsBundle:
    """
    Refunds credits back to the active bundle upon message failure or cancellation.
    Logs an immutable CreditTransaction record.
    """
    if credits_to_refund <= 0:
        return get_or_create_active_bundle(db, tenant_id=tenant_id)

    if bundle_id:
        bundle = db.get(SmsBundle, bundle_id)
    else:
        bundle = None

    if not bundle:
        bundle = get_or_create_active_bundle(db, tenant_id=tenant_id)

    bundle.available_credits += credits_to_refund
    bundle.used_credits = max(0, bundle.used_credits - credits_to_refund)

    tx = CreditTransaction(
        tenant_id=bundle.tenant_id,
        bundle_id=bundle.id,
        message_id=message_id,
        tx_type="refund",
        amount=credits_to_refund,
        balance_after=bundle.available_credits,
        reason=reason,
    )
    db.add(tx)
    db.commit()
    db.refresh(bundle)

    logger.info(
        f"Refunded {credits_to_refund} SMS credits to bundle [{bundle.id}] for message [{message_id}]. New balance: {bundle.available_credits}"
    )
    return bundle


def topup_bundle(
    db: Session,
    credits_to_add: int,
    extend_days: Optional[int] = 30,
    plan_name: Optional[str] = None,
    tenant_id: Optional[str] = None,
    reason: Optional[str] = None,
) -> SmsBundle:
    """
    Adds credits to the active bundle, extends its expiration date, and records a CreditTransaction.
    """
    bundle = get_or_create_active_bundle(db, tenant_id=tenant_id)
    now = datetime.now(timezone.utc)

    if credits_to_add > 0:
        bundle.total_credits += credits_to_add
        bundle.available_credits += credits_to_add

    # If already expired, start extension from now, otherwise add to current expiration
    current_expiry = bundle.expires_at
    if current_expiry.tzinfo is None:
        current_expiry = current_expiry.replace(tzinfo=timezone.utc)

    base_date = max(now, current_expiry)
    if extend_days and extend_days > 0:
        bundle.expires_at = base_date + timedelta(days=extend_days)

    if plan_name:
        bundle.plan_name = plan_name.strip()

    tx = CreditTransaction(
        tenant_id=bundle.tenant_id,
        bundle_id=bundle.id,
        tx_type="topup",
        amount=credits_to_add,
        balance_after=bundle.available_credits,
        reason=reason or f"Top-up of +{credits_to_add} SMS credits ({bundle.plan_name})",
    )
    db.add(tx)
    db.commit()
    db.refresh(bundle)
    logger.info(
        f"Topped up bundle with +{credits_to_add} credits. Total: {bundle.available_credits}, Expiry: {bundle.expires_at}"
    )
    return bundle


def get_bundle_summary(db: Session, tenant_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns bundle statistics and remaining days calculation for tenant or global view.
    """
    bundle = get_or_create_active_bundle(db, tenant_id=tenant_id)
    now = datetime.now(timezone.utc)

    expires_at = bundle.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    diff = expires_at - now
    days_left = max(0, diff.days)
    hours_left = max(0, int(diff.total_seconds() // 3600))
    is_expired = diff.total_seconds() <= 0

    percent_remaining = (
        round((bundle.available_credits / bundle.total_credits) * 100, 1)
        if bundle.total_credits > 0
        else 0.0
    )

    return {
        "id": bundle.id,
        "tenant_id": bundle.tenant_id,
        "plan_name": bundle.plan_name,
        "total_credits": bundle.total_credits,
        "used_credits": bundle.used_credits,
        "available_credits": bundle.available_credits,
        "expires_at": expires_at.isoformat(),
        "days_left": days_left,
        "hours_left": hours_left,
        "is_expired": is_expired,
        "percent_remaining": percent_remaining,
        "status": "expired" if is_expired else ("warning" if days_left <= 3 else "active"),
    }


def list_credit_transactions(
    db: Session,
    tenant_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[CreditTransaction]:
    """Retrieves credit ledger transactions for audit and reporting."""
    query = select(CreditTransaction)
    if tenant_id:
        query = query.where(CreditTransaction.tenant_id == tenant_id)
    return db.scalars(
        query.order_by(desc(CreditTransaction.created_at))
        .offset(offset)
        .limit(limit)
    ).all()
