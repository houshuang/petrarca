#!/usr/bin/env python3
"""Simulate user reading journeys and test the knowledge tracking system.

This script simulates realistic reading patterns and evaluates:
1. Knowledge state tracking (claim ledger)
2. Delta report quality
3. Reader novelty marking accuracy
4. Knowledge growth curves

Usage:
    python3 scripts/simulate_reading.py                    # full simulation
    python3 scripts/simulate_reading.py --scenario tech    # tech-focused reading
    python3 scripts/simulate_reading.py --scenario broad   # broad diverse reading
    python3 scripts/simulate_reading.py --report           # generate HTML report
"""

import json
import sys
import argparse
import random
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, field, asdict

import numpy as np

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
ARTICLES_PATH = DATA_DIR / "articles.json"
EMBEDDINGS_PATH = DATA_DIR / "claim_embeddings_nomic.npz"  # Nomic is default (better separation, local, free)


@dataclass
class ClaimState:
    """Knowledge state for a single claim."""
    claim_id: str
    status: str = "unknown"  # unknown | encountered | absorbed
    source_article: str = ""
    encountered_at_step: int = -1
    confidence: float = 0.0


@dataclass
class KnowledgeLedger:
    """Track what the user knows."""
    states: dict = field(default_factory=dict)  # claim_id -> ClaimState
    step: int = 0

    def encounter(self, claim_id: str, article_id: str):
        if claim_id not in self.states:
            self.states[claim_id] = ClaimState(
                claim_id=claim_id,
                status="encountered",
                source_article=article_id,
                encountered_at_step=self.step,
                confidence=0.7,
            )
        else:
            # Reinforce
            self.states[claim_id].confidence = min(1.0, self.states[claim_id].confidence + 0.2)

    def absorb(self, claim_id: str):
        if claim_id in self.states:
            self.states[claim_id].status = "absorbed"
            self.states[claim_id].confidence = 1.0

    def is_known(self, claim_id: str) -> bool:
        return claim_id in self.states and self.states[claim_id].status in ("encountered", "absorbed")

    def known_count(self) -> int:
        return sum(1 for s in self.states.values() if s.status in ("encountered", "absorbed"))


def load_data():
    """Load articles, claims, and embeddings."""
    with open(ARTICLES_PATH) as f:
        articles = json.load(f)

    claims = []
    claim_to_idx = {}
    for article in articles:
        for claim in article.get("atomic_claims", []):
            idx = len(claims)
            claim_to_idx[claim["id"]] = idx
            claims.append({
                **claim,
                "article_id": article.get("id", ""),
                "article_title": article.get("title", ""),
            })

    data = np.load(EMBEDDINGS_PATH)
    embeddings = data["embeddings"]

    # Pre-compute normalized embeddings for cosine similarity
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normalized = embeddings / norms
    similarity = normalized @ normalized.T

    return articles, claims, claim_to_idx, similarity


def find_similar_known(claim_idx: int, ledger: KnowledgeLedger,
                       claim_to_idx: dict, similarity: np.ndarray,
                       threshold: float = 0.75) -> tuple[float, str | None]:
    """Find the most similar known claim. Returns (max_sim, known_claim_id)."""
    max_sim = 0.0
    best_id = None

    for known_id in ledger.states:
        if not ledger.is_known(known_id):
            continue
        known_idx = claim_to_idx.get(known_id)
        if known_idx is None:
            continue
        sim = float(similarity[claim_idx, known_idx])
        if sim > max_sim:
            max_sim = sim
            best_id = known_id

    return max_sim, best_id


def classify_claim(claim_idx: int, ledger: KnowledgeLedger,
                   claim_to_idx: dict, claims: list[dict],
                   similarity: np.ndarray) -> str:
    """Classify a claim as NEW, KNOWN, EXTENDS, or CONTRADICTS.

    Thresholds calibrated for Nomic-embed-text-v1.5 (768 dim). Nomic produces
    wider similarity distributions than Gemini embedding-001, with near-duplicates
    at ~0.93 vs 0.90. NLI experiment validated that cosine overestimates in the
    0.68-0.78 range — the LLM judge disagrees 25% of the time there.
    """
    claim_id = claims[claim_idx]["id"]

    # Direct hit
    if ledger.is_known(claim_id):
        return "KNOWN"

    max_sim, _ = find_similar_known(claim_idx, ledger, claim_to_idx, similarity)

    if max_sim >= 0.78:
        return "KNOWN"
    elif max_sim >= 0.68:
        return "EXTENDS"
    else:
        return "NEW"


def simulate_article_read(article: dict, claims: list[dict],
                          claim_to_idx: dict, ledger: KnowledgeLedger,
                          similarity: np.ndarray) -> dict:
    """Simulate reading a single article. Returns reading stats."""
    article_claims = [c for c in claims if c["article_id"] == article.get("id", "")]
    if not article_claims:
        return {"title": article.get("title", ""), "skipped": True}

    classifications = {"NEW": 0, "KNOWN": 0, "EXTENDS": 0}
    claim_details = []

    for claim in article_claims:
        idx = claim_to_idx.get(claim["id"])
        if idx is None:
            continue
        classification = classify_claim(idx, ledger, claim_to_idx, claims, similarity)
        classifications[classification] = classifications.get(classification, 0) + 1
        claim_details.append({
            "text": claim["normalized_text"][:80],
            "type": claim["claim_type"],
            "classification": classification,
        })

    total = sum(classifications.values())
    novelty_pct = ((classifications["NEW"] + classifications["EXTENDS"]) / total * 100) if total > 0 else 0

    # Update ledger — user now knows these claims
    for claim in article_claims:
        ledger.encounter(claim["id"], article.get("id", ""))

    ledger.step += 1

    return {
        "title": article.get("title", "")[:60],
        "total_claims": total,
        "classifications": classifications,
        "novelty_pct": round(novelty_pct, 1),
        "claim_details": claim_details,
    }


def generate_delta_report(topic: str, claims: list[dict],
                          claim_to_idx: dict, ledger: KnowledgeLedger,
                          similarity: np.ndarray) -> dict:
    """Generate a comprehensive delta report for a topic."""
    topic_claims = [c for c in claims if topic in c.get("topics", [])]
    if not topic_claims:
        return {"topic": topic, "error": "no claims"}

    sections = {
        "new": [],
        "extends": [],
        "known": [],
    }

    for claim in topic_claims:
        idx = claim_to_idx.get(claim["id"])
        if idx is None:
            continue

        classification = classify_claim(idx, ledger, claim_to_idx, claims, similarity)

        entry = {
            "text": claim["normalized_text"],
            "type": claim["claim_type"],
            "article": claim["article_title"][:50],
        }

        if classification == "NEW":
            sections["new"].append(entry)
        elif classification == "EXTENDS":
            max_sim, similar_id = find_similar_known(idx, ledger, claim_to_idx, similarity)
            entry["similarity"] = round(max_sim, 3)
            if similar_id and similar_id in claim_to_idx:
                entry["extends_claim"] = claims[claim_to_idx[similar_id]]["normalized_text"][:80]
            sections["extends"].append(entry)
        else:
            sections["known"].append(entry)

    # Group new claims by article
    by_article: dict[str, list] = defaultdict(list)
    for c in sections["new"]:
        by_article[c["article"]].append(c)

    return {
        "topic": topic,
        "total_claims": len(topic_claims),
        "new_count": len(sections["new"]),
        "extends_count": len(sections["extends"]),
        "known_count": len(sections["known"]),
        "new_by_article": {k: v for k, v in by_article.items()},
        "extends": sections["extends"][:10],
        "coverage_pct": round(len(sections["known"]) / len(topic_claims) * 100, 1) if topic_claims else 0,
    }


def simulate_paragraph_dimming(article: dict, claims: list[dict],
                               claim_to_idx: dict, ledger: KnowledgeLedger,
                               similarity: np.ndarray) -> list[dict]:
    """Simulate which paragraphs would be dimmed in the reader."""
    content = article.get("content_markdown", "")
    if not content:
        return []

    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    article_claims = [c for c in claims if c["article_id"] == article.get("id", "")]

    para_results = []
    for i, para in enumerate(paragraphs):
        # Find claims sourced from this paragraph
        para_claims = [c for c in article_claims
                       if i in c.get("source_paragraphs", [])]

        if not para_claims:
            # No claims mapped to this paragraph — treat as neutral
            para_results.append({
                "paragraph_index": i,
                "text_preview": para[:80],
                "novelty": "neutral",
                "opacity": 1.0,
                "claim_count": 0,
            })
            continue

        # Classify claims in this paragraph
        classifications = []
        for claim in para_claims:
            idx = claim_to_idx.get(claim["id"])
            if idx is not None:
                classifications.append(
                    classify_claim(idx, ledger, claim_to_idx, claims, similarity)
                )

        new_count = classifications.count("NEW")
        extends_count = classifications.count("EXTENDS")
        known_count = classifications.count("KNOWN")
        total = len(classifications)

        if total == 0:
            novelty = "neutral"
            opacity = 1.0
        elif known_count == total:
            novelty = "familiar"
            opacity = 0.55
        elif new_count == total:
            novelty = "novel"
            opacity = 1.0
        else:
            novelty = "mixed"
            opacity = 0.55 + 0.45 * ((new_count + extends_count * 0.5) / total)

        para_results.append({
            "paragraph_index": i,
            "text_preview": para[:80],
            "novelty": novelty,
            "opacity": round(opacity, 2),
            "claim_count": total,
            "new": new_count,
            "extends": extends_count,
            "known": known_count,
        })

    return para_results


def run_scenario(name: str, articles: list[dict], claims: list[dict],
                 claim_to_idx: dict, similarity: np.ndarray) -> dict:
    """Run a reading scenario and collect results."""
    ledger = KnowledgeLedger()

    # Define reading orders based on scenario
    if name == "tech":
        # Read Claude Code / AI agent articles in order
        order = [a for a in articles if any(
            t in (a.get("topics", []) + [tag for c in a.get("atomic_claims", []) for tag in c.get("topics", [])])
            for t in ["claude-code", "ai-agents", "coding-agents"]
        )]
    elif name == "broad":
        # Read diverse articles — mix of topics
        order = articles[:]
        random.seed(42)
        random.shuffle(order)
    elif name == "sequential":
        # Read in default order (how they appear in the feed)
        order = articles[:]
    else:
        order = articles[:]

    results = {
        "scenario": name,
        "article_count": len(order),
        "readings": [],
        "knowledge_growth": [],
        "novelty_curve": [],
        "delta_reports": [],
    }

    for i, article in enumerate(order[:15]):  # read up to 15 articles
        reading = simulate_article_read(article, claims, claim_to_idx, ledger, similarity)
        results["readings"].append(reading)
        results["knowledge_growth"].append(ledger.known_count())
        results["novelty_curve"].append(reading.get("novelty_pct", 0))

    # Generate delta reports for top topics after reading
    topic_counts = defaultdict(int)
    for claim in claims:
        for t in claim.get("topics", []):
            topic_counts[t] += 1
    top_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    for topic, _ in top_topics:
        delta = generate_delta_report(topic, claims, claim_to_idx, ledger, similarity)
        results["delta_reports"].append(delta)

    # Simulate paragraph dimming for the next unread article
    unread = [a for a in order[15:] if a.get("content_markdown")]
    if unread:
        dimming = simulate_paragraph_dimming(unread[0], claims, claim_to_idx, ledger, similarity)
        results["dimming_preview"] = {
            "article": unread[0].get("title", "")[:60],
            "paragraphs": dimming,
        }

    return results


def generate_html_report(results: list[dict]) -> str:
    """Generate an HTML report from simulation results."""
    html = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Petrarca Reading Simulation Report</title>
<style>
  body { font-family: 'Crimson Pro', Georgia, serif; max-width: 800px; margin: 40px auto; padding: 0 20px; background: #f7f4ec; color: #2a2420; }
  h1 { font-family: 'Cormorant Garamond', serif; color: #8b2500; font-weight: 600; }
  h2 { font-family: 'EB Garamond', serif; text-transform: uppercase; letter-spacing: 2px; font-size: 14px; color: #8b2500; margin-top: 40px; }
  h2::before { content: '✦ '; }
  .double-rule { border-top: 2px solid #2a2420; padding-top: 5px; border-bottom: 1px solid #2a2420; margin: 10px 0 20px; height: 0; }
  table { border-collapse: collapse; width: 100%; margin: 10px 0; }
  th { font-family: 'DM Sans', sans-serif; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; text-align: left; padding: 8px; border-bottom: 2px solid #e4dfd4; color: #6a6458; }
  td { padding: 8px; border-bottom: 1px solid #e4dfd4; font-size: 14px; }
  .bar { display: inline-block; height: 16px; border-radius: 2px; }
  .bar-new { background: #2a7a4a; }
  .bar-extends { background: #c9a84c; }
  .bar-known { background: #d0ccc0; }
  .novelty-pct { font-family: 'Cormorant Garamond', serif; font-size: 24px; font-weight: 600; }
  .claim-new { border-left: 2px solid #2a7a4a; padding-left: 12px; margin: 8px 0; }
  .claim-extends { border-left: 2px solid #c9a84c; padding-left: 12px; margin: 8px 0; }
  .claim-known { border-left: 2px solid #d0ccc0; padding-left: 12px; margin: 8px 0; opacity: 0.55; }
  .meta { font-family: 'DM Sans', sans-serif; font-size: 11px; color: #6a6458; }
  .dimming-preview { margin: 4px 0; padding: 8px 12px; border-radius: 4px; }
  .growth-chart { display: flex; align-items: flex-end; gap: 4px; height: 100px; margin: 10px 0; }
  .growth-bar { background: #8b2500; width: 40px; border-radius: 2px 2px 0 0; position: relative; }
  .growth-label { font-size: 10px; text-align: center; font-family: 'DM Sans', sans-serif; }
  @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600&family=Crimson+Pro&family=DM+Sans:wght@400;500&family=EB+Garamond:ital@0;1&display=swap');
</style>
</head>
<body>
<h1>Petrarca Reading Simulation</h1>
<div class="double-rule"></div>
"""

    for scenario in results:
        name = scenario["scenario"]
        readings = scenario["readings"]
        growth = scenario["knowledge_growth"]
        deltas = scenario.get("delta_reports", [])

        html += f'<h2>Scenario: {name}</h2>\n'

        # Reading journey table
        html += '<table>\n<tr><th>Article</th><th>Claims</th><th>Novelty</th><th>Distribution</th></tr>\n'
        for r in readings:
            if r.get("skipped"):
                continue
            c = r.get("classifications", {})
            total = r["total_claims"]
            new_w = int(c.get("NEW", 0) / max(total, 1) * 200)
            ext_w = int(c.get("EXTENDS", 0) / max(total, 1) * 200)
            kn_w = int(c.get("KNOWN", 0) / max(total, 1) * 200)

            html += f'<tr><td>{r["title"]}</td>'
            html += f'<td>{total}</td>'
            html += f'<td><span class="novelty-pct">{r["novelty_pct"]}%</span></td>'
            html += f'<td><span class="bar bar-new" style="width:{new_w}px"></span>'
            html += f'<span class="bar bar-extends" style="width:{ext_w}px"></span>'
            html += f'<span class="bar bar-known" style="width:{kn_w}px"></span></td></tr>\n'
        html += '</table>\n'

        # Knowledge growth chart
        max_growth = max(growth) if growth else 1
        html += '<h2>Knowledge Growth</h2>\n<div class="growth-chart">\n'
        for i, g in enumerate(growth):
            h = int(g / max_growth * 100)
            html += f'<div style="text-align:center"><div class="growth-bar" style="height:{h}px"></div>'
            html += f'<div class="growth-label">{g}</div></div>\n'
        html += '</div>\n'

        # Delta reports
        for delta in deltas:
            if delta.get("error"):
                continue
            html += f'<h2>Delta: {delta["topic"]}</h2>\n'
            html += f'<p class="meta">{delta["total_claims"]} total · {delta["new_count"]} new · '
            html += f'{delta["extends_count"]} extends · {delta["known_count"]} known '
            html += f'({delta["coverage_pct"]}% covered)</p>\n'

            if delta.get("new_by_article"):
                for article, article_claims in list(delta["new_by_article"].items())[:3]:
                    html += f'<p class="meta"><strong>From: {article}</strong></p>\n'
                    for c in article_claims[:5]:
                        html += f'<div class="claim-new">{c["text"][:120]}</div>\n'

            if delta.get("extends"):
                html += '<p class="meta"><strong>Extends known knowledge:</strong></p>\n'
                for c in delta["extends"][:3]:
                    html += f'<div class="claim-extends">{c["text"][:120]}'
                    if c.get("extends_claim"):
                        html += f'<br><span class="meta">↔ {c["extends_claim"]}</span>'
                    html += '</div>\n'

        # Paragraph dimming preview
        if scenario.get("dimming_preview"):
            dp = scenario["dimming_preview"]
            html += f'<h2>Reader Preview: {dp["article"]}</h2>\n'
            html += '<p class="meta">Paragraph dimming based on knowledge state:</p>\n'
            for p in dp["paragraphs"][:15]:
                opacity = p["opacity"]
                bg = "#f0ece2" if opacity < 0.8 else "transparent"
                label = p["novelty"]
                html += f'<div class="dimming-preview" style="opacity:{opacity}; background:{bg}">'
                html += f'<span class="meta">[{label}]</span> {p["text_preview"]}'
                if p["claim_count"] > 0:
                    html += f' <span class="meta">({p.get("new",0)}N {p.get("extends",0)}E {p.get("known",0)}K)</span>'
                html += '</div>\n'

    html += '</body></html>'
    return html


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="all", help="Scenario: tech, broad, sequential, all")
    parser.add_argument("--report", action="store_true", help="Generate HTML report")
    args = parser.parse_args()

    print("Loading data...", file=sys.stderr)
    articles, claims, claim_to_idx, similarity = load_data()
    print(f"  {len(articles)} articles, {len(claims)} claims", file=sys.stderr)

    scenarios = ["tech", "broad", "sequential"] if args.scenario == "all" else [args.scenario]
    all_results = []

    for scenario in scenarios:
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"  Running scenario: {scenario}", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)

        result = run_scenario(scenario, articles, claims, claim_to_idx, similarity)
        all_results.append(result)

        # Print summary
        print(f"\n  Reading journey ({len(result['readings'])} articles):")
        for r in result["readings"]:
            if r.get("skipped"):
                continue
            c = r.get("classifications", {})
            new = c.get("NEW", 0)
            ext = c.get("EXTENDS", 0)
            known = c.get("KNOWN", 0)
            pct = r["novelty_pct"]
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            print(f"    {r['title'][:50]}")
            print(f"      {bar} {pct}% novel (N:{new} E:{ext} K:{known})")

        print(f"\n  Knowledge growth: {' → '.join(str(g) for g in result['knowledge_growth'])}")

        # Print delta summaries
        for delta in result.get("delta_reports", []):
            if delta.get("error"):
                continue
            print(f"\n  Delta [{delta['topic']}]: {delta['new_count']} new, "
                  f"{delta['extends_count']} extends, {delta['known_count']} known "
                  f"({delta['coverage_pct']}% covered)")

    if args.report:
        report_html = generate_html_report(all_results)
        report_path = DATA_DIR / "reading_simulation_report.html"
        with open(report_path, "w") as f:
            f.write(report_html)
        print(f"\n  HTML report: {report_path}", file=sys.stderr)

    # Save raw results
    results_path = DATA_DIR / "simulation_results.json"
    # Strip claim_details to keep file size reasonable
    for r in all_results:
        for reading in r.get("readings", []):
            if "claim_details" in reading:
                del reading["claim_details"]
    with open(results_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"  Results saved: {results_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
