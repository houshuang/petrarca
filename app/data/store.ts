import { Article, ReadingState, UserSignal, ReadingDepth, Concept, ConceptState, ConceptKnowledgeLevel } from './types';
import { logEvent } from './logger';
import { loadSignals, saveSignals, loadReadingStates, saveReadingStates, loadConceptStates, saveConceptStates } from './persistence';

let articles: Article[] = [];
let concepts: Concept[] = [];
let readingStates = new Map<string, ReadingState>();
let conceptStates = new Map<string, ConceptState>();
let signals: UserSignal[] = [];
let initialized = false;
let initPromise: Promise<void> | null = null;

// Precomputed: article_id -> concept_ids
let articleConceptIndex = new Map<string, string[]>();

export async function initStore(): Promise<void> {
  if (initialized) return;
  if (initPromise) return initPromise;

  initPromise = (async () => {
    // Load articles - try dynamic import, fall back to empty
    try {
      const data = require('./articles.json');
      articles = (Array.isArray(data) ? data : []) as Article[];
    } catch {
      articles = [];
    }

    // Sort by date descending
    articles.sort((a, b) => (b.date || '').localeCompare(a.date || ''));

    // Load concepts
    try {
      const conceptData = require('./concepts.json');
      concepts = (Array.isArray(conceptData) ? conceptData : []) as Concept[];
    } catch {
      concepts = [];
    }

    // Build article->concept index
    articleConceptIndex.clear();
    for (const c of concepts) {
      for (const aid of c.source_article_ids) {
        if (!articleConceptIndex.has(aid)) articleConceptIndex.set(aid, []);
        articleConceptIndex.get(aid)!.push(c.id);
      }
    }

    signals = await loadSignals();
    readingStates = await loadReadingStates();
    conceptStates = await loadConceptStates();
    initialized = true;

    logEvent('store_initialized', {
      total_articles: articles.length,
      total_concepts: concepts.length,
      loaded_signals: signals.length,
      loaded_reading_states: readingStates.size,
      loaded_concept_states: conceptStates.size,
    });
  })();

  return initPromise;
}

export function isInitialized(): boolean {
  return initialized;
}

// --- Article access ---

export function getArticles(): Article[] {
  return articles;
}

export function getArticleById(id: string): Article | undefined {
  return articles.find(a => a.id === id);
}

export function getFeedArticles(): Article[] {
  return articles.filter(a => {
    const state = readingStates.get(a.id);
    return !state || state.depth === 'unread';
  });
}

export function getLibraryArticles(): Article[] {
  return articles
    .filter(a => {
      const state = readingStates.get(a.id);
      return state && state.depth !== 'unread';
    })
    .sort((a, b) => {
      const sa = readingStates.get(a.id);
      const sb = readingStates.get(b.id);
      return (sb?.last_read_at || 0) - (sa?.last_read_at || 0);
    });
}

// --- Reading state ---

export function getReadingState(articleId: string): ReadingState {
  return readingStates.get(articleId) || {
    article_id: articleId,
    depth: 'unread' as ReadingDepth,
    current_section_index: 0,
    last_read_at: 0,
    time_spent_ms: 0,
    started_at: 0,
  };
}

export function updateReadingState(articleId: string, updates: Partial<ReadingState>) {
  const current = getReadingState(articleId);
  const updated = { ...current, ...updates, article_id: articleId };
  readingStates.set(articleId, updated);
  saveReadingStates(readingStates);

  logEvent('reading_state_update', {
    article_id: articleId,
    depth: updated.depth,
    section_index: updated.current_section_index,
    time_spent_ms: updated.time_spent_ms,
  });
}

// --- Signals ---

export function addSignal(signal: UserSignal) {
  signals.push(signal);
  saveSignals(signals);

  const article = getArticleById(signal.article_id);
  logEvent('signal', {
    article_id: signal.article_id,
    signal: signal.signal,
    title: article?.title,
    topics: article?.topics,
    depth: signal.depth,
    section_index: signal.section_index,
  });
}

export function getSignals(): UserSignal[] {
  return [...signals];
}

export function getSignalForArticle(id: string): UserSignal | undefined {
  return signals.findLast(s => s.article_id === id);
}

// --- Topic grouping ---

export function getByTopic(): Map<string, Article[]> {
  const topicMap = new Map<string, Article[]>();
  for (const a of articles) {
    for (const t of a.topics) {
      if (!topicMap.has(t)) topicMap.set(t, []);
      topicMap.get(t)!.push(a);
    }
  }
  return topicMap;
}

// --- Stats ---

export function getStats() {
  const readArticles = articles.filter(a => {
    const s = readingStates.get(a.id);
    return s && s.depth !== 'unread';
  });

  const depthCounts = { summary: 0, claims: 0, sections: 0, full: 0 };
  let totalTimeMs = 0;
  for (const [, state] of readingStates) {
    if (state.depth !== 'unread') {
      depthCounts[state.depth]++;
      totalTimeMs += state.time_spent_ms;
    }
  }

  return {
    total: articles.length,
    read: readArticles.length,
    unread: articles.length - readArticles.length,
    ...depthCounts,
    totalTimeMs,
    signals: signals.length,
    totalConcepts: concepts.length,
    knownConcepts: [...conceptStates.values()].filter(s => s.state === 'known').length,
    encounteredConcepts: [...conceptStates.values()].filter(s => s.state === 'encountered').length,
  };
}

// --- Concepts & Knowledge Model ---

export function getConcepts(): Concept[] {
  return concepts;
}

export function getConceptState(conceptId: string): ConceptState {
  return conceptStates.get(conceptId) || {
    concept_id: conceptId,
    state: 'unknown' as ConceptKnowledgeLevel,
    last_seen: 0,
    signal_count: 0,
  };
}

export function updateConceptState(conceptId: string, state: ConceptKnowledgeLevel) {
  const current = getConceptState(conceptId);
  const updated: ConceptState = {
    ...current,
    concept_id: conceptId,
    state,
    last_seen: Date.now(),
    signal_count: current.signal_count + 1,
  };
  conceptStates.set(conceptId, updated);
  saveConceptStates(conceptStates);

  logEvent('concept_state_update', {
    concept_id: conceptId,
    state,
    signal_count: updated.signal_count,
  });
}

/**
 * When a user signals on a claim, find matching concepts and update their state.
 * "knew_it" -> concept becomes "known"
 * "interesting" -> concept becomes "encountered"
 */
export function processClaimSignalForConcepts(articleId: string, claimText: string, signal: string) {
  const articleConcepts = articleConceptIndex.get(articleId) || [];
  const normalizedClaim = claimText.toLowerCase().replace(/[^\w\s]/g, '');

  for (const cid of articleConcepts) {
    const concept = concepts.find(c => c.id === cid);
    if (!concept) continue;

    const normalizedConcept = concept.text.toLowerCase().replace(/[^\w\s]/g, '');
    // Match if claim text overlaps significantly with concept text
    const claimWords = new Set(normalizedClaim.split(/\s+/));
    const conceptWords = normalizedConcept.split(/\s+/);
    const overlap = conceptWords.filter(w => claimWords.has(w)).length;
    const overlapRatio = conceptWords.length > 0 ? overlap / conceptWords.length : 0;

    if (overlapRatio > 0.4) {
      if (signal === 'knew_it') {
        updateConceptState(cid, 'known');
      } else if (signal === 'interesting') {
        updateConceptState(cid, 'encountered');
      }
    }
  }
}

/**
 * Compute novelty score for an article.
 * Returns 0.0-1.0 where 1.0 = completely novel, 0.0 = all concepts known.
 * Falls back to claim-based estimation when concepts aren't available.
 */
export function getNoveltyScore(articleId: string): number {
  const conceptIds = articleConceptIndex.get(articleId);

  if (conceptIds && conceptIds.length > 0) {
    const unknownCount = conceptIds.filter(cid => {
      const state = conceptStates.get(cid);
      return !state || state.state === 'unknown';
    }).length;
    return unknownCount / conceptIds.length;
  }

  // Fallback: use claim signals from the article
  const article = articles.find(a => a.id === articleId);
  if (!article || article.key_claims.length === 0) return 1.0; // assume novel if no data

  const articleSignals = signals.filter(s => s.article_id === articleId);
  if (articleSignals.length === 0) return 1.0; // not yet interacted

  const knewCount = articleSignals.filter(s => s.signal === 'knew_it').length;
  const totalSignaled = articleSignals.length;
  if (totalSignaled === 0) return 1.0;

  return 1.0 - (knewCount / totalSignaled);
}

/**
 * Get knowledge stats per topic for the dashboard.
 */
export function getTopicKnowledgeStats(): Map<string, { known: number; encountered: number; unknown: number; total: number }> {
  const topicStats = new Map<string, { known: number; encountered: number; unknown: number; total: number }>();

  for (const concept of concepts) {
    const topic = concept.topic;
    if (!topicStats.has(topic)) {
      topicStats.set(topic, { known: 0, encountered: 0, unknown: 0, total: 0 });
    }
    const stats = topicStats.get(topic)!;
    stats.total++;

    const state = conceptStates.get(concept.id);
    if (!state || state.state === 'unknown') {
      stats.unknown++;
    } else if (state.state === 'encountered') {
      stats.encountered++;
    } else if (state.state === 'known') {
      stats.known++;
    }
  }

  return topicStats;
}
