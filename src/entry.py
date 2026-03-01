"""
BLT-Rewards Distribution Service
A Cloudflare Python Worker for distributing rewards across multiple blockchain protocols.

This worker acts as an API gateway and request validator, forwarding validated requests
to protocol-specific backend servers that handle actual blockchain operations.
"""

import json
import os
from typing import Any, Dict, List
from urllib.parse import urlparse

try:
    import yaml
except ImportError:
    # Fallback if yaml not available in worker environment
    yaml = None


class Response:
    """Simple response class for Cloudflare Workers."""

    def __init__(self, body: str, status: int = 200, headers: Dict[str, str] = None):
        self.body = body
        self.status = status
        self.headers = headers or {"Content-Type": "application/json"}


class RewardsWorker:
    """
    Main worker class for multi-chain rewards distribution.
    
    Acts as an API gateway that validates requests and forwards them to protocol-specific
    backend servers. This architecture allows the worker to run in Cloudflare's sandboxed
    environment while the actual blockchain operations run on traditional servers.
    """

    def __init__(self):
        # Backend server URLs (JSON map of protocol -> URL)
        backend_urls_str = os.getenv("BACKEND_URLS", "{}")
        try:
            self.backend_urls = json.loads(backend_urls_str)
        except json.JSONDecodeError:
            self.backend_urls = {}
        
        # Supported protocols
        protocols_str = os.getenv("SUPPORTED_PROTOCOLS", "bitcoin-runes")
        self.supported_protocols = [p.strip() for p in protocols_str.split(",")]
        
        # API authentication
        self.wallet_api_password = os.getenv("WALLET_API_PASSWORD", "wallet_password")
        
        # Rate limiting (requests per minute)
        self.rate_limit = int(os.getenv("RATE_LIMIT", "60"))

    def _validate_protocol(self, protocol: str) -> tuple[bool, str]:
        """
        Validate that the protocol is supported.
        
        Returns: (is_valid, error_message)
        """
        if not protocol:
            return False, "Protocol is required"
        
        if protocol not in self.supported_protocols:
            return False, f"Protocol '{protocol}' is not supported. Supported: {', '.join(self.supported_protocols)}"
        
        if protocol not in self.backend_urls:
            return False, f"Backend URL not configured for protocol '{protocol}'"
        
        return True, ""

    def _validate_recipients(self, recipients: List[Dict[str, Any]]) -> tuple[bool, str]:
        """
        Validate recipients list for rewards distribution.
        
        Returns: (is_valid, error_message)
        """
        if not recipients or not isinstance(recipients, list):
            return False, "Recipients must be a non-empty list"
        
        if len(recipients) > 1000:
            return False, "Too many recipients (max 1000)"
        
        for i, recipient in enumerate(recipients):
            if not isinstance(recipient, dict):
                return False, f"Recipient {i} must be an object"
            
            if "address" not in recipient:
                return False, f"Recipient {i} missing 'address' field"
            
            if "amount" not in recipient:
                return False, f"Recipient {i} missing 'amount' field"
            
            if not isinstance(recipient["amount"], (int, float)) or recipient["amount"] <= 0:
                return False, f"Recipient {i} amount must be positive"
        
        return True, ""

    async def send_rewards(self, protocol: str, request_data: Dict[str, Any]) -> Response:
        """
        Generic method to send rewards on any supported protocol.
        """
        # Validate protocol
        is_valid, error_msg = self._validate_protocol(protocol)
        if not is_valid:
            return Response(
                json.dumps({"success": False, "error": error_msg}),
                status=400,
            )
        
        # Validate recipients
        recipients = request_data.get("recipients", [])
        is_valid, error_msg = self._validate_recipients(recipients)
        if not is_valid:
            return Response(
                json.dumps({"success": False, "error": error_msg}),
                status=400,
            )
        
        # Validate fee rate (if applicable)
        fee_rate = request_data.get("fee_rate")
        if fee_rate and not isinstance(fee_rate, (int, float)):
            return Response(
                json.dumps({"success": False, "error": "Invalid fee_rate"}),
                status=400,
            )
        
        # Check dry run mode and authentication
        is_dry_run = request_data.get("dry_run", True)
        if not is_dry_run:
            password = request_data.get("password")
            if not password:
                return Response(
                    json.dumps({"success": False, "error": "Password required for non-dry-run"}),
                    status=400,
                )
            elif password != self.wallet_api_password:
                return Response(
                    json.dumps({"success": False, "error": "Invalid password"}),
                    status=401,
                )
        
        # Forward to protocol-specific backend
        backend_url = self.backend_urls[protocol]
        try:
            backend_response = await self._fetch_backend(
                f"{backend_url}/send-rewards",
                method="POST",
                body=json.dumps(request_data),
                headers={"Content-Type": "application/json"},
            )
            return Response(backend_response, status=200)
        except Exception as e:
            return Response(
                json.dumps({"success": False, "error": f"Backend error: {str(e)}"}),
                status=500,
            )

    def _validate_yaml_content(self, yaml_content: str) -> tuple[bool, str]:
        """
        Validate YAML content for security and structure.
        
        Returns: (is_valid, error_message)
        """
        if not yaml_content or not isinstance(yaml_content, str):
            return False, "YAML content must be a non-empty string"
        
        if len(yaml_content) > 1_000_000:  # 1MB limit
            return False, "YAML content too large (max 1MB)"
        
        # Basic structure validation if yaml module available
        if yaml:
            try:
                data = yaml.safe_load(yaml_content)
                if not isinstance(data, dict) or "outputs" not in data:
                    return False, "YAML must contain 'outputs' key"
                if not isinstance(data["outputs"], list):
                    return False, "outputs must be a list"
            except yaml.YAMLError as e:
                return False, f"Invalid YAML format: {str(e)}"
        
        return True, ""

    async def send_bacon_tokens_mainnet(self, request_data: Dict[str, Any]) -> Response:
        """
        Validate and forward mainnet token distribution request to backend.
        """
        yaml_content = request_data.get("yaml_content")
        fee_rate = request_data.get("fee_rate")
        is_dry_run = request_data.get("dry_run", True)

        # Validate YAML content
        is_valid, error_msg = self._validate_yaml_content(yaml_content)
        if not is_valid:
            return Response(
                json.dumps({"success": False, "error": error_msg}),
                status=400,
            )

        # Validate fee rate
        if not fee_rate or not isinstance(fee_rate, (int, float)):
            return Response(
                json.dumps({"success": False, "error": "Valid fee_rate is required"}),
                status=400,
            )
        
        if fee_rate < 1 or fee_rate > 1000:
            return Response(
                json.dumps({"success": False, "error": "fee_rate must be between 1 and 1000 sat/vB"}),
                status=400,
            )

        # Validate authentication for real transactions
        if not is_dry_run:
            password = request_data.get("password")
            if not password:
                return Response(
                    json.dumps({"success": False, "error": "Password is required for non-dry-run transactions"}),
                    status=400,
                )
            elif password != self.wallet_api_password:
                return Response(
                    json.dumps({"success": False, "error": "Invalid password"}),
                    status=401,
                )

        # Forward to backend ord server
        if not self.ord_backend_url:
            return Response(
                json.dumps({"success": False, "error": "Backend server not configured"}),
                status=500,
            )

        try:
            # Use fetch API to call backend (Cloudflare Workers native)
            backend_response = await self._fetch_backend(
                f"{self.ord_backend_url}/mainnet/send-bacon-tokens",
                method="POST",
                body=json.dumps(request_data),
                headers={"Content-Type": "application/json"},
            )
            return Response(backend_response, status=200)
        except Exception as e:
            return Response(
                json.dumps({"success": False, "error": f"Backend error: {str(e)}"}),
                status=500,
            )

    async def send_bacon_tokens_regtest(self, request_data: Dict[str, Any]) -> Response:
        """
        Validate and forward regtest token distribution request to backend.
        """
        num_users = request_data.get("num_users")
        fee_rate = request_data.get("fee_rate")

        # Validate num_users
        if not num_users or not isinstance(num_users, int) or num_users <= 0:
            return Response(
                json.dumps({"success": False, "error": "num_users must be a positive integer"}),
                status=400,
            )
        
        if num_users > 1000:
            return Response(
                json.dumps({"success": False, "error": "num_users cannot exceed 1000"}),
                status=400,
            )

        # Validate fee rate
        if not fee_rate or not isinstance(fee_rate, (int, float)):
            return Response(
                json.dumps({"success": False, "error": "Valid fee_rate is required"}),
                status=400,
            )
        
        if fee_rate < 1 or fee_rate > 1000:
            return Response(
                json.dumps({"success": False, "error": "fee_rate must be between 1 and 1000 sat/vB"}),
                status=400,
            )

        # Forward to backend ord server
        if not self.ord_backend_url:
            return Response(
                json.dumps({"success": False, "error": "Backend server not configured"}),
                status=500,
            )

        try:
            backend_response = await self._fetch_backend(
                f"{self.ord_backend_url}/regtest/send-bacon-tokens",
                method="POST",
                body=json.dumps(request_data),
                headers={"Content-Type": "application/json"},
            )
            return Response(backend_response, status=200)
        except Exception as e:
            return Response(
                json.dumps({"success": False, "error": f"Backend error: {str(e)}"}),
                status=500,
            )

    async def get_wallet_balance(self, protocol: str) -> Response:
        """
        Get wallet balance for a specific protocol.
        """
        # Validate protocol
        is_valid, error_msg = self._validate_protocol(protocol)
        if not is_valid:
            return Response(
                json.dumps({"success": False, "error": error_msg}),
                status=400,
            )
        
        backend_url = self.backend_urls[protocol]
        try:
            backend_response = await self._fetch_backend(
                f"{backend_url}/wallet-balance",
                method="GET",
            )
            return Response(backend_response, status=200)
        except Exception as e:
            return Response(
                json.dumps({"success": False, "error": f"Backend error: {str(e)}"}),
                status=500,
            )

    async def get_wallet_balance_mainnet(self) -> Response:
        """
        Forward wallet balance request to backend.
        """
        if not self.ord_backend_url:
            return Response(
                json.dumps({"success": False, "error": "Backend server not configured"}),
                status=500,
            )

        try:
            backend_response = await self._fetch_backend(
                f"{self.ord_backend_url}/mainnet/wallet-balance",
                method="GET",
            )
            return Response(backend_response, status=200)
        except Exception as e:
            return Response(
                json.dumps({"success": False, "error": f"Backend error: {str(e)}"}),
                status=500,
            )

    async def _fetch_backend(self, url: str, method: str = "GET", body: str = None, headers: Dict[str, str] = None) -> str:
        """
        Helper method to fetch from backend server.
        Uses Cloudflare Workers' fetch API.
        """
        # This will be implemented using Cloudflare's fetch API
        # For now, return a placeholder that indicates the architecture
        raise NotImplementedError(
            "Backend fetch not yet implemented. "
            "This worker needs to be deployed with proper fetch implementation."
        )

    async def handle_request(self, request: Any) -> Response:
        """Main request handler with multi-protocol support."""
        try:
            # Parse URL path safely using urlparse
            parsed_url = urlparse(request.url)
            path = parsed_url.path.lstrip("/")
            parts = path.split("/")
            
            # Health check endpoint
            if path == "" or path == "health":
                return Response(
                    json.dumps({
                        "status": "healthy",
                        "service": "BLT-Rewards Distribution Service",
                        "version": "1.0.0",
                        "architecture": "API Gateway -> Protocol Backends",
                        "supported_protocols": self.supported_protocols,
                    }),
                    status=200,
                )
            
            # Protocol-specific endpoints: /{protocol}/send-rewards
            if len(parts) >= 2 and parts[1] == "send-rewards" and request.method == "POST":
                protocol = parts[0]
                body = await request.json()
                return await self.send_rewards(protocol, body)
            
            # Protocol-specific wallet balance: /{protocol}/wallet-balance
            if len(parts) >= 2 and parts[1] == "wallet-balance" and request.method == "GET":
                protocol = parts[0]
                return await self.get_wallet_balance(protocol)
            
            # Backward compatibility: Legacy BACON endpoints
            if path == "mainnet/send-bacon-tokens" and request.method == "POST":
                body = await request.json()
                return await self.send_bacon_tokens_mainnet(body)

            elif path == "regtest/send-bacon-tokens" and request.method == "POST":
                body = await request.json()
                return await self.send_bacon_tokens_regtest(body)

            elif path == "mainnet/wallet-balance" and request.method == "GET":
                return await self.get_wallet_balance_mainnet()
            
            # Not found
            else:
                return Response(
                    json.dumps({
                        "error": "Not found",
                        "hint": "Use /{protocol}/send-rewards or /{protocol}/wallet-balance"
                    }),
                    status=404,
                )

        except Exception as e:
            return Response(
                json.dumps({"error": str(e)}),
                status=500,
            )


# Cloudflare Worker entry point
try:
    from workers import WorkerEntrypoint

    class Default(WorkerEntrypoint):
        async def fetch(self, request):
            worker = RewardsWorker()
            return await worker.handle_request(request)

except ImportError:
    # Fallback for local testing without Cloudflare Workers SDK
    worker = RewardsWorker()
