import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.utils.phone_tz import (
    normalize_tz_phone,
    classify_mno,
    calculate_sms_encoding_and_parts,
    is_tcra_quiet_hours,
    is_opt_out_keyword,
    render_spintax,
    interpolate_variables,
)
from app.models.dnd_and_moderation import DndBlacklist
from app.models.device import GatewayDevice
from app.schemas.incoming import IncomingSmsReportRequest
from app.services.incoming_service import ingest_incoming_sms


def test_tanzania_mno_classification():
    # Vodacom TZ
    assert classify_mno("+255742123456") == "VODACOM_TZ"
    assert classify_mno("+255754123456") == "VODACOM_TZ"
    assert classify_mno("+255767123456") == "VODACOM_TZ"

    # Airtel TZ
    assert classify_mno("+255682123456") == "AIRTEL_TZ"
    assert classify_mno("+255693123456") == "AIRTEL_TZ"
    assert classify_mno("+255784123456") == "AIRTEL_TZ"

    # Mixx by Yas (Tigo / Zantel)
    assert classify_mno("+255655123456") == "YAS_TIGO_TZ"
    assert classify_mno("+255677123456") == "YAS_TIGO_TZ"
    assert classify_mno("+255713123456") == "YAS_TIGO_TZ"
    assert classify_mno("+255772123456") == "YAS_TIGO_TZ"

    # Halotel TZ
    assert classify_mno("+255612123456") == "HALOTEL_TZ"
    assert classify_mno("+255624123456") == "HALOTEL_TZ"

    # TTCL TZ
    assert classify_mno("+255732123456") == "TTCL_TZ"

    # International
    assert classify_mno("+14155552671") == "INTERNATIONAL"
    assert classify_mno("+447700900077") == "INTERNATIONAL"


def test_gsm_7bit_vs_ucs2_encoding_calculation():
    # 1. Standard GSM 7-bit basic string (160 characters = 1 part)
    ascii_160 = "A" * 160
    enc1, parts1, septets1 = calculate_sms_encoding_and_parts(ascii_160)
    assert enc1 == "GSM_7BIT"
    assert parts1 == 1
    assert septets1 == 160

    # 161 GSM characters = 2 parts
    ascii_161 = "A" * 161
    enc2, parts2, septets2 = calculate_sms_encoding_and_parts(ascii_161)
    assert enc2 == "GSM_7BIT"
    assert parts2 == 2
    assert septets2 == 161

    # 2. GSM 7-bit Extension Table characters (| ^ € { } [ ~ ] \) take 2 septets each
    # Text: 'Hello €' (5 chars 'Hello' = 5 septets, 1 space = 1 septet, '€' = 2 septets -> total 8 septets)
    euro_text = "Hello €"
    enc3, parts3, septets3 = calculate_sms_encoding_and_parts(euro_text)
    assert enc3 == "GSM_7BIT"
    assert parts3 == 1
    assert septets3 == 8

    # 3. UCS-2 Encoding (Emoji or non-GSM symbol forces UCS-2)
    emoji_text = "Habari ya asubuhi 🚀"
    enc4, parts4, length4 = calculate_sms_encoding_and_parts(emoji_text)
    assert enc4 == "UCS_2"
    assert parts4 == 1
    assert length4 == len(emoji_text)

    # 71 UCS-2 characters = 2 parts (since limit is 70 for single part, 67 for multipart)
    ucs2_71 = "🌟" + ("A" * 70)
    enc5, parts5, _ = calculate_sms_encoding_and_parts(ucs2_71)
    assert enc5 == "UCS_2"
    assert parts5 == 2


def test_spintax_and_variable_interpolation():
    # Spintax resolution
    template = "{Habari|Mambo|Salamu} ndugu mteja!"
    rendered = render_spintax(template, seed=42)
    assert any(greeting in rendered for greeting in ["Habari", "Mambo", "Salamu"])
    assert "{" not in rendered and "}" not in rendered

    # Variable interpolation
    msg_template = "Habari {{name}}, ankara yako ya {{invoice}} imekamilika kiasi cha TZS {{amount}}."
    vars_dict = {"name": "Baraka", "invoice": "INV-9921", "amount": "150,000"}
    interpolated = interpolate_variables(msg_template, vars_dict)
    assert "Habari Baraka" in interpolated
    assert "INV-9921" in interpolated
    assert "150,000" in interpolated


def test_tcra_dnd_auto_blacklisting_and_opt_out(client, db_session: Session):
    # Register device
    device = GatewayDevice(
        name="OptOutTestDevice",
        device_token_hash="hash_test_opt_out",
        is_online=True,
    )
    db_session.add(device)
    db_session.commit()

    # Ingest incoming SMS containing 'ONDOA'
    opt_out_phone = "+255714999888"
    req = IncomingSmsReportRequest(
        from_number=opt_out_phone,
        body="ONDOA",
        received_at=datetime.now(timezone.utc),
    )
    ingested, _ = ingest_incoming_sms(db_session, device, req)
    assert ingested.id is not None

    # Verify DndBlacklist entry was automatically created
    dnd = db_session.query(DndBlacklist).filter(DndBlacklist.phone_number == opt_out_phone).first()
    assert dnd is not None
    assert dnd.reason == "user_opt_out"

    # Now verify that sending a 'promotional' message to this number is rejected
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "hemy@2004"},
    )
    admin_token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    promo_payload = {
        "to": opt_out_phone,
        "message": "Pata punguzo la 50% leo!",
        "message_type": "promotional",
    }
    promo_res = client.post("/api/v1/messages", json=promo_payload, headers=headers)
    assert promo_res.status_code == 400
    assert "DND Opt-Out Blacklist" in promo_res.json()["detail"]

    # Transactional message (e.g. OTP) to the same number MUST still be allowed!
    otp_payload = {
        "to": opt_out_phone,
        "message": "Nambari yako ya uthibitisho ni 4821",
        "message_type": "transactional",
    }
    otp_res = client.post("/api/v1/messages", json=otp_payload, headers=headers)
    assert otp_res.status_code == 201
    assert otp_res.json()["status"] == "queued"
