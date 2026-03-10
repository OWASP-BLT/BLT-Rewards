"""Main entry point for BLT-Rewards (BACON) - Cloudflare Worker"""

from js import Response, URL
import json


async def on_fetch(request, env):
    """Basic fetch handler for static assets and a status API."""
    url = URL.new(request.url)
    path = url.pathname

    # generic CORS headers
    cors_headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
    }

    if request.method == 'OPTIONS':
        return Response.new('', {'headers': cors_headers})

    if path == '/':
        return Response.new('', {
            'status': 302,
            'headers': {**cors_headers, 'Location': '/index.html'}
        })

    if path == '/api/status':
        # default payload
        data = {'chains': ['Bitcoin', 'Solana'], 'balance': 0}

        # try to fetch actual balance from ord-server if configured
        try:
            ord_url = getattr(env, 'ORD_SERVER_URL_MAINNET', None)
            if ord_url:
                ord_url = ord_url.rstrip('/') + '/mainnet/wallet-balance'
                resp = await js.fetch(ord_url)
                if resp.ok:
                    body = await resp.json()
                    if isinstance(body, dict) and body.get('success'):
                        data['balance'] = body.get('balance', data['balance'])
        except Exception:
            pass

        if hasattr(env, 'TREASURY_ADDRESS'):
            data['address'] = env.TREASURY_ADDRESS

        return Response.new(json.dumps(data), {'status': 200, 'headers': {**cors_headers, 'Content-Type': 'application/json'}})

    # fall through to asset serving
    return None
