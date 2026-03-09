import { Platform } from 'react-native';

export const RESEARCH_BASE = Platform.OS === 'web'
  ? `${window.location.protocol}//${window.location.hostname}:8090`
  : 'http://alifstian.duckdns.org:8090';

interface ChatResponse {
  answer: string;
  conversation_id: string;
}

export async function askAI(
  question: string,
  context: string,
  conversationId?: string,
): Promise<ChatResponse> {
  const resp = await fetch(`${RESEARCH_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question,
      context,
      conversation_id: conversationId || undefined,
    }),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Chat failed (${resp.status}): ${text}`);
  }
  return resp.json();
}

export async function uploadVoiceNote(
  audioUri: string,
  articleId: string,
  articleTitle: string,
  topics: string[],
  articleContext: string,
): Promise<{ id: string }> {
  const formData = new FormData();
  formData.append('audio', {
    uri: audioUri,
    type: 'audio/m4a',
    name: 'note.m4a',
  } as any);
  formData.append('article_id', articleId);
  formData.append('article_title', articleTitle);
  formData.append('topics', JSON.stringify(topics));
  formData.append('article_context', articleContext.slice(0, 2000));

  const resp = await fetch(`${RESEARCH_BASE}/note`, {
    method: 'POST',
    body: formData,
  });
  if (!resp.ok) throw new Error(`Upload failed: ${resp.status}`);
  return resp.json();
}

export async function spawnTopicResearch(
  topic: string,
  context: string,
  articleTitles: string[],
): Promise<{ id: string; status: string }> {
  const resp = await fetch(`${RESEARCH_BASE}/research/topic`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      topic,
      context,
      article_titles: articleTitles,
    }),
  });
  if (!resp.ok) throw new Error(`Research failed: ${resp.status}`);
  return resp.json();
}

// --- Article ingestion from links ---

export interface IngestResponse {
  status: string;
  url: string;
  ingest_id: string;
  article_id: string;
}

export interface IngestStatus {
  id: string;
  status: 'processing' | 'completed' | 'failed' | 'unknown';
  article_id?: string;
  url?: string;
}

export async function ingestUrl(url: string, source: string = 'reader_link'): Promise<IngestResponse> {
  const resp = await fetch(`${RESEARCH_BASE}/ingest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, source }),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Ingest failed (${resp.status}): ${text}`);
  }
  return resp.json();
}

export async function getIngestStatus(ingestId: string): Promise<IngestStatus> {
  const resp = await fetch(`${RESEARCH_BASE}/ingest-status?id=${encodeURIComponent(ingestId)}`);
  if (!resp.ok) {
    return { id: ingestId, status: 'unknown' };
  }
  return resp.json();
}

// --- Voice notes ---

export interface VoiceNote {
  id: string;
  article_id: string;
  article_title: string;
  topics: string[];
  transcript?: string;
  status: string;
  created_at: number;
}

export async function fetchNotes(articleId?: string): Promise<VoiceNote[]> {
  const url = articleId
    ? `${RESEARCH_BASE}/notes?article_id=${articleId}`
    : `${RESEARCH_BASE}/notes`;
  const resp = await fetch(url);
  if (!resp.ok) return [];
  return resp.json();
}
