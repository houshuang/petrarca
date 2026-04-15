"""Claude LLM wrapper — delegates to `limbic.cerebellum.claude_cli` for
subprocess + cost logging. Preserves the legacy Petrarca API (call_claude,
call_claude_json, call_claude_search, call_claude_or_gemini) so existing
callers (review_engine.py, curriculum_db.py, etc.) don't need edits.

Returns None on failure, never raises. Gemini fallback stays in this module.

Usage:
    from claude_llm import call_claude, call_claude_json

    answer = call_claude("Explain the Battle of Himera")
    data = call_claude_json("Extract key facts...", timeout=300)
"""

from __future__ import annotations

import json
import re
import time

from limbic.cerebellum.claude_cli import (
    ClaudeCLIError,
    generate as _limbic_generate,
)

PROJECT = "petrarca"


def call_claude(prompt: str, *, timeout: int = 180, retries: int = 1,
                model: str | None = None) -> str | None:
    """Call Claude via `claude -p`. Returns text or None on failure.

    Uses Max plan OAuth. Logs cost/usage to the shared limbic cost_log on
    every call (success or failure).
    """
    last_err: Exception | None = None
    for attempt in range(1 + retries):
        try:
            result, _ = _limbic_generate(
                prompt=prompt,
                project=PROJECT,
                purpose="call_claude",
                model=model or "sonnet",
                timeout=timeout,
            )
            if isinstance(result, str) and result.strip():
                return result.strip()
        except ClaudeCLIError as e:
            last_err = e
            print(f'[claude] {e} (attempt {attempt+1})', flush=True)
        except FileNotFoundError:
            print('[claude] CLI not found — is claude installed?', flush=True)
            return None

        if attempt < retries:
            time.sleep(2)

    if last_err:
        print(f'[claude] giving up: {last_err}', flush=True)
    return None


def call_claude_json(prompt: str, *, timeout: int = 180, retries: int = 1,
                     model: str | None = None) -> dict | list | None:
    """Call Claude and parse JSON from the response. Falls back to Gemini on failure.

    Uses a text-mode call and a tolerant JSON extractor (not --json-schema),
    since the existing prompts rely on soft "Output JSON only" hints rather
    than strict schemas. The Gemini fallback stays in petrarca — limbic
    doesn't know about cross-provider fallback.
    """
    if 'json' not in prompt.lower()[-100:]:
        prompt = prompt.rstrip() + '\n\nOutput JSON only.'

    raw = call_claude(prompt, timeout=timeout, retries=retries, model=model)
    if raw:
        result = extract_json(raw)
        if result is not None:
            return result

    print('[call_claude_json] Claude failed, falling back to Gemini/OpenAI', flush=True)
    try:
        from gemini_llm import call_llm
        raw = call_llm(prompt, max_tokens=4096, response_mime_type='application/json')
        if raw:
            return extract_json(raw)
    except ImportError as e:
        print(f'[call_claude_json] gemini_llm import failed: {e}', flush=True)
    except Exception as e:
        print(f'[call_claude_json] Gemini/OpenAI fallback also failed: {e}', flush=True)

    return None


def extract_json(text: str) -> dict | list | None:
    """Extract JSON from text that may contain markdown fences or preamble."""
    cleaned = text.strip()

    if '```' in cleaned:
        match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?\s*```', cleaned)
        if match:
            cleaned = match.group(1).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    for pattern in [r'\[[\s\S]*\]', r'\{[\s\S]*\}']:
        match = re.search(pattern, cleaned)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                fixed = re.sub(r',\s*([}\]])', r'\1', match.group())
                try:
                    return json.loads(fixed)
                except json.JSONDecodeError:
                    continue

    print(f'[claude] could not extract JSON from response ({len(text)} chars)',
          flush=True)
    return None


def call_claude_search(prompt: str, *, timeout: int = 180,
                       model: str | None = None) -> str | None:
    """Call Claude with web search enabled. Replaces Gemini's call_with_search."""
    try:
        result, _ = _limbic_generate(
            prompt=prompt,
            project=PROJECT,
            purpose="call_claude_search",
            model=model or "sonnet",
            tools="WebSearch,WebFetch",
            timeout=timeout,
        )
        if isinstance(result, str) and result.strip():
            return result.strip()
    except ClaudeCLIError as e:
        print(f'[claude-search] {e}', flush=True)
    except FileNotFoundError:
        print('[claude-search] CLI not found', flush=True)
    return None


def call_claude_or_gemini(prompt: str, *, timeout: int = 180,
                          json_mode: bool = False,
                          model: str | None = None) -> str | dict | list | None:
    """Try Claude first, fall back to Gemini if Claude fails.

    For the transition period — gradually remove Gemini fallbacks as
    Claude proves reliable for each use case.
    """
    if json_mode:
        result = call_claude_json(prompt, timeout=timeout, model=model)
        if result is not None:
            return result
    else:
        result = call_claude(prompt, timeout=timeout, model=model)
        if result is not None:
            return result

    print('[claude] falling back to Gemini', flush=True)
    try:
        from gemini_llm import call_llm
        kwargs = {'max_tokens': 4096}
        if json_mode:
            kwargs['response_mime_type'] = 'application/json'
        raw = call_llm(prompt, **kwargs)
        if raw and json_mode:
            return extract_json(raw)
        return raw
    except Exception as e:
        print(f'[claude] Gemini fallback also failed: {e}', flush=True)
        return None
