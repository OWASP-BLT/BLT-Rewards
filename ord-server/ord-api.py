import subprocess
import os
import uuid
import time
import hmac
import hashlib
import yaml
import hmac
import hashlib
from flask import Flask, jsonify, request
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)


def verify_webhook_signature(req):
    """Verify the HMAC-SHA256 webhook signature from the X-Signature-256 header.

    The caller must send:
        X-Signature-256: sha256=<hex_digest>

    where hex_digest = HMAC-SHA256(WEBHOOK_SECRET, raw_request_body).

    Returns True if the signature is valid, False otherwise.
    """
    secret = os.getenv("WEBHOOK_SECRET")
    if not secret:
        # If no secret is configured, reject all requests for safety.
        return False

    signature_header = req.headers.get("X-Signature-256", "")
    if not signature_header.startswith("sha256="):
        return False

    expected_sig = signature_header[len("sha256="):]
    # Require a 64-character hex-encoded SHA-256 digest to keep comparison timing-safe.
    if len(expected_sig) != 64:
        return False
    try:
        expected_sig_bytes = bytes.fromhex(expected_sig)
    except ValueError:
        return False

    computed_sig = hmac.new(
        secret.encode("utf-8"),
        req.get_data(),
        hashlib.sha256,
    ).digest()

    return hmac.compare_digest(expected_sig_bytes, computed_sig)

# Environment Variables
ORD_PATH = os.getenv("ORD_PATH", "/usr/local/bin/ord")
YAML_FILE_PATH = os.getenv("YAML_FILE_PATH", "/blockchain/ord-flask-server/tmp-batch.yaml")

# Bitcoin RPC Configuration for Mainnet
BITCOIN_RPC_USER_MAINNET = os.getenv("BITCOIN_RPC_USER_MAINNET", "bitcoin_mainnet")
BITCOIN_RPC_PASSWORD_MAINNET = os.getenv("BITCOIN_RPC_PASSWORD_MAINNET", "password_mainnet")
BITCOIN_RPC_URL_MAINNET = os.getenv("BITCOIN_RPC_URL_MAINNET", "http://bitcoin-node-ip:8332")
BITCOIN_DATADIR_MAINNET = os.getenv("BITCOIN_DATADIR_MAINNET", "/blockchain/bitcoin/data")

# Bitcoin RPC Configuration for Regtest
BITCOIN_RPC_USER_REGTEST = os.getenv("BITCOIN_RPC_USER_REGTEST", "bitcoin_regtest")
BITCOIN_RPC_PASSWORD_REGTEST = os.getenv("BITCOIN_RPC_PASSWORD_REGTEST", "password_regtest")
BITCOIN_RPC_URL_REGTEST = os.getenv("BITCOIN_RPC_URL_REGTEST", "http://regtest-node-ip:18443")
BITCOIN_DATADIR_REGTEST = os.getenv("BITCOIN_DATADIR_REGTEST", "/blockchain/regtest/data")

# Ordinal Server Configuration
ORD_SERVER_URL_MAINNET = os.getenv("ORD_SERVER_URL_MAINNET", "http://ord-server-ip:9001")
ORD_SERVER_URL_REGTEST = os.getenv("ORD_SERVER_URL_REGTEST", "http://regtest-server-ip:9001")

# Wallet Configuration
WALLET_NAME_MAINNET = os.getenv("WALLET_NAME_MAINNET", "master-wallet")
WALLET_NAME_REGTEST = os.getenv("WALLET_NAME_REGTEST", "regtest-wallet")
WALLET_ADDRESS_REGTEST = os.getenv("WALLET_ADDRESS_REGTEST", "bcrt1")

# Keywords indicating a transient ord/RPC failure worth retrying.
_TRANSIENT_ERROR_KEYWORDS = [
    "connection refused",
    "timed out",
    "temporarily unavailable",
    "service unavailable",
    "connection reset",
    "network unreachable",
    "could not connect",
    "broken pipe",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_transient_error(stderr: str) -> bool:
    """Return True if stderr suggests a transient infrastructure failure."""
    lower = stderr.lower()
    return any(kw in lower for kw in _TRANSIENT_ERROR_KEYWORDS)


def run_ord_command(command: list, max_retries: int = 3, retry_delay: float = 2.0):
    """Run an ord CLI command with exponential-backoff retry on transient errors.

    Returns the CompletedProcess on success; raises subprocess.CalledProcessError
    on final failure.
    """
    last_exc = None
    for attempt in range(max_retries):
        try:
            return subprocess.run(command, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            last_exc = e
            if attempt < max_retries - 1 and _is_transient_error(e.stderr):
                time.sleep(retry_delay * (2 ** attempt))
                continue
            break
    raise last_exc


def sanitize_error(stderr: str) -> str:
    """Strip sensitive values from stderr before sending it to the caller."""
    for secret in [
        BITCOIN_RPC_PASSWORD_MAINNET,
        BITCOIN_RPC_PASSWORD_REGTEST,
        os.getenv("WALLET_API_PASSWORD", ""),
    ]:
        if secret:
            stderr = stderr.replace(secret, "[REDACTED]")
    return stderr.strip()


def write_temp_yaml(content: str) -> str:
    """Write content to a uniquely named temp file and return its path.

    Using a UUID suffix avoids race conditions when concurrent requests
    share the same YAML_FILE_PATH directory.
    """
    base_dir = os.path.dirname(YAML_FILE_PATH) or "/tmp"
    tmp_path = os.path.join(base_dir, f"batch-{uuid.uuid4().hex}.yaml")
    with open(tmp_path, "w") as f:
        f.write(content)
    return tmp_path


def make_base_command(network: str = "mainnet") -> list:
    """Return the ord invocation prefix for the given network."""
    if network == "mainnet":
        return [
            "sudo", ORD_PATH,
            f"--bitcoin-rpc-username={BITCOIN_RPC_USER_MAINNET}",
            f"--bitcoin-rpc-password={BITCOIN_RPC_PASSWORD_MAINNET}",
            f"--bitcoin-rpc-url={BITCOIN_RPC_URL_MAINNET}",
        ]
    return [
        "sudo", ORD_PATH,
        f"--bitcoin-rpc-username={BITCOIN_RPC_USER_REGTEST}",
        f"--bitcoin-rpc-password={BITCOIN_RPC_PASSWORD_REGTEST}",
        f"--bitcoin-rpc-url={BITCOIN_RPC_URL_REGTEST}",
        "-r",
    ]


def make_wallet_args(network: str = "mainnet") -> list:
    """Return the ord wallet sub-command args for the given network."""
    if network == "mainnet":
        return [
            "wallet",
            f"--server-url={ORD_SERVER_URL_MAINNET}",
            f"--name={WALLET_NAME_MAINNET}",
        ]
    return [
        "wallet",
        f"--server-url={ORD_SERVER_URL_REGTEST}",
        f"--name={WALLET_NAME_REGTEST}",
    ]


def validate_fee_rate(fee_rate) -> bool:
    """Return True when fee_rate is a number in the acceptable range (1-10000)."""
    if not isinstance(fee_rate, (int, float)):
        return False
    return 1 <= float(fee_rate) <= 10000


def validate_live_auth(body: dict):
    """Check password for non-dry-run transactions.

    Returns (True, None) on success; (False, flask_response_tuple) on failure.
    """
    password = body.get("password")
    if not password:
        return False, (
            jsonify({"success": False, "error": "Password is required for non-dry-run transactions"}),
            401,
        )
    expected = os.getenv("WALLET_API_PASSWORD")
    if not expected:
        return False, (jsonify({"success": False, "error": "Live transactions are not configured"}), 503)
    if not hmac.compare_digest(password, expected):
        return False, (jsonify({"success": False, "error": "Invalid password"}), 401)
    return True, None


# ── Existing endpoints (improved) ────────────────────────────────────────────

@app.route("/mainnet/send-bacon-tokens", methods=["POST"])
def send_bacon_tokens():
    if not verify_webhook_signature(request):
        return jsonify({"success": False, "error": "Invalid or missing webhook signature"}), 401

    data = request.json or {}
    yaml_content = data.get("yaml_content")
    fee_rate = data.get("fee_rate")
    is_dry_run = data.get("dry_run", True)

    if not yaml_content:
        return jsonify({"success": False, "error": "YAML content missing"}), 400
    if not validate_fee_rate(fee_rate):
        return jsonify({"success": False, "error": "fee_rate must be a number between 1 and 10000"}), 400
    if not is_dry_run:
        ok, err = validate_live_auth(data)
        if not ok:
            return err

    try:
        tmp_path = write_temp_yaml(yaml_content)
    except OSError as e:
        return jsonify({"success": False, "error": f"Failed to write batch file: {e}"}), 500

    command = (
        make_base_command("mainnet")
        + make_wallet_args("mainnet")
        + ["split", f"--splits={tmp_path}", f"--fee-rate={fee_rate}"]
    )
    if is_dry_run:
        command.append("--dry-run")

    try:
        result = run_ord_command(command)
        return jsonify({"success": True, "txid": result.stdout.strip(), "dry_run": is_dry_run})
    except subprocess.CalledProcessError as e:
        return jsonify({"success": False, "error": sanitize_error(e.stderr), "dry_run": is_dry_run}), 500
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@app.route("/regtest/send-bacon-tokens", methods=["POST"])
def send_bacon_tokens_regtest():
    if not verify_webhook_signature(request):
        return jsonify({"success": False, "error": "Invalid or missing webhook signature"}), 401

    data = request.json or {}
    num_users = data.get("num_users")
    fee_rate = data.get("fee_rate")

    if not isinstance(num_users, int) or num_users <= 0:
        return jsonify({"success": False, "error": "num_users must be a positive integer"}), 400
    if not validate_fee_rate(fee_rate):
        return jsonify({"success": False, "error": "fee_rate must be a number between 1 and 10000"}), 400

    yaml_data = {
        "outputs": [
            {"address": WALLET_ADDRESS_REGTEST, "runes": {"BLT•BACON•TOKENS": 1}}
            for _ in range(num_users)
        ]
    }

    try:
        tmp_path = write_temp_yaml(yaml.dump(yaml_data, default_flow_style=False))
    except OSError as e:
        return jsonify({"success": False, "error": f"Failed to write batch file: {e}"}), 500

    command = (
        make_base_command("regtest")
        + make_wallet_args("regtest")
        + ["split", f"--splits={tmp_path}", f"--fee-rate={fee_rate}", "--dry-run"]
    )

    try:
        result = run_ord_command(command)
        return jsonify({"success": True, "txid": result.stdout.strip(), "dry_run": True})
    except subprocess.CalledProcessError as e:
        return jsonify({"success": False, "error": sanitize_error(e.stderr), "dry_run": True}), 500
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@app.route("/mainnet/wallet-balance", methods=["GET"])
def wallet_balance():
    if not verify_webhook_signature(request):
        return jsonify({"success": False, "error": "Invalid or missing webhook signature"}), 401

    command = (
        make_base_command("mainnet")
        + [f"--data-dir={BITCOIN_DATADIR_MAINNET}"]
        + make_wallet_args("mainnet")
        + ["balance"]
    )

    try:
        result = run_ord_command(command)
        return jsonify({"success": True, "balance": result.stdout.strip()})
    except subprocess.CalledProcessError as e:
        return jsonify({"success": False, "error": sanitize_error(e.stderr)}), 500


# ── Rune etching (creation) ───────────────────────────────────────────────────

def _etch_rune(network: str):
    """Shared handler for mainnet and regtest Rune etching."""
    if not verify_webhook_signature(request):
        return jsonify({"success": False, "error": "Invalid or missing webhook signature"}), 401

    data = request.json or {}
    rune_name = data.get("rune_name")
    symbol = data.get("symbol")
    divisibility = data.get("divisibility", 0)
    premine = data.get("premine")
    fee_rate = data.get("fee_rate")
    is_dry_run = data.get("dry_run", True)
    turbo = data.get("turbo", False)
    mint_cap = data.get("mint_cap")
    mint_amount = data.get("mint_amount")
    mint_height_start = data.get("mint_height_start")
    mint_height_end = data.get("mint_height_end")
    mint_offset_start = data.get("mint_offset_start")
    mint_offset_end = data.get("mint_offset_end")

    if not rune_name or not isinstance(rune_name, str):
        return jsonify({"success": False, "error": "rune_name is required"}), 400
    if not symbol or not isinstance(symbol, str) or len(symbol) != 1:
        return jsonify({"success": False, "error": "symbol must be exactly one character"}), 400
    if not isinstance(divisibility, int) or not (0 <= divisibility <= 38):
        return jsonify({"success": False, "error": "divisibility must be an integer between 0 and 38"}), 400
    if not validate_fee_rate(fee_rate):
        return jsonify({"success": False, "error": "fee_rate must be a number between 1 and 10000"}), 400

    has_open_mint = mint_cap is not None or mint_amount is not None
    if premine is None and not has_open_mint:
        return jsonify({
            "success": False,
            "error": "Supply must be defined via premine, open-mint terms (mint_cap/mint_amount), or both",
        }), 400

    if not is_dry_run:
        ok, err = validate_live_auth(data)
        if not ok:
            return err

    command = (
        make_base_command(network)
        + make_wallet_args(network)
        + [
            "etch",
            f"--rune={rune_name}",
            f"--symbol={symbol}",
            f"--divisibility={divisibility}",
            f"--fee-rate={fee_rate}",
        ]
    )

    if premine is not None:
        command.append(f"--premine={premine}")
    if mint_cap is not None:
        command.append(f"--terms-cap={mint_cap}")
    if mint_amount is not None:
        command.append(f"--terms-amount={mint_amount}")
    if mint_height_start is not None:
        command.append(f"--terms-height-start={mint_height_start}")
    if mint_height_end is not None:
        command.append(f"--terms-height-end={mint_height_end}")
    if mint_offset_start is not None:
        command.append(f"--terms-offset-start={mint_offset_start}")
    if mint_offset_end is not None:
        command.append(f"--terms-offset-end={mint_offset_end}")
    if turbo:
        command.append("--turbo")
    if is_dry_run:
        command.append("--dry-run")

    try:
        result = run_ord_command(command)
        return jsonify({
            "success": True,
            "output": result.stdout.strip(),
            "rune_name": rune_name,
            "dry_run": is_dry_run,
        })
    except subprocess.CalledProcessError as e:
        return jsonify({
            "success": False,
            "error": sanitize_error(e.stderr),
            "dry_run": is_dry_run,
        }), 500


@app.route("/mainnet/etch-rune", methods=["POST"])
def etch_rune_mainnet():
    return _etch_rune("mainnet")


@app.route("/regtest/etch-rune", methods=["POST"])
def etch_rune_regtest():
    return _etch_rune("regtest")


# ── Rune minting (open-mint claim) ───────────────────────────────────────────

def _mint_rune(network: str):
    """Shared handler for mainnet and regtest Rune minting."""
    if not verify_webhook_signature(request):
        return jsonify({"success": False, "error": "Invalid or missing webhook signature"}), 401

    data = request.json or {}
    rune_name = data.get("rune_name")
    fee_rate = data.get("fee_rate")
    is_dry_run = data.get("dry_run", True)
    postage = data.get("postage")
    destination = data.get("destination")

    if not rune_name or not isinstance(rune_name, str):
        return jsonify({"success": False, "error": "rune_name is required"}), 400
    if not validate_fee_rate(fee_rate):
        return jsonify({"success": False, "error": "fee_rate must be a number between 1 and 10000"}), 400

    if not is_dry_run:
        ok, err = validate_live_auth(data)
        if not ok:
            return err

    command = (
        make_base_command(network)
        + make_wallet_args(network)
        + ["mint", f"--rune={rune_name}", f"--fee-rate={fee_rate}"]
    )

    if postage:
        command.append(f"--postage={postage}")
    if destination:
        command.append(f"--destination={destination}")
    if is_dry_run:
        command.append("--dry-run")

    try:
        result = run_ord_command(command)
        return jsonify({
            "success": True,
            "output": result.stdout.strip(),
            "rune_name": rune_name,
            "dry_run": is_dry_run,
        })
    except subprocess.CalledProcessError as e:
        return jsonify({
            "success": False,
            "error": sanitize_error(e.stderr),
            "dry_run": is_dry_run,
        }), 500


@app.route("/mainnet/mint-rune", methods=["POST"])
def mint_rune_mainnet():
    return _mint_rune("mainnet")


@app.route("/regtest/mint-rune", methods=["POST"])
def mint_rune_regtest():
    return _mint_rune("regtest")


# ── Startup ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("FLASK_PORT", 9002)))
