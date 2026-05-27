# Usage

This page documents how to prepare TELBench, configure API access, run DRIFT,
and evaluate predictions.

## Install

```bash
git clone https://github.com/NJU-LINK/DRIFT.git
cd DRIFT
python -m pip install -e .
```

## Prepare TELBench

The encrypted 1,000-instance TELBench JSONL is stored under `data/`:

```text
data/TELBench.jsonl.enc
```

Decrypt it with the release passphrase:

```bash
export TELBENCH_PASSPHRASE="..."
bash scripts/decrypt_telbench.sh
```

This creates:

```text
data/TELBench.jsonl
```

The script verifies the decrypted file against `data/TELBench.jsonl.sha256`.
The decrypted JSONL and local key file are ignored by git.

## Configure API

You can pass API settings on the command line:

```bash
drift \
  --setting drift \
  --input data/TELBench.jsonl \
  --model gpt-5.4 \
  --api-type responses \
  --base-url https://example.com/codex \
  --api-key "$API_KEY" \
  --outdir runs/telbench_gpt54 \
  --workers 8
```

Or put them in an env file:

```bash
cat > .env <<'EOF'
API_URL=https://example.com/codex
API_KEY=your_api_key_here
EOF
```

Then run:

```bash
drift \
  --setting drift \
  --input data/TELBench.jsonl \
  --model gpt-5.4 \
  --api-type responses \
  --env-file .env \
  --outdir runs/telbench_gpt54 \
  --workers 8
```

Supported API types:

- `chat`: OpenAI-compatible `/v1/chat/completions`.
- `responses`: OpenAI-compatible `/v1/responses`.

For Responses API models, `--reasoning-effort low` is the default because it is
stable and cost-effective for the JSON-only DRIFT prompts.

## Run Experiments

Run the bare full-context baseline:

```bash
drift \
  --setting bare \
  --input data/TELBench.jsonl \
  --model gpt-5.4 \
  --api-type responses \
  --env-file .env \
  --outdir runs/telbench_gpt54 \
  --workers 8
```

Run DRIFT:

```bash
drift \
  --setting drift \
  --input data/TELBench.jsonl \
  --model gpt-5.4 \
  --api-type responses \
  --env-file .env \
  --outdir runs/telbench_gpt54 \
  --workers 8
```

Outputs are written to:

```text
runs/telbench_gpt54/{setting}/{model}/
  summary.json
  {case_id}/run.json
```

`summary.json` contains all predictions and token usage. Each per-case
`run.json` stores pass-wise audit logs for inspection.

## Evaluate

```bash
drift-eval \
  --gold data/TELBench.jsonl \
  --pred runs/telbench_gpt54/drift/gpt-5.4/summary.json \
  --output runs/telbench_gpt54/drift/gpt-5.4/eval.json
```

The evaluator reports macro precision, macro recall, macro F1, micro metrics,
first-error accuracy, and missing or extra prediction ids.

## Prediction Schema

The public prediction schema is:

```json
{
  "traj_id": "0001",
  "error_span_ids": ["s003", "s011"],
  "earliest_harmful_span_id": "s003",
  "reasons": [
    {
      "span_id": "s003",
      "reason": "short reason"
    }
  ]
}
```

