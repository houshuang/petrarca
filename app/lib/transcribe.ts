const SONIOX_API_KEY = '557c7c5a86a2f5b8fa734ddbbe179f0f21fd342c762768c9af4f4ffff8c58e1f';
const SONIOX_BASE_URL = 'https://api.soniox.com/v1';
const MODEL = 'stt-async-v4';
const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 3 * 60 * 1000;
const LANGUAGE_HINTS = ['en', 'no', 'sv', 'da', 'it', 'de', 'es', 'fr', 'zh', 'id'];

const headers = { Authorization: `Bearer ${SONIOX_API_KEY}` };

async function uploadFile(fileUri: string): Promise<string> {
  const formData = new FormData();
  formData.append('file', {
    uri: fileUri,
    type: 'audio/m4a',
    name: 'feedback.m4a',
  } as any);
  const resp = await fetch(`${SONIOX_BASE_URL}/files`, {
    method: 'POST',
    headers: { Authorization: headers.Authorization },
    body: formData,
  });
  if (!resp.ok) throw new Error(`Upload failed: ${resp.status}`);
  return (await resp.json()).id;
}

async function createTranscription(fileId: string): Promise<string> {
  const resp = await fetch(`${SONIOX_BASE_URL}/transcriptions`, {
    method: 'POST',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: MODEL, file_id: fileId, language_hints: LANGUAGE_HINTS }),
  });
  if (!resp.ok) throw new Error(`Transcription create failed: ${resp.status}`);
  return (await resp.json()).id;
}

async function pollUntilComplete(transcriptionId: string): Promise<void> {
  const start = Date.now();
  while (true) {
    const resp = await fetch(`${SONIOX_BASE_URL}/transcriptions/${transcriptionId}`, { headers });
    if (!resp.ok) throw new Error(`Poll failed: ${resp.status}`);
    const data = await resp.json();
    if (data.status === 'completed') return;
    if (data.status === 'error') throw new Error(`Transcription error: ${data.error_message}`);
    if (Date.now() - start > POLL_TIMEOUT_MS) throw new Error('Transcription timed out');
    await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));
  }
}

async function getTranscriptText(transcriptionId: string): Promise<string> {
  const resp = await fetch(`${SONIOX_BASE_URL}/transcriptions/${transcriptionId}/transcript`, { headers });
  if (!resp.ok) throw new Error(`Get transcript failed: ${resp.status}`);
  const data = await resp.json();
  if (data.tokens && Array.isArray(data.tokens)) {
    return data.tokens.map((t: any) => t.text).join('').trim();
  }
  return (data.text || '').trim();
}

async function cleanup(fileId: string | null, transcriptionId: string | null): Promise<void> {
  if (transcriptionId) {
    try { await fetch(`${SONIOX_BASE_URL}/transcriptions/${transcriptionId}`, { method: 'DELETE', headers }); } catch {}
  }
  if (fileId) {
    try { await fetch(`${SONIOX_BASE_URL}/files/${fileId}`, { method: 'DELETE', headers }); } catch {}
  }
}

export async function transcribeAudio(fileUri: string): Promise<string> {
  let fileId: string | null = null;
  let transcriptionId: string | null = null;
  try {
    fileId = await uploadFile(fileUri);
    transcriptionId = await createTranscription(fileId);
    await pollUntilComplete(transcriptionId);
    return await getTranscriptText(transcriptionId);
  } finally {
    await cleanup(fileId, transcriptionId);
  }
}
