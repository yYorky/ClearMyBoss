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
   * Expose the runner through a `main.py` entry point so the backend can be started with a single command and listen for new documents shared to the service account email.
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

## **Sprint 4 – Groq Rate Limit Resilience** (1 week)

**Goal:** Prevent "429 Too Many Requests" errors by throttling requests and handling rate limits gracefully.

**Tasks:**

1. **Rate Limit Research**

   * Review Groq API documentation and headers to determine allowed request rates.
   * Define configurable limits (requests per minute / concurrent calls).
2. **Centralized Throttling**

   * Implement lightweight rate limiter or queue for Groq requests.
   * Ensure document chunks are processed sequentially when limits are reached.
3. **Enhanced Retry Logic**

   * Detect `429` responses in `get_suggestions`.
   * Respect `Retry-After` header and apply exponential backoff with jitter.
4. **Testing**

   * Unit test simulating repeated `429` responses to verify retry/backoff behavior.
   * Integration test confirming throttler limits parallel requests.

---

## **Sprint 5 – Reviewer Precision & Persona** (1 week)

**Goal:** Enable the AI reviewer to give targeted feedback with a clear boss-like persona.

**Tasks:**

1. **Section-Level Commenting**

   * Allow AI to anchor comments to specific document ranges.
   * Include quoted text so feedback highlights the exact section.
2. **Comment Thread Handling**

   * Track comment authors to ensure the reviewer only replies to user comments.
   * Prevent AI from responding to its own previous remarks.
3. **System Prompt & Persona**

   * Craft a system prompt that sets the tone of a boss reviewing work.
   * Integrate the prompt into the review pipeline for consistent behaviour.
4. **Testing & Validation**

   * Unit tests for comment filtering and section targeting.
   * Manual review to confirm persona and specific feedback.

---

✅ **End State after Sprint 5:**

* Reviewer highlights exact text segments in its comments.
* AI responds only to human-authored comments.
* System prompt ensures consistent "boss" persona in all feedback.
