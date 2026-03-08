"""Evaluation: deterministic checks for clean_markdown, LLM-as-judge for extraction layers."""

import json
import re

from validate_articles import BOILERPLATE_PATTERNS

# Extended boilerplate patterns (supplement the pipeline's set)
EXTRA_BOILERPLATE = [
    re.compile(r"ko-fi\.com", re.IGNORECASE),
    re.compile(r"support us on", re.IGNORECASE),
    re.compile(r"tip jar", re.IGNORECASE),
    re.compile(r"sponsor", re.IGNORECASE),
    re.compile(r"all rights reserved", re.IGNORECASE),
    re.compile(r"powered by wordpress", re.IGNORECASE),
    re.compile(r"download our app", re.IGNORECASE),
    re.compile(r"sent from my iphone", re.IGNORECASE),
]
ALL_BOILERPLATE = BOILERPLATE_PATTERNS + EXTRA_BOILERPLATE


# ---------- Layer 1: clean_markdown (deterministic) ----------

ARTIFACT_PATTERNS = {
    "nav_links": re.compile(
        r'\[(?:View PDF|HTML \(experimental\)|PDF|Download PDF|Full Text)\]',
        re.IGNORECASE,
    ),
    "cookie_banners": re.compile(
        r'(?:cookie\s*(?:policy|notice|consent|banner)|accept\s*(?:all\s*)?cookies|we\s+use\s+cookies)',
        re.IGNORECASE,
    ),
    "subscribe_cruft": re.compile(
        r'(?:subscribe\s+to\s+(?:our\s+)?(?:newsletter|mailing)|sign\s+up\s+for\s+(?:our\s+)?(?:free\s+)?(?:newsletter|updates))',
        re.IGNORECASE,
    ),
    "wikipedia_edit_links": re.compile(r'\[edit\]'),
    "orphaned_edit_urls": re.compile(
        r'(?:^|\s)\(https?://[^)]*action=edit[^)]*\)',
        re.MULTILINE,
    ),
    "citation_markers": re.compile(r'\[\d{1,3}\]'),
    "empty_links": re.compile(r'\[\s*\]\([^)]+\)'),
    "social_sharing": re.compile(
        r'(?:share\s+(?:this|on)\s+(?:twitter|facebook|linkedin|x|email)|tweet\s+this)',
        re.IGNORECASE,
    ),
    "skip_to_content": re.compile(r'skip\s+to\s+(?:main\s+)?content', re.IGNORECASE),
    "unsubscribe_links": re.compile(
        r'(?:unsubscribe|opt.out|manage\s+(?:your\s+)?(?:email\s+)?preferences)',
        re.IGNORECASE,
    ),
    "email_headers": re.compile(
        r'^-{3,}\s*Forwarded\s+message|^From:.*<[^>]+>|^Sent from my',
        re.MULTILINE | re.IGNORECASE,
    ),
}


def evaluate_clean_markdown(input_text: str, cleaned_text: str,
                            metadata: dict | None = None,
                            reference_text: str | None = None) -> dict:
    """Run deterministic quality checks on cleaned markdown output.

    Args:
        input_text: Original input (may be HTML or markdown)
        cleaned_text: Output of clean_markdown()
        metadata: Fixture metadata with optional expected_removed patterns
        reference_text: For HTML inputs, the trafilatura-extracted text (fairer word count comparison)
    """
    checks = {}
    issues = []

    # Check for artifact patterns
    for name, pattern in ARTIFACT_PATTERNS.items():
        matches = list(pattern.finditer(cleaned_text))
        checks[f"no_{name}"] = len(matches) == 0
        for m in matches:
            line_num = cleaned_text[:m.start()].count('\n') + 1
            issues.append(f"Found {name}: '{m.group()[:80]}' on line {line_num}")

    # Heading hierarchy: at most 1 H1
    h1_count = len(re.findall(r'^# [^#]', cleaned_text, re.MULTILINE))
    checks["single_h1"] = h1_count <= 1
    if h1_count > 1:
        issues.append(f"Found {h1_count} H1 headings (expected <=1)")

    # Boilerplate tail check (use extended patterns)
    tail = cleaned_text[-500:] if len(cleaned_text) > 500 else cleaned_text
    has_boilerplate = any(p.search(tail) for p in ALL_BOILERPLATE)
    checks["no_boilerplate_tail"] = not has_boilerplate
    if has_boilerplate:
        matching = [p.pattern for p in ALL_BOILERPLATE if p.search(tail)]
        issues.append(f"Boilerplate in tail: {matching[0][:40]}")

    # Content preservation — use reference_text if provided (fairer for HTML inputs)
    compare_text = reference_text or input_text
    input_words = len(compare_text.split())
    output_words = len(cleaned_text.split())
    if input_words > 0:
        ratio = output_words / input_words
        checks["content_preserved"] = ratio > 0.7
        if ratio <= 0.7:
            issues.append(f"Content ratio {ratio:.2f} — lost too much ({input_words} → {output_words} words)")
    else:
        checks["content_preserved"] = True

    # Non-empty output
    checks["non_empty"] = len(cleaned_text.strip()) > 50
    if not checks["non_empty"]:
        issues.append(f"Output too short: {len(cleaned_text.strip())} chars")

    # Broken markdown: dangling content from removal
    orphan_parens = re.findall(r'^#{1,6}\s+\w+\(https?://', cleaned_text, re.MULTILINE)
    checks["no_broken_headings"] = len(orphan_parens) == 0
    if orphan_parens:
        issues.append(f"Broken heading with orphaned URL: '{orphan_parens[0][:60]}'")

    # Multiple consecutive blank lines (cleanup quality)
    triple_blanks = re.findall(r'\n{4,}', cleaned_text)
    checks["no_excessive_blanks"] = len(triple_blanks) == 0
    if triple_blanks:
        issues.append(f"Found {len(triple_blanks)} runs of 4+ blank lines")

    # Fixture-specific expected removals
    if metadata and metadata.get("expected_removed"):
        for pattern_str in metadata["expected_removed"]:
            found = re.search(pattern_str, cleaned_text, re.IGNORECASE)
            checks[f"removed_{pattern_str[:30]}"] = found is None
            if found:
                issues.append(f"Expected removal not cleaned: '{pattern_str}'")

    all_passed = all(checks.values())
    return {
        "checks": checks,
        "issues": issues,
        "pass": all_passed,
        "summary": f"{'PASS' if all_passed else 'FAIL'}: {sum(checks.values())}/{len(checks)} checks passed",
    }


# ---------- Layer 2: article_extraction (deterministic + LLM-as-judge) ----------

VALID_CONTENT_TYPES = {
    "analysis", "tutorial", "opinion", "news", "research",
    "reference", "announcement", "discussion", "review", "essay",
    "interview", "comparison", "guide", "report",
}


def evaluate_extraction_structure(extraction: dict) -> dict:
    """Deterministic structural checks for article extraction output.

    These catch parsing/schema issues without needing an LLM.
    """
    checks = {}
    issues = []

    # Required fields exist and are non-empty
    checks["has_title"] = bool(extraction.get("title", "").strip())
    if not checks["has_title"]:
        issues.append("Missing or empty title")

    summary = extraction.get("one_line_summary", "")
    checks["has_summary"] = bool(summary.strip())
    if not checks["has_summary"]:
        issues.append("Missing one_line_summary")
    checks["summary_length_ok"] = len(summary) <= 150
    if not checks["summary_length_ok"]:
        issues.append(f"one_line_summary too long: {len(summary)} chars (max 150)")

    checks["has_full_summary"] = bool(extraction.get("full_summary", "").strip())
    if not checks["has_full_summary"]:
        issues.append("Missing full_summary")

    # Content type validation
    ct = extraction.get("content_type", "")
    checks["valid_content_type"] = ct.lower() in VALID_CONTENT_TYPES
    if not checks["valid_content_type"]:
        issues.append(f"Invalid content_type: '{ct}' (expected one of {sorted(VALID_CONTENT_TYPES)})")

    # Key claims
    claims = extraction.get("key_claims", [])
    checks["has_key_claims"] = len(claims) >= 1
    if not checks["has_key_claims"]:
        issues.append("No key_claims")
    checks["claims_count_ok"] = 1 <= len(claims) <= 15
    if not checks["claims_count_ok"]:
        issues.append(f"key_claims count {len(claims)} out of expected range 1-15")

    # Topics
    topics = extraction.get("topics", [])
    checks["has_topics"] = len(topics) >= 1
    if not checks["has_topics"]:
        issues.append("No topics")

    # Sections
    sections = extraction.get("sections", [])
    checks["has_sections"] = len(sections) >= 1
    if not checks["has_sections"]:
        issues.append("No sections")
    # Validate section structure
    bad_sections = []
    for i, s in enumerate(sections):
        if not s.get("heading"):
            bad_sections.append(f"section[{i}] missing heading")
    checks["sections_valid"] = len(bad_sections) == 0
    if bad_sections:
        issues.extend(bad_sections[:3])

    # Interest topics structure
    itopics = extraction.get("interest_topics", [])
    checks["has_interest_topics"] = len(itopics) >= 1
    if not checks["has_interest_topics"]:
        issues.append("No interest_topics")
    bad_it = []
    for i, t in enumerate(itopics):
        if not t.get("broad"):
            bad_it.append(f"interest_topics[{i}] missing 'broad'")
        if not t.get("specific"):
            bad_it.append(f"interest_topics[{i}] missing 'specific'")
    checks["interest_topics_valid"] = len(bad_it) == 0
    if bad_it:
        issues.extend(bad_it[:3])

    # Novelty claims structure
    nclaims = extraction.get("novelty_claims", [])
    checks["has_novelty_claims"] = len(nclaims) >= 1
    if not checks["has_novelty_claims"]:
        issues.append("No novelty_claims")
    for i, nc in enumerate(nclaims):
        if nc.get("specificity") not in ("high", "medium", "low"):
            issues.append(f"novelty_claims[{i}] invalid specificity: '{nc.get('specificity')}'")
            checks["novelty_claims_valid"] = False
            break
    else:
        checks["novelty_claims_valid"] = True

    # Read time
    rt = extraction.get("estimated_read_minutes", 0)
    checks["read_time_reasonable"] = isinstance(rt, (int, float)) and 1 <= rt <= 120
    if not checks["read_time_reasonable"]:
        issues.append(f"Unreasonable estimated_read_minutes: {rt}")

    all_passed = all(checks.values())
    return {
        "checks": checks,
        "issues": issues,
        "pass": all_passed,
        "summary": f"{'PASS' if all_passed else 'FAIL'}: {sum(checks.values())}/{len(checks)} checks passed",
    }


JUDGE_PROMPT = """You are evaluating the quality of an article extraction for a reading app.

## Original Article
Title: {title}
Content (first 3000 chars):
{content_preview}

## Extracted Output
{extraction_json}

## Scoring Criteria (1-5 each)

1. **title_quality**: Is the title clear, accurate, and improved from the original?
2. **summary_quality**: Does the summary capture all key points concisely?
3. **claims_specificity**: Are key_claims specific and factual (not vague)?
4. **topics_relevance**: Are topic tags relevant and well-chosen?
5. **interest_topics_quality**: Are interest_topics hierarchical (broad>specific>entity) and useful for knowledge modeling?
6. **novelty_claims_quality**: Are novelty_claims genuinely novel/surprising with accurate specificity ratings?
7. **section_coverage**: Do sections cover the article well with useful summaries?

Return ONLY a JSON object:
{{
  "scores": {{
    "title_quality": N,
    "summary_quality": N,
    "claims_specificity": N,
    "topics_relevance": N,
    "interest_topics_quality": N,
    "novelty_claims_quality": N,
    "section_coverage": N
  }},
  "issues": ["specific issue 1", "specific issue 2"],
  "overall": N.N
}}"""


def build_judge_prompt(fixture_content: str, fixture_title: str, extraction: dict) -> str:
    """Build the LLM-as-judge prompt for article extraction evaluation."""
    content_preview = fixture_content[:3000]
    extraction_json = json.dumps(extraction, indent=2, ensure_ascii=False)
    return JUDGE_PROMPT.format(
        title=fixture_title,
        content_preview=content_preview,
        extraction_json=extraction_json,
    )


def evaluate_article_extraction(fixture_content: str, fixture_title: str,
                                extraction: dict, judge_model: str = "gemini/gemini-2.0-flash") -> dict:
    """Evaluate article extraction: deterministic structure checks + LLM-as-judge."""
    from extract_entity_concepts import parse_json_response
    from lib.runner import call_llm_instrumented

    # Phase 1: deterministic checks (always run, free)
    struct_eval = evaluate_extraction_structure(extraction)

    # Phase 2: LLM-as-judge
    prompt = build_judge_prompt(fixture_content, fixture_title, extraction)
    result = call_llm_instrumented(prompt, model=judge_model)

    if not result or not result.get("response"):
        struct_eval["llm_judge"] = "failed"
        struct_eval["issues"].append("LLM judge call failed")
        return struct_eval

    parsed = parse_json_response(result["response"])
    if not parsed or not isinstance(parsed, dict):
        struct_eval["llm_judge"] = "parse_error"
        struct_eval["issues"].append("LLM judge response not parseable")
        struct_eval["raw_response"] = result["response"]
        return struct_eval

    # Merge: structural checks + LLM scores
    scores = parsed.get("scores", {})
    llm_issues = parsed.get("issues", [])
    overall = parsed.get("overall", 0.0)

    # Validate LLM scores are in expected range
    for key, val in list(scores.items()):
        if not isinstance(val, (int, float)) or val < 1 or val > 5:
            scores[key] = 0  # invalid score

    return {
        "structure": struct_eval,
        "scores": scores,
        "issues": struct_eval["issues"] + llm_issues,
        "overall": overall,
        "pass": struct_eval["pass"],
    }


# ---------- Layer 3: entity_concepts ----------

ENTITY_JUDGE_PROMPT = """You are evaluating extracted knowledge entities from articles.

## Source Articles (summaries)
{articles_summary}

## Extracted Entities
{entities_json}

## Scoring Criteria (1-5 each)

1. **entity_quality**: Are entities well-named (short noun phrases, 1-6 words)?
2. **specificity**: Are they specific enough to be useful (not too generic, not too verbose)?
3. **coverage**: Do they cover the important concepts from the articles?
4. **deduplication**: Are there any duplicates or near-duplicates that should be merged?
5. **descriptions**: Are descriptions concise and informative (1-2 sentences)?

Return ONLY a JSON object:
{{
  "scores": {{
    "entity_quality": N,
    "specificity": N,
    "coverage": N,
    "deduplication": N,
    "descriptions": N
  }},
  "issues": ["specific issue 1"],
  "overall": N.N
}}"""


def build_entity_judge_prompt(articles: list[dict], entities: list[dict]) -> str:
    summaries = []
    for a in articles:
        summaries.append(f"- **{a.get('title', 'Untitled')}**: {a.get('full_summary', a.get('one_line_summary', ''))[:200]}")
    return ENTITY_JUDGE_PROMPT.format(
        articles_summary="\n".join(summaries),
        entities_json=json.dumps(entities, indent=2, ensure_ascii=False),
    )


# ---------- Layer: atomic_claims (deterministic + LLM-as-judge) ----------

VALID_CLAIM_TYPES = {
    "factual", "causal", "comparative", "procedural",
    "evaluative", "predictive", "experiential",
}

# Pronouns that suggest a claim is not self-contained
DANGLING_PRONOUN_RE = re.compile(r"^(It|They|This|He|She|These|Those|That)\s", re.IGNORECASE)


def evaluate_claims_structure(claims: list[dict], metadata: dict | None = None) -> dict:
    """Deterministic structural checks for atomic claims output."""
    checks = {}
    issues = []

    # Claim count in expected range
    count = len(claims)
    expected = (metadata or {}).get("expected_claim_count_range", [5, 40])
    lo, hi = expected[0], expected[1]
    checks["claim_count_in_range"] = lo <= count <= hi
    if not checks["claim_count_in_range"]:
        issues.append(f"Claim count {count} outside expected range [{lo}, {hi}]")

    # Per-claim checks
    bad_fields = []
    bad_types = []
    bad_pronouns = []
    bad_compound = []
    bad_topics = []
    bad_empty = []

    for i, claim in enumerate(claims):
        # Required fields
        missing = []
        for field in ["normalized_text", "claim_type", "source_paragraphs", "topics"]:
            if field not in claim or claim[field] is None:
                missing.append(field)
        if missing:
            bad_fields.append(f"claim[{i}] missing: {', '.join(missing)}")

        # Valid claim_type
        ct = claim.get("claim_type", "")
        if ct not in VALID_CLAIM_TYPES:
            bad_types.append(f"claim[{i}] invalid type: '{ct}'")

        # Self-contained check (no dangling pronouns)
        text = claim.get("normalized_text", "")
        if DANGLING_PRONOUN_RE.match(text):
            bad_pronouns.append(f"claim[{i}] starts with pronoun: '{text[:50]}'")

        # No empty text
        if not text.strip():
            bad_empty.append(f"claim[{i}] has empty normalized_text")

        # Topics present
        topics = claim.get("topics", [])
        if not topics:
            bad_topics.append(f"claim[{i}] has no topics")

        # Compound claim check (rough heuristic)
        if " and " in text:
            parts = text.split(" and ")
            # Only flag if both parts look like independent clauses (contain a verb-like word)
            if len(parts) == 2 and len(parts[0].split()) > 4 and len(parts[1].split()) > 4:
                bad_compound.append(f"claim[{i}] may be compound: '{text[:60]}'")

    checks["required_fields"] = len(bad_fields) == 0
    if bad_fields:
        issues.extend(bad_fields[:3])

    checks["valid_claim_types"] = len(bad_types) == 0
    if bad_types:
        issues.extend(bad_types[:3])

    checks["self_contained"] = len(bad_pronouns) <= max(1, len(claims) * 0.05)  # allow up to 1 or 5%
    if bad_pronouns:
        issues.extend(bad_pronouns[:3])

    checks["no_empty_text"] = len(bad_empty) == 0
    if bad_empty:
        issues.extend(bad_empty[:3])

    checks["topics_present"] = len(bad_topics) <= len(claims) * 0.1  # allow up to 10% without topics
    if bad_topics:
        issues.extend(bad_topics[:3])

    checks["no_compound_claims"] = len(bad_compound) <= len(claims) * 0.3  # allow up to 30% (heuristic is noisy)
    if bad_compound:
        issues.extend(bad_compound[:3])

    all_passed = all(checks.values())
    return {
        "checks": checks,
        "issues": issues,
        "pass": all_passed,
        "summary": f"{'PASS' if all_passed else 'FAIL'}: {sum(checks.values())}/{len(checks)} checks passed",
        "claim_count": count,
        "type_distribution": _type_distribution(claims),
    }


def _type_distribution(claims: list[dict]) -> dict[str, int]:
    """Count claims by type."""
    dist: dict[str, int] = {}
    for c in claims:
        ct = c.get("claim_type", "unknown")
        dist[ct] = dist.get(ct, 0) + 1
    return dist


CLAIMS_JUDGE_PROMPT = """You are evaluating the quality of atomic claim extraction from an article.

## Original Article
Title: {title}
Content (first 3000 chars):
{content_preview}

## Extracted Claims ({claim_count} total)
{claims_json}

## Scoring Criteria (1-5 each)

1. **granularity**: Are claims atomic enough? Each should be one single assertion. Not too broad (paragraph-level), not too narrow (trivial detail). Score 5 = perfectly atomic.
2. **decontextualization**: Can each claim be understood without the original article? No dangling pronouns, sufficient context added. Score 5 = fully self-contained.
3. **type_accuracy**: Are claim_type labels correct? (factual vs causal vs evaluative etc.) Score 5 = all labels correct.
4. **coverage**: Do the claims cover the article's main knowledge contributions? Not just the introduction. Score 5 = comprehensive coverage.
5. **topic_quality**: Are topic tags relevant, specific enough, and in kebab-case? Score 5 = excellent tagging.

Return ONLY a JSON object:
{{
  "scores": {{
    "granularity": N,
    "decontextualization": N,
    "type_accuracy": N,
    "coverage": N,
    "topic_quality": N
  }},
  "issues": ["specific issue 1", "specific issue 2"],
  "overall": N.N
}}"""


def build_claims_judge_prompt(fixture_content: str, fixture_title: str, claims: list[dict]) -> str:
    """Build the LLM-as-judge prompt for atomic claims evaluation."""
    content_preview = fixture_content[:3000]
    claims_json = json.dumps(claims, indent=2, ensure_ascii=False)
    return CLAIMS_JUDGE_PROMPT.format(
        title=fixture_title,
        content_preview=content_preview,
        claims_json=claims_json,
        claim_count=len(claims),
    )


def evaluate_atomic_claims(fixture_content: str, fixture_title: str,
                           claims: list[dict], metadata: dict | None = None,
                           judge_model: str = "gemini/gemini-2.0-flash") -> dict:
    """Evaluate atomic claims: deterministic structure checks + LLM-as-judge."""
    from extract_entity_concepts import parse_json_response
    from lib.runner import call_llm_instrumented

    # Phase 1: deterministic checks
    struct_eval = evaluate_claims_structure(claims, metadata)

    # Phase 2: LLM-as-judge
    prompt = build_claims_judge_prompt(fixture_content, fixture_title, claims)
    result = call_llm_instrumented(prompt, model=judge_model)

    if not result or not result.get("response"):
        struct_eval["llm_judge"] = "failed"
        struct_eval["issues"].append("LLM judge call failed")
        return struct_eval

    parsed = parse_json_response(result["response"])
    if not parsed or not isinstance(parsed, dict):
        struct_eval["llm_judge"] = "parse_error"
        struct_eval["issues"].append("LLM judge response not parseable")
        struct_eval["raw_response"] = result["response"]
        return struct_eval

    # Merge: structural checks + LLM scores
    scores = parsed.get("scores", {})
    llm_issues = parsed.get("issues", [])
    overall = parsed.get("overall", 0.0)

    for key, val in list(scores.items()):
        if not isinstance(val, (int, float)) or val < 1 or val > 5:
            scores[key] = 0

    return {
        "structure": struct_eval,
        "scores": scores,
        "issues": struct_eval["issues"] + llm_issues,
        "overall": overall,
        "pass": struct_eval["pass"],
        "claim_count": struct_eval["claim_count"],
        "type_distribution": struct_eval["type_distribution"],
    }
