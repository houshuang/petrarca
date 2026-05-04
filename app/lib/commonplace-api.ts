import { RESEARCH_BASE, fetchWithTimeout } from './chat-api';

export interface CommonplaceEcho {
  chunk_id: string;
  chunk_text: string;
  chunk_type: string;
  similarity: number;
  transcript_id: string;
  transcript_source: string;
  transcript_date: number;
  days_ago: number;
  transcript_node_title: string;
  transcript_excerpt: string;
}

export interface ResurfaceResult {
  echoes: CommonplaceEcho[];
  query_excerpt: string;
  meta: {
    threshold?: number;
    min_age_days?: number;
    candidates_scanned?: number;
    matches_above_threshold?: number;
    error?: string;
  };
  event_id?: string;
  transcript?: string;   // present when query_source = 'audio'
  error?: string;
}

export async function resurfaceFromText(
  queryText: string,
  opts: { minAgeDays?: number; threshold?: number; maxResults?: number; source?: string } = {},
): Promise<ResurfaceResult> {
  const res = await fetchWithTimeout(`${RESEARCH_BASE}/commonplace/resurface`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query_text: queryText,
      min_age_days: opts.minAgeDays ?? 30,
      threshold: opts.threshold ?? 0.55,
      max_results: opts.maxResults ?? 5,
      source: opts.source ?? 'manual',
    }),
    timeout: 30000,
  });
  if (!res.ok && res.status !== 400) {
    throw new Error(`resurface failed: ${res.status}`);
  }
  return res.json();
}

export async function resurfaceFromAudio(
  audioUri: string,
  opts: { minAgeDays?: number; threshold?: number; maxResults?: number } = {},
): Promise<ResurfaceResult> {
  const form = new FormData();
  form.append('audio', { uri: audioUri, type: 'audio/m4a', name: 'commonplace.m4a' } as any);
  form.append('min_age_days', String(opts.minAgeDays ?? 30));
  form.append('threshold', String(opts.threshold ?? 0.55));
  form.append('max_results', String(opts.maxResults ?? 5));
  const res = await fetchWithTimeout(`${RESEARCH_BASE}/commonplace/resurface-audio`, {
    method: 'POST',
    body: form,
    timeout: 120000,
  });
  if (res.status === 422) return res.json();
  if (!res.ok) throw new Error(`resurface-audio failed: ${res.status}`);
  return res.json();
}

export async function transcribeAudio(audioUri: string): Promise<{ transcript: string; error?: string }> {
  const form = new FormData();
  form.append('audio', { uri: audioUri, type: 'audio/m4a', name: 'voice.m4a' } as any);
  const res = await fetchWithTimeout(`${RESEARCH_BASE}/defender/transcribe`, {
    method: 'POST',
    body: form,
    timeout: 90000,
  });
  if (res.status === 422 || res.status === 200) return res.json();
  throw new Error(`transcribe failed: ${res.status}`);
}
