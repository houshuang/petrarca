import AsyncStorage from '@react-native-async-storage/async-storage';
import { UserSignal } from './types';

const SIGNALS_KEY = '@petrarca/signals';

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
