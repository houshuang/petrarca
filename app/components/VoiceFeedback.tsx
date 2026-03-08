import { useState, useRef } from 'react';
import { View, Text, Pressable, StyleSheet, Platform } from 'react-native';
import { Audio } from 'expo-av';
import { colors, fonts } from '../design/tokens';
import { transcribeAudio } from '../lib/transcribe';
import { logEvent } from '../data/logger';

type Status = 'idle' | 'recording' | 'transcribing' | 'done' | 'error';

interface VoiceFeedbackProps {
  articleId: string;
  articleContext: string;
  onClose: () => void;
}

export default function VoiceFeedback({ articleId, articleContext, onClose }: VoiceFeedbackProps) {
  const [status, setStatus] = useState<Status>('idle');
  const [transcript, setTranscript] = useState('');
  const [error, setError] = useState('');
  const [duration, setDuration] = useState(0);
  const recording = useRef<Audio.Recording | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const startRecording = async () => {
    try {
      const permission = await Audio.requestPermissionsAsync();
      if (!permission.granted) {
        setError('Microphone permission required');
        setStatus('error');
        return;
      }
      await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });
      const { recording: rec } = await Audio.Recording.createAsync(
        Audio.RecordingOptionsPresets.HIGH_QUALITY,
      );
      recording.current = rec;
      setStatus('recording');
      setDuration(0);
      timerRef.current = setInterval(() => setDuration(d => d + 1), 1000);
      logEvent('voice_feedback_start', { article_id: articleId });
    } catch (e) {
      setError(`Failed to start recording: ${e}`);
      setStatus('error');
    }
  };

  const stopAndTranscribe = async () => {
    if (!recording.current) return;
    if (timerRef.current) clearInterval(timerRef.current);

    try {
      await recording.current.stopAndUnloadAsync();
      const uri = recording.current.getURI();
      recording.current = null;

      if (!uri) {
        setError('No recording file');
        setStatus('error');
        return;
      }

      setStatus('transcribing');
      logEvent('voice_feedback_stop', { article_id: articleId, duration_seconds: duration });

      const text = await transcribeAudio(uri);
      setTranscript(text);
      setStatus('done');

      // Log the feedback with full context
      logEvent('voice_feedback_transcript', {
        article_id: articleId,
        transcript: text,
        duration_seconds: duration,
        article_context: articleContext.slice(0, 2000),
      });
    } catch (e) {
      setError(`Transcription failed: ${e}`);
      setStatus('error');
    }
  };

  const formatTime = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`;

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>{'✦ Voice Feedback'}</Text>
        <Pressable onPress={onClose} style={styles.closeButton}>
          <Text style={styles.closeText}>Done</Text>
        </Pressable>
      </View>

      <View style={styles.body}>
        {status === 'idle' && (
          <>
            <Text style={styles.hint}>
              Record your thoughts about this article. The recording will be transcribed and saved with your reading context.
            </Text>
            <Pressable onPress={startRecording} style={styles.recordButton}>
              <View style={styles.recordDot} />
              <Text style={styles.recordButtonText}>Start Recording</Text>
            </Pressable>
          </>
        )}

        {status === 'recording' && (
          <>
            <View style={styles.recordingIndicator}>
              <View style={styles.recordingPulse} />
              <Text style={styles.recordingTime}>{formatTime(duration)}</Text>
            </View>
            <Pressable onPress={stopAndTranscribe} style={styles.stopButton}>
              <Text style={styles.stopButtonText}>Stop & Transcribe</Text>
            </Pressable>
          </>
        )}

        {status === 'transcribing' && (
          <Text style={styles.hint}>Transcribing...</Text>
        )}

        {status === 'done' && (
          <>
            <Text style={styles.transcriptLabel}>Transcribed feedback:</Text>
            <Text style={styles.transcriptText}>{transcript || '(empty)'}</Text>
            <Text style={styles.savedNote}>Saved to interaction log</Text>
          </>
        )}

        {status === 'error' && (
          <Text style={styles.errorText}>{error}</Text>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: colors.parchment,
    borderTopWidth: 1,
    borderTopColor: colors.rule,
    paddingBottom: Platform.OS === 'ios' ? 34 : 16,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.rule,
  },
  title: {
    fontFamily: fonts.uiMedium,
    fontSize: 11,
    letterSpacing: 1,
    color: colors.rubric,
    textTransform: 'uppercase',
  },
  closeButton: {
    paddingVertical: 4,
    paddingHorizontal: 8,
  },
  closeText: {
    fontFamily: fonts.ui,
    fontSize: 14,
    color: colors.textMuted,
  },
  body: {
    padding: 20,
    alignItems: 'center',
    gap: 16,
  },
  hint: {
    fontFamily: fonts.reading,
    fontSize: 14,
    lineHeight: 21,
    color: colors.textSecondary,
    textAlign: 'center',
  },
  recordButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: colors.ink,
    paddingHorizontal: 24,
    paddingVertical: 14,
    borderRadius: 24,
  },
  recordDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: colors.rubric,
  },
  recordButtonText: {
    fontFamily: fonts.uiMedium,
    fontSize: 15,
    color: colors.parchment,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  recordingIndicator: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  recordingPulse: {
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: colors.rubric,
  },
  recordingTime: {
    fontFamily: fonts.display,
    fontSize: 28,
    color: colors.ink,
  },
  stopButton: {
    backgroundColor: colors.rubric,
    paddingHorizontal: 24,
    paddingVertical: 14,
    borderRadius: 24,
  },
  stopButtonText: {
    fontFamily: fonts.uiMedium,
    fontSize: 15,
    color: colors.parchment,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  transcriptLabel: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    alignSelf: 'flex-start',
  },
  transcriptText: {
    fontFamily: fonts.reading,
    fontSize: 14,
    lineHeight: 21,
    color: colors.textBody,
    alignSelf: 'flex-start',
  },
  savedNote: {
    fontFamily: fonts.ui,
    fontSize: 12,
    color: colors.claimNew,
  },
  errorText: {
    fontFamily: fonts.reading,
    fontSize: 14,
    color: colors.rubric,
    textAlign: 'center',
  },
});
