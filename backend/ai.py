"""Google Gemini chat integration; secrets stay on the server."""
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import types


# Load configuration from the standalone project root, independent of the
# working directory used to start the server.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_MODEL = "gemini-3.5-flash-lite"
SYSTEM_PROMPT = """You are RoastBhai AI, a funny, warm, playful AI dost who speaks natural Hinglish or the language the user uses. Be witty and offer friendly, lighthearted roasts when invited, including roast battles and savage-style jokes that stay good-natured. Keep teasing focused on harmless habits or situations, never a person's identity, protected traits, body, or vulnerabilities. Do not use hateful, discriminatory, humiliating, or seriously harmful insults. Be genuinely useful for ordinary questions, explain things clearly, and switch to a respectful, supportive tone when the user needs help. Never pretend to have experiences or capabilities you do not have. Keep replies concise unless detail is useful. The user may be a minor, so keep content age-appropriate."""


class AIConfigurationError(Exception):
    pass


class AIServiceError(Exception):
    pass


async def generate_reply(messages: list[dict[str, str]]) -> str:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key in {"your_gemini_api_key_here", "your_api_key_here"}:
        raise AIConfigurationError(
            "AI is not configured yet. Add GEMINI_API_KEY to the project root .env file, then restart RoastBhai AI."
        )

    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    contents = [
        types.Content(
            role="model" if message["role"] == "assistant" else "user",
            parts=[types.Part.from_text(text=message["content"])],
        )
        for message in messages
    ]

    try:
        async with genai.Client(api_key=api_key).aio as client:
            response = await client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.8,
                ),
            )
        reply = response.text
        if not isinstance(reply, str) or not reply.strip():
            raise AIServiceError("Gemini returned an empty response. Please try again.")
        return reply.strip()
    except AIServiceError:
        raise
    except (TimeoutError, httpx.TimeoutException):
        raise AIServiceError("Gemini took too long to respond. Please try again.") from None
    except httpx.ConnectError:
        raise AIServiceError(
            "Could not connect to Gemini. Check the internet connection, proxy, or firewall settings."
        ) from None
    except Exception as exc:
        status_code = getattr(exc, "code", None)
        if status_code in (401, 403):
            raise AIConfigurationError(
                "Gemini rejected the API key or project access. Check GEMINI_API_KEY in the root .env file."
            ) from None
        if status_code == 404:
            raise AIConfigurationError(
                "The configured Gemini model is unavailable to this API key. Check GEMINI_MODEL and model access in AI Studio."
            ) from None
        if status_code == 429:
            raise AIServiceError(
                "Gemini quota or rate limit reached for this model. Check AI Studio quota and try again later."
            ) from None
        raise AIServiceError(
            "Gemini API request failed. Check the connection, GEMINI_MODEL, and provider settings."
        ) from None
