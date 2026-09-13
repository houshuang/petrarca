/** Durable study events. Server receipt and client occurrence times are separate. */
import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants from 'expo-constants';
import * as Updates from 'expo-updates';
import * as FileSystem from 'expo-file-system/legacy';
import { Platform } from 'react-native';
import { logEvent } from '../data/logger';
import { getResearchServerUrl } from './server-urls';
import type { AspectCardData } from '../components/AspectCard';
import type { SequenceCardData } from '../components/SequenceCard';
import type { SynchronicCardData } from '../components/SynchronicCard';
import type { CausalChainCardData } from '../components/CausalChainCard';

export type Grade = { position_id: string; score: 'knew' | 'missed'; reveal_time_ms: number };
export type CaptureKind = 'recall' | 'wondering' | 'correction' | 'reflection';
type BaseItem = {
  id: string; title: string; version: string; needs_introduction: boolean; introduction?: string;
  topic?: string; cue_type?: string; evidence_note?: string;
  intended_depth: string; sources: { recording: string; segment?: string; start_ms?: number; tana_link: string }[];
  references: { title: string; url: string }[];
};
export type StudyItem = BaseItem & (
  | ({ kind: 'aspect' } & AspectCardData)
  | ({ kind: 'sequence' } & SequenceCardData)
  | ({ kind: 'synchronic' } & SynchronicCardData)
  | ({ kind: 'causal' } & CausalChainCardData)
  | { kind: 'term' | 'voice' | 'prompt'; positions: {position_id: string; question_text: string; answer_text: string}[] }
);
export type PracticeMode = 'scheduled' | 'extra';
export type StudyRun = { practice?: PracticeMode; topic?: string; topics?: {id:string;label:string}[];
  availability?: {due:number;new:number;total:number;next_due_at:number|null;waiting_for_foundation:number}; run_id: string; items: StudyItem[]; completed_ids: string[]; audio_item_ids: string[]; experiment: {id: string; design_version: string} };
export type StudyStatus = { active: boolean; title?: string; items?: number };
type Event = { request_id: string; run_id: string; item_id: string; event: string; client_time: number;
  detail: Record<string, unknown>; client_context: ReturnType<typeof clientContext>; results?: Grade[] };
export type PendingAudio = { id: string; run: string; item: string; uri: string; kind: CaptureKind; mime: string };
const EVENTS = '@petrarca/study/events-v1';
const AUDIO = '@petrarca/study/audio-v1';
let serial: Promise<unknown> = Promise.resolve();
function locked<T>(work: () => Promise<T>): Promise<T> {
  const next = serial.catch(() => undefined).then(work); serial = next; return next;
}
export function requestId(): string { return `st_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 12)}`; }
export function clientContext() {
  return { app_version: Constants.expoConfig?.version, update_id: Updates.updateId,
    runtime_version: Updates.runtimeVersion, platform: Platform.OS, client_schema: 'study-events-v1' };
}
export async function studyRequest<T>(path: string, body?: unknown): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch(`${getResearchServerUrl()}/study/${path}`, {
      method: body === undefined ? 'GET' : 'POST', signal: controller.signal,
      headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok) throw new Error(`Kunne ikke lagre (${response.status}). Prøv igjen.`);
    return await response.json() as T;
  } finally { clearTimeout(timer); }
}
let networkSerial: Promise<unknown> = Promise.resolve();
async function drain() {
  while (true) {
    const first = await locked(async () => (JSON.parse(await AsyncStorage.getItem(EVENTS) || '[]') as Event[])[0]);
    if (!first) return;
    await studyRequest('event', first);
    await locked(async () => {
      const queue: Event[] = JSON.parse(await AsyncStorage.getItem(EVENTS) || '[]');
      await AsyncStorage.setItem(EVENTS, JSON.stringify(queue.filter(e => e.request_id !== first.request_id)));
    });
  }
}
export function flushStudyEvents() {
  const next = networkSerial.catch(() => undefined).then(drain); networkSerial = next; return next;
}
export function studyEvent(run: string, item: string, event: string, detail: Record<string, unknown> = {}, results?: Grade[]) {
  logEvent(`study_${event}`, { run_id: run, item_id: item, ...detail });
  const occurrenceTime = Date.now();
  const context = clientContext();
  return locked(async () => {
    const queue: Event[] = JSON.parse(await AsyncStorage.getItem(EVENTS) || '[]');
    // Retrying a terminal action reuses its entire original payload, including time.
    const id = ['complete','introduced','skip'].includes(event) ? `${run}_${item}_${event}` : requestId();
    if (!queue.some(e => e.request_id === id)) {
      queue.push({request_id: id, run_id: run, item_id: item, event, detail, results,
        client_time: occurrenceTime, client_context: context});
      await AsyncStorage.setItem(EVENTS, JSON.stringify(queue));
    }
  }).then(flushStudyEvents);
}
export async function loadStudyRun(mode: string, fresh = false, practice: PracticeMode = 'scheduled', topic = 'all'): Promise<StudyRun> {
  await flushStudyEvents();
  const key = `@petrarca/study/run-v2-${mode}-${practice}-${topic}`;
  let id = fresh ? null : await AsyncStorage.getItem(key);
  if (!id) { id = requestId(); await AsyncStorage.setItem(key, id); }
  return studyRequest('session', { request_id: id, mode, practice, topic, client_context: clientContext() });
}
export async function pendingAudio(): Promise<PendingAudio[]> { return JSON.parse(await AsyncStorage.getItem(AUDIO) || '[]'); }
export async function preserveAudio(run: string, item: string, uri: string, kind: CaptureKind): Promise<PendingAudio> {
  const id = requestId();
  const entry: PendingAudio = {id, run, item, uri, kind, mime: Platform.OS === 'web' ? 'audio/webm' : 'audio/mp4'};
  await locked(async () => {
    const all = await pendingAudio(); all.push(entry); await AsyncStorage.setItem(AUDIO, JSON.stringify(all));
  });
  if (Platform.OS !== 'web') {
    try {
      const directory = `${FileSystem.documentDirectory}study-audio/`;
      await FileSystem.makeDirectoryAsync(directory, { intermediates: true });
      const saved = `${directory}${id}.m4a`;
      await FileSystem.copyAsync({from: uri, to: saved}); entry.uri = saved;
      await locked(async () => {
        const all = await pendingAudio(); await AsyncStorage.setItem(AUDIO, JSON.stringify(all.map(a => a.id===id ? entry : a)));
      });
    } catch { /* Original recording URI remains indexed for retry. */ }
  }
  return entry;
}
export async function uploadAudio(entry: PendingAudio): Promise<void> {
  const url = `${getResearchServerUrl()}/study/voice?run=${encodeURIComponent(entry.run)}&item=${encodeURIComponent(entry.item)}&kind=${entry.kind}`;
  let status: number;
  if (Platform.OS === 'web') {
    const blob = await (await fetch(entry.uri)).blob();
    status = (await fetch(url, {method: 'POST', headers: {'Content-Type': entry.mime}, body: blob})).status;
  } else {
    status = (await FileSystem.uploadAsync(url, entry.uri, {httpMethod: 'POST',
      uploadType: FileSystem.FileSystemUploadType.BINARY_CONTENT, headers: {'Content-Type': entry.mime}})).status;
  }
  if (status !== 200) throw new Error('Opptaket er bevart på telefonen. Prøv opplasting igjen.');
  await studyEvent(entry.run, entry.item, 'audio_uploaded', { audio_local_id: entry.id, response_kind: entry.kind });
  await locked(async () => {
    const all = await pendingAudio(); await AsyncStorage.setItem(AUDIO, JSON.stringify(all.filter(a => a.id !== entry.id)));
  });
  if (Platform.OS !== 'web') await FileSystem.deleteAsync(entry.uri, {idempotent: true}).catch(() => undefined);
}
