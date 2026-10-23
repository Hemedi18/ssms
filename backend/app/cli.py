import argparse
import sys
from datetime import datetime, timezone, timedelta
from sqlalchemy import select

from app.core.database import SessionLocal, init_db
from app.core.security import generate_api_key
from app.models.api_key import ApiKey
from app.models.device import GatewayDevice
from app.models.message import Message
from app.services.device_service import create_pairing_code


def cmd_init_db(args):
    """Initializes database schema."""
    print("Initializing database tables...")
    init_db()
    print("Database tables initialized successfully.")


def cmd_create_api_key(args):
    """Generates a new API client key with specified scopes."""
    db = SessionLocal()
    try:
        raw_key, prefix, key_hash = generate_api_key(prefix="sms_live_")
        scopes = [s.strip() for s in args.scopes.split(",") if s.strip()]

        expires_at = None
        if args.expires_in_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=args.expires_in_days)

        api_key = ApiKey(
            name=args.name,
            key_hash=key_hash,
            key_prefix=prefix,
            scopes=scopes,
            rate_limit=args.rate_limit,
            expires_at=expires_at,
        )
        db.add(api_key)
        db.commit()
        db.refresh(api_key)

        print("=================================================================")
        print("API KEY CREATED SUCCESSFULLY (Save this now; it will not be shown again!)")
        print("=================================================================")
        print(f"Key ID:       {api_key.id}")
        print(f"Name:         {api_key.name}")
        print(f"Raw Key:      {raw_key}")
        print(f"Prefix:       {prefix}")
        print(f"Scopes:       {scopes}")
        print(f"Rate Limit:   {api_key.rate_limit} req/min")
        if expires_at:
            print(f"Expires At:   {expires_at.isoformat()}")
        print("=================================================================")
    finally:
        db.close()


def cmd_list_api_keys(args):
    """Lists existing API keys with masked secrets."""
    db = SessionLocal()
    try:
        keys = db.scalars(select(ApiKey).order_by(ApiKey.created_at.desc())).all()
        print(f"{'ID':<38} {'NAME':<20} {'PREFIX':<14} {'ACTIVE':<8} {'SCOPES'}")
        print("-" * 90)
        for k in keys:
            print(f"{k.id:<38} {k.name[:18]:<20} {k.key_prefix:<14} {str(k.is_active):<8} {','.join(k.scopes)}")
    finally:
        db.close()


def cmd_revoke_api_key(args):
    """Deactivates an API key."""
    db = SessionLocal()
    try:
        key = db.get(ApiKey, args.id)
        if not key:
            print(f"Error: API key '{args.id}' not found.")
            sys.exit(1)
        key.is_active = False
        db.commit()
        print(f"API key '{args.id}' ({key.name}) has been deactivated.")
    finally:
        db.close()


def cmd_create_pairing_code(args):
    """Generates a temporary pairing code for phone setup."""
    db = SessionLocal()
    try:
        pairing = create_pairing_code(
            db, device_name=args.name, expires_in_seconds=args.expires_in
        )
        print("=================================================================")
        print("DEVICE PAIRING CODE GENERATED")
        print("=================================================================")
        print(f"Pairing Code:   {pairing.code}")
        print(f"Device Name:    {pairing.device_name}")
        print(f"Expires In:     {args.expires_in} seconds ({pairing.expires_at.isoformat()})")
        print("Enter this code in the Android SMS Gateway mobile app under Connect to Server.")
        print("=================================================================")
    finally:
        db.close()


def cmd_list_devices(args):
    """Lists registered gateway devices."""
    db = SessionLocal()
    try:
        devices = db.scalars(select(GatewayDevice).order_by(GatewayDevice.created_at.desc())).all()
        print(f"{'DEVICE ID':<38} {'NAME':<20} {'STATUS':<10} {'SIM':<6} {'LAST SEEN'}")
        print("-" * 90)
        for d in devices:
            status_str = "REVOKED" if d.is_revoked else ("ONLINE" if d.is_online else "OFFLINE")
            sim_str = "YES" if d.sim_ready else "NO"
            last_seen = d.last_seen_at.strftime("%Y-%m-%d %H:%M:%S") if d.last_seen_at else "Never"
            print(f"{d.id:<38} {d.name[:18]:<20} {status_str:<10} {sim_str:<6} {last_seen}")
    finally:
        db.close()


def cmd_list_messages(args):
    """Lists recent messages and delivery status."""
    db = SessionLocal()
    try:
        messages = db.scalars(
            select(Message).order_by(Message.created_at.desc()).limit(args.limit)
        ).all()
        print(f"{'MESSAGE ID':<38} {'RECIPIENT':<16} {'STATUS':<12} {'PARTS':<6} {'CREATED AT'}")
        print("-" * 90)
        for m in messages:
            created = m.created_at.strftime("%Y-%m-%d %H:%M:%S")
            print(f"{m.id:<38} {m.to:<16} {m.status:<12} {m.parts_count:<6} {created}")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="SIM SMS Gateway CLI - Manage API keys, pairing codes, devices, and messages.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # init-db
    subparsers.add_parser("init-db", help="Initialize database tables")

    # create-api-key
    p_key = subparsers.add_parser("create-api-key", help="Create a client API key")
    p_key.add_argument("--name", default="External Application", help="Client name")
    p_key.add_argument(
        "--scopes",
        default="sms:send,sms:read,incoming:read,webhooks:manage",
        help="Comma-separated scopes (sms:send, sms:read, incoming:read, webhooks:manage, admin)",
    )
    p_key.add_argument("--rate-limit", type=int, default=60, help="Max requests per minute")
    p_key.add_argument("--expires-in-days", type=int, default=None, help="Optional validity in days")
    p_key.set_defaults(func=cmd_create_api_key)

    # list-api-keys
    p_lkeys = subparsers.add_parser("list-api-keys", help="List registered API keys")
    p_lkeys.set_defaults(func=cmd_list_api_keys)

    # revoke-api-key
    p_rkey = subparsers.add_parser("revoke-api-key", help="Revoke an API key")
    p_rkey.add_argument("--id", required=True, help="API key UUID")
    p_rkey.set_defaults(func=cmd_revoke_api_key)

    # create-pairing-code
    p_pair = subparsers.add_parser("create-pairing-code", help="Generate temporary device pairing code")
    p_pair.add_argument("--name", default="Android Gateway Phone", help="Device name")
    p_pair.add_argument("--expires-in", type=int, default=600, help="Expiration in seconds (default: 600)")
    p_pair.set_defaults(func=cmd_create_pairing_code)

    # list-devices
    p_devs = subparsers.add_parser("list-devices", help="List gateway devices")
    p_devs.set_defaults(func=cmd_list_devices)

    # list-messages
    p_msgs = subparsers.add_parser("list-messages", help="List recent messages")
    p_msgs.add_argument("--limit", type=int, default=20, help="Maximum messages to display")
    p_msgs.set_defaults(func=cmd_list_messages)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    if hasattr(args, "func"):
        args.func(args)


if __name__ == "__main__":
    main()
