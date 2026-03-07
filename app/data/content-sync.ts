import { Platform } from 'react-native';
import { Article } from './types';
import { logEvent } from './logger';

const CONTENT_BASE = Platform.OS === 'web'
  ? '/content'
  : 'https://alifstian.duckdns.org/content';
const MANIFEST_URL = `${CONTENT_BASE}/manifest.json`;
const ARTICLES_URL = `${CONTENT_BASE}/articles.json`;

const CONTENT_DIR_NAME = 'content';
const WEB_CACHE_PREFIX = '@petrarca/cache_';

// Lazy-load expo-file-system only on native
let NativeFS: any = null;
function getNativeFS() {
  if (!NativeFS && Platform.OS !== 'web') {
    NativeFS = require('expo-file-system');
  }
  return NativeFS;
}

// --- Web cache helpers ---

function webCacheRead(name: string): string | null {
  return localStorage.getItem(`${WEB_CACHE_PREFIX}${name}`);
}

function webCacheWrite(name: string, data: string) {
  try {
    localStorage.setItem(`${WEB_CACHE_PREFIX}${name}`, data);
  } catch {
    // localStorage full — not critical
  }
}

// --- Native file helpers ---

function getContentDir() {
  const { Paths, Directory } = getNativeFS();
  return new Directory(Paths.document, CONTENT_DIR_NAME);
}

function getCachedFile(name: string) {
  const { Paths, File } = getNativeFS();
  return new File(Paths.document, CONTENT_DIR_NAME, name);
}

function ensureContentDir() {
  const dir = getContentDir();
  if (!dir.exists) {
    dir.create({ intermediates: true });
  }
}

interface Manifest {
  last_updated: string;
  article_count: number;
  articles_hash: string;
  concepts_hash?: string;
  concept_count?: number;
  books_hash?: string;
}

export async function checkForUpdates(): Promise<boolean> {
  try {
    const resp = await fetch(MANIFEST_URL, { cache: 'no-store' });
    if (!resp.ok) return false;
    const remote: Manifest = await resp.json();

    if (Platform.OS === 'web') {
      const localRaw = webCacheRead('manifest.json');
      if (localRaw) {
        const local: Manifest = JSON.parse(localRaw);
        return remote.articles_hash !== local.articles_hash;
      }
      return true;
    }

    const manifestFile = getCachedFile('manifest.json');
    if (manifestFile.exists) {
      const localRaw = await manifestFile.text();
      const local: Manifest = JSON.parse(localRaw);
      return remote.articles_hash !== local.articles_hash;
    }
    return true;
  } catch {
    return false;
  }
}

export async function downloadContent(): Promise<{ articles: Article[] } | null> {
  try {
    if (Platform.OS !== 'web') ensureContentDir();

    const [articlesResp, manifestResp] = await Promise.all([
      fetch(ARTICLES_URL),
      fetch(MANIFEST_URL),
    ]);

    if (!articlesResp.ok) return null;

    const articles: Article[] = await articlesResp.json();
    const manifestText = await manifestResp.text();

    if (Platform.OS === 'web') {
      webCacheWrite('articles.json', JSON.stringify(articles));
      webCacheWrite('manifest.json', manifestText);
    } else {
      getCachedFile('articles.json').write(JSON.stringify(articles));
      getCachedFile('manifest.json').write(manifestText);
    }

    logEvent('content_downloaded', { article_count: articles.length });
    return { articles };
  } catch {
    return null;
  }
}

export async function loadCachedContent(): Promise<{ articles: Article[] } | null> {
  try {
    if (Platform.OS === 'web') {
      const articlesRaw = webCacheRead('articles.json');
      if (!articlesRaw) return null;
      return { articles: JSON.parse(articlesRaw) };
    }

    const articlesFile = getCachedFile('articles.json');
    if (!articlesFile.exists) return null;

    return { articles: JSON.parse(await articlesFile.text()) };
  } catch {
    return null;
  }
}
