import AsyncStorage from '@react-native-async-storage/async-storage';
import { logEvent } from './logger';

const QUEUE_KEY = '@petrarca/exploration_queue';
const FLUSH_THRESHOLD = 5;

// Server URL (same as research server)
const RESEARCH_SERVER = 'http://alifstian.duckdns.org:8090';

interface ExplorationItem {
  conceptId: string;
  name: string;
  articleContextId: string;
  articleTitle?: string;
  articleSummary?: string;
  queuedAt: number;
}

let queue: ExplorationItem[] = [];
let loaded = false;

async function ensureLoaded(): Promise<void> {
  if (loaded) return;
  try {
    const raw = await AsyncStorage.getItem(QUEUE_KEY);
    if (raw) queue = JSON.parse(raw);
  } catch (e) {
    console.warn('[exploration] failed to load queue:', e);
  }
  loaded = true;
}

async function saveQueue(): Promise<void> {
  try {
    await AsyncStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
  } catch (e) {
    console.warn('[exploration] failed to save queue:', e);
  }
}

export async function queueExploration(
  conceptId: string,
  name: string,
  articleContextId: string,
  articleTitle?: string,
  articleSummary?: string,
): Promise<number> {
  await ensureLoaded();

  // Dedup by conceptId
  if (queue.some(item => item.conceptId === conceptId)) {
    return queue.length;
  }

  queue.push({
    conceptId,
    name,
    articleContextId,
    articleTitle,
    articleSummary,
    queuedAt: Date.now(),
  });

  await saveQueue();

  logEvent('exploration_queued', {
    concept_id: conceptId,
    concept_name: name,
    article_id: articleContextId,
    queue_length: queue.length,
  });

  // Auto-flush when threshold reached
  if (queue.length >= FLUSH_THRESHOLD) {
    flushExplorationQueue().catch(() => {});
  }

  return queue.length;
}

export async function getExplorationQueue(): Promise<ExplorationItem[]> {
  await ensureLoaded();
  return [...queue];
}

export async function getQueueLength(): Promise<number> {
  await ensureLoaded();
  return queue.length;
}

export async function flushExplorationQueue(): Promise<boolean> {
  await ensureLoaded();
  if (queue.length === 0) return true;

  const batch = queue.map(item => ({
    id: item.conceptId,
    name: item.name,
    context_article_title: item.articleTitle || '',
    context_article_summary: item.articleSummary || '',
  }));

  logEvent('exploration_flush_start', { count: batch.length });

  try {
    const response = await fetch(`${RESEARCH_SERVER}/research/explore-batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ concepts: batch }),
    });

    if (response.ok) {
      queue = [];
      await saveQueue();
      logEvent('exploration_flush_success', { count: batch.length });
      return true;
    } else {
      logEvent('exploration_flush_failed', { status: response.status });
      return false;
    }
  } catch (e) {
    logEvent('exploration_flush_error', { error: String(e) });
    return false;
  }
}
