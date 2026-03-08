import AsyncStorage from '@react-native-async-storage/async-storage';
import { logEvent } from './logger';

const QUEUE_KEY = '@petrarca/reading_queue';

let queuedIds: string[] = [];
let loaded = false;

export async function loadQueue(): Promise<void> {
  try {
    const raw = await AsyncStorage.getItem(QUEUE_KEY);
    if (raw) queuedIds = JSON.parse(raw);
    loaded = true;
  } catch (e) {
    console.warn('[queue] failed to load:', e);
    queuedIds = [];
    loaded = true;
  }
}

async function saveQueue(): Promise<void> {
  try {
    await AsyncStorage.setItem(QUEUE_KEY, JSON.stringify(queuedIds));
  } catch (e) {
    console.warn('[queue] failed to save:', e);
  }
}

export async function addToQueue(articleId: string): Promise<void> {
  if (!loaded) await loadQueue();
  if (queuedIds.includes(articleId)) return;
  queuedIds.push(articleId);
  await saveQueue();
  logEvent('queue_add', { article_id: articleId });
}

export async function removeFromQueue(articleId: string): Promise<void> {
  if (!loaded) await loadQueue();
  queuedIds = queuedIds.filter(id => id !== articleId);
  await saveQueue();
  logEvent('queue_remove', { article_id: articleId });
}

export function getQueuedArticleIds(): string[] {
  return [...queuedIds];
}

export function isQueued(articleId: string): boolean {
  return queuedIds.includes(articleId);
}
