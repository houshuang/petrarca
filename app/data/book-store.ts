/**
 * Physical book state management — module-level vars + AsyncStorage persistence.
 * Follows the same pattern as store.ts: module-level arrays, exported accessors,
 * async persistence functions.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { PhysicalBook, BookCapture } from './types';
import { logEvent } from './logger';
import { syncBooksToServer, loadBooksFromServer } from '../lib/book-api';

const BOOKS_KEY = '@petrarca/physical_books';
const CAPTURES_KEY = '@petrarca/book_captures';
const PENDING_UPLOADS_KEY = '@petrarca/pending_book_uploads';

// --- Module-level state ---

let books: PhysicalBook[] = [];
let captures: BookCapture[] = [];
let bookStoreVersion = 0;

// --- Change listeners (for background updates) ---

type BookStoreListener = () => void;
const listeners: Set<BookStoreListener> = new Set();

export function onBookStoreChange(fn: BookStoreListener): () => void {
  listeners.add(fn);
  return () => { listeners.delete(fn); };
}

function notifyListeners() {
  for (const fn of listeners) {
    try { fn(); } catch { /* ignore */ }
  }
}

// --- Initialization ---

export async function initBookStore(): Promise<void> {
  try {
    // Load local first (fast)
    const [booksRaw, capturesRaw] = await Promise.all([
      AsyncStorage.getItem(BOOKS_KEY),
      AsyncStorage.getItem(CAPTURES_KEY),
    ]);
    if (booksRaw) books = JSON.parse(booksRaw);
    if (capturesRaw) captures = JSON.parse(capturesRaw);

    // Network reconciliation must never hold the native splash screen open.
    void refreshBooksFromServer();

    logEvent('book_store_loaded', {
      books: books.length,
      captures: captures.length,
    });
  } catch (e) {
    logEvent('warning', { message: '[book-store] failed to load', error: String(e) });
  }
}

async function refreshBooksFromServer(): Promise<void> {
  try {
    const serverData = await loadBooksFromServer();
    if (serverData.books.length > 0 || serverData.captures.length > 0) {
      // Merge: server data wins for same ID, local-only items are kept
      const serverBookIds = new Set(serverData.books.map((b: PhysicalBook) => b.id));
      const serverCapIds = new Set(serverData.captures.map((c: BookCapture) => c.id));

      // Keep local-only books (not on server yet), add all server books
      const localOnlyBooks = books.filter(b => !serverBookIds.has(b.id));
      books = [...serverData.books, ...localOnlyBooks];

      const localOnlyCaptures = captures.filter(c => !serverCapIds.has(c.id));
      captures = [...serverData.captures, ...localOnlyCaptures];

      bookStoreVersion++;
      notifyListeners();

      // Save merged result locally
      await Promise.all([saveBooks(), saveCaptures()]);

      // If we had local-only items, push them to server too
      if (localOnlyBooks.length > 0 || localOnlyCaptures.length > 0) {
        syncBooksToServer(books, captures);
      }
    }
  } catch {
    // Server unavailable — local data is fine
  }
}

// --- Book accessors ---

export function getPhysicalBooks(): PhysicalBook[] {
  return [...books].sort((a, b) => b.last_interaction_at - a.last_interaction_at);
}

export function getPhysicalBook(id: string): PhysicalBook | undefined {
  return books.find(b => b.id === id);
}

export function getBookStoreVersion(): number {
  return bookStoreVersion;
}

// --- Book mutations ---

export async function addPhysicalBook(book: PhysicalBook): Promise<void> {
  books.push(book);
  bookStoreVersion++;
  notifyListeners();
  await saveBooks();
  syncToServer();
  logEvent('book_added', { book_id: book.id, title: book.title });
}

export async function updatePhysicalBook(
  id: string,
  updates: Partial<PhysicalBook>,
): Promise<void> {
  const idx = books.findIndex(b => b.id === id);
  if (idx === -1) return;
  books[idx] = { ...books[idx], ...updates, last_interaction_at: Date.now() };
  bookStoreVersion++;
  notifyListeners();
  await saveBooks();
  syncToServer();
}

export async function updateReadingPosition(
  bookId: string,
  page?: number,
  chapter?: string,
): Promise<void> {
  const updates: Partial<PhysicalBook> = {};
  if (page !== undefined) updates.current_page = page;
  if (chapter !== undefined) updates.current_chapter = chapter;
  await updatePhysicalBook(bookId, updates);
  logEvent('book_position_updated', { book_id: bookId, page, chapter });
}

export async function archiveBook(bookId: string): Promise<void> {
  await updatePhysicalBook(bookId, { reading_status: 'archived' });
  logEvent('book_archived', { book_id: bookId });
}

export async function deletePhysicalBook(id: string): Promise<void> {
  books = books.filter(b => b.id !== id);
  captures = captures.filter(c => c.book_id !== id);
  bookStoreVersion++;
  notifyListeners();
  await Promise.all([saveBooks(), saveCaptures()]);
  syncToServer();
  logEvent('book_deleted', { book_id: id });
}

// --- Capture accessors ---

export function getBookCaptures(bookId: string): BookCapture[] {
  return captures
    .filter(c => c.book_id === bookId)
    .sort((a, b) => b.created_at - a.created_at);
}

export function getAllCaptures(): BookCapture[] {
  return [...captures].sort((a, b) => b.created_at - a.created_at);
}

// --- Capture mutations ---

export async function addBookCapture(capture: BookCapture): Promise<void> {
  captures.push(capture);
  // Touch the book's last_interaction_at
  const bookIdx = books.findIndex(b => b.id === capture.book_id);
  if (bookIdx !== -1) {
    books[bookIdx].last_interaction_at = Date.now();
  }
  bookStoreVersion++;
  notifyListeners();
  await Promise.all([saveCaptures(), saveBooks()]);
  syncToServer();
  logEvent('book_capture_added', {
    book_id: capture.book_id,
    type: capture.type,
    capture_id: capture.id,
  });
}

export async function updateBookCapture(
  id: string,
  updates: Partial<BookCapture>,
): Promise<void> {
  const idx = captures.findIndex(c => c.id === id);
  if (idx === -1) return;
  captures[idx] = { ...captures[idx], ...updates };
  bookStoreVersion++;
  notifyListeners();
  await saveCaptures();
  syncToServer();
}

// --- Pending uploads (offline retry queue) ---

interface PendingBookUpload {
  capture_id: string;
  book_id: string;
  type: BookCapture['type'];
  local_path: string;
  created_at: number;
  retry_count: number;
}

export async function getPendingUploads(): Promise<PendingBookUpload[]> {
  try {
    const raw = await AsyncStorage.getItem(PENDING_UPLOADS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export async function addPendingUpload(upload: PendingBookUpload): Promise<void> {
  const pending = await getPendingUploads();
  pending.push(upload);
  await AsyncStorage.setItem(PENDING_UPLOADS_KEY, JSON.stringify(pending));
}

export async function removePendingUpload(captureId: string): Promise<void> {
  const pending = await getPendingUploads();
  const filtered = pending.filter(p => p.capture_id !== captureId);
  await AsyncStorage.setItem(PENDING_UPLOADS_KEY, JSON.stringify(filtered));
}

// --- ID generation ---

export function generateBookId(): string {
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 6);
  return `pb_${ts}_${rand}`;
}

export function generateCaptureId(): string {
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 6);
  return `cap_${ts}_${rand}`;
}

// --- Persistence helpers ---

async function saveBooks(): Promise<void> {
  try {
    await AsyncStorage.setItem(BOOKS_KEY, JSON.stringify(books));
  } catch (e) {
    logEvent('warning', { message: '[book-store] failed to save books', error: String(e) });
  }
}

async function saveCaptures(): Promise<void> {
  try {
    await AsyncStorage.setItem(CAPTURES_KEY, JSON.stringify(captures));
  } catch (e) {
    logEvent('warning', { message: '[book-store] failed to save captures', error: String(e) });
  }
}

/** Push current state to server. Called after every mutation for cross-device sync. */
async function syncToServer(): Promise<void> {
  syncBooksToServer(books, captures);
}
