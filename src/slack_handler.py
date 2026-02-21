"""
Slack bot handler for the /bacon slash command.

Command usage:
  /bacon @user <amount>          – Send BACON to a user
  /bacon approve @user           – (admins only) Add a user to the allowlist
  /bacon remove @user            – (admins only) Remove a user from the allowlist
  /bacon list                    – (admins only) Show the current allowlist

Access control – checked in priority order, NO outbound HTTP calls:
  1. ADMIN_USER_IDS env var (comma-separated user IDs)  → admin + authorized
  2. D1 approved_users row with is_admin = 1            → admin + authorized
  3. D1 approved_users row with is_admin = 0            → authorized only

Only admins (tiers 1 or 2) can use approve / remove / list.

To bootstrap: add your own Slack user ID to ADMIN_USER_IDS in wrangler.toml,
deploy, then use `/bacon approve @someone` to delegate from within Slack.

Environment variables / Worker secrets required:
  SLACK_SIGNING_SECRET  – Found in your Slack app's "Basic Information" page.
  ADMIN_USER_IDS        – (optional) Comma-separated Slack user IDs, e.g.
                          "U012AB3CD,U098ZY7WX". These users are always admins.

D1 binding required (set in wrangler.toml):
  DB  – Cloudflare D1 database.
        Run migrations/0001_init.sql then migrations/0002_add_is_admin.sql.
"""

import hashlib
import hmac
import json
import re
import time


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------

def _verify_slack_signature(signing_secret: str, request_body: str,
                             timestamp: str, signature: str) -> bool:
    """
    Verify Slack's HMAC-SHA256 request signature.
    https://api.slack.com/authentication/verifying-requests-from-slack
    """
    try:
        if abs(time.time() - float(timestamp)) > 300:
            return False
    except (ValueError, TypeError):
        return False

    sig_basestring = f"v0:{timestamp}:{request_body}".encode("utf-8")
    computed = "v0=" + hmac.new(
        signing_secret.encode("utf-8"),
        sig_basestring,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(computed, signature)


# ---------------------------------------------------------------------------
# Authorization helpers
# ---------------------------------------------------------------------------

async def _resolve_authorization(user_id: str, env) -> tuple:
    """
    Return (is_authorized, is_admin) for the given Slack user_id.

    is_authorized – can use /bacon at all
    is_admin      – can approve / remove / list users

    Priority order:
      1. ADMIN_USER_IDS env var  → admin + authorized  (bootstrap)
      2. D1 approved_users table → authorized
      3. D1 approved_users with is_admin=1 → also admin
    """
    # 1. Bootstrap env-var allowlist (always checked first, no DB round-trip)
    admin_ids_raw = getattr(env, "ADMIN_USER_IDS", "") or ""
    hard_admin_ids = {uid.strip() for uid in admin_ids_raw.split(",") if uid.strip()}
    if user_id in hard_admin_ids:
        return True, True

    # 2. D1 approved_users table
    db = getattr(env, "DB", None)
    if db:
        try:
            row = await db.prepare(
                "SELECT is_admin FROM approved_users WHERE user_id = ?"
            ).bind(user_id).first()
            if row:
                is_db_admin = bool(getattr(row, "is_admin", 0))
                return True, is_db_admin
        except Exception:
            pass

    return False, False


# ---------------------------------------------------------------------------
# Text parsers
# ---------------------------------------------------------------------------

def _parse_transfer(text: str):
    """
    Parse '/bacon @user <amount>' command text.

    Returns (mention, amount, display_name) or (None, None, None).
    """
    text = text.strip()

    # Rich Slack mention: <@U12345|name> 50
    rich = re.match(r"^<@([A-Z0-9]+)\|?([^>]*)>\s+([\d]+(?:\.\d+)?)$", text)
    if rich:
        user_id  = rich.group(1)
        display  = rich.group(2) or user_id
        amount   = float(rich.group(3))
        return f"<@{user_id}>", amount, display

    # Plain @username 50
    plain = re.match(r"^@([\w.\-]+)\s+([\d]+(?:\.\d+)?)$", text)
    if plain:
        username = plain.group(1)
        amount   = float(plain.group(2))
        return f"@{username}", amount, username

    return None, None, None


def _parse_user_mention(text: str):
    """
    Extract a user mention from approve/remove command text.

    Returns (user_id_or_none, display_name) where user_id is only populated
    for rich Slack mentions (<@U…|name>).
    """
    text = text.strip()

    # Rich mention: <@U12345|name>
    rich = re.match(r"^<@([A-Z0-9]+)\|?([^>]*)>$", text)
    if rich:
        uid     = rich.group(1)
        display = rich.group(2) or uid
        return uid, display

    # Plain @username
    plain = re.match(r"^@([\w.\-]+)$", text)
    if plain:
        return None, plain.group(1)

    return None, None


# ---------------------------------------------------------------------------
# Slack response builder
# ---------------------------------------------------------------------------

def _slack_response(text: str, response_type: str = "ephemeral") -> dict:
    """Build a minimal Slack slash-command response payload."""
    return {"response_type": response_type, "text": text}


# ---------------------------------------------------------------------------
# Sub-command handlers
# ---------------------------------------------------------------------------

async def _handle_approve(sender_id: str, sender_name: str, arg: str, env) -> str:
    """Add a user to the D1 approved_users table. Returns a status string."""
    uid, display = _parse_user_mention(arg)
    if not display:
        return ":x: Usage: `/bacon approve @user`"

    if not uid:
        return (
            f":x: Could not resolve a Slack user ID for `@{display}`.\n"
            "Please @-mention the user directly (e.g. `/bacon approve <@U12345>`)"
        )

    db = getattr(env, "DB", None)
    if not db:
        return ":x: D1 database is not bound. Check `wrangler.toml`."

    try:
        await db.prepare(
            "INSERT OR REPLACE INTO approved_users (user_id, user_name, added_by, added_at, is_admin) "
            "VALUES (?, ?, ?, ?, 0)"
        ).bind(uid, display, sender_id, int(time.time())).run()
        return f":white_check_mark: `@{display}` (`{uid}`) has been added to the /bacon allowlist."
    except Exception as exc:
        return f":x: Database error: {exc}"


async def _handle_remove(sender_id: str, arg: str, env) -> str:
    """Remove a user from the D1 approved_users table. Returns a status string."""
    uid, display = _parse_user_mention(arg)
    if not display:
        return ":x: Usage: `/bacon remove @user`"

    if not uid:
        return (
            f":x: Could not resolve a Slack user ID for `@{display}`.\n"
            "Please @-mention the user directly."
        )

    db = getattr(env, "DB", None)
    if not db:
        return ":x: D1 database is not bound. Check `wrangler.toml`."

    try:
        await db.prepare(
            "DELETE FROM approved_users WHERE user_id = ?"
        ).bind(uid).run()
        return f":wastebasket: `@{display}` (`{uid}`) has been removed from the /bacon allowlist."
    except Exception as exc:
        return f":x: Database error: {exc}"


async def _handle_list(env) -> str:
    """Return a formatted list of all approved users from D1."""
    db = getattr(env, "DB", None)
    if not db:
        return ":x: D1 database is not bound. Check `wrangler.toml`."

    try:
        result = await db.prepare(
            "SELECT user_id, user_name FROM approved_users ORDER BY added_at ASC"
        ).all()
        rows = result.results if hasattr(result, "results") else []
        if not rows:
            return ":information_source: The approved-user allowlist is currently empty. Workspace admins always have access."
        lines = [":bacon: *Approved /bacon users:*"]
        for row in rows:
            uid  = getattr(row, "user_id",   "?")
            name = getattr(row, "user_name",  "?")
            lines.append(f"  • `<@{uid}>` (`@{name}`)")
        return "\n".join(lines)
    except Exception as exc:
        return f":x: Database error: {exc}"


# ---------------------------------------------------------------------------
# Main entry point called from index.py
# ---------------------------------------------------------------------------

async def handle_bacon_command(request, env):
    """
    Handle POST /api/slack/bacon

    Flow:
      1. Verify Slack signature
      2. Parse form body
      3. Authorize sender (admin env var / D1 allowlist / Slack API)
      4. Dispatch sub-command (approve | remove | list | transfer)
      5. Persist transfer to D1
      6. Respond to Slack
    """
    from js import Response  # Cloudflare Workers JS interop

    json_headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
    }

    # Global safety net: any unhandled exception must return a valid Slack
    # response (HTTP 200) rather than crashing the Worker, because a crash
    # causes Cloudflare to return a 1101/530 error which Slack reports as
    # "dispatch_failed".
    try:
        return await _handle_bacon_inner(request, env, Response, json_headers)
    except Exception as exc:
        payload = _slack_response(f":x: Internal error: {exc}")
        return Response.new(json.dumps(payload), {"status": 200, "headers": json_headers})


async def _handle_bacon_inner(request, env, Response, json_headers):
    """Inner handler – all exceptions bubble up to handle_bacon_command's safety net."""
    # ------------------------------------------------------------------ #
    # 1. Read raw body (needed for signature verification)                 #
    # ------------------------------------------------------------------ #
    try:
        body_text = await request.text()
    except Exception:
        payload = _slack_response(":x: Could not read request body.")
        return Response.new(json.dumps(payload), {"status": 400, "headers": json_headers})

    # ------------------------------------------------------------------ #
    # 2. Verify Slack signature                                            #
    # ------------------------------------------------------------------ #
    signing_secret = getattr(env, "SLACK_SIGNING_SECRET", None)
    if signing_secret:
        # JS Headers.get() returns null (Python None) for missing headers,
        # not "", so we must coerce explicitly.
        timestamp = request.headers.get("X-Slack-Request-Timestamp") or ""
        signature = request.headers.get("X-Slack-Signature") or ""
        if not _verify_slack_signature(signing_secret, body_text, timestamp, signature):
            payload = _slack_response(":x: Request signature verification failed.")
            return Response.new(json.dumps(payload), {"status": 401, "headers": json_headers})

    # ------------------------------------------------------------------ #
    # 3. Parse form body                                                   #
    # ------------------------------------------------------------------ #
    from urllib.parse import unquote_plus

    form_data: dict = {}
    for pair in body_text.split("&"):
        if "=" in pair:
            k, _, v = pair.partition("=")
            form_data[k] = unquote_plus(v)

    command_text = form_data.get("text", "").strip()
    sender_name  = form_data.get("user_name", "someone")
    sender_id    = form_data.get("user_id", "")
    channel_id   = form_data.get("channel_id", "")

    # ------------------------------------------------------------------ #
    # 4. Show usage when no arguments given                                #
    # ------------------------------------------------------------------ #
    if not command_text:
        usage = (
            ":bacon: *BACON slash command*\n"
            "*Usage:*\n"
            "  `/bacon @user <amount>` – Send BACON to someone\n"
            "  `/bacon approve @user`  – _(admins)_ Add user to allowlist\n"
            "  `/bacon remove @user`   – _(admins)_ Remove user from allowlist\n"
            "  `/bacon list`           – _(admins)_ Show the allowlist"
        )
        payload = _slack_response(usage)
        return Response.new(json.dumps(payload), {"status": 200, "headers": json_headers})

    # ------------------------------------------------------------------ #
    # 5. Authorize the sender                                              #
    # ------------------------------------------------------------------ #
    try:
        is_authorized, is_admin = await _resolve_authorization(sender_id, env)
    except Exception:
        is_authorized, is_admin = False, False

    if not is_authorized:
        payload = _slack_response(
            ":no_entry: You are not authorized to use `/bacon`.\n"
            "Ask a workspace admin to run `/bacon approve @you`."
        )
        return Response.new(json.dumps(payload), {"status": 200, "headers": json_headers})

    # ------------------------------------------------------------------ #
    # 6. Dispatch sub-commands (admin only)                                #
    # ------------------------------------------------------------------ #
    lower = command_text.lower()

    if lower.startswith("approve "):
        if not is_admin:
            payload = _slack_response(":no_entry: Only workspace admins can approve users.")
            return Response.new(json.dumps(payload), {"status": 200, "headers": json_headers})
        arg = command_text[len("approve "):].strip()
        msg = await _handle_approve(sender_id, sender_name, arg, env)
        payload = _slack_response(msg)
        return Response.new(json.dumps(payload), {"status": 200, "headers": json_headers})

    if lower.startswith("remove "):
        if not is_admin:
            payload = _slack_response(":no_entry: Only workspace admins can remove users.")
            return Response.new(json.dumps(payload), {"status": 200, "headers": json_headers})
        arg = command_text[len("remove "):].strip()
        msg = await _handle_remove(sender_id, arg, env)
        payload = _slack_response(msg)
        return Response.new(json.dumps(payload), {"status": 200, "headers": json_headers})

    if lower == "list":
        if not is_admin:
            payload = _slack_response(":no_entry: Only workspace admins can list approved users.")
            return Response.new(json.dumps(payload), {"status": 200, "headers": json_headers})
        msg = await _handle_list(env)
        payload = _slack_response(msg)
        return Response.new(json.dumps(payload), {"status": 200, "headers": json_headers})

    # ------------------------------------------------------------------ #
    # 7. Parse transfer: /bacon @user <amount>                             #
    # ------------------------------------------------------------------ #
    mention, amount, display_name = _parse_transfer(command_text)

    if mention is None:
        error_msg = (
            f":x: Could not parse `{command_text}`.\n"
            "*Usage:* `/bacon @user <amount>`  |  `/bacon approve @user`  |  `/bacon list`"
        )
        payload = _slack_response(error_msg)
        return Response.new(json.dumps(payload), {"status": 200, "headers": json_headers})

    if amount <= 0:
        payload = _slack_response(":x: Amount must be greater than 0.")
        return Response.new(json.dumps(payload), {"status": 200, "headers": json_headers})

    # ------------------------------------------------------------------ #
    # 8. Persist transfer to D1                                            #
    # ------------------------------------------------------------------ #
    db = getattr(env, "DB", None)
    if db:
        try:
            await db.prepare(
                "INSERT INTO transfers "
                "(from_user_id, from_user_name, to_user_display, amount, channel_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)"
            ).bind(
                sender_id, sender_name, display_name, amount, channel_id, int(time.time())
            ).run()
        except Exception:
            pass  # Non-fatal – transfer is still announced

    # ------------------------------------------------------------------ #
    # 9. Respond to Slack                                                  #
    # ------------------------------------------------------------------ #
    success_msg = (
        f":bacon: *@{sender_name}* sent *{amount:g} BACON* to *{mention}*! "
        f"Keep contributing to earn more! :rocket:"
    )
    payload = _slack_response(success_msg, response_type="in_channel")
    return Response.new(json.dumps(payload), {"status": 200, "headers": json_headers})
