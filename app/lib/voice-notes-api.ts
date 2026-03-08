import { Platform } from 'react-native';

const RESEARCH_BASE = Platform.OS === 'web'
  ? `${window.location.protocol}//${window.location.hostname}:8090`
  : 'http://alifstian.duckdns.org:8090';

export interface NoteAction {
  id: string;
  type: 'research' | 'tag' | 'remember';
  description: string;
  topic?: string;
  tag?: string;
  note_text?: string;
  status: 'pending' | 'running' | 'done' | 'failed';
}

export interface VoiceNote {
  id: string;
  article_id: string;
  article_title: string;
  topics: string[];
  transcript?: string;
  status: string;
  created_at: number;
  duration?: number;
  actions?: NoteAction[];
}

export async function fetchAllNotes(): Promise<VoiceNote[]> {
  try {
    const resp = await fetch(`${RESEARCH_BASE}/notes`);
    if (!resp.ok) return [];
    return resp.json();
  } catch {
    return [];
  }
}

export async function fetchArticleNotes(articleId: string): Promise<VoiceNote[]> {
  try {
    const resp = await fetch(`${RESEARCH_BASE}/notes?article_id=${articleId}`);
    if (!resp.ok) return [];
    return resp.json();
  } catch {
    return [];
  }
}

export async function executeNoteAction(
  noteId: string,
  actionId: string,
): Promise<{ action_id: string; status: string }> {
  const resp = await fetch(`${RESEARCH_BASE}/notes/${noteId}/execute-action`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action_id: actionId }),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Execute action failed (${resp.status}): ${text}`);
  }
  return resp.json();
}
