import AsyncStorage from '@react-native-async-storage/async-storage';
import { logEvent } from './logger';

const BOOKMARKS_KEY = '@petrarca/bookmarks';

let bookmarkedIds: string[] = [];
let loaded = false;

export async function loadBookmarks(): Promise<void> {
  try {
    const raw = await AsyncStorage.getItem(BOOKMARKS_KEY);
    if (raw) bookmarkedIds = JSON.parse(raw);
    loaded = true;
  } catch (e) {
    console.warn('[bookmarks] failed to load:', e);
    bookmarkedIds = [];
    loaded = true;
  }
}

async function saveBookmarks(): Promise<void> {
  try {
    await AsyncStorage.setItem(BOOKMARKS_KEY, JSON.stringify(bookmarkedIds));
  } catch (e) {
    console.warn('[bookmarks] failed to save:', e);
  }
}

export async function toggleBookmark(articleId: string): Promise<boolean> {
  if (!loaded) await loadBookmarks();
  const wasBookmarked = bookmarkedIds.includes(articleId);
  if (wasBookmarked) {
    bookmarkedIds = bookmarkedIds.filter(id => id !== articleId);
  } else {
    bookmarkedIds.unshift(articleId);
  }
  await saveBookmarks();
  logEvent(wasBookmarked ? 'bookmark_remove' : 'bookmark_add', { article_id: articleId });
  return !wasBookmarked;
}

export function isBookmarked(articleId: string): boolean {
  return bookmarkedIds.includes(articleId);
}

export function getBookmarkedArticleIds(): string[] {
  return [...bookmarkedIds];
}
