import { VoiceNote } from './types';
import { updateVoiceNoteTranscript, updateVoiceNoteStatus, processTranscriptForConcepts } from './store';
import { logEvent } from './logger';

const SONIOX_API_KEY = '557c7c5a86a2f5b8fa734ddbbe179f0f21fd342c762768c9af4f4ffff8c58e1f';
const SONIOX_BASE_URL = 'https://api.soniox.com/v1';
const MODEL = 'stt-async-v4';
const POLL_INTERVAL_MS = 3000;
const POLL_TIMEOUT_MS = 5 * 60 * 1000;
const LANGUAGE_HINTS = ['en', 'no', 'sv', 'da', 'it', 'de', 'es', 'fr', 'zh', 'id'];

const headers = {
  Authorization: `Bearer ${SONIOX_API_KEY}`,
};

async function uploadFile(fileUri: string): Promise<string> {
  const formData = new FormData();
  formData.append('file', {
    uri: fileUri,
    type: 'audio/m4a',
    name: 'voice_note.m4a',
  } as any);

  const resp = await fetch(`${SONIOX_BASE_URL}/files`, {
    method: 'POST',
    headers: { Authorization: headers.Authorization },
    body: formData,
  });
  if (!resp.ok) throw new Error(`Upload failed: ${resp.status}`);
  const data = await resp.json();
  return data.id;
}

async function createTranscription(fileId: string): Promise<string> {
  const resp = await fetch(`${SONIOX_BASE_URL}/transcriptions`, {
    method: 'POST',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: MODEL,
      file_id: fileId,
      language_hints: LANGUAGE_HINTS,
    }),
  });
  if (!resp.ok) throw new Error(`Create transcription failed: ${resp.status}`);
  const data = await resp.json();
  return data.id;
}

async function pollUntilComplete(transcriptionId: string): Promise<void> {
  const start = Date.now();
  while (true) {
    const resp = await fetch(`${SONIOX_BASE_URL}/transcriptions/${transcriptionId}`, {
      headers,
    });
    if (!resp.ok) throw new Error(`Poll failed: ${resp.status}`);
    const data = await resp.json();

    if (data.status === 'completed') return;
    if (data.status === 'error') throw new Error(`Transcription error: ${data.error_message || 'unknown'}`);
    if (Date.now() - start > POLL_TIMEOUT_MS) throw new Error('Transcription timed out');

    await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));
  }
}

async function getTranscriptText(transcriptionId: string): Promise<string> {
  const resp = await fetch(`${SONIOX_BASE_URL}/transcriptions/${transcriptionId}/transcript`, {
    headers,
  });
  if (!resp.ok) throw new Error(`Get transcript failed: ${resp.status}`);
  const data = await resp.json();
  // Extract plain text from tokens
  if (data.tokens && Array.isArray(data.tokens)) {
    return data.tokens.map((t: any) => t.text).join('').trim();
  }
  if (data.text) return data.text.trim();
  return '';
}

async function cleanup(fileId: string | null, transcriptionId: string | null): Promise<void> {
  if (transcriptionId) {
    try { await fetch(`${SONIOX_BASE_URL}/transcriptions/${transcriptionId}`, { method: 'DELETE', headers }); } catch {}
  }
  if (fileId) {
    try { await fetch(`${SONIOX_BASE_URL}/files/${fileId}`, { method: 'DELETE', headers }); } catch {}
  }
}

export async function transcribeVoiceNote(note: VoiceNote): Promise<string | null> {
  let fileId: string | null = null;
  let transcriptionId: string | null = null;

  updateVoiceNoteStatus(note.id, 'processing');
  logEvent('transcription_start', { note_id: note.id, article_id: note.article_id });

  try {
    fileId = await uploadFile(note.file_uri);
    transcriptionId = await createTranscription(fileId);
    await pollUntilComplete(transcriptionId);
    const text = await getTranscriptText(transcriptionId);

    if (text) {
      updateVoiceNoteTranscript(note.id, text);
      processTranscriptForConcepts(note.article_id, text, note.id);
      logEvent('transcription_complete', { note_id: note.id, article_id: note.article_id, length: text.length });
      return text;
    } else {
      updateVoiceNoteStatus(note.id, 'failed');
      logEvent('transcription_empty', { note_id: note.id });
      return null;
    }
  } catch (err: any) {
    console.warn('[transcription] failed:', err.message);
    updateVoiceNoteStatus(note.id, 'failed');
    logEvent('transcription_error', { note_id: note.id, error: err.message });
    return null;
  } finally {
    await cleanup(fileId, transcriptionId);
  }
}

export async function transcribeAllPending(notes: VoiceNote[]): Promise<number> {
  const pending = notes.filter(n => n.transcription_status === 'pending');
  let completed = 0;
  for (const note of pending) {
    const result = await transcribeVoiceNote(note);
    if (result) completed++;
  }
  return completed;
}
