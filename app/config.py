"""Configuration de l'application."""
import os
from dotenv import load_dotenv

load_dotenv()

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

# Redis (broker + backend + pub/sub)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0").strip()
BROKER_URL = REDIS_URL
RESULT_BACKEND = REDIS_URL

# Rate Limiting LLM
LLM_RPM = int(os.getenv("LLM_RPM", "500"))  # Requests per minute
LLM_TPM = int(os.getenv("LLM_TPM", "100000"))  # Tokens per minute
