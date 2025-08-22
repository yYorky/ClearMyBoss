# 📄 ClearMyBoss

### Work-in-progress

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![Groq](https://img.shields.io/badge/LLM-Groq-brightgreen?logo=groq)
![Google Docs](https://img.shields.io/badge/API-Google%20Docs-blue?logo=google)
![Google Drive](https://img.shields.io/badge/API-Google%20Drive-blue?logo=google-drive)
![License](https://img.shields.io/badge/license-MIT-lightgrey)
![Tests](https://img.shields.io/badge/tests-passing-brightgreen?logo=pytest)

People often wonder if AI will replace white-collar workers, but what if it could replace our bosses instead? In many Singapore offices a staff member sends draft documents up the chain for review. ClearMyBoss explores that idea by letting an AI read your Google Doc and leave short, boss-style comments so you can tidy up your work before it reaches a human manager.

### How it works

* Draft a report or proposal in Google Docs.
* Authorize the app with your Google account and edit as usual.
* Get quick, boss-style comments to tidy up your work early.

---

## 🎯 Objective

Provide an autonomous **"boss" reviewer** that acts like your manager: it reviews documents in your Google Drive and offers direct, helpful feedback without human involvement.

---

## ✨ Features

* 🚀 **Drive & Docs integration** – Polls Google Drive for modified or newly shared docs and retrieves paragraph text.
* 🔍 **Change tracking** – Detects changes by comparing the latest revision with the last reviewed version.
* 🤖 **LLM suggestions** – Sends edited text to Groq's Chat Completions API with chunking, retries, and rate limiting.
* 💬 **Automated comments** – Drive comments can't directly anchor to text, so the
  reviewer creates Docs *named ranges* and references them in each comment,
  optionally inserting a tiny "🔗" link target inside the document for easy
  navigation.
* 📝 **Context-aware feedback** – Treats a document's description as extra context for the reviewer.
* ♻️ **Revision-aware deduplication** – Stores the last reviewed revision and hashed suggestions in Drive `appProperties` to skip repeated comments.
* ⏱ **Scheduled runner** – Runs `main.py` periodically using the `schedule` library.

---

## 🏗 Architecture

1. **`src/main.py`** – Initializes authenticated services (Drive & Docs) and schedules the review cycle.
2. **`src/google_drive.py`** – Manages file listings, appProperties, revisions, comments, and threads.
3. **`src/google_docs.py`** – Extracts and chunks document paragraphs.
4. **`src/review.py`** – Orchestrates review: change detection → suggestion generation → deduplication → posting.
5. **`src/groq_client.py`** – Handles Groq API requests with retries, chunking, and rate limiting.

---

## 🔄 Workflow

```mermaid
flowchart TD
    A[Start `main.py`] --> B[Init Drive & Docs services]
    B --> C[Set `since` timestamp]
    C --> D{Every minute}
    D --> E[List docs changed since `since`]
    E --> F[Review & comment on each doc]
    F --> G[Update `since` to latest change]
    G --> D
```

```mermaid
sequenceDiagram
    participant U as User
    participant C as ClearMyBoss
    participant GDocs as Google Docs/Drive
    participant LLM as Groq API

    U->>GDocs: Share or edit doc
    C->>GDocs: Poll for updated docs
    C->>GDocs: Fetch paragraphs & metadata
    C->>LLM: Request suggestions
    LLM-->>C: Return feedback
    C->>GDocs: Post comments via Drive API
    GDocs-->>U: Comments appear in doc
```

---

## 🛠 Tech Stack

* ![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python) Python 3.11
* ![Groq](https://img.shields.io/badge/LLM-Groq-brightgreen?logo=groq) Groq Chat Completions API
* ![Google Docs](https://img.shields.io/badge/API-Google%20Docs-blue?logo=google) Google Docs & Drive APIs
* `requests`, `schedule`
* ![Pytest](https://img.shields.io/badge/tests-Pytest-brightgreen?logo=pytest) `pytest` for unit testing

---

## ⚙️ Configuration

Environment variables are loaded from `.env`:

| Variable                      | Description |
| ----------------------------- | ------------------------------------------------------------------------------------ |
| `GROQ_API_KEY`                | Groq API token |
| `GOOGLE_OAUTH_CLIENT_SECRET_JSON` | Path to OAuth client secret JSON downloaded from Google Cloud |
| `GOOGLE_OAUTH_TOKEN_JSON`     | Path to store the OAuth token retrieved after consent |
| `GROQ_CHUNK_SIZE`             | Max bytes per request to Groq (default `20000`) |
| `GROQ_REQUESTS_PER_MINUTE`    | Requests per minute before throttling (default `10`) |

On Windows, escape backslashes in paths or use forward slashes:

```env
GOOGLE_OAUTH_CLIENT_SECRET_JSON=C:\path\to\client_secret.json
GOOGLE_OAUTH_TOKEN_JSON=C:\path\to\token.json
# or
GOOGLE_OAUTH_CLIENT_SECRET_JSON=C:/path/to/client_secret.json
GOOGLE_OAUTH_TOKEN_JSON=C:/path/to/token.json
```
---

## ▶️ Running

Edit a Google Doc in your Drive and let the authorized app read it. Optional: add background context in the file's **Description** field so the reviewer understands the goal.

```bash
pip install -r requirements.txt
python -m src.main
```

* The service checks for new/edited documents every minute.
* `GROQ_REQUESTS_PER_MINUTE` must match your Groq plan limits.
* If exceeded, the client backs off using Groq's `Retry-After` hints.

---

## 🧪 Testing

```bash
pytest
```

---

## 📂 Repository Layout

* `src/` – application source code
* `config/` – environment settings
* `test/` – unit tests
* `PRD.md`, `SprintPlanning.md` – planning docs
