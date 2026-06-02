#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="$ROOT_DIR/data"
ENC_FILE="$DATA_DIR/TELBench.jsonl.enc"
OUT_FILE="$DATA_DIR/TELBench.jsonl"
KEY_FILE="$DATA_DIR/.telbench_key"
PUBLIC_KEY_FILE="$DATA_DIR/TELBench.passphrase.txt"

if [[ ! -f "$ENC_FILE" ]]; then
  cat >&2 <<EOF
Missing $ENC_FILE.
Download TELBench first:
  hf download NJU-LINK/TELBench --repo-type dataset --local-dir data \\
    --include "TELBench.jsonl.enc" \\
    --include "TELBench.jsonl.enc.sha256" \\
    --include "TELBench.jsonl.sha256"
EOF
  exit 1
fi

if [[ -z "${TELBENCH_PASSPHRASE:-}" ]]; then
  if [[ -f "$KEY_FILE" ]]; then
    TELBENCH_PASSPHRASE="$(<"$KEY_FILE")"
    export TELBENCH_PASSPHRASE
  elif [[ -f "$PUBLIC_KEY_FILE" ]]; then
    TELBENCH_PASSPHRASE="$(<"$PUBLIC_KEY_FILE")"
    export TELBENCH_PASSPHRASE
  else
    echo "Missing TELBENCH_PASSPHRASE. Set it, create data/.telbench_key, or download data/TELBench.passphrase.txt from Hugging Face." >&2
    exit 1
  fi
fi

openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
  -in "$ENC_FILE" \
  -out "$OUT_FILE" \
  -pass env:TELBENCH_PASSPHRASE

if [[ -f "$DATA_DIR/TELBench.jsonl.sha256" ]]; then
  (
    cd "$DATA_DIR"
    shasum -a 256 -c TELBench.jsonl.sha256
  )
fi

echo "Decrypted TELBench to $OUT_FILE"
