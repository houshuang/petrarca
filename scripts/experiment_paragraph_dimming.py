#!/usr/bin/env python3
"""Experiment: Paragraph-level dimming with combined scoring.

Tests the reader UI experience: given the user's knowledge state,
which paragraphs should be dimmed (familiar), highlighted (novel),
or marked as bridging (extends)?

Also generates a visual HTML preview of what the reader would look like.

Usage:
    python3 scripts/experiment_paragraph_dimming.py
    python3 scripts/experiment_paragraph_dimming.py --article 15  # specific article index
"""

import json
import sys
import math
import argparse
from pathlib import Path
from collections import defaultdict

import numpy as np

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
ARTICLES_PATH = DATA_DIR / "articles.json"


def load_data():
    with open(ARTICLES_PATH) as f:
        articles = json.load(f)

    claims = []
    claim_to_idx = {}
    for article in articles:
        for claim in article.get("atomic_claims", []):
            idx = len(claims)
            claim_to_idx[claim["id"]] = idx
            claims.append({**claim, "article_id": article.get("id", ""),
                           "article_title": article.get("title", "")})

    data = np.load(DATA_DIR / "claim_embeddings_nomic.npz")
    embeddings = data["embeddings"]
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1
    similarity = (embeddings / norms) @ (embeddings / norms).T

    return articles, claims, claim_to_idx, similarity


def classify_claim(claim_idx, known_ids, claim_to_idx, similarity):
    """Simple cosine classification (no NLI for speed)."""
    max_sim = 0.0
    for kid in known_ids:
        kidx = claim_to_idx.get(kid)
        if kidx is not None:
            sim = float(similarity[claim_idx, kidx])
            if sim > max_sim:
                max_sim = sim

    if max_sim >= 0.78:
        return "KNOWN", max_sim
    elif max_sim >= 0.68:
        return "EXTENDS", max_sim
    else:
        return "NEW", max_sim


def compute_paragraph_dimming(article, claims, claim_to_idx, known_ids, similarity):
    """Compute per-paragraph novelty and opacity."""
    content = article.get("content_markdown", "")
    if not content:
        return []

    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    article_claims = [c for c in claims if c["article_id"] == article.get("id", "")]

    # Build paragraph → claims mapping
    para_claims = defaultdict(list)
    for claim in article_claims:
        for pi in claim.get("source_paragraphs", []):
            if 0 <= pi < len(paragraphs):
                para_claims[pi].append(claim)

    results = []
    for i, para in enumerate(paragraphs):
        p_claims = para_claims.get(i, [])

        if not p_claims:
            results.append({
                "index": i,
                "text": para,
                "novelty": "neutral",
                "opacity": 0.85,  # Slight dim for unmapped paragraphs
                "claims": [],
            })
            continue

        classifications = []
        claim_details = []
        for claim in p_claims:
            idx = claim_to_idx.get(claim["id"])
            if idx is None:
                continue
            cls, sim = classify_claim(idx, known_ids, claim_to_idx, similarity)
            classifications.append(cls)
            claim_details.append({
                "text": claim["normalized_text"][:100],
                "type": claim["claim_type"],
                "classification": cls,
                "similarity": round(sim, 3),
            })

        new_count = classifications.count("NEW")
        extends_count = classifications.count("EXTENDS")
        known_count = classifications.count("KNOWN")
        total = len(classifications)

        if total == 0:
            novelty = "neutral"
            opacity = 0.85
        elif known_count == total:
            novelty = "familiar"
            opacity = 0.55
        elif new_count == total:
            novelty = "novel"
            opacity = 1.0
        elif new_count + extends_count >= total * 0.7:
            novelty = "mostly_novel"
            opacity = 0.95
        elif known_count >= total * 0.7:
            novelty = "mostly_familiar"
            opacity = 0.60
        else:
            novelty = "mixed"
            opacity = 0.55 + 0.45 * ((new_count + extends_count * 0.5) / total)

        results.append({
            "index": i,
            "text": para,
            "novelty": novelty,
            "opacity": round(opacity, 2),
            "claims": claim_details,
            "counts": {"new": new_count, "extends": extends_count, "known": known_count},
        })

    return results


def generate_reader_preview(article, paragraphs, article_stats):
    """Generate an HTML preview of what the reader would look like."""
    title = article.get("title", "Untitled")

    # Calculate article-level stats
    total_new = sum(p.get("counts", {}).get("new", 0) for p in paragraphs)
    total_ext = sum(p.get("counts", {}).get("extends", 0) for p in paragraphs)
    total_known = sum(p.get("counts", {}).get("known", 0) for p in paragraphs)
    total = total_new + total_ext + total_known
    novelty_pct = round((total_new + total_ext) / total * 100) if total > 0 else 0

    # Novelty badge
    if novelty_pct >= 80:
        badge_text = "Mostly new"
        badge_color = "#2a7a4a"
    elif novelty_pct >= 50:
        badge_text = f"{novelty_pct}% new"
        badge_color = "#c9a84c"
    elif novelty_pct >= 20:
        badge_text = "Partly familiar"
        badge_color = "#b0a898"
    else:
        badge_text = "Mostly review"
        badge_color = "#d0ccc0"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Reader Preview — {title}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600&family=Crimson+Pro:wght@400;500&family=DM+Sans:wght@400;500&family=EB+Garamond:ital,wght@0,400;0,500;1,400&display=swap');

:root {{
  --parchment: #f7f4ec;
  --ink: #2a2420;
  --rubric: #8b2500;
  --claimNew: #2a7a4a;
  --claimKnown: #d0ccc0;
  --gold: #c9a84c;
  --rule: #e4dfd4;
}}

* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: 'Crimson Pro', Georgia, serif; max-width: 680px; margin: 0 auto; padding: 40px 16px 80px; background: var(--parchment); color: var(--ink); }}
h1 {{ font-family: 'Cormorant Garamond', serif; font-weight: 600; font-size: 28px; margin-bottom: 8px; }}
.double-rule {{ border-top: 2px solid var(--ink); margin-top: 8px; padding-top: 5px; border-bottom: 1px solid var(--ink); height: 0; margin-bottom: 24px; }}
.meta {{ font-family: 'DM Sans', sans-serif; font-size: 12px; color: #6a6458; }}
.badge {{ display: inline-block; padding: 2px 10px; border-radius: 12px; font-family: 'DM Sans', sans-serif; font-size: 11px; color: white; margin-bottom: 12px; }}

.paragraph {{ padding: 12px 16px; margin: 4px 0; border-radius: 4px; transition: opacity 0.3s; position: relative; font-size: 17px; line-height: 1.7; }}
.paragraph.novel {{ background: rgba(42, 122, 74, 0.04); border-left: 3px solid var(--claimNew); }}
.paragraph.mostly_novel {{ background: rgba(42, 122, 74, 0.02); border-left: 2px solid var(--claimNew); }}
.paragraph.extends {{ background: rgba(201, 168, 76, 0.04); border-left: 2px solid var(--gold); }}
.paragraph.mixed {{ border-left: 2px solid var(--gold); }}
.paragraph.familiar {{ border-left: 2px solid var(--claimKnown); }}
.paragraph.mostly_familiar {{ border-left: 2px solid var(--claimKnown); }}
.paragraph.neutral {{ border-left: 1px solid var(--rule); }}

.claim-indicators {{ position: absolute; right: 8px; top: 8px; display: flex; gap: 3px; }}
.claim-dot {{ width: 6px; height: 6px; border-radius: 50%; }}
.claim-dot.new {{ background: var(--claimNew); }}
.claim-dot.extends {{ background: var(--gold); }}
.claim-dot.known {{ background: var(--claimKnown); }}

.claim-popup {{ display: none; position: absolute; right: 0; top: 24px; background: white; border: 1px solid var(--rule); border-radius: 4px; padding: 8px 12px; width: 280px; z-index: 10; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
.claim-popup.visible {{ display: block; }}
.claim-item {{ font-size: 12px; padding: 4px 0; border-bottom: 1px solid var(--rule); }}
.claim-item:last-child {{ border-bottom: none; }}
.claim-item .label {{ font-family: 'DM Sans', sans-serif; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; }}

.minimap {{ position: fixed; right: 20px; top: 50%; transform: translateY(-50%); width: 12px; height: 300px; background: rgba(0,0,0,0.05); border-radius: 6px; overflow: hidden; }}
.minimap-segment {{ width: 100%; }}

.stats {{ display: flex; gap: 16px; margin: 16px 0; padding: 12px; background: rgba(0,0,0,0.02); border-radius: 4px; }}
.stat {{ text-align: center; flex: 1; }}
.stat-value {{ font-family: 'Cormorant Garamond', serif; font-size: 24px; font-weight: 600; }}
.stat-label {{ font-family: 'DM Sans', sans-serif; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; color: #6a6458; }}
</style>
</head>
<body>

<h1>{title}</h1>
<span class="badge" style="background:{badge_color}">{badge_text}</span>
<div class="double-rule"></div>

<div class="stats">
  <div class="stat"><div class="stat-value" style="color:var(--claimNew)">{total_new}</div><div class="stat-label">New</div></div>
  <div class="stat"><div class="stat-value" style="color:var(--gold)">{total_ext}</div><div class="stat-label">Extends</div></div>
  <div class="stat"><div class="stat-value" style="color:var(--claimKnown)">{total_known}</div><div class="stat-label">Known</div></div>
</div>
"""

    # Minimap
    html += '<div class="minimap">\n'
    total_paras = len(paragraphs)
    for p in paragraphs:
        h = max(2, 300 / max(total_paras, 1))
        novelty = p.get("novelty", "neutral")
        color_map = {
            "novel": "var(--claimNew)",
            "mostly_novel": "var(--claimNew)",
            "mixed": "var(--gold)",
            "extends": "var(--gold)",
            "mostly_familiar": "var(--claimKnown)",
            "familiar": "var(--claimKnown)",
            "neutral": "rgba(0,0,0,0.05)",
        }
        color = color_map.get(novelty, "rgba(0,0,0,0.05)")
        html += f'<div class="minimap-segment" style="height:{h}px;background:{color}"></div>\n'
    html += '</div>\n'

    # Paragraphs
    for p in paragraphs:
        opacity = p["opacity"]
        novelty = p["novelty"]
        css_class = novelty if novelty in ("novel", "mostly_novel", "familiar", "mostly_familiar", "mixed", "neutral") else "neutral"

        text = p["text"]
        # Handle markdown headers
        if text.startswith("#"):
            level = len(text.split()[0])
            text_content = text.lstrip("# ")
            if level <= 2:
                html += f'<h2 style="opacity:{opacity}">{text_content}</h2>\n'
                continue
            else:
                html += f'<h3 style="opacity:{opacity}">{text_content}</h3>\n'
                continue

        html += f'<div class="paragraph {css_class}" style="opacity:{opacity}">\n'

        # Claim indicator dots
        if p.get("claims"):
            html += '<div class="claim-indicators">\n'
            for claim in p["claims"]:
                dot_class = claim["classification"].lower()
                html += f'<div class="claim-dot {dot_class}" title="{claim["text"][:60]}"></div>\n'
            html += '</div>\n'

        html += f'{text}\n</div>\n'

    html += """
<script>
// Click on claim dots to show popup
document.querySelectorAll('.claim-indicators').forEach(el => {
  el.style.cursor = 'pointer';
  el.addEventListener('click', e => {
    const popup = el.parentElement.querySelector('.claim-popup');
    if (popup) popup.classList.toggle('visible');
  });
});
</script>
</body></html>"""

    return html


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--article", type=int, default=None, help="Article index to preview")
    parser.add_argument("--read-first", type=int, default=10, help="How many articles to read first")
    args = parser.parse_args()

    print("Loading data...", file=sys.stderr)
    articles, claims, claim_to_idx, similarity = load_data()
    print(f"  {len(articles)} articles, {len(claims)} claims", file=sys.stderr)

    # Build knowledge from first N articles
    known_ids = set()
    for article in articles[:args.read_first]:
        for claim in article.get("atomic_claims", []):
            known_ids.add(claim["id"])
    print(f"  Read {args.read_first} articles, know {len(known_ids)} claims", file=sys.stderr)

    # Pick target article
    if args.article is not None:
        target_idx = args.article
    else:
        # Find the most interesting unread article (highest EXTENDS ratio)
        best_idx = args.read_first
        best_extends = 0
        for i in range(args.read_first, len(articles)):
            a = articles[i]
            a_claims = [c for c in claims if c["article_id"] == a.get("id", "")]
            extends = 0
            for c in a_claims:
                idx = claim_to_idx.get(c["id"])
                if idx is not None:
                    cls, _ = classify_claim(idx, known_ids, claim_to_idx, similarity)
                    if cls == "EXTENDS":
                        extends += 1
            if extends > best_extends:
                best_extends = extends
                best_idx = i
        target_idx = best_idx

    target = articles[target_idx]
    print(f"  Target: [{target_idx}] {target.get('title', '')[:60]}", file=sys.stderr)

    # Compute paragraph dimming
    paragraphs = compute_paragraph_dimming(target, claims, claim_to_idx, known_ids, similarity)

    # Stats
    novelties = [p["novelty"] for p in paragraphs]
    print(f"\n  Paragraph dimming results:")
    print(f"    Total paragraphs: {len(paragraphs)}")
    for novelty in ["novel", "mostly_novel", "mixed", "mostly_familiar", "familiar", "neutral"]:
        count = novelties.count(novelty)
        if count > 0:
            print(f"    {novelty}: {count}")

    opacities = [p["opacity"] for p in paragraphs]
    print(f"    Opacity range: {min(opacities):.2f} - {max(opacities):.2f}")
    print(f"    Mean opacity: {np.mean(opacities):.2f}")

    # Generate HTML preview
    html = generate_reader_preview(target, paragraphs, {})
    output_path = DATA_DIR / "reader_preview.html"
    with open(output_path, "w") as f:
        f.write(html)
    print(f"\n  Reader preview: {output_path}", file=sys.stderr)

    # Also generate previews for a few more articles
    for i in [args.read_first, args.read_first + 5, args.read_first + 10]:
        if i >= len(articles):
            break
        a = articles[i]
        paras = compute_paragraph_dimming(a, claims, claim_to_idx, known_ids, similarity)
        html = generate_reader_preview(a, paras, {})
        path = DATA_DIR / f"reader_preview_{i}.html"
        with open(path, "w") as f:
            f.write(html)
        print(f"  Preview [{i}]: {path}", file=sys.stderr)

    # Save raw data
    output = {
        "article_index": target_idx,
        "article_title": target.get("title", ""),
        "articles_read": args.read_first,
        "known_claims": len(known_ids),
        "paragraphs": [{k: v for k, v in p.items() if k != "text"}
                        for p in paragraphs],
    }
    output_path = DATA_DIR / "experiment_paragraph_dimming.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"  Data: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
