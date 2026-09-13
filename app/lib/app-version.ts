import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants from 'expo-constants';
import * as Updates from 'expo-updates';

const SEEN_UPDATE_KEY = '@petrarca/seen-update-id';

/** Device UI preference only; this is not study or knowledge state. */
export async function detectNewlyAppliedUpdate() {
  if (!Updates.isEnabled || Updates.isEmbeddedLaunch || !Updates.updateId) return null;
  const updateId = Updates.updateId;
  try {
    if (await AsyncStorage.getItem(SEEN_UPDATE_KEY) === updateId) return null;
    await AsyncStorage.setItem(SEEN_UPDATE_KEY, updateId);
    const date = Updates.createdAt?.toLocaleString('nb-NO', {
      day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
    });
    return {
      updateId,
      label: [`v${Constants.expoConfig?.version ?? '1.0.0'}`, date].filter(Boolean).join(' · '),
    };
  } catch {
    return null; // A notice must never prevent the app from opening.
  }
}
