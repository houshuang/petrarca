/**
 * API client for physical book server endpoints.
 * Follows the same FormData upload pattern as chat-api.ts.
 */

import { Platform } from 'react-native';
import { RESEARCH_BASE, fetchWithTimeout } from './chat-api';
import type {
  PhysicalBookChapter, BookResearch, ChapterInsights, StorySoFarBriefing,
} from '../data/types';

// --- Response types ---

export interface BookIdentifyResult {
  title: string;
  author: string;
  cover_url?: string;
  isbn?: string;
  publisher?: string;
  year?: number;
  page_count?: number;
  topics: string[];
  chapters?: PhysicalBookChapter[];
}

export interface TOCParseResult {
  chapters: PhysicalBookChapter[];
}

export interface PageOCRResult {
  text: string;
  detected_page_number?: number;
  extracted_ideas: string[];
  topics: string[];
}

export interface BookVoiceNoteResult {
  id: string;
  transcript: string;
  extracted_ideas: string[];
  topics: string[];
}

export interface PageOCRResultEnhanced extends PageOCRResult {
  key_passage?: string;
  elaborative_question?: string;
}

// --- Helper: create FormData with image ---

async function appendImage(formData: FormData, fieldName: string, imageUri: string): Promise<void> {
  if (Platform.OS === 'web' && (imageUri.startsWith('data:') || imageUri.startsWith('blob:'))) {
    const r = await fetch(imageUri);
    const blob = await r.blob();
    formData.append(fieldName, blob, 'photo.jpg');
  } else {
    // Native: use URI object
    const ext = imageUri.split('.').pop()?.toLowerCase() || 'jpg';
    const mimeType = ext === 'png' ? 'image/png' : 'image/jpeg';
    formData.append(fieldName, {
      uri: imageUri,
      type: mimeType,
      name: `photo.${ext}`,
    } as any);
  }
}

// --- API functions ---

export async function identifyBookCover(
  photoUri: string,
): Promise<BookIdentifyResult> {
  const formData = new FormData();
  await appendImage(formData, 'photo', photoUri);

  const resp = await fetch(`${RESEARCH_BASE}/book/identify`, {
    method: 'POST',
    body: formData,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Book identify failed (${resp.status}): ${text}`);
  }
  return resp.json();
}

export async function ocrTableOfContents(
  photoUri: string,
  bookId: string,
): Promise<TOCParseResult> {
  const formData = new FormData();
  await appendImage(formData, 'photo', photoUri);
  formData.append('book_id', bookId);

  const resp = await fetch(`${RESEARCH_BASE}/book/ocr-toc`, {
    method: 'POST',
    body: formData,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`TOC OCR failed (${resp.status}): ${text}`);
  }
  return resp.json();
}

export async function ocrPage(
  photoUri: string,
  bookId: string,
  bookTitle: string,
  pageNumber?: number,
  chapter?: string,
): Promise<PageOCRResult> {
  const formData = new FormData();
  await appendImage(formData, 'photo', photoUri);
  formData.append('book_id', bookId);
  formData.append('book_title', bookTitle);
  if (pageNumber !== undefined) formData.append('page_number', String(pageNumber));
  if (chapter) formData.append('chapter', chapter);

  const resp = await fetch(`${RESEARCH_BASE}/book/ocr-page`, {
    method: 'POST',
    body: formData,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Page OCR failed (${resp.status}): ${text}`);
  }
  return resp.json();
}

export async function uploadBookVoiceNote(
  audioUri: string,
  bookId: string,
  bookTitle: string,
  chapter?: string,
  pageNumber?: number,
): Promise<BookVoiceNoteResult> {
  const formData = new FormData();
  formData.append('audio', {
    uri: audioUri,
    type: 'audio/m4a',
    name: 'note.m4a',
  } as any);
  formData.append('book_id', bookId);
  formData.append('book_title', bookTitle);
  if (chapter) formData.append('chapter', chapter);
  if (pageNumber !== undefined) formData.append('page_number', String(pageNumber));

  const resp = await fetch(`${RESEARCH_BASE}/book/voice-note`, {
    method: 'POST',
    body: formData,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Book voice note upload failed (${resp.status}): ${text}`);
  }
  return resp.json();
}

// --- Book Research API ---

export async function researchBook(
  bookId: string,
  title: string,
  author: string,
  chapters: PhysicalBookChapter[],
  topics: string[],
  isbn?: string,
): Promise<void> {
  const resp = await fetchWithTimeout(`${RESEARCH_BASE}/book/research`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      book_id: bookId, title, author, isbn,
      chapters: chapters.map(ch => ({ number: ch.number, title: ch.title })),
      topics,
    }),
    timeout: 120000, // research spawns claude -p, can take a while
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Book research failed (${resp.status}): ${text}`);
  }
}

export async function getBookResearch(
  bookId: string,
): Promise<BookResearch | null> {
  const resp = await fetchWithTimeout(`${RESEARCH_BASE}/book/research/${bookId}`, { timeout: 8000 });
  if (resp.status === 404) return null;
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Get book research failed (${resp.status}): ${text}`);
  }
  return resp.json();
}

export async function getChapterInsights(
  bookId: string,
  chapterNumber: number,
  chapterTitle: string,
  captures?: Array<{ text?: string; ocr_text?: string; transcript?: string; chapter?: string }>,
): Promise<ChapterInsights> {
  const resp = await fetch(`${RESEARCH_BASE}/book/chapter-insights`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      book_id: bookId,
      chapter_number: chapterNumber,
      chapter_title: chapterTitle,
      captures: captures || [],
    }),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Chapter insights failed (${resp.status}): ${text}`);
  }
  return resp.json();
}

export async function getStorySoFar(
  bookId: string,
  title: string,
  author: string,
  currentChapter?: string,
  currentPage?: number,
  pageCount?: number,
  captures?: Array<{ text?: string; ocr_text?: string; transcript?: string; chapter?: string; page_number?: number; extracted_ideas?: string[] }>,
): Promise<StorySoFarBriefing> {
  const resp = await fetchWithTimeout(`${RESEARCH_BASE}/book/story-so-far`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      book_id: bookId, title, author,
      current_chapter: currentChapter,
      current_page: currentPage,
      page_count: pageCount,
      captures: captures || [],
    }),
    timeout: 30000,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Story so far failed (${resp.status}): ${text}`);
  }
  return resp.json();
}

// --- Curriculum context for books ---

export interface BookCurriculumMapping {
  node_id: string;
  node_title: string;
  coverage: 'surface' | 'moderate' | 'deep';
  evidence: string;
  knowledge: 'unknown' | 'mentioned' | 'engaged' | 'anchored';
  interest: string;
  confidence: number;
  description: string;
}

export interface CrossBookConnection {
  node_id: string;
  node_title: string;
  other_book_id: string;
  other_book_title: string;
  other_coverage: string;
}

export interface BookCurriculumDomain {
  domain_id: string;
  domain_title: string;
  node_count: number;
  mappings: BookCurriculumMapping[];
  cross_book_connections: CrossBookConnection[];
}

export interface BookCurriculumContext {
  domains: BookCurriculumDomain[];
}

export async function getBookCurriculumContext(
  bookId: string,
): Promise<BookCurriculumContext> {
  const resp = await fetch(`${RESEARCH_BASE}/curriculum/book-context/${bookId}`);
  if (!resp.ok) return { domains: [] };
  return resp.json();
}

// --- Book Sync API (server-authoritative persistence) ---

import type { PhysicalBook, BookCapture } from '../data/types';

export async function syncBooksToServer(
  books: PhysicalBook[],
  captures: BookCapture[],
): Promise<void> {
  try {
    // Strip local-only fields (photo URIs, audio URIs) that won't work on server
    const cleanBooks = books.map(b => ({
      ...b,
      cover_image_uri: undefined, // local file path, not useful on server
    }));
    const cleanCaptures = captures.map(c => ({
      ...c,
      photo_uri: undefined,
      audio_uri: undefined,
    }));

    await fetchWithTimeout(`${RESEARCH_BASE}/book/sync`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ books: cleanBooks, captures: cleanCaptures }),
      timeout: 10000,
    });
  } catch {
    // Sync failure is non-critical — local data is preserved
  }
}

export async function loadBooksFromServer(): Promise<{
  books: PhysicalBook[];
  captures: BookCapture[];
}> {
  const resp = await fetchWithTimeout(`${RESEARCH_BASE}/book/sync`, { timeout: 8000 });
  if (!resp.ok) return { books: [], captures: [] };
  return resp.json();
}

// --- Resurfacing API ---

import type { ResurfacingSession, ReviewStreamResponse } from '../data/types';

export async function generateResurfacingSession(
  includeDialogues: boolean = true,
): Promise<ResurfacingSession> {
  const resp = await fetch(`${RESEARCH_BASE}/book/resurfacing/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ include_dialogues: includeDialogues }),
  });
  if (!resp.ok) throw new Error(`Resurfacing generate failed (${resp.status})`);
  return resp.json();
}

export async function respondToResurfacing(
  captureId: string,
  responseText: string,
  responseType: 'text' | 'voice' = 'text',
): Promise<void> {
  await fetch(`${RESEARCH_BASE}/book/resurfacing/respond`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ capture_id: captureId, response_text: responseText, response_type: responseType }),
  });
}

export async function skipResurfacing(captureId: string): Promise<void> {
  await fetch(`${RESEARCH_BASE}/book/resurfacing/skip`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ capture_id: captureId }),
  });
}

export async function getResurfacingStatus(): Promise<Record<string, unknown>> {
  const resp = await fetch(`${RESEARCH_BASE}/book/resurfacing/status`);
  if (!resp.ok) return {};
  return resp.json();
}

// --- Curriculum Review API ---

export async function fetchReviewStream(
  opts: { domain?: string; limit?: number; offset?: number } = {},
): Promise<ReviewStreamResponse> {
  const resp = await fetch(`${RESEARCH_BASE}/curriculum/review/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      domain: opts.domain,
      limit: opts.limit ?? 20,
      offset: opts.offset ?? 0,
    }),
  });
  if (!resp.ok) throw new Error(`Review stream failed (${resp.status})`);
  return resp.json();
}

export async function recordReviewResult(
  questionId: string,
  result: string,
  responseTimeMs?: number,
): Promise<{ next_due_at?: number; new_stability_days?: number }> {
  const payload: Record<string, unknown> = { question_id: questionId, result };
  if (responseTimeMs != null) payload.response_time_ms = responseTimeMs;
  const resp = await fetch(`${RESEARCH_BASE}/curriculum/review/result`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) throw new Error(`Review result failed (${resp.status})`);
  return resp.json();
}

export async function gradeStructuralCard(
  cardId: string,
  results: Array<{ position_id: string; score: 'knew' | 'missed' }>,
): Promise<{ card_id: string; positions: Array<{ position_id: string; score: string; new_stability_days: number; next_due_at: number }>; knew: number; total: number }> {
  const resp = await fetch(`${RESEARCH_BASE}/structural/grade`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ card_id: cardId, results }),
  });
  if (!resp.ok) throw new Error(`Structural grade failed (${resp.status})`);
  return resp.json();
}

export async function suspendReviewItem(itemId: string): Promise<void> {
  const resp = await fetch(`${RESEARCH_BASE}/curriculum/review/suspend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ item_id: itemId }),
  });
  if (!resp.ok) throw new Error(`Suspend failed (${resp.status})`);
}

// Legacy wrapper for backwards compatibility
export async function generateCurriculumReview(
  domain?: string,
): Promise<ResurfacingSession> {
  const stream = await fetchReviewStream({ domain });
  return {
    id: `cr_${Date.now()}`,
    items: stream.items,
    generated_at: stream.generated_at,
    resonance_count: 0,
    dialogue_count: 0,
    total_questions_in_pool: stream.total_items,
  };
}

// --- Microlearning Research API ---

export async function triggerMicrolearning(opts: {
  query: string;
  sourceItemId?: string;
  sourceNodeId?: string;
  sourceDomain?: string;
}): Promise<{ id: string; status: string; query: string }> {
  const resp = await fetch(`${RESEARCH_BASE}/review/microlearning`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: opts.query,
      source_item_id: opts.sourceItemId,
      source_node_id: opts.sourceNodeId,
      source_domain: opts.sourceDomain,
    }),
  });
  if (!resp.ok) throw new Error(`Microlearning request failed (${resp.status})`);
  return resp.json();
}

export async function dismissMicrolearning(
  opts: { cardId?: string; quizId?: string },
): Promise<{ status: string; card_id?: string; quiz_id?: string }> {
  const resp = await fetch(`${RESEARCH_BASE}/review/microlearning/dismiss`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ card_id: opts.cardId, quiz_id: opts.quizId }),
  });
  if (!resp.ok) throw new Error(`Dismiss failed (${resp.status})`);
  return resp.json();
}

// --- Factual Quiz API ---

export async function createFactualQuiz(itemId: string, question: string, answer: string, factId?: string): Promise<{ quiz_id: string; status: string }> {
  const resp = await fetch(`${RESEARCH_BASE}/review/create-factual-quiz`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ item_id: itemId, question, answer, fact_id: factId }),
  });
  if (!resp.ok) throw new Error(`Create quiz failed (${resp.status})`);
  return resp.json();
}

export async function suspendFact(factId: string): Promise<{ count: number }> {
  const resp = await fetch(`${RESEARCH_BASE}/review/suspend-fact`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ fact_id: factId }),
  });
  if (!resp.ok) throw new Error(`Suspend fact failed (${resp.status})`);
  return resp.json();
}

export async function flagMicrolearningInaccurate(
  cardId: string,
  reason: string = '',
): Promise<{ ok: boolean; card_id: string }> {
  const resp = await fetch(`${RESEARCH_BASE}/review/ml-flag-inaccurate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ card_id: cardId, reason }),
  });
  if (!resp.ok) throw new Error(`Flag inaccurate failed (${resp.status})`);
  return resp.json();
}

// --- Follow-up Query API ---

export async function triggerFollowUp(itemId: string, query: string): Promise<{ triggered: string[] }> {
  const resp = await fetch(`${RESEARCH_BASE}/review/follow-up/trigger`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ item_id: itemId, query }),
  });
  if (!resp.ok) throw new Error(`Follow-up trigger failed (${resp.status})`);
  return resp.json();
}

export async function generateFollowUps(opts: {
  nodeTitle: string;
  nodeDescription?: string;
  factContext?: string;
  exclude?: string[];
}): Promise<{ follow_up_queries: string[] }> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30000);
  try {
    const resp = await fetch(`${RESEARCH_BASE}/review/follow-up/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        node_title: opts.nodeTitle,
        node_description: opts.nodeDescription || '',
        fact_context: opts.factContext || '',
        exclude: opts.exclude || [],
      }),
      signal: controller.signal,
    });
    if (!resp.ok) throw new Error(`Follow-up generate failed (${resp.status})`);
    return resp.json();
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchAlsoWantToKnow(opts: {
  itemId: string;
  question: string;
  entities: Array<{name: string; type?: string; entity_type?: string}>;
}): Promise<{ suggestions: Array<{query: string; type: string; label: string}> }> {
  const resp = await fetch(`${RESEARCH_BASE}/review/also-want-to-know`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      item_id: opts.itemId,
      question: opts.question,
      entities: opts.entities,
    }),
  });
  if (!resp.ok) return { suggestions: [] };
  return resp.json();
}

export async function submitTargetedQuiz(opts: {
  itemId: string;
  query: string;
  type: string;
}): Promise<{ card_id?: string; quiz_id?: string; question?: string; answer?: string }> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30000);
  try {
    const resp = await fetch(`${RESEARCH_BASE}/review/targeted-quiz`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        item_id: opts.itemId,
        query: opts.query,
        type: opts.type,
      }),
      signal: controller.signal,
    });
    if (!resp.ok) throw new Error(`Targeted quiz failed (${resp.status})`);
    return resp.json();
  } finally {
    clearTimeout(timer);
  }
}

// --- Entity API ---

export async function fetchEntityDetails(
  entityId: string,
): Promise<import('../data/types').EntityDetails> {
  const resp = await fetch(`${RESEARCH_BASE}/entity/${entityId}`);
  if (!resp.ok) throw new Error(`Entity fetch failed (${resp.status})`);
  return resp.json();
}

export async function fetchEntityQuestions(
  entityId: string,
  entityName: string,
  entityType?: string,
  description?: string,
): Promise<{ entity_id: string; questions: string[] }> {
  const resp = await fetch(`${RESEARCH_BASE}/entity/questions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      entity_id: entityId,
      entity_name: entityName,
      entity_type: entityType,
      description: description,
    }),
  });
  if (!resp.ok) throw new Error(`Entity questions failed (${resp.status})`);
  return resp.json();
}

export async function triggerEntityResearch(
  entityId: string,
  entityName: string,
  entityType?: string,
  description?: string,
): Promise<{ card_id: string; status: string; entity_id: string }> {
  const resp = await fetch(`${RESEARCH_BASE}/entity/research`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      entity_id: entityId,
      entity_name: entityName,
      entity_type: entityType,
      description: description,
    }),
  });
  if (!resp.ok) throw new Error(`Entity research failed (${resp.status})`);
  return resp.json();
}

export async function recordEntityTap(
  entityId: string,
  action: 'tap' | 'unknown' | 'interested' | 'encountered' = 'tap',
): Promise<{ status: string; prompts_created?: number }> {
  const resp = await fetch(`${RESEARCH_BASE}/entity/tap`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ entity_id: entityId, action }),
  });
  return resp.json();
}

export async function saveEntityNote(
  entityId: string,
  note: string,
): Promise<{ status: string; entity_id: string; created_at: number }> {
  const resp = await fetch(`${RESEARCH_BASE}/entity/notes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ entity_id: entityId, note }),
  });
  if (!resp.ok) throw new Error(`Save note failed (${resp.status})`);
  return resp.json();
}

// --- Kindle Processing API ---

export async function processKindleBooks(max: number = 10): Promise<void> {
  await fetch(`${RESEARCH_BASE}/book/process-kindle`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ max }),
  });
}

export interface KindleRecentBook {
  key: string;
  title: string;
  author: string;
  cover_url: string;
  progress_pct: number;
  status: string;
  category: string | null;
  last_seen: string;
  first_seen: string;
}

export async function fetchKindleRecentlyStarted(): Promise<KindleRecentBook[]> {
  const resp = await fetchWithTimeout(`${RESEARCH_BASE}/kindle/recently-started`);
  if (!resp.ok) return [];
  const data = await resp.json();
  return data.books || [];
}

export async function dismissKindleBook(key: string): Promise<void> {
  await fetch(`${RESEARCH_BASE}/kindle/curate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ updates: [{ key, status: 'skipped' }] }),
  });
}

export async function includeKindleBook(key: string): Promise<{
  book: PhysicalBook;
  captures: BookCapture[];
  already_existed: boolean;
}> {
  const resp = await fetch(`${RESEARCH_BASE}/kindle/include`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key }),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Kindle include failed (${resp.status}): ${text}`);
  }
  return resp.json();
}
