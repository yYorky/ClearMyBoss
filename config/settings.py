from dotenv import load_dotenv
import os

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GOOGLE_OAUTH_CLIENT_SECRET_JSON = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET_JSON")
GOOGLE_OAUTH_TOKEN_JSON = os.getenv("GOOGLE_OAUTH_TOKEN_JSON")
GROQ_CHUNK_SIZE = int(os.getenv("GROQ_CHUNK_SIZE", 20000))
# Default to Groq's published rate limit of 10 requests per minute
GROQ_REQUESTS_PER_MINUTE = int(os.getenv("GROQ_REQUESTS_PER_MINUTE", 10))

