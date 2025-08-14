from dotenv import load_dotenv
import os

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
GROQ_CHUNK_SIZE = int(os.getenv("GROQ_CHUNK_SIZE", 20000))
GROQ_REQUESTS_PER_MINUTE = int(os.getenv("GROQ_REQUESTS_PER_MINUTE", 30))