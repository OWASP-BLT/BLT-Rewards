# 🎁 BLT-Rewards Distribution Service

**BLT-Rewards** is a blockchain-agnostic rewards distribution service for the OWASP BLT project, built as a Cloudflare Python Worker for high performance and global edge distribution.

## 🌟 Overview

This service handles the distribution of rewards tokens across multiple blockchain protocols. It provides a simple REST API for:
- Sending rewards tokens to contributors on various blockchains
- Testing token distribution on testnets
- Checking wallet balances
- Managing batch transactions
- Supporting multiple token types (BACON on Bitcoin Runes, SOL rewards on Solana, etc.)

## 🏗️ Architecture

This is a **Cloudflare Python Worker** that acts as an API gateway for blockchain rewards operations. The worker validates requests and forwards them to protocol-specific backend servers that execute actual blockchain operations.

### Two-Tier Architecture

```
Client Request → Cloudflare Worker (Validation/Gateway) → Protocol Backend Servers → Blockchain Nodes
```

**Cloudflare Worker (This Repository)**:
- Request validation and sanitization
- Authentication and rate limiting
- API gateway and routing
- Protocol-agnostic interface
- Global edge distribution

**Backend Servers** (see `ord-server/` and other protocol directories):
- Protocol-specific RPC communication
- Wallet operations
- Transaction execution
- File system operations

This architecture combines Cloudflare's edge performance with the flexibility of protocol-specific backend servers.

### Technology Stack
- **Python 3.11+** - Core language
- **Cloudflare Workers** - Serverless edge computing platform
- **Protocol Backends** - Flask/Python servers for blockchain operations
- **Multi-Chain Support**:
  - **Bitcoin Runes** - BACON tokens via Ord
  - **Solana** - SOL-based rewards
  - **Extensible** - Easy to add new blockchain protocols

## 📋 Prerequisites

### For Cloudflare Worker
- Python 3.11 or higher
- Node.js 14+ (for Cloudflare tooling)
- `uv` package manager ([installation guide](https://github.com/astral-sh/uv))
- Cloudflare Workers account

### For Backend Servers
- Python 3.11+
- Blockchain nodes for your protocols:
  - Bitcoin node with Runes support + Ord (for BACON tokens)
  - Solana node (for SOL rewards)
  - Other protocol-specific requirements
- See protocol-specific README files in backend directories

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/OWASP-BLT/BLT-Rewards.git
cd BLT-Rewards
```

### 2. Install Dependencies

```bash
# Install uv if you haven't already
pip install uv

# Install project dependencies
uv pip install -r requirements.txt
```

### 3. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your configuration
nano .env
```

**Required Configuration:**
- `BACKEND_URLS` - URLs of your protocol-specific backend servers
- `WALLET_API_PASSWORD` - Password for transaction authorization
- `SUPPORTED_PROTOCOLS` - List of enabled blockchain protocols

### 4. Set Up Backend Servers

The Cloudflare Worker forwards requests to protocol-specific backends. See:
- `ord-server/README.md` - For Bitcoin/BACON token distribution
- Protocol-specific directories for other blockchain setups

### 5. Deploy to Cloudflare

```bash
# Deploy to Cloudflare Workers
uv run pywrangler deploy

# Or run locally for testing
uv run pywrangler dev
```

## 📡 API Endpoints

### Health Check
```http
GET /health
```

Returns service status and version information.

**Response:**
```json
{
  "status": "healthy",
  "service": "BLT-Rewards Distribution Service",
  "version": "1.0.0",
  "supported_protocols": ["bitcoin-runes", "solana"]
}
```

### Send Rewards (Generic Endpoint)
```http
POST /{protocol}/send-rewards
Content-Type: application/json
```

Send rewards tokens on any supported blockchain protocol.

**Supported Protocols:**
- `bitcoin-runes` - For BACON tokens on Bitcoin
- `solana` - For SOL-based rewards
- More protocols can be added

### Send BACON Tokens (Bitcoin Runes)
```http
POST /bitcoin-runes/send-rewards
Content-Type: application/json
```

Send BACON tokens to one or more addresses on Bitcoin mainnet.

**Request Body:**
```json
{
  "recipients": [
    {
      "address": "bc1...",
      "amount": 10,
      "token": "BLT•BACON•TOKENS"
    }
  ],
  "fee_rate": 50,
  "dry_run": true,
  "password": "your_secure_password"
}
```

**Parameters:**
- `recipients` (required): Array of recipient objects with address, amount, and token
- `fee_rate` (required): Transaction fee rate in sat/vB
- `dry_run` (optional): If true, simulates transaction without broadcasting (default: true)
- `password` (required when dry_run=false): API password for authorization

**Response:**
```json
{
  "success": true,
  "txid": "abc123...",
  "dry_run": true
}
```

### Send Rewards (Testnet)
```http
POST /{protocol}/send-rewards-test
Content-Type: application/json
```

Send rewards on testnet/regtest for testing purposes.

**Request Body:**
```json
{
  "protocol": "bitcoin-runes",
  "num_users": 5,
  "amount_per_user": 1,
  "fee_rate": 50
}
```

**Parameters:**
- `protocol` (required): Which blockchain protocol to use
- `num_users` (required): Number of recipients (generates test addresses)
- `amount_per_user` (optional): Amount to send to each user (default: 1)
- `fee_rate` (required): Transaction fee rate

**Response:**
```json
{
  "success": true,
  "txid": "test123...",
  "dry_run": true
}
```

### Get Wallet Balance
```http
GET /{protocol}/wallet-balance
Content-Type: application/json
```

Get the current balance for a specific protocol wallet.

**Example:** `GET /bitcoin-runes/wallet-balance`

**Response:**
```json
{
  "success": true,
  "protocol": "bitcoin-runes",
  "balance": "...",
  "tokens": {
    "BLT•BACON•TOKENS": 1000
  }
}
```

## 🔧 Configuration

### Environment Variables

The Cloudflare Worker requires minimal configuration:

**Required Variables:**
- `BACKEND_URLS` - JSON object mapping protocols to backend URLs
  ```json
  {
    "bitcoin-runes": "https://ord.example.com",
    "solana": "https://sol.example.com"
  }
  ```
- `WALLET_API_PASSWORD` - API password for transaction authorization
- `RATE_LIMIT` - Maximum requests per minute (default: 60)
- `SUPPORTED_PROTOCOLS` - Comma-separated list of enabled protocols

See `.env.example` for the complete template.

### Backend Server Configuration

Each protocol backend has its own configuration requirements:

**Bitcoin Runes Backend** (`ord-server/.env.example`):
- `ORD_PATH` - Path to ord binary
- `BITCOIN_RPC_USER_MAINNET` - Bitcoin RPC username
- `BITCOIN_RPC_PASSWORD_MAINNET` - Bitcoin RPC password
- `BITCOIN_RPC_URL_MAINNET` - Bitcoin RPC URL
- And more...

**Solana Backend** (if implemented):
- `SOLANA_RPC_URL` - Solana RPC endpoint
- `SOLANA_WALLET_KEYPAIR` - Wallet keypair path
- And more...

See protocol-specific README files in backend directories for detailed configuration.

### Cloudflare Configuration

Edit `wrangler.jsonc` to customize deployment settings:

```jsonc
{
  "name": "blt-rewards-worker",
  "main": "src/entry.py",
  "compatibility_flags": ["python_workers"],
  "compatibility_date": "2026-03-01"
}
```

## 🧪 Testing

### Local Testing

```bash
# Run the worker locally
uv run pywrangler dev

# Test with curl
curl http://localhost:8787/health
```

### Test Token Distribution

```bash
# Test with dry-run (no actual transaction)
curl -X POST http://localhost:8787/bitcoin-runes/send-rewards \
  -H "Content-Type: application/json" \
  -d '{
    "recipients": [{
      "address": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
      "amount": 1,
      "token": "BLT•BACON•TOKENS"
    }],
    "fee_rate": 50,
    "dry_run": true
  }'
```

## 🔐 Security

- **API Gateway Pattern**: Worker validates all requests before forwarding to protocol backends
- **Password Protection**: Production transactions require authentication via `WALLET_API_PASSWORD`
- **Input Validation**: Request content is validated for structure and size limits
- **Protocol Isolation**: Each blockchain protocol runs in isolated backend
- **Rate Limiting**: Configurable request rate limits per client
- **Dry Run Mode**: Always test with `dry_run: true` before executing real transactions
- **Environment Variables**: Never commit credentials to version control
- **Backend Isolation**: Backend servers not directly exposed to internet

## 📚 Documentation

For more detailed information:
- [Full Documentation](https://owasp-blt.github.io/BLT-Rewards/)
- [OWASP BLT Project](https://owaspblt.org/)
- [Bitcoin Runes Protocol](https://docs.ordinals.com/runes.html)
- [Solana Documentation](https://docs.solana.com/)
- [Cloudflare Workers Python](https://developers.cloudflare.com/workers/languages/python/)

## 🤝 Contributing

We welcome contributions! Please see the [OWASP BLT Contributing Guide](https://github.com/OWASP-BLT/BLT/blob/main/CONTRIBUTING.md) for details.

## 📄 License

This project is part of OWASP BLT and is licensed under the AGPL-3.0 License. See the [LICENSE](LICENSE) file for details.

## 🎯 Project Structure

```
BLT-Rewards/
├── src/
│   └── entry.py          # Cloudflare Worker (API Gateway)
├── ord-server/           # Bitcoin Runes backend (BACON tokens)
│   ├── ord-api.py        # Flask application
│   └── README.md         # Backend setup guide
├── solana-server/        # Solana backend (future)
├── docs/                 # Documentation website
├── wrangler.jsonc        # Cloudflare Workers configuration
├── pyproject.toml        # Python dependencies (worker)
├── .env.example          # Environment variables (worker)
├── index.html            # API documentation page
└── README.md             # This file
```

## 🔗 Related Repositories

- [OWASP BLT](https://github.com/OWASP-BLT/BLT) - Main Bug Logging Tool
- [BLT-Extension](https://github.com/OWASP-BLT/BLT-Extension) - Browser extension
- [BLT-Action](https://github.com/OWASP-BLT/BLT-Action) - GitHub Action

## 💬 Support

- **Issues**: [GitHub Issues](https://github.com/OWASP-BLT/BLT-Rewards/issues)
- **Slack**: [OWASP Slack #project-blt](https://owasp.org/slack/invite)
- **Twitter**: [@OWASP_BLT](https://twitter.com/OWASP_BLT)

---

Made with ❤️ by the OWASP BLT Community
