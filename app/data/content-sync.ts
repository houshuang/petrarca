import { Platform } from 'react-native';
import type { Article, KnowledgeIndex } from './types';
import { logEvent } from './logger';

const CONTENT_BASE = Platform.OS === 'web'
  ? '/content'
  : 'https://alifstian.duckdns.org/content';
const MANIFEST_URL = `${CONTENT_BASE}/manifest.json`;
const ARTICLES_URL = `${CONTENT_BASE}/articles.json`;
const KNOWLEDGE_INDEX_URL = `${CONTENT_BASE}/knowledge_index.json`;
const CLUSTERS_URL = `${CONTENT_BASE}/concept_clusters.json`;
const SYNTHESES_URL = `${CONTENT_BASE}/syntheses.json`;

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
  knowledge_index_hash?: string;
  clusters_hash?: string;
  syntheses_hash?: string;
}

export async function checkForUpdates(): Promise<boolean> {
  try {
    const resp = await fetch(MANIFEST_URL, { cache: 'no-store' });
    if (!resp.ok) return false;
    const remote: Manifest = await resp.json();

    const hasChanged = (local: Manifest) =>
      remote.articles_hash !== local.articles_hash
      || remote.knowledge_index_hash !== local.knowledge_index_hash
      || remote.clusters_hash !== local.clusters_hash
      || remote.syntheses_hash !== local.syntheses_hash;

    if (Platform.OS === 'web') {
      const localRaw = webCacheRead('manifest.json');
      if (localRaw) {
        return hasChanged(JSON.parse(localRaw));
      }
      return true;
    }

    const manifestFile = getCachedFile('manifest.json');
    if (manifestFile.exists) {
      const localRaw = await manifestFile.text();
      return hasChanged(JSON.parse(localRaw));
    }
    return true;
  } catch {
    return false;
  }
}

export interface DownloadedContent {
  articles: Article[];
  knowledgeIndex: KnowledgeIndex | null;
  conceptClusters: any | null;
  syntheses: any | null;
}

export async function downloadContent(): Promise<DownloadedContent | null> {
  try {
    if (Platform.OS !== 'web') ensureContentDir();

    const [articlesResp, manifestResp, knowledgeResp, clustersResp, synthesesResp] = await Promise.all([
      fetch(ARTICLES_URL),
      fetch(MANIFEST_URL),
      fetch(KNOWLEDGE_INDEX_URL).catch(() => null),
      fetch(CLUSTERS_URL).catch(() => null),
      fetch(SYNTHESES_URL).catch(() => null),
    ]);

    if (!articlesResp.ok) return null;

    const articles: Article[] = await articlesResp.json();
    const manifestText = await manifestResp.text();

    let knowledgeIndex: KnowledgeIndex | null = null;
    if (knowledgeResp && knowledgeResp.ok) {
      const knowledgeText = await knowledgeResp.text();
      knowledgeIndex = JSON.parse(knowledgeText);
      if (Platform.OS === 'web') {
        webCacheWrite('knowledge_index.json', knowledgeText);
      } else {
        getCachedFile('knowledge_index.json').write(knowledgeText);
      }
    }

    let conceptClusters: any = null;
    if (clustersResp && clustersResp.ok) {
      const clustersText = await clustersResp.text();
      conceptClusters = JSON.parse(clustersText);
      if (Platform.OS === 'web') {
        webCacheWrite('concept_clusters.json', clustersText);
      } else {
        getCachedFile('concept_clusters.json').write(clustersText);
      }
    }

    let syntheses: any = null;
    if (synthesesResp && synthesesResp.ok) {
      const synthesesText = await synthesesResp.text();
      const synthesesData = JSON.parse(synthesesText);
      // syntheses.json wraps the array: { meta: {...}, syntheses: [...] }
      syntheses = Array.isArray(synthesesData) ? synthesesData : synthesesData?.syntheses ?? null;
      if (Platform.OS === 'web') {
        webCacheWrite('syntheses.json', synthesesText);
      } else {
        getCachedFile('syntheses.json').write(synthesesText);
      }
    }

    if (Platform.OS === 'web') {
      webCacheWrite('articles.json', JSON.stringify(articles));
      webCacheWrite('manifest.json', manifestText);
    } else {
      getCachedFile('articles.json').write(JSON.stringify(articles));
      getCachedFile('manifest.json').write(manifestText);
    }

    logEvent('content_downloaded', {
      article_count: articles.length,
      knowledge_index: !!knowledgeIndex,
      clusters: !!conceptClusters,
      syntheses: !!syntheses,
    });
    return { articles, knowledgeIndex, conceptClusters, syntheses };
  } catch (e) {
    logEvent('content_download_error', { error: String(e) });
    return null;
  }
}

export async function loadCachedContent(): Promise<DownloadedContent | null> {
  try {
    if (Platform.OS === 'web') {
      const articlesRaw = webCacheRead('articles.json');
      if (!articlesRaw) return null;
      const knowledgeRaw = webCacheRead('knowledge_index.json');
      const clustersRaw = webCacheRead('concept_clusters.json');
      const synthesesRaw = webCacheRead('syntheses.json');
      let parsedSyntheses = null;
      if (synthesesRaw) {
        const data = JSON.parse(synthesesRaw);
        parsedSyntheses = Array.isArray(data) ? data : data?.syntheses ?? null;
      }
      return {
        articles: JSON.parse(articlesRaw),
        knowledgeIndex: knowledgeRaw ? JSON.parse(knowledgeRaw) : null,
        conceptClusters: clustersRaw ? JSON.parse(clustersRaw) : null,
        syntheses: parsedSyntheses,
      };
    }

    const articlesFile = getCachedFile('articles.json');
    if (!articlesFile.exists) return null;

    let knowledgeIndex: KnowledgeIndex | null = null;
    const knowledgeFile = getCachedFile('knowledge_index.json');
    if (knowledgeFile.exists) {
      knowledgeIndex = JSON.parse(await knowledgeFile.text());
    }

    let conceptClusters: any = null;
    const clustersFile = getCachedFile('concept_clusters.json');
    if (clustersFile.exists) {
      conceptClusters = JSON.parse(await clustersFile.text());
    }

    let syntheses: any = null;
    const synthesesFile = getCachedFile('syntheses.json');
    if (synthesesFile.exists) {
      const data = JSON.parse(await synthesesFile.text());
      syntheses = Array.isArray(data) ? data : data?.syntheses ?? null;
    }

    return { articles: JSON.parse(await articlesFile.text()), knowledgeIndex, conceptClusters, syntheses };
  } catch {
    return null;
  }
}
