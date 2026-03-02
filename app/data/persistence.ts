import AsyncStorage from '@react-native-async-storage/async-storage';
import { UserSignal, ReadingState, ConceptState } from './types';

const SIGNALS_KEY = '@petrarca/signals';
const READING_STATES_KEY = '@petrarca/reading_states';
const CONCEPT_STATES_KEY = '@petrarca/concept_states';

export async function loadSignals(): Promise<UserSignal[]> {
  try {
    const raw = await AsyncStorage.getItem(SIGNALS_KEY);
    if (!raw) return [];
    return JSON.parse(raw);
  } catch (e) {
    console.warn('[persistence] failed to load signals:', e);
    return [];
  }
}

export async function saveSignals(signals: UserSignal[]): Promise<void> {
  try {
    await AsyncStorage.setItem(SIGNALS_KEY, JSON.stringify(signals));
  } catch (e) {
    console.warn('[persistence] failed to save signals:', e);
  }
}

export async function loadReadingStates(): Promise<Map<string, ReadingState>> {
  try {
    const raw = await AsyncStorage.getItem(READING_STATES_KEY);
    if (!raw) return new Map();
    const entries: [string, ReadingState][] = JSON.parse(raw);
    return new Map(entries);
  } catch (e) {
    console.warn('[persistence] failed to load reading states:', e);
    return new Map();
  }
}

export async function saveReadingStates(states: Map<string, ReadingState>): Promise<void> {
  try {
    const entries = Array.from(states.entries());
    await AsyncStorage.setItem(READING_STATES_KEY, JSON.stringify(entries));
  } catch (e) {
    console.warn('[persistence] failed to save reading states:', e);
  }
}

export async function loadConceptStates(): Promise<Map<string, ConceptState>> {
  try {
    const raw = await AsyncStorage.getItem(CONCEPT_STATES_KEY);
    if (!raw) return new Map();
    const entries: [string, ConceptState][] = JSON.parse(raw);
    return new Map(entries);
  } catch (e) {
    console.warn('[persistence] failed to load concept states:', e);
    return new Map();
  }
}

export async function saveConceptStates(states: Map<string, ConceptState>): Promise<void> {
  try {
    const entries = Array.from(states.entries());
    await AsyncStorage.setItem(CONCEPT_STATES_KEY, JSON.stringify(entries));
  } catch (e) {
    console.warn('[persistence] failed to save concept states:', e);
  }
}
