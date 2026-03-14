#!/usr/bin/env python3
"""Generate structured syntheses from concept clusters.

Reads concept_clusters.json (from build_concept_clusters.py), articles.json,
and knowledge_index.json to produce rich narrative syntheses per cluster.

Uses gemini_llm.call_llm() with gemini-2.0-flash for synthesis quality.

Output: data/syntheses.json

Usage:
    python3 scripts/generate_syntheses.py --all
    python3 scripts/generate_syntheses.py --cluster "Orchestration and Tooling"
    python3 scripts/generate_syntheses.py --cluster-id 3
    python3 scripts/generate_syntheses.py --dry-run --verbose
    python3 scripts/generate_syntheses.py --force --min-articles 3
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
CLUSTERS_PATH = DATA_DIR / "concept_clusters.json"
ARTICLES_PATH = DATA_DIR / "articles.json"
KNOWLEDGE_INDEX_PATH = DATA_DIR / "knowledge_index.json"
SYNTHESES_PATH = DATA_DIR / "syntheses.json"

# Quality thresholds
MIN_TOTAL_WORDS = 200          # Skip clusters where all articles sum to < this
LARGE_CLUSTER_THRESHOLD = 15   # Above this, send summaries only for peripheral articles
CORE_ARTICLES_FOR_LARGE = 5    # Full content for top N core articles in large clusters
MAX_CONTEXT_CHARS = 120_000    # Truncate total context to stay within model limits

SYNTHESIS_MODEL = "gemini-3-flash-preview"

# Load env from .env file if present
for env_path in [PROJECT_DIR / ".env", Path("/opt/petrarca/.env")]:
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    key, value = key.strip(), value.strip()
                    if key not in os.environ:
                        os.environ[key] = value


def log(msg: str):
    print(msg, file=sys.stderr)


def load_data() -> tuple[list[dict], dict, dict]:
    """Load articles.json, knowledge_index.json, and concept_clusters.json."""
    for path, name in [
        (CLUSTERS_PATH, "concept_clusters.json"),
        (ARTICLES_PATH, "articles.json"),
        (KNOWLEDGE_INDEX_PATH, "knowledge_index.json"),
    ]:
        if not path.exists():
            log(f"ERROR: {name} not found at {path}")
            sys.exit(1)

    with open(CLUSTERS_PATH) as f:
        clusters_data = json.load(f)
    with open(ARTICLES_PATH) as f:
        articles = json.load(f)
    with open(KNOWLEDGE_INDEX_PATH) as f:
        ki = json.load(f)

    return articles, ki, clusters_data


def load_existing_syntheses() -> dict[str, dict]:
    """Load existing syntheses keyed by cluster_id for incremental updates."""
    if not SYNTHESES_PATH.exists():
        return {}
    try:
        with open(SYNTHESES_PATH) as f:
            data = json.load(f)
        return {s["cluster_id"]: s for s in data.get("syntheses", []) if "cluster_id" in s}
    except (json.JSONDecodeError, KeyError):
        return {}


def cluster_has_changed(cluster: dict, existing: dict) -> bool:
    """Check if cluster articles have changed since last synthesis."""
    current_ids = set(a["id"] for a in cluster["articles"])
    previous_ids = set(existing.get("article_ids", []))
    return current_ids != previous_ids


def estimate_cluster_word_count(cluster: dict, article_map: dict[str, dict]) -> int:
    """Sum word counts across all articles in cluster."""
    total = 0
    for entry in cluster["articles"]:
        art = article_map.get(entry["id"], {})
        total += art.get("word_count", 0)
    return total


def build_article_context(article: dict, ki: dict, full: bool = True) -> str:
    """Build context string for one article.

    If full=True, includes sections content. Otherwise just summary + key_claims.
    """
    parts = []
    parts.append(f"### {article['title']}")
    parts.append(f"ID: {article['id']}")
    if article.get("author"):
        parts.append(f"Author: {article['author']}")
    if article.get("hostname"):
        parts.append(f"Source: {article['hostname']}")
    parts.append(f"Word count: {article.get('word_count', 0)}")
    parts.append(f"Topics: {', '.join(article.get('topics', []))}")
    parts.append("")

    # Summary
    summary = article.get("full_summary", article.get("one_line_summary", ""))
    if summary:
        parts.append(f"**Summary:** {summary}")
        parts.append("")

    # Key claims
    key_claims = article.get("key_claims", [])
    if key_claims:
        parts.append("**Key claims:**")
        for c in key_claims:
            parts.append(f"- {c}")
        parts.append("")

    # Atomic claims with IDs
    atomic = article.get("atomic_claims", [])
    if atomic:
        parts.append(f"**Atomic claims ({len(atomic)}):**")
        for ac in atomic:
            cid = ac.get("id", "")
            text = ac.get("normalized_text", ac.get("original_text", ""))
            ctype = ac.get("claim_type", "")
            parts.append(f"- [{cid}] ({ctype}) {text}")
        parts.append("")

    # Full sections content (only if requested)
    if full and article.get("sections"):
        parts.append("**Sections:**")
        for sec in article["sections"]:
            heading = sec.get("heading", "Untitled")
            content = sec.get("content", "")
            sec_summary = sec.get("summary", "")
            parts.append(f"\n#### {heading}")
            if sec_summary:
                parts.append(f"*Summary: {sec_summary}*")
            if content:
                # Truncate very long sections
                if len(content) > 3000:
                    content = content[:3000] + "\n[...truncated...]"
                parts.append(content)
        parts.append("")

    return "\n".join(parts)


def build_cross_article_context(cluster: dict, ki: dict, article_map: dict[str, dict]) -> str:
    """Build context about relationships between articles in the cluster."""
    cluster_ids = set(a["id"] for a in cluster["articles"])
    nm = ki.get("article_novelty_matrix", {})
    claims_dict = ki.get("claims", {})

    parts = []
    parts.append("## Cross-Article Relationships")
    parts.append("")

    # Show novelty matrix entries between cluster articles
    relationships = []
    for target_id in cluster_ids:
        if target_id not in nm:
            continue
        for read_id, counts in nm[target_id].items():
            if read_id not in cluster_ids or read_id == target_id:
                continue
            new = counts.get("new", 0)
            extends = counts.get("extends", 0)
            known = counts.get("known", 0)
            total = new + extends + known
            if total == 0:
                continue
            target_title = article_map.get(target_id, {}).get("title", target_id[:8])
            read_title = article_map.get(read_id, {}).get("title", read_id[:8])
            overlap_pct = round((extends + known) / total * 100) if total else 0
            relationships.append(
                f"- After reading \"{read_title[:50]}\", "
                f"\"{target_title[:50]}\" has {new} new / {extends} extending / "
                f"{known} known claims ({overlap_pct}% overlap)"
            )

    if relationships:
        # Limit to most interesting relationships
        parts.extend(relationships[:30])
    else:
        parts.append("No novelty matrix data available between these articles.")

    # Show key shared claims from cluster data
    key_shared = cluster.get("key_shared_claims", [])
    if key_shared:
        parts.append("")
        parts.append("## Key Shared Claims (appear across multiple articles)")
        for c in key_shared:
            claim_info = claims_dict.get(c["claim_id"], {})
            art_id = claim_info.get("article_id", c.get("article_id", ""))
            art_title = article_map.get(art_id, {}).get("title", "")[:40]
            parts.append(
                f"- [{c['claim_id']}] {c['text']} "
                f"(from \"{art_title}\", {c['cross_article_links']} cross-links)"
            )

    return "\n".join(parts)


def build_synthesis_prompt(cluster: dict, article_map: dict[str, dict],
                           ki: dict) -> str:
    """Build the full LLM prompt for synthesis generation."""
    cluster_label = cluster["label"]
    cluster_articles = cluster["articles"]
    num_articles = len(cluster_articles)

    is_large = num_articles > LARGE_CLUSTER_THRESHOLD
    core_ids = set(cluster.get("core_article_ids", []))

    # Build article contexts
    article_sections = []
    total_chars = 0

    # Sort: core articles first, then by claim count descending
    sorted_entries = sorted(
        cluster_articles,
        key=lambda a: (not a.get("is_core", False), -a.get("claim_count", 0))
    )

    for i, entry in enumerate(sorted_entries):
        art = article_map.get(entry["id"])
        if not art:
            continue

        # Full content for core articles (or all if small cluster)
        if is_large:
            use_full = entry["id"] in core_ids and i < CORE_ARTICLES_FOR_LARGE
        else:
            use_full = True

        ctx = build_article_context(art, ki, full=use_full)

        # Respect context limit
        if total_chars + len(ctx) > MAX_CONTEXT_CHARS:
            # Truncate this one to summary-only
            ctx = build_article_context(art, ki, full=False)
            if total_chars + len(ctx) > MAX_CONTEXT_CHARS:
                article_sections.append(f"### {art['title']}\n[Content omitted due to context limits]")
                continue

        article_sections.append(ctx)
        total_chars += len(ctx)

    articles_text = "\n---\n\n".join(article_sections)

    # Build article reference key (ID→title lookup for LLM to write proper links)
    ref_lines = []
    for entry in sorted_entries:
        art = article_map.get(entry["id"])
        if art:
            ref_lines.append(f"- {entry['id']} → [**{art['title']}**](article:{entry['id']})")
    article_ref_table = "\n".join(ref_lines)

    # Cross-article relationships
    cross_context = build_cross_article_context(cluster, ki, article_map)

    # Collect all claim IDs in cluster for reference
    all_claim_ids = []
    for entry in cluster_articles:
        art = article_map.get(entry["id"], {})
        for ac in art.get("atomic_claims", []):
            if ac.get("id"):
                all_claim_ids.append(ac["id"])

    system_instruction = (
        "You are a humanist scholar synthesizing research across multiple sources. "
        "Write flowing, substantive prose — not thin summaries or bullet lists. "
        "Each section should have 2-3 rich paragraphs with equal depth throughout. "
        "Two non-negotiable rules: "
        "(1) Reference source articles using markdown links in the format "
        "[Article Title](article:ARTICLE_ID) — use the exact IDs and titles from the "
        "Article Reference Key provided. Every paragraph must reference at least one source. "
        "(2) Actively surface tensions, disagreements, and different emphases between sources — "
        "embed them inline as blockquotes with the ⚡ marker."
    )

    prompt = f"""Synthesize {num_articles} articles about "{cluster_label}" into a rich narrative analysis.

# Articles

{articles_text}

---

{cross_context}

---

# Article Reference Key

Use these exact IDs when linking to articles in your synthesis:

{article_ref_table}

---

# Instructions

Produce a JSON object with exactly these fields:

1. **"synthesis_markdown"**: A rich narrative synthesis in Markdown.

   STRUCTURE:
   - Use descriptive ## headings that capture the actual insight, e.g. "## Agents Self-Organize and Invent Their Own Protocols" — NEVER generic headings like "Theme 1", "Shared Themes", "Overview", "Unique Contributions".
   - Organize by insight and argument, not by article. Let the structure emerge from the ideas.
   - Each section: 2-3 rich paragraphs. Equal depth throughout — don't front-load.

   STYLE REQUIREMENTS:
   - Reference source articles as markdown links: [Article Title](article:ARTICLE_ID) using the exact IDs from the Article Reference Key above. NEVER use raw hex IDs like [a1b2c3d4e5f6]. NEVER use **bold title** without a link.
   - Every paragraph must reference at least one source via link.
   - Flowing scholarly prose, not bullet lists.

   TENSIONS (inline):
   - When sources disagree or emphasize different things, embed tensions inline as blockquotes:
     > ⚡ **Tension label**
     > Description referencing [Article A](article:x) vs [Article B](article:y)...
   - Look hard for tensions. Different emphases, scope, audience, methodology all count. Aim for 3-5 inline tension blocks.

   RESEARCH PROMPTS (inline):
   - Weave open questions into the narrative as italicized asides: *Open question: How does X relate to Y?*

   PROGRESSIVE DISCLOSURE:
   - For detailed technical subsections or extended examples, wrap them in HTML comment markers:
     <!-- detail -->
     Detailed content here...
     <!-- /detail -->
   - Use 2-4 of these per synthesis for secondary depth.

2. **"article_coverage"**: Object mapping article_id → float (0.0 to 1.0). What fraction of each article's intellectual value is captured? Be honest.

3. **"claims_covered"**: Array of claim_id strings. All atomic claim IDs meaningfully represented in the synthesis — err on inclusion.

4. **"unique_per_article"**: Object mapping article_id → array of strings. 1-3 bullets per article on what ONLY it contributes.

5. **"follow_up_questions"**: Array of 5 objects, each with:
   - "question": A specific question a curious reader would want answered
   - "research_prompt": A search query to find the answer
   - "related_topics": Array of 1-3 topic strings

6. **"tensions"**: Array of objects, each with:
   - "label": Short tension title (e.g. "Open-source vs proprietary agent stacks")
   - "description": Full description naming sources on each side using [Title](article:ID) links
   - "article_ids": Array of article IDs involved
"""

    return prompt, system_instruction


def parse_llm_response(response: str) -> dict | None:
    """Parse the LLM's JSON response, handling common formatting issues."""
    if not response:
        return None

    text = response.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?\s*```\s*$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        log(f"    JSON parse error: {e}")
        # Try to find JSON object in the response
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        log(f"    Could not extract valid JSON from response ({len(text)} chars)")
        return None


def _build_synthesis_tool():
    """Build the FunctionDeclaration for structured synthesis output."""
    from google.genai import types as gtypes
    return gtypes.FunctionDeclaration(
        name="submit_synthesis",
        description="Submit the completed synthesis analysis",
        parameters=gtypes.Schema(
            type="OBJECT",
            properties={
                "synthesis_markdown": gtypes.Schema(
                    type="STRING",
                    description="Rich narrative synthesis in Markdown with descriptive ## headings, inline article links as [Title](article:ID), inline ⚡ tension blockquotes, and <!-- detail --> progressive disclosure markers",
                ),
                "article_coverage": gtypes.Schema(
                    type="ARRAY",
                    description="Per-article coverage estimates",
                    items=gtypes.Schema(
                        type="OBJECT",
                        properties={
                            "article_id": gtypes.Schema(type="STRING"),
                            "coverage": gtypes.Schema(type="NUMBER", description="0.0 to 1.0"),
                        },
                        required=["article_id", "coverage"],
                    ),
                ),
                "claims_covered": gtypes.Schema(
                    type="ARRAY",
                    items=gtypes.Schema(type="STRING"),
                    description="Claim IDs meaningfully covered by the synthesis",
                ),
                "unique_per_article": gtypes.Schema(
                    type="ARRAY",
                    description="What each article uniquely contributes",
                    items=gtypes.Schema(
                        type="OBJECT",
                        properties={
                            "article_id": gtypes.Schema(type="STRING"),
                            "contributions": gtypes.Schema(
                                type="ARRAY", items=gtypes.Schema(type="STRING"),
                            ),
                        },
                        required=["article_id", "contributions"],
                    ),
                ),
                "follow_up_questions": gtypes.Schema(
                    type="ARRAY",
                    items=gtypes.Schema(
                        type="OBJECT",
                        properties={
                            "question": gtypes.Schema(type="STRING"),
                            "research_prompt": gtypes.Schema(type="STRING"),
                            "related_topics": gtypes.Schema(
                                type="ARRAY", items=gtypes.Schema(type="STRING"),
                            ),
                        },
                        required=["question", "research_prompt"],
                    ),
                ),
                "tensions": gtypes.Schema(
                    type="ARRAY",
                    items=gtypes.Schema(
                        type="OBJECT",
                        properties={
                            "label": gtypes.Schema(type="STRING", description="Short tension title"),
                            "description": gtypes.Schema(type="STRING", description="Full description naming sources"),
                            "article_ids": gtypes.Schema(
                                type="ARRAY", items=gtypes.Schema(type="STRING"),
                                description="Article IDs involved",
                            ),
                        },
                        required=["label", "description"],
                    ),
                    description="Disagreements or different perspectives between named sources",
                ),
            },
            required=["synthesis_markdown", "article_coverage", "claims_covered",
                       "unique_per_article", "follow_up_questions", "tensions"],
        ),
    )


_SYNTHESIS_TOOL = None


def get_synthesis_tool():
    global _SYNTHESIS_TOOL
    if _SYNTHESIS_TOOL is None:
        _SYNTHESIS_TOOL = _build_synthesis_tool()
    return _SYNTHESIS_TOOL


def generate_one_synthesis(cluster: dict, article_map: dict[str, dict],
                            ki: dict, verbose: bool = False) -> dict | None:
    """Generate a synthesis for a single cluster via tool calling."""
    from gemini_llm import call_llm, call_llm_tool

    cluster_label = cluster["label"]
    cluster_id = f"cluster_{cluster['cluster_id']}"
    article_entries = cluster["articles"]
    article_ids = [a["id"] for a in article_entries]

    log(f"  Generating synthesis: {cluster_label} ({len(article_entries)} articles)...")

    prompt, system_instruction = build_synthesis_prompt(cluster, article_map, ki)
    tool_prompt = prompt + "\n\nCall submit_synthesis with your complete analysis."

    if verbose:
        log(f"    Prompt length: {len(tool_prompt)} chars")

    # Try tool calling first (structured output, no JSON parsing needed)
    parsed = call_llm_tool(
        tool_prompt,
        get_synthesis_tool(),
        model=SYNTHESIS_MODEL,
        max_tokens=12288,
        system_instruction=system_instruction,
    )

    # Fallback to raw JSON if tool calling fails
    if not parsed:
        log(f"    Tool calling failed, falling back to raw JSON...")
        response = call_llm(
            prompt,
            model=SYNTHESIS_MODEL,
            max_tokens=12288,
            system_instruction=system_instruction,
        )
        if response:
            parsed = parse_llm_response(response)
            if not parsed:
                log(f"    FAILED: Could not parse LLM response")
                if verbose:
                    log(f"    Raw response (first 500 chars): {response[:500]}")
                return None
        else:
            log(f"    FAILED: No response from LLM")
            return None

    if verbose:
        log(f"    Got structured response with {len(parsed)} fields")

    # Validate required fields
    synthesis_md = parsed.get("synthesis_markdown", "")
    if not synthesis_md or len(synthesis_md) < 100:
        log(f"    FAILED: Synthesis too short ({len(synthesis_md)} chars)")
        return None

    # Normalize article_coverage: handle both array format (tool calling)
    # and dict format (raw JSON fallback)
    raw_coverage = parsed.get("article_coverage", {})
    if isinstance(raw_coverage, list):
        article_coverage = {
            item.get("article_id", ""): item.get("coverage", 0)
            for item in raw_coverage if item.get("article_id")
        }
    else:
        article_coverage = raw_coverage

    # Normalize unique_per_article: handle both array and dict formats
    raw_unique = parsed.get("unique_per_article", {})
    if isinstance(raw_unique, list):
        unique_per_article = {
            item.get("article_id", ""): item.get("contributions", [])
            for item in raw_unique if item.get("article_id")
        }
    else:
        unique_per_article = raw_unique

    llm_claims_covered = set(parsed.get("claims_covered", []))
    follow_up_questions = parsed.get("follow_up_questions", [])

    # Normalize tensions: handle both old string format and new object format
    raw_tensions = parsed.get("tensions", [])
    tensions = []
    for t in raw_tensions:
        if isinstance(t, str):
            tensions.append({"label": t[:80], "description": t, "article_ids": []})
        elif isinstance(t, dict):
            tensions.append(t)

    # Count total claims in cluster and build claim → article mapping
    total_claims_in_cluster = 0
    all_cluster_claim_ids = set()
    claims_by_article = {}
    for entry in article_entries:
        art = article_map.get(entry["id"], {})
        art_claims = [ac.get("id") for ac in art.get("atomic_claims", []) if ac.get("id")]
        claims_by_article[entry["id"]] = art_claims
        all_cluster_claim_ids.update(art_claims)
        total_claims_in_cluster += len(art_claims)

    # POST-PROCESS: Expand claims_covered using article_coverage + similarity matrix.
    # The LLM typically under-reports which claims it covers (tags 5-10% when it
    # discusses 50-80% of the content). Fix by including all claims from articles
    # with high coverage, plus claims similar to any LLM-tagged claim.
    expanded_claims = set(llm_claims_covered)

    # 1. Include ALL claims from articles with >= 60% coverage
    for aid, cov_val in article_coverage.items():
        cov = cov_val if isinstance(cov_val, (int, float)) else 0
        if cov >= 0.6:
            expanded_claims.update(claims_by_article.get(aid, []))

    # 2. Include claims with high similarity (>= 0.78 KNOWN) to any covered claim
    similarities = ki.get("similarities", [])
    claims_lookup = ki.get("claims", {})
    for sim in similarities:
        if sim.get("score", 0) < 0.78:
            continue
        a_id, b_id = sim.get("a", ""), sim.get("b", "")
        # If one side is already covered, include the other (if it's in this cluster)
        if a_id in expanded_claims and b_id in all_cluster_claim_ids:
            expanded_claims.add(b_id)
        elif b_id in expanded_claims and a_id in all_cluster_claim_ids:
            expanded_claims.add(a_id)

    claims_covered = sorted(expanded_claims & all_cluster_claim_ids)

    if verbose:
        log(f"    Claim coverage: LLM tagged {len(llm_claims_covered)}, "
            f"expanded to {len(claims_covered)} "
            f"(+{len(claims_covered) - len(llm_claims_covered)} via coverage + similarity)")

    result = {
        "cluster_id": cluster_id,
        "label": cluster_label,
        "synthesis_markdown": synthesis_md,
        "article_ids": article_ids,
        "article_coverage": article_coverage,
        "claims_covered": claims_covered,
        "unique_per_article": unique_per_article,
        "follow_up_questions": follow_up_questions,
        "tensions": tensions,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_articles": len(article_ids),
        "total_claims_covered": len(claims_covered),
        "total_claims_in_cluster": total_claims_in_cluster,
    }

    log(f"    OK: {len(synthesis_md)} chars, "
        f"{len(claims_covered)}/{total_claims_in_cluster} claims covered, "
        f"{len(follow_up_questions)} questions, {len(tensions)} tensions")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Generate structured syntheses from concept clusters"
    )
    parser.add_argument("--all", action="store_true",
                        help="Generate syntheses for all eligible clusters")
    parser.add_argument("--cluster", type=str, default=None,
                        help="Generate for cluster matching this label (substring match)")
    parser.add_argument("--cluster-id", type=int, default=None,
                        help="Generate for cluster with this numeric ID")
    parser.add_argument("--min-articles", type=int, default=2,
                        help="Minimum articles per cluster (default: 2)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be generated without calling LLM")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show detailed output")
    parser.add_argument("--force", action="store_true",
                        help="Regenerate even if cluster hasn't changed")
    args = parser.parse_args()

    if not args.all and args.cluster is None and args.cluster_id is None:
        parser.error("Specify --all, --cluster LABEL, or --cluster-id N")

    log("=== Petrarca Synthesis Generator ===")
    log("")

    # Load data
    log("Loading data...")
    articles, ki, clusters_data = load_data()
    article_map = {a["id"]: a for a in articles}
    all_clusters = clusters_data.get("clusters", [])
    log(f"  {len(articles)} articles, {len(all_clusters)} clusters")

    # Load existing syntheses for incremental mode
    existing = load_existing_syntheses()
    log(f"  {len(existing)} existing syntheses loaded")

    # Filter clusters
    targets = []
    for cluster in all_clusters:
        size = cluster["size"]
        label = cluster["label"]
        cid = cluster.get("cluster_id", 0)

        if size < args.min_articles:
            continue

        # Check if cluster content is too thin
        word_count = estimate_cluster_word_count(cluster, article_map)
        if word_count < MIN_TOTAL_WORDS:
            if args.verbose:
                log(f"  Skipping {label}: only {word_count} total words")
            continue

        if args.cluster is not None:
            if args.cluster.lower() not in label.lower():
                continue

        if args.cluster_id is not None:
            if cid != args.cluster_id:
                continue

        # Check if regeneration needed (unless --force)
        cid_key = f"cluster_{cid}"
        if not args.force and cid_key in existing:
            if not cluster_has_changed(cluster, existing[cid_key]):
                if args.verbose:
                    log(f"  Skipping {label}: unchanged since last generation")
                continue

        targets.append(cluster)

    if not targets:
        log("No clusters to synthesize.")
        if args.cluster:
            log(f"  No cluster matched '{args.cluster}'. Available labels:")
            for c in all_clusters:
                log(f"    #{c.get('cluster_id', '?')} [{c['size']}] {c['label']}")
        sys.exit(0)

    log(f"\nTargets: {len(targets)} clusters")
    for c in targets:
        word_count = estimate_cluster_word_count(c, article_map)
        log(f"  #{c.get('cluster_id', '?')} [{c['size']} articles, {word_count} words] {c['label']}")

    if args.dry_run:
        log("\n[dry-run] Would generate syntheses for the above clusters.")
        for c in targets:
            log(f"\n  --- {c['label']} ---")
            for entry in c["articles"]:
                art = article_map.get(entry["id"], {})
                log(f"    {art.get('title', entry['id'])} "
                    f"({art.get('word_count', 0)} words, "
                    f"{len(art.get('atomic_claims', []))} claims, "
                    f"core={entry.get('is_core', False)})")
            log(f"    Key shared claims: {len(c.get('key_shared_claims', []))}")
            log(f"    Unique claims: {c.get('total_unique_claims', 0)}")
            log(f"    Shared claims: {c.get('total_shared_claims', 0)}")
        sys.exit(0)

    # Generate syntheses
    new_syntheses = []
    for cluster in targets:
        result = generate_one_synthesis(cluster, article_map, ki, verbose=args.verbose)
        if result:
            new_syntheses.append(result)

    if not new_syntheses:
        log("\nNo syntheses were generated.")
        sys.exit(1)

    # Merge with existing: new results overwrite by cluster_id
    merged = dict(existing)
    for s in new_syntheses:
        merged[s["cluster_id"]] = s

    # Build output
    all_syntheses = sorted(merged.values(), key=lambda s: -s.get("total_articles", 0))

    output = {
        "version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "total_syntheses": len(all_syntheses),
            "total_articles_covered": len(set(
                aid for s in all_syntheses for aid in s.get("article_ids", [])
            )),
            "total_claims_covered": sum(
                s.get("total_claims_covered", 0) for s in all_syntheses
            ),
        },
        "syntheses": all_syntheses,
    }

    SYNTHESES_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    file_size = SYNTHESES_PATH.stat().st_size
    log(f"\n{len(new_syntheses)} new syntheses generated, "
        f"{len(all_syntheses)} total in {SYNTHESES_PATH}")
    log(f"  File size: {file_size:,} bytes ({file_size / 1024:.1f} KB)")

    # Print summary
    print(f"\n{'='*60}")
    print(f"  Synthesis Generation Complete")
    print(f"{'='*60}")
    for s in new_syntheses:
        coverage_vals = list(s.get("article_coverage", {}).values())
        avg_coverage = sum(coverage_vals) / len(coverage_vals) if coverage_vals else 0
        print(f"\n  {s['label']}")
        print(f"    Articles: {s['total_articles']}")
        print(f"    Claims covered: {s['total_claims_covered']}/{s['total_claims_in_cluster']}")
        print(f"    Avg coverage: {avg_coverage:.0%}")
        print(f"    Follow-up questions: {len(s.get('follow_up_questions', []))}")
        print(f"    Tensions: {len(s.get('tensions', []))}")
        print(f"    Synthesis length: {len(s.get('synthesis_markdown', ''))} chars")

        if args.verbose:
            print(f"\n    --- Synthesis Preview ---")
            md = s.get("synthesis_markdown", "")
            # Show first 800 chars
            preview = md[:800]
            if len(md) > 800:
                preview += "\n    [...truncated...]"
            for line in preview.split("\n"):
                print(f"    {line}")

            print(f"\n    --- Article Coverage ---")
            for aid, cov in s.get("article_coverage", {}).items():
                title = article_map.get(aid, {}).get("title", aid[:12])
                print(f"      {cov:.0%} — {title[:60]}")

            print(f"\n    --- Follow-up Questions ---")
            for q in s.get("follow_up_questions", []):
                print(f"      Q: {q.get('question', '')}")
                print(f"         Search: {q.get('research_prompt', '')}")

            print(f"\n    --- Tensions ---")
            for t in s.get("tensions", []):
                if isinstance(t, dict):
                    print(f"      - {t.get('label', '')}: {t.get('description', '')}")
                else:
                    print(f"      - {t}")


if __name__ == "__main__":
    main()
