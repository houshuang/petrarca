import bookmarksRaw from './bookmarks.json';
import { Bookmark, UserSignal } from './types';

const bookmarks = bookmarksRaw as Bookmark[];

// Sort by relevance score descending
const sorted = [...bookmarks].sort((a, b) => b._relevance_score - a._relevance_score);

// In-memory signal store (persists across screens within session)
const signals: UserSignal[] = [];

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
