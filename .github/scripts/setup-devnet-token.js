/**
 * setup-devnet-token.js
 *
 * One-time script to bootstrap the BACON SPL token on Solana devnet.
 * Run this locally ONCE to obtain the two secrets needed by the GitHub Action:
 *
 *   BACON_TREASURY_KEYPAIR  ← JSON-array or base58 secret key
 *   BACON_TOKEN_MINT        ← SPL token mint address
 *
 * Usage:
 *   cd .github/scripts
 *   npm install
 *   node setup-devnet-token.js
 *
 * ⚠ NEVER commit the generated bacon-treasury-keypair.json to the repo.
 *   Add it to GitHub via: Settings → Secrets → Actions → New secret.
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

import {
  Connection,
  Keypair,
  clusterApiUrl,
  LAMPORTS_PER_SOL,
} from '@solana/web3.js';

import {
  createMint,
  getOrCreateAssociatedTokenAccount,
  mintTo,
  setAuthority,
  AuthorityType,
} from '@solana/spl-token';

import bs58 from 'bs58';

// ES module __dirname shim
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Configuration
const NETWORK = process.env.SOLANA_NETWORK || 'devnet';
const DECIMALS = 6;
const INITIAL_SUPPLY = 1_000_000;            // 1 million whole tokens
const KEYPAIR_FILE = path.join(__dirname, 'bacon-treasury-keypair.json');

async function main() {
  const connection = new Connection(clusterApiUrl(NETWORK), 'confirmed');
  console.log(`\n── BACON Devnet Bootstrap ────────────────────────────────`);
  console.log(`  Network: ${NETWORK}`);
  console.log(`  RPC:     ${clusterApiUrl(NETWORK)}`);
  console.log(`──────────────────────────────────────────────────────────\n`);

  // ── Load or generate treasury keypair ────────────────────────────────────────
  let treasury;
  if (fs.existsSync(KEYPAIR_FILE)) {
    console.log(`Loading existing keypair from ${KEYPAIR_FILE}…`);
    treasury = Keypair.fromSecretKey(
      Uint8Array.from(JSON.parse(fs.readFileSync(KEYPAIR_FILE, 'utf8')))
    );
    console.log(`Treasury public key: ${treasury.publicKey.toString()}`);
  } else {
    console.log('Generating new treasury keypair…');
    treasury = Keypair.generate();
    // Save as JSON array (Solana CLI format — safe for GH Secrets too)
    // Use restrictive file mode (0o600)
    fs.writeFileSync(KEYPAIR_FILE, JSON.stringify(Array.from(treasury.secretKey)), { mode: 0o600 });
    console.log(`Treasury public key: ${treasury.publicKey.toString()}`);
    console.log(`Key saved to:        ${KEYPAIR_FILE}  ← keep this secret!\n`);
  }

  // ── Airdrop SOL for transaction fees ─────────────────────────────────────────
  const balance = await connection.getBalance(treasury.publicKey);
  console.log(`Current SOL balance: ${balance / LAMPORTS_PER_SOL} SOL`);

  if (balance < 0.5 * LAMPORTS_PER_SOL) {
    if (NETWORK === 'mainnet-beta') {
      console.warn('Low balance on mainnet-beta. Please fund the treasury wallet manually.');
    } else {
      console.log(`Requesting ${NETWORK} airdrop (2 SOL)…`);
      const sig = await connection.requestAirdrop(treasury.publicKey, 2 * LAMPORTS_PER_SOL);
      await connection.confirmTransaction(sig, 'confirmed');
      console.log(`Airdrop confirmed: ${sig}`);
    }
  } else {
    console.log('Sufficient SOL balance, skipping airdrop.');
  }

  // ── Create the SPL token mint ─────────────────────────────────────────────────
  console.log(`\nCreating BACON token mint (decimals=${DECIMALS})…`);
  const mint = await createMint(
    connection,
    treasury,               // payer
    treasury.publicKey,     // mint authority
    null,                   // freeze authority (set to null for fixed-supply tokens)
    DECIMALS
  );
  console.log(`Mint created: ${mint.toString()}`);

  // ── Create treasury ATA and mint initial supply ───────────────────────────────
  console.log(`\nCreating treasury Associated Token Account…`);
  const treasuryATA = await getOrCreateAssociatedTokenAccount(
    connection,
    treasury,
    mint,
    treasury.publicKey
  );
  console.log(`Treasury ATA: ${treasuryATA.address.toString()}`);

  const rawSupply = BigInt(INITIAL_SUPPLY) * (BigInt(10) ** BigInt(DECIMALS));
  console.log(`Minting ${INITIAL_SUPPLY.toLocaleString()} BACON tokens…`);
  const mintSig = await mintTo(
    connection,
    treasury,
    mint,
    treasuryATA.address,
    treasury.publicKey,
    rawSupply
  );
  console.log(`Mint tx: ${mintSig}`);

  // ── Revoke mint authority after initial supply is minted ─────────────────────
  console.log('Revoking mint authority…');
  await setAuthority(
    connection,
    treasury,
    mint,
    treasury.publicKey,
    AuthorityType.MintTokens,
    null
  );
  console.log('Mint authority revoked.');
  console.log(`Explorer: https://explorer.solana.com/tx/${mintSig}?cluster=${NETWORK}`);

  // ── Print GitHub Secrets values ───────────────────────────────────────────────
  console.log('\n══════════════════════════════════════════════════════════');
  console.log('Add the following two values as GitHub Actions Secrets:');
  console.log('Settings → Secrets and variables → Actions → New repository secret');
  console.log('══════════════════════════════════════════════════════════\n');

  console.log('Secret name:  BACON_TREASURY_KEYPAIR');
  console.log('Secret value: (contents of bacon-treasury-keypair.json)');
  console.log(`              ${JSON.stringify(Array.from(treasury.secretKey))}\n`);

  console.log('Secret name:  BACON_TOKEN_MINT');
  console.log(`Secret value: ${mint.toString()}`);

  console.log('\n══════════════════════════════════════════════════════════');
  console.log('⚠  Delete bacon-treasury-keypair.json after copying the secret!');
  console.log('   Run:  rm .github/scripts/bacon-treasury-keypair.json');
  console.log('══════════════════════════════════════════════════════════\n');
}

main().catch((err) => {
  console.error('Error:', err.message || err);
  process.exit(1);
});
