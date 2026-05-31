# TELBench Data

TELBench artifacts are hosted on Hugging Face instead of being committed to the
GitHub repository. Download the encrypted release into this directory:

```bash
python -m pip install -U huggingface_hub

hf download NJU-LINK/TELBench \
  --repo-type dataset \
  --local-dir data \
  --include "TELBench.jsonl.enc" \
  --include "TELBench.jsonl.enc.sha256" \
  --include "TELBench.jsonl.sha256"
```

Downloaded files:

- `TELBench.jsonl.enc`: AES-256-CBC encrypted JSONL file.
- `TELBench.jsonl.enc.sha256`: checksum of the encrypted file.
- `TELBench.jsonl.sha256`: checksum of the decrypted JSONL file.

The decrypted file is intentionally ignored by git. To recover it, place the
data passphrase in `TELBENCH_PASSPHRASE` or in `data/.telbench_key`, then run:

```bash
bash scripts/decrypt_telbench.sh
```

The command writes `data/TELBench.jsonl` and verifies its SHA-256 checksum.

## JSONL Format

Each line is one trajectory-level instance:

```json
{
  "id": "0001",
  "source_id": "traj_...",
  "question": "...",
  "spans": [
    {
      "id": "s001",
      "raw": "original semantic span text"
    }
  ],
  "gold": {
    "error_span_ids": ["s008"]
  },
  "meta": {
    "bench": "gaia",
    "difficulty": "easy",
    "framework": "miroflow",
    "model": "gaia-val-gemini25pro",
    "answer_status": "correct"
  },
  "annotations": {}
}
```

DRIFT sanitizes inputs before prompting. Model calls receive only `question`,
`id`, and ordered raw span text. Gold labels, annotations, metadata, judge
results, span types, and manual notes are not passed to the model.
