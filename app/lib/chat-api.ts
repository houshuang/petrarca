import { Platform } from 'react-native';

const RESEARCH_BASE = Platform.OS === 'web'
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
