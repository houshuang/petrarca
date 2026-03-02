import { Paths, File, Directory } from 'expo-file-system';

const LOG_DIR_NAME = 'logs';

let sessionId: string | null = null;
let writeQueue: Promise<void> = Promise.resolve();

function generateSessionId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

function getDateString(): string {
  return new Date().toISOString().slice(0, 10);
}

function getLogDir(): Directory {
  return new Directory(Paths.document, LOG_DIR_NAME);
}

function getLogFile(): File {
  return new File(Paths.document, LOG_DIR_NAME, `interactions_${getDateString()}.jsonl`);
}

function ensureLogDir() {
  const dir = getLogDir();
  if (!dir.exists) {
    dir.create({ intermediates: true });
  }
}

export function getSessionId(): string {
  if (!sessionId) {
    sessionId = generateSessionId();
  }
  return sessionId;
}

export function startNewSession(): string {
  sessionId = generateSessionId();
  logEvent('session_start');
  return sessionId;
}

export function logEvent(event: string, data?: Record<string, any>) {
  const entry = {
    ts: new Date().toISOString(),
    event,
    session_id: getSessionId(),
    ...data,
  };

  // Queue writes sequentially to avoid file corruption
  writeQueue = writeQueue.then(async () => {
    try {
      ensureLogDir();
      const file = getLogFile();
      const line = JSON.stringify(entry) + '\n';
      if (file.exists) {
        const existing = await file.text();
        file.write(existing + line);
      } else {
        file.create();
        file.write(line);
      }
    } catch (e) {
      console.warn('[logger] write failed:', e);
    }
  });
}

export async function getLogFiles(): Promise<string[]> {
  try {
    ensureLogDir();
    const dir = getLogDir();
    const entries = dir.list();
    return entries
      .filter((e): e is File => e instanceof File && e.name.endsWith('.jsonl'))
      .map(f => f.name)
      .sort();
  } catch {
    return [];
  }
}

export async function readLogFile(filename: string): Promise<string> {
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
  return getLogDir().uri;
}
