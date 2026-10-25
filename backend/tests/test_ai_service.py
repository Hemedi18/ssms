import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.incoming_message import IncomingMessage
from app.models.message import Message
from app.services.ai_service import (
    clean_sms_text,
    generate_gemini_reply,
    process_incoming_sms_with_ai,
    get_conversation_history,
)


def test_clean_sms_text_markdown_stripping():
    sample_text = (
        "**Habari!** Karibu sana kwenye *huduma* zetu.\n\n"
        "- Kipengele 1: Huduma ya SMS\n"
        "- Kipengele 2: [Tembelea hapa](https://edusphere.co.tz)\n"
        "### Maelekezo:\n"
        "Tumia nambari yako ya simu `+255712345678`."
    )
    cleaned = clean_sms_text(sample_text)

    # Assert markdown markers are stripped
    assert "**" not in cleaned
    assert "###" not in cleaned
    assert "`" not in cleaned
    assert "[Tembelea" not in cleaned
    assert "Tembelea hapa" in cleaned
    assert "Habari! Karibu sana kwenye huduma zetu." in cleaned
    assert len(cleaned) <= 320


def test_clean_sms_text_long_truncation():
    very_long = "Neno " * 100  # 500 characters
    cleaned = clean_sms_text(very_long)
    assert len(cleaned) <= 320
    assert cleaned.endswith("...")


def test_generate_gemini_reply_unconfigured():
    with patch.object(settings, "GEMINI_API_KEY", None):
        reply = generate_gemini_reply("Habari")
        assert reply is None


def test_generate_gemini_reply_mocked_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "**Habari!** Karibu kwenye huduma yetu ya SMS."}],
                    "role": "model",
                }
            }
        ]
    }

    with patch.object(settings, "GEMINI_API_KEY", "fake-api-key"):
        with patch("httpx.Client.post", return_value=mock_response):
            reply = generate_gemini_reply("Habari za leo?")
            assert reply is not None
            assert "Habari!" in reply
            assert "**" not in reply  # Cleaned


def test_process_incoming_sms_with_ai_flow(db_session: Session):
    incoming = IncomingMessage(
        from_number="+255712345678",
        body="Habari, naomba kujua kuhusu vifurushi vyenu vya SMS",
        received_at_device=datetime.now(timezone.utc),
        raw_pdu_hash="test-pdu-hash-ai-1",
        tenant_id="tenant-ai-test",
    )
    db_session.add(incoming)
    db_session.commit()
    db_session.refresh(incoming)

    mock_ai_reply = "Karibu! Vifurushi vyetu ni vya kila siku, wiki, na mwezi kwa bei nafuu sana."

    with patch.object(settings, "GEMINI_API_KEY", "fake-api-key"):
        with patch.object(settings, "AI_AUTO_REPLY_ENABLED", True):
            with patch("app.services.ai_service.generate_gemini_reply", return_value=mock_ai_reply):
                reply_msg = process_incoming_sms_with_ai(incoming.id, db_override=db_session)

                assert reply_msg is not None
                assert reply_msg.to == "+255712345678"
                assert reply_msg.body == mock_ai_reply
                assert reply_msg.status == "queued"
                assert reply_msg.client_reference == f"ai-reply-{incoming.id}"

                # Test idempotency: calling again should not create duplicate
                duplicate_reply = process_incoming_sms_with_ai(incoming.id, db_override=db_session)
                assert duplicate_reply.id == reply_msg.id


def test_process_incoming_sms_skips_opt_out(db_session: Session):
    incoming = IncomingMessage(
        from_number="+255787654321",
        body="STOP",
        received_at_device=datetime.now(timezone.utc),
        raw_pdu_hash="test-pdu-hash-ai-stop",
    )
    db_session.add(incoming)
    db_session.commit()
    db_session.refresh(incoming)

    with patch.object(settings, "GEMINI_API_KEY", "fake-api-key"):
        with patch.object(settings, "AI_AUTO_REPLY_ENABLED", True):
            reply_msg = process_incoming_sms_with_ai(incoming.id, db_override=db_session)
            assert reply_msg is None


def test_test_ai_reply_endpoint_unconfigured(client):
    with patch.object(settings, "GEMINI_API_KEY", None):
        response = client.post(
            "/api/v1/incoming/test-ai-reply",
            json={"message": "Habari za kazi?"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unconfigured"
        assert data["configured"] is False


def test_test_ai_reply_endpoint_success(client):
    mock_reply = "Habari njema! Tunafurahi kukuhudumia."
    with patch.object(settings, "GEMINI_API_KEY", "test-key"):
        with patch("app.api.v1.incoming.generate_gemini_reply", return_value=mock_reply):
            response = client.post(
                "/api/v1/incoming/test-ai-reply",
                json={"message": "Habari za kazi?"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["reply"] == mock_reply
            assert data["configured"] is True


def test_admin_ai_config_and_playground(client, tmp_path):
    # 1. Login as admin
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "hemy@2004"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Get AI config
    get_res = client.get("/api/v1/admin/ai-config", headers=headers)
    assert get_res.status_code == 200
    cfg = get_res.json()
    assert "ai_auto_reply_enabled" in cfg
    assert "gemini_model" in cfg

    # 3. Update AI config and persist to temp .env
    test_env = tmp_path / ".env"
    test_env.write_text("SOME_VAR=123\n", encoding="utf-8")

    with patch("app.services.ai_service.find_env_file_path", return_value=str(test_env)):
        post_res = client.post(
            "/api/v1/admin/ai-config",
            headers=headers,
            json={
                "ai_auto_reply_enabled": True,
                "gemini_api_key": "AIzaSyTestKey12345678",
                "gemini_model": "gemini-2.0-flash",
                "ai_system_prompt": "Jibu kwa adabu na haraka sana.",
                "ai_max_output_tokens": 120,
                "ai_temperature": 0.5,
                "ai_reply_sender_name": "TESTBRAND",
            },
        )
        assert post_res.status_code == 200
        saved = post_res.json()
        assert saved["gemini_model"] == "gemini-2.0-flash"
        assert saved["ai_temperature"] == 0.5
        assert saved["gemini_api_key_set"] is True
        assert saved["ai_reply_sender_name"] == "TESTBRAND"

        # Verify .env contents
        env_content = test_env.read_text(encoding="utf-8")
        assert "GEMINI_API_KEY=\"AIzaSyTestKey12345678\"" in env_content
        assert "GEMINI_MODEL=\"gemini-2.0-flash\"" in env_content

    # 4. Test playground endpoint
    mock_reply = "Karibu sana kwenye ofisi yetu! Tunafungua saa 2 asubuhi."
    with patch("app.services.ai_service.generate_gemini_reply", return_value=mock_reply):
        test_play_res = client.post(
            "/api/v1/admin/ai-test",
            headers=headers,
            json={"message": "Mnafungua saa ngapi?"},
        )
        assert test_play_res.status_code == 200
        play_data = test_play_res.json()
        assert play_data["status"] == "success"
        assert play_data["reply"] == mock_reply
        assert play_data["sms_parts"] >= 1
        assert play_data["characters"] == len(mock_reply)
