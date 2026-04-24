import { Platform } from 'react-native';
import type { ArticleContent, ArticleSection } from './types';
import { logEvent } from './logger';
import { getResearchServerUrl } from '../lib/server-urls';

const CONTENT_DIR_NAME = 'content';
const WEB_CACHE_PREFIX = '@petrarca/content_';

// In-memory cache for loaded content
const contentCache = new Map<string, ArticleContent>();

// Lazy-load expo-file-system only on native
let NativeFS: any = null;
function getNativeFS() {
  if (!NativeFS && Platform.OS !== 'web') {
    NativeFS = require('expo-file-system');
  }
  return NativeFS;
}

function getCachedFile(name: string) {
  const { Paths, File } = getNativeFS();
  return new File(Paths.document, CONTENT_DIR_NAME, name);
}

function ensureContentDir() {
  const { Paths, Directory } = getNativeFS();
  const dir = new Directory(Paths.document, CONTENT_DIR_NAME);
  if (!dir.exists) dir.create({ intermediates: true });
}

/** Load article content from cache or fetch from API. */
export async function getArticleContent(articleId: string): Promise<ArticleContent | null> {
  // Check in-memory cache first
  if (contentCache.has(articleId)) {
    return contentCache.get(articleId)!;
  }

  // Check disk cache
  const cached = await loadCachedArticleContent(articleId);
  if (cached) {
    contentCache.set(articleId, cached);
    return cached;
  }

  // Fetch from API
  try {
    const resp = await fetch(`${getResearchServerUrl()}/api/articles/${encodeURIComponent(articleId)}/content`);
    if (!resp.ok) return null;
    const data: ArticleContent = await resp.json();
    contentCache.set(articleId, data);
    cacheArticleContent(articleId, data);
    return data;
  } catch (e) {
    logEvent('article_content_fetch_error', { article_id: articleId, error: String(e) });
    return null;
  }
}

/** Prefetch content for multiple articles in background. */
export function prefetchArticleContent(articleIds: string[]): void {
  for (const id of articleIds) {
    if (!contentCache.has(id)) {
      getArticleContent(id); // fire and forget
    }
  }
}

/** Check if content is available without fetching. */
export function isContentCached(articleId: string): boolean {
  return contentCache.has(articleId);
}

/** Clear in-memory cache (e.g., on content refresh). */
export function clearContentCache(): void {
  contentCache.clear();
}

// --- Disk persistence ---

function cacheArticleContent(articleId: string, data: ArticleContent): void {
  const json = JSON.stringify(data);
  const key = `article_${articleId}.json`;
  if (Platform.OS === 'web') {
    try { localStorage.setItem(`${WEB_CACHE_PREFIX}${key}`, json); } catch {}
  } else {
    try {
      ensureContentDir();
      getCachedFile(key).write(json);
    } catch {}
  }
}

async function loadCachedArticleContent(articleId: string): Promise<ArticleContent | null> {
  const key = `article_${articleId}.json`;
  try {
    if (Platform.OS === 'web') {
      const raw = localStorage.getItem(`${WEB_CACHE_PREFIX}${key}`);
      return raw ? JSON.parse(raw) : null;
    } else {
      const file = getCachedFile(key);
      if (!file.exists) return null;
      return JSON.parse(await file.text());
    }
  } catch {
    return null;
  }
}
