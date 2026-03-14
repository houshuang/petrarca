import AsyncStorage from '@react-native-async-storage/async-storage';
import { UserSignal, ReadingState, Highlight } from './types';
import { logEvent } from './logger';

const SIGNALS_KEY = '@petrarca/signals';
const READING_STATES_KEY = '@petrarca/reading_states';
const HIGHLIGHTS_KEY = '@petrarca/highlights';

export async function loadSignals(): Promise<UserSignal[]> {
  try {
    const raw = await AsyncStorage.getItem(SIGNALS_KEY);
    if (!raw) return [];
    return JSON.parse(raw);
  } catch (e) {
    logEvent('warning', { message: '[persistence] failed to load signals', error: String(e) });
    return [];
  }
}

export async function saveSignals(signals: UserSignal[]): Promise<void> {
  try {
    await AsyncStorage.setItem(SIGNALS_KEY, JSON.stringify(signals));
  } catch (e) {
    logEvent('warning', { message: '[persistence] failed to save signals', error: String(e) });
  }
}

export async function loadReadingStates(): Promise<Map<string, ReadingState>> {
  try {
    const raw = await AsyncStorage.getItem(READING_STATES_KEY);
    if (!raw) return new Map();
    const entries: [string, ReadingState][] = JSON.parse(raw);
    // Migrate old depth-based states to status-based
    for (const [, state] of entries) {
      if (!state.status) {
        if (state.completed_at) {
          state.status = 'read';
        } else if (state.depth && state.depth !== 'unread') {
          state.status = 'reading';
        } else {
          state.status = 'unread';
        }
      }
    }
    return new Map(entries);
  } catch (e) {
    logEvent('warning', { message: '[persistence] failed to load reading states', error: String(e) });
    return new Map();
  }
}

export async function saveReadingStates(states: Map<string, ReadingState>): Promise<void> {
  try {
    const entries = Array.from(states.entries());
    await AsyncStorage.setItem(READING_STATES_KEY, JSON.stringify(entries));
  } catch (e) {
    logEvent('warning', { message: '[persistence] failed to save reading states', error: String(e) });
  }
}

export async function loadHighlights(): Promise<Highlight[]> {
  try {
    const raw = await AsyncStorage.getItem(HIGHLIGHTS_KEY);
    if (!raw) return [];
    return JSON.parse(raw);
  } catch (e) {
    logEvent('warning', { message: '[persistence] failed to load highlights', error: String(e) });
    return [];
  }
}

export async function saveHighlights(highlights: Highlight[]): Promise<void> {
  try {
    await AsyncStorage.setItem(HIGHLIGHTS_KEY, JSON.stringify(highlights));
  } catch (e) {
    logEvent('warning', { message: '[persistence] failed to save highlights', error: String(e) });
  }
}
