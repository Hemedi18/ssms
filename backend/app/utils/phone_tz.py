import math
import re
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional, Dict, Any, List

# ---------------------------------------------------------------------------
# 1. Tanzania MNO Prefix Constants & Detection
# ---------------------------------------------------------------------------
# Vodacom TZ: +25574, +25575, +25576
# Airtel TZ: +25568, +25569, +25578
# Mixx by Yas (Tigo / Zantel): +25565, +25567, +25571, +25577
# Halotel TZ: +25561, +25562
# TTCL: +25573
MNO_PREFIX_MAP = {
    "+25574": "VODACOM_TZ",
    "+25575": "VODACOM_TZ",
    "+25576": "VODACOM_TZ",
    "+25568": "AIRTEL_TZ",
    "+25569": "AIRTEL_TZ",
    "+25578": "AIRTEL_TZ",
    "+25565": "YAS_TIGO_TZ",
    "+25567": "YAS_TIGO_TZ",
    "+25571": "YAS_TIGO_TZ",
    "+25577": "YAS_TIGO_TZ",
    "+25561": "HALOTEL_TZ",
    "+25562": "HALOTEL_TZ",
    "+25573": "TTCL_TZ",
}

E164_REGEX = re.compile(r"^\+[1-9]\d{6,14}$")


def normalize_tz_phone(phone: str, default_country_code: str = "+255") -> str:
    """
    Normalizes phone numbers to standard E.164.
    Handles Tanzanian local formats (07..., 06...) as well as international numbers.
    """
    clean = re.sub(r"[\s\-\(\)\.]", "", str(phone).strip())
    if not clean:
        raise ValueError("Phone number cannot be empty")

    if clean.startswith("+"):
        normalized = clean
    elif clean.startswith("00"):
        normalized = "+" + clean[2:]
    elif clean.startswith("0"):
        cc = default_country_code if default_country_code.startswith("+") else f"+{default_country_code}"
        normalized = f"{cc}{clean[1:]}"
    elif clean.startswith("255"):
        normalized = f"+{clean}"
    elif clean.startswith(default_country_code.lstrip("+")):
        normalized = f"+{clean}"
    else:
        cc = default_country_code if default_country_code.startswith("+") else f"+{default_country_code}"
        normalized = f"{cc}{clean}"

    if not E164_REGEX.match(normalized):
        raise ValueError(
            f"Invalid E.164 phone number: '{phone}'. Must be + followed by 7-15 digits (e.g., +255712345678)."
        )
    return normalized


def classify_mno(normalized_phone: str) -> str:
    """
    Classifies the Mobile Network Operator (MNO) for a normalized E.164 number.
    Returns: VODACOM_TZ, AIRTEL_TZ, YAS_TIGO_TZ, HALOTEL_TZ, TTCL_TZ, INTERNATIONAL, or UNKNOWN.
    """
    if not normalized_phone.startswith("+255"):
        return "INTERNATIONAL"

    # Check 6-character prefix (e.g., '+25574')
    prefix = normalized_phone[:6]
    return MNO_PREFIX_MAP.get(prefix, "UNKNOWN")


# ---------------------------------------------------------------------------
# 2. GSM 03.38 Standard vs. UCS-2 Encoding & Multipart Calculations
# ---------------------------------------------------------------------------
# Standard GSM 7-bit default alphabet (basic character set - 1 septet each)
GSM_7BIT_BASIC = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)

# GSM 7-bit extension table (takes 2 septets: ESCAPE 0x1B + character)
GSM_7BIT_EXTENDED = set("|^{}\\[~]€")


def calculate_sms_encoding_and_parts(text: str) -> Tuple[str, int, int]:
    """
    Inspects every character in the message according to 3GPP TS 23.038 / GSM 03.38 standard.
    Returns: (encoding, parts_count, septets_or_chars_count)
      - encoding: 'GSM_7BIT' or 'UCS_2'
      - parts_count: integer count of SMS segments
      - septets_or_chars_count: total septets for GSM-7 or character length for UCS-2
    """
    if not text:
        return "GSM_7BIT", 1, 0

    total_septets = 0
    is_gsm = True

    for char in text:
        if char in GSM_7BIT_BASIC:
            total_septets += 1
        elif char in GSM_7BIT_EXTENDED:
            total_septets += 2  # Escape septet + char septet
        else:
            is_gsm = False
            break

    if is_gsm:
        encoding = "GSM_7BIT"
        if total_septets <= 160:
            parts = 1
        else:
            parts = math.ceil(total_septets / 153)
        return encoding, parts, total_septets
    else:
        encoding = "UCS_2"
        # In UCS-2 (UTF-16 encoding units)
        length = len(text)
        if length <= 70:
            parts = 1
        else:
            parts = math.ceil(length / 67)
        return encoding, parts, length


# ---------------------------------------------------------------------------
# 3. TCRA Promotional Quiet Hours (21:00 to 06:00 Africa/Dar_es_Salaam EAT)
# ---------------------------------------------------------------------------
EAT_TIMEZONE = timezone(timedelta(hours=3), name="Africa/Dar_es_Salaam")


def is_tcra_quiet_hours(
    dt_utc: Optional[datetime] = None,
    start_hour: int = 21,
    end_hour: int = 6,
) -> Tuple[bool, Optional[datetime]]:
    """
    Checks if current time is within TCRA promotional curfew (21:00 - 06:00 EAT).
    Returns (is_quiet_hours, next_dispatch_time_utc).
    """
    now_utc = dt_utc or datetime.now(timezone.utc)
    now_eat = now_utc.astimezone(EAT_TIMEZONE)

    current_hour = now_eat.hour

    # Quiet hours: 21:00 to 23:59 or 00:00 to 05:59
    if current_hour >= start_hour or current_hour < end_hour:
        # Calculate next 06:00 EAT
        if current_hour >= start_hour:
            # Tomorrow 06:00 EAT
            dispatch_eat = (now_eat + timedelta(days=1)).replace(
                hour=end_hour, minute=0, second=0, microsecond=0
            )
        else:
            # Today 06:00 EAT
            dispatch_eat = now_eat.replace(
                hour=end_hour, minute=0, second=0, microsecond=0
            )
        return True, dispatch_eat.astimezone(timezone.utc)

    return False, None


# ---------------------------------------------------------------------------
# 4. Inbound DND Opt-Out Detection (STOP / ONDOA / JIONDOE / UNSUBSCRIBE)
# ---------------------------------------------------------------------------
DND_OPT_OUT_KEYWORDS = {
    "STOP",
    "ONDOA",
    "JIONDOE",
    "UNSUBSCRIBE",
    "ZUIA",
    "SITAKI",
    "CANCEL",
    "QUIT",
}


def is_opt_out_keyword(body: str) -> bool:
    """Determines whether an inbound SMS is an explicit TCRA DND unsubscribe request."""
    clean = body.strip().upper()
    return clean in DND_OPT_OUT_KEYWORDS


# ---------------------------------------------------------------------------
# 5. Dynamic Spintax & Variable Interpolation Engine
# ---------------------------------------------------------------------------
import random

SPINTAX_PATTERN = re.compile(r"\{([^{}]+)\}")


def render_spintax(text: str, seed: Optional[Any] = None) -> str:
    """
    Resolves Spintax patterns like '{Habari|Mambo|Salamu} jina lake ni...'
    Recursively evaluates nested spintax.
    """
    rng = random.Random(seed) if seed is not None else random

    def _replace_match(match: re.Match) -> str:
        options = match.group(1).split("|")
        return rng.choice(options)

    rendered = text
    while "{" in rendered and "}" in rendered:
        new_text = SPINTAX_PATTERN.sub(_replace_match, rendered)
        if new_text == rendered:
            break
        rendered = new_text

    return rendered


def interpolate_variables(text: str, variables: Optional[Dict[str, Any]] = None) -> str:
    """
    Interpolates variables formatted as {{key}} or {key} from the variables dict.
    Example: 'Habari {{name}}, deni lako ni {{amount}} TZS.'
    """
    if not variables:
        return text

    rendered = text
    for k, v in variables.items():
        val_str = str(v)
        rendered = rendered.replace(f"{{{{{k}}}}}", val_str)
        rendered = rendered.replace(f"{{{k}}}", val_str)
    return rendered
