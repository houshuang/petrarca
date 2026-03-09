#!/usr/bin/env python3
"""Experiment: Interactive knowledge map visualization.

Builds a D3.js force-directed graph showing articles as nodes connected
by shared claims. Uses UMAP for initial positioning and embeds everything
into a self-contained HTML file with Annotated Folio styling.

Usage:
    python3 scripts/experiment_knowledge_map.py
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

import numpy as np

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
ARTICLES_PATH = DATA_DIR / "articles.json"
EMBEDDINGS_PATH = DATA_DIR / "claim_embeddings_nomic.npz"
CROSS_LINKS_PATH = DATA_DIR / "experiment_cross_article_links.json"


def load_data():
    with open(ARTICLES_PATH) as f:
        articles = json.load(f)

    # Load embeddings
    data = np.load(EMBEDDINGS_PATH)
    embeddings = data["embeddings"]

    # Build claim index
    claims = []
    article_claim_indices = defaultdict(list)
    for article in articles:
        for claim in article.get("atomic_claims", []):
            idx = len(claims)
            claims.append({**claim, "article_id": article.get("id", "")})
            article_claim_indices[article.get("id", "")].append(idx)

    return articles, claims, embeddings, article_claim_indices


def compute_article_embeddings(articles, claims, embeddings, article_claim_indices):
    """Average claim embeddings per article."""
    article_embeddings = []
    for article in articles:
        aid = article.get("id", "")
        indices = article_claim_indices.get(aid, [])
        if indices:
            article_embeddings.append(np.mean(embeddings[indices], axis=0))
        else:
            article_embeddings.append(np.zeros(embeddings.shape[1]))
    return np.array(article_embeddings)


def compute_article_similarity(articles, claims, embeddings, article_claim_indices):
    """Compute pairwise article similarity and shared claim counts."""
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normed = embeddings / norms
    similarity = normed @ normed.T

    edges = []
    n = len(articles)
    for i in range(n):
        aid_a = articles[i].get("id", "")
        idx_a = article_claim_indices.get(aid_a, [])
        if not idx_a:
            continue
        for j in range(i + 1, n):
            aid_b = articles[j].get("id", "")
            idx_b = article_claim_indices.get(aid_b, [])
            if not idx_b:
                continue

            # Count high-similarity claim pairs
            high_pairs = 0
            for a in idx_a:
                for b in idx_b:
                    if float(similarity[a, b]) >= 0.68:
                        high_pairs += 1

            if high_pairs >= 3:
                # Compute average best-match similarity
                best_a = [max(float(similarity[a, b]) for b in idx_b) for a in idx_a]
                best_b = [max(float(similarity[b, a]) for a in idx_a) for b in idx_b]
                avg_sim = (np.mean(best_a) + np.mean(best_b)) / 2

                edges.append({
                    "source": i,
                    "target": j,
                    "shared_claims": high_pairs,
                    "similarity": round(float(avg_sim), 3),
                })

    return edges


def run_umap(article_embeddings):
    """Run UMAP for 2D layout."""
    try:
        import umap
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "umap-learn"])
        import umap

    reducer = umap.UMAP(n_components=2, metric="cosine", random_state=42,
                        n_neighbors=8, min_dist=0.3)
    coords = reducer.fit_transform(article_embeddings)

    # Normalize to [50, 950] for SVG
    for dim in range(2):
        mn, mx = coords[:, dim].min(), coords[:, dim].max()
        if mx > mn:
            coords[:, dim] = 50 + 900 * (coords[:, dim] - mn) / (mx - mn)
        else:
            coords[:, dim] = 500

    return coords


def classify_topic(topics):
    """Assign a broad category for coloring."""
    topic_colors = {
        "ai": 0, "agent": 0, "llm": 0, "claude": 0, "coding": 0,
        "history": 1, "ottoman": 1, "medieval": 1, "ancient": 1, "byzantine": 1,
        "literature": 2, "poetry": 2, "fiction": 2, "book": 2, "reading": 2,
        "tool": 3, "developer": 3, "software": 3, "rust": 3,
        "knowledge": 4, "learning": 4, "research": 4,
    }
    for topic in topics:
        for keyword, category in topic_colors.items():
            if keyword in topic.lower():
                return category
    return 5  # Other


def generate_html(nodes, edges):
    """Generate self-contained D3.js knowledge map HTML."""

    # Color palette (Annotated Folio earth tones)
    colors = [
        "#8b2500",  # rubric (AI/agents)
        "#5b7553",  # muted green (history)
        "#9b7e4a",  # gold (literature)
        "#6a6458",  # warm gray (developer tools)
        "#2a7a4a",  # claimNew green (knowledge)
        "#7a6b8a",  # muted purple (other)
    ]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Petrarca — Knowledge Map</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600&family=Crimson+Pro:wght@400;500&family=DM+Sans:wght@400;500&family=EB+Garamond:ital,wght@0,400;0,500;1,400&display=swap');

:root {{
  --parchment: #f7f4ec;
  --ink: #2a2420;
  --rubric: #8b2500;
  --rule: #e4dfd4;
  --gold: #c9a84c;
}}

* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: 'Crimson Pro', Georgia, serif; background: var(--parchment); color: var(--ink); overflow: hidden; }}

.header {{
  position: fixed; top: 0; left: 0; right: 0; z-index: 100;
  background: var(--parchment); padding: 16px 24px 0;
}}
.header h1 {{ font-family: 'Cormorant Garamond', serif; font-weight: 600; font-size: 28px; }}
.header .subtitle {{ font-family: 'DM Sans', sans-serif; font-size: 11px; color: #6a6458; letter-spacing: 1px; text-transform: uppercase; margin-top: 2px; }}
.double-rule {{ border-top: 2px solid var(--ink); margin-top: 6px; padding-top: 4px; border-bottom: 1px solid var(--ink); height: 0; }}

#graph {{ width: 100vw; height: 100vh; cursor: grab; }}
#graph:active {{ cursor: grabbing; }}

.tooltip {{
  position: fixed; pointer-events: none; z-index: 200;
  background: white; border: 1px solid var(--rule); border-radius: 4px;
  padding: 12px 16px; max-width: 380px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  display: none;
}}
.tooltip h3 {{ font-family: 'EB Garamond', serif; font-size: 15px; color: var(--rubric); margin-bottom: 6px; }}
.tooltip .meta {{ font-family: 'DM Sans', sans-serif; font-size: 10px; color: #6a6458; margin-bottom: 8px; }}
.tooltip .claims {{ font-family: 'Crimson Pro', serif; font-size: 13px; line-height: 1.5; color: #333; }}
.tooltip .claim-item {{ padding: 2px 0; border-left: 2px solid var(--rule); padding-left: 8px; margin: 4px 0; }}

.sidebar {{
  position: fixed; top: 80px; right: 16px; z-index: 100;
  background: white; border: 1px solid var(--rule); border-radius: 4px;
  padding: 12px 16px; width: 200px; max-height: calc(100vh - 100px); overflow-y: auto;
}}
.sidebar h3 {{ font-family: 'EB Garamond', serif; text-transform: uppercase; letter-spacing: 1.5px; font-size: 11px; color: var(--rubric); margin-bottom: 8px; }}
.sidebar h3::before {{ content: '✦ '; }}
.filter-item {{
  font-family: 'DM Sans', sans-serif; font-size: 11px; display: flex; align-items: center; gap: 6px;
  padding: 3px 0; cursor: pointer;
}}
.filter-item input {{ accent-color: var(--rubric); }}
.filter-dot {{ width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }}

.search-box {{
  position: fixed; top: 80px; left: 16px; z-index: 100;
}}
.search-box input {{
  font-family: 'DM Sans', sans-serif; font-size: 12px;
  padding: 6px 12px; border: 1px solid var(--rule); border-radius: 4px;
  background: white; color: var(--ink); width: 220px; outline: none;
}}
.search-box input:focus {{ border-color: var(--rubric); }}

.stats {{
  position: fixed; bottom: 16px; left: 16px; z-index: 100;
  font-family: 'DM Sans', sans-serif; font-size: 10px; color: #6a6458;
}}
</style>
</head>
<body>

<div class="header">
  <h1>Knowledge Map</h1>
  <p class="subtitle">Articles connected by shared claims</p>
  <div class="double-rule"></div>
</div>

<div class="search-box">
  <input type="text" id="search" placeholder="Search articles..." />
</div>

<div class="sidebar" id="sidebar">
  <h3>Topics</h3>
  <div id="filters"></div>
</div>

<div class="tooltip" id="tooltip"></div>

<svg id="graph"></svg>

<div class="stats" id="stats"></div>

<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
const nodes = {json.dumps(nodes)};
const edges = {json.dumps(edges)};
const colors = {json.dumps(colors)};

const categories = ['AI & Agents', 'History', 'Literature', 'Developer Tools', 'Knowledge', 'Other'];
const activeCategories = new Set(categories.map((_, i) => i));

const width = window.innerWidth;
const height = window.innerHeight;

const svg = d3.select('#graph')
  .attr('width', width)
  .attr('height', height);

const g = svg.append('g');

// Zoom
const zoom = d3.zoom()
  .scaleExtent([0.3, 5])
  .on('zoom', (e) => g.attr('transform', e.transform));
svg.call(zoom);

// Initial transform to center
svg.call(zoom.transform, d3.zoomIdentity.translate(width * 0.1, height * 0.15).scale(0.8));

// Build simulation
const simulation = d3.forceSimulation(nodes)
  .force('link', d3.forceLink(edges).id((d, i) => i).distance(d => 200 - d.shared_claims * 10).strength(d => d.shared_claims * 0.02))
  .force('charge', d3.forceManyBody().strength(-120))
  .force('center', d3.forceCenter(width / 2, height / 2))
  .force('collision', d3.forceCollide().radius(d => d.radius + 5))
  .force('x', d3.forceX(d => d.x).strength(0.15))
  .force('y', d3.forceY(d => d.y).strength(0.15));

// Draw edges
const linkGroup = g.append('g');
const link = linkGroup.selectAll('line')
  .data(edges)
  .join('line')
  .attr('stroke', '#e4dfd4')
  .attr('stroke-opacity', d => Math.min(0.8, 0.1 + d.shared_claims * 0.03))
  .attr('stroke-width', d => Math.min(4, 0.5 + d.shared_claims * 0.1));

// Draw nodes
const nodeGroup = g.append('g');
const node = nodeGroup.selectAll('circle')
  .data(nodes)
  .join('circle')
  .attr('r', d => d.radius)
  .attr('fill', d => colors[d.category] || colors[5])
  .attr('fill-opacity', 0.75)
  .attr('stroke', '#fff')
  .attr('stroke-width', 1.5)
  .attr('cursor', 'pointer')
  .call(d3.drag()
    .on('start', dragStart)
    .on('drag', dragging)
    .on('end', dragEnd));

// Labels for large nodes
const label = g.append('g').selectAll('text')
  .data(nodes.filter(d => d.radius >= 10))
  .join('text')
  .attr('font-family', 'DM Sans, sans-serif')
  .attr('font-size', '9px')
  .attr('fill', '#6a6458')
  .attr('text-anchor', 'middle')
  .attr('dy', d => d.radius + 12)
  .text(d => d.title.length > 30 ? d.title.slice(0, 28) + '...' : d.title);

// Tooltip
const tooltip = document.getElementById('tooltip');

node.on('mouseover', function(event, d) {{
  d3.select(this).attr('stroke', '#8b2500').attr('stroke-width', 2.5);

  // Highlight connected
  const connectedIds = new Set();
  edges.forEach(e => {{
    const si = typeof e.source === 'object' ? e.source.index : e.source;
    const ti = typeof e.target === 'object' ? e.target.index : e.target;
    if (si === d.index) connectedIds.add(ti);
    if (ti === d.index) connectedIds.add(si);
  }});

  node.attr('fill-opacity', n => n.index === d.index || connectedIds.has(n.index) ? 0.9 : 0.15);
  link.attr('stroke-opacity', l => {{
    const si = typeof l.source === 'object' ? l.source.index : l.source;
    const ti = typeof l.target === 'object' ? l.target.index : l.target;
    return (si === d.index || ti === d.index) ? 0.7 : 0.03;
  }});

  let claimsHtml = d.top_claims.map(c =>
    `<div class="claim-item">${{c}}</div>`
  ).join('');

  tooltip.innerHTML = `
    <h3>${{d.title}}</h3>
    <div class="meta">${{d.n_claims}} claims · ${{d.topics.join(', ')}}</div>
    <div class="claims">${{claimsHtml}}</div>
  `;
  tooltip.style.display = 'block';
  tooltip.style.left = (event.clientX + 15) + 'px';
  tooltip.style.top = (event.clientY - 10) + 'px';
}})
.on('mousemove', function(event) {{
  tooltip.style.left = (event.clientX + 15) + 'px';
  tooltip.style.top = (event.clientY - 10) + 'px';
}})
.on('mouseout', function() {{
  node.attr('fill-opacity', 0.75);
  link.attr('stroke-opacity', d => Math.min(0.8, 0.1 + d.shared_claims * 0.03));
  d3.select(this).attr('stroke', '#fff').attr('stroke-width', 1.5);
  tooltip.style.display = 'none';
}});

// Simulation tick
simulation.on('tick', () => {{
  link
    .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
    .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
  node.attr('cx', d => d.x).attr('cy', d => d.y);
  label.attr('x', d => d.x).attr('y', d => d.y);
}});

// Drag handlers
function dragStart(event, d) {{
  if (!event.active) simulation.alphaTarget(0.3).restart();
  d.fx = d.x; d.fy = d.y;
}}
function dragging(event, d) {{
  d.fx = event.x; d.fy = event.y;
}}
function dragEnd(event, d) {{
  if (!event.active) simulation.alphaTarget(0);
  d.fx = null; d.fy = null;
}}

// Filters
const filtersEl = document.getElementById('filters');
categories.forEach((cat, i) => {{
  const div = document.createElement('div');
  div.className = 'filter-item';
  div.innerHTML = `<input type="checkbox" checked data-cat="${{i}}">
    <span class="filter-dot" style="background:${{colors[i]}}"></span>${{cat}}`;
  div.querySelector('input').addEventListener('change', function() {{
    if (this.checked) activeCategories.add(i);
    else activeCategories.delete(i);
    node.attr('display', d => activeCategories.has(d.category) ? null : 'none');
    label.attr('display', d => activeCategories.has(d.category) ? null : 'none');
  }});
  filtersEl.appendChild(div);
}});

// Search
document.getElementById('search').addEventListener('input', function() {{
  const q = this.value.toLowerCase();
  if (!q) {{
    node.attr('fill-opacity', 0.75).attr('stroke', '#fff').attr('stroke-width', 1.5);
    return;
  }}
  node.attr('fill-opacity', d => d.title.toLowerCase().includes(q) ? 1.0 : 0.12)
    .attr('stroke', d => d.title.toLowerCase().includes(q) ? '#8b2500' : '#fff')
    .attr('stroke-width', d => d.title.toLowerCase().includes(q) ? 2.5 : 1.5);
}});

// Stats
document.getElementById('stats').textContent =
  `${{nodes.length}} articles · ${{edges.length}} connections · ${{nodes.reduce((s, n) => s + n.n_claims, 0)}} claims`;
</script>
</body>
</html>"""
    return html


def main():
    print("Loading data...", file=sys.stderr)
    articles, claims, embeddings, article_claim_indices = load_data()
    print(f"  {len(articles)} articles, {len(claims)} claims", file=sys.stderr)

    # Compute article-level embeddings
    print("Computing article embeddings...", file=sys.stderr)
    article_embeddings = compute_article_embeddings(
        articles, claims, embeddings, article_claim_indices)

    # Run UMAP for layout
    print("Running UMAP...", file=sys.stderr)
    coords = run_umap(article_embeddings)

    # Compute edges
    print("Computing article similarity...", file=sys.stderr)
    edges = compute_article_similarity(
        articles, claims, embeddings, article_claim_indices)
    print(f"  {len(edges)} edges (≥3 shared claims)", file=sys.stderr)

    # Build node data
    nodes = []
    for i, article in enumerate(articles):
        aid = article.get("id", "")
        article_claims_list = [c for c in claims if c["article_id"] == aid]
        top_claims = [c["normalized_text"][:100] for c in article_claims_list[:4]]

        # Aggregate topics from claims
        from collections import Counter
        topic_counts = Counter()
        for c in article_claims_list:
            for t in c.get("topics", []):
                topic_counts[t] += 1
        topics = [t for t, _ in topic_counts.most_common(3)]

        nodes.append({
            "index": i,
            "title": article.get("title", "")[:80],
            "x": float(coords[i, 0]),
            "y": float(coords[i, 1]),
            "topics": topics,
            "n_claims": len(article_claims_list),
            "radius": max(5, min(20, len(article_claims_list) * 0.7)),
            "category": classify_topic(topics),
            "top_claims": top_claims,
        })

    # Generate HTML
    print("Generating visualization...", file=sys.stderr)
    html = generate_html(nodes, edges)

    output_path = DATA_DIR / "knowledge_map.html"
    with open(output_path, "w") as f:
        f.write(html)
    print(f"\n  Knowledge map: {output_path}", file=sys.stderr)

    # Stats
    print(f"\n  Nodes: {len(nodes)}", file=sys.stderr)
    print(f"  Edges: {len(edges)}", file=sys.stderr)
    categories = defaultdict(int)
    for n in nodes:
        categories[n["category"]] += 1
    cat_names = ['AI/Agents', 'History', 'Literature', 'Dev Tools', 'Knowledge', 'Other']
    for cat_id, count in sorted(categories.items()):
        name = cat_names[cat_id] if cat_id < len(cat_names) else 'Other'
        print(f"  {name}: {count} articles", file=sys.stderr)


if __name__ == "__main__":
    main()
