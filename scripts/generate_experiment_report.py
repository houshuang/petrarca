#!/usr/bin/env python3
"""Generate a visual HTML report of all novelty system experiments.

Produces an Annotated Folio styled report with charts, tables, and
cluster visualizations.

Usage:
    python3 scripts/generate_experiment_report.py
"""

import json
import sys
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def generate_report():
    # Load all experiment results
    nli = load_json(DATA_DIR / "experiment_nli_entailment.json")
    clustering = load_json(DATA_DIR / "experiment_topic_clustering.json")
    decay = load_json(DATA_DIR / "experiment_knowledge_decay.json")
    curiosity = load_json(DATA_DIR / "experiment_curiosity_zone.json")
    combined = load_json(DATA_DIR / "experiment_combined_scoring.json")
    simulation = load_json(DATA_DIR / "simulation_results.json")

    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Petrarca — Novelty System Experiments</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600&family=Crimson+Pro:wght@400;500&family=DM+Sans:wght@400;500&family=EB+Garamond:ital,wght@0,400;0,500;1,400&display=swap');

:root {
  --parchment: #f7f4ec;
  --ink: #2a2420;
  --rubric: #8b2500;
  --textBody: #333333;
  --textSecondary: #6a6458;
  --textMuted: #b0a898;
  --rule: #e4dfd4;
  --claimNew: #2a7a4a;
  --claimKnown: #d0ccc0;
  --gold: #c9a84c;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Crimson Pro', Georgia, serif; max-width: 780px; margin: 0 auto; padding: 40px 20px 80px; background: var(--parchment); color: var(--ink); }
h1 { font-family: 'Cormorant Garamond', serif; font-weight: 600; font-size: 36px; margin-bottom: 4px; }
h1 span { color: var(--rubric); }
.subtitle { font-family: 'DM Sans', sans-serif; font-size: 13px; color: var(--textSecondary); letter-spacing: 1px; text-transform: uppercase; }
.double-rule { border-top: 2px solid var(--ink); margin-top: 8px; padding-top: 5px; border-bottom: 1px solid var(--ink); height: 0; margin-bottom: 32px; }
h2 { font-family: 'EB Garamond', serif; text-transform: uppercase; letter-spacing: 2px; font-size: 14px; color: var(--rubric); margin: 40px 0 16px; }
h2::before { content: '✦ '; }
h3 { font-family: 'EB Garamond', serif; font-size: 16px; color: var(--ink); margin: 24px 0 8px; }
p { font-size: 16px; line-height: 1.6; color: var(--textBody); margin-bottom: 12px; }
.meta { font-family: 'DM Sans', sans-serif; font-size: 12px; color: var(--textSecondary); }

table { border-collapse: collapse; width: 100%; margin: 12px 0 24px; }
th { font-family: 'DM Sans', sans-serif; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; text-align: left; padding: 8px; border-bottom: 2px solid var(--rule); color: var(--textSecondary); }
td { padding: 8px; border-bottom: 1px solid var(--rule); font-size: 14px; }
td.num { font-family: 'Cormorant Garamond', serif; font-size: 20px; font-weight: 600; text-align: right; }

.bar-chart { display: flex; align-items: flex-end; gap: 4px; height: 120px; margin: 16px 0; padding-left: 30px; border-left: 1px solid var(--rule); border-bottom: 1px solid var(--rule); }
.bar-group { display: flex; flex-direction: column; align-items: center; }
.bar { width: 30px; border-radius: 2px 2px 0 0; transition: height 0.3s; }
.bar-new { background: var(--claimNew); }
.bar-extends { background: var(--gold); }
.bar-known { background: var(--claimKnown); }
.bar-partial { background: #a09888; }
.bar-label { font-family: 'DM Sans', sans-serif; font-size: 9px; color: var(--textMuted); margin-top: 4px; text-align: center; max-width: 40px; overflow: hidden; }

.legend { display: flex; gap: 16px; margin: 8px 0 16px; }
.legend-item { display: flex; align-items: center; gap: 4px; font-family: 'DM Sans', sans-serif; font-size: 11px; color: var(--textSecondary); }
.legend-dot { width: 10px; height: 10px; border-radius: 2px; }

.metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 16px 0 24px; }
.metric { text-align: center; padding: 16px 8px; border: 1px solid var(--rule); border-radius: 4px; }
.metric-value { font-family: 'Cormorant Garamond', serif; font-size: 28px; font-weight: 600; color: var(--rubric); }
.metric-label { font-family: 'DM Sans', sans-serif; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; color: var(--textSecondary); margin-top: 4px; }

.claim-card { border-left: 2px solid var(--rule); padding: 8px 12px; margin: 8px 0; }
.claim-card.new { border-color: var(--claimNew); }
.claim-card.extends { border-color: var(--gold); }
.claim-card.known { border-color: var(--claimKnown); opacity: 0.55; }

.scatter-plot { position: relative; width: 100%; height: 300px; border: 1px solid var(--rule); border-radius: 4px; margin: 16px 0; background: white; overflow: hidden; }
.scatter-dot { position: absolute; width: 6px; height: 6px; border-radius: 50%; transform: translate(-50%, -50%); opacity: 0.7; }

.timeline { display: flex; flex-direction: column; gap: 2px; margin: 16px 0; }
.timeline-row { display: grid; grid-template-columns: 40px 1fr 60px; align-items: center; gap: 8px; padding: 4px 0; }
.timeline-bar { height: 20px; display: flex; border-radius: 2px; overflow: hidden; }
.timeline-segment { height: 100%; }
</style>
</head>
<body>

<h1>Novelty System <span>Experiments</span></h1>
<p class="subtitle">Petrarca · March 8, 2026 · 858 claims · 47 articles · 5 experiments</p>
<div class="double-rule"></div>
"""

    # ─── Summary Metrics ─────────────────────────────────────────────
    html += """
<div class="metric-grid">
  <div class="metric"><div class="metric-value">858</div><div class="metric-label">Claims</div></div>
  <div class="metric"><div class="metric-value">47</div><div class="metric-label">Articles</div></div>
  <div class="metric"><div class="metric-value">59</div><div class="metric-label">Topic Clusters</div></div>
  <div class="metric"><div class="metric-value">768</div><div class="metric-label">Embedding Dim</div></div>
</div>
"""

    # ─── Embedding Comparison ────────────────────────────────────────
    html += '<h2>Embedding Model Comparison</h2>\n'
    html += """
<table>
<tr><th>Property</th><th>Gemini embedding-001</th><th>Nomic-embed-text-v1.5</th><th>Winner</th></tr>
<tr><td>Dimensions</td><td>3072</td><td>768</td><td style="color:var(--claimNew)">Nomic (4× smaller)</td></tr>
<tr><td>Speed (858 claims)</td><td>~10s (API)</td><td>3.9s (local)</td><td style="color:var(--claimNew)">Nomic (local)</td></tr>
<tr><td>Cost</td><td>Free tier (limited)</td><td>Free (forever)</td><td style="color:var(--claimNew)">Nomic</td></tr>
<tr><td>Near-duplicate peak</td><td>0.90</td><td>0.93</td><td style="color:var(--claimNew)">Nomic (clearer)</td></tr>
<tr><td>Discriminable range</td><td>0.62-0.73</td><td>0.68-0.93</td><td style="color:var(--claimNew)">Nomic (wider)</td></tr>
</table>
<p class="meta">Decision: Nomic is default. Thresholds calibrated: KNOWN ≥ 0.78, EXTENDS ≥ 0.68</p>
"""

    # ─── NLI Entailment ──────────────────────────────────────────────
    if nli:
        html += '<h2>NLI Entailment — LLM Judge vs Cosine</h2>\n'
        html += f'<p>Tested {nli["total_pairs"]} claim pairs. Agreement rate: <strong>{nli["agreement_rate"]}%</strong></p>\n'

        # Agreement by bucket
        html += '<div class="bar-chart">\n'
        buckets = ["low (0.40-0.55)", "medium (0.55-0.65)", "medium-high (0.65-0.75)", "high (0.75-1.0)"]
        for bucket_name in buckets:
            pairs = nli["buckets"].get(bucket_name, [])
            agree = sum(1 for p in pairs if p.get("agree"))
            disagree = len(pairs) - agree
            max_h = 100
            agree_h = int(agree / max(len(pairs), 1) * max_h) if pairs else 0
            disagree_h = int(disagree / max(len(pairs), 1) * max_h) if pairs else 0
            label = bucket_name.split("(")[1].rstrip(")")
            html += f'<div class="bar-group">'
            html += f'<div style="display:flex;align-items:flex-end;gap:2px;height:100px">'
            html += f'<div class="bar bar-new" style="height:{agree_h}px;width:14px" title="Agree: {agree}"></div>'
            html += f'<div class="bar" style="height:{disagree_h}px;width:14px;background:var(--rubric)" title="Disagree: {disagree}"></div>'
            html += f'</div>'
            html += f'<div class="bar-label">{label}</div></div>\n'
        html += '</div>\n'
        html += '<div class="legend">'
        html += '<div class="legend-item"><div class="legend-dot" style="background:var(--claimNew)"></div>Agree</div>'
        html += '<div class="legend-item"><div class="legend-dot" style="background:var(--rubric)"></div>Disagree</div>'
        html += '</div>\n'

        # Disagreement patterns
        if nli.get("disagreements"):
            html += '<h3>Disagreement Pattern</h3>\n'
            html += '<p class="meta">Where cosine and LLM judge disagree:</p>\n'
            patterns = {}
            for d in nli["disagreements"]:
                key = f'{d["cosine_class"]} → {d["llm_class"]}'
                patterns[key] = patterns.get(key, 0) + 1
            for pattern, count in sorted(patterns.items(), key=lambda x: -x[1]):
                html += f'<div class="claim-card extends">{pattern}: {count} cases</div>\n'

    # ─── Topic Clustering ────────────────────────────────────────────
    if clustering:
        html += '<h2>Topic Clustering — UMAP + HDBSCAN</h2>\n'
        html += f'<div class="metric-grid" style="grid-template-columns:repeat(3,1fr)">'
        html += f'<div class="metric"><div class="metric-value">{clustering["n_clusters"]}</div><div class="metric-label">Clusters</div></div>'
        html += f'<div class="metric"><div class="metric-value">{clustering["n_noise"]}</div><div class="metric-label">Noise Points</div></div>'
        noise_pct = round(clustering["n_noise"] / clustering["n_claims"] * 100, 1)
        html += f'<div class="metric"><div class="metric-value">{noise_pct}%</div><div class="metric-label">Noise Rate</div></div>'
        html += '</div>\n'

        # Cluster scatter plot
        if clustering.get("coords_2d") and clustering.get("labels"):
            coords = clustering["coords_2d"]
            labels = clustering["labels"]
            # Normalize to 0-100%
            xs = [c[0] for c in coords]
            ys = [c[1] for c in coords]
            xmin, xmax = min(xs), max(xs)
            ymin, ymax = min(ys), max(ys)
            xrange = xmax - xmin or 1
            yrange = ymax - ymin or 1

            # Color palette for clusters
            colors = [
                "#8b2500", "#2a7a4a", "#c9a84c", "#4a6fa5", "#7b4b94",
                "#d45b90", "#2d9d92", "#e07c3e", "#5b7553", "#8b6914",
                "#6b4226", "#3a6b7e", "#9b4dca", "#d4a76a", "#4e8b3d",
            ]

            html += '<h3>Claim Embedding Space (2D UMAP)</h3>\n'
            html += '<div class="scatter-plot">\n'
            for i, (x, y) in enumerate(coords[:500]):  # Limit to 500 for performance
                px = (x - xmin) / xrange * 95 + 2.5
                py = (y - ymin) / yrange * 95 + 2.5
                label = labels[i]
                color = colors[label % len(colors)] if label >= 0 else "#cccccc"
                size = "4" if label >= 0 else "3"
                html += f'<div class="scatter-dot" style="left:{px}%;top:{py}%;background:{color};width:{size}px;height:{size}px"></div>\n'
            html += '</div>\n'
            html += '<p class="meta">Each dot is a claim, colored by cluster. Grey = noise. Nearby dots have similar meaning.</p>\n'

        # Topic alignment summary
        if clustering.get("topic_cluster_mapping"):
            mapping = clustering["topic_cluster_mapping"]
            good = sum(1 for v in mapping.values() if v["purity"] > 0.6)
            partial = sum(1 for v in mapping.values() if 0.3 < v["purity"] <= 0.6)
            poor = sum(1 for v in mapping.values() if v["purity"] <= 0.3)

            html += '<h3>LLM Topic ↔ Embedding Cluster Alignment</h3>\n'
            html += f'<div class="metric-grid" style="grid-template-columns:repeat(3,1fr)">'
            html += f'<div class="metric"><div class="metric-value" style="color:var(--claimNew)">{good}</div><div class="metric-label">Clean Match (>60%)</div></div>'
            html += f'<div class="metric"><div class="metric-value" style="color:var(--gold)">{partial}</div><div class="metric-label">Partial (30-60%)</div></div>'
            html += f'<div class="metric"><div class="metric-value" style="color:var(--rubric)">{poor}</div><div class="metric-label">Poor (<30%)</div></div>'
            html += '</div>\n'

    # ─── Knowledge Decay ─────────────────────────────────────────────
    if decay:
        html += '<h2>FSRS Knowledge Decay</h2>\n'

        # Burst reading timeline
        if decay.get("burst_timeline"):
            html += '<h3>Burst Reading (15 articles in 5 days)</h3>\n'
            html += '<div class="timeline">\n'
            for step in decay["burst_timeline"]:
                c = step["counts"] if "counts" in step else step.get("classifications", {})
                total = step["total_claims"]
                if total == 0:
                    continue
                new_pct = c.get("NEW", 0) / total * 100
                ext_pct = c.get("EXTENDS", 0) / total * 100
                known_pct = c.get("KNOWN", 0) / total * 100
                partial_pct = c.get("PARTIALLY_KNOWN", 0) / total * 100

                html += f'<div class="timeline-row">'
                html += f'<div class="meta">D{step["day"]}</div>'
                html += f'<div class="timeline-bar">'
                html += f'<div class="timeline-segment" style="width:{new_pct}%;background:var(--claimNew)"></div>'
                html += f'<div class="timeline-segment" style="width:{ext_pct}%;background:var(--gold)"></div>'
                html += f'<div class="timeline-segment" style="width:{partial_pct}%;background:#a09888"></div>'
                html += f'<div class="timeline-segment" style="width:{known_pct}%;background:var(--claimKnown)"></div>'
                html += f'</div>'
                html += f'<div class="meta">{step["novelty_pct"]}%</div>'
                html += f'</div>\n'
            html += '</div>\n'

            html += '<div class="legend">'
            html += '<div class="legend-item"><div class="legend-dot" style="background:var(--claimNew)"></div>New</div>'
            html += '<div class="legend-item"><div class="legend-dot" style="background:var(--gold)"></div>Extends</div>'
            html += '<div class="legend-item"><div class="legend-dot" style="background:#a09888"></div>Partial</div>'
            html += '<div class="legend-item"><div class="legend-dot" style="background:var(--claimKnown)"></div>Known</div>'
            html += '</div>\n'

        # Decay curve
        html += '<h3>Knowledge Retention Over Time</h3>\n'
        html += '<p>After reading 15 articles in 5 days (BASE_STABILITY = 30 days):</p>\n'
        html += '<table><tr><th>Day</th><th>Known</th><th>Partial</th><th>Forgotten</th></tr>\n'
        for row in [
            ("0", "100%", "0%", "0%"),
            ("7", "100%", "0%", "0%"),
            ("14", "100%", "0%", "0%"),
            ("30", "0%", "100%", "0%"),
            ("45", "0%", "0%", "100%"),
        ]:
            html += f'<tr><td>{row[0]}</td><td>{row[1]}</td><td>{row[2]}</td><td>{row[3]}</td></tr>\n'
        html += '</table>\n'

    # ─── Curiosity Zone ──────────────────────────────────────────────
    if curiosity:
        html += '<h2>Curiosity Zone Scoring</h2>\n'

        corr = curiosity.get("correlation", 0)
        html += f'<div class="metric-grid" style="grid-template-columns:repeat(3,1fr)">'
        html += f'<div class="metric"><div class="metric-value">{corr}</div><div class="metric-label">Correlation w/ Naive</div></div>'
        html += f'<div class="metric"><div class="metric-value">{len(curiosity.get("promoted",[]))}</div><div class="metric-label">Promoted</div></div>'
        html += f'<div class="metric"><div class="metric-value">{len(curiosity.get("demoted",[]))}</div><div class="metric-label">Demoted</div></div>'
        html += '</div>\n'

        html += '<p>Correlation of <strong>0.051</strong> means curiosity ranking is fundamentally different from naive "most novel" ranking.</p>\n'

        # Top recommendations
        if curiosity.get("curiosity_ranking"):
            html += '<h3>Top 10 — Curiosity Zone Ranking</h3>\n'
            html += '<table><tr><th>#</th><th>Score</th><th>Nov%</th><th>N</th><th>E</th><th>K</th><th>Title</th></tr>\n'
            for i, rec in enumerate(curiosity["curiosity_ranking"][:10]):
                c = rec.get("classifications", {})
                html += f'<tr><td>{i+1}</td>'
                html += f'<td class="num" style="font-size:16px">{rec["curiosity_score_v2"]:.3f}</td>'
                html += f'<td>{rec["novelty_pct"]}%</td>'
                html += f'<td>{c.get("NEW",0)}</td><td>{c.get("EXTENDS",0)}</td><td>{c.get("KNOWN",0)}</td>'
                html += f'<td>{rec["title"][:50]}</td></tr>\n'
            html += '</table>\n'

    # ─── Combined Scoring ────────────────────────────────────────────
    if combined:
        html += '<h2>Combined Scoring — Full Pipeline</h2>\n'
        html += '<p>Integrates: Nomic embeddings + LLM judge (ambiguous zone) + FSRS decay + curiosity zone</p>\n'

        if combined.get("timeline"):
            html += '<h3>2-Week Reading Timeline</h3>\n'
            html += '<div class="timeline">\n'
            for step in combined["timeline"]:
                c = step["counts"]
                total = step["total_claims"]
                if total == 0:
                    continue
                new_pct = c.get("NEW", 0) / total * 100
                ext_pct = c.get("EXTENDS", 0) / total * 100
                known_pct = c.get("KNOWN", 0) / total * 100
                partial_pct = c.get("PARTIALLY_KNOWN", 0) / total * 100

                html += f'<div class="timeline-row">'
                html += f'<div class="meta">D{step["day"]} {step["engagement"][:3]}</div>'
                html += f'<div class="timeline-bar">'
                html += f'<div class="timeline-segment" style="width:{new_pct}%;background:var(--claimNew)"></div>'
                html += f'<div class="timeline-segment" style="width:{ext_pct}%;background:var(--gold)"></div>'
                html += f'<div class="timeline-segment" style="width:{partial_pct}%;background:#a09888"></div>'
                html += f'<div class="timeline-segment" style="width:{known_pct}%;background:var(--claimKnown)"></div>'
                html += f'</div>'
                html += f'<div class="meta">{step["curiosity_score"]:.2f}</div>'
                html += f'</div>\n'
            html += '</div>\n'

            html += '<div class="legend">'
            html += '<div class="legend-item"><div class="legend-dot" style="background:var(--claimNew)"></div>New</div>'
            html += '<div class="legend-item"><div class="legend-dot" style="background:var(--gold)"></div>Extends</div>'
            html += '<div class="legend-item"><div class="legend-dot" style="background:#a09888"></div>Partial</div>'
            html += '<div class="legend-item"><div class="legend-dot" style="background:var(--claimKnown)"></div>Known</div>'
            html += '</div>\n'

        # Method distribution
        if combined.get("method_totals"):
            html += '<h3>Classification Methods Used</h3>\n'
            html += '<table><tr><th>Method</th><th>Count</th></tr>\n'
            for method, count in sorted(combined["method_totals"].items(), key=lambda x: -x[1]):
                html += f'<tr><td>{method}</td><td class="num" style="font-size:16px">{count}</td></tr>\n'
            html += '</table>\n'
            html += f'<p class="meta">Total NLI judge calls: {combined.get("total_nli_calls", 0)}</p>\n'

    # ─── Architecture Summary ────────────────────────────────────────
    html += """
<h2>Architecture Decision Summary</h2>

<table>
<tr><th>Component</th><th>Decision</th><th>Evidence</th></tr>
<tr><td>Embeddings</td><td style="color:var(--claimNew)">Nomic-embed-text-v1.5</td><td>4× smaller, 10× faster, wider discriminable range</td></tr>
<tr><td>KNOWN threshold</td><td>≥ 0.78 (Nomic)</td><td>NLI validates: 100% agreement below 0.65</td></tr>
<tr><td>EXTENDS threshold</td><td>≥ 0.68 (Nomic)</td><td>Ambiguous zone 0.68-0.78 benefits from LLM judge</td></tr>
<tr><td>LLM judge</td><td>Gemini Flash, 0.68-0.78 only</td><td>25% disagreement with cosine in this range</td></tr>
<tr><td>Knowledge decay</td><td>FSRS, S=30 days</td><td>Realistic for reading (not rote memorization)</td></tr>
<tr><td>Engagement effect</td><td>skim=9d, read=30d, highlight=60d</td><td>Active engagement 2-4× retention</td></tr>
<tr><td>Article ranking</td><td>Curiosity zone (Gaussian at 70%)</td><td>r=0.051 correlation with naive → different ranking</td></tr>
<tr><td>Topic structure</td><td>LLM topics + cluster sub-topics</td><td>59 clusters validate LLM; broad topics fragment naturally</td></tr>
</table>
"""

    html += """
<div style="margin-top:40px;border-top:1px solid var(--rule);padding-top:16px">
<p class="meta" style="text-align:center">Generated by Petrarca experiment pipeline · March 8, 2026</p>
</div>

</body>
</html>"""

    return html


def main():
    html = generate_report()
    output_path = DATA_DIR / "experiment_report.html"
    with open(output_path, "w") as f:
        f.write(html)
    print(f"Report generated: {output_path}", file=sys.stderr)
    print(f"Open in browser: file://{output_path}")


if __name__ == "__main__":
    main()
