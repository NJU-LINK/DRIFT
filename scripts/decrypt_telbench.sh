#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="$ROOT_DIR/data"
ENC_FILE="$DATA_DIR/TELBench.jsonl.enc"
OUT_FILE="$DATA_DIR/TELBench.jsonl"
KEY_FILE="$DATA_DIR/.telbench_key"

if [[ -z "${TELBENCH_PASSPHRASE:-}" ]]; then
  if [[ -f "$KEY_FILE" ]]; then
    TELBENCH_PASSPHRASE="$(<"$KEY_FILE")"
    export TELBENCH_PASSPHRASE
  else
    echo "Missing TELBENCH_PASSPHRASE. Set it or create data/.telbench_key." >&2
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

