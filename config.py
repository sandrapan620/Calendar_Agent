import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
GOOGLE_TOKEN_PATH = os.getenv("GOOGLE_TOKEN_PATH", "token.json")

LLM_MODEL = "claude-sonnet-4-6"
GOOGLE_SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Calendars to include in the batch pipeline.
# Use the exact names shown in Google Calendar.
# "primary" always refers to your main calendar regardless of its display name.
INCLUDED_CALENDARS = {"primary", "clubs/activities", "#hellton"}
