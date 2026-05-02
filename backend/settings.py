import os
from dotenv import load_dotenv

load_dotenv()

# Google Vision + Speech
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GOOGLE_CREDENTIALS

# Gemini key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")