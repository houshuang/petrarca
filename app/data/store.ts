import { Article, ReadingState, UserSignal, ReadingDepth, Concept, ConceptState, ConceptKnowledgeLevel, VoiceNote, ConceptReview, ReviewRating, ConceptNote } from './types';
import { logEvent } from './logger';
import { loadSignals, saveSignals, loadReadingStates, saveReadingStates, loadConceptStates, saveConceptStates, loadVoiceNotes, saveVoiceNotes, loadConceptReviews, saveConceptReviews } from './persistence';

let articles: Article[] = [];
let concepts: Concept[] = [];
let readingStates = new Map<string, ReadingState>();
let conceptStates = new Map<string, ConceptState>();
let conceptReviews = new Map<string, ConceptReview>();
let voiceNotes: VoiceNote[] = [];
let signals: UserSignal[] = [];
let initialized = false;
let initPromise: Promise<void> | null = null;

// Precomputed: article_id -> concept_ids
let articleConceptIndex = new Map<string, string[]>();
const DAY_MS = 24 * 60 * 60 * 1000;

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
    conceptReviews = await loadConceptReviews();
    voiceNotes = await loadVoiceNotes();
    initialized = true;

    logEvent('store_initialized', {
      total_articles: articles.length,
      total_concepts: concepts.length,
      loaded_signals: signals.length,
      loaded_reading_states: readingStates.size,
      loaded_concept_states: conceptStates.size,
      loaded_concept_reviews: conceptReviews.size,
      loaded_voice_notes: voiceNotes.length,
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

export function getInProgressArticles(): Article[] {
  return articles
    .filter(a => {
      const state = readingStates.get(a.id);
      return state && state.depth !== 'unread' && state.depth !== 'full';
    })
    .sort((a, b) => {
      const sa = readingStates.get(a.id);
      const sb = readingStates.get(b.id);
      return (sb?.last_read_at || 0) - (sa?.last_read_at || 0);
    });
}

/**
 * Find articles related to the given article through shared concepts.
 */
export function getRelatedArticles(articleId: string, limit: number = 3): Array<{ article: Article; sharedConcepts: string[] }> {
  const conceptIds = articleConceptIndex.get(articleId) || [];
  if (conceptIds.length === 0) return [];

  const scores = new Map<string, { count: number; concepts: string[] }>();

  for (const cid of conceptIds) {
    const concept = concepts.find(c => c.id === cid);
    if (!concept) continue;

    for (const relatedArticleId of concept.source_article_ids) {
      if (relatedArticleId === articleId) continue;
      if (!scores.has(relatedArticleId)) {
        scores.set(relatedArticleId, { count: 0, concepts: [] });
      }
      const entry = scores.get(relatedArticleId)!;
      entry.count++;
      entry.concepts.push(concept.text);
    }
  }

  return [...scores.entries()]
    .sort((a, b) => b[1].count - a[1].count)
    .slice(0, limit)
    .map(([id, { concepts: sharedConcepts }]) => {
      const article = articles.find(a => a.id === id);
      return article ? { article, sharedConcepts } : null;
    })
    .filter((x): x is { article: Article; sharedConcepts: string[] } => x !== null);
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

  // Create review state if transitioning from unknown
  if (current.state === 'unknown' && state !== 'unknown' && !conceptReviews.has(conceptId)) {
    const review = getOrCreateReview(conceptId);
    // "known" concepts get longer initial interval
    review.stability_days = state === 'known' ? 7 : 1;
    review.due_at = Date.now() + review.stability_days * DAY_MS;
    conceptReviews.set(conceptId, review);
    saveConceptReviews(conceptReviews);
  }

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
const STOP_WORDS = new Set([
  'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
  'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
  'should', 'may', 'might', 'shall', 'can', 'need', 'must',
  'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as',
  'into', 'through', 'during', 'before', 'after', 'above', 'below',
  'and', 'but', 'or', 'nor', 'not', 'so', 'yet', 'both', 'either',
  'that', 'which', 'who', 'whom', 'this', 'these', 'those',
  'it', 'its', 'they', 'them', 'their', 'we', 'our', 'you', 'your',
  'than', 'more', 'most', 'very', 'also', 'just', 'about',
]);

function contentWords(text: string): Set<string> {
  const words = text.toLowerCase().replace(/[^\w\s]/g, '').split(/\s+/).filter(Boolean);
  return new Set(words.filter(w => w.length > 2 && !STOP_WORDS.has(w)));
}

export function processClaimSignalForConcepts(articleId: string, claimText: string, signal: string) {
  const articleConcepts = articleConceptIndex.get(articleId) || [];
  const claimContent = contentWords(claimText);

  for (const cid of articleConcepts) {
    const concept = concepts.find(c => c.id === cid);
    if (!concept) continue;

    const conceptContent = contentWords(concept.text);
    if (conceptContent.size === 0) continue;

    const overlap = [...conceptContent].filter(w => claimContent.has(w)).length;
    const overlapRatio = overlap / conceptContent.size;

    // Lower threshold since we're matching content words only (stop words removed)
    if (overlapRatio > 0.3) {
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
 * Returns null if no data available, or 0.0-1.0 where 1.0 = completely novel.
 */
export function getNoveltyScore(articleId: string): number | null {
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
  if (!article || article.key_claims.length === 0) return null;

  const articleSignals = signals.filter(s => s.article_id === articleId);
  if (articleSignals.length === 0) return null; // no signals yet, can't estimate

  const knewCount = articleSignals.filter(s => s.signal === 'knew_it').length;
  const totalSignaled = articleSignals.length;
  if (totalSignaled === 0) return null;

  return 1.0 - (knewCount / totalSignaled);
}

// --- Voice Notes ---

export function getVoiceNotes(articleId?: string): VoiceNote[] {
  if (articleId) return voiceNotes.filter(n => n.article_id === articleId);
  return voiceNotes;
}

export function addVoiceNote(note: VoiceNote) {
  voiceNotes.push(note);
  saveVoiceNotes(voiceNotes);
  logEvent('voice_note_added', {
    article_id: note.article_id,
    depth: note.depth,
    duration_ms: note.duration_ms,
  });
}

export function updateVoiceNoteTranscript(noteId: string, transcript: string) {
  const note = voiceNotes.find(n => n.id === noteId);
  if (!note) return;
  note.transcript = transcript;
  note.transcription_status = 'completed';
  saveVoiceNotes(voiceNotes);
  logEvent('voice_note_transcribed', { note_id: noteId, article_id: note.article_id });
}

// --- Spaced Attention Scheduling ---

function getOrCreateReview(conceptId: string): ConceptReview {
  const existing = conceptReviews.get(conceptId);
  if (existing) return existing;

  return {
    concept_id: conceptId,
    stability_days: 1,
    difficulty: 1.0,
    due_at: Date.now(), // due immediately
    engagement_count: 0,
    last_engaged_at: 0,
    understanding: 0,
    notes: [],
  };
}

/**
 * Ensure concepts that have been encountered/known have review states.
 */
export function ensureReviewStates() {
  let created = 0;
  for (const [cid, state] of conceptStates) {
    if (state.state !== 'unknown' && !conceptReviews.has(cid)) {
      const review = getOrCreateReview(cid);
      review.due_at = Date.now(); // due now
      conceptReviews.set(cid, review);
      created++;
    }
  }
  if (created > 0) {
    saveConceptReviews(conceptReviews);
  }
}

/**
 * Get concepts that are due for review, ranked by priority.
 * Priority factors: overdue amount, relevance to current reading, topic interest.
 */
export function getReviewQueue(limit: number = 10): Array<{
  concept: Concept;
  review: ConceptReview;
  priority: number;
  reason: string;
}> {
  ensureReviewStates();
  const now = Date.now();
  const results: Array<{ concept: Concept; review: ConceptReview; priority: number; reason: string }> = [];

  // Get current active topics from recent reading
  const activeTopics = new Set<string>();
  for (const [, state] of readingStates) {
    if (state.depth !== 'unread' && now - state.last_read_at < 7 * DAY_MS) {
      const article = articles.find(a => a.id === state.article_id);
      if (article) article.topics.forEach(t => activeTopics.add(t));
    }
  }

  for (const [cid, review] of conceptReviews) {
    const concept = concepts.find(c => c.id === cid);
    if (!concept) continue;

    // Base: how overdue is this concept?
    const overdueDays = Math.max(0, (now - review.due_at) / DAY_MS);
    const scheduling = Math.min(overdueDays / Math.max(1, review.stability_days), 2.0);

    // Relevance: does this topic appear in recent reading?
    const relevant = activeTopics.has(concept.topic);
    const relevanceFactor = relevant ? 1.5 : 0.7;

    // Topic interest: how many articles read in this topic?
    const topicArticles = articles.filter(a => a.topics.includes(concept.topic));
    const engagedCount = topicArticles.filter(a => {
      const s = readingStates.get(a.id);
      return s && s.depth !== 'unread';
    }).length;
    const interestFactor = engagedCount >= 5 ? 1.5 : engagedCount >= 2 ? 1.0 : 0.5;

    // Maturity: new concepts should be reviewed sooner
    const maturityFactor = review.engagement_count <= 1 ? 1.3 : review.engagement_count >= 5 ? 0.8 : 1.0;

    const priority = Math.max(0.01, scheduling * relevanceFactor * interestFactor * maturityFactor);

    // Build reason string
    let reason = '';
    if (overdueDays > 7) reason = `Overdue by ${Math.round(overdueDays)} days`;
    else if (relevant) reason = 'Connects to current reading';
    else if (review.engagement_count === 0) reason = 'New concept to explore';
    else reason = 'Scheduled review';

    results.push({ concept, review, priority, reason });
  }

  results.sort((a, b) => b.priority - a.priority);
  return results.slice(0, limit);
}

/**
 * Record a review engagement and update scheduling.
 */
export function submitReview(conceptId: string, rating: ReviewRating, noteText?: string) {
  const review = getOrCreateReview(conceptId);

  // Update scheduling based on rating
  // Rating 1 (again): reset to 1 day, increase difficulty
  // Rating 2 (hard): interval * 1.2, slight difficulty increase
  // Rating 3 (good): interval * 2.5, slight difficulty decrease
  // Rating 4 (easy): interval * 3.5, difficulty decrease
  const multipliers: Record<ReviewRating, number> = { 1: 0.5, 2: 1.2, 3: 2.5, 4: 3.5 };
  const difficultyAdjust: Record<ReviewRating, number> = { 1: 0.3, 2: 0.1, 3: -0.05, 4: -0.15 };

  if (rating === 1) {
    review.stability_days = 1; // Reset
  } else {
    review.stability_days = Math.max(1, Math.min(365, review.stability_days * multipliers[rating]));
  }
  review.difficulty = Math.max(0.3, Math.min(3.0, review.difficulty + difficultyAdjust[rating]));
  review.due_at = Date.now() + review.stability_days * DAY_MS;
  review.engagement_count++;
  review.last_engaged_at = Date.now();
  review.understanding = rating;

  if (noteText) {
    review.notes.push({
      id: `note_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
      text: noteText,
      created_at: Date.now(),
    });
  }

  conceptReviews.set(conceptId, review);
  saveConceptReviews(conceptReviews);

  logEvent('concept_review', {
    concept_id: conceptId,
    rating,
    stability_days: review.stability_days,
    engagement_count: review.engagement_count,
    has_note: !!noteText,
  });
}

export function getConceptReview(conceptId: string): ConceptReview | undefined {
  return conceptReviews.get(conceptId);
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
