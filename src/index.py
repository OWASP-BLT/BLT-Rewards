import hmac
import hashlib
import json
from js import Response, URL


async def verify_signature(payload_bytes, signature, secret):
    """
    Verify the cryptographic signature from GitHub.
    GitHub uses HMAC-SHA256 with the secret.
    """
    if not signature or not secret:
        return False
    
    # GitHub sends signature as 'sha256=...'
    if not signature.startswith('sha256='):
        return False
        
    expected_signature = "sha256=" + hmac.new(
        secret.encode('utf-8'),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)


async def on_fetch(request, env):
    """Main request handler for BLT-Rewards Worker"""
    url = URL.new(request.url)
    path = url.pathname
    method = request.method
    
    # CORS headers
    cors_headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, X-Hub-Signature-256, X-GitHub-Delivery',
    }
    
    # Handle CORS preflight
    if method == 'OPTIONS':
        return Response.new('', {'headers': cors_headers})
    
    # Redirect root path to index.html
    if path == '/':
        return Response.new('', {
            'status': 302,
            'headers': {
                **cors_headers,
                'Location': '/index.html'
            }
        })

    # ─── GitHub Webhook Handler ──────────────────────────────────────────
    if (path == '/api/webhook/github' or path == '/webhook') and method == 'POST':
        # 1. Check for required headers
        signature = request.headers.get('x-hub-signature-256')
        delivery_id = request.headers.get('x-github-delivery')
        
        if not signature or not delivery_id:
            return Response.new(
                json.dumps({'error': 'Missing security headers'}), 
                {'status': 400, 'headers': {'Content-Type': 'application/json', **cors_headers}}
            )

        # 2. Get the raw payload
        # Note: We must verify signature on the raw bytes before parsing JSON
        payload_text = await request.text()
        payload_bytes = payload_text.encode('utf-8')

        # 3. Verify Signature (The "Signature Fix")
        # Ensure BACON_WEBHOOK_SECRET is set in Cloudflare dashboard or wrangler.toml
        secret = env.BACON_WEBHOOK_SECRET
        if not secret:
            return Response.new(
                json.dumps({'error': 'Webhook secret not configured on server'}), 
                {'status': 500, 'headers': {'Content-Type': 'application/json', **cors_headers}}
            )

        if not await verify_signature(payload_bytes, signature, secret):
            return Response.new(
                json.dumps({'error': 'Invalid signature'}), 
                {'status': 401, 'headers': {'Content-Type': 'application/json', **cors_headers}}
            )

        # 4. Nonce Tracking / Deduplication (The "Replay Protection")
        # Check if we've already processed this specific delivery ID in Cloudflare KV
        if hasattr(env, 'REWARDS_KV'):
            kv_key = f"webhook_delivery:{delivery_id}"
            
            # Check for existing record
            existing = await env.REWARDS_KV.get(kv_key)
            if existing:
                return Response.new(
                    json.dumps({'status': 'skipped', 'reason': 'Duplicate delivery ID detected (replay protection)'}), 
                    {'status': 200, 'headers': {'Content-Type': 'application/json', **cors_headers}}
                )
            
            # Store the ID to prevent future replays
            # We "put" it now. For production, you'd ideally use expirationTtl to clean up old IDs.
            await env.REWARDS_KV.put(kv_key, "processed")
        else:
            # Fallback if KV is not bound yet, though it should be
            print("Warning: REWARDS_KV not bound to worker")

        # 5. Process the event
        try:
            event_data = json.loads(payload_text)
            event_type = request.headers.get('x-github-event')
            
            print(f"Verified webhook received: {event_type} (Delivery: {delivery_id})")
            
            # TODO: Add specific logic to trigger BACON rewards based on event_data
            # For now, we acknowledge successful receipt and verification
            return Response.new(
                json.dumps({
                    'status': 'success', 
                    'message': 'Webhook verified and recorded',
                    'delivery_id': delivery_id
                }), 
                {'status': 200, 'headers': {'Content-Type': 'application/json', **cors_headers}}
            )
            
        except Exception as e:
            return Response.new(
                json.dumps({'error': f'Failed to process event: {str(e)}'}), 
                {'status': 500, 'headers': {'Content-Type': 'application/json', **cors_headers}}
            )
    
    # All other routes handled by Cloudflare's static asset serving (return None)
    return None
