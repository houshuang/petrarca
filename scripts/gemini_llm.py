"""Shared Gemini LLM wrapper using google.genai SDK.

Replaces litellm which truncates output from Gemini 2.5+ / 3.1 models.
Uses GEMINI_API_KEY or GEMINI_KEY env var for authentication.
"""

import os

from google import genai

# Model to use across the pipeline
DEFAULT_MODEL = os.environ.get("PETRARCA_LLM_MODEL", "gemini-3.1-flash-lite-preview")

# Ensure API key is set
_api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_KEY")
if _api_key:
    _client = genai.Client(api_key=_api_key)
else:
    _client = None


def call_llm(prompt: str, *, model: str | None = None, max_tokens: int = 4096,
             system_instruction: str | None = None) -> str | None:
    """Generate text with Gemini. Returns response text or None on error."""
    if not _client:
        print("ERROR: No GEMINI_API_KEY or GEMINI_KEY set", flush=True)
        return None

    use_model = model or DEFAULT_MODEL

    try:
        config = genai.types.GenerateContentConfig(
            max_output_tokens=max_tokens,
        )
        if system_instruction:
            config.system_instruction = system_instruction

        response = _client.models.generate_content(
            model=use_model,
            contents=prompt,
            config=config,
        )
        return response.text.strip() if response.text else None
    except Exception as e:
        print(f"Gemini error ({use_model}): {e}", flush=True)
        return None


def call_chat(messages: list[dict], *, model: str | None = None,
              max_tokens: int = 1500) -> str | None:
    """Multi-turn chat with Gemini. Messages: [{'role': 'user'|'model', 'content': '...'}].

    System messages should be passed as system_instruction in the first message
    or extracted before calling this function.
    """
    if not _client:
        print("ERROR: No GEMINI_API_KEY or GEMINI_KEY set", flush=True)
        return None

    use_model = model or DEFAULT_MODEL

    # Extract system instruction if first message has role 'system'
    system_instruction = None
    chat_messages = messages
    if messages and messages[0].get('role') == 'system':
        system_instruction = messages[0]['content']
        chat_messages = messages[1:]

    # Convert to Gemini format
    contents = []
    for msg in chat_messages:
        role = 'model' if msg['role'] == 'assistant' else 'user'
        contents.append(genai.types.Content(
            role=role,
            parts=[genai.types.Part(text=msg['content'])],
        ))

    try:
        config = genai.types.GenerateContentConfig(
            max_output_tokens=max_tokens,
        )
        if system_instruction:
            config.system_instruction = system_instruction

        response = _client.models.generate_content(
            model=use_model,
            contents=contents,
            config=config,
        )
        return response.text.strip() if response.text else None
    except Exception as e:
        print(f"Gemini chat error ({use_model}): {e}", flush=True)
        return None


def call_with_search(prompt: str, *, model: str | None = None,
                     max_tokens: int = 4096) -> str | None:
    """Generate text with Gemini + Google Search grounding enabled."""
    if not _client:
        print("ERROR: No GEMINI_API_KEY or GEMINI_KEY set", flush=True)
        return None

    use_model = model or DEFAULT_MODEL

    try:
        config = genai.types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            tools=[genai.types.Tool(google_search=genai.types.GoogleSearch())],
        )

        response = _client.models.generate_content(
            model=use_model,
            contents=prompt,
            config=config,
        )
        return response.text.strip() if response.text else None
    except Exception as e:
        print(f"Gemini search error ({use_model}): {e}", flush=True)
        return None
