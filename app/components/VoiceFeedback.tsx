import { useState, useRef, useEffect } from 'react';
import { View, Text, Pressable, StyleSheet, Platform } from 'react-native';
import { Audio } from 'expo-av';
import { documentDirectory, makeDirectoryAsync, copyAsync, getInfoAsync } from 'expo-file-system/legacy';
import { colors, fonts } from '../design/tokens';
import { uploadVoiceNote } from '../lib/chat-api';
import { logEvent } from '../data/logger';
import * as Haptics from 'expo-haptics';
import AsyncStorage from '@react-native-async-storage/async-storage';

const PENDING_NOTES_KEY = '@petrarca/pending_voice_notes';

interface PendingNote {
  localPath: string;
  articleId: string;
  articleTitle: string;
  topics: string[];
  articleContext: string;
  recordedAt: number;
}

async function savePendingNote(note: PendingNote): Promise<void> {
  try {
    const raw = await AsyncStorage.getItem(PENDING_NOTES_KEY);
    const pending: PendingNote[] = raw ? JSON.parse(raw) : [];
    pending.push(note);
    await AsyncStorage.setItem(PENDING_NOTES_KEY, JSON.stringify(pending));
  } catch (e) {
    console.warn('[VoiceFeedback] failed to save pending note:', e);
  }
}

async function removePendingNote(localPath: string): Promise<void> {
  try {
    const raw = await AsyncStorage.getItem(PENDING_NOTES_KEY);
    if (!raw) return;
    const pending: PendingNote[] = JSON.parse(raw);
    const filtered = pending.filter(n => n.localPath !== localPath);
    await AsyncStorage.setItem(PENDING_NOTES_KEY, JSON.stringify(filtered));
  } catch (e) {
    console.warn('[VoiceFeedback] failed to remove pending note:', e);
  }
}

async function tryUploadPending(): Promise<void> {
  try {
    const raw = await AsyncStorage.getItem(PENDING_NOTES_KEY);
    if (!raw) return;
    const pending: PendingNote[] = JSON.parse(raw);
    for (const note of pending) {
      try {
        const info = await getInfoAsync(note.localPath);
        if (!info.exists) {
          await removePendingNote(note.localPath);
          continue;
        }
        await uploadVoiceNote(note.localPath, note.articleId, note.articleTitle, note.topics, note.articleContext);
        await removePendingNote(note.localPath);
        logEvent('voice_note_retry_success', { article_id: note.articleId });
      } catch {
        // Will retry next time
      }
    }
  } catch (e) {
    console.warn('[VoiceFeedback] retry upload error:', e);
  }
}

// Retry pending uploads on mount
let retryScheduled = false;
function scheduleRetry() {
  if (retryScheduled) return;
  retryScheduled = true;
  setTimeout(() => {
    tryUploadPending().finally(() => { retryScheduled = false; });
  }, 5000);
}

interface VoiceFeedbackProps {
  articleId: string;
  articleTitle: string;
  topics: string[];
  articleContext: string;
  onClose: () => void;
}

export default function VoiceFeedback({ articleId, articleTitle, topics, articleContext, onClose }: VoiceFeedbackProps) {
  const [recording, setRecording] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');
  const [duration, setDuration] = useState(0);
  const recRef = useRef<Audio.Recording | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Try uploading any pending notes on mount
  useEffect(() => { scheduleRetry(); }, []);

  const startRecording = async () => {
    try {
      const permission = await Audio.requestPermissionsAsync();
      if (!permission.granted) { setError('Mic permission needed'); return; }
      await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });
      const { recording: rec } = await Audio.Recording.createAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
      recRef.current = rec;
      setRecording(true);
      setDuration(0);
      timerRef.current = setInterval(() => setDuration(d => d + 1), 1000);
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      logEvent('voice_note_start', { article_id: articleId });
    } catch (e) {
      setError(`Recording failed: ${e}`);
    }
  };

  const stopAndSend = async () => {
    if (!recRef.current) return;
    if (timerRef.current) clearInterval(timerRef.current);
    try {
      await recRef.current.stopAndUnloadAsync();
      const uri = recRef.current.getURI();
      recRef.current = null;
      setRecording(false);
      if (!uri) { setError('No audio file'); return; }

      // Save locally first for reliability
      let localPath = uri;
      if (Platform.OS !== 'web' && documentDirectory) {
        const filename = `voice_${articleId}_${Date.now()}.m4a`;
        localPath = `${documentDirectory}voice-notes/${filename}`;
        await makeDirectoryAsync(`${documentDirectory}voice-notes/`, { intermediates: true });
        await copyAsync({ from: uri, to: localPath });
      }

      // Mark as sent immediately — recording is safely stored locally
      setSent(true);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      logEvent('voice_note_saved', { article_id: articleId, duration_seconds: duration, local_path: localPath });

      // Upload in background — if it fails, we have a local copy + retry queue
      uploadVoiceNote(localPath, articleId, articleTitle, topics, articleContext)
        .then(() => {
          logEvent('voice_note_uploaded', { article_id: articleId });
        })
        .catch(async (e) => {
          console.warn('[VoiceFeedback] upload failed, queued for retry:', e);
          await savePendingNote({
            localPath,
            articleId,
            articleTitle,
            topics,
            articleContext,
            recordedAt: Date.now(),
          });
          logEvent('voice_note_upload_failed', { article_id: articleId, error: String(e) });
        });

      // Auto-close after brief confirmation
      setTimeout(onClose, 1200);
    } catch (e) {
      setRecording(false);
      setError(`Recording error: ${e}`);
    }
  };

  const fmt = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`;

  if (sent) {
    return (
      <View style={styles.bar}>
        <Text style={styles.sentText}>✓ Saved — uploading in background</Text>
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.bar}>
        <Text style={styles.errorText}>{error}</Text>
        <Pressable onPress={onClose}><Text style={styles.dismiss}>Dismiss</Text></Pressable>
      </View>
    );
  }

  return (
    <View style={styles.bar}>
      {!recording ? (
        <Pressable onPress={startRecording} style={styles.recordBtn}>
          <View style={styles.recordDot} />
          <Text style={styles.btnText}>Record note</Text>
        </Pressable>
      ) : (
        <>
          <View style={styles.recordingRow}>
            <View style={styles.pulseDot} />
            <Text style={styles.timer}>{fmt(duration)}</Text>
          </View>
          <Pressable onPress={stopAndSend} style={styles.sendBtn}>
            <Text style={styles.sendText}>Send</Text>
          </Pressable>
        </>
      )}
      <Pressable onPress={onClose} style={styles.cancelBtn}>
        <Text style={styles.cancelText}>✕</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.parchment,
    borderTopWidth: 1,
    borderTopColor: colors.rule,
    paddingHorizontal: 16,
    paddingVertical: 12,
    gap: 12,
  },
  recordBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: colors.ink,
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 20,
  },
  recordDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.rubric,
  },
  btnText: {
    fontFamily: fonts.uiMedium,
    fontSize: 14,
    color: colors.parchment,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  recordingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flex: 1,
  },
  pulseDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: colors.rubric,
  },
  timer: {
    fontFamily: fonts.display,
    fontSize: 22,
    color: colors.ink,
  },
  sendBtn: {
    backgroundColor: colors.rubric,
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 20,
  },
  sendText: {
    fontFamily: fonts.uiMedium,
    fontSize: 14,
    color: colors.parchment,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  cancelBtn: {
    padding: 8,
    minWidth: 44,
    minHeight: 44,
    justifyContent: 'center',
    alignItems: 'center',
  },
  cancelText: {
    fontSize: 18,
    color: colors.textMuted,
  },
  sentText: {
    fontFamily: fonts.ui,
    fontSize: 14,
    color: colors.claimNew,
    flex: 1,
  },
  errorText: {
    fontFamily: fonts.ui,
    fontSize: 14,
    color: colors.rubric,
    flex: 1,
  },
  dismiss: {
    fontFamily: fonts.ui,
    fontSize: 14,
    color: colors.textMuted,
  },
});
