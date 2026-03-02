import { Article, ReadingState, UserSignal, ReadingDepth } from './types';
import { logEvent } from './logger';
import { loadSignals, saveSignals, loadReadingStates, saveReadingStates } from './persistence';

let articles: Article[] = [];
let readingStates = new Map<string, ReadingState>();
let signals: UserSignal[] = [];
let initialized = false;
let initPromise: Promise<void> | null = null;

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

    signals = await loadSignals();
    readingStates = await loadReadingStates();
    initialized = true;

    logEvent('store_initialized', {
      total_articles: articles.length,
      loaded_signals: signals.length,
      loaded_reading_states: readingStates.size,
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
  };
}
