import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.dnd_and_moderation import ContentModerationRule
from app.models.message import Message
from app.models.bundle import SmsBundle
from app.models.credit_transaction import CreditTransaction


def test_content_moderation_firewall_rules(client, db_session: Session):
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "hemy@2004"},
    )
    admin_token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Rule: auto_replace "MKUPO WA BURE" -> "Ofa Maalum"
    rule_replace = ContentModerationRule(
        name="Scam Phrase Censor",
        pattern=r"\bMKUPO WA BURE\b",
        action="auto_replace",
        replacement_text="Ofa Maalum",
        is_active=True,
    )
    db_session.add(rule_replace)

    # 2. Rule: hold_for_approval if contains "pata mkopo bila dhamana"
    rule_quarantine = ContentModerationRule(
        name="Loan Quarantine",
        pattern=r"mkopo bila dhamana",
        action="hold_for_approval",
        is_active=True,
    )
    db_session.add(rule_quarantine)

    # 3. Rule: reject if contains "kamari mtandaoni"
    rule_reject = ContentModerationRule(
        name="Gambling Block",
        pattern=r"kamari mtandaoni",
        action="reject",
        is_active=True,
    )
    db_session.add(rule_reject)
    db_session.commit()

    # Test auto_replace
    res_replace = client.post(
        "/api/v1/messages",
        json={"to": "+255712111222", "message": "Pata MKUPO WA BURE leo!"},
        headers=headers,
    )
    assert res_replace.status_code == 201
    data_rep = res_replace.json()
    assert "Ofa Maalum" in data_rep["body"]
    assert "MKUPO WA BURE" not in data_rep["body"]
    assert data_rep["original_body"] is not None
    assert "MKUPO WA BURE" in data_rep["original_body"]

    # Test hold_for_approval
    res_quarantine = client.post(
        "/api/v1/messages",
        json={"to": "+255712333444", "message": "Tunakupa mkopo bila dhamana haraka."},
        headers=headers,
    )
    assert res_quarantine.status_code == 201
    assert res_quarantine.json()["status"] == "pending_approval"

    # Test reject
    res_reject = client.post(
        "/api/v1/messages",
        json={"to": "+255712555666", "message": "Cheza kamari mtandaoni ushinde mamilioni."},
        headers=headers,
    )
    assert res_reject.status_code == 400
    assert "blocked by content moderation firewall" in res_reject.json()["detail"]


def test_admin_inline_per_sms_modification(client, db_session: Session):
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "hemy@2004"},
    )
    admin_token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Create a 1-part queued message
    create_res = client.post(
        "/api/v1/messages",
        json={"to": "+255718123456", "message": "Short initial notification."},
        headers=headers,
    )
    assert create_res.status_code == 201
    msg_id = create_res.json()["id"]
    assert create_res.json()["parts_count"] == 1

    # Check bundle credits
    bundle_before = client.get("/api/v1/admin/bundle", headers=headers).json()
    credits_before = bundle_before["available_credits"]

    # 2. Modify message to 2 parts (more than 160 GSM chars) and change priority + sim_slot
    long_body = "A" * 170
    modify_payload = {
        "body": long_body,
        "sender_name": "EDUSPHERE_PRO",
        "sim_slot": 1,
        "priority": 25,
        "admin_notes": "Expanded content per customer request",
    }
    modify_res = client.patch(
        f"/api/v1/admin/messages/{msg_id}/modify",
        json=modify_payload,
        headers=headers,
    )
    assert modify_res.status_code == 200
    mod_data = modify_res.json()
    assert mod_data["parts_count"] == 2
    assert mod_data["sim_slot"] == 1
    assert mod_data["priority"] == 25
    assert mod_data["original_body"] is not None
    assert "Short initial notification." in mod_data["original_body"]

    # Verify credit reconciliation: 1 additional credit deducted
    bundle_after = client.get("/api/v1/admin/bundle", headers=headers).json()
    assert bundle_after["available_credits"] == credits_before - 1


def test_batch_action_approval_and_rejection_with_refund(client, db_session: Session):
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "hemy@2004"},
    )
    admin_token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Create 2 quarantined messages
    rule_quarantine = ContentModerationRule(
        name="Crypto Quarantine",
        pattern=r"crypto investment",
        action="hold_for_approval",
        is_active=True,
    )
    db_session.add(rule_quarantine)
    db_session.commit()

    m1_res = client.post(
        "/api/v1/messages",
        json={"to": "+255719000111", "message": "High return crypto investment plan."},
        headers=headers,
    )
    m2_res = client.post(
        "/api/v1/messages",
        json={"to": "+255719000222", "message": "Join our crypto investment group."},
        headers=headers,
    )
    m1_id = m1_res.json()["id"]
    m2_id = m2_res.json()["id"]
    assert m1_res.json()["status"] == "pending_approval"
    assert m2_res.json()["status"] == "pending_approval"

    bundle_before_actions = client.get("/api/v1/admin/bundle", headers=headers).json()
    credits_before_reject = bundle_before_actions["available_credits"]

    # 2. Batch action: Approve m1
    approve_res = client.post(
        "/api/v1/admin/messages/batch-action",
        json={"message_ids": [m1_id], "action": "approve"},
        headers=headers,
    )
    assert approve_res.status_code == 200
    assert approve_res.json()["affected_count"] == 1

    # Verify m1 is now queued
    m1_updated = client.get(f"/api/v1/messages/{m1_id}", headers=headers).json()
    assert m1_updated["status"] == "queued"

    # 3. Batch action: Reject m2 with credit refund
    reject_res = client.post(
        "/api/v1/admin/messages/batch-action",
        json={
            "message_ids": [m2_id],
            "action": "reject",
            "admin_notes": "Scam proposal rejected by moderator",
        },
        headers=headers,
    )
    assert reject_res.status_code == 200
    assert reject_res.json()["affected_count"] == 1
    assert reject_res.json()["credits_refunded"] == 1

    # Verify m2 is rejected and credits were refunded to bundle
    m2_updated = client.get(f"/api/v1/messages/{m2_id}", headers=headers).json()
    assert m2_updated["status"] == "rejected"

    bundle_after_reject = client.get("/api/v1/admin/bundle", headers=headers).json()
    assert bundle_after_reject["available_credits"] == credits_before_reject + 1
