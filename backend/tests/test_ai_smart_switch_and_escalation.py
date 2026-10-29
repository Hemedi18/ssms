import pytest
from unittest.mock import patch
from app.services.ai_service import is_owner_communication_request, process_incoming_sms_with_ai
from app.models.incoming_message import IncomingMessage
from app.models.chat_ai_preference import ChatAiPreference
from app.models.dnd_and_moderation import DndBlacklist
from datetime import datetime, timezone


def test_is_owner_communication_request_matches():
    assert is_owner_communication_request("i need to communicate with owner") is True
    assert is_owner_communication_request("Can I please talk to the owner right now?") is True
    assert is_owner_communication_request("Nataka kuongea na mmliki wa biashara") is True
    assert is_owner_communication_request("I need to speak to the boss") is True
    assert is_owner_communication_request("Wasikilize mimi, nataka kuongea na mtu halisi") is True
    assert is_owner_communication_request("Just normal question about price") is False


def test_ai_reply_blocked_contact(db_session):
    # Add blocked user in ChatAiPreference
    phone = "+255711223344"
    pref = ChatAiPreference(phone_number=phone, is_blocked=True, is_ai_enabled=True)
    db_session.add(pref)

    incoming = IncomingMessage(
        from_number=phone,
        body="Hello AI, how much is this?",
        received_at_device=datetime.now(timezone.utc),
    )
    db_session.add(incoming)
    db_session.commit()

    with patch("app.core.config.settings.AI_AUTO_REPLY_ENABLED", True), \
         patch("app.core.config.settings.GEMINI_API_KEY", "mock-key"):
        result = process_incoming_sms_with_ai(incoming.id, db_override=db_session)
        assert result is None, "AI should NOT reply to a blocked contact"


def test_ai_reply_smart_switch_off(db_session):
    # Smart switch toggled OFF for this chat
    phone = "+255755667788"
    pref = ChatAiPreference(phone_number=phone, is_blocked=False, is_ai_enabled=False)
    db_session.add(pref)

    incoming = IncomingMessage(
        from_number=phone,
        body="Hello AI please assist me",
        received_at_device=datetime.now(timezone.utc),
    )
    db_session.add(incoming)
    db_session.commit()

    with patch("app.core.config.settings.AI_AUTO_REPLY_ENABLED", True), \
         patch("app.core.config.settings.GEMINI_API_KEY", "mock-key"):
        result = process_incoming_sms_with_ai(incoming.id, db_override=db_session)
        assert result is None, "AI should NOT reply when smart switch is toggled OFF"


def test_owner_escalation_triggers_email_and_stops_ai(db_session):
    phone = "+255788990011"
    incoming = IncomingMessage(
        from_number=phone,
        body="I need to communicate with owner immediately!",
        received_at_device=datetime.now(timezone.utc),
    )
    db_session.add(incoming)
    db_session.commit()

    with patch("app.core.config.settings.AI_AUTO_REPLY_ENABLED", True), \
         patch("app.core.config.settings.GEMINI_API_KEY", "mock-key"), \
         patch("app.services.ai_service.send_owner_escalation_alert") as mock_email_alert:

        result = process_incoming_sms_with_ai(incoming.id, db_override=db_session)
        assert result is None, "AI should not generate standard LLM reply"
        assert mock_email_alert.called is True
        args, kwargs = mock_email_alert.call_args
        assert kwargs.get("sender_phone") == phone
        assert "owner" in kwargs.get("incoming_text").lower()

        # Check that preference is marked as escalated
        updated_pref = db_session.query(ChatAiPreference).filter(ChatAiPreference.phone_number == phone).first()
        assert updated_pref is not None
        assert updated_pref.is_escalated is True
        assert updated_pref.is_ai_enabled is False
