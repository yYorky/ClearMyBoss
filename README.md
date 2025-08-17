# ClearMyBoss

ClearMyBoss automatically reviews Google Docs and leaves concise, boss-like comments powered by Groq's large language models.

## Objective

Provide an autonomous "boss" that reviews documents shared with a service account and offers direct, helpful feedback without human involvement.

## Features

- **Drive & Docs integration** – Polls Google Drive for documents that were modified or newly shared and retrieves their paragraph text.
- **Change tracking** – Compares the current revision against the last reviewed revision to isolate just the edited sections.
- **LLM suggestions** – Sends changed text to Groq's Chat Completions API, handling chunking, retries, and rate limiting.
- **Automated comments** – Posts feedback through the Apps Script Execution API, anchoring comments to character offsets and threading long replies.
- **Deduplication** – Stores hashes of previous suggestions in Drive `appProperties` to avoid repeating comments across runs.
- **Scheduled runner** – `main.py` uses the `schedule` library to run the review loop at regular intervals.

## Architecture

1. **`src/main.py`** builds authenticated services (Drive, Docs, Apps Script) and schedules the review cycle.
2. **`src/google_drive.py`** lists recent documents, manages file `appProperties`, downloads revisions, and handles comment threads.
3. **`src/google_docs.py`** fetches paragraphs and groups them into size‑bound chunks.
4. **`src/review.py`** orchestrates the review pipeline: detect changed ranges, generate suggestions, deduplicate, and post comments.
5. **`src/groq_client.py`** wraps Groq's API with request chunking, retries with backoff, and a sliding‑window rate limiter.
6. **`src/google_apps_script.py`** invokes an Apps Script function to create text‑anchored comments inside the document.

## Tech Stack

- Python 3.11
- Groq Chat Completions API
- Google Drive, Docs & Apps Script APIs
- `requests`, `schedule`
- `pytest` for unit tests

## Configuration

Environment variables are loaded from `.env`:

| Variable | Description |
| -------- | ----------- |
| `GROQ_API_KEY` | Groq API token |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Path to service account credentials |
| `GOOGLE_APPS_SCRIPT_ID` | ID of deployed Apps Script used for commenting<br>1. Open the Apps Script project.<br>2. Go to **Project Settings** → copy the **Script ID**.<br>3. Place it in `.env` as `GOOGLE_APPS_SCRIPT_ID=<copied_id>`. |
| `GROQ_CHUNK_SIZE` | Max bytes per request to Groq (default `20000`) |
| `GROQ_REQUESTS_PER_MINUTE` | Requests per minute before throttling (default `10`) |

## Running

```bash
pip install -r requirements.txt
python -m src.main
```

Set `GROQ_REQUESTS_PER_MINUTE` in your `.env` to match the limits of your Groq plan.
Exceeding this value results in `429 Too Many Requests`; the client will back off and
temporarily reduce its rate based on Groq's `Retry-After` hints.

The service checks for new documents every minute and posts comments automatically.

## Testing

```bash
pytest
```

## Repository Layout

- `src/` – application source code
- `config/` – environment‑based settings
- `test/` – unit tests
- `PRD.md`, `SprintPlanning.md` – project planning documents

