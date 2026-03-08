"""Test runners for each pipeline layer."""

import json
import os
import sys
import time
from pathlib import Path

from . import FIXTURES_DIR, SCRIPTS_DIR
from .session import create_session, save_session

# Bridge GEMINI_KEY → GEMINI_API_KEY for litellm
if os.environ.get("GEMINI_KEY") and not os.environ.get("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = os.environ["GEMINI_KEY"]

# Also bridge ANTHROPIC_KEY → ANTHROPIC_API_KEY
if os.environ.get("ANTHROPIC_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
    os.environ["ANTHROPIC_API_KEY"] = os.environ["ANTHROPIC_KEY"]


def check_api_keys(model: str | None = None):
    """Validate that required API keys are set for the given model. Raises RuntimeError if not."""
    model = model or os.environ.get("PETRARCA_LLM_MODEL", "gemini/gemini-2.0-flash")
    if model.startswith("gemini/"):
        if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("GEMINI_KEY"):
            raise RuntimeError(
                f"Model {model} requires GEMINI_KEY or GEMINI_API_KEY. "
                "Set it in your environment or .env file."
            )
    elif model.startswith("anthropic/") or "claude" in model:
        if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_KEY"):
            raise RuntimeError(
                f"Model {model} requires ANTHROPIC_KEY or ANTHROPIC_API_KEY."
            )


def call_llm_instrumented(prompt: str, model: str | None = None,
                          timeout: int = 120) -> dict:
    """Call LLM via litellm with timing and token usage capture.

    Returns dict with: response, model, duration_ms, token_usage, prompt.
    """
    from litellm import completion

    model = model or os.environ.get("PETRARCA_LLM_MODEL", "gemini/gemini-2.0-flash")
    start = time.time()

    try:
        resp = completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=8192,
            timeout=timeout,
        )
        duration_ms = int((time.time() - start) * 1000)
        content = resp.choices[0].message.content.strip()
        usage = resp.usage
        return {
            "response": content,
            "model": model,
            "duration_ms": duration_ms,
            "token_usage": {
                "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                "completion_tokens": getattr(usage, "completion_tokens", 0),
                "total_tokens": getattr(usage, "total_tokens", 0),
            },
            "prompt": prompt,
        }
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        return {
            "response": None,
            "model": model,
            "duration_ms": duration_ms,
            "error": str(e),
            "prompt": prompt,
        }


def load_fixture(layer: str, fixture_name: str) -> dict:
    """Load a fixture by layer and name. Returns dict with input content and metadata."""
    fixture_dir = FIXTURES_DIR / layer / fixture_name
    if not fixture_dir.exists():
        available = list_fixtures(layer)
        hint = f" Available: {', '.join(available)}" if available else ""
        raise FileNotFoundError(f"Fixture '{fixture_name}' not found for layer '{layer}'.{hint}")

    result = {"name": fixture_name, "dir": str(fixture_dir)}

    # Load metadata
    meta_path = fixture_dir / "metadata.json"
    if meta_path.exists():
        result["metadata"] = json.loads(meta_path.read_text())
    else:
        result["metadata"] = {}

    # Load input (HTML or markdown)
    for ext in ["input.html", "input.md", "input.txt"]:
        input_path = fixture_dir / ext
        if input_path.exists():
            result["input_text"] = input_path.read_text()
            result["input_type"] = ext.split(".")[-1]
            break

    # Load article objects (for entity_concepts layer)
    articles_path = fixture_dir / "articles.json"
    if articles_path.exists():
        result["articles"] = json.loads(articles_path.read_text())

    # For e2e fixtures, a URL in metadata is sufficient (no input file needed)
    has_url = result.get("metadata", {}).get("url")
    if "input_text" not in result and "articles" not in result and not has_url:
        raise FileNotFoundError(f"No input file (input.html/md/txt or articles.json) in {fixture_dir}")

    return result


def list_fixtures(layer: str) -> list[str]:
    """List available fixture names for a layer."""
    layer_dir = FIXTURES_DIR / layer
    if not layer_dir.exists():
        return []
    return sorted(d.name for d in layer_dir.iterdir() if d.is_dir())


# ---------- Layer 1: clean_markdown ----------

def run_clean_markdown(fixture_name: str) -> dict:
    """Run clean_markdown on a fixture. Returns session metadata."""
    from build_articles import clean_markdown

    fixture = load_fixture("clean_markdown", fixture_name)
    input_text = fixture["input_text"]
    input_type = fixture["input_type"]

    session = create_session("clean_markdown", fixture_name)
    start = time.time()

    # If HTML, extract with trafilatura first
    reference_text = None
    if input_type == "html":
        import trafilatura
        extracted = trafilatura.extract(input_text, output_format="txt",
                                        include_links=True, include_formatting=True)
        if not extracted:
            extracted = input_text
        reference_text = extracted  # use this for fair word count comparison
        cleaned = clean_markdown(extracted)
        output = {"extracted_text": extracted, "cleaned_text": cleaned}
    else:
        cleaned = clean_markdown(input_text)
        output = {"cleaned_text": cleaned}

    session["duration_ms"] = int((time.time() - start) * 1000)
    session["status"] = "completed"

    # Auto-evaluate (pass reference_text for HTML to get fair content preservation check)
    from .evaluator import evaluate_clean_markdown
    evaluation = evaluate_clean_markdown(
        input_text, cleaned, fixture.get("metadata"),
        reference_text=reference_text,
    )

    save_session(session, output, evaluation)
    return {**session, "evaluation": evaluation}


# ---------- Layer 2: article_extraction ----------

def run_article_extraction(fixture_name: str, model: str | None = None) -> dict:
    """Run article extraction (LLM) on a fixture. Returns session metadata."""
    from build_articles import _build_article_prompt
    from extract_entity_concepts import parse_json_response

    check_api_keys(model)

    fixture = load_fixture("article_extraction", fixture_name)
    input_text = fixture["input_text"]
    title = fixture["metadata"].get("title", fixture_name)

    session = create_session("article_extraction", fixture_name, model=model)
    start = time.time()

    prompt = _build_article_prompt(input_text, title)
    llm_result = call_llm_instrumented(prompt, model=model)

    session["duration_ms"] = int((time.time() - start) * 1000)
    session["token_usage"] = llm_result.get("token_usage")
    session["model"] = llm_result["model"]

    if llm_result.get("response"):
        parsed = parse_json_response(llm_result["response"])
        if parsed and isinstance(parsed, dict):
            session["status"] = "completed"

            # Run deterministic structure checks automatically
            from .evaluator import evaluate_extraction_structure
            struct_eval = evaluate_extraction_structure(parsed)

            save_session(session, parsed, evaluation=struct_eval, llm_response={
                "prompt": llm_result["prompt"],
                "response": llm_result["response"],
            })
            return {**session, "output": parsed, "evaluation": struct_eval}
        else:
            session["status"] = "parse_error"
            save_session(session, {"raw_response": llm_result["response"]}, llm_response={
                "prompt": llm_result["prompt"],
                "response": llm_result["response"],
            })
            return {**session, "error": "Failed to parse LLM response"}
    else:
        session["status"] = "llm_error"
        save_session(session, {"error": llm_result.get("error", "Unknown error")})
        return {**session, "error": llm_result.get("error")}


# ---------- Layer 3: entity_concepts ----------

def run_entity_concepts(fixture_name: str, model: str | None = None) -> dict:
    """Run entity concept extraction on a fixture. Returns session metadata."""
    from extract_entity_concepts import (
        build_extraction_prompt, parse_json_response, deduplicate_concepts,
    )

    check_api_keys(model)

    fixture = load_fixture("entity_concepts", fixture_name)
    articles = fixture["articles"]

    session = create_session("entity_concepts", fixture_name, model=model)
    start = time.time()

    prompt = build_extraction_prompt(articles)
    llm_result = call_llm_instrumented(prompt, model=model)

    session["duration_ms"] = int((time.time() - start) * 1000)
    session["token_usage"] = llm_result.get("token_usage")
    session["model"] = llm_result["model"]

    if llm_result.get("response"):
        parsed = parse_json_response(llm_result["response"])
        if parsed and isinstance(parsed, list):
            deduped = deduplicate_concepts(parsed)
            session["status"] = "completed"
            output = {"raw_concepts": parsed, "deduped_concepts": deduped}
            save_session(session, output, llm_response={
                "prompt": llm_result["prompt"],
                "response": llm_result["response"],
            })
            return {**session, "output": output}
        else:
            session["status"] = "parse_error"
            save_session(session, {"raw_response": llm_result["response"]})
            return {**session, "error": "Failed to parse concepts from LLM response"}
    else:
        session["status"] = "llm_error"
        save_session(session, {"error": llm_result.get("error", "Unknown error")})
        return {**session, "error": llm_result.get("error")}


# ---------- Layer: atomic_claims ----------

def run_atomic_claims(fixture_name: str, model: str | None = None) -> dict:
    """Run atomic claim extraction on a fixture. Returns session metadata."""
    from build_articles import _build_atomic_decomposition_prompt
    from extract_entity_concepts import parse_json_response

    check_api_keys(model)

    fixture = load_fixture("atomic_claims", fixture_name)
    input_text = fixture["input_text"]
    title = fixture["metadata"].get("title", fixture_name)
    topics = fixture["metadata"].get("topics", [])

    session = create_session("atomic_claims", fixture_name, model=model)
    start = time.time()

    prompt = _build_atomic_decomposition_prompt(input_text, title, topics)
    llm_result = call_llm_instrumented(prompt, model=model)

    session["duration_ms"] = int((time.time() - start) * 1000)
    session["token_usage"] = llm_result.get("token_usage")
    session["model"] = llm_result["model"]

    if llm_result.get("response"):
        # Parse: strip markdown code fences if present
        raw = llm_result["response"]
        cleaned = raw
        if cleaned.startswith("```"):
            import re as _re
            cleaned = _re.sub(r"^```(?:json)?\n?", "", cleaned)
            cleaned = _re.sub(r"\n?```$", "", cleaned)

        parsed = parse_json_response(cleaned)
        if parsed and isinstance(parsed, list):
            from build_articles import _fix_pronoun_starts, _claim_id
            claims = []
            for raw_claim in parsed:
                normalized = raw_claim.get("normalized_text", "").strip()
                if not normalized:
                    continue
                claims.append({
                    "normalized_text": normalized,
                    "original_text": raw_claim.get("original_text", "").strip(),
                    "claim_type": raw_claim.get("claim_type", "factual"),
                    "source_paragraphs": raw_claim.get("source_paragraphs", []),
                    "topics": raw_claim.get("topics", []),
                })
            claims = _fix_pronoun_starts(claims)
            for c in claims:
                c["id"] = _claim_id(c["normalized_text"])

            session["status"] = "completed"

            # Run deterministic structure checks
            from .evaluator import evaluate_claims_structure
            struct_eval = evaluate_claims_structure(claims, fixture.get("metadata"))

            save_session(session, {"claims": claims}, evaluation=struct_eval, llm_response={
                "prompt": llm_result["prompt"],
                "response": llm_result["response"],
            })
            return {**session, "output": {"claims": claims}, "evaluation": struct_eval}
        else:
            session["status"] = "parse_error"
            save_session(session, {"raw_response": llm_result["response"]}, llm_response={
                "prompt": llm_result["prompt"],
                "response": llm_result["response"],
            })
            return {**session, "error": "Failed to parse claims from LLM response"}
    else:
        session["status"] = "llm_error"
        save_session(session, {"error": llm_result.get("error", "Unknown error")})
        return {**session, "error": llm_result.get("error")}


# ---------- Layer 4: end_to_end ----------

def run_end_to_end(fixture_name: str, model: str | None = None) -> dict:
    """Run full pipeline: fetch → clean → extract. Returns session metadata."""
    from build_articles import fetch_article, clean_markdown, _build_article_prompt
    from extract_entity_concepts import parse_json_response

    check_api_keys(model)

    fixture = load_fixture("end_to_end", fixture_name)
    url = fixture["metadata"].get("url")

    session = create_session("end_to_end", fixture_name, model=model)
    start = time.time()

    # Step 1: fetch (or use cached HTML)
    if fixture.get("input_text") and fixture.get("input_type") == "html":
        import trafilatura
        extracted = trafilatura.extract(fixture["input_text"], output_format="txt",
                                        include_links=True, include_formatting=True)
        fetched = {"title": fixture["metadata"].get("title", ""), "text": extracted or ""}
    elif url:
        fetched = fetch_article(url)
        if not fetched:
            session["status"] = "fetch_error"
            session["duration_ms"] = int((time.time() - start) * 1000)
            save_session(session, {"error": f"Failed to fetch {url}"})
            return {**session, "error": f"Failed to fetch {url}"}
    else:
        session["status"] = "error"
        session["duration_ms"] = int((time.time() - start) * 1000)
        save_session(session, {"error": "No URL or HTML input"})
        return {**session, "error": "No URL or HTML input"}

    # Step 2: clean
    cleaned = clean_markdown(fetched["text"])

    # Step 3: LLM extract
    prompt = _build_article_prompt(cleaned, fetched.get("title", "Untitled"))
    llm_result = call_llm_instrumented(prompt, model=model)

    session["duration_ms"] = int((time.time() - start) * 1000)
    session["token_usage"] = llm_result.get("token_usage")
    session["model"] = llm_result["model"]

    output = {
        "fetched_title": fetched.get("title", ""),
        "fetched_word_count": len(fetched.get("text", "").split()),
        "cleaned_text": cleaned,
        "cleaned_word_count": len(cleaned.split()),
    }

    if llm_result.get("response"):
        parsed = parse_json_response(llm_result["response"])
        if parsed and isinstance(parsed, dict):
            output["extraction"] = parsed
            session["status"] = "completed"

            # Run both clean and extraction evaluations
            from .evaluator import evaluate_clean_markdown, evaluate_extraction_structure
            clean_eval = evaluate_clean_markdown(fetched["text"], cleaned)
            struct_eval = evaluate_extraction_structure(parsed)
            evaluation = {
                "clean": clean_eval,
                "extraction": struct_eval,
                "pass": clean_eval["pass"] and struct_eval["pass"],
            }
        else:
            output["raw_response"] = llm_result["response"]
            session["status"] = "parse_error"
            evaluation = None
    else:
        output["error"] = llm_result.get("error")
        session["status"] = "llm_error"
        evaluation = None

    save_session(session, output, evaluation=evaluation, llm_response={
        "prompt": llm_result.get("prompt", ""),
        "response": llm_result.get("response", ""),
    })
    return {**session, "output": output}
