import { RESEARCH_BASE, fetchWithTimeout } from './chat-api';

export interface DefenderObjection {
  angle: string;
  text: string;
  evidence_hint?: string;
}

export interface DefenderStartResult {
  session_id: string;
  thesis: string;
  objections: DefenderObjection[];
  context_summary: string;
  error?: string;
}

export interface DefenderGrade {
  engagement?: string;
  evidence?: string;
  concession?: string;
  feedback?: string;
}

export interface DefenderRespondResult {
  session_id: string;
  grade: DefenderGrade;
  next_move: 'follow_up_objection' | 'concede_and_pivot' | 'conclude';
  follow_up?: DefenderObjection | null;
  conclusion?: string | null;
  status: 'active' | 'concluded';
  round_count: number;
  error?: string;
}

export interface DefenderSessionSummary {
  id: string;
  thesis: string;
  domain_id?: string;
  node_id?: string;
  entity_name?: string;
  status: 'active' | 'concluded';
  created_at: number;
  concluded_at?: number;
  rounds: number;
}

async function postJson<T>(path: string, body: object, timeoutMs = 120000): Promise<T> {
  const res = await fetchWithTimeout(`${RESEARCH_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    timeout: timeoutMs,
  });
  if (!res.ok && res.status !== 400) {
    throw new Error(`${path} failed: ${res.status}`);
  }
  return res.json();
}

export async function startDefenderSession(
  thesis: string,
  opts: { domainId?: string; nodeId?: string; entityName?: string } = {},
): Promise<DefenderStartResult> {
  return postJson('/defender/start', {
    thesis,
    domain_id: opts.domainId,
    node_id: opts.nodeId,
    entity_name: opts.entityName,
  });
}

export async function respondToObjection(
  sessionId: string,
  responseText: string,
  objectionIndex: number,
): Promise<DefenderRespondResult> {
  return postJson('/defender/respond', {
    session_id: sessionId,
    response_text: responseText,
    objection_index: objectionIndex,
  });
}

export async function listDefenderSessions(limit = 20): Promise<{ sessions: DefenderSessionSummary[] }> {
  const res = await fetchWithTimeout(
    `${RESEARCH_BASE}/defender/sessions?limit=${limit}`,
    { timeout: 10000 },
  );
  if (!res.ok) throw new Error(`list sessions failed: ${res.status}`);
  return res.json();
}

export interface CurriculumDomainInfo {
  id: string;
  title: string;
  depth?: string;
  node_count?: number;
}

export async function listCurriculumDomains(): Promise<{ curricula: CurriculumDomainInfo[] }> {
  const res = await fetchWithTimeout(
    `${RESEARCH_BASE}/curriculum/list`,
    { timeout: 10000 },
  );
  if (!res.ok) throw new Error(`list curricula failed: ${res.status}`);
  return res.json();
}
