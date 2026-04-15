"""LLM wrapper: Gemini (google.genai) when GEMINI_KEY is set, else OpenAI when OPENAI_API_KEY is set.

Pipeline code imports this module as `gemini_llm`; both backends implement the same entrypoints.
"""

from __future__ import annotations

import base64
import os
from typing import Any

from google import genai

# Model defaults
DEFAULT_MODEL = os.environ.get("PETRARCA_LLM_MODEL", "gemini-3.1-flash-lite-preview")
OPENAI_MODEL = os.environ.get("PETRARCA_OPENAI_MODEL", "gpt-4o-mini")
OPENAI_VISION_MODEL = os.environ.get("PETRARCA_OPENAI_VISION_MODEL", "gpt-4o-mini")

_gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_KEY")
_openai_key = os.environ.get("OPENAI_API_KEY")

# Force backend: "gemini" | "openai" | unset (auto: gemini if key, else openai)
_llm_backend_env = (os.environ.get("PETRARCA_LLM_BACKEND") or "").strip().lower()

if _gemini_key:
    _client = genai.Client(api_key=_gemini_key)
else:
    _client = None

_oa_client: Any = None


def _backend() -> str:
    if _llm_backend_env == "openai":
        return "openai" if _openai_key else "none"
    if _llm_backend_env == "gemini":
        return "gemini" if _gemini_key else "none"
    if _gemini_key:
        return "gemini"
    if _openai_key:
        return "openai"
    return "none"


def _openai():
    global _oa_client
    if _oa_client is None and _openai_key:
        from openai import OpenAI

        _oa_client = OpenAI(api_key=_openai_key)
    return _oa_client


# Cost logging (optional — available when limbic is on PYTHONPATH)
try:
    from limbic.cerebellum.cost_log import cost_log as _cost_log
except ImportError:
    _cost_log = None


def _log_gemini_usage(response, model: str) -> None:
    if not _cost_log:
        return
    try:
        um = response.usage_metadata
        if not um:
            return
        _cost_log.log(
            project="petrarca",
            model=f"gemini/{model}",
            prompt_tokens=um.prompt_token_count or 0,
            completion_tokens=um.candidates_token_count or 0,
            cached_tokens=um.cached_content_token_count or 0,
            api_key_hint=_gemini_key[-4:] if _gemini_key else "",
        )
    except Exception:
        pass


def _log_openai_usage(model: str, usage) -> None:
    if not _cost_log or not usage:
        return
    try:
        _cost_log.log(
            project="petrarca",
            model=f"openai/{model}",
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            cached_tokens=0,
            api_key_hint=_openai_key[-4:] if _openai_key else "",
        )
    except Exception:
        pass


def _openai_chat(
    messages: list[dict],
    *,
    model: str,
    max_tokens: int,
    response_format: dict | None = None,
) -> str | None:
    client = _openai()
    if not client:
        print("ERROR: No OPENAI_API_KEY set", flush=True)
        return None
    kwargs: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if response_format:
        kwargs["response_format"] = response_format
    try:
        r = client.chat.completions.create(**kwargs)
    except TypeError:
        kwargs.pop("max_tokens", None)
        kwargs["max_completion_tokens"] = max_tokens
        try:
            r = client.chat.completions.create(**kwargs)
        except Exception as e:
            print(f"OpenAI error ({model}): {e}", flush=True)
            return None
    except Exception as e:
        print(f"OpenAI error ({model}): {e}", flush=True)
        return None
    if r.usage:
        _log_openai_usage(model, r.usage)
    text = (r.choices[0].message.content or "").strip()
    return text or None


def call_llm(prompt: str, *, model: str | None = None, max_tokens: int = 4096,
             system_instruction: str | None = None,
             response_mime_type: str | None = None) -> str | None:
    """Generate text. Gemini or OpenAI depending on keys / PETRARCA_LLM_BACKEND."""
    b = _backend()
    if b == "openai":
        messages: list[dict] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        if response_mime_type == "application/json":
            messages.append({
                "role": "user",
                "content": prompt + "\n\nReply with a single valid JSON object only, no markdown fences.",
            })
            fmt = {"type": "json_object"}
        else:
            messages.append({"role": "user", "content": prompt})
            fmt = None
        return _openai_chat(
            messages,
            model=model or OPENAI_MODEL,
            max_tokens=max_tokens,
            response_format=fmt,
        )

    if b != "gemini" or not _client:
        print("ERROR: Set GEMINI_KEY / GEMINI_API_KEY or OPENAI_API_KEY", flush=True)
        return None

    use_model = model or DEFAULT_MODEL
    try:
        config = genai.types.GenerateContentConfig(max_output_tokens=max_tokens)
        if system_instruction:
            config.system_instruction = system_instruction
        if response_mime_type:
            config.response_mime_type = response_mime_type
        response = _client.models.generate_content(
            model=use_model,
            contents=prompt,
            config=config,
        )
        _log_gemini_usage(response, use_model)
        return response.text.strip() if response.text else None
    except Exception as e:
        print(f"Gemini error ({use_model}): {e}", flush=True)
        return None


def call_chat(messages: list[dict], *, model: str | None = None,
              max_tokens: int = 1500) -> str | None:
    """Multi-turn chat. Gemini or OpenAI."""
    b = _backend()
    if b == "openai":
        oa_msgs = []
        for msg in messages:
            role = msg.get("role", "user")
            if role == "model":
                role = "assistant"
            if role == "system":
                oa_msgs.append({"role": "system", "content": msg["content"]})
            elif role in ("user", "assistant"):
                oa_msgs.append({"role": role, "content": msg["content"]})
        return _openai_chat(oa_msgs, model=model or OPENAI_MODEL, max_tokens=max_tokens)

    if b != "gemini" or not _client:
        print("ERROR: Set GEMINI_KEY / GEMINI_API_KEY or OPENAI_API_KEY", flush=True)
        return None

    use_model = model or DEFAULT_MODEL
    system_instruction = None
    chat_messages = messages
    if messages and messages[0].get("role") == "system":
        system_instruction = messages[0]["content"]
        chat_messages = messages[1:]

    contents = []
    for msg in chat_messages:
        role = "model" if msg["role"] == "assistant" else "user"
        contents.append(genai.types.Content(
            role=role,
            parts=[genai.types.Part(text=msg["content"])],
        ))

    try:
        config = genai.types.GenerateContentConfig(max_output_tokens=max_tokens)
        if system_instruction:
            config.system_instruction = system_instruction
        response = _client.models.generate_content(
            model=use_model,
            contents=contents,
            config=config,
        )
        _log_gemini_usage(response, use_model)
        return response.text.strip() if response.text else None
    except Exception as e:
        print(f"Gemini chat error ({use_model}): {e}", flush=True)
        return None


def call_llm_tool(prompt: str, tool_declaration: Any,
                  *, model: str | None = None, max_tokens: int = 8192,
                  system_instruction: str | None = None) -> dict | None:
    """Structured tool call (Gemini native). OpenAI: return None so callers fall back to call_llm JSON."""
    if _backend() == "openai":
        return None

    if not _client:
        print("ERROR: No GEMINI_API_KEY or GEMINI_KEY set", flush=True)
        return None

    use_model = model or DEFAULT_MODEL
    try:
        config = genai.types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            tools=[genai.types.Tool(function_declarations=[tool_declaration])],
            tool_config=genai.types.ToolConfig(
                function_calling_config=genai.types.FunctionCallingConfig(mode="ANY"),
            ),
        )
        if system_instruction:
            config.system_instruction = system_instruction

        response = _client.models.generate_content(
            model=use_model,
            contents=prompt,
            config=config,
        )
        _log_gemini_usage(response, use_model)

        if not response.candidates or not response.candidates[0].content.parts:
            print(f"Gemini tool error ({use_model}): empty response", flush=True)
            return None

        for part in response.candidates[0].content.parts:
            if part.function_call:
                return dict(part.function_call.args)

        print(f"Gemini tool error ({use_model}): no function call in response", flush=True)
        return None
    except Exception as e:
        print(f"Gemini tool error ({use_model}): {e}", flush=True)
        return None


def call_vision(image_data: bytes, prompt: str, *, model: str | None = None,
                max_tokens: int = 4096, mime_type: str = "image/jpeg",
                response_mime_type: str | None = None) -> str | None:
    """Vision: Gemini or OpenAI."""
    b = _backend()
    if b == "openai":
        b64 = base64.standard_b64encode(image_data).decode("ascii")
        data_url = f"data:{mime_type};base64,{b64}"
        use_model = model or OPENAI_VISION_MODEL
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ]
        fmt = {"type": "json_object"} if response_mime_type == "application/json" else None
        return _openai_chat(messages, model=use_model, max_tokens=max_tokens, response_format=fmt)

    if b != "gemini" or not _client:
        print("ERROR: Set GEMINI_KEY / GEMINI_API_KEY or OPENAI_API_KEY", flush=True)
        return None

    use_model = model or "gemini-2.5-flash"
    try:
        config = genai.types.GenerateContentConfig(max_output_tokens=max_tokens)
        if response_mime_type:
            config.response_mime_type = response_mime_type

        contents = [
            genai.types.Content(
                role="user",
                parts=[
                    genai.types.Part(text=prompt),
                    genai.types.Part(
                        inline_data=genai.types.Blob(
                            mime_type=mime_type,
                            data=image_data,
                        )
                    ),
                ],
            )
        ]

        response = _client.models.generate_content(
            model=use_model,
            contents=contents,
            config=config,
        )
        _log_gemini_usage(response, use_model)
        return response.text.strip() if response.text else None
    except Exception as e:
        print(f"Gemini vision error ({use_model}): {e}", flush=True)
        return None


def call_with_search(prompt: str, *, model: str | None = None,
                     max_tokens: int = 4096) -> str | None:
    """Gemini + Google Search, or OpenAI plain completion (no live web search)."""
    b = _backend()
    if b == "openai":
        sys = (
            "You do not have live web search. Answer from general knowledge; "
            "say when facts may be outdated or uncertain."
        )
        return call_llm(
            prompt,
            model=model or OPENAI_MODEL,
            max_tokens=max_tokens,
            system_instruction=sys,
        )

    if b != "gemini" or not _client:
        print("ERROR: Set GEMINI_KEY / GEMINI_API_KEY or OPENAI_API_KEY", flush=True)
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
        _log_gemini_usage(response, use_model)
        return response.text.strip() if response.text else None
    except Exception as e:
        print(f"Gemini search error ({use_model}): {e}", flush=True)
        return None
