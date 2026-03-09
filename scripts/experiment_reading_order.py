#!/usr/bin/env python3
"""Experiment: Optimal reading order via curiosity zone scoring.

Simulates reading the entire corpus under 4 strategies and compares
knowledge growth, wasted reading, and information efficiency.

Strategies:
1. Curiosity Zone (optimal) — greedy pick highest curiosity-scored article
2. Chronological — read in articles.json order
3. Random — shuffled order, averaged over 5 runs
4. Most-Novel-First — always pick highest raw novelty %

Usage:
    python3 scripts/experiment_reading_order.py
"""

import json
import math
import random
import sys
from copy import deepcopy
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
ARTICLES_PATH = DATA_DIR / "articles.json"
EMBEDDINGS_PATH = DATA_DIR / "claim_embeddings_nomic.npz"

KNOWN_THRESHOLD = 0.78
EXTENDS_THRESHOLD = 0.68


# ─── Data Loading ────────────────────────────────────────────────────────

def load_data():
    """Load articles, claims, claim index, and precomputed similarity matrix."""
    with open(ARTICLES_PATH) as f:
        articles = json.load(f)

    claims = []
    claim_to_idx = {}
    article_claim_ids = {}  # article_id -> list of claim ids

    for article in articles:
        aid = article.get("id", "")
        article_claim_ids[aid] = []
        for claim in article.get("atomic_claims", []):
            idx = len(claims)
            claim_to_idx[claim["id"]] = idx
            claims.append({
                **claim,
                "article_id": aid,
                "article_title": article.get("title", ""),
            })
            article_claim_ids[aid].append(claim["id"])

    data = np.load(EMBEDDINGS_PATH)
    embeddings = data["embeddings"]
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normalized = embeddings / norms
    similarity = normalized @ normalized.T

    return articles, claims, claim_to_idx, article_claim_ids, similarity


# ─── Claim Classification ───────────────────────────────────────────────

def classify_article_claims(article_id, article_claim_ids, claim_to_idx,
                            known_indices, similarity):
    """Classify all claims in an article relative to known claims.

    Uses vectorized max-similarity for speed.
    Returns (NEW, EXTENDS, KNOWN, total).
    """
    cids = article_claim_ids.get(article_id, [])
    if not cids:
        return 0, 0, 0, 0

    article_indices = []
    for cid in cids:
        idx = claim_to_idx.get(cid)
        if idx is not None:
            article_indices.append(idx)

    if not article_indices:
        return 0, 0, 0, 0

    total = len(article_indices)

    if not known_indices:
        return total, 0, 0, total

    art_idx = np.array(article_indices)
    kn_idx = np.array(list(known_indices))

    # Vectorized: max similarity of each article claim to any known claim
    sim_block = similarity[np.ix_(art_idx, kn_idx)]
    max_sims = sim_block.max(axis=1)

    new = int(np.sum(max_sims < EXTENDS_THRESHOLD))
    extends = int(np.sum((max_sims >= EXTENDS_THRESHOLD) & (max_sims < KNOWN_THRESHOLD)))
    known = int(np.sum(max_sims >= KNOWN_THRESHOLD))

    return new, extends, known, total


# ─── Curiosity Zone Scoring ─────────────────────────────────────────────

def curiosity_score(novelty_ratio, n_claims):
    """Compute curiosity zone score for an article.

    Peak at 70% novelty — articles with ~30% familiar context and
    70% new content are in the optimal learning zone.
    """
    # Novelty peak: Gaussian centered at 0.7
    novelty_peak = math.exp(-((novelty_ratio - 0.7) ** 2) / (2 * 0.15 ** 2))
    # Context bonus: having some familiar content helps anchor learning
    context_bonus = min(1.0, (1 - novelty_ratio) * 3) * 0.3 if novelty_ratio < 1.0 else 0
    # Size factor: prefer substantial articles
    size_factor = min(1.0, n_claims / 15) * 0.2
    return novelty_peak * 0.6 + context_bonus + size_factor


# ─── Reading Simulation ─────────────────────────────────────────────────

def simulate_reading(articles, article_claim_ids, claim_to_idx, similarity,
                     order_fn, total_claims_count):
    """Simulate reading articles in an order determined by order_fn.

    order_fn(unread_articles, known_indices) -> next article to read

    Returns list of step dicts with per-step metrics.
    """
    known_indices = set()  # indices into the similarity matrix
    known_claim_ids = set()
    steps = []

    remaining = list(range(len(articles)))

    for step_num in range(len(articles)):
        if not remaining:
            break

        # Let the strategy pick the next article
        next_idx = order_fn(remaining, known_indices, articles,
                            article_claim_ids, claim_to_idx, similarity)
        remaining.remove(next_idx)
        article = articles[next_idx]
        aid = article.get("id", "")

        # Classify claims before reading
        new, extends, known, total = classify_article_claims(
            aid, article_claim_ids, claim_to_idx, known_indices, similarity
        )

        # "Read" the article — add all its claims to known set
        for cid in article_claim_ids.get(aid, []):
            idx = claim_to_idx.get(cid)
            if idx is not None:
                known_indices.add(idx)
                known_claim_ids.add(cid)

        novelty_ratio = (new + extends) / total if total > 0 else 1.0
        familiar_ratio = known / total if total > 0 else 0.0

        steps.append({
            "step": step_num + 1,
            "article_idx": next_idx,
            "title": article.get("title", "")[:60],
            "total_claims": total,
            "new": new,
            "extends": extends,
            "known_before": known,
            "novelty_pct": round(novelty_ratio * 100, 1),
            "familiar_pct": round(familiar_ratio * 100, 1),
            "cumulative_known": len(known_claim_ids),
            "knowledge_coverage": round(len(known_claim_ids) / total_claims_count * 100, 1),
            "curiosity_score": round(curiosity_score(novelty_ratio, total), 4),
        })

    return steps


# ─── Strategy Functions ──────────────────────────────────────────────────

def strategy_curiosity_zone(remaining, known_indices, articles,
                            article_claim_ids, claim_to_idx, similarity):
    """Pick the article with the highest curiosity zone score."""
    best_idx = remaining[0]
    best_score = -1.0

    for idx in remaining:
        aid = articles[idx].get("id", "")
        new, extends, known, total = classify_article_claims(
            aid, article_claim_ids, claim_to_idx, known_indices, similarity
        )
        if total == 0:
            continue
        novelty_ratio = (new + extends) / total
        score = curiosity_score(novelty_ratio, total)
        if score > best_score:
            best_score = score
            best_idx = idx

    return best_idx


def strategy_chronological(remaining, known_indices, articles,
                           article_claim_ids, claim_to_idx, similarity):
    """Pick the first article in original order."""
    return min(remaining)


def strategy_most_novel(remaining, known_indices, articles,
                        article_claim_ids, claim_to_idx, similarity):
    """Pick the article with the highest raw novelty %."""
    best_idx = remaining[0]
    best_novelty = -1.0

    for idx in remaining:
        aid = articles[idx].get("id", "")
        new, extends, known, total = classify_article_claims(
            aid, article_claim_ids, claim_to_idx, known_indices, similarity
        )
        if total == 0:
            continue
        novelty = (new + extends) / total
        if novelty > best_novelty:
            best_novelty = novelty
            best_idx = idx

    return best_idx


def make_random_strategy(seed):
    """Create a random-order strategy with a fixed seed."""
    rng = random.Random(seed)
    shuffled_order = None

    def strategy(remaining, known_indices, articles,
                 article_claim_ids, claim_to_idx, similarity):
        nonlocal shuffled_order
        if shuffled_order is None:
            shuffled_order = list(range(len(articles)))
            rng.shuffle(shuffled_order)
        # Pick the first article from shuffled order that is still remaining
        remaining_set = set(remaining)
        for idx in shuffled_order:
            if idx in remaining_set:
                return idx
        return remaining[0]

    return strategy


# ─── Metrics Aggregation ────────────────────────────────────────────────

def compute_summary(steps):
    """Compute summary metrics for a reading strategy."""
    total_familiar_claims = sum(s["known_before"] for s in steps)
    total_claims_read = sum(s["total_claims"] for s in steps)
    avg_novelty = sum(s["novelty_pct"] for s in steps) / len(steps) if steps else 0
    avg_curiosity = sum(s["curiosity_score"] for s in steps) / len(steps) if steps else 0

    # Wasted reading: cumulative familiar claims / total claims read
    wasted_pct = total_familiar_claims / total_claims_read * 100 if total_claims_read > 0 else 0

    # Knowledge growth efficiency: area under the coverage curve
    # Higher = faster knowledge accumulation
    coverage_auc = sum(s["knowledge_coverage"] for s in steps) / len(steps) if steps else 0

    # First step where we reach 50%, 75%, 90% coverage
    milestones = {}
    for target in [50, 75, 90]:
        for s in steps:
            if s["knowledge_coverage"] >= target:
                milestones[f"step_to_{target}pct"] = s["step"]
                break
        else:
            milestones[f"step_to_{target}pct"] = None

    return {
        "avg_novelty_pct": round(avg_novelty, 1),
        "avg_curiosity_score": round(avg_curiosity, 4),
        "total_familiar_claims": total_familiar_claims,
        "total_claims_read": total_claims_read,
        "wasted_reading_pct": round(wasted_pct, 1),
        "coverage_auc": round(coverage_auc, 1),
        "final_coverage_pct": steps[-1]["knowledge_coverage"] if steps else 0,
        **milestones,
    }


# ─── HTML Visualization ─────────────────────────────────────────────────

def generate_html(results, output_path):
    """Generate an Annotated Folio styled HTML visualization."""

    # Prepare data series for the chart
    strategies = ["curiosity_zone", "chronological", "random_avg", "most_novel_first"]
    labels = ["Curiosity Zone", "Chronological", "Random (avg 5)", "Most Novel First"]
    colors = ["#8b2500", "#2a2420", "#b0a898", "#2a7a4a"]

    coverage_data = {}
    novelty_data = {}
    wasted_data = {}

    for key in strategies:
        steps = results[key]["steps"]
        coverage_data[key] = [s["knowledge_coverage"] for s in steps]
        novelty_data[key] = [s["novelty_pct"] for s in steps]
        # Cumulative wasted: running total of familiar claims / running total claims read
        cum_familiar = 0
        cum_total = 0
        wasted_series = []
        for s in steps:
            cum_familiar += s["known_before"]
            cum_total += s["total_claims"]
            wasted_series.append(round(cum_familiar / cum_total * 100, 1) if cum_total > 0 else 0)
        wasted_data[key] = wasted_series

    # Summary table data
    summaries = {key: results[key]["summary"] for key in strategies}

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Reading Order Optimization — Petrarca</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600&family=Crimson+Pro:wght@400;500&family=DM+Sans:wght@400;500;600&family=EB+Garamond:ital,wght@0,400;0,600;1,400&display=swap" rel="stylesheet">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: #f7f4ec;
    color: #2a2420;
    font-family: 'Crimson Pro', serif;
    font-size: 17px;
    line-height: 1.6;
    padding: 40px 24px;
    max-width: 900px;
    margin: 0 auto;
  }}
  h1 {{
    font-family: 'Cormorant Garamond', serif;
    font-weight: 600;
    font-size: 32px;
    color: #2a2420;
    margin-bottom: 4px;
  }}
  .subtitle {{
    font-family: 'DM Sans', sans-serif;
    font-size: 13px;
    color: #6a6458;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    margin-bottom: 12px;
  }}
  .double-rule {{
    border: none;
    border-top: 2px solid #2a2420;
    margin-bottom: 5px;
  }}
  .double-rule-thin {{
    border: none;
    border-top: 1px solid #2a2420;
    margin-bottom: 32px;
  }}
  .section-heading {{
    font-family: 'EB Garamond', serif;
    font-weight: 600;
    font-size: 14px;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: #8b2500;
    margin: 40px 0 16px;
  }}
  .section-heading::before {{
    content: '\\2726 ';
    color: #8b2500;
  }}
  .chart-container {{
    background: white;
    border: 1px solid #e4dfd4;
    border-radius: 4px;
    padding: 24px;
    margin: 16px 0 32px;
    position: relative;
  }}
  .chart-title {{
    font-family: 'EB Garamond', serif;
    font-weight: 600;
    font-size: 16px;
    margin-bottom: 16px;
    color: #1a1a18;
  }}
  canvas {{
    width: 100% !important;
    height: 320px !important;
  }}
  .legend {{
    display: flex;
    gap: 24px;
    flex-wrap: wrap;
    margin-top: 12px;
    font-family: 'DM Sans', sans-serif;
    font-size: 12px;
  }}
  .legend-item {{
    display: flex;
    align-items: center;
    gap: 6px;
  }}
  .legend-dot {{
    width: 12px;
    height: 3px;
    border-radius: 1px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 16px 0;
    font-family: 'DM Sans', sans-serif;
    font-size: 13px;
  }}
  th {{
    font-family: 'EB Garamond', serif;
    font-weight: 600;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #6a6458;
    text-align: left;
    padding: 8px 12px;
    border-bottom: 2px solid #e4dfd4;
  }}
  th.num {{ text-align: right; }}
  td {{
    padding: 8px 12px;
    border-bottom: 1px solid #e4dfd4;
    color: #333333;
  }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  tr.highlight {{ background: rgba(139, 37, 0, 0.04); }}
  tr.highlight td:first-child {{ font-weight: 600; color: #8b2500; }}
  .metric-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px;
    margin: 16px 0 32px;
  }}
  .metric-card {{
    border-left: 2px solid #e4dfd4;
    padding: 12px 16px;
  }}
  .metric-card.winner {{ border-left-color: #8b2500; }}
  .metric-value {{
    font-family: 'Cormorant Garamond', serif;
    font-weight: 600;
    font-size: 28px;
    color: #1a1a18;
  }}
  .metric-label {{
    font-family: 'DM Sans', sans-serif;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #6a6458;
    margin-top: 2px;
  }}
  .metric-detail {{
    font-family: 'DM Sans', sans-serif;
    font-size: 11px;
    color: #b0a898;
    margin-top: 4px;
  }}
  .insight {{
    font-family: 'Crimson Pro', serif;
    font-size: 16px;
    color: #333333;
    line-height: 1.7;
    margin: 12px 0;
    padding: 16px 20px;
    border-left: 2px solid #c9a84c;
    background: rgba(201, 168, 76, 0.04);
  }}
  .reading-order {{
    font-family: 'DM Sans', sans-serif;
    font-size: 12px;
    margin: 16px 0;
  }}
  .reading-order li {{
    padding: 4px 0;
    color: #333333;
    list-style: none;
    display: flex;
    gap: 8px;
  }}
  .reading-order .step-num {{
    font-family: 'Cormorant Garamond', serif;
    font-weight: 600;
    font-size: 16px;
    color: #b0a898;
    min-width: 24px;
    text-align: right;
  }}
  .reading-order .step-novelty {{
    font-size: 11px;
    color: #2a7a4a;
    min-width: 40px;
    text-align: right;
  }}
  .reading-order .step-novelty.low {{ color: #b0a898; }}
  .footer {{
    margin-top: 48px;
    padding-top: 16px;
    border-top: 1px solid #e4dfd4;
    font-family: 'DM Sans', sans-serif;
    font-size: 11px;
    color: #b0a898;
  }}
</style>
</head>
<body>

<h1>Reading Order Optimization</h1>
<div class="subtitle">Petrarca Experiment &mdash; {len(results['curiosity_zone']['steps'])} articles, {results['total_claims']} claims</div>
<hr class="double-rule">
<hr class="double-rule-thin">

<div class="insight">
  Does reading order matter? This experiment simulates reading the entire corpus
  under four strategies, tracking how quickly knowledge grows and how much
  familiar content the reader encounters along the way.
</div>

<div class="section-heading">Key Results</div>

<div class="metric-grid">
  <div class="metric-card winner">
    <div class="metric-value">{summaries['curiosity_zone']['wasted_reading_pct']}%</div>
    <div class="metric-label">Wasted Reading (Curiosity)</div>
    <div class="metric-detail">vs {summaries['chronological']['wasted_reading_pct']}% chronological</div>
  </div>
  <div class="metric-card winner">
    <div class="metric-value">{summaries['curiosity_zone']['coverage_auc']}</div>
    <div class="metric-label">Coverage AUC (Curiosity)</div>
    <div class="metric-detail">vs {summaries['chronological']['coverage_auc']} chronological</div>
  </div>
  <div class="metric-card">
    <div class="metric-value">{summaries['curiosity_zone']['avg_curiosity_score']}</div>
    <div class="metric-label">Avg Curiosity Score</div>
    <div class="metric-detail">vs {summaries['most_novel_first']['avg_curiosity_score']} most-novel</div>
  </div>
  <div class="metric-card">
    <div class="metric-value">{summaries['curiosity_zone'].get('step_to_90pct') or 'N/A'}</div>
    <div class="metric-label">Steps to 90% Coverage</div>
    <div class="metric-detail">vs {summaries['chronological'].get('step_to_90pct') or 'N/A'} chronological</div>
  </div>
</div>

<div class="section-heading">Knowledge Growth Curves</div>
<div class="chart-container">
  <div class="chart-title">Knowledge Coverage (% of total claims known)</div>
  <canvas id="coverageChart"></canvas>
  <div class="legend">
    <div class="legend-item"><div class="legend-dot" style="background:#8b2500"></div>Curiosity Zone</div>
    <div class="legend-item"><div class="legend-dot" style="background:#2a2420"></div>Chronological</div>
    <div class="legend-item"><div class="legend-dot" style="background:#b0a898"></div>Random (avg)</div>
    <div class="legend-item"><div class="legend-dot" style="background:#2a7a4a"></div>Most Novel First</div>
  </div>
</div>

<div class="section-heading">Per-Article Novelty</div>
<div class="chart-container">
  <div class="chart-title">Novelty % at each reading step</div>
  <canvas id="noveltyChart"></canvas>
  <div class="legend">
    <div class="legend-item"><div class="legend-dot" style="background:#8b2500"></div>Curiosity Zone</div>
    <div class="legend-item"><div class="legend-dot" style="background:#2a2420"></div>Chronological</div>
    <div class="legend-item"><div class="legend-dot" style="background:#b0a898"></div>Random (avg)</div>
    <div class="legend-item"><div class="legend-dot" style="background:#2a7a4a"></div>Most Novel First</div>
  </div>
</div>

<div class="section-heading">Cumulative Wasted Reading</div>
<div class="chart-container">
  <div class="chart-title">% of consumed content that was already familiar</div>
  <canvas id="wastedChart"></canvas>
  <div class="legend">
    <div class="legend-item"><div class="legend-dot" style="background:#8b2500"></div>Curiosity Zone</div>
    <div class="legend-item"><div class="legend-dot" style="background:#2a2420"></div>Chronological</div>
    <div class="legend-item"><div class="legend-dot" style="background:#b0a898"></div>Random (avg)</div>
    <div class="legend-item"><div class="legend-dot" style="background:#2a7a4a"></div>Most Novel First</div>
  </div>
</div>

<div class="section-heading">Strategy Comparison</div>
<table>
  <thead>
    <tr>
      <th>Strategy</th>
      <th class="num">Avg Novelty</th>
      <th class="num">Avg Curiosity</th>
      <th class="num">Wasted %</th>
      <th class="num">Coverage AUC</th>
      <th class="num">Steps to 50%</th>
      <th class="num">Steps to 90%</th>
    </tr>
  </thead>
  <tbody>"""

    for key, label in zip(strategies, labels):
        s = summaries[key]
        row_class = ' class="highlight"' if key == "curiosity_zone" else ""
        html += f"""
    <tr{row_class}>
      <td>{label}</td>
      <td class="num">{s['avg_novelty_pct']}%</td>
      <td class="num">{s['avg_curiosity_score']}</td>
      <td class="num">{s['wasted_reading_pct']}%</td>
      <td class="num">{s['coverage_auc']}</td>
      <td class="num">{s.get('step_to_50pct') or '—'}</td>
      <td class="num">{s.get('step_to_90pct') or '—'}</td>
    </tr>"""

    html += """
  </tbody>
</table>

<div class="section-heading">Optimal Reading Order (Curiosity Zone)</div>
<ol class="reading-order">"""

    for s in results["curiosity_zone"]["steps"]:
        novelty_class = "low" if s["novelty_pct"] < 50 else ""
        html += f"""
  <li>
    <span class="step-num">{s['step']}</span>
    <span class="step-novelty {novelty_class}">{s['novelty_pct']}%</span>
    <span>{s['title']}</span>
  </li>"""

    html += f"""
</ol>

<div class="footer">
  Generated by experiment_reading_order.py &mdash; {len(results['curiosity_zone']['steps'])} articles,
  {results['total_claims']} atomic claims, Nomic embeddings,
  thresholds: KNOWN&ge;{KNOWN_THRESHOLD}, EXTENDS&ge;{EXTENDS_THRESHOLD}
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<script>
const coverageData = {json.dumps(coverage_data)};
const noveltyData = {json.dumps(novelty_data)};
const wastedData = {json.dumps(wasted_data)};

const strategies = {json.dumps(strategies)};
const labels = {json.dumps(labels)};
const colors = {json.dumps(colors)};

function makeChart(canvasId, dataObj, yLabel, yMax) {{
  const ctx = document.getElementById(canvasId).getContext('2d');
  const datasets = strategies.map((key, i) => ({{
    label: labels[i],
    data: dataObj[key],
    borderColor: colors[i],
    backgroundColor: 'transparent',
    borderWidth: key === 'curiosity_zone' ? 2.5 : 1.5,
    pointRadius: 0,
    tension: 0.3,
  }}));

  new Chart(ctx, {{
    type: 'line',
    data: {{
      labels: dataObj[strategies[0]].map((_, i) => i + 1),
      datasets: datasets,
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          mode: 'index',
          intersect: false,
          titleFont: {{ family: 'DM Sans', size: 12 }},
          bodyFont: {{ family: 'DM Sans', size: 11 }},
        }},
      }},
      scales: {{
        x: {{
          title: {{
            display: true,
            text: 'Articles Read',
            font: {{ family: 'DM Sans', size: 11 }},
            color: '#6a6458',
          }},
          grid: {{ color: '#e4dfd4' }},
          ticks: {{ font: {{ family: 'DM Sans', size: 10 }}, color: '#6a6458' }},
        }},
        y: {{
          title: {{
            display: true,
            text: yLabel,
            font: {{ family: 'DM Sans', size: 11 }},
            color: '#6a6458',
          }},
          min: 0,
          max: yMax,
          grid: {{ color: '#e4dfd4' }},
          ticks: {{
            font: {{ family: 'DM Sans', size: 10 }},
            color: '#6a6458',
            callback: v => v + '%',
          }},
        }},
      }},
    }},
  }});
}}

makeChart('coverageChart', coverageData, 'Coverage %', 100);
makeChart('noveltyChart', noveltyData, 'Novelty %', 100);
makeChart('wastedChart', wastedData, 'Wasted %', undefined);
</script>

</body>
</html>"""

    with open(output_path, "w") as f:
        f.write(html)


# ─── Main ────────────────────────────────────────────────────────────────

def main():
    print("Loading data...", file=sys.stderr)
    articles, claims, claim_to_idx, article_claim_ids, similarity = load_data()
    total_claims = len(claims)
    print(f"  {len(articles)} articles, {total_claims} claims", file=sys.stderr)

    results = {"total_claims": total_claims, "total_articles": len(articles)}

    # ─── Strategy 1: Curiosity Zone (optimal greedy) ─────────────────
    print("\nSimulating: Curiosity Zone...", file=sys.stderr)
    cz_steps = simulate_reading(articles, article_claim_ids, claim_to_idx,
                                similarity, strategy_curiosity_zone, total_claims)
    results["curiosity_zone"] = {
        "steps": cz_steps,
        "summary": compute_summary(cz_steps),
    }
    print(f"  Done. Final coverage: {cz_steps[-1]['knowledge_coverage']}%", file=sys.stderr)

    # ─── Strategy 2: Chronological ───────────────────────────────────
    print("Simulating: Chronological...", file=sys.stderr)
    ch_steps = simulate_reading(articles, article_claim_ids, claim_to_idx,
                                similarity, strategy_chronological, total_claims)
    results["chronological"] = {
        "steps": ch_steps,
        "summary": compute_summary(ch_steps),
    }
    print(f"  Done. Final coverage: {ch_steps[-1]['knowledge_coverage']}%", file=sys.stderr)

    # ─── Strategy 3: Random (average of 5 runs) ─────────────────────
    print("Simulating: Random (5 runs)...", file=sys.stderr)
    random_runs = []
    for seed in range(5):
        strat = make_random_strategy(seed=42 + seed)
        r_steps = simulate_reading(articles, article_claim_ids, claim_to_idx,
                                   similarity, strat, total_claims)
        random_runs.append(r_steps)

    # Average the random runs
    n_steps = len(random_runs[0])
    avg_steps = []
    for i in range(n_steps):
        avg_step = {
            "step": i + 1,
            "title": f"(random avg, step {i+1})",
            "total_claims": round(sum(r[i]["total_claims"] for r in random_runs) / 5, 1),
            "new": round(sum(r[i]["new"] for r in random_runs) / 5, 1),
            "extends": round(sum(r[i]["extends"] for r in random_runs) / 5, 1),
            "known_before": round(sum(r[i]["known_before"] for r in random_runs) / 5, 1),
            "novelty_pct": round(sum(r[i]["novelty_pct"] for r in random_runs) / 5, 1),
            "familiar_pct": round(sum(r[i]["familiar_pct"] for r in random_runs) / 5, 1),
            "cumulative_known": round(sum(r[i]["cumulative_known"] for r in random_runs) / 5, 1),
            "knowledge_coverage": round(sum(r[i]["knowledge_coverage"] for r in random_runs) / 5, 1),
            "curiosity_score": round(sum(r[i]["curiosity_score"] for r in random_runs) / 5, 4),
        }
        avg_steps.append(avg_step)

    results["random_avg"] = {
        "steps": avg_steps,
        "summary": compute_summary(avg_steps),
    }
    print(f"  Done. Final coverage: {avg_steps[-1]['knowledge_coverage']}%", file=sys.stderr)

    # ─── Strategy 4: Most Novel First ────────────────────────────────
    print("Simulating: Most Novel First...", file=sys.stderr)
    mn_steps = simulate_reading(articles, article_claim_ids, claim_to_idx,
                                similarity, strategy_most_novel, total_claims)
    results["most_novel_first"] = {
        "steps": mn_steps,
        "summary": compute_summary(mn_steps),
    }
    print(f"  Done. Final coverage: {mn_steps[-1]['knowledge_coverage']}%", file=sys.stderr)

    # ─── Print Comparison Table ──────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"  READING ORDER OPTIMIZATION — {len(articles)} articles, {total_claims} claims")
    print(f"{'='*80}")

    strategies_list = [
        ("Curiosity Zone", results["curiosity_zone"]["summary"]),
        ("Chronological", results["chronological"]["summary"]),
        ("Random (avg 5)", results["random_avg"]["summary"]),
        ("Most Novel First", results["most_novel_first"]["summary"]),
    ]

    print(f"\n  {'Strategy':<20} {'AvgNov%':>8} {'AvgCur':>8} {'Waste%':>8} "
          f"{'CovAUC':>8} {'->50%':>6} {'->75%':>6} {'->90%':>6}")
    print(f"  {'─'*20} {'─'*8} {'─'*8} {'─'*8} {'─'*8} {'─'*6} {'─'*6} {'─'*6}")

    for name, s in strategies_list:
        s50 = str(s.get("step_to_50pct") or "—")
        s75 = str(s.get("step_to_75pct") or "—")
        s90 = str(s.get("step_to_90pct") or "—")
        print(f"  {name:<20} {s['avg_novelty_pct']:>7.1f}% {s['avg_curiosity_score']:>8.4f} "
              f"{s['wasted_reading_pct']:>7.1f}% {s['coverage_auc']:>8.1f} "
              f"{s50:>6} {s75:>6} {s90:>6}")

    # ─── Detailed Curiosity Zone Order ───────────────────────────────
    print(f"\n{'='*80}")
    print(f"  OPTIMAL READING ORDER (Curiosity Zone)")
    print(f"{'='*80}")
    print(f"\n  {'Step':>4} {'Nov%':>6} {'Cur':>6} {'N':>4} {'E':>4} {'K':>4} "
          f"{'Cov%':>6} {'Title'}")
    print(f"  {'─'*4} {'─'*6} {'─'*6} {'─'*4} {'─'*4} {'─'*4} {'─'*6} {'─'*45}")

    for s in cz_steps:
        print(f"  {s['step']:>4} {s['novelty_pct']:>5.1f}% {s['curiosity_score']:>6.4f} "
              f"{s['new']:>4} {s['extends']:>4} {s['known_before']:>4} "
              f"{s['knowledge_coverage']:>5.1f}% {s['title'][:45]}")

    # ─── Per-Step Comparison ─────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"  KNOWLEDGE COVERAGE AT KEY STEPS")
    print(f"{'='*80}")

    milestones = [1, 5, 10, 15, 20, 25, 30, 35, 40, 45, len(articles)]
    milestones = [m for m in milestones if m <= len(articles)]

    print(f"\n  {'Step':>5}  ", end="")
    for name, _ in strategies_list:
        print(f" {name:>16}", end="")
    print()
    print(f"  {'─'*5}  ", end="")
    for _ in strategies_list:
        print(f" {'─'*16}", end="")
    print()

    for m in milestones:
        idx = m - 1
        print(f"  {m:>5}  ", end="")
        for _, s_data in [(None, results[k]["steps"]) for k in
                          ["curiosity_zone", "chronological", "random_avg", "most_novel_first"]]:
            if idx < len(s_data):
                print(f" {s_data[idx]['knowledge_coverage']:>15.1f}%", end="")
            else:
                print(f" {'—':>16}", end="")
        print()

    # ─── Save JSON ───────────────────────────────────────────────────
    json_path = DATA_DIR / "experiment_reading_order.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Results saved: {json_path}", file=sys.stderr)

    # ─── Generate HTML ───────────────────────────────────────────────
    html_path = DATA_DIR / "reading_order_curves.html"
    generate_html(results, html_path)
    print(f"  HTML saved: {html_path}", file=sys.stderr)

    print(f"\n  Done!", file=sys.stderr)


if __name__ == "__main__":
    main()
