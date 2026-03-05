import AsyncStorage from '@react-native-async-storage/async-storage';
import { UserSignal, ReadingState, ConceptState, VoiceNote, ConceptReview, Highlight, BookReadingState } from './types';

const SIGNALS_KEY = '@petrarca/signals';
const READING_STATES_KEY = '@petrarca/reading_states';
const CONCEPT_STATES_KEY = '@petrarca/concept_states';
const VOICE_NOTES_KEY = '@petrarca/voice_notes';
const CONCEPT_REVIEWS_KEY = '@petrarca/concept_reviews';
const HIGHLIGHTS_KEY = '@petrarca/highlights';
const BOOK_READING_STATES_KEY = '@petrarca/book_reading_states';

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
    // Migrate old 'claims' depth to 'concepts'
    for (const [, state] of entries) {
      if ((state.depth as string) === 'claims') {
        state.depth = 'concepts';
      }
    }
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

export async function loadVoiceNotes(): Promise<VoiceNote[]> {
  try {
    const raw = await AsyncStorage.getItem(VOICE_NOTES_KEY);
    if (!raw) return [];
    return JSON.parse(raw);
  } catch (e) {
    console.warn('[persistence] failed to load voice notes:', e);
    return [];
  }
}

export async function saveVoiceNotes(notes: VoiceNote[]): Promise<void> {
  try {
    await AsyncStorage.setItem(VOICE_NOTES_KEY, JSON.stringify(notes));
  } catch (e) {
    console.warn('[persistence] failed to save voice notes:', e);
  }
}

export async function loadConceptReviews(): Promise<Map<string, ConceptReview>> {
  try {
    const raw = await AsyncStorage.getItem(CONCEPT_REVIEWS_KEY);
    if (!raw) return new Map();
    const entries: [string, ConceptReview][] = JSON.parse(raw);
    return new Map(entries);
  } catch (e) {
    console.warn('[persistence] failed to load concept reviews:', e);
    return new Map();
  }
}

export async function saveConceptReviews(reviews: Map<string, ConceptReview>): Promise<void> {
  try {
    const entries = Array.from(reviews.entries());
    await AsyncStorage.setItem(CONCEPT_REVIEWS_KEY, JSON.stringify(entries));
  } catch (e) {
    console.warn('[persistence] failed to save concept reviews:', e);
  }
}

export async function loadHighlights(): Promise<Highlight[]> {
  try {
    const raw = await AsyncStorage.getItem(HIGHLIGHTS_KEY);
    if (!raw) return [];
    return JSON.parse(raw);
  } catch (e) {
    console.warn('[persistence] failed to load highlights:', e);
    return [];
  }
}

export async function saveHighlights(highlights: Highlight[]): Promise<void> {
  try {
    await AsyncStorage.setItem(HIGHLIGHTS_KEY, JSON.stringify(highlights));
  } catch (e) {
    console.warn('[persistence] failed to save highlights:', e);
  }
}

export async function loadBookReadingStates(): Promise<Map<string, BookReadingState>> {
  try {
    const raw = await AsyncStorage.getItem(BOOK_READING_STATES_KEY);
    if (!raw) return new Map();
    const entries: [string, BookReadingState][] = JSON.parse(raw);
    return new Map(entries);
  } catch (e) {
    console.warn('[persistence] failed to load book reading states:', e);
    return new Map();
  }
}

export async function saveBookReadingStates(states: Map<string, BookReadingState>): Promise<void> {
  try {
    const entries = Array.from(states.entries());
    await AsyncStorage.setItem(BOOK_READING_STATES_KEY, JSON.stringify(entries));
  } catch (e) {
    console.warn('[persistence] failed to save book reading states:', e);
  }
}
