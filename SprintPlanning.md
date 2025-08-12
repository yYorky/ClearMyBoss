## **Sprint 1 – Environment & API Foundations** (1–1.5 weeks)

**Goal:** Get the base system running with Google APIs and Groq, without yet posting comments.

**Tasks:**

1. **Project Setup**

   * Create Git repository & folder structure (`src/`, `tests/`, `config/`).
   * Set up virtual environment & `requirements.txt` (Flask, google-api-python-client, groq, etc.).
   * Configure `.env` for credentials (Groq API key, Google service account JSON path).
2. **Google API Setup**

   * Create Google Cloud Project.
   * Enable Google Drive API & Google Docs API.
   * Create service account & download credentials JSON.
   * Configure **domain-wide delegation** for service account (allowing it to access shared docs).
3. **Drive API – Document Detection**

   * Implement function to list Google Docs shared with service account.
   * Filter for files updated since last run (using `modifiedTime`).
   * Write test to simulate newly shared doc detection.
4. **Docs API – Content Retrieval**

   * Implement function to fetch doc text & structure via Docs API.
   * Handle paragraph-level chunking for token limits.
5. **Groq API Integration**

   * Create basic prompt template for grammar/style suggestions.
   * Send text chunk to Groq & log AI output (no comments yet).
   * Implement error handling & retry logic for Groq requests.

---

## **Sprint 2 – AI Review Processing & Deduplication** (1–1.5 weeks)

**Goal:** Process document revisions intelligently and prepare comment data for posting.

**Tasks:**

1. **Revision Tracking**

   * Implement `lastReviewedRevisionId` storage in `appProperties` of the doc.
   * Retrieve previous revision ID & detect only changed sections.
2. **Diff & Changed Range Detection**

   * Compare current revision text to last reviewed revision.
   * Identify changed paragraphs (track `start_para_idx` and `end_para_idx`).
3. **AI Review Pipeline**

   * Process only changed ranges through Groq API.
   * Format Groq output into structured review items (`issue`, `suggestion`, `severity`, `quote`).
4. **Deduplication**

   * Generate short hash of suggestion + quote.
   * Store recent hashes in doc `appProperties` or local store.
   * Skip adding comment if hash already exists.
5. **Unit Tests**

   * Test diff detection logic.
   * Test deduplication logic with simulated unchanged text.

---

## **Sprint 3 – Comment Posting & Full MVP Loop** (1–1.5 weeks)

**Goal:** Fully close the loop — detect docs, review changes, and post comments.

**Tasks:**

1. **Google Docs API – Comment Creation**

   * Implement `comments.create` with `content` from AI suggestion.
   * Anchor comment to correct text range using `startIndex`/`endIndex`.
   * Prefix comment with AI author tag (e.g., `AI Reviewer: <hash>`).
2. **Polling Mechanism**

   * Implement scheduled runner (Flask + cron job or Python `schedule`) to check every 3–5 minutes.
   * Ensure it runs locally as a persistent process.
3. **Performance & Error Handling**

   * Add retries for API failures.
   * Log errors & skipped docs.
   * Ensure no duplicate comments across runs.
4. **Integration Testing**

   * Simulate workflow: share a doc → agent detects → AI reviews → comments posted.
5. **MVP Demo Prep**

   * Create demo script & sample doc.
   * Record a short video showing end-to-end flow.

---

✅ **End State after Sprint 3:**

* User shares doc with AI reviewer email.
* AI reviews changes automatically within 5 minutes.
* Comments posted directly in Google Docs with context and deduplication.

---

If you want, I can **extend this into a 4th sprint** for **“Future Enhancements Foundation”** so that switching to push notifications instead of polling is easier later — this would align with section 8 of your PRD.

Do you want me to prepare that extra sprint plan?
