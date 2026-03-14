/**
 * API client for physical book server endpoints.
 * Follows the same FormData upload pattern as chat-api.ts.
 */

import { Platform } from 'react-native';
import { RESEARCH_BASE } from './chat-api';
import type { PhysicalBookChapter } from '../data/types';

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

// --- Helper: create FormData with image ---

function appendImage(formData: FormData, fieldName: string, imageUri: string): void {
  if (Platform.OS === 'web' && imageUri.startsWith('data:')) {
    // Web: convert data URI to blob
    fetch(imageUri)
      .then(r => r.blob())
      .then(blob => formData.append(fieldName, blob, 'photo.jpg'));
  } else if (Platform.OS === 'web' && imageUri.startsWith('blob:')) {
    fetch(imageUri)
      .then(r => r.blob())
      .then(blob => formData.append(fieldName, blob, 'photo.jpg'));
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
  appendImage(formData, 'photo', photoUri);

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
  appendImage(formData, 'photo', photoUri);
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
  appendImage(formData, 'photo', photoUri);
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
