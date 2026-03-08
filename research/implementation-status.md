# Knowledge System Implementation Status

**Date**: March 8, 2026
**Status**: V1 deployed, UI polish needed
**Commit**: `426237e` — "Add knowledge-aware reading system"

---

## What Was Built

On March 8, 2026, the full knowledge-aware reading system was implemented end-to-end based on the design in `research/novelty-system-architecture.md` and validated by 11 experiments documented in `research/experiment-results-report.md`.

### Architecture Overview

The system splits into **server-computed INDEX** (user-independent) and **client-side LEDGER** (user-specific):

```
Server Pipeline (cron every 4 hours):
  Twitter + Readwise → build_articles.py --claims → atomic claims
  → build_claim_embeddings.py → Nomic-embed-text-v1.5 (768-dim)
  → build_knowledge_index.py → knowledge_index.json (served via nginx)

App (Expo SDK 54):
  content-sync.ts downloads knowledge_index.json
  → knowledge-engine.ts classifies claims against user's ledger
  → paragraph dimming, curiosity scoring, delta reports
  → AsyncStorage persists knowledge ledger (@petrarca/knowledge_ledger)
```

### Files Created/Modified

#### New Files

| File | Description |
|------|-------------|
| `app/data/knowledge-engine.ts` | Core knowledge engine — FSRS decay, claim classification, paragraph dimming, curiosity scoring, knowledge ledger persistence. Module-level state (singleton). |
| `app/data/queue.ts` | Reading queue with AsyncStorage persistence. Add/remove/list queued article IDs. |
| `app/app/(tabs)/topics.tsx` | Topics screen — articles grouped by broad topic, expandable clusters with delta report summaries and top claims. |
| `app/app/(tabs)/queue.tsx` | Queue screen — saved-for-later articles with swipe-to-remove. |
| `scripts/build_knowledge_index.py` | Server pipeline — loads articles + Nomic embeddings, computes cosine similarity matrix, extracts cross-article pairs, builds paragraph mappings, generates LLM delta reports (Gemini Flash via litellm). Outputs `data/knowledge_index.json`. |
| `scripts/deploy_knowledge_index.sh` | Deploys knowledge_index.json to nginx + updates manifest hash. Supports `--local` mode. |

#### Modified Files

| File | Changes |
|------|---------|
| `app/data/types.ts` | Added 9 types: `KnowledgeIndex`, `DeltaReport`, `NoveltyClassification`, `ClaimKnowledgeEntry`, `ClaimClassification`, `ParagraphDimming`, `ArticleNovelty` |
| `app/data/content-sync.ts` | Downloads `knowledge_index.json` alongside articles. Added `KNOWLEDGE_INDEX_URL`, `knowledge_index_hash` to manifest checking, graceful fallback if index doesn't exist. |
| `app/data/store.ts` | Imports and initializes knowledge engine + queue in `initStore()`. Exports wrapper functions. Added bundled fallback `require('./knowledge_index.json')`. |
| `app/app/reader.tsx` | 3 reading modes (Full/Guided/New Only), paragraph dimming via `blockDimming` map, collapsible familiar sections (`CollapsedBar` component), "What's new for you" claims card, `ReadingModeToggle` component, `buildParagraphToBlockMap()` for mapping pipeline paragraph indices to markdown block indices. Calls `markArticleEncountered()` on Done. |
| `app/app/(tabs)/index.tsx` | Curiosity-zone re-ranking (with 0.05 threshold for stability), topic filter chips (horizontal ScrollView), swipe-right-to-queue, novelty hints ("N new claims"), `ContinueReadingCard` component (limited to 2 most recent). |
| `app/app/(tabs)/_layout.tsx` | 3-tab layout: Feed / Topics / Queue. Text-only labels (EB Garamond), rubric dot active indicator. |
| `scripts/content-refresh.sh` | Added Step 4: `build_knowledge_index.py`. Added `knowledge_index.json` to file copy loops. |

### Data Generated

| File | Size | Contents |
|------|------|----------|
| `data/knowledge_index.json` | 932 KB | 858 claims, 8,863 similarity pairs (≥0.68), 47 article paragraph maps, article novelty matrix, 116 LLM delta reports |
| `data/claim_embeddings_nomic.npz` | 2.4 MB | 858 × 768 Nomic-embed-text-v1.5 embeddings |
| `data/articles.json` | ~2 MB | 47 articles with `atomic_claims[]` (10-30 claims each) |

### Algorithm Parameters (validated by experiments)

| Parameter | Value | Source |
|-----------|-------|--------|
| KNOWN threshold | ≥ 0.78 cosine | Nomic calibration experiment |
| EXTENDS threshold | ≥ 0.68 cosine | Nomic calibration experiment |
| FORGOTTEN threshold | R < 0.3 | FSRS standard |
| Stability (skim) | 9 days | FSRS experiment |
| Stability (read) | 30 days | FSRS experiment |
| Stability (highlight) | 60 days | FSRS experiment |
| Reinforcement factor | 2.5× | FSRS standard |
| Curiosity peak | 70% novelty | Curiosity zone experiment |
| Curiosity Gaussian σ | 0.15 | Curiosity zone experiment |
| Similarity index threshold | ≥ 0.68 | Pairs below this are always NEW |
| Feed re-rank threshold | 0.05 | Prevents unstable sorts when scores are close |

---

## Deployment Status

### Server (Hetzner: alifstian.duckdns.org)

| Component | Status | Notes |
|-----------|--------|-------|
| nginx content server (:8083) | ✅ Working | Serves articles.json, knowledge_index.json, manifest.json |
| Static web app (:8084) | ✅ Deployed | Rebuilt with `npx expo export --platform web`, `/content/` proxied to :8083 |
| Expo native (:8082) | ✅ Running | systemd `petrarca-expo`, pulled latest commit |
| knowledge_index.json | ✅ Deployed | 932KB with 116 delta reports |
| articles.json | ✅ 47 articles with claims | Server backup of original 171 articles at `articles_backup_171.json` |
| claim_embeddings_nomic.npz | ✅ Uploaded | 2.4MB, 858 embeddings |
| manifest.json | ✅ Updated | Has `knowledge_index_hash` field |
| Python deps | ✅ numpy + litellm installed | In `/opt/petrarca/.venv` |
| Cron pipeline | ⚠️ Partially working | `content-refresh.sh` updated, but Nomic model not installed (can't generate embeddings for new articles) |

### SSH Access
- Use `ssh alif` (configured in `~/.ssh/config` → `root@46.225.75.29` via `~/.ssh/hetzner_ed25519`)

---

## Known Issues & Bugs

### UI Issues (from user screenshot, Mar 8)

1. **Filter chips row clipped** — `maxHeight: 40` on the horizontal ScrollView cuts off chip text. **FIX APPLIED** (changed to `flexGrow: 0`) but not yet deployed.
2. **Continue Reading section too large** — shows all in-progress articles (user had 5), pushing feed below fold. **FIX APPLIED** (limited to 2 most recent) but not yet deployed.
3. **Continue Reading cards have card-like backgrounds** — too heavy visually. **FIX APPLIED** (removed parchmentDark background) but not yet deployed.
4. **UI not visually tested** — Agent only did TypeScript compilation and bundle checks, did not use agent-browser or screenshot verification. **Must visually verify all screens before considering done.**

### Data Issues

5. **Server has only 47 articles** — Original 171-article corpus backed up as `articles_backup_171.json`. Need to run `build_articles.py --claims-only` on full corpus, re-embed, rebuild index.
6. **Nomic model not installed on server** — `sentence-transformers` + `nomic-embed-text-v1.5` needed for cron to auto-embed new articles.
7. **GEMINI_KEY on server** — Needs verification in `/opt/petrarca/.env` for delta report generation during cron.

### Logic Issues

8. **Reading mode toggle shows even when no dimming** — Fixed: now checks `Array.from(blockDimming.values()).some(d => d.opacity < 1)`.
9. **Feed sort unstable with empty ledger** — Fixed: added 0.05 threshold + rank tiebreaker so interest model order is preserved until curiosity scores meaningfully diverge.
10. **Paragraph-to-block mapping is heuristic** — `buildParagraphToBlockMap()` uses text prefix matching (first 50 chars). May mismap in articles with repeated paragraph openings.

---

## How the Knowledge System Works (User Perspective)

### First Use (Empty Ledger)
1. All claims classify as NEW (no ledger entries to compare against)
2. Feed shows articles ranked by interest model (curiosity scoring has no effect yet)
3. Reader shows "What's new for you" card with novel claims from the knowledge index
4. Reading mode toggle does NOT appear (no familiar blocks to dim)
5. User reads article → Done → claims recorded in ledger with stability=30d

### After Reading Several Articles
1. Open an article on a related topic → knowledge engine finds similar claims via cosine similarity
2. Claims matching ledger entries at ≥0.78 → KNOWN, ≥0.68 → EXTENDS, <0.68 → NEW
3. Paragraph dimming computed: familiar paragraphs get opacity 0.55, novel get 1.0, mixed get blended
4. Reading mode toggle appears:
   - **Full** — all content at normal opacity
   - **Guided** — familiar paragraphs dimmed (opacity from dimming map)
   - **New Only** — familiar blocks collapsed into "N familiar sections" bars, tap to expand
5. Feed re-ranks: articles with ~70% novelty ratio score highest (curiosity zone)

### Knowledge Decay
- Claims fade over time: R = e^(-t/S) where S = stability_days
- Skim=9d, Read=30d, Highlight=60d
- Re-reading reinforces: stability × 2.5
- Forgotten when R < 0.3 → claim treated as unknown again

### Topics & Delta Reports
- Topics tab groups articles by broad topic from `interest_topics`
- Expanding a topic shows the LLM-generated delta report: "What's new in [topic]"
- Delta reports are pre-generated by `build_knowledge_index.py` using Gemini Flash
- Each report: summary paragraph + top 5 claims

---

## Next Steps (Priority Order)

### Immediate (before daily use)
1. **Deploy UI fixes** — filter chips, continue reading limits, card styling. Commit + push + rebuild on server.
2. **Visual testing** — Use agent-browser or Expo Go to verify every screen on mobile before declaring done.
3. **Verify GEMINI_KEY** on server `/opt/petrarca/.env`

### Short-term (enable full pipeline)
4. **Restore full article corpus** — Run `build_articles.py --claims-only` on server's 171 articles → re-embed → rebuild index
5. **Install Nomic model on server** — `pip install sentence-transformers` in venv, download `nomic-embed-text-v1.5`
6. **Add embedding step to cron** — `build_claim_embeddings.py` needs to run incrementally (embed only new claims)
7. **Production bundle optimization** — Remove bundled `knowledge_index.json` from JS (load from server only, cache in AsyncStorage)

### Medium-term (feature completion)
8. **LLM judge for ambiguous range** — Claims with 0.68-0.78 cosine similarity get LLM verification (cosine overestimates in this range)
9. **Sub-topic splitting** — Use embedding clusters for broad topics like "ai-agents" (110 claims)
10. **Micro-delights** — Pull-to-refresh ornament, claim reveal animations, completion flash
11. **Entry row sidebar** — Design system calls for 76px sidebar with large numbers + depth dots (not yet implemented in feed)

### Longer-term
12. **Contradiction detection** — Current corpus too harmonious (mostly tech blogs). Needs diverse sources.
13. **Research agent button** — Capture ideas while reading → spawn background research
14. **Voice notes** — Record → Soniox transcription → link to reading context

---

## Key Design Documents

| Document | Purpose |
|----------|---------|
| `research/system-state-of-the-art.md` | **START HERE** — Comprehensive reference covering all research, algorithms, data structures, experiments, UI mockups |
| `research/novelty-system-architecture.md` | Architecture design for the knowledge-aware system |
| `research/experiment-results-report.md` | Results from 11 validation experiments |
| `research/experiment-log.md` | Append-only chronological experiment log |
| `research/ux-redesign-spec.md` | 2 rounds of mockup feedback, approved interaction models |
| `design/DESIGN_GUIDE.md` | The Annotated Folio design system specification |
| `research/knowledge-diff-interfaces.md` | HCI research on adaptive presentation (dimming, stretchtext) |
| `research/knowledge-tracing-for-reading.md` | FSRS/BKT adaptation for reading knowledge |
| `research/knowledge-deduplication.md` | Embedding + dedup architecture |

## Key Scripts

| Script | Purpose |
|--------|---------|
| `scripts/build_articles.py --claims` | Extract atomic claims from articles (Gemini Flash) |
| `scripts/build_claim_embeddings.py` | Generate Nomic embeddings for all claims |
| `scripts/build_knowledge_index.py` | Build knowledge_index.json from embeddings |
| `scripts/build_knowledge_index.py --skip-delta` | Build without LLM delta reports (faster) |
| `scripts/deploy_knowledge_index.sh` | Deploy to nginx + update manifest |
| `scripts/deploy_knowledge_index.sh --local` | Update local copies only |
| `scripts/content-refresh.sh` | Full cron pipeline (fetch → extract → embed → index → deploy) |
| `scripts/simulate_reading.py` | Simulate reading journeys for testing |
| `scripts/experiment_*.py` | 11 experiment scripts (see experiment-results-report.md) |
