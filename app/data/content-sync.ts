import { Paths, File, Directory } from 'expo-file-system';
import { Article, Concept, TopicSynthesis } from './types';
import { logEvent } from './logger';

const CONTENT_BASE = 'http://alifstian.duckdns.org:8083/content';
const MANIFEST_URL = `${CONTENT_BASE}/manifest.json`;
const ARTICLES_URL = `${CONTENT_BASE}/articles.json`;
const CONCEPTS_URL = `${CONTENT_BASE}/concepts.json`;
const SYNTHESES_URL = `${CONTENT_BASE}/syntheses.json`;

const CONTENT_DIR_NAME = 'content';

function getContentDir(): Directory {
  return new Directory(Paths.document, CONTENT_DIR_NAME);
}

function getCachedFile(name: string): File {
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
}

export async function checkForUpdates(): Promise<boolean> {
  try {
    const resp = await fetch(MANIFEST_URL, { cache: 'no-store' });
    if (!resp.ok) return false;
    const remote: Manifest = await resp.json();

    const manifestFile = getCachedFile('manifest.json');
    if (manifestFile.exists) {
      const localRaw = await manifestFile.text();
      const local: Manifest = JSON.parse(localRaw);
      return remote.articles_hash !== local.articles_hash
          || remote.concepts_hash !== local.concepts_hash;
    }
    // No cached manifest = first sync
    return true;
  } catch {
    return false; // offline or server unreachable
  }
}

export async function downloadContent(): Promise<{ articles: Article[]; concepts: Concept[]; syntheses?: TopicSynthesis[] } | null> {
  try {
    ensureContentDir();

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
    getCachedFile('articles.json').write(JSON.stringify(articles));
    getCachedFile('concepts.json').write(JSON.stringify(concepts));
    getCachedFile('manifest.json').write(manifestText);

    // Try to download syntheses (optional — may not exist on server yet)
    let syntheses: TopicSynthesis[] | undefined;
    try {
      const synthResp = await fetch(SYNTHESES_URL);
      if (synthResp.ok) {
        syntheses = await synthResp.json();
        getCachedFile('syntheses.json').write(JSON.stringify(syntheses));
      }
    } catch {
      // syntheses not available, not critical
    }

    logEvent('content_downloaded', {
      article_count: articles.length,
      concept_count: concepts.length,
      synthesis_count: syntheses?.length || 0,
    });

    return { articles, concepts, syntheses };
  } catch {
    return null;
  }
}

export async function loadCachedContent(): Promise<{ articles: Article[]; concepts: Concept[]; syntheses?: TopicSynthesis[] } | null> {
  try {
    const articlesFile = getCachedFile('articles.json');
    const conceptsFile = getCachedFile('concepts.json');

    if (!articlesFile.exists || !conceptsFile.exists) return null;

    let syntheses: TopicSynthesis[] | undefined;
    const synthFile = getCachedFile('syntheses.json');
    if (synthFile.exists) {
      try { syntheses = JSON.parse(await synthFile.text()); } catch {}
    }

    return {
      articles: JSON.parse(await articlesFile.text()),
      concepts: JSON.parse(await conceptsFile.text()),
      syntheses,
    };
  } catch {
    return null;
  }
}
