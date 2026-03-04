import { Platform } from 'react-native';
import { Article, Concept, TopicSynthesis, Book, BookSection } from './types';
import { logEvent } from './logger';

const CONTENT_BASE = 'http://alifstian.duckdns.org:8083/content';
const MANIFEST_URL = `${CONTENT_BASE}/manifest.json`;
const ARTICLES_URL = `${CONTENT_BASE}/articles.json`;
const CONCEPTS_URL = `${CONTENT_BASE}/concepts.json`;
const SYNTHESES_URL = `${CONTENT_BASE}/syntheses.json`;
const BOOKS_URL = `${CONTENT_BASE}/books.json`;

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

function webCacheExists(name: string): boolean {
  return localStorage.getItem(`${WEB_CACHE_PREFIX}${name}`) !== null;
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
  concept_count: number;
  articles_hash: string;
  concepts_hash: string;
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
        return remote.articles_hash !== local.articles_hash
            || remote.concepts_hash !== local.concepts_hash
            || (remote.books_hash || '') !== (local.books_hash || '');
      }
      return true;
    }

    const manifestFile = getCachedFile('manifest.json');
    if (manifestFile.exists) {
      const localRaw = await manifestFile.text();
      const local: Manifest = JSON.parse(localRaw);
      return remote.articles_hash !== local.articles_hash
          || remote.concepts_hash !== local.concepts_hash
          || (remote.books_hash || '') !== (local.books_hash || '');
    }
    // No cached manifest = first sync
    return true;
  } catch {
    return false; // offline or server unreachable
  }
}

export async function downloadContent(): Promise<{ articles: Article[]; concepts: Concept[]; syntheses?: TopicSynthesis[]; books?: Book[] } | null> {
  try {
    if (Platform.OS !== 'web') ensureContentDir();

    const [articlesResp, conceptsResp, manifestResp] = await Promise.all([
      fetch(ARTICLES_URL),
      fetch(CONCEPTS_URL),
      fetch(MANIFEST_URL),
    ]);

    if (!articlesResp.ok || !conceptsResp.ok) return null;

    const articles: Article[] = await articlesResp.json();
    const concepts: Concept[] = await conceptsResp.json();
    const manifestText = await manifestResp.text();

    // Write to local cache
    if (Platform.OS === 'web') {
      webCacheWrite('articles.json', JSON.stringify(articles));
      webCacheWrite('concepts.json', JSON.stringify(concepts));
      webCacheWrite('manifest.json', manifestText);
    } else {
      getCachedFile('articles.json').write(JSON.stringify(articles));
      getCachedFile('concepts.json').write(JSON.stringify(concepts));
      getCachedFile('manifest.json').write(manifestText);
    }

    // Try to download syntheses (optional — may not exist on server yet)
    let syntheses: TopicSynthesis[] | undefined;
    try {
      const synthResp = await fetch(SYNTHESES_URL);
      if (synthResp.ok) {
        syntheses = await synthResp.json();
        if (Platform.OS === 'web') {
          webCacheWrite('syntheses.json', JSON.stringify(syntheses));
        } else {
          getCachedFile('syntheses.json').write(JSON.stringify(syntheses));
        }
      }
    } catch {
      // syntheses not available, not critical
    }

    // Try to download books index (optional — may not exist yet)
    let books: Book[] | undefined;
    try {
      const booksResp = await fetch(BOOKS_URL);
      if (booksResp.ok) {
        books = await booksResp.json();
        if (Platform.OS === 'web') {
          webCacheWrite('books.json', JSON.stringify(books));
        } else {
          getCachedFile('books.json').write(JSON.stringify(books));
        }
      }
    } catch {
      // books not available, not critical
    }

    logEvent('content_downloaded', {
      article_count: articles.length,
      concept_count: concepts.length,
      synthesis_count: syntheses?.length || 0,
      book_count: books?.length || 0,
    });

    return { articles, concepts, syntheses, books };
  } catch {
    return null;
  }
}

export async function loadCachedContent(): Promise<{ articles: Article[]; concepts: Concept[]; syntheses?: TopicSynthesis[]; books?: Book[] } | null> {
  try {
    if (Platform.OS === 'web') {
      const articlesRaw = webCacheRead('articles.json');
      const conceptsRaw = webCacheRead('concepts.json');
      if (!articlesRaw || !conceptsRaw) return null;

      let syntheses: TopicSynthesis[] | undefined;
      const synthRaw = webCacheRead('syntheses.json');
      if (synthRaw) {
        try { syntheses = JSON.parse(synthRaw); } catch {}
      }

      let books: Book[] | undefined;
      const booksRaw = webCacheRead('books.json');
      if (booksRaw) {
        try { books = JSON.parse(booksRaw); } catch {}
      }

      return {
        articles: JSON.parse(articlesRaw),
        concepts: JSON.parse(conceptsRaw),
        syntheses,
        books,
      };
    }

    const articlesFile = getCachedFile('articles.json');
    const conceptsFile = getCachedFile('concepts.json');

    if (!articlesFile.exists || !conceptsFile.exists) return null;

    let syntheses: TopicSynthesis[] | undefined;
    const synthFile = getCachedFile('syntheses.json');
    if (synthFile.exists) {
      try { syntheses = JSON.parse(await synthFile.text()); } catch {}
    }

    let books: Book[] | undefined;
    const booksFile = getCachedFile('books.json');
    if (booksFile.exists) {
      try { books = JSON.parse(await booksFile.text()); } catch {}
    }

    return {
      articles: JSON.parse(await articlesFile.text()),
      concepts: JSON.parse(await conceptsFile.text()),
      syntheses,
      books,
    };
  } catch {
    return null;
  }
}

/**
 * Fetch sections for a specific book chapter. Fetched on demand (lazy loading).
 * Caches locally after first fetch.
 */
export async function fetchBookChapterSections(bookId: string, chapterNumber: number): Promise<BookSection[] | null> {
  const cacheKey = `books/${bookId}/ch${chapterNumber}_sections.json`;

  // Try cache first
  try {
    if (Platform.OS === 'web') {
      const cached = webCacheRead(cacheKey);
      if (cached) return JSON.parse(cached);
    } else {
      const cachedFile = getCachedFile(cacheKey);
      if (cachedFile.exists) return JSON.parse(await cachedFile.text());
    }
  } catch {}

  // Fetch from server
  try {
    const url = `${CONTENT_BASE}/books/${bookId}/ch${chapterNumber}_sections.json`;
    const resp = await fetch(url);
    if (!resp.ok) return null;

    const sections: BookSection[] = await resp.json();

    // Cache
    const data = JSON.stringify(sections);
    if (Platform.OS === 'web') {
      webCacheWrite(cacheKey, data);
    } else {
      // Ensure books/{bookId} directory exists
      const { Paths, Directory, File } = getNativeFS();
      const bookDir = new Directory(Paths.document, CONTENT_DIR_NAME, 'books', bookId);
      if (!bookDir.exists) bookDir.create({ intermediates: true });
      new File(Paths.document, CONTENT_DIR_NAME, 'books', bookId, `ch${chapterNumber}_sections.json`).write(data);
    }

    logEvent('book_chapter_downloaded', { book_id: bookId, chapter: chapterNumber, section_count: sections.length });
    return sections;
  } catch {
    return null;
  }
}
