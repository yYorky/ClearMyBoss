# Product Requirements Document (PRD)

- **Project Name:** ClearMyBoss
- **Version:** 0.1 MVP
- **Date:** 2025-08-12
- **Owner:** York Yong

---

## 1. Overview

The ClearMyBoss app acts as an automated collaborator in Google Docs. When users share a document with the agent’s email (service account), the AI will:

* Detect newly shared or updated docs.
* Review the content autonomously.
* Insert comments with actionable feedback directly in the doc.

Interaction happens entirely inside Google Docs via comments—no separate frontend is required.

---

## 2. Objectives

* Allow anyone to activate AI review by adding the agent’s email to their doc.
* Ensure reviews happen automatically without manual prompts.
* Maintain a seamless Google Docs workflow using comments.

---

## 3. Core Features (MVP)

### 3.1 Document Monitoring

* Poll the Google Drive API for any docs shared with the service account.
* Detect changes since the last review using revision history.

### 3.2 AI Review

* Fetch document content via the Google Docs API.
* Process text in manageable chunks (paragraph-level) to handle API token limits.
* For each chunk, the AI suggests:

  * Grammar/style corrections
  * Clarity improvements
  * Conciseness suggestions

### 3.3 Comment Posting

* Use Google Docs API `comments.create` to insert feedback.
* Highlight the exact range of text related to feedback.
* Tag comments with an AI author prefix (e.g., “AI Reviewer”) and a short hash for deduplication.

---

## 4. Non-Goals (MVP)

* Real-time AI as-you-type feedback.
* Complex user preference handling (tone, writing style).
* Inline edits — only comments.

---

## 5. Technical Requirements

### Backend

* **Language:** Python (Flask/Cron Worker) or Node.js
* **APIs:**

  * Google Drive API (detect shared docs)
  * Google Docs API (read/write, comment)
  * Google OAuth Service Account with domain-wide delegation
* **AI Service:** Groq API (e.g., `llama-3.1-70b-versatile`, `mixtral-8x7b`)
* **Storage:**

  * Minimal: Use Google Drive `appProperties` for storing `lastReviewedRevisionId` and recent comment hashes.
  * Optional: Local file or SQLite for deduplication tracking.

### Execution Model

* Local long-running process that:

  1. Finds docs shared with the service account.
  2. Checks for revisions since the last run.
  3. Reviews only changed ranges.
  4. Posts comments.
* Polling interval: e.g., every 3–5 minutes.

---

## 6. User Flow

1. User adds AI reviewer’s email (service account) to a Google Doc (Commenter or Editor access).
2. Backend detects the new document via the Drive API.
3. Document content is fetched and sent to Groq for review.
4. AI generates feedback and posts as comments anchored to the relevant ranges.
5. If the doc is updated later, the agent re-reviews only changed parts.

---

## 7. Success Criteria

* Document is reviewed within 5 minutes of being shared.
* At least 80% of AI comments are contextually relevant.
* No duplicate comments on unchanged text.

---

## 8. Future Enhancements

* User-set “review depth” (light, medium, deep).
* AI can resolve its own outdated comments if text changes.
* Multiple review passes (grammar first, then structure).
* Push notifications via Google Drive API instead of polling.

---

## 9. Implementation Notes

* Deduplication:

  * Store `lastReviewedRevisionId` in Drive `appProperties`.
  * Append short hash tags to comments (e.g., `[#AI d41d8c]`) for easy tracking.
* Anchoring Comments:

  * Use `startIndex`/`endIndex` from Docs structural elements to accurately attach comments to text ranges.
* Groq Prompt:

  * Return JSON array with `{issue, suggestion, severity, quote, start_para_idx, end_para_idx}`.
  * Map back to document indices before posting comments.

---

**End of Document**
