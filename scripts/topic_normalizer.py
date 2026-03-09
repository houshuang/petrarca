"""
Topic normalization for Petrarca's interest_topics pipeline.

Ensures consistent topic hierarchies by:
1. Normalizing formatting (kebab-case, lowercase)
2. Matching against a canonical registry with include/exclude descriptions
3. Using LLM to decide merge-vs-create for unrecognized topics
4. Auto-updating the registry with verified new topics

Lessons from Otak's topic tree:
- Include/exclude descriptions are crucial for LLM disambiguation
- Unconstrained proliferation leads to 315 domains from 8 intended
- Cluster-first, name-later beats per-article generation
- Keep hierarchy shallow (broad → specific, max 2 levels)
"""

import json
import re
import sys
from pathlib import Path

REGISTRY_PATH = Path(__file__).parent / "topic_registry.json"


def load_registry() -> dict:
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text())
    return {"version": 1, "max_broad": 25, "max_specific_per_broad": 15, "broad": {}, "specific": {}}


def save_registry(registry: dict) -> None:
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n")


def to_slug(text: str) -> str:
    """Normalize to kebab-case slug: lowercase, hyphens, no special chars."""
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def normalize_entity(entity) -> str | None:
    """Clean entity value — filter out invalid 'none' strings."""
    if entity is None:
        return None
    if isinstance(entity, str):
        s = entity.strip()
        if s.lower() in ("none", "null", "n/a", ""):
            return None
        return s
    return None


def _format_registry_for_llm(registry: dict, level: str) -> str:
    """Format registry entries for LLM context."""
    entries = registry.get(level, {})
    lines = []
    for slug, info in sorted(entries.items()):
        parent = f" (under: {info['broad']})" if "broad" in info else ""
        lines.append(f'  "{slug}"{parent}')
        lines.append(f'    INCLUDES: {info.get("includes", "N/A")}')
        lines.append(f'    EXCLUDES: {info.get("excludes", "N/A")}')
    return "\n".join(lines)


def _llm_match_topic(
    new_slug: str,
    level: str,
    registry: dict,
    article_context: str,
    call_llm,
) -> dict:
    """Use LLM to decide whether a new topic matches an existing one or is genuinely new.

    Returns: {"action": "merge", "canonical": "existing-slug"}
          or {"action": "create", "slug": "new-slug", "includes": "...", "excludes": "...", "broad": "..."}
    """
    existing = _format_registry_for_llm(registry, level)

    if level == "broad":
        prompt = f"""A new broad topic category was generated: "{new_slug}"
Article context: {article_context}

Here are the existing canonical broad categories:
{existing}

Is this new topic:
A) The same as (or a subset of) an existing broad category? If so, which one?
B) A genuinely new broad category that should be added?

Return JSON:
If A: {{"action": "merge", "canonical": "existing-slug-name"}}
If B: {{"action": "create", "slug": "{new_slug}", "includes": "what this category covers", "excludes": "what does NOT belong here (and where it goes instead)"}}

Only choose B if the topic is genuinely distinct from ALL existing categories.
Return ONLY valid JSON."""
    else:
        # For specific topics, also provide broad context
        broad_entries = _format_registry_for_llm(registry, "broad")
        prompt = f"""A new specific topic was generated: "{new_slug}"
Article context: {article_context}

Existing broad categories:
{broad_entries}

Existing specific topics:
{existing}

Is this new specific topic:
A) The same as (or very similar to) an existing specific topic? If so, which one?
B) A genuinely new specific topic? If so, which broad category should it belong under?

Return JSON:
If A: {{"action": "merge", "canonical": "existing-slug-name"}}
If B: {{"action": "create", "slug": "{new_slug}", "broad": "parent-broad-slug", "includes": "what this topic covers", "excludes": "what does NOT belong here"}}

Only choose B if the topic is genuinely distinct from ALL existing specific topics.
Return ONLY valid JSON."""

    try:
        response = call_llm(prompt)
        if not response:
            return {"action": "create_fallback", "slug": new_slug}

        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned)
        result = json.loads(cleaned)

        if result.get("action") == "merge":
            canonical = to_slug(result.get("canonical", ""))
            if canonical and canonical in registry.get(level, {}):
                return {"action": "merge", "canonical": canonical}
            # LLM suggested a slug that doesn't exist — fall through to create
            print(f"    LLM suggested merge with '{canonical}' but it's not in registry, treating as new", file=sys.stderr)

        if result.get("action") == "create":
            return result

        return {"action": "create_fallback", "slug": new_slug}

    except (json.JSONDecodeError, Exception) as e:
        print(f"    LLM topic matching failed: {e}", file=sys.stderr)
        return {"action": "create_fallback", "slug": new_slug}


def normalize_article_topics(
    raw_topics: list[dict],
    registry: dict,
    article_title: str = "",
    call_llm=None,
) -> list[dict]:
    """Normalize interest_topics against the canonical registry.

    Args:
        raw_topics: List of {"broad": "...", "specific": "...", "entity": "..."} dicts
        registry: The canonical topic registry
        article_title: For LLM context when matching new topics
        call_llm: Function to call LLM (signature: call_llm(prompt, purpose=...) -> str)

    Returns:
        Normalized list of topic dicts with consistent slugs
    """
    normalized = []
    registry_updated = False

    for raw in raw_topics:
        broad_raw = raw.get("broad", "")
        specific_raw = raw.get("specific", "")
        entity_raw = raw.get("entity")

        if not broad_raw or not specific_raw:
            continue

        broad_slug = to_slug(broad_raw)
        specific_slug = to_slug(specific_raw)
        entity = normalize_entity(entity_raw)

        # --- Resolve broad ---
        if broad_slug not in registry.get("broad", {}):
            if call_llm:
                result = _llm_match_topic(
                    broad_slug, "broad", registry,
                    f"Article: {article_title}", call_llm,
                )
                if result["action"] == "merge":
                    broad_slug = result["canonical"]
                    print(f"    Broad '{to_slug(broad_raw)}' → merged to '{broad_slug}'", file=sys.stderr)
                else:
                    # Create new broad entry
                    new_entry = {
                        "includes": result.get("includes", ""),
                        "excludes": result.get("excludes", ""),
                    }
                    registry.setdefault("broad", {})[broad_slug] = new_entry
                    registry_updated = True
                    print(f"    Broad '{broad_slug}' → NEW canonical entry", file=sys.stderr)
            else:
                # No LLM available — add with empty descriptions
                registry.setdefault("broad", {})[broad_slug] = {"includes": "", "excludes": ""}
                registry_updated = True

        # --- Resolve specific ---
        if specific_slug not in registry.get("specific", {}):
            if call_llm:
                result = _llm_match_topic(
                    specific_slug, "specific", registry,
                    f"Article: {article_title}, Broad: {broad_slug}", call_llm,
                )
                if result["action"] == "merge":
                    specific_slug = result["canonical"]
                    # Use the canonical entry's broad parent
                    canonical_broad = registry["specific"][specific_slug].get("broad")
                    if canonical_broad:
                        broad_slug = canonical_broad
                    print(f"    Specific '{to_slug(specific_raw)}' → merged to '{specific_slug}'", file=sys.stderr)
                else:
                    # Create new specific entry
                    resolved_broad = result.get("broad", broad_slug)
                    if resolved_broad:
                        resolved_broad = to_slug(resolved_broad)
                    new_entry = {
                        "broad": resolved_broad or broad_slug,
                        "includes": result.get("includes", ""),
                        "excludes": result.get("excludes", ""),
                    }
                    registry.setdefault("specific", {})[specific_slug] = new_entry
                    registry_updated = True
                    print(f"    Specific '{specific_slug}' → NEW canonical entry (under {new_entry['broad']})", file=sys.stderr)
            else:
                registry.setdefault("specific", {})[specific_slug] = {
                    "broad": broad_slug, "includes": "", "excludes": "",
                }
                registry_updated = True
        else:
            # Existing specific — enforce its canonical broad parent
            canonical_broad = registry["specific"][specific_slug].get("broad")
            if canonical_broad and canonical_broad != broad_slug:
                print(f"    Correcting broad: '{broad_slug}' → '{canonical_broad}' (canonical parent of '{specific_slug}')", file=sys.stderr)
                broad_slug = canonical_broad

        normalized.append({
            "broad": broad_slug,
            "specific": specific_slug,
            **({"entity": entity} if entity else {}),
        })

    if registry_updated:
        _enforce_limits(registry)

    return normalized


def _enforce_limits(registry: dict) -> None:
    """Warn (don't block) if registry exceeds configured limits."""
    max_broad = registry.get("max_broad", 25)
    max_specific = registry.get("max_specific_per_broad", 15)

    broad_count = len(registry.get("broad", {}))
    if broad_count > max_broad:
        print(f"    WARNING: {broad_count} broad categories exceeds limit of {max_broad}", file=sys.stderr)

    broad_specific_counts = {}
    for slug, info in registry.get("specific", {}).items():
        parent = info.get("broad", "unknown")
        broad_specific_counts[parent] = broad_specific_counts.get(parent, 0) + 1

    for broad, count in broad_specific_counts.items():
        if count > max_specific:
            print(f"    WARNING: '{broad}' has {count} specific topics (limit: {max_specific})", file=sys.stderr)


def registry_needs_defrag(registry: dict) -> bool:
    """Check if the registry exceeds configured limits and needs defragmentation."""
    max_broad = registry.get("max_broad", 25)
    max_specific = registry.get("max_specific_per_broad", 15)

    if len(registry.get("broad", {})) > max_broad:
        return True

    broad_counts = {}
    for info in registry.get("specific", {}).values():
        parent = info.get("broad", "unknown")
        broad_counts[parent] = broad_counts.get(parent, 0) + 1

    return any(count > max_specific for count in broad_counts.values())


def defragment_registry(
    registry: dict,
    articles: list[dict],
    call_llm=None,
    dry_run: bool = False,
) -> dict:
    """Consolidate overpopulated categories by merging similar topics via LLM.

    Returns a merge map: {old_slug: new_slug} for all applied merges.
    """
    if not call_llm:
        print("  Defrag requires LLM — skipping", file=sys.stderr)
        return {}

    max_broad = registry.get("max_broad", 25)
    max_specific = registry.get("max_specific_per_broad", 15)
    merge_map = {}  # old_slug -> new_slug

    # --- Phase 1: Consolidate specific topics within overpopulated broad categories ---
    broad_to_specifics = {}
    for slug, info in registry.get("specific", {}).items():
        parent = info.get("broad", "unknown")
        broad_to_specifics.setdefault(parent, []).append(slug)

    for broad, specifics in sorted(broad_to_specifics.items()):
        if len(specifics) <= max_specific:
            continue

        print(f"  Defrag: '{broad}' has {len(specifics)} specific topics (limit {max_specific}), asking LLM to consolidate...", file=sys.stderr)

        # Format the specific topics under this broad category
        topic_lines = []
        for s in sorted(specifics):
            info = registry["specific"][s]
            topic_lines.append(f'  "{s}": includes={info.get("includes", "?")}')

        merges_needed = len(specifics) - max_specific
        prompt = f"""This broad category "{broad}" has {len(specifics)} specific topics, {merges_needed} over the limit of {max_specific}.

Current specific topics:
{chr(10).join(topic_lines)}

Reduce to at most {max_specific} topics by merging the most similar/overlapping ones.
For each merge group, pick the best canonical slug and explain what the merged topic covers.

Return JSON:
{{
  "merges": [
    {{"canonical": "best-slug", "absorbs": ["slug-1", "slug-2"], "includes": "merged description of what this covers", "excludes": "what does NOT belong here"}}
  ],
  "keep": ["slug-that-stays-unchanged"]
}}

Rules:
- Every current topic must appear in exactly one merge group OR in the keep list
- The canonical slug should be the most general/descriptive of the group
- Prefer merging very specific topics into slightly broader ones
- Only merge topics that genuinely overlap in subject matter
- Keep clearly distinct topics separate — only merge when there's real overlap

Return ONLY valid JSON."""

        try:
            response = call_llm(prompt)
            if not response:
                continue

            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
                cleaned = re.sub(r"\n?```$", "", cleaned)
            result = json.loads(cleaned)

            for group in result.get("merges", []):
                canonical = to_slug(group.get("canonical", ""))
                absorbs = [to_slug(s) for s in group.get("absorbs", [])]
                if not canonical or not absorbs:
                    continue

                # Map absorbed topics to canonical
                for old_slug in absorbs:
                    if old_slug != canonical and old_slug in registry.get("specific", {}):
                        merge_map[old_slug] = canonical
                        print(f"    Merge: '{old_slug}' → '{canonical}'", file=sys.stderr)

                # Update or create the canonical entry
                if not dry_run:
                    registry.setdefault("specific", {})[canonical] = {
                        "broad": broad,
                        "includes": group.get("includes", ""),
                        "excludes": group.get("excludes", ""),
                    }

        except (json.JSONDecodeError, Exception) as e:
            print(f"    Defrag LLM call failed for '{broad}': {e}", file=sys.stderr)

    # --- Phase 2: Consolidate broad categories if over limit ---
    broad_count = len(registry.get("broad", {}))
    if broad_count > max_broad:
        print(f"  Defrag: {broad_count} broad categories (limit {max_broad}), asking LLM to consolidate...", file=sys.stderr)

        broad_lines = []
        for slug, info in sorted(registry.get("broad", {}).items()):
            n_specific = len(broad_to_specifics.get(slug, []))
            broad_lines.append(f'  "{slug}" ({n_specific} specifics): includes={info.get("includes", "?")}')

        # Only merge the minimum needed to get back to the limit
        merges_needed = broad_count - max_broad

        # Find small categories (few specific topics) — these are merge candidates
        small_broads = sorted(
            [(b, len(broad_to_specifics.get(b, []))) for b in registry.get("broad", {})],
            key=lambda x: x[1],
        )
        candidate_slugs = [b for b, n in small_broads if n <= 5]

        prompt = f"""There are {broad_count} broad categories, {merges_needed} over the limit of {max_broad}.

Current broad categories (with number of specific sub-topics):
{chr(10).join(broad_lines)}

Merge EXACTLY {merges_needed} of the smallest/most niche categories into larger related ones.
Prefer absorbing these small categories: {', '.join(candidate_slugs[:merges_needed * 2])}

IMPORTANT: Do NOT merge major distinct categories like "history", "literature", "artificial-intelligence", "politics" together.
Only merge categories that are truly redundant or too niche to stand alone.

Return JSON:
{{
  "merges": [
    {{"canonical": "larger-category-slug", "absorbs": ["small-niche-slug"], "includes": "merged description", "excludes": "what does NOT belong here"}}
  ]
}}

Rules:
- Return exactly {merges_needed} merge groups
- Each merge should absorb 1-2 small categories into an existing larger one
- The canonical slug should be the LARGER, more established category
- Keep all major distinct subject areas as separate categories

Return ONLY valid JSON."""

        try:
            response = call_llm(prompt)
            if not response:
                pass
            else:
                cleaned = response.strip()
                if cleaned.startswith("```"):
                    cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
                    cleaned = re.sub(r"\n?```$", "", cleaned)
                result = json.loads(cleaned)

                for group in result.get("merges", []):
                    canonical = to_slug(group.get("canonical", ""))
                    absorbs = [to_slug(s) for s in group.get("absorbs", [])]
                    if not canonical or not absorbs:
                        continue

                    for old_slug in absorbs:
                        if old_slug != canonical and old_slug in registry.get("broad", {}):
                            # Also need to remap specific topics that pointed to old broad
                            merge_map[f"broad:{old_slug}"] = canonical
                            print(f"    Merge broad: '{old_slug}' → '{canonical}'", file=sys.stderr)

                    if not dry_run:
                        registry.setdefault("broad", {})[canonical] = {
                            "includes": group.get("includes", ""),
                            "excludes": group.get("excludes", ""),
                        }

        except (json.JSONDecodeError, Exception) as e:
            print(f"    Defrag LLM call failed for broad categories: {e}", file=sys.stderr)

    if not merge_map:
        print("  Defrag: no merges needed", file=sys.stderr)
        return merge_map

    if dry_run:
        print(f"  Defrag (dry run): {len(merge_map)} merges would be applied", file=sys.stderr)
        return merge_map

    # --- Phase 3: Apply merge map ---

    # 3a: Remove absorbed entries from registry
    for old_slug, new_slug in merge_map.items():
        if old_slug.startswith("broad:"):
            old_broad = old_slug[6:]
            registry.get("broad", {}).pop(old_broad, None)
            # Reassign specific topics that belonged to the absorbed broad
            for spec_slug, spec_info in registry.get("specific", {}).items():
                if spec_info.get("broad") == old_broad:
                    spec_info["broad"] = new_slug
        else:
            registry.get("specific", {}).pop(old_slug, None)

    # 3b: Update articles
    articles_updated = 0
    for article in articles:
        topics = article.get("interest_topics", [])
        if not topics:
            continue
        changed = False
        new_topics = []
        for t in topics:
            broad = t.get("broad", "")
            specific = t.get("specific", "")

            # Check broad merge
            broad_key = f"broad:{broad}"
            if broad_key in merge_map:
                broad = merge_map[broad_key]
                changed = True

            # Check specific merge
            if specific in merge_map:
                specific = merge_map[specific]
                # Also adopt the canonical entry's broad parent
                canonical_info = registry.get("specific", {}).get(specific)
                if canonical_info and canonical_info.get("broad"):
                    broad = canonical_info["broad"]
                changed = True

            new_topics.append({
                "broad": broad,
                "specific": specific,
                **({"entity": t["entity"]} if t.get("entity") else {}),
            })

        if changed:
            article["interest_topics"] = new_topics
            articles_updated += 1

    print(f"  Defrag: {len(merge_map)} merges applied, {articles_updated} articles updated", file=sys.stderr)
    return merge_map


def run_normalization_pass(articles: list[dict], call_llm=None, dry_run: bool = False) -> list[dict]:
    """Normalize interest_topics across all articles.

    Used for batch normalization (e.g., with --normalize-topics flag).
    """
    registry = load_registry()
    changes = 0

    for article in articles:
        raw_topics = article.get("interest_topics", [])
        if not raw_topics:
            continue

        normalized = normalize_article_topics(
            raw_topics, registry,
            article_title=article.get("title", ""),
            call_llm=call_llm,
        )

        if normalized != raw_topics:
            changes += 1
            if not dry_run:
                article["interest_topics"] = normalized

    if not dry_run:
        save_registry(registry)

    print(f"  Topic normalization: {changes} articles updated", file=sys.stderr)
    return articles
