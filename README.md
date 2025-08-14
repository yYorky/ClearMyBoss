# ClearMyBoss
A MVP that plugs into Google Docs and lets an AI automatically review the document and leave comments (like how your boss would do it).

## Groq API

`src/groq_client.py` contacts Groq's Chat Completions endpoint for grammar
feedback. Long documents are automatically split into 8KB chunks before
being sent to the API to avoid request-size errors. The suggestions from
each chunk are concatenated into a single response.
