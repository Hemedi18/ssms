import os
import re
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_, desc
import httpx

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import logger
from app.models.incoming_message import IncomingMessage
from app.models.message import Message
from app.schemas.message import MessageCreate
from app.services.message_service import create_message
from app.services.webhook_service import queue_event
from app.utils.phone_tz import is_opt_out_keyword, normalize_tz_phone


def clean_sms_text(text: str) -> str:
    """
    Cleans up LLM response for cellular SMS dispatch:
    - Removes markdown (asterisks, bold, italics, backticks, hashes, brackets).
    - Removes bullet points and markdown links.
    - Normalizes whitespace.
    - Limits length cleanly so it fits into standard SMS parts (max 320 chars).
    """
    if not text:
        return ""

    # Remove code blocks and inline code
    s = re.sub(r"```[\s\S]*?```", "", text)
    s = re.sub(r"`([^`]+)`", r"\1", s)

    # Remove markdown links [text](url) -> text
    s = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", s)

    # Remove bold/italic asterisks & underscores
    s = re.sub(r"(\*\*|__)(.*?)\1", r"\2", s)
    s = re.sub(r"(\*|_)(.*?)\1", r"\2", s)

    # Remove header hashes and bullet indicators
    s = re.sub(r"^#{1,6}\s*", "", s, flags=re.MULTILINE)
    s = re.sub(r"^[\*\-\+]\s+", "", s, flags=re.MULTILINE)

    # Collapse multiple spaces and excessive newlines
    s = re.sub(r"\r\n|\r", "\n", s)
    s = re.sub(r"\n{2,}", "\n", s)
    s = re.sub(r"[ \t]+", " ", s)
    cleaned = s.strip()

    # Graceful truncation if response exceeds 320 characters
    max_len = 320
    if len(cleaned) > max_len:
        truncated = cleaned[:max_len - 3]
        last_space = truncated.rfind(" ")
        if last_space > 200:
            cleaned = truncated[:last_space] + "..."
        else:
            cleaned = truncated + "..."

    return cleaned


def get_conversation_history(
    db: Session,
    phone_number: str,
    limit: int = 4
) -> List[Dict[str, Any]]:
    """
    Retrieves recent SMS interactions with the phone number to provide
    conversational memory to Gemini (alternating user and model turns).
    """
    try:
        norm_phone = normalize_tz_phone(
            phone_number, default_country_code=settings.DEFAULT_COUNTRY_CODE
        )
    except Exception:
        norm_phone = phone_number

    # 1. Fetch recent incoming messages
    incoming_list = db.scalars(
        select(IncomingMessage)
        .where(
            or_(
                IncomingMessage.from_number == phone_number,
                IncomingMessage.from_number == norm_phone,
            )
        )
        .order_by(desc(IncomingMessage.created_at))
        .limit(limit)
    ).all()

    # 2. Fetch recent outgoing messages
    outgoing_list = db.scalars(
        select(Message)
        .where(
            or_(
                Message.to == phone_number,
                Message.to == norm_phone,
            ),
            Message.status.in_(["queued", "dispatched", "sending", "sent", "delivered"])
        )
        .order_by(desc(Message.created_at))
        .limit(limit)
    ).all()

    # Merge and sort chronologically
    combined = []
    for inc in incoming_list:
        combined.append((inc.created_at, "user", inc.body))
    for out in outgoing_list:
        combined.append((out.created_at, "model", out.body))

    combined.sort(key=lambda x: x[0])
    # Keep only the last `limit` messages
    recent = combined[-limit:] if len(combined) > limit else combined

    history: List[Dict[str, Any]] = []
    for _, role, content in recent:
        if content and content.strip():
            history.append({
                "role": role,
                "parts": [{"text": content.strip()}]
            })

    return history


# Global tracking for the last AI communication error
_last_ai_error: Optional[str] = None

# Aliases to map legacy or deprecated Gemini model names to active Google AI Studio models
MODEL_ALIASES = {
    "gemini-1.5-flash": "gemini-3.5-flash-lite",
    "gemini-1.5-pro": "gemini-3.5-flash",
    "gemini-2.0-flash": "gemini-3.5-flash-lite",
    "gemini-2.5-flash": "gemini-3.5-flash-lite",
    "gemini-2.5-flash-lite": "gemini-3.5-flash-lite",
    "gemini-2.5-pro": "gemini-3.5-flash",
}


def get_last_ai_error() -> Optional[str]:
    """Returns the most recent Gemini API error message, if any."""
    global _last_ai_error
    return _last_ai_error


def generate_gemini_reply(
    prompt: str,
    history: Optional[List[Dict[str, Any]]] = None,
    system_instruction: Optional[str] = None,
    model_override: Optional[str] = None,
) -> Optional[str]:
    """
    Calls Google AI Studio (Gemini REST API) using httpx.
    Returns cleaned SMS reply text or None if error/unconfigured.
    Automatically handles deprecated model aliasing and fallback.
    """
    global _last_ai_error
    _last_ai_error = None

    api_key = settings.GEMINI_API_KEY
    if not api_key or not api_key.strip():
        _last_ai_error = "GEMINI_API_KEY is not configured in .env."
        logger.warning("GEMINI_API_KEY is not configured in .env. Skipping AI auto-reply.")
        return None

    raw_model = model_override or settings.GEMINI_MODEL or "gemini-3.5-flash-lite"
    model = MODEL_ALIASES.get(raw_model.strip(), raw_model.strip())
    sys_prompt = system_instruction or settings.AI_SYSTEM_PROMPT

    # Build contents with history if available
    contents: List[Dict[str, Any]] = []
    if history:
        for turn in history:
            contents.append(turn)

    # Append current incoming prompt
    contents.append({
        "role": "user",
        "parts": [{"text": prompt}]
    })

    payload: Dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": max(settings.AI_MAX_OUTPUT_TOKENS, 250),
            "temperature": settings.AI_TEMPERATURE,
        }
    }

    if sys_prompt and sys_prompt.strip():
        payload["system_instruction"] = {
            "parts": [{"text": sys_prompt.strip()}]
        }

    # Attempt primary model, with automatic fallback to gemini-3.5-flash-lite if 404
    models_to_try = [model]
    if model != "gemini-3.5-flash-lite":
        models_to_try.append("gemini-3.5-flash-lite")

    last_response_text = ""
    for candidate_model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{candidate_model}:generateContent?key={api_key.strip()}"
        try:
            with httpx.Client(timeout=25.0) as client:
                response = client.post(url, json=payload)

                if response.status_code == 200:
                    data = response.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        # Extract text, skipping reasoning/thought parts
                        text_chunks = [
                            p.get("text", "") for p in parts
                            if isinstance(p, dict) and p.get("text") and not p.get("thought")
                        ]
                        if not text_chunks and parts:
                            for p in parts:
                                if isinstance(p, dict) and p.get("text"):
                                    text_chunks.append(p["text"])

                        if text_chunks:
                            raw_reply = " ".join(text_chunks).strip()
                            cleaned = clean_sms_text(raw_reply)
                            logger.info(f"Gemini AI ({candidate_model}) generated reply ({len(cleaned)} chars): '{cleaned}'")
                            return cleaned

                    logger.warning(f"Gemini API returned 200 but no candidates: {data}")
                    _last_ai_error = "Gemini returned empty candidate response."
                    return None

                last_response_text = response.text
                # If 404 (model not found / deprecated) and we have a fallback, try next model
                if response.status_code == 404 and candidate_model != models_to_try[-1]:
                    logger.warning(f"Model {candidate_model} returned 404, falling back to {models_to_try[-1]}...")
                    continue

                logger.error(f"Gemini API error (HTTP {response.status_code}): {response.text}")
                try:
                    err_json = response.json()
                    _last_ai_error = err_json.get("error", {}).get("message", f"HTTP {response.status_code}: {response.text[:150]}")
                except Exception:
                    _last_ai_error = f"HTTP {response.status_code}: {response.text[:150]}"
                return None

        except httpx.TimeoutException:
            logger.error(f"Gemini API call timed out after 25s for model {candidate_model}.")
            _last_ai_error = "Gemini request timed out (25s). Check network connection."
            if candidate_model != models_to_try[-1]:
                continue
            return None
        except Exception as e:
            logger.error(f"Failed to communicate with Google AI Studio: {e}", exc_info=True)
            _last_ai_error = str(e)
            return None

    _last_ai_error = f"Failed to generate response: {last_response_text[:150]}"
    return None


def process_incoming_sms_with_ai(
    incoming_id: str,
    db_override: Optional[Session] = None
) -> Optional[Message]:
    """
    Background worker/task function:
    1. Loads the incoming message by ID.
    2. Validates AI settings.
    3. Generates conversational reply via Gemini.
    4. Enqueues the reply as an outgoing SMS job for the phone to dispatch.
    """
    if not settings.AI_AUTO_REPLY_ENABLED:
        logger.debug("AI auto-reply is disabled (AI_AUTO_REPLY_ENABLED=False).")
        return None

    if not settings.GEMINI_API_KEY:
        logger.debug("GEMINI_API_KEY not set. Skipping AI processing.")
        return None

    own_session = False
    if db_override is not None:
        db = db_override
    else:
        db = SessionLocal()
        own_session = True

    try:
        incoming = db.scalar(
            select(IncomingMessage).where(IncomingMessage.id == incoming_id)
        )
        if not incoming:
            logger.warning(f"IncomingMessage [{incoming_id}] not found for AI processing.")
            return None

        # Check TCRA opt-out keywords (STOP, ONDOA, JIONDOE)
        if is_opt_out_keyword(incoming.body):
            logger.info(f"Skipping AI reply for opt-out SMS from {incoming.from_number}")
            return None

        # Idempotency check: avoid double-replying to the same incoming message
        reply_ref = f"ai-reply-{incoming.id}"
        existing_reply = db.scalar(
            select(Message).where(Message.client_reference == reply_ref)
        )
        if existing_reply:
            logger.info(f"AI auto-reply already created for message {incoming.id} (reply {existing_reply.id})")
            return existing_reply

        # Retrieve conversational context (previous 4 messages)
        history = get_conversation_history(db, incoming.from_number, limit=4)

        # Generate Gemini reply
        reply_text = generate_gemini_reply(
            prompt=incoming.body,
            history=history,
            system_instruction=settings.AI_SYSTEM_PROMPT,
        )

        if not reply_text:
            logger.warning(f"Could not generate AI reply for incoming SMS {incoming.id}")
            return None

        # Enqueue outgoing SMS via message_service
        msg_payload = MessageCreate(
            to=incoming.from_number,
            message=reply_text,
            sender_name=settings.AI_REPLY_SENDER_NAME,
            client_reference=reply_ref,
            message_type="transactional",
            priority=10,
            tenant_id=incoming.tenant_id,
        )

        reply_message, _ = create_message(
            db=db,
            payload=msg_payload,
            actor_id="gemini-ai",
            tenant_id=incoming.tenant_id,
        )

        # Notify via webhook event
        queue_event(
            db=db,
            event_type="ai.replied",
            data={
                "incoming_id": incoming.id,
                "reply_message_id": reply_message.id,
                "to": incoming.from_number,
                "reply": reply_message.body,
                "tenant_id": incoming.tenant_id,
            }
        )

        logger.info(
            f"AI auto-reply successfully queued (id={reply_message.id}) to {incoming.from_number}: '{reply_text}'"
        )
        return reply_message

    except Exception as e:
        logger.error(f"Error in process_incoming_sms_with_ai for {incoming_id}: {e}", exc_info=True)
        return None
    finally:
        if own_session:
            db.close()


def find_env_file_path() -> str:
    """Finds active .env file location across development and cPanel production."""
    # 1. Base directory above 'app' (e.g. backend/.env or /home/eduspher/sms_gateway/.env)
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env_candidate = os.path.join(base_dir, ".env")
    if os.path.exists(env_candidate):
        return env_candidate

    # 2. Current working directory
    cwd_env = os.path.join(os.getcwd(), ".env")
    if os.path.exists(cwd_env):
        return cwd_env

    return env_candidate


def persist_ai_config_to_env(updates: Dict[str, Any]) -> str:
    """
    Saves AI configuration variables directly into the server's .env file,
    preserving comments and existing settings, and dynamically updates in-memory settings.
    """
    env_path = find_env_file_path()
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    handled_keys = set()
    new_lines = []

    for line in lines:
        stripped = line.strip()
        matched_key = None
        for key in updates.keys():
            pattern = rf"^#?\s*{re.escape(key)}\s*="
            if re.match(pattern, stripped):
                matched_key = key
                break

        if matched_key:
            val = updates[matched_key]
            if isinstance(val, bool):
                val_str = "true" if val else "false"
            elif isinstance(val, (int, float)):
                val_str = str(val)
            elif val is None:
                val_str = '""'
            else:
                clean_val = str(val).replace('"', '\\"')
                val_str = f'"{clean_val}"'
            new_lines.append(f"{matched_key}={val_str}\n")
            handled_keys.add(matched_key)
        else:
            new_lines.append(line)

    # For any new keys not found in existing lines, append them
    for key, val in updates.items():
        if key not in handled_keys:
            if isinstance(val, bool):
                val_str = "true" if val else "false"
            elif isinstance(val, (int, float)):
                val_str = str(val)
            elif val is None:
                val_str = '""'
            else:
                clean_val = str(val).replace('"', '\\"')
                val_str = f'"{clean_val}"'
            new_lines.append(f"{key}={val_str}\n")

    # Ensure target directory exists
    os.makedirs(os.path.dirname(os.path.abspath(env_path)), exist_ok=True)
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    # Update in-memory settings so changes apply immediately without server restart
    for k, v in updates.items():
        if hasattr(settings, k):
            setattr(settings, k, v)

    logger.info(f"Persisted AI configuration to {env_path}: keys updated: {list(updates.keys())}")
    return env_path
