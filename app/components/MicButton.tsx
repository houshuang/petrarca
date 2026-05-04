import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { colors, fonts } from '../design/tokens';

let Audio: any = null;
let Haptics: any = null;
if (Platform.OS !== 'web') {
  try { Audio = require('expo-av').Audio; } catch {}
  try { Haptics = require('expo-haptics'); } catch {}
}

type State = 'idle' | 'recording' | 'busy';

interface Props {
  onAudio: (uri: string, durationSec: number) => void | Promise<void>;
  busy?: boolean;
  busyLabel?: string;
  idleLabel?: string;
  recordingLabel?: string;
  disabled?: boolean;
  size?: 'sm' | 'md';
}

/** Tap to start, tap to stop. Calls onAudio with the local file URI when finished.
 * Web is unsupported — the button hides itself there.
 */
export default function MicButton({
  onAudio, busy = false, idleLabel = 'Record', busyLabel = 'Working…',
  recordingLabel = 'Stop', disabled = false, size = 'md',
}: Props) {
  const [state, setState] = useState<State>(busy ? 'busy' : 'idle');
  const [duration, setDuration] = useState(0);
  const [error, setError] = useState('');
  const recRef = useRef<any>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (busy) setState('busy');
    else if (state === 'busy') setState('idle');
  }, [busy]);

  useEffect(() => () => {
    if (timerRef.current) clearInterval(timerRef.current);
    if (recRef.current) recRef.current.stopAndUnloadAsync().catch(() => {});
  }, []);

  const start = useCallback(async () => {
    if (!Audio) { setError('Recording unavailable on web'); return; }
    try {
      const permission = await Audio.requestPermissionsAsync();
      if (!permission.granted) { setError('Mic permission needed'); return; }
      await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });
      const { recording: rec } = await Audio.Recording.createAsync(
        Audio.RecordingOptionsPresets.HIGH_QUALITY
      );
      recRef.current = rec;
      setState('recording');
      setDuration(0);
      setError('');
      timerRef.current = setInterval(() => setDuration(d => d + 1), 1000);
      if (Haptics) Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    } catch (e: any) {
      setError(`Recording failed: ${e?.message || e}`);
      setState('idle');
    }
  }, []);

  const stop = useCallback(async () => {
    if (!recRef.current) { setState('idle'); return; }
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    try {
      await recRef.current.stopAndUnloadAsync();
      const uri = recRef.current.getURI();
      const captured = duration;
      recRef.current = null;
      setState('busy');
      if (Haptics) Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      if (uri) {
        await onAudio(uri, captured);
      }
    } catch (e: any) {
      setError(`Stop failed: ${e?.message || e}`);
      setState('idle');
    }
  }, [duration, onAudio]);

  if (Platform.OS === 'web') return null;

  const isBusy = state === 'busy' || busy;
  const isRecording = state === 'recording';
  const handlePress = isRecording ? stop : start;

  return (
    <View>
      <Pressable
        disabled={disabled || isBusy}
        onPress={handlePress}
        style={[
          styles.button,
          size === 'sm' && styles.buttonSm,
          isRecording && styles.buttonRecording,
          isBusy && styles.buttonBusy,
        ]}
      >
        {isBusy ? (
          <>
            <ActivityIndicator color="#fff" />
            <Text style={styles.label}>{busyLabel}</Text>
          </>
        ) : (
          <>
            <Text style={styles.icon}>{isRecording ? '■' : '●'}</Text>
            <Text style={styles.label}>
              {isRecording ? `${recordingLabel} (${Math.floor(duration / 60)}:${String(duration % 60).padStart(2, '0')})` : idleLabel}
            </Text>
          </>
        )}
      </Pressable>
      {error ? <Text style={styles.error}>{error}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  button: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingVertical: 12,
    paddingHorizontal: 18,
    backgroundColor: colors.rubric,
    borderRadius: 6,
  },
  buttonSm: { paddingVertical: 8, paddingHorizontal: 12 },
  buttonRecording: { backgroundColor: colors.danger },
  buttonBusy: { backgroundColor: colors.textSecondary },
  icon: { color: '#fff', fontSize: 14, fontFamily: fonts.bodyMedium },
  label: { color: '#fff', fontFamily: fonts.bodyMedium, fontSize: 14 },
  error: { color: colors.danger, fontFamily: fonts.bodyMedium, fontSize: 12, marginTop: 6 },
});
