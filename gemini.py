import itertools
import logging
from google import genai
from google.genai import types
from config import GEMINI_API_KEYS, SYSTEM_INSTRUCTION, DEFAULT_MODEL

logger = logging.getLogger("elena-ai")

if not GEMINI_API_KEYS:
    raise RuntimeError("No GEMINI_API_KEY or GEMINI_API_KEYS provided. Set them in your .env file.")

# Initialize a client for each configured Gemini API key
_clients = [
    genai.Client(
        api_key=key,
        http_options=types.HttpOptions(
            timeout=12000,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )
    for key in GEMINI_API_KEYS
]
_client_counter = itertools.cycle(range(len(_clients)))

FALLBACK_MODELS = [DEFAULT_MODEL, "gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3.5-flash"]


def get_clients_in_order():
    """Return clients starting from the current round-robin cursor across all keys."""
    start_idx = next(_client_counter)
    total = len(_clients)
    return [_clients[(start_idx + i) % total] for i in range(total)]


def _history_to_contents(history):
    contents = []
    for item in history:
        role = "model" if item["role"] == "model" else "user"
        contents.append(
            types.Content(role=role, parts=[types.Part.from_text(text=item["content"])])
        )
    return contents


async def _generate_content_with_retry(model: str, contents: list) -> str:
    candidates = [model]
    for fallback in FALLBACK_MODELS:
        if fallback not in candidates:
            candidates.append(fallback)

    last_exception = None
    for cand in candidates:
        clients = get_clients_in_order()
        for idx, client in enumerate(clients):
            try:
                response = await client.aio.models.generate_content(
                    model=cand,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                        temperature=0.7,
                        max_output_tokens=2048,
                    ),
                )
                return response.text or "I couldn't generate a response. Please try again."
            except Exception as e:
                logger.warning(
                    "Model '%s' failed on key #%d (%s...): %s. Trying next key/model...",
                    cand,
                    idx + 1,
                    client.api_key[:8] if hasattr(client, "api_key") and client.api_key else "key",
                    e,
                )
                last_exception = e

    if last_exception:
        raise last_exception
    return "I couldn't generate a response. Please try again."


async def ask_gemini(model: str, history: list, user_text: str) -> str:
    contents = _history_to_contents(history)
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user_text)]))
    return await _generate_content_with_retry(model, contents)


async def ask_gemini_with_media(
    model: str, history: list, prompt: str, media_bytes: bytes, mime_type: str
) -> str:
    contents = _history_to_contents(history)
    media_part = types.Part.from_bytes(data=media_bytes, mime_type=mime_type)
    contents.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt), media_part],
        )
    )
    return await _generate_content_with_retry(model, contents)
