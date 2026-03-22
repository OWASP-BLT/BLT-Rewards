"""BLT-Rewards Cloudflare Worker – public API gateway + static site host."""

import hmac
import hashlib
import json
from js import Response, URL, fetch


def _json_error(message: str, status: int) -> Response:
    """Return a JSON error response."""
    return Response.new(
        json.dumps({"success": False, "error": message}),
        {"status": status, "headers": {"Content-Type": "application/json"}},
    )


def _verify_signature(body: bytes, signature_header: str, secret: str) -> bool:
    """Constant-time HMAC-SHA256 check against X-Signature-256 header."""
    if not signature_header.startswith("sha256="):
        return False
    expected_hex = signature_header[len("sha256="):]
    if len(expected_hex) != 64:
        return False
    try:
        expected_bytes = bytes.fromhex(expected_hex)
    except ValueError:
        return False
    computed = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return hmac.compare_digest(expected_bytes, computed)


async def on_fetch(request, env):
    """Route traffic: serve static site or proxy authenticated API calls."""
    url = URL.new(request.url)
    path = url.pathname

    # ── Static site ──────────────────────────────────────────────────────────
    if not (path.startswith("/mainnet/") or path.startswith("/regtest/")):
        if path == "/":
            return Response.new("", {"status": 302, "headers": {"Location": "/index.html"}})
        return None  # Cloudflare serves the static asset directly

    # ── API routes: verify signature then proxy to private ord backend ────────
    secret = getattr(env, "WEBHOOK_SECRET", None)
    backend_url = getattr(env, "ORD_BACKEND_URL", None)

    if not secret:
        return _json_error("Webhook secret not configured on server", 500)
    if not backend_url:
        return _json_error("Backend service not configured", 500)

    body_text = await request.text()
    signature = request.headers.get("X-Signature-256", "")

    if not _verify_signature(body_text.encode("utf-8"), signature, secret):
        return _json_error("Invalid or missing webhook signature", 401)

    query = f"?{url.search}" if url.search else ""
    return await fetch(
        f"{backend_url}{path}{query}",
        {"method": request.method, "headers": {"Content-Type": "application/json"}, "body": body_text},
    )
