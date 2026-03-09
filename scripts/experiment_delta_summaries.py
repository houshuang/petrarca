#!/usr/bin/env python3
"""Experiment: Generate natural-language delta report summaries.

Instead of raw claim lists, generate human-readable summaries like:
"Since you last read about AI agents, 3 new articles have appeared.
The main new insights are: [claim clusters]. You already know about [X]
but [article Y] adds detail on [Z]."

Uses Gemini Flash to synthesize claim lists into readable reports.

Usage:
    python3 scripts/experiment_delta_summaries.py
    python3 scripts/experiment_delta_summaries.py --topic claude-code
"""

import json
import os
import sys
import argparse
from pathlib import Path
from collections import defaultdict

import numpy as np

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
ARTICLES_PATH = DATA_DIR / "articles.json"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_KEY", "")


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


def classify_claims_for_topic(topic, claims, claim_to_idx, known_ids, similarity):
    """Classify all claims in a topic as NEW, EXTENDS, or KNOWN."""
    topic_claims = [c for c in claims if topic in c.get("topics", [])]

    new_claims = []
    extends_claims = []
    known_claims = []

    for claim in topic_claims:
        idx = claim_to_idx.get(claim["id"])
        if idx is None:
            continue

        if claim["id"] in known_ids:
            known_claims.append(claim)
            continue

        max_sim = 0.0
        best_known = None
        for kid in known_ids:
            kidx = claim_to_idx.get(kid)
            if kidx is not None:
                sim = float(similarity[idx, kidx])
                if sim > max_sim:
                    max_sim = sim
                    best_known = kid

        if max_sim >= 0.78:
            known_claims.append(claim)
        elif max_sim >= 0.68:
            extends_claims.append({
                **claim,
                "similarity": round(max_sim, 3),
                "extends": claims[claim_to_idx[best_known]]["normalized_text"][:100] if best_known and best_known in claim_to_idx else "",
            })
        else:
            new_claims.append(claim)

    return new_claims, extends_claims, known_claims


def generate_delta_summary(topic, new_claims, extends_claims, known_claims):
    """Use Gemini to generate a natural-language delta summary."""
    import litellm

    total = len(new_claims) + len(extends_claims) + len(known_claims)
    coverage = round(len(known_claims) / total * 100) if total > 0 else 0

    # Group new claims by article
    new_by_article = defaultdict(list)
    for c in new_claims:
        new_by_article[c["article_title"][:50]].append(c["normalized_text"])

    prompt = f"""You are generating a knowledge delta report for a reader who tracks what they know.

TOPIC: {topic}
TOTAL CLAIMS: {total}
COVERAGE: {coverage}% (claims already known)

NEW CLAIMS (things the reader hasn't seen):
{json.dumps([c['normalized_text'] for c in new_claims[:15]], indent=2)}

EXTENDS KNOWN (elaborations on things they already know):
{json.dumps([{'claim': c['normalized_text'], 'extends': c.get('extends', '')} for c in extends_claims[:10]], indent=2)}

ARTICLES WITH NEW CONTENT:
{json.dumps({k: len(v) for k, v in new_by_article.items()}, indent=2)}

Write a brief, engaging delta report (3-5 sentences). Style: scholarly but accessible. Format:
1. Opening: state what fraction is new vs known
2. Highlight 2-3 most interesting new insights (specific, not vague)
3. Note what extends existing knowledge
4. Suggest which article to read first and why

Do NOT use bullet points. Write flowing prose. Be specific about the content, not just meta-commentary."""

    try:
        resp = litellm.completion(
            model="gemini/gemini-2.0-flash",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.3,
            api_key=GEMINI_API_KEY,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Error generating summary: {e}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", type=str, default=None, help="Specific topic to report on")
    parser.add_argument("--read-first", type=int, default=10, help="Articles read first")
    parser.add_argument("--top-n", type=int, default=5, help="Number of topics to report on")
    args = parser.parse_args()

    if not GEMINI_API_KEY:
        print("Error: GEMINI_KEY or GEMINI_API_KEY required", file=sys.stderr)
        sys.exit(1)

    print("Loading data...", file=sys.stderr)
    articles, claims, claim_to_idx, similarity = load_data()
    print(f"  {len(articles)} articles, {len(claims)} claims", file=sys.stderr)

    # Build knowledge from first N articles
    known_ids = set()
    for article in articles[:args.read_first]:
        for claim in article.get("atomic_claims", []):
            known_ids.add(claim["id"])
    print(f"  Read {args.read_first} articles, know {len(known_ids)} claims", file=sys.stderr)

    # Find topics to report on
    if args.topic:
        topics = [args.topic]
    else:
        # Find topics with most new content
        topic_counts = defaultdict(lambda: {"new": 0, "extends": 0, "known": 0})
        for claim in claims:
            idx = claim_to_idx.get(claim["id"])
            if idx is None:
                continue
            for topic in claim.get("topics", []):
                if claim["id"] in known_ids:
                    topic_counts[topic]["known"] += 1
                else:
                    max_sim = 0.0
                    for kid in known_ids:
                        kidx = claim_to_idx.get(kid)
                        if kidx is not None:
                            sim = float(similarity[idx, kidx])
                            if sim > max_sim:
                                max_sim = sim
                    if max_sim >= 0.78:
                        topic_counts[topic]["known"] += 1
                    elif max_sim >= 0.68:
                        topic_counts[topic]["extends"] += 1
                    else:
                        topic_counts[topic]["new"] += 1

        # Pick topics with most new content
        topics = sorted(topic_counts.keys(),
                       key=lambda t: topic_counts[t]["new"] + topic_counts[t]["extends"],
                       reverse=True)[:args.top_n]

    reports = []
    for topic in topics:
        print(f"\n  Generating delta for: {topic}", file=sys.stderr)
        new_claims, extends_claims, known_claims = classify_claims_for_topic(
            topic, claims, claim_to_idx, known_ids, similarity
        )

        total = len(new_claims) + len(extends_claims) + len(known_claims)
        if total == 0:
            continue

        summary = generate_delta_summary(topic, new_claims, extends_claims, known_claims)

        report = {
            "topic": topic,
            "total_claims": total,
            "new": len(new_claims),
            "extends": len(extends_claims),
            "known": len(known_claims),
            "coverage_pct": round(len(known_claims) / total * 100, 1),
            "summary": summary,
            "new_articles": list(set(c["article_title"][:50] for c in new_claims)),
        }
        reports.append(report)

        print(f"\n{'─'*60}")
        print(f"  ✦ {topic.upper()}")
        print(f"    {len(new_claims)} new · {len(extends_claims)} extends · "
              f"{len(known_claims)} known ({report['coverage_pct']}% covered)")
        print(f"{'─'*60}")
        print(f"\n  {summary}\n")

    # Generate HTML report
    html = generate_html_delta_report(reports)
    output_path = DATA_DIR / "delta_summaries.html"
    with open(output_path, "w") as f:
        f.write(html)
    print(f"\n  HTML report: {output_path}", file=sys.stderr)

    # Save raw data
    output_path = DATA_DIR / "experiment_delta_summaries.json"
    with open(output_path, "w") as f:
        json.dump(reports, f, indent=2)
    print(f"  Data: {output_path}", file=sys.stderr)


def generate_html_delta_report(reports):
    """Generate Annotated Folio styled delta report."""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Petrarca — Knowledge Delta Report</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600&family=Crimson+Pro:wght@400;500&family=DM+Sans:wght@400;500&family=EB+Garamond:ital,wght@0,400;0,500;1,400&display=swap');

:root {
  --parchment: #f7f4ec;
  --ink: #2a2420;
  --rubric: #8b2500;
  --claimNew: #2a7a4a;
  --claimKnown: #d0ccc0;
  --gold: #c9a84c;
  --rule: #e4dfd4;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Crimson Pro', Georgia, serif; max-width: 680px; margin: 0 auto; padding: 40px 16px 80px; background: var(--parchment); color: var(--ink); }
h1 { font-family: 'Cormorant Garamond', serif; font-weight: 600; font-size: 32px; }
.subtitle { font-family: 'DM Sans', sans-serif; font-size: 12px; color: #6a6458; letter-spacing: 1px; text-transform: uppercase; margin-top: 4px; }
.double-rule { border-top: 2px solid var(--ink); margin-top: 8px; padding-top: 5px; border-bottom: 1px solid var(--ink); height: 0; margin-bottom: 32px; }
h2 { font-family: 'EB Garamond', serif; text-transform: uppercase; letter-spacing: 2px; font-size: 14px; color: var(--rubric); margin: 32px 0 12px; }
h2::before { content: '✦ '; }

.delta-card { margin: 24px 0; padding: 20px; border: 1px solid var(--rule); border-radius: 4px; background: white; }
.delta-topic { font-family: 'EB Garamond', serif; font-style: italic; font-size: 20px; color: var(--rubric); margin-bottom: 8px; }
.delta-stats { font-family: 'DM Sans', sans-serif; font-size: 11px; color: #6a6458; margin-bottom: 12px; display: flex; gap: 12px; }
.delta-stat { display: flex; align-items: center; gap: 4px; }
.delta-dot { width: 8px; height: 8px; border-radius: 50%; }
.delta-summary { font-size: 16px; line-height: 1.7; color: #333; }
.delta-bar { display: flex; height: 6px; border-radius: 3px; overflow: hidden; margin: 8px 0 12px; }
.delta-bar-segment { height: 100%; }

.source-list { margin-top: 12px; padding-top: 8px; border-top: 1px solid var(--rule); }
.source-item { font-family: 'DM Sans', sans-serif; font-size: 11px; color: #6a6458; padding: 2px 0; }
.source-item::before { content: '→ '; color: var(--claimNew); }
</style>
</head>
<body>

<h1>Knowledge Delta</h1>
<p class="subtitle">What's new since your last reading session</p>
<div class="double-rule"></div>
"""

    for report in reports:
        total = report["total_claims"]
        new_pct = report["new"] / total * 100 if total else 0
        ext_pct = report["extends"] / total * 100 if total else 0
        known_pct = report["known"] / total * 100 if total else 0

        html += '<div class="delta-card">\n'
        html += f'<div class="delta-topic">{report["topic"]}</div>\n'

        html += '<div class="delta-stats">'
        html += f'<div class="delta-stat"><div class="delta-dot" style="background:var(--claimNew)"></div>{report["new"]} new</div>'
        html += f'<div class="delta-stat"><div class="delta-dot" style="background:var(--gold)"></div>{report["extends"]} extends</div>'
        html += f'<div class="delta-stat"><div class="delta-dot" style="background:var(--claimKnown)"></div>{report["known"]} known</div>'
        html += f'<div class="delta-stat">{report["coverage_pct"]}% covered</div>'
        html += '</div>\n'

        html += '<div class="delta-bar">'
        html += f'<div class="delta-bar-segment" style="width:{new_pct}%;background:var(--claimNew)"></div>'
        html += f'<div class="delta-bar-segment" style="width:{ext_pct}%;background:var(--gold)"></div>'
        html += f'<div class="delta-bar-segment" style="width:{known_pct}%;background:var(--claimKnown)"></div>'
        html += '</div>\n'

        html += f'<div class="delta-summary">{report["summary"]}</div>\n'

        if report.get("new_articles"):
            html += '<div class="source-list">\n'
            for article in report["new_articles"][:3]:
                html += f'<div class="source-item">{article}</div>\n'
            html += '</div>\n'

        html += '</div>\n'

    html += '</body></html>'
    return html


if __name__ == "__main__":
    main()
