"""Main entry point for BLT-Rewards (BACON) - Cloudflare Worker"""

from js import Response, URL
import json


async def on_fetch(request, env):
    """Main request handler"""
    url = URL.new(request.url)
    path = url.pathname
    
    # CORS headers
    cors_headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
    }
    
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        return Response.new('', {'headers': cors_headers})
    
    # API routes
    if path.startswith('/api/'):
        return handle_api_request(path, request, cors_headers)
    
    # Redirect root path to index.html
    if path == '/':
        return Response.new('', {
            'status': 302,
            'headers': {
                **cors_headers,
                'Location': '/index.html'
            }
        })
    
    # All other routes (including /index.html and other static files) 
    # are handled by Cloudflare's static asset serving
    # Return None to let Cloudflare serve the static asset
    return None


def handle_api_request(path, request, cors_headers):
    """Handle API requests"""
    
    # Extract query parameters
    url = URL.new(request.url)
    
    if path == '/api/leaderboard':
        ranking = url.searchParams.get('ranking') or 'bacon'
        limit = int(url.searchParams.get('limit') or '100')
        offset = int(url.searchParams.get('offset') or '0')
        
        leaderboard_data = get_mock_leaderboard(ranking, limit, offset)
        return Response.new(json.dumps(leaderboard_data), {
            'headers': {
                **cors_headers,
                'Content-Type': 'application/json'
            }
        })
    
    elif path == '/api/metrics':
        metrics_data = get_mock_metrics()
        return Response.new(json.dumps(metrics_data), {
            'headers': {
                **cors_headers,
                'Content-Type': 'application/json'
            }
        })
    
    elif path == '/api/transactions':
        limit = int(url.searchParams.get('limit') or '20')
        offset = int(url.searchParams.get('offset') or '0')
        
        transactions_data = get_mock_transactions(limit, offset)
        return Response.new(json.dumps(transactions_data), {
            'headers': {
                **cors_headers,
                'Content-Type': 'application/json'
            }
        })
    
    # Return 404 for unknown API routes
    return Response.new(json.dumps({'error': 'Not found'}), {
        'status': 404,
        'headers': {
            **cors_headers,
            'Content-Type': 'application/json'
        }
    })


def get_mock_leaderboard(ranking, limit, offset):
    """Generate mock leaderboard data"""
    contributors = [
        {
            'rank': i+1, 
            'username': f'contributor_{i}', 
            'wallet': f'7{i:039d}', 
            'total_bacon': 1000 - (i*10), 
            'pr_count': 50 - i,
            'avg_value': (1000 - (i*10)) / max(1, 50 - i)
        }
        for i in range(150)
    ]
    
    # Sort by ranking type
    if ranking == 'contributions':
        contributors.sort(key=lambda x: x['pr_count'], reverse=True)
    else:  # bacon (default)
        contributors.sort(key=lambda x: x['total_bacon'], reverse=True)
    
    # Re-rank after sorting
    for idx, contributor in enumerate(contributors):
        contributor['rank'] = idx + 1
    
    # Apply pagination
    paginated = contributors[offset:offset+limit]
    
    return {
        'data': paginated,
        'total': len(contributors),
        'limit': limit,
        'offset': offset
    }


def get_mock_metrics():
    """Generate mock metrics data"""
    return {
        'total_bacon_distributed': 50000,
        'total_active_contributors': 145,
        'avg_reward_per_contributor': 344.83,
        'recent_transaction': {
            'id': 'tx_0',
            'contributor': 'contributor_0',
            'amount': 100,
            'timestamp': '2024-01-01T00:00:00Z'
        }
    }


def get_mock_transactions(limit, offset):
    """Generate mock transaction data"""
    transactions = [
        {
            'signature': f'{i:064x}',
            'username': f'contributor_{i}',
            'amount': 100 - (i % 50),
            'timestamp': f'2024-01-{(i % 28) + 1:02d}T{(i % 24):02d}:00:00Z',
            'explorer_url': f'https://solscan.io/tx/{i:064x}'
        }
        for i in range(500)
    ]
    
    # Sort by timestamp descending (newest first)
    transactions.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # Apply pagination
    paginated = transactions[offset:offset+limit]
    
    return {
        'transactions': paginated,
        'total': len(transactions),
        'limit': limit,
        'offset': offset
    }
