import { Article, ArticleMeta, ReadingState, UserSignal, Highlight, TopicSynthesis } from './types';
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
  markClaimsEncountered as _markClaimsEncountered,
  getDeltaReports as _getDeltaReports,
  getCrossArticleConnections as _getCrossArticleConnections,
  getParagraphConnections as _getParagraphConnections,
  getArticleCurriculumNodes,
} from './knowledge-engine';
import type { CrossArticleConnection } from './knowledge-engine';
import { loadQueue, getQueuedArticleIds, isQueued } from './queue';
import { loadBookmarks } from './bookmarks';
import { initBookStore, getPhysicalBooks } from './book-store';
import { prefetchArticleContent } from './article-content';
import AsyncStorage from '@react-native-async-storage/async-storage';

let articles: ArticleMeta[] = [];
let syntheses: TopicSynthesis[] = [];
let conceptClusters: any = null;
let readingStates = new Map<string, ReadingState>();
let highlights: Highlight[] = [];
let signals: UserSignal[] = [];
let dismissedArticles = new Set<string>();
let completedSyntheses = new Set<string>();
let initialized = false;
let initPromise: Promise<void> | null = null;

const COMPLETED_SYNTHESES_KEY = '@petrarca/completed_syntheses';

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
      if (cached.syntheses && Array.isArray(cached.syntheses)) {
        syntheses = cached.syntheses;
      }
      if (cached.conceptClusters) {
        conceptClusters = cached.conceptClusters;
      }
    }

    // Sort by date (newest first)
    articles.sort((a, b) => (b.date || '').localeCompare(a.date || ''));

    signals = await loadSignals();
    readingStates = await loadReadingStates();
    highlights = await loadHighlights();
    await loadDismissedArticles();
    await loadCompletedSyntheses();
    await loadInterestProfile();
    await loadQueue();
    await loadBookmarks();
    await initBookStore();
    await initKnowledgeEngine(cachedKnowledgeIndex);

    initialized = true;

    // Prefetch content for queued and in-progress articles (offline readiness)
    const queuedIds = getQueuedArticleIds();
    const inProgressIds = [...readingStates.entries()]
      .filter(([_, s]) => s.status === 'reading')
      .map(([id]) => id);
    prefetchArticleContent([...queuedIds, ...inProgressIds]);

    logEvent('store_initialized', {
      total_articles: articles.length,
      total_syntheses: syntheses.length,
      loaded_signals: signals.length,
      loaded_reading_states: readingStates.size,
      loaded_highlights: highlights.length,
      loaded_dismissed: dismissedArticles.size,
    });

    // First-launch downloads also run after local initialization: the review
    // screen reads its own API and must not wait for article exports.
    void (async () => {
      if (articles.length === 0) {
        const fresh = await downloadContent();
        if (fresh) {
          articles = fresh.articles;
          articles.sort((a, b) => (b.date || '').localeCompare(a.date || ''));
          if (fresh.knowledgeIndex) {
            await initKnowledgeEngine(fresh.knowledgeIndex);
          }
          if (fresh.syntheses && Array.isArray(fresh.syntheses)) {
            syntheses = fresh.syntheses;
          }
          if (fresh.conceptClusters) {
            conceptClusters = fresh.conceptClusters;
          }
          logEvent('content_downloaded_first_launch', {
            article_count: fresh.articles.length,
            knowledge_index: !!fresh.knowledgeIndex,
            syntheses_count: syntheses.length,
          });
        }
      } else {
        await checkForUpdates().then(async (hasUpdates) => {
          if (hasUpdates) {
            const fresh = await downloadContent();
            if (fresh) {
              articles = fresh.articles;
              articles.sort((a, b) => (b.date || '').localeCompare(a.date || ''));
              if (fresh.knowledgeIndex) {
                await initKnowledgeEngine(fresh.knowledgeIndex);
              }
              if (fresh.syntheses && Array.isArray(fresh.syntheses)) {
                syntheses = fresh.syntheses;
              }
              if (fresh.conceptClusters) {
                conceptClusters = fresh.conceptClusters;
              }
              logEvent('content_refreshed', {
                article_count: fresh.articles.length,
                knowledge_index_updated: !!fresh.knowledgeIndex,
                syntheses_count: syntheses.length,
              });
            }
          }
        });
      }
    })().catch((error: unknown) => {
      console.warn('[store] Background content sync failed:', error);
    });
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
        if (fresh.syntheses && Array.isArray(fresh.syntheses)) {
          syntheses = fresh.syntheses;
        }
        if (fresh.conceptClusters) {
          conceptClusters = fresh.conceptClusters;
        }
        logEvent('content_pull_refresh', {
          article_count: fresh.articles.length,
          knowledge_index_updated: !!fresh.knowledgeIndex,
          syntheses_count: syntheses.length,
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

export function getArticles(): ArticleMeta[] {
  return articles;
}

export function getArticleById(id: string): ArticleMeta | undefined {
  return articles.find(a => a.id === id);
}

/**
 * Get feed articles: not dismissed, not read. Ranked by interest model.
 * Cold start (~< 20 signals): falls back to date sort.
 */
export function getRankedFeedArticles(): ArticleMeta[] {
  const candidates = articles.filter(a => {
    if (dismissedArticles.has(a.id)) return false;
    const state = readingStates.get(a.id);
    if (state && state.status === 'read') return false;
    const synthCoverage = getArticleSynthesisCoverage(a.id);
    if (synthCoverage !== null && synthCoverage >= 0.80) return false;
    // Skip short Wikipedia chunks (stub intros / thin sections)
    const isWiki = a.source_url?.includes('wikipedia.org');
    if (isWiki && (a.word_count || 0) < 500) return false;
    return true;
  });

  const hasEnoughSignals = getTotalSignalCount() >= 10;
  if (!hasEnoughSignals) {
    return _capPerSource(candidates);
  }

  // Build recent topic list (last 10 articles shown) for variety penalty
  const recentTopics = candidates
    .slice(0, 10)
    .flatMap(a => (a.interest_topics || []).map(t => t.specific));

  const useKnowledge = isKnowledgeReady();

  const ranked = candidates
    .map(a => {
      const interestScore = scoreArticle(a, recentTopics);
      let score: number;
      if (!useKnowledge) {
        score = interestScore;
      } else {
        const novelty = _getArticleNovelty(a.id);
        const curiosity = novelty.curiosity_score;
        // Blend: interest model (60%) + knowledge curiosity (40%)
        // Curiosity score already peaks at 70% novelty via Gaussian
        score = interestScore * 0.6 + curiosity * 0.4;
      }
      // Boost articles matching topics of actively-read books
      const bookBoost = _getActiveBookTopicBoost(a);
      score += bookBoost;

      const sc = getArticleSynthesisCoverage(a.id);
      if (sc !== null && sc >= 0.50) score *= (1 - sc * 0.5);
      return { article: a, score };
    })
    .sort((a, b) => b.score - a.score)
    .map(x => x.article);

  return _capPerSource(ranked);
}

// Cap chunked articles to 3 per base source URL (keeps top-ranked chunks)
function _capPerSource(sorted: ArticleMeta[], max: number = 3): ArticleMeta[] {
  const counts = new Map<string, number>();
  return sorted.filter(a => {
    const url = _baseSourceUrl(a.source_url);
    if (!url) return true;
    const n = (counts.get(url) || 0) + 1;
    counts.set(url, n);
    return n <= max;
  });
}

function _baseSourceUrl(url: string | undefined): string | undefined {
  if (!url) return undefined;
  // Only cap multi-chunk sources (Wikipedia, etc.)
  if (!url.includes('wikipedia.org')) return undefined;
  // Strip #chunk-N fragments
  return url.split('#')[0];
}

// --- Active book reading boost ---

let _activeBookTopicsCache: { topics: Set<string>; at: number } | null = null;

function _getActiveBookTopics(): Set<string> {
  // Cache for 60s to avoid re-scanning books on every article score
  if (_activeBookTopicsCache && Date.now() - _activeBookTopicsCache.at < 60_000) {
    return _activeBookTopicsCache.topics;
  }
  const topics = new Set<string>();
  for (const book of getPhysicalBooks()) {
    if (book.reading_status === 'reading') {
      for (const t of (book.topics || [])) {
        topics.add(t.toLowerCase());
      }
    }
  }
  _activeBookTopicsCache = { topics, at: Date.now() };
  return topics;
}

function _getActiveBookTopicBoost(article: ArticleMeta): number {
  // When actively reading books on a topic, articles on that SAME topic
  // are less urgent (you're getting the knowledge from books instead).
  // Only boost articles that share ONE topic with books but cover OTHER topics too
  // (these provide complementary perspective). Pure-overlap articles get no boost.
  const bookTopics = _getActiveBookTopics();
  if (bookTopics.size === 0) return 0;
  const articleTopics = (article.topics || []).map(t => t.toLowerCase());
  const overlap = articleTopics.filter(t => bookTopics.has(t)).length;
  const nonOverlap = articleTopics.length - overlap;
  // Complementary: has some overlap (relevant) but mostly new angles
  if (overlap > 0 && nonOverlap > overlap) return 0.08;
  return 0;
}

/**
 * Get curriculum-based book connections for an article.
 * Returns book titles whose curriculum nodes overlap with the article's claims.
 */
export function getArticleBookConnections(articleId: string): string[] {
  const nodes = getArticleCurriculumNodes(articleId);
  if (nodes.length === 0) return [];

  const activeBooks = getPhysicalBooks().filter(b => b.reading_status === 'reading');
  if (activeBooks.length === 0) return [];

  // For now, match via topic overlap between article's curriculum domain
  // and book topics. Full curriculum-mediated matching requires book→curriculum
  // mapping data on the client, which we'll add in the next iteration.
  const articleDomains = new Set(nodes.map(n => n.domain_id));
  const matches: string[] = [];
  for (const book of activeBooks) {
    const bookTopicLower = (book.topics || []).map(t => t.toLowerCase());
    // Check if book topics suggest overlap with article's curriculum domains
    const domainKeywords: Record<string, string[]> = {
      'sicily_history_culture_and_legacy': ['sicily', 'sicilia', 'mafia', 'syracuse'],
      'ancient_greece_800300_bc_political_military_cultural_and': ['greece', 'greek', 'athens', 'sparta', 'hellenism'],
      'roman_republic_and_empire': ['rome', 'roman', 'republic', 'empire', 'cicero', 'caesar'],
    };
    for (const domain of articleDomains) {
      const keywords = domainKeywords[domain] || [];
      if (bookTopicLower.some(t => keywords.some(k => t.includes(k)))) {
        matches.push(book.title);
        break;
      }
    }
  }
  return matches;
}

/**
 * Get read articles for the bottom section of the feed.
 */
export function getReadArticles(): ArticleMeta[] {
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

// --- Source type helpers ---

export type SourceCategory = 'twitter' | 'newsletter' | 'research' | 'exploration' | 'other';

export function getArticleSourceCategory(a: ArticleMeta): SourceCategory {
  const src = (a.sources || [])[0];
  if (!src) return 'other';
  if (src.type === 'twitter_bookmark') return 'twitter';
  if (src.type === 'readwise') return 'newsletter';
  if (src.type?.startsWith('research:')) return 'research';
  if (src.type === 'exploration') return 'exploration';
  return 'other';
}

export function getResearchQuery(a: ArticleMeta): string | null {
  for (const s of (a.sources || [])) {
    if (s.type?.startsWith('research:')) return s.type.slice('research:'.length);
  }
  return null;
}

/** Get research articles from the feed, grouped by query. */
export function getResearchArticles(): Array<{ query: string; articles: ArticleMeta[] }> {
  const feedArticles = articles.filter(a => {
    if (dismissedArticles.has(a.id)) return false;
    const state = readingStates.get(a.id);
    if (state && state.status === 'read') return false;
    return (a.sources || []).some(s => s.type?.startsWith('research:'));
  });
  const groups = new Map<string, ArticleMeta[]>();
  for (const a of feedArticles) {
    const query = getResearchQuery(a) || 'Research';
    if (!groups.has(query)) groups.set(query, []);
    groups.get(query)!.push(a);
  }
  return [...groups.entries()].map(([query, arts]) => ({ query, articles: arts }));
}

/** Get topic and source distribution for a set of articles. */
export function getFeedDistribution(feedArticles: ArticleMeta[]): {
  topics: Array<{ topic: string; count: number }>;
  sources: Array<{ source: SourceCategory; label: string; count: number }>;
} {
  const topicCounts = new Map<string, number>();
  const sourceCounts = new Map<SourceCategory, number>();
  for (const a of feedArticles) {
    const broad = (a.interest_topics || []).map(t => t.broad);
    const topicList = broad.length > 0 ? broad : a.topics.slice(0, 2);
    for (const t of topicList) {
      topicCounts.set(t, (topicCounts.get(t) || 0) + 1);
    }
    const src = getArticleSourceCategory(a);
    sourceCounts.set(src, (sourceCounts.get(src) || 0) + 1);
  }
  const sourceLabels: Record<SourceCategory, string> = {
    twitter: 'Twitter', newsletter: 'Newsletter', research: 'AI Research',
    exploration: 'Wikipedia', other: 'Other',
  };
  return {
    topics: [...topicCounts.entries()]
      .map(([topic, count]) => ({ topic, count }))
      .sort((a, b) => b.count - a.count),
    sources: [...sourceCounts.entries()]
      .map(([source, count]) => ({ source, label: sourceLabels[source], count }))
      .filter(s => s.count > 0)
      .sort((a, b) => b.count - a.count),
  };
}

// --- Topic grouping ---

export function getByTopic(): Map<string, ArticleMeta[]> {
  const topicMap = new Map<string, ArticleMeta[]>();
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

export function markClaimsEncountered(claimIds: string[], engagement: 'skim' | 'read' | 'highlight'): number {
  return _markClaimsEncountered(claimIds, engagement);
}

// --- Syntheses ---

async function loadCompletedSyntheses(): Promise<void> {
  try {
    const raw = await AsyncStorage.getItem(COMPLETED_SYNTHESES_KEY);
    if (raw) completedSyntheses = new Set(JSON.parse(raw));
  } catch (e) {
    logEvent('completed_syntheses_load_error', { error: String(e) });
  }
}

async function saveCompletedSyntheses(): Promise<void> {
  try {
    await AsyncStorage.setItem(COMPLETED_SYNTHESES_KEY, JSON.stringify([...completedSyntheses]));
  } catch (e) {
    logEvent('completed_syntheses_save_error', { error: String(e) });
  }
}

export function getConceptClusters(): any {
  return conceptClusters;
}

export function getSyntheses(): TopicSynthesis[] {
  return syntheses;
}

export function getSynthesisForCluster(clusterId: string): TopicSynthesis | undefined {
  return syntheses.find(s => s.cluster_id === clusterId);
}

export function getSynthesisForArticle(articleId: string): TopicSynthesis | undefined {
  return syntheses.find(s => s.article_ids.includes(articleId));
}

export function getSynthesesForArticle(articleId: string): TopicSynthesis[] {
  return syntheses.filter(s => s.article_ids.includes(articleId));
}

export function isSynthesisCompleted(clusterId: string): boolean {
  return completedSyntheses.has(clusterId);
}

export function markSynthesisCompleted(clusterId: string): void {
  completedSyntheses.add(clusterId);
  saveCompletedSyntheses();
}

export function getArticleSynthesisCoverage(articleId: string): number | null {
  const completedSynths = syntheses.filter(
    s => completedSyntheses.has(s.cluster_id) && s.article_ids.includes(articleId)
  );
  if (completedSynths.length === 0) return null;
  let maxCoverage = 0;
  for (const s of completedSynths) {
    const coverage = s.article_coverage[articleId];
    if (coverage !== undefined && coverage > maxCoverage) {
      maxCoverage = coverage;
    }
  }
  return maxCoverage > 0 ? maxCoverage : null;
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
export function getTopRecommendedArticle(): ArticleMeta | null {
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
export function getArticlesByLens(lens: FeedLens, topicFilter?: string, sourceFilter?: SourceCategory): ArticleMeta[] {
  let candidates = articles.filter(a => {
    if (dismissedArticles.has(a.id)) return false;
    const state = readingStates.get(a.id);
    if (state && state.status === 'read') return false;
    const synthCoverage = getArticleSynthesisCoverage(a.id);
    if (synthCoverage !== null && synthCoverage >= 0.80) return false;
    return true;
  });

  if (topicFilter) {
    candidates = candidates.filter(a => {
      const topics = (a.interest_topics || []).map(t => t.broad);
      const fallback = topics.length > 0 ? topics : a.topics;
      return fallback.some(t => t.toLowerCase().includes(topicFilter.toLowerCase()));
    });
  }

  if (sourceFilter) {
    candidates = candidates.filter(a => getArticleSourceCategory(a) === sourceFilter);
  }

  switch (lens) {
    case 'latest':
      return candidates.sort((a, b) => (b.date || '').localeCompare(a.date || ''));

    case 'best': {
      let ranked = getRankedFeedArticles().filter(a => {
        if (topicFilter) {
          const topics = (a.interest_topics || []).map(t => t.broad);
          const fallback = topics.length > 0 ? topics : a.topics;
          return fallback.some(t => t.toLowerCase().includes(topicFilter.toLowerCase()));
        }
        if (sourceFilter) {
          return getArticleSourceCategory(a) === sourceFilter;
        }
        return true;
      });
      // Boost queued articles to top, preserving queue order
      const queuedIds = getQueuedArticleIds();
      if (queuedIds.length > 0) {
        const queuedSet = new Set(queuedIds);
        const queued = queuedIds
          .map(id => ranked.find(a => a.id === id))
          .filter((a): a is ArticleMeta => !!a);
        const rest = ranked.filter(a => !queuedSet.has(a.id));
        ranked = [...queued, ...rest];
      }
      return ranked;
    }

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
export function getArticlesGroupedByTopic(): Array<{ topic: string; articles: ArticleMeta[] }> {
  const candidates = articles.filter(a => {
    if (dismissedArticles.has(a.id)) return false;
    const state = readingStates.get(a.id);
    if (state && state.status === 'read') return false;
    return true;
  });

  const groups = new Map<string, ArticleMeta[]>();
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
export function getInProgressArticles(): ArticleMeta[] {
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
