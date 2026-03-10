import { useState, useRef, useEffect, useCallback } from 'react';
import {
  View, Text, Pressable, TextInput, StyleSheet,
  Platform, Animated, Modal, Dimensions, Image,
} from 'react-native';
import { Audio } from 'expo-av';
import { captureScreen } from 'react-native-view-shot';
// Note: captureScreen works on native only. On web, screenshot is skipped.
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Haptics from 'expo-haptics';
import { colors, fonts, layout } from '../design/tokens';
import { logEvent } from '../data/logger';
import { getFeedbackContext } from '../lib/feedback-context';
import { uploadFeedback } from '../lib/chat-api';

const FEEDBACK_HIDDEN_KEY = '@petrarca/feedback_button_hidden';

export default function FeedbackCapture() {
  const [hidden, setHidden] = useState(true);
  const [overlayVisible, setOverlayVisible] = useState(false);
  const [recording, setRecording] = useState(false);
  const [duration, setDuration] = useState(0);
  const [audioUri, setAudioUri] = useState<string | null>(null);
  const [screenshotUri, setScreenshotUri] = useState<string | null>(null);
  const [textInput, setTextInput] = useState('');
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');

  const recRef = useRef<Audio.Recording | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const buttonOpacity = useRef(new Animated.Value(0)).current;
  const contextRef = useRef<Record<string, any>>({});

  // Load hidden state
  useEffect(() => {
    AsyncStorage.getItem(FEEDBACK_HIDDEN_KEY).then((val) => {
      const isHidden = val === 'true';
      setHidden(isHidden);
      if (!isHidden) {
        Animated.timing(buttonOpacity, { toValue: 1, duration: 300, useNativeDriver: true }).start();
      }
    });
  }, []);

  const toggleVisibility = useCallback(() => {
    const newHidden = !hidden;
    setHidden(newHidden);
    AsyncStorage.setItem(FEEDBACK_HIDDEN_KEY, String(newHidden));
    Animated.timing(buttonOpacity, {
      toValue: newHidden ? 0 : 1, duration: 200, useNativeDriver: true,
    }).start();
    if (Platform.OS !== 'web') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
  }, [hidden]);

  const openOverlay = useCallback(async () => {
    // Capture context and screenshot BEFORE showing the modal
    contextRef.current = getFeedbackContext();
    logEvent('feedback_capture_start', { screen: contextRef.current.screen, article_id: contextRef.current.articleId });

    // Take screenshot
    try {
      const uri = await captureScreen({ format: 'png', quality: 0.8 });
      setScreenshotUri(uri);
    } catch {
      setScreenshotUri(null);
    }

    setOverlayVisible(true);
    setSent(false);
    setSending(false);
    setError('');
    setAudioUri(null);
    setTextInput('');
    setDuration(0);
    if (Platform.OS !== 'web') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
  }, []);

  const dismissOverlay = useCallback(() => {
    if (recRef.current) {
      recRef.current.stopAndUnloadAsync().catch(() => {});
      recRef.current = null;
    }
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    setRecording(false);
    setOverlayVisible(false);
    logEvent('feedback_capture_dismiss', { had_audio: !!audioUri, had_text: textInput.length > 0 });
  }, [audioUri, textInput]);

  const startRecording = async () => {
    try {
      const permission = await Audio.requestPermissionsAsync();
      if (!permission.granted) { setError('Microphone permission needed'); return; }
      await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });
      const { recording: rec } = await Audio.Recording.createAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
      recRef.current = rec;
      setRecording(true);
      setDuration(0);
      timerRef.current = setInterval(() => setDuration(d => d + 1), 1000);
      if (Platform.OS !== 'web') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    } catch (e) {
      setError(`Recording failed: ${e}`);
    }
  };

  const stopRecording = async () => {
    if (!recRef.current) return;
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    try {
      await recRef.current.stopAndUnloadAsync();
      const uri = recRef.current.getURI();
      recRef.current = null;
      setRecording(false);
      if (uri) setAudioUri(uri);
      if (Platform.OS !== 'web') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    } catch (e) {
      setRecording(false);
      setError(`Stop failed: ${e}`);
    }
  };

  const handleSend = async () => {
    if (!textInput.trim() && !audioUri) {
      setError('Add a voice recording or type some text');
      return;
    }
    setSending(true);
    setError('');

    try {
      await uploadFeedback({
        screenshotUri,
        audioUri,
        text: textInput.trim() || null,
        context: contextRef.current,
      });

      logEvent('feedback_capture_complete', {
        screen: contextRef.current.screen,
        article_id: contextRef.current.articleId,
        has_audio: !!audioUri,
        has_screenshot: !!screenshotUri,
        has_text: !!textInput.trim(),
        audio_duration: audioUri ? duration : 0,
      });

      setSent(true);
      if (Platform.OS !== 'web') Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      setTimeout(() => { setOverlayVisible(false); setSent(false); }, 1200);
    } catch (e) {
      setError(`Upload failed — saved locally`);
      // Fallback: save locally
      try {
        const raw = await AsyncStorage.getItem('@petrarca/feedback_items');
        const items = raw ? JSON.parse(raw) : [];
        items.push({
          id: `fb_${Date.now()}`,
          timestamp: new Date().toISOString(),
          context: contextRef.current,
          audio_uri: audioUri,
          screenshot_uri: screenshotUri,
          text: textInput.trim() || null,
          uploaded: false,
        });
        await AsyncStorage.setItem('@petrarca/feedback_items', JSON.stringify(items));
      } catch {}
      setSending(false);
    }
  };

  const fmt = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`;

  if (hidden) return null;

  return (
    <>
      {/* Floating button */}
      <Animated.View style={[styles.floatingButton, { opacity: buttonOpacity }]}>
        <Pressable
          onPress={openOverlay}
          onLongPress={toggleVisibility}
          delayLongPress={600}
          style={styles.buttonTouchable}
          accessibilityLabel="Capture feedback"
          accessibilityRole="button"
        >
          <Text style={styles.buttonGlyph}>✦</Text>
        </Pressable>
      </Animated.View>

      {/* Overlay modal */}
      <Modal visible={overlayVisible} transparent animationType="fade" onRequestClose={dismissOverlay}>
        <Pressable style={styles.backdrop} onPress={dismissOverlay}>
          <Pressable style={styles.overlayCard} onPress={e => e.stopPropagation()}>
            {/* Header */}
            <View style={styles.overlayHeader}>
              <Text style={styles.overlayTitle}>Feedback</Text>
              <Pressable onPress={dismissOverlay} style={styles.closeButton} hitSlop={12}>
                <Text style={styles.closeText}>✕</Text>
              </Pressable>
            </View>

            {/* Context line */}
            <Text style={styles.contextLine} numberOfLines={1}>
              {contextRef.current.screen}
              {contextRef.current.articleTitle ? ` · ${contextRef.current.articleTitle}` : ''}
              {contextRef.current.activeLens ? ` · ${contextRef.current.activeLens}` : ''}
            </Text>

            {sent ? (
              <View style={styles.sentRow}>
                <Text style={styles.sentText}>Sent ✓</Text>
              </View>
            ) : (
              <>
                {/* Screenshot thumbnail */}
                {screenshotUri && (
                  <View style={styles.screenshotRow}>
                    <Image source={{ uri: screenshotUri }} style={styles.screenshotThumb} resizeMode="cover" />
                    <Pressable onPress={() => setScreenshotUri(null)}>
                      <Text style={styles.removeText}>Remove</Text>
                    </Pressable>
                  </View>
                )}

                {/* Text input */}
                <TextInput
                  style={styles.textInput}
                  placeholder="What's on your mind..."
                  placeholderTextColor={colors.textMuted}
                  value={textInput}
                  onChangeText={setTextInput}
                  multiline
                  maxLength={2000}
                  autoFocus
                />

                {/* Voice recording */}
                <View style={styles.voiceSection}>
                  {!recording && !audioUri && (
                    <Pressable onPress={startRecording} style={styles.recordBtn}>
                      <View style={styles.recordDot} />
                      <Text style={styles.recordLabel}>Record voice</Text>
                    </Pressable>
                  )}
                  {recording && (
                    <View style={styles.recordingRow}>
                      <View style={styles.pulseDot} />
                      <Text style={styles.timer}>{fmt(duration)}</Text>
                      <Pressable onPress={stopRecording} style={styles.stopBtn}>
                        <Text style={styles.stopLabel}>Stop</Text>
                      </Pressable>
                    </View>
                  )}
                  {audioUri && !recording && (
                    <View style={styles.recordedRow}>
                      <Text style={styles.recordedText}>Recorded {fmt(duration)}</Text>
                      <Pressable onPress={() => { setAudioUri(null); setDuration(0); }}>
                        <Text style={styles.removeText}>Remove</Text>
                      </Pressable>
                    </View>
                  )}
                </View>

                {error ? <Text style={styles.errorText}>{error}</Text> : null}

                {/* Send button */}
                <Pressable
                  onPress={handleSend}
                  style={[styles.sendBtn, sending && styles.sendBtnDisabled, !textInput.trim() && !audioUri && styles.sendBtnDisabled]}
                  disabled={sending}
                >
                  <Text style={[styles.sendLabel, !textInput.trim() && !audioUri && styles.sendLabelDisabled]}>
                    {sending ? 'Sending...' : 'Send'}
                  </Text>
                </Pressable>
              </>
            )}
          </Pressable>
        </Pressable>
      </Modal>
    </>
  );
}

export async function showFeedbackButton(): Promise<void> {
  await AsyncStorage.setItem(FEEDBACK_HIDDEN_KEY, 'false');
}

const BUTTON_SIZE = 30;

const styles = StyleSheet.create({
  floatingButton: {
    position: 'absolute',
    bottom: 24,
    right: 16,
    zIndex: 9999,
  },
  buttonTouchable: {
    width: BUTTON_SIZE,
    height: BUTTON_SIZE,
    borderRadius: BUTTON_SIZE / 2,
    backgroundColor: colors.parchmentDark,
    alignItems: 'center',
    justifyContent: 'center',
    opacity: 0.65,
    ...(Platform.OS === 'web' ? { cursor: 'pointer' as any } : {}),
  },
  buttonGlyph: {
    fontSize: 13,
    color: colors.textMuted,
    marginTop: -1,
  },

  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.35)',
    justifyContent: 'flex-end',
  },
  overlayCard: {
    backgroundColor: colors.parchment,
    borderTopLeftRadius: 12,
    borderTopRightRadius: 12,
    paddingHorizontal: layout.screenPadding,
    paddingTop: 16,
    paddingBottom: Platform.OS === 'ios' ? 34 : 20,
    maxHeight: Dimensions.get('window').height * 0.7,
  },
  overlayHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  overlayTitle: {
    fontFamily: fonts.displaySemiBold,
    fontSize: 18,
    color: colors.ink,
    ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}),
  },
  closeButton: {
    width: layout.touchTarget,
    height: layout.touchTarget,
    alignItems: 'center',
    justifyContent: 'center',
  },
  closeText: {
    fontSize: 18,
    color: colors.textMuted,
  },
  contextLine: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.textMuted,
    marginBottom: 12,
  },

  screenshotRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: 12,
  },
  screenshotThumb: {
    width: 80,
    height: 60,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: colors.rule,
  },

  textInput: {
    fontFamily: fonts.reading,
    fontSize: 15,
    lineHeight: 22,
    color: colors.textBody,
    borderWidth: 1,
    borderColor: colors.rule,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    minHeight: 80,
    maxHeight: 160,
    textAlignVertical: 'top',
    marginBottom: 12,
  },

  voiceSection: { marginBottom: 12 },
  recordBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 8,
  },
  recordDot: {
    width: 8, height: 8, borderRadius: 4,
    backgroundColor: colors.rubric,
  },
  recordLabel: {
    fontFamily: fonts.uiMedium,
    fontSize: 13,
    color: colors.rubric,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  recordingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  pulseDot: {
    width: 10, height: 10, borderRadius: 5,
    backgroundColor: colors.rubric,
  },
  timer: {
    fontFamily: fonts.display,
    fontSize: 20,
    color: colors.ink,
    flex: 1,
  },
  stopBtn: {
    backgroundColor: colors.ink,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 16,
  },
  stopLabel: {
    fontFamily: fonts.uiMedium,
    fontSize: 13,
    color: colors.parchment,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  recordedRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  recordedText: {
    fontFamily: fonts.ui,
    fontSize: 13,
    color: colors.textSecondary,
    flex: 1,
  },
  removeText: {
    fontFamily: fonts.ui,
    fontSize: 13,
    color: colors.rubric,
  },
  errorText: {
    fontFamily: fonts.ui,
    fontSize: 12,
    color: colors.rubric,
    marginBottom: 8,
  },
  sendBtn: {
    backgroundColor: colors.rubric,
    paddingVertical: 12,
    borderRadius: 8,
    alignItems: 'center',
  },
  sendBtnDisabled: { backgroundColor: colors.rule },
  sendLabel: {
    fontFamily: fonts.uiMedium,
    fontSize: 14,
    color: colors.parchment,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  sendLabelDisabled: { color: colors.textMuted },
  sentRow: { paddingVertical: 20, alignItems: 'center' },
  sentText: {
    fontFamily: fonts.ui,
    fontSize: 14,
    color: colors.claimNew,
  },
});
