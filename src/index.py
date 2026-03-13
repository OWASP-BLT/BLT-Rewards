"""Main entry point for BLT-Rewards (BACON) - Cloudflare Worker"""

import js
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
                # add 5‑second timeout to avoid hanging
                from js import AbortSignal
                resp = await js.fetch(ord_url, {"signal": AbortSignal.timeout(5000)})
                if resp.ok:
                    # convert JS proxy object to native Python dict
                    body = await resp.json()
                    try:
                        body = body.to_py()
                    except Exception:
                        # fallback: treat as dict or empty
                        if not isinstance(body, dict):
                            try:
                                body = json.loads(await resp.text())
                            except Exception:
                                body = {}
                    if isinstance(body, dict) and body.get('success'):
                        data['balance'] = body.get('balance', data['balance'])
        except Exception as e:
            # log failure so we can debug if ord-server is unreachable or timeout
            try:
                js.console.error('status fetch failed', str(e))
            except Exception:
                pass

        #if hasattr(env, 'TREASURY_ADDRESS'):
        #    data['address'] = env.TREASURY_ADDRESS
        # tmp hardcode address
        data['address'] = "mntjJdXMvLkALMnyYFsdvxUnFXjLzLPpiNQwQSC58BL"
        return Response.new(json.dumps(data), {'status': 200, 'headers': {**cors_headers, 'Content-Type': 'application/json'}})

    # fall through to asset serving
    return None
