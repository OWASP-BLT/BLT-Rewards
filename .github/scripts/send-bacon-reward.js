/**
 * send-bacon-reward.js
 *
 * Transfers BACON SPL tokens from the project treasury to the PR contributor
 * on Solana devnet (or any Solana cluster).
 *
 * Environment variables (set as GitHub Actions secrets / env):
 *   BACON_TREASURY_KEYPAIR  – treasury private key as JSON array [1,2,…] or base58 string
 *   BACON_TOKEN_MINT        – SPL mint address, e.g. "6Xn7…"
 *   CONTRIBUTOR_GITHUB      – GitHub username of the PR author
 *   REWARD_AMOUNT           – integer number of whole tokens to send
 *   SOLANA_NETWORK          – "devnet" | "testnet" | "mainnet-beta"  (default: devnet)
 *   PR_NUMBER               – PR number, used for logging only
 *
 * Outputs written to $GITHUB_OUTPUT:
 *   status   – "success" | "skipped" | "failed"
 *   txid     – Solana transaction signature (on success)
 *   reason   – human-readable message (on skip/failure)
 *   amount   – tokens sent
 *   recipient – recipient wallet address
 */

'use strict';

const fs   = require('fs');
const path = require('path');

const {
  Connection,
  Keypair,
  PublicKey,
  clusterApiUrl,
} = require('@solana/web3.js');

const {
  getOrCreateAssociatedTokenAccount,
  transfer,
  getMint,
} = require('@solana/spl-token');

const bs58 = require('bs58');

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Append a key=value pair to $GITHUB_OUTPUT (or log to stdout in local runs). */
function setOutput(key, value) {
  const outputFile = process.env.GITHUB_OUTPUT;
  if (outputFile) {
    fs.appendFileSync(outputFile, `${key}=${value}\n`);
  } else {
    console.log(`[OUTPUT] ${key}=${value}`);
  }
}

/** Parse the treasury keypair from either a JSON-array or base58 string. */
function parseKeypair(raw) {
  const trimmed = raw.trim();

  // JSON array: [1,2,3,...,64]
  if (trimmed.startsWith('[')) {
    const arr = JSON.parse(trimmed);
    return Keypair.fromSecretKey(Uint8Array.from(arr));
  }

  // Base58 string (Phantom / Solflare export format)
  const decoded = bs58.decode(trimmed);
  return Keypair.fromSecretKey(decoded);
}

/**
 * Look up the recipient wallet address for a given GitHub username.
 *
 * Priority:
 *   1. .github/contributors-wallets.json  (static map maintained in the repo)
 *   2. "SOLANA_WALLET: <address>" anywhere in the PR body
 *      (GITHUB_EVENT_PATH points at the full event JSON)
 *
 * Returns a PublicKey or null.
 */
function resolveRecipientWallet(contributorGithub) {
  // ── Method 1: contributors-wallets.json ──────────────────────────────────────
  const walletsFile = path.join(__dirname, '..', 'contributors-wallets.json');
  if (fs.existsSync(walletsFile)) {
    let wallets;
    try {
      wallets = JSON.parse(fs.readFileSync(walletsFile, 'utf8'));
    } catch (e) {
      console.warn(`Warning: could not parse contributors-wallets.json — ${e.message}`);
    }
    if (wallets && wallets[contributorGithub]) {
      console.log(`Found wallet for @${contributorGithub} in contributors-wallets.json`);
      return new PublicKey(wallets[contributorGithub]);
    }
  }

  // ── Method 2: PR body  ────────────────────────────────────────────────────────
  const eventPath = process.env.GITHUB_EVENT_PATH;
  if (eventPath && fs.existsSync(eventPath)) {
    try {
      const event  = JSON.parse(fs.readFileSync(eventPath, 'utf8'));
      const prBody = event.pull_request?.body || '';
      const match  = prBody.match(/SOLANA_WALLET[:\s]+([1-9A-HJ-NP-Za-km-z]{32,44})/);
      if (match) {
        const addr = new PublicKey(match[1]);   // throws if invalid
        console.log(`Found wallet for @${contributorGithub} in PR body`);
        return addr;
      }
    } catch (e) {
      console.warn(`Warning: could not extract wallet from PR body — ${e.message}`);
    }
  }

  return null;
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  const treasuryRaw      = process.env.BACON_TREASURY_KEYPAIR;
  const mintStr          = process.env.BACON_TOKEN_MINT;
  const contributorGH    = process.env.CONTRIBUTOR_GITHUB   || 'unknown';
  const rewardAmountRaw  = process.env.REWARD_AMOUNT         || '10';
  const network          = process.env.SOLANA_NETWORK        || 'devnet';
  const prNumber         = process.env.PR_NUMBER             || '?';

  // ── Validate required env vars ───────────────────────────────────────────────
  if (!treasuryRaw) {
    console.error('ERROR: BACON_TREASURY_KEYPAIR is not set.');
    setOutput('status', 'failed');
    setOutput('reason', 'BACON_TREASURY_KEYPAIR secret is not configured');
    process.exit(1);
  }
  if (!mintStr) {
    console.error('ERROR: BACON_TOKEN_MINT is not set.');
    setOutput('status', 'failed');
    setOutput('reason', 'BACON_TOKEN_MINT secret is not configured');
    process.exit(1);
  }

  // ── Parse treasury keypair ────────────────────────────────────────────────────
  let treasuryKeypair;
  try {
    treasuryKeypair = parseKeypair(treasuryRaw);
  } catch (e) {
    console.error('ERROR: Could not parse BACON_TREASURY_KEYPAIR:', e.message);
    setOutput('status', 'failed');
    setOutput('reason', 'Invalid BACON_TREASURY_KEYPAIR format');
    process.exit(1);
  }

  const tokenMint    = new PublicKey(mintStr);
  const rewardAmount = parseInt(rewardAmountRaw, 10);

  console.log(`\n── BACON Reward Pipeline ──────────────────────────────────`);
  console.log(`  PR:          #${prNumber}`);
  console.log(`  Contributor: @${contributorGH}`);
  console.log(`  Reward:      ${rewardAmount} BACON`);
  console.log(`  Network:     ${network}`);
  console.log(`  Treasury:    ${treasuryKeypair.publicKey.toString()}`);
  console.log(`  Mint:        ${tokenMint.toString()}`);
  console.log(`────────────────────────────────────────────────────────────\n`);

  // ── Resolve recipient wallet ──────────────────────────────────────────────────
  const recipientPubkey = resolveRecipientWallet(contributorGH);

  if (!recipientPubkey) {
    console.warn(`No Solana wallet registered for @${contributorGH}.`);
    setOutput('status', 'skipped');
    setOutput('reason',
      `No Solana wallet registered for @${contributorGH}. ` +
      'Add it to .github/contributors-wallets.json or include ' +
      '"SOLANA_WALLET: <address>" in a PR description.'
    );
    setOutput('txid',   '');
    setOutput('amount', rewardAmount.toString());
    process.exit(0);   // exit 0 — not an error, just a pending state
  }

  // ── Connect to Solana ─────────────────────────────────────────────────────────
  const rpcUrl     = clusterApiUrl(network);
  const connection = new Connection(rpcUrl, 'confirmed');
  console.log(`Connected to ${network}: ${rpcUrl}`);

  // ── Fetch mint info (decimals) ────────────────────────────────────────────────
  const mintInfo  = await getMint(connection, tokenMint);
  const rawAmount = BigInt(rewardAmount) * BigInt(10 ** mintInfo.decimals);
  console.log(`Token decimals: ${mintInfo.decimals}`);
  console.log(`Raw transfer amount: ${rawAmount}`);

  // ── Get / create treasury Associated Token Account ────────────────────────────
  console.log('Fetching treasury ATA…');
  const treasuryATA = await getOrCreateAssociatedTokenAccount(
    connection,
    treasuryKeypair,
    tokenMint,
    treasuryKeypair.publicKey
  );
  console.log(`Treasury ATA:     ${treasuryATA.address.toString()}`);
  console.log(`Treasury balance: ${treasuryATA.amount.toString()} (raw)`);

  if (BigInt(treasuryATA.amount) < rawAmount) {
    const msg =
      `Treasury has insufficient BACON tokens. ` +
      `Has ${treasuryATA.amount} raw, needs ${rawAmount} raw.`;
    console.error('ERROR:', msg);
    setOutput('status', 'failed');
    setOutput('reason', msg);
    setOutput('txid',   '');
    process.exit(1);
  }

  // ── Get / create recipient Associated Token Account ───────────────────────────
  console.log(`Fetching / creating recipient ATA for ${recipientPubkey.toString()}…`);
  const recipientATA = await getOrCreateAssociatedTokenAccount(
    connection,
    treasuryKeypair,    // treasury pays for ATA creation if it doesn't exist
    tokenMint,
    recipientPubkey
  );
  console.log(`Recipient ATA: ${recipientATA.address.toString()}`);

  // ── Execute transfer ──────────────────────────────────────────────────────────
  console.log(`\nTransferring ${rewardAmount} BACON → @${contributorGH} (${recipientPubkey.toString()})…`);

  const txid = await transfer(
    connection,
    treasuryKeypair,
    treasuryATA.address,
    recipientATA.address,
    treasuryKeypair.publicKey,
    rawAmount
  );

  const explorerUrl = `https://explorer.solana.com/tx/${txid}?cluster=${network}`;
  console.log(`\nTransaction confirmed!`);
  console.log(`TXID:     ${txid}`);
  console.log(`Explorer: ${explorerUrl}`);

  // ── Write outputs ─────────────────────────────────────────────────────────────
  setOutput('status',    'success');
  setOutput('txid',      txid);
  setOutput('amount',    rewardAmount.toString());
  setOutput('recipient', recipientPubkey.toString());
  setOutput('explorer',  explorerUrl);
}

main().catch((err) => {
  console.error('Fatal error:', err.message || err);
  setOutput('status', 'failed');
  setOutput('reason', String(err.message || err));
  setOutput('txid',   '');
  process.exit(1);
});
