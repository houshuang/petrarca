import bookmarksRaw from './bookmarks.json';
import { Bookmark, UserSignal } from './types';
import { logEvent } from './logger';
import { loadSignals, saveSignals } from './persistence';

const bookmarks = bookmarksRaw as Bookmark[];

// Sort by relevance score descending
const sorted = [...bookmarks].sort((a, b) => b._relevance_score - a._relevance_score);

// Signal store — loaded from disk on init, persisted on every change
let signals: UserSignal[] = [];
let initialized = false;
let initPromise: Promise<void> | null = null;

export async function initStore(): Promise<void> {
  if (initialized) return;
  if (initPromise) return initPromise;

  initPromise = (async () => {
    signals = await loadSignals();
    initialized = true;
    logEvent('store_initialized', {
      total_bookmarks: sorted.length,
      loaded_signals: signals.length,
    });
  })();

  return initPromise;
}

export function isInitialized(): boolean {
  return initialized;
}

export function getBookmarks(): Bookmark[] {
  return sorted;
}

export function getBookmarkById(id: string): Bookmark | undefined {
  return sorted.find(b => b.id === id);
}

export function getUntriaged(): Bookmark[] {
  const triagedIds = new Set(signals.map(s => s.bookmarkId));
  return sorted.filter(b => !triagedIds.has(b.id));
}

export function addSignal(signal: UserSignal) {
  signals.push(signal);
  saveSignals(signals);

  const bookmark = getBookmarkById(signal.bookmarkId);
  logEvent('signal', {
    bookmark_id: signal.bookmarkId,
    signal: signal.signal,
    author: bookmark?.author_username,
    topics: bookmark?._llm_summary?.topics,
    relevance_score: bookmark?._relevance_score,
    content_type: bookmark?._llm_summary?.content_type,
    notes: signal.notes,
  });
}

export function getSignals(): UserSignal[] {
  return [...signals];
}

export function getSignalForBookmark(id: string): UserSignal | undefined {
  return signals.findLast(s => s.bookmarkId === id);
}

export function getByTopic(): Map<string, Bookmark[]> {
  const topicMap = new Map<string, Bookmark[]>();
  for (const b of sorted) {
    const topics = b._llm_summary?.topics ?? [];
    for (const t of topics) {
      if (!topicMap.has(t)) topicMap.set(t, []);
      topicMap.get(t)!.push(b);
    }
  }
  return topicMap;
}

export function getStats() {
  return {
    total: sorted.length,
    triaged: signals.length,
    interesting: signals.filter(s => s.signal === 'interesting').length,
    deepDive: signals.filter(s => s.signal === 'deep_dive').length,
    knewIt: signals.filter(s => s.signal === 'knew_it').length,
    notRelevant: signals.filter(s => s.signal === 'not_relevant').length,
  };
}
