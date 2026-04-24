import { Platform } from 'react-native';
import type { ArticleMeta, KnowledgeIndex } from './types';
import { logEvent } from './logger';
import { getContentBaseUrl, getResearchServerUrl } from '../lib/server-urls';
import { fetchWithTimeout } from '../lib/chat-api';

/** Avoid hanging forever on unreachable research server (blocks root layout). */
const T_MANIFEST_MS = 20_000;
const T_ARTICLES_MS = 90_000;
const T_JSON_MS = 60_000;

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

function cacheWrite(name: string, data: string) {
  if (Platform.OS === 'web') {
    webCacheWrite(name, data);
  } else {
    try {
      ensureContentDir();
      getCachedFile(name).write(data);
    } catch {}
  }
}

function cacheRead(name: string): string | null {
  if (Platform.OS === 'web') {
    return webCacheRead(name);
  }
  try {
    const file = getCachedFile(name);
    // expo-file-system File.text() is sync in newer versions
    return file.exists ? file.text() : null;
  } catch {
    return null;
  }
}

// --- Change detection ---

function getLocalManifest(): Manifest | null {
  const raw = cacheRead('manifest.json');
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

export async function checkForUpdates(): Promise<boolean> {
  try {
    const resp = await fetchWithTimeout(`${getResearchServerUrl()}/api/manifest`, {
      cache: 'no-store',
      timeout: T_MANIFEST_MS,
    });
    if (!resp.ok) return false;
    const remote: Manifest = await resp.json();

    const local = getLocalManifest();
    if (!local) return true;

    return remote.articles_hash !== local.articles_hash
      || remote.knowledge_index_hash !== local.knowledge_index_hash
      || remote.clusters_hash !== local.clusters_hash
      || remote.syntheses_hash !== local.syntheses_hash;
  } catch {
    return false;
  }
}

// --- Download ---

export interface DownloadedContent {
  articles: ArticleMeta[];
  knowledgeIndex: KnowledgeIndex | null;
  conceptClusters: any | null;
  syntheses: any | null;
}

/** Try incremental article sync, fall back to full download. */
export async function downloadContent(): Promise<DownloadedContent | null> {
  try {
    if (Platform.OS !== 'web') ensureContentDir();

    // Check if we can do an incremental sync for articles
    const localManifest = getLocalManifest();
    const cachedArticlesRaw = cacheRead('articles_meta.json');
    const canIncremental = localManifest?.last_updated && cachedArticlesRaw;

    // Fetch manifest first to know what changed
    const manifestResp = await fetchWithTimeout(`${getResearchServerUrl()}/api/manifest`, {
      cache: 'no-store',
      timeout: T_MANIFEST_MS,
    });
    if (!manifestResp.ok) return downloadContentFallback();
    const manifestText = await manifestResp.text();
    const remoteManifest: Manifest = JSON.parse(manifestText);

    const articlesChanged = !localManifest || remoteManifest.articles_hash !== localManifest.articles_hash;
    const knowledgeChanged = !localManifest || remoteManifest.knowledge_index_hash !== localManifest.knowledge_index_hash;
    const clustersChanged = !localManifest || remoteManifest.clusters_hash !== localManifest.clusters_hash;
    const synthesesChanged = !localManifest || remoteManifest.syntheses_hash !== localManifest.syntheses_hash;

    // --- Articles: incremental or full ---
    let articles: ArticleMeta[];
    let syncMode: string;

    if (!articlesChanged && cachedArticlesRaw) {
      // No change — use cache
      articles = JSON.parse(cachedArticlesRaw);
      syncMode = 'cached';
    } else if (canIncremental && articlesChanged) {
      // Try incremental: fetch only articles since last sync
      const since = localManifest!.last_updated;
      const incResp = await fetchWithTimeout(
        `${getResearchServerUrl()}/api/articles-meta?since=${encodeURIComponent(since)}`,
        { timeout: T_ARTICLES_MS },
      );
      if (incResp.ok) {
        const incData = await incResp.json();
        const newArticles: ArticleMeta[] = incData.articles || incData;
        const cached: ArticleMeta[] = JSON.parse(cachedArticlesRaw!);

        // Merge: index cached by ID, overlay with new
        const byId = new Map(cached.map(a => [a.id, a]));
        for (const a of newArticles) byId.set(a.id, a);
        articles = Array.from(byId.values());

        if (articles.length === remoteManifest.article_count) {
          syncMode = 'incremental';
        } else {
          // Count mismatch (deletions or missed articles) — full download
          const fullResp = await fetchWithTimeout(`${getResearchServerUrl()}/api/articles-meta`, {
            timeout: T_ARTICLES_MS,
          });
          if (!fullResp.ok) return downloadContentFallback();
          const fullData = await fullResp.json();
          articles = fullData.articles || fullData;
          syncMode = 'full_after_mismatch';
        }
      } else {
        // Incremental endpoint failed — full download
        const fullResp = await fetchWithTimeout(`${getResearchServerUrl()}/api/articles-meta`, {
          timeout: T_ARTICLES_MS,
        });
        if (!fullResp.ok) return downloadContentFallback();
        const fullData = await fullResp.json();
        articles = fullData.articles || fullData;
        syncMode = 'full';
      }
    } else {
      // No cache or first launch — full download
      const fullResp = await fetchWithTimeout(`${getResearchServerUrl()}/api/articles-meta`, {
        timeout: T_ARTICLES_MS,
      });
      if (!fullResp.ok) return downloadContentFallback();
      const fullData = await fullResp.json();
      articles = fullData.articles || fullData;
      syncMode = 'full';
    }

    // --- Knowledge index, clusters, syntheses: fetch only if changed ---
    const [knowledgeResp, clustersResp, synthesesResp] = await Promise.all([
      knowledgeChanged
        ? fetchWithTimeout(`${getResearchServerUrl()}/api/knowledge-index`, { timeout: T_JSON_MS }).catch(() => null)
        : null,
      clustersChanged
        ? fetchWithTimeout(`${getResearchServerUrl()}/api/clusters`, { timeout: T_JSON_MS }).catch(() => null)
        : null,
      synthesesChanged
        ? fetchWithTimeout(`${getResearchServerUrl()}/api/syntheses`, { timeout: T_JSON_MS }).catch(() => null)
        : null,
    ]);

    let knowledgeIndex: KnowledgeIndex | null = null;
    if (knowledgeResp && knowledgeResp.ok) {
      const knowledgeText = await knowledgeResp.text();
      knowledgeIndex = JSON.parse(knowledgeText);
      cacheWrite('knowledge_index.json', knowledgeText);
    } else if (!knowledgeChanged) {
      // Use cache
      const raw = cacheRead('knowledge_index.json');
      if (raw) knowledgeIndex = JSON.parse(raw);
    }

    let conceptClusters: any = null;
    if (clustersResp && clustersResp.ok) {
      const clustersText = await clustersResp.text();
      conceptClusters = JSON.parse(clustersText);
      cacheWrite('concept_clusters.json', clustersText);
    } else if (!clustersChanged) {
      const raw = cacheRead('concept_clusters.json');
      if (raw) conceptClusters = JSON.parse(raw);
    }

    let syntheses: any = null;
    if (synthesesResp && synthesesResp.ok) {
      const synthesesData = JSON.parse(await synthesesResp.text());
      syntheses = Array.isArray(synthesesData) ? synthesesData : synthesesData?.syntheses ?? null;
      cacheWrite('syntheses.json', JSON.stringify(synthesesData));
    } else if (!synthesesChanged) {
      const raw = cacheRead('syntheses.json');
      if (raw) {
        const data = JSON.parse(raw);
        syntheses = Array.isArray(data) ? data : data?.syntheses ?? null;
      }
    }

    // Persist articles + manifest
    cacheWrite('articles_meta.json', JSON.stringify(articles));
    cacheWrite('manifest.json', manifestText);

    logEvent('content_downloaded', {
      article_count: articles.length,
      knowledge_index: !!knowledgeIndex,
      clusters: !!conceptClusters,
      syntheses: !!syntheses,
      source: 'api',
      sync_mode: syncMode,
    });
    return { articles, knowledgeIndex, conceptClusters, syntheses };
  } catch (e) {
    logEvent('content_download_error', { error: String(e) });
    return downloadContentFallback();
  }
}

/** Fallback: download from nginx-served JSON files (pre-Phase 4 compatibility). */
async function downloadContentFallback(): Promise<DownloadedContent | null> {
  try {
    if (Platform.OS !== 'web') ensureContentDir();

    const [articlesResp, manifestResp, knowledgeResp, clustersResp, synthesesResp] = await Promise.all([
      fetchWithTimeout(`${getContentBaseUrl()}/articles.json`, { timeout: T_ARTICLES_MS }),
      fetchWithTimeout(`${getContentBaseUrl()}/manifest.json`, { timeout: T_MANIFEST_MS }),
      fetchWithTimeout(`${getContentBaseUrl()}/knowledge_index.json`, { timeout: T_JSON_MS }).catch(() => null),
      fetchWithTimeout(`${getContentBaseUrl()}/concept_clusters.json`, { timeout: T_JSON_MS }).catch(() => null),
      fetchWithTimeout(`${getContentBaseUrl()}/syntheses.json`, { timeout: T_JSON_MS }).catch(() => null),
    ]);

    if (!articlesResp.ok) return null;

    const fullArticles = await articlesResp.json();
    // Strip content_markdown and sections for in-memory use
    const articles: ArticleMeta[] = fullArticles.map((a: any) => {
      const { content_markdown, sections, ...meta } = a;
      return meta;
    });
    const manifestText = await manifestResp.text();

    let knowledgeIndex: KnowledgeIndex | null = null;
    if (knowledgeResp && knowledgeResp.ok) {
      const knowledgeText = await knowledgeResp.text();
      knowledgeIndex = JSON.parse(knowledgeText);
      cacheWrite('knowledge_index.json', knowledgeText);
    }

    let conceptClusters: any = null;
    if (clustersResp && clustersResp.ok) {
      const clustersText = await clustersResp.text();
      conceptClusters = JSON.parse(clustersText);
      cacheWrite('concept_clusters.json', clustersText);
    }

    let syntheses: any = null;
    if (synthesesResp && synthesesResp.ok) {
      const synthesesData = JSON.parse(await synthesesResp.text());
      syntheses = Array.isArray(synthesesData) ? synthesesData : synthesesData?.syntheses ?? null;
      cacheWrite('syntheses.json', JSON.stringify(synthesesData));
    }

    cacheWrite('articles_meta.json', JSON.stringify(articles));
    cacheWrite('manifest.json', manifestText);

    logEvent('content_downloaded', {
      article_count: articles.length,
      knowledge_index: !!knowledgeIndex,
      clusters: !!conceptClusters,
      syntheses: !!syntheses,
      source: 'fallback_json',
    });
    return { articles, knowledgeIndex, conceptClusters, syntheses };
  } catch (e) {
    logEvent('content_download_fallback_error', { error: String(e) });
    return null;
  }
}

// --- Load cached ---

export async function loadCachedContent(): Promise<DownloadedContent | null> {
  try {
    // Try new meta-only cache first, fall back to old full articles cache
    let articlesRaw = cacheRead('articles_meta.json');
    if (!articlesRaw) {
      // Fall back to old cache (full articles) — strip content fields
      articlesRaw = cacheRead('articles.json');
      if (!articlesRaw) return null;
      const full = JSON.parse(articlesRaw);
      const stripped = full.map((a: any) => {
        const { content_markdown, sections, ...meta } = a;
        return meta;
      });
      articlesRaw = JSON.stringify(stripped);
    }

    const knowledgeRaw = cacheRead('knowledge_index.json');
    const clustersRaw = cacheRead('concept_clusters.json');
    const synthesesRaw = cacheRead('syntheses.json');

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
  } catch {
    return null;
  }
}
