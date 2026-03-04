#!/usr/bin/env python3
"""Add exploration_tier and exploration_order fields to articles based on exploration plans.

Reads exploration plan JSON files to get subtopic -> tier mapping,
then matches articles by source_url or parent_id to assign tiers.

Usage:
    python3 scripts/add_exploration_tiers.py
"""

import json
import sys
from pathlib import Path
from urllib.parse import unquote

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
ARTICLES_PATH = DATA_DIR / "articles.json"
EXPLORATIONS_DIR = DATA_DIR / "explorations"


def normalize_url(url: str) -> str:
    """Normalize URL for matching (decode percent-encoding, strip trailing slash)."""
    return unquote(url).rstrip("/").lower()


def load_exploration_plans() -> dict:
    """Load all exploration plans and build url -> (tier, order) mapping."""
    url_to_tier = {}

    if not EXPLORATIONS_DIR.exists():
        print(f"No explorations directory at {EXPLORATIONS_DIR}", file=sys.stderr)
        return url_to_tier

    for plan_path in EXPLORATIONS_DIR.glob("*.json"):
        print(f"Loading exploration plan: {plan_path.name}", file=sys.stderr)
        plan = json.loads(plan_path.read_text())

        for i, subtopic in enumerate(plan.get("subtopics", [])):
            tier = subtopic.get("reading_order", "deep")
            for url in subtopic.get("urls", []):
                url_to_tier[normalize_url(url)] = {
                    "tier": tier,
                    "subtopic_index": i,
                    "subtopic_name": subtopic.get("name", ""),
                }

    return url_to_tier


def main():
    articles = json.loads(ARTICLES_PATH.read_text())
    url_to_tier = load_exploration_plans()

    if not url_to_tier:
        print("No exploration plans found, nothing to do.", file=sys.stderr)
        return

    print(f"Loaded {len(url_to_tier)} URL -> tier mappings", file=sys.stderr)

    # First pass: match articles by source_url
    article_by_id = {a["id"]: a for a in articles}
    matched = 0
    parent_tiers = {}  # article_id -> tier info for parent articles

    for article in articles:
        if not article.get("exploration_tag"):
            continue

        source_url = normalize_url(article.get("source_url", ""))
        tier_info = url_to_tier.get(source_url)

        if tier_info:
            article["exploration_tier"] = tier_info["tier"]
            article["exploration_order"] = tier_info["subtopic_index"]
            parent_tiers[article["id"]] = tier_info
            matched += 1

    print(f"First pass (URL match): {matched} articles matched", file=sys.stderr)

    # Second pass: propagate tier from parent to children
    propagated = 0
    for article in articles:
        if article.get("exploration_tier"):
            continue
        if not article.get("exploration_tag"):
            continue

        parent_id = article.get("parent_id")
        if parent_id and parent_id in parent_tiers:
            tier_info = parent_tiers[parent_id]
            article["exploration_tier"] = tier_info["tier"]
            article["exploration_order"] = tier_info["subtopic_index"]
            propagated += 1

    print(f"Second pass (parent propagation): {propagated} articles matched", file=sys.stderr)

    # Third pass: any exploration articles still missing tier?
    # These are exploration articles whose source_url doesn't match any plan URL
    # Try matching by checking if the article's source_url is a subpage of a plan URL
    remaining = 0
    for article in articles:
        if article.get("exploration_tier"):
            continue
        if not article.get("exploration_tag"):
            continue
        remaining += 1
        print(f"  UNMATCHED: [{article['id']}] {article['title'][:60]} -> {article.get('source_url', 'N/A')}", file=sys.stderr)

    # Summary
    tier_counts = {"foundational": 0, "intermediate": 0, "deep": 0}
    for article in articles:
        tier = article.get("exploration_tier")
        if tier:
            tier_counts[tier] = tier_counts.get(tier, 0) + 1

    print(f"\nTier distribution:", file=sys.stderr)
    for tier, count in tier_counts.items():
        print(f"  {tier}: {count}", file=sys.stderr)
    print(f"  unmatched exploration: {remaining}", file=sys.stderr)

    # Write back
    ARTICLES_PATH.write_text(json.dumps(articles, indent=2, ensure_ascii=False) + "\n")
    print(f"\nUpdated {ARTICLES_PATH}", file=sys.stderr)

    # Also update app/data/articles.json if it exists
    app_articles = PROJECT_DIR / "app" / "data" / "articles.json"
    if app_articles.exists():
        app_articles.write_text(json.dumps(articles, indent=2, ensure_ascii=False) + "\n")
        print(f"Updated {app_articles}", file=sys.stderr)


if __name__ == "__main__":
    main()
