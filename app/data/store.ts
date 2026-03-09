import { Article, ReadingState, UserSignal, Highlight } from './types';
import type { ClaimClassification, ParagraphDimming, ArticleNovelty, DeltaReport } from './types';
import { logEvent } from './logger';
import { loadSignals, saveSignals, loadReadingStates, saveReadingStates, loadHighlights, saveHighlights } from './persistence';
import { checkForUpdates, downloadContent, loadCachedContent } from './content-sync';
import { loadInterestProfile, scoreArticle, recordSignal, recordTopicSignal as _recordTopicSignal, recordTopicSignalAtLevel as _recordTopicSignalAtLevel, getTotalSignalCount } from './interest-model';
import type { SignalAction } from './interest-model';
import {
  initKnowledgeEngine,
  isKnowledgeReady,
  getArticleNovelty as _getArticleNovelty,
  classifyArticleClaims as _classifyArticleClaims,
  computeParagraphDimming as _computeParagraphDimming,
  markArticleEncountered as _markArticleEncountered,
  getDeltaReports as _getDeltaReports,
  getCrossArticleConnections as _getCrossArticleConnections,
  getParagraphConnections as _getParagraphConnections,
} from './knowledge-engine';
import type { CrossArticleConnection } from './knowledge-engine';
import { loadQueue, getQueuedArticleIds, isQueued } from './queue';
import { loadBookmarks } from './bookmarks';
import AsyncStorage from '@react-native-async-storage/async-storage';

let articles: Article[] = [];
let readingStates = new Map<string, ReadingState>();
let highlights: Highlight[] = [];
let signals: UserSignal[] = [];
let dismissedArticles = new Set<string>();
let initialized = false;
let initPromise: Promise<void> | null = null;

const DISMISSED_KEY = '@petrarca/dismissed_articles';

// --- Dismissed articles ---

async function loadDismissedArticles(): Promise<void> {
  try {
    const raw = await AsyncStorage.getItem(DISMISSED_KEY);
    if (raw) dismissedArticles = new Set(JSON.parse(raw));
  } catch (e) {
    console.warn('[store] failed to load dismissed articles:', e);
  }
}

async function saveDismissedArticles(): Promise<void> {
  try {
    await AsyncStorage.setItem(DISMISSED_KEY, JSON.stringify([...dismissedArticles]));
  } catch (e) {
    console.warn('[store] failed to save dismissed articles:', e);
  }
}

export function dismissArticle(articleId: string, reason: string) {
  dismissedArticles.add(articleId);
  saveDismissedArticles();
  logEvent('article_dismissed', { article_id: articleId, reason });
}

export function isDismissed(articleId: string): boolean {
  return dismissedArticles.has(articleId);
}

// --- Init ---

export async function initStore(): Promise<void> {
  if (initialized) return;
  if (initPromise) return initPromise;

  initPromise = (async () => {
    // Load articles from cache (downloaded from server on previous launch)
    let cachedKnowledgeIndex = null;
    const cached = await loadCachedContent();
    if (cached && cached.articles.length > 0) {
      articles = cached.articles;
      cachedKnowledgeIndex = cached.knowledgeIndex;
    }

    // Sort by date (newest first)
    articles.sort((a, b) => (b.date || '').localeCompare(a.date || ''));

    signals = await loadSignals();
    readingStates = await loadReadingStates();
    highlights = await loadHighlights();
    await loadDismissedArticles();
    await loadInterestProfile();
    await loadQueue();
    await loadBookmarks();
    await initKnowledgeEngine(cachedKnowledgeIndex);

    initialized = true;

    logEvent('store_initialized', {
      total_articles: articles.length,
      loaded_signals: signals.length,
      loaded_reading_states: readingStates.size,
      loaded_highlights: highlights.length,
      loaded_dismissed: dismissedArticles.size,
    });

    // If no cached articles, download immediately (first launch)
    // Otherwise check for updates in background
    if (articles.length === 0) {
      const fresh = await downloadContent();
      if (fresh) {
        articles = fresh.articles;
        articles.sort((a, b) => (b.date || '').localeCompare(a.date || ''));
        if (fresh.knowledgeIndex) {
          await initKnowledgeEngine(fresh.knowledgeIndex);
        }
        logEvent('content_downloaded_first_launch', {
          article_count: fresh.articles.length,
          knowledge_index: !!fresh.knowledgeIndex,
        });
      }
    } else {
      checkForUpdates().then(async (hasUpdates) => {
        if (hasUpdates) {
          const fresh = await downloadContent();
          if (fresh) {
            articles = fresh.articles;
            articles.sort((a, b) => (b.date || '').localeCompare(a.date || ''));
            if (fresh.knowledgeIndex) {
              await initKnowledgeEngine(fresh.knowledgeIndex);
            }
            logEvent('content_refreshed', {
              article_count: fresh.articles.length,
              knowledge_index_updated: !!fresh.knowledgeIndex,
            });
          }
        }
      });
    }
  })();

  return initPromise;
}

export function isInitialized(): boolean {
  return initialized;
}

export async function refreshContent(): Promise<boolean> {
  try {
    const hasUpdates = await checkForUpdates();
    if (hasUpdates) {
      const fresh = await downloadContent();
      if (fresh) {
        articles = fresh.articles;
        articles.sort((a, b) => (b.date || '').localeCompare(a.date || ''));
        if (fresh.knowledgeIndex) {
          await initKnowledgeEngine(fresh.knowledgeIndex);
        }
        logEvent('content_pull_refresh', {
          article_count: fresh.articles.length,
          knowledge_index_updated: !!fresh.knowledgeIndex,
        });
        return true;
      }
    }
    return false;
  } catch (e) {
    logEvent('content_pull_refresh_error', { error: String(e) });
    return false;
  }
}

// --- Article access ---

export function getArticles(): Article[] {
  return articles;
}

export function getArticleById(id: string): Article | undefined {
  return articles.find(a => a.id === id);
}

/**
 * Get feed articles: not dismissed, not read. Ranked by interest model.
 * Cold start (~< 20 signals): falls back to date sort.
 */
export function getRankedFeedArticles(): Article[] {
  const candidates = articles.filter(a => {
    if (dismissedArticles.has(a.id)) return false;
    const state = readingStates.get(a.id);
    if (state && state.status === 'read') return false;
    return true;
  });

  const hasEnoughSignals = getTotalSignalCount() >= 10;
  if (!hasEnoughSignals) {
    return candidates; // Already sorted by date from initStore
  }

  // Build recent topic list (last 10 articles shown) for variety penalty
  const recentTopics = candidates
    .slice(0, 10)
    .flatMap(a => (a.interest_topics || []).map(t => t.specific));

  const useKnowledge = isKnowledgeReady();

  return candidates
    .map(a => {
      const interestScore = scoreArticle(a, recentTopics);
      if (!useKnowledge) return { article: a, score: interestScore };
      const novelty = _getArticleNovelty(a.id);
      const curiosity = novelty.curiosity_score;
      // Blend: interest model (60%) + knowledge curiosity (40%)
      // Curiosity score already peaks at 70% novelty via Gaussian
      return { article: a, score: interestScore * 0.6 + curiosity * 0.4 };
    })
    .sort((a, b) => b.score - a.score)
    .map(x => x.article);
}

/**
 * Get read articles for the bottom section of the feed.
 */
export function getReadArticles(): Article[] {
  return articles
    .filter(a => {
      const state = readingStates.get(a.id);
      return state && state.status === 'read';
    })
    .sort((a, b) => {
      const sa = readingStates.get(a.id);
      const sb = readingStates.get(b.id);
      return (sb?.completed_at || sb?.last_read_at || 0) - (sa?.completed_at || sa?.last_read_at || 0);
    });
}

// --- Reading state ---

export function getReadingState(articleId: string): ReadingState {
  return readingStates.get(articleId) || {
    article_id: articleId,
    status: 'unread',
    last_read_at: 0,
    time_spent_ms: 0,
    started_at: 0,
    scroll_position_y: 0,
  };
}

export function updateReadingState(articleId: string, updates: Partial<ReadingState>) {
  const current = getReadingState(articleId);
  const updated = { ...current, ...updates, article_id: articleId };
  readingStates.set(articleId, updated);
  saveReadingStates(readingStates);
}

export function markArticleRead(articleId: string) {
  const current = getReadingState(articleId);
  const updated: ReadingState = {
    ...current,
    article_id: articleId,
    status: 'read',
    completed_at: Date.now(),
    last_read_at: Date.now(),
  };
  readingStates.set(articleId, updated);
  saveReadingStates(readingStates);
  logEvent('article_read', { article_id: articleId, time_spent_ms: updated.time_spent_ms });
}

// --- Signals ---

export function addSignal(signal: UserSignal) {
  signals.push(signal);
  saveSignals(signals);
  logEvent('signal', {
    article_id: signal.article_id,
    signal: signal.signal,
  });
}

export function getSignals(): UserSignal[] {
  return [...signals];
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

// --- Highlights ---

export function getHighlights(articleId?: string): Highlight[] {
  if (articleId) return highlights.filter(h => h.article_id === articleId);
  return highlights;
}

export function getHighlightBlockIndices(articleId: string): Set<number> {
  return new Set(highlights.filter(h => h.article_id === articleId).map(h => h.block_index));
}

export function addHighlight(highlight: Highlight) {
  highlights.push(highlight);
  saveHighlights(highlights);
  logEvent('paragraph_highlight', {
    article_id: highlight.article_id,
    block_index: highlight.block_index,
    zone: highlight.zone,
    text_preview: highlight.text.slice(0, 80),
  });
}

export function removeHighlight(articleId: string, blockIndex: number) {
  highlights = highlights.filter(h => !(h.article_id === articleId && h.block_index === blockIndex));
  saveHighlights(highlights);
  logEvent('paragraph_unhighlight', { article_id: articleId, block_index: blockIndex });
}

// --- Interest signals ---

export function recordInterestSignal(action: SignalAction, articleId: string) {
  const article = getArticleById(articleId);
  if (article) {
    recordSignal(action, article);
  }
}

export function recordTopicInterestSignal(action: SignalAction, topic: import('./types').InterestTopic) {
  _recordTopicSignal(action, topic);
}

export function recordTopicInterestSignalAtLevel(
  action: SignalAction,
  topicKey: string,
  level: 'broad' | 'specific' | 'entity',
  parent?: string,
) {
  _recordTopicSignalAtLevel(action, topicKey, level, parent);
}

// --- Knowledge engine ---

export function getArticleNovelty(articleId: string): ArticleNovelty {
  return _getArticleNovelty(articleId);
}

export function classifyArticleClaims(articleId: string): ClaimClassification[] {
  return _classifyArticleClaims(articleId);
}

export function computeParagraphDimming(articleId: string): ParagraphDimming[] {
  return _computeParagraphDimming(articleId);
}

export function markArticleEncountered(articleId: string, engagement: 'skim' | 'read' | 'highlight'): void {
  _markArticleEncountered(articleId, engagement);
}

export function getDeltaReports(): Record<string, DeltaReport> {
  return _getDeltaReports();
}

export function getCrossArticleConnections(articleId: string): CrossArticleConnection[] {
  return _getCrossArticleConnections(articleId);
}

export function getParagraphConnections(articleId: string): Map<number, Array<{ articleId: string; claimText: string }>> {
  return _getParagraphConnections(articleId);
}

// --- Feed version (for reactive reranking) ---

let feedVersion = 0;

export function getFeedVersion(): number {
  return feedVersion;
}

export function bumpFeedVersion(): void {
  feedVersion++;
}

// --- Lens-based article retrieval ---

export type FeedLens = 'latest' | 'best' | 'topics' | 'quick';

/**
 * Get the single top-recommended article (highest curiosity × interest score),
 * excluding articles that are queued or in-progress.
 */
export function getTopRecommendedArticle(): Article | null {
  const ranked = getRankedFeedArticles();
  const queuedSet = new Set(getQueuedArticleIds());
  for (const a of ranked) {
    const state = readingStates.get(a.id);
    if (queuedSet.has(a.id)) continue;
    if (state && state.status === 'reading') continue;
    return a;
  }
  return ranked[0] || null;
}

/**
 * Get articles organized by the active lens.
 * For 'topics' lens, use getArticlesGroupedByTopic() instead.
 */
export function getArticlesByLens(lens: FeedLens, topicFilter?: string): Article[] {
  let candidates = articles.filter(a => {
    if (dismissedArticles.has(a.id)) return false;
    const state = readingStates.get(a.id);
    if (state && state.status === 'read') return false;
    return true;
  });

  if (topicFilter) {
    candidates = candidates.filter(a => {
      const topics = (a.interest_topics || []).map(t => t.broad);
      const fallback = topics.length > 0 ? topics : a.topics;
      return fallback.some(t => t.toLowerCase().includes(topicFilter.toLowerCase()));
    });
  }

  switch (lens) {
    case 'latest':
      return candidates.sort((a, b) => (b.date || '').localeCompare(a.date || ''));

    case 'best':
      return getRankedFeedArticles().filter(a => {
        if (topicFilter) {
          const topics = (a.interest_topics || []).map(t => t.broad);
          const fallback = topics.length > 0 ? topics : a.topics;
          return fallback.some(t => t.toLowerCase().includes(topicFilter.toLowerCase()));
        }
        return true;
      });

    case 'quick': {
      const quickCandidates = candidates.filter(a => a.estimated_read_minutes <= 3);
      const hasEnough = getTotalSignalCount() >= 10;
      if (!hasEnough) return quickCandidates.sort((a, b) => (b.date || '').localeCompare(a.date || ''));
      const recentTopics = quickCandidates.slice(0, 10).flatMap(x => (x.interest_topics || []).map(t => t.specific));
      const useKnowledge = isKnowledgeReady();
      return quickCandidates
        .map(a => {
          const interest = scoreArticle(a, recentTopics);
          if (!useKnowledge) return { article: a, score: interest };
          const curiosity = _getArticleNovelty(a.id).curiosity_score;
          return { article: a, score: interest * 0.6 + curiosity * 0.4 };
        })
        .sort((a, b) => b.score - a.score)
        .map(x => x.article);
    }

    default:
      return candidates;
  }
}

/**
 * Get the next or previous article ID in the current feed order.
 */
export function getAdjacentArticleId(
  currentId: string,
  direction: 'next' | 'prev',
  lens: FeedLens = 'best'
): string | null {
  const list = getArticlesByLens(lens);
  const idx = list.findIndex(a => a.id === currentId);
  if (idx === -1) return null;
  const target = direction === 'next' ? idx + 1 : idx - 1;
  return list[target]?.id ?? null;
}

/**
 * Get articles grouped by broad topic for the Topics lens.
 * Returns groups sorted by topic interest score.
 */
export function getArticlesGroupedByTopic(): Array<{ topic: string; articles: Article[] }> {
  const candidates = articles.filter(a => {
    if (dismissedArticles.has(a.id)) return false;
    const state = readingStates.get(a.id);
    if (state && state.status === 'read') return false;
    return true;
  });

  const groups = new Map<string, Article[]>();
  for (const a of candidates) {
    const topics = (a.interest_topics || []).map(t => t.broad);
    const fallback = topics.length > 0 ? topics : a.topics.slice(0, 2);
    for (const t of fallback) {
      if (!groups.has(t)) groups.set(t, []);
      groups.get(t)!.push(a);
    }
  }

  return [...groups.entries()]
    .map(([topic, arts]) => ({ topic, articles: arts }))
    .sort((a, b) => b.articles.length - a.articles.length);
}

/**
 * Get in-progress articles (status === 'reading'), sorted by last_read_at descending.
 */
export function getInProgressArticles(): Article[] {
  return articles
    .filter(a => {
      const state = readingStates.get(a.id);
      return state && state.status === 'reading';
    })
    .sort((a, b) => {
      const sa = readingStates.get(a.id);
      const sb = readingStates.get(b.id);
      return (sb?.last_read_at || 0) - (sa?.last_read_at || 0);
    });
}

// --- Stats (simplified) ---

export function getStats() {
  let totalTimeMs = 0;
  let readCount = 0;
  for (const [, state] of readingStates) {
    totalTimeMs += state.time_spent_ms;
    if (state.status === 'read') readCount++;
  }

  return {
    total: articles.length,
    read: readCount,
    unread: articles.length - readCount,
    totalTimeMs,
    signals: signals.length,
  };
}
