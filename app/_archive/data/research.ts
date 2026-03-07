import AsyncStorage from '@react-native-async-storage/async-storage';
import { ResearchResult } from './types';
import { logEvent } from './logger';

const RESEARCH_RESULTS_KEY = '@petrarca/research_results';
const RESEARCH_SERVER_URL = 'http://alifstian.duckdns.org:8090';

let researchResults: ResearchResult[] = [];
let loaded = false;

async function ensureLoaded() {
  if (loaded) return;
  try {
    const raw = await AsyncStorage.getItem(RESEARCH_RESULTS_KEY);
    if (raw) researchResults = JSON.parse(raw);
  } catch (e) {
    console.warn('[research] failed to load results:', e);
  }
  loaded = true;
}

async function save() {
  try {
    await AsyncStorage.setItem(RESEARCH_RESULTS_KEY, JSON.stringify(researchResults));
  } catch (e) {
    console.warn('[research] failed to save results:', e);
  }
}

export async function triggerResearch(params: {
  query: string;
  articleId: string;
  articleTitle: string;
  articleSummary: string;
  concepts: string[];
  voiceNoteId?: string;
}): Promise<ResearchResult> {
  await ensureLoaded();

  const id = `res_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
  const result: ResearchResult = {
    id,
    query: params.query,
    article_id: params.articleId,
    article_title: params.articleTitle,
    voice_note_id: params.voiceNoteId,
    status: 'pending',
    requested_at: Date.now(),
  };

  researchResults.unshift(result);
  await save();

  logEvent('research_triggered', {
    research_id: id,
    article_id: params.articleId,
    voice_note_id: params.voiceNoteId,
    query_length: params.query.length,
  });

  // Send to server (fire-and-forget, update status on response)
  try {
    const resp = await fetch(`${RESEARCH_SERVER_URL}/research`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id,
        query: params.query,
        article_title: params.articleTitle,
        article_summary: params.articleSummary,
        concepts: params.concepts,
      }),
    });

    if (resp.ok) {
      result.status = 'processing';
      await save();
    } else {
      result.status = 'failed';
      result.error = `Server returned ${resp.status}`;
      await save();
    }
  } catch (err: any) {
    result.status = 'failed';
    result.error = err.message;
    await save();
    logEvent('research_trigger_failed', { research_id: id, error: err.message });
  }

  return result;
}

export async function fetchResearchResults(): Promise<number> {
  await ensureLoaded();

  let fetched = 0;
  try {
    const resp = await fetch(`${RESEARCH_SERVER_URL}/research/results`);
    if (!resp.ok) return 0;

    const serverResults: ResearchResult[] = await resp.json();

    for (const sr of serverResults) {
      const existing = researchResults.find(r => r.id === sr.id);
      if (existing && existing.status !== 'completed') {
        existing.status = sr.status;
        existing.completed_at = sr.completed_at;
        existing.perspectives = sr.perspectives;
        existing.recommendations = sr.recommendations;
        existing.connections = sr.connections;
        existing.error = sr.error;
        fetched++;
      } else if (!existing) {
        researchResults.unshift(sr);
        fetched++;
      }
    }

    if (fetched > 0) {
      await save();
      logEvent('research_results_fetched', { count: fetched });
    }
  } catch (err: any) {
    console.warn('[research] failed to fetch results:', err.message);
  }

  return fetched;
}

export async function getResearchResults(): Promise<ResearchResult[]> {
  await ensureLoaded();
  return [...researchResults];
}

export async function getResearchResultsForArticle(articleId: string): Promise<ResearchResult[]> {
  await ensureLoaded();
  return researchResults.filter(r => r.article_id === articleId);
}
