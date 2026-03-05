import { Platform } from 'react-native';

const LOG_DIR_NAME = 'logs';
const LOG_STORAGE_PREFIX = '@petrarca/log_';

let sessionId: string | null = null;
let writeQueue: Promise<void> = Promise.resolve();

// Buffer for batched native writes — avoids O(n²) read-append-write per event
let nativeBuffer: string[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;
const FLUSH_INTERVAL_MS = 2000;

// Lazy-load expo-file-system only on native
let NativeFS: any = null;
function getNativeFS() {
  if (!NativeFS && Platform.OS !== 'web') {
    NativeFS = require('expo-file-system');
  }
  return NativeFS;
}

function generateSessionId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

function getDateString(): string {
  return new Date().toISOString().slice(0, 10);
}

// --- Web implementation using localStorage ---

function webLogKey(date: string): string {
  return `${LOG_STORAGE_PREFIX}${date}`;
}

function webAppendLog(line: string) {
  const key = webLogKey(getDateString());
  const existing = localStorage.getItem(key) || '';
  localStorage.setItem(key, existing + line);
}

function webGetLogFiles(): string[] {
  const files: string[] = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key?.startsWith(LOG_STORAGE_PREFIX)) {
      files.push(`interactions_${key.slice(LOG_STORAGE_PREFIX.length)}.jsonl`);
    }
  }
  return files.sort();
}

function webReadLogFile(filename: string): string {
  const date = filename.replace('interactions_', '').replace('.jsonl', '');
  return localStorage.getItem(webLogKey(date)) || '';
}

// --- Native implementation using expo-file-system ---

function getLogDir() {
  const { Paths, Directory } = getNativeFS();
  return new Directory(Paths.document, LOG_DIR_NAME);
}

function getLogFile() {
  const { Paths, File } = getNativeFS();
  return new File(Paths.document, LOG_DIR_NAME, `interactions_${getDateString()}.jsonl`);
}

function ensureLogDir() {
  const dir = getLogDir();
  if (!dir.exists) {
    dir.create({ intermediates: true });
  }
}

// --- Public API ---

export function getSessionId(): string {
  if (!sessionId) {
    sessionId = generateSessionId();
  }
  return sessionId;
}

export function startNewSession(): string {
  sessionId = generateSessionId();
  logEvent('session_start');
  flushNativeBuffer();
  return sessionId;
}

function flushNativeBuffer() {
  if (nativeBuffer.length === 0) return;
  const lines = nativeBuffer.join('');
  nativeBuffer = [];

  writeQueue = writeQueue.then(async () => {
    try {
      ensureLogDir();
      const file = getLogFile();
      if (file.exists) {
        const existing = await file.text();
        file.write(existing + lines);
      } else {
        file.create();
        file.write(lines);
      }
    } catch (e) {
      console.warn('[logger] write failed:', e);
    }
  });
}

export function logEvent(event: string, data?: Record<string, any>) {
  const entry = {
    ts: new Date().toISOString(),
    event,
    session_id: getSessionId(),
    ...data,
  };

  const line = JSON.stringify(entry) + '\n';

  if (Platform.OS === 'web') {
    webAppendLog(line);
  } else {
    nativeBuffer.push(line);
    if (flushTimer) clearTimeout(flushTimer);
    flushTimer = setTimeout(flushNativeBuffer, FLUSH_INTERVAL_MS);
  }
}

export async function getLogFiles(): Promise<string[]> {
  try {
    if (Platform.OS === 'web') {
      return webGetLogFiles();
    }
    ensureLogDir();
    const dir = getLogDir();
    const { File } = getNativeFS();
    const entries = dir.list();
    return entries
      .filter((e: any): e is typeof File => e instanceof File && e.name.endsWith('.jsonl'))
      .map((f: any) => f.name)
      .sort();
  } catch {
    return [];
  }
}

export async function readLogFile(filename: string): Promise<string> {
  if (Platform.OS === 'web') {
    return webReadLogFile(filename);
  }
  const { Paths, File } = getNativeFS();
  const file = new File(Paths.document, LOG_DIR_NAME, filename);
  if (!file.exists) return '';
  return file.text();
}

export async function exportAllLogs(): Promise<string> {
  const files = await getLogFiles();
  const parts: string[] = [];
  for (const f of files) {
    parts.push(await readLogFile(f));
  }
  return parts.join('');
}

export function getLogDirectory(): string {
  if (Platform.OS === 'web') {
    return 'localStorage';
  }
  return getLogDir().uri;
}
