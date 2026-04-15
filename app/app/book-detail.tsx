import { useState, useCallback, useMemo, useRef } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, Image, Platform, TextInput,
  Alert, ActivityIndicator, KeyboardAvoidingView,
} from 'react-native';
import { useRouter, useLocalSearchParams, useFocusEffect } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import { Audio } from 'expo-av';
import { documentDirectory, makeDirectoryAsync, copyAsync, getInfoAsync } from 'expo-file-system/legacy';
import * as Haptics from 'expo-haptics';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { logEvent } from '../data/logger';
import {
  getPhysicalBook, getBookCaptures, updateReadingPosition,
  addBookCapture, generateCaptureId, updatePhysicalBook, updateBookCapture,
} from '../data/book-store';
import { useBookStoreVersion } from '../data/use-book-store';
import {
  uploadBookVoiceNote, researchBook, getBookResearch, getStorySoFar, identifyBookCover, waitForBookResearch,
} from '../lib/book-api';
import { notifyChapterComplete } from '../lib/review-api';
import ChapterContext from '../components/ChapterContext';
import { enqueuePhotoUpload, pollPhotoResults, getUploadQueueStatus, initUploadQueue } from '../lib/upload-queue';
import type { PhysicalBook, BookCapture, BookResearch, StorySoFarBriefing, BookArticleConnection, SuggestedReading } from '../data/types';
import { colors, fonts, type, layout } from '../design/tokens';
import { setFeedbackContext } from '../lib/feedback-context';
import DoubleRule from '../components/DoubleRule';
import BookCurriculumContext from '../components/BookCurriculumContext';

const PENDING_BOOK_VOICE_KEY = '@petrarca/pending_book_voice_notes';
interface PendingBookVoice {
  localPath: string;
  captureId: string;
  bookId: string;
  bookTitle: string;
  chapter?: string;
  pageNumber?: number;
}

async function savePendingVoice(note: PendingBookVoice): Promise<void> {
  const raw = await AsyncStorage.getItem(PENDING_BOOK_VOICE_KEY);
  const pending: PendingBookVoice[] = raw ? JSON.parse(raw) : [];
  pending.push(note);
  await AsyncStorage.setItem(PENDING_BOOK_VOICE_KEY, JSON.stringify(pending));
}

async function removePendingVoice(captureId: string): Promise<void> {
  const raw = await AsyncStorage.getItem(PENDING_BOOK_VOICE_KEY);
  if (!raw) return;
  const pending: PendingBookVoice[] = JSON.parse(raw);
  await AsyncStorage.setItem(PENDING_BOOK_VOICE_KEY, JSON.stringify(pending.filter(n => n.captureId !== captureId)));
}

async function retryPendingVoiceNotes(): Promise<void> {
  const raw = await AsyncStorage.getItem(PENDING_BOOK_VOICE_KEY);
  if (!raw) return;
  const pending: PendingBookVoice[] = JSON.parse(raw);
  for (const note of pending) {
    try {
      if (Platform.OS !== 'web' && documentDirectory) {
        const info = await getInfoAsync(note.localPath);
        if (!info.exists) {
          await removePendingVoice(note.captureId);
          continue;
        }
      }
      const result = await uploadBookVoiceNote(note.localPath, note.bookId, note.bookTitle, note.chapter, note.pageNumber);
      await updateBookCapture(note.captureId, {
        transcript: result.transcript,
        extracted_ideas: result.extracted_ideas,
        topics: result.topics,
        transcription_status: 'completed',
        upload_status: 'uploaded',
      });
      await removePendingVoice(note.captureId);
      logEvent('book_voice_retry_success', { capture_id: note.captureId });
    } catch {
      // Will retry next time the screen is focused
    }
  }
}


function formatTimeAgo(timestamp: number): string {
  const hours = Math.floor((Date.now() - timestamp) / 3600000);
  if (hours < 1) return 'just now';
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return 'yesterday';
  if (days < 7) return `${days}d ago`;
  return `${Math.floor(days / 7)}w ago`;
}

function CaptureCard({ capture }: { capture: BookCapture }) {
  const typeLabel = capture.type === 'voice_note' ? 'Voice note' : capture.type === 'page_photo' ? 'Page scan' : 'Note';
  const typeIcon = capture.type === 'voice_note' ? '🎙' : capture.type === 'page_photo' ? '📷' : '✎';

  return (
    <View style={captureStyles.card}>
      <View style={captureStyles.header}>
        <Text style={captureStyles.typeIcon}>{typeIcon}</Text>
        <Text style={captureStyles.typeLabel}>{typeLabel}</Text>
        {capture.chapter && <><Text style={captureStyles.dot}>·</Text><Text style={captureStyles.meta}>{capture.chapter}</Text></>}
        {capture.page_number != null && <><Text style={captureStyles.dot}>·</Text><Text style={captureStyles.meta}>p. {capture.page_number}</Text></>}
        <View style={{ flex: 1 }} />
        <Text style={captureStyles.time}>{formatTimeAgo(capture.created_at)}</Text>
      </View>
      {capture.extracted_ideas && capture.extracted_ideas.length > 0 && (
        <View style={captureStyles.ideas}>
          <Text style={captureStyles.ideasLabel}>{'\u2726'} Key ideas</Text>
          {capture.extracted_ideas.map((idea, i) => (
            <View key={i} style={captureStyles.ideaRow}>
              <View style={captureStyles.ideaBullet} />
              <Text style={captureStyles.ideaText}>{idea}</Text>
            </View>
          ))}
        </View>
      )}
      {capture.transcript && (
        <Text style={captureStyles.transcript} numberOfLines={3}>{capture.transcript}</Text>
      )}
      {capture.type === 'voice_note' && capture.transcription_status === 'processing' && (
        <Text style={captureStyles.transcript}>Transcribing…</Text>
      )}
      {capture.type === 'voice_note' && capture.transcription_status === 'failed' && (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Text style={[captureStyles.transcript, { color: colors.rubric }]}>Transcription failed</Text>
          <Pressable onPress={() => retryPendingVoiceNotes()}>
            <Text style={{ fontFamily: fonts.ui, fontSize: 12, color: colors.rubric, textDecorationLine: 'underline' }}>Retry</Text>
          </Pressable>
        </View>
      )}
      {capture.type === 'page_photo' && capture.upload_status === 'pending' && (
        <Text style={captureStyles.transcript}>Uploading…</Text>
      )}
      {capture.type === 'page_photo' && capture.upload_status === 'uploaded' && capture.ocr_status === 'processing' && (
        <Text style={captureStyles.transcript}>Processing OCR…</Text>
      )}
      {capture.type === 'page_photo' && capture.ocr_status === 'failed' && (
        <Text style={[captureStyles.transcript, { color: colors.rubric }]}>OCR failed</Text>
      )}
      {capture.text && <Text style={captureStyles.noteText}>{capture.text}</Text>}
      {capture.ocr_text && !capture.extracted_ideas?.length && (
        <Text style={captureStyles.transcript} numberOfLines={3}>{capture.ocr_text}</Text>
      )}
    </View>
  );
}

const captureStyles = StyleSheet.create({
  card: { paddingVertical: 14, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.rule },
  header: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 },
  typeIcon: { fontSize: 14 },
  typeLabel: { fontFamily: fonts.uiMedium, fontSize: 11, color: colors.ink, letterSpacing: 0.3, textTransform: 'uppercase', ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}) },
  dot: { fontFamily: fonts.ui, fontSize: 11, color: colors.textMuted },
  meta: { fontFamily: fonts.ui, fontSize: 11, color: colors.textMuted },
  time: { fontFamily: fonts.ui, fontSize: 10, color: colors.textMuted },
  ideas: { marginBottom: 8 },
  ideasLabel: { fontFamily: fonts.bodyItalic, fontSize: 11.5, color: colors.rubric, marginBottom: 6, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  ideaRow: { flexDirection: 'row', gap: 8, marginBottom: 4, paddingLeft: 4 },
  ideaBullet: { width: 4, height: 4, borderRadius: 2, backgroundColor: colors.rubric, marginTop: 7 },
  ideaText: { flex: 1, fontFamily: fonts.reading, fontSize: 14, lineHeight: 20, color: colors.textBody },
  transcript: { fontFamily: fonts.readingItalic, fontSize: 13, lineHeight: 19, color: colors.textSecondary, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  noteText: { fontFamily: fonts.reading, fontSize: 14, lineHeight: 20, color: colors.textBody },
});

export default function BookDetailScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [refreshKey, setRefreshKey] = useState(0);
  const [textNoteInput, setTextNoteInput] = useState('');
  const [showTextInput, setShowTextInput] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [voiceRecording, setVoiceRecording] = useState(false);
  const [voiceDuration, setVoiceDuration] = useState(0);
  const [voiceUploading, setVoiceUploading] = useState(false);
  const recRef = useRef<Audio.Recording | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [chapterDropdownOpen, setChapterDropdownOpen] = useState(false);
  const [research, setResearch] = useState<BookResearch | null>(null);
  const [researchLoading, setResearchLoading] = useState(false);
  const [researchRegenerating, setResearchRegenerating] = useState(false);
  const [storySoFar, setStorySoFar] = useState<StorySoFarBriefing | null>(null);
  const [showStorySoFar, setShowStorySoFar] = useState(false);
  const [chapterCompleteText, setChapterCompleteText] = useState<string | null>(null);
  const [reviewDueCount, setReviewDueCount] = useState(0);
  const [chapterContextMode, setChapterContextMode] = useState<'preview' | 'review' | null>(null);

  useFocusEffect(useCallback(() => {
    setRefreshKey(k => k + 1);
    setFeedbackContext({ screen: 'book-detail', extra: { bookId: id } });

    // Initialize upload queue and poll for completed OCR results
    initUploadQueue();
    pollPhotoResults().then(completed => {
      if (completed > 0) setRefreshKey(k => k + 1);
    });

    // Re-enqueue any failed photos that have local URIs (migration from old system)
    if (id) {
      const caps = getBookCaptures(id);
      const book = getPhysicalBook(id);
      if (book) {
        for (const cap of caps) {
          if (cap.type === 'page_photo' && cap.upload_status === 'failed' && cap.photo_uri) {
            enqueuePhotoUpload({
              captureId: cap.id, photoUri: cap.photo_uri,
              bookId: book.id, bookTitle: book.title,
              chapter: cap.chapter, pageNumber: cap.page_number,
            });
          }
        }
      }
    }

    // Voice retries still use old system
    retryPendingVoiceNotes().then(() => setRefreshKey(k => k + 1));

    // Poll for OCR results periodically while screen is focused
    const interval = setInterval(() => {
      pollPhotoResults().then(completed => {
        if (completed > 0) setRefreshKey(k => k + 1);
      });
    }, 5000);
    return () => clearInterval(interval);
  }, [id]));

  const storeVersion = useBookStoreVersion();
  const book = useMemo(() => id ? getPhysicalBook(id) : undefined, [id, refreshKey, storeVersion]);
  const captures = useMemo(() => id ? getBookCaptures(id) : [], [id, refreshKey, storeVersion]);

  const [pageInput, setPageInput] = useState(book?.current_page?.toString() || '');
  const [selectedChapter, setSelectedChapter] = useState(book?.current_chapter || '');

  // Fetch research data when book is loaded
  useFocusEffect(useCallback(() => {
    if (!book) return;
    let cancelled = false;

    (async () => {
      try {
        const res = await getBookResearch(book.id);
        if (cancelled) return;
        setResearch(res);
        if (!res?.thesis?.trim()) {
          setResearchLoading(true);
          logEvent('book_research_started', { book_id: book.id, title: book.title });
          await researchBook(book.id, book.title, book.author, book.chapters, book.topics, book.isbn, {
            invalidate: Boolean(res),
          });
          if (cancelled) return;
          const updated = await waitForBookResearch(book.id, { maxWaitMs: 180000, intervalMs: 4000 });
          if (!cancelled) setResearch(updated);
        }
      } catch {
        if (!cancelled) setResearch(null);
      } finally {
        if (!cancelled) setResearchLoading(false);
      }

      // Story So Far disabled — not useful in practice
    })();

    return () => { cancelled = true; };
  }, [book?.id]));

  const handleKickoffResearch = useCallback(() => {
    if (!book || researchRegenerating || researchLoading) return;
    void (async () => {
      setResearchRegenerating(true);
      setResearch(null);
      try {
        logEvent('book_research_kickoff', { book_id: book.id, title: book.title });
        await researchBook(book.id, book.title, book.author, book.chapters, book.topics, book.isbn, {
          invalidate: true,
        });
        const updated = await waitForBookResearch(book.id, { maxWaitMs: 180000, intervalMs: 4000 });
        setResearch(updated);
        if (!updated?.thesis?.trim()) {
          Alert.alert(
            'Still running',
            'Research is not ready yet. Tap Generate summary again in a minute, or reopen this book.',
          );
        }
      } catch (e) {
        Alert.alert('Summary failed', e instanceof Error ? e.message : 'Unknown error');
      } finally {
        setResearchRegenerating(false);
      }
    })();
  }, [book, researchRegenerating, researchLoading]);

  const handleRegenerateResearch = useCallback(() => {
    if (!book || researchRegenerating || researchLoading) return;
    Alert.alert(
      'Regenerate book research?',
      'Clears the cached summary and re-runs search-backed research. This usually takes one to three minutes.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Regenerate',
          onPress: () => {
            void (async () => {
              setResearchRegenerating(true);
              setResearch(null);
              try {
                logEvent('book_research_regenerate', { book_id: book.id, title: book.title });
                await researchBook(book.id, book.title, book.author, book.chapters, book.topics, book.isbn, {
                  invalidate: true,
                });
                const updated = await waitForBookResearch(book.id, { maxWaitMs: 180000, intervalMs: 4000 });
                setResearch(updated);
                if (!updated?.thesis?.trim()) {
                  Alert.alert(
                    'Still running',
                    'Research is not ready yet. Leave this screen and open the book again in a minute.',
                  );
                }
              } catch (e) {
                Alert.alert('Regenerate failed', e instanceof Error ? e.message : 'Unknown error');
              } finally {
                setResearchRegenerating(false);
              }
            })();
          },
        },
      ],
    );
  }, [book, researchRegenerating, researchLoading]);

  if (!book) {
    return (
      <View style={styles.container}>
        <Pressable style={styles.backButton} onPress={() => router.back()}>
          <Text style={styles.backText}>{'\u2039'} Library</Text>
        </Pressable>
        <Text style={styles.errorText}>Book not found</Text>
      </View>
    );
  }

  const coverUri = book.cover_url || book.cover_image_uri;
  const progress = book.current_page && book.page_count ? Math.round((book.current_page / book.page_count) * 100) : 0;
  const hasResearchThesis = Boolean(research?.thesis?.trim());
  const researchBusy = researchLoading || researchRegenerating;

  const handlePageUpdate = async () => {
    const page = parseInt(pageInput, 10);
    if (!isNaN(page) && page > 0) {
      await updateReadingPosition(book.id, page, undefined);
      setRefreshKey(k => k + 1);
    }
  };

  const handleChapterSelect = async (ch: { number: number; title: string }) => {
    const previousChapter = book.current_chapter;
    const chapterLabel = `Ch ${ch.number}: ${ch.title}`;
    setSelectedChapter(chapterLabel);
    setChapterDropdownOpen(false);
    await updateReadingPosition(book.id, undefined, chapterLabel);
    logEvent('book_chapter_select', { book_id: book.id, chapter: ch.number });

    // Advancing to a new chapter implies finishing the previous one
    if (previousChapter && previousChapter !== chapterLabel) {
      logEvent('book_chapter_completed', {
        book_id: book.id,
        completed_chapter: previousChapter,
        next_chapter: chapterLabel,
      });
      // Show brief chapter-complete acknowledgment
      setChapterCompleteText(`Finished ${previousChapter}`);
      setTimeout(() => setChapterCompleteText(null), 3000);

      // Trigger review item creation in background
      const prevChapterNum = parseInt(previousChapter.replace(/^Ch (\d+):.*/, '$1'), 10);
      if (!isNaN(prevChapterNum)) {
        notifyChapterComplete(book.id, prevChapterNum, previousChapter.replace(/^Ch \d+:\s*/, ''))
          .then(result => {
            if (result.items_created > 0) {
              setReviewDueCount(c => c + result.items_created);
            }
          })
          .catch(() => {});
      }
    }
    setRefreshKey(k => k + 1);
  };

  const handlePhotoCapture = async () => {
    const result = await ImagePicker.launchCameraAsync({ quality: 0.8 });
    if (result.canceled || !result.assets[0]) return;
    const photoUri = result.assets[0].uri;
    logEvent('book_capture_photo_taken', { book_id: book.id });

    const captureId = generateCaptureId();
    // Save capture immediately with pending status
    await addBookCapture({
      id: captureId, book_id: book.id, type: 'page_photo', created_at: Date.now(),
      photo_uri: photoUri, ocr_status: 'processing', upload_status: 'pending',
      page_number: book.current_page || undefined, chapter: book.current_chapter || undefined,
    });
    setRefreshKey(k => k + 1);

    // Enqueue for background upload — returns immediately
    await enqueuePhotoUpload({
      captureId, photoUri,
      bookId: book.id, bookTitle: book.title,
      chapter: book.current_chapter || undefined,
      pageNumber: book.current_page || undefined,
    });
  };

  const handleTextNote = async () => {
    if (!textNoteInput.trim()) return;
    await addBookCapture({
      id: generateCaptureId(), book_id: book.id, type: 'text_note', created_at: Date.now(),
      text: textNoteInput.trim(), upload_status: 'uploaded',
      page_number: book.current_page || undefined, chapter: book.current_chapter || undefined,
    });
    logEvent('book_capture_text_saved', { book_id: book.id });
    setTextNoteInput('');
    setShowTextInput(false);
    setRefreshKey(k => k + 1);
  };

  const handleVoiceStart = async () => {
    try {
      const permission = await Audio.requestPermissionsAsync();
      if (!permission.granted) { Alert.alert('Permission needed', 'Microphone access is required for voice notes.'); return; }
      await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });
      const { recording: rec } = await Audio.Recording.createAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
      recRef.current = rec;
      setVoiceRecording(true);
      setVoiceDuration(0);
      timerRef.current = setInterval(() => setVoiceDuration(d => d + 1), 1000);
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      logEvent('book_capture_voice_start', { book_id: book.id });
    } catch (e) {
      Alert.alert('Recording failed', String(e));
    }
  };

  const handleVoiceStop = async () => {
    if (!recRef.current) return;
    if (timerRef.current) clearInterval(timerRef.current);
    try {
      await recRef.current.stopAndUnloadAsync();
      const uri = recRef.current.getURI();
      recRef.current = null;
      setVoiceRecording(false);
      if (!uri) { Alert.alert('Error', 'No audio file produced'); return; }

      // Copy to stable local path so the temp recording isn't lost
      let localPath = uri;
      if (Platform.OS !== 'web' && documentDirectory) {
        const filename = `voice_${book.id}_${Date.now()}.m4a`;
        localPath = `${documentDirectory}book-voice-notes/${filename}`;
        await makeDirectoryAsync(`${documentDirectory}book-voice-notes/`, { intermediates: true });
        await copyAsync({ from: uri, to: localPath });
      }

      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      setVoiceUploading(true);

      const captureId = generateCaptureId();
      const chapter = book.current_chapter || undefined;
      const pageNumber = book.current_page || undefined;
      await addBookCapture({
        id: captureId, book_id: book.id, type: 'voice_note', created_at: Date.now(),
        audio_uri: localPath, transcription_status: 'processing', upload_status: 'pending',
        page_number: pageNumber, chapter,
      });
      setRefreshKey(k => k + 1);
      logEvent('book_capture_voice_saved', { book_id: book.id, duration_seconds: voiceDuration });

      try {
        const result = await uploadBookVoiceNote(localPath, book.id, book.title, chapter, pageNumber);
        await updateBookCapture(captureId, {
          transcript: result.transcript,
          extracted_ideas: result.extracted_ideas,
          topics: result.topics,
          transcription_status: 'completed',
          upload_status: 'uploaded',
        });
        logEvent('book_capture_voice_transcribed', { book_id: book.id, ideas: result.extracted_ideas?.length || 0 });
      } catch (e: any) {
        await updateBookCapture(captureId, { transcription_status: 'failed', upload_status: 'failed' });
        await savePendingVoice({ localPath, captureId, bookId: book.id, bookTitle: book.title, chapter, pageNumber });
        logEvent('book_capture_voice_failed', { book_id: book.id, error: String(e) });
      }
      setVoiceUploading(false);
      setRefreshKey(k => k + 1);
    } catch (e) {
      setVoiceRecording(false);
      setVoiceUploading(false);
      Alert.alert('Recording error', String(e));
    }
  };

  const handleVoiceCancel = async () => {
    if (timerRef.current) clearInterval(timerRef.current);
    if (recRef.current) {
      try { await recRef.current.stopAndUnloadAsync(); } catch {}
      recRef.current = null;
    }
    setVoiceRecording(false);
    setVoiceDuration(0);
    logEvent('book_capture_voice_cancelled', { book_id: book.id });
  };

  const fmtDuration = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`;

  const needsIdentify = book.title === 'Unidentified Book' || book.title === 'Identifying...';
  const [identifying, setIdentifying] = useState(false);

  const handleReidentify = useCallback(async () => {
    if (!book) return;
    // Try existing photo first
    let uri = book.cover_image_uri;
    if (uri && Platform.OS !== 'web') {
      try {
        const info = await getInfoAsync(uri);
        if (!info.exists) uri = undefined;
      } catch { uri = undefined; }
    }
    // Fall back to camera/picker
    if (!uri) {
      const { status } = await ImagePicker.requestCameraPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Camera permission needed');
        return;
      }
      const result = await ImagePicker.launchCameraAsync({ quality: 0.8 });
      if (result.canceled || !result.assets[0]) return;
      uri = result.assets[0].uri;
      await updatePhysicalBook(book.id, { cover_image_uri: uri });
    }
    setIdentifying(true);
    try {
      const result = await identifyBookCover(uri);
      await updatePhysicalBook(book.id, {
        title: result.title || 'Unknown Book',
        author: result.author || '',
        cover_url: result.cover_url,
        isbn: result.isbn || undefined,
        publisher: result.publisher || undefined,
        year: result.year || undefined,
        page_count: result.page_count || undefined,
        topics: result.topics || [],
        chapters: result.chapters || [],
        processing_status: 'ready',
      });
      logEvent('book_reidentify_success', { book_id: book.id, title: result.title });
    } catch (e: any) {
      Alert.alert('Identification failed', 'Could not reach the server. Try again later.');
      logEvent('book_reidentify_failed', { book_id: book.id, error: e.message });
    } finally {
      setIdentifying(false);
      setRefreshKey(k => k + 1);
    }
  }, [book]);

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
    <ScrollView style={styles.container} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
      <Pressable style={styles.backButton} onPress={() => router.back()}>
        <Text style={styles.backText}>{'\u2039'} Library</Text>
      </Pressable>

      {/* Book header */}
      <View style={styles.bookHeader}>
        {coverUri ? <Image source={{ uri: coverUri }} style={styles.headerCover} /> : (
          <View style={[styles.headerCover, styles.headerCoverPlaceholder]}>
            <Text style={styles.coverInitial}>{book.title.charAt(0)}</Text>
          </View>
        )}
        <View style={styles.headerInfo}>
          <Text style={styles.bookTitle}>{book.title}</Text>
          <Text style={styles.bookAuthor}>{book.author}</Text>
          {needsIdentify && (
            <Pressable
              style={styles.reidentifyButton}
              onPress={handleReidentify}
              disabled={identifying}
            >
              {identifying
                ? <ActivityIndicator size="small" color={colors.rubric} />
                : <Text style={styles.reidentifyText}>{'\u2726'} Re-identify book</Text>
              }
            </Pressable>
          )}
          {book.topics.length > 0 && (
            <View style={styles.topicRow}>
              {book.topics.map((t: string) => <Text key={t} style={styles.topicTag}>{t}</Text>)}
            </View>
          )}
          {progress > 0 && (
            <View style={styles.progressInfo}>
              <View style={styles.progressTrack}>
                <View style={[styles.progressFill, { width: `${progress}%` as any }]} />
              </View>
              <Text style={styles.progressText}>{progress}% complete</Text>
            </View>
          )}
          <View style={styles.statusRow}>
            {(['reading', 'paused', 'finished', 'archived'] as const).map(s => (
              <Pressable
                key={s}
                style={[styles.statusPill, book.reading_status === s && styles.statusPillActive]}
                onPress={async () => {
                  const updates: Partial<typeof book> = { reading_status: s };
                  if (s === 'finished') {
                    updates.finished_date = new Date().toISOString();
                  }
                  await updatePhysicalBook(book.id, updates);
                  logEvent('book_status_changed', { book_id: book.id, status: s });
                  if (s === 'archived') {
                    router.back();
                    return;
                  }
                  setRefreshKey(k => k + 1);
                }}
              >
                <Text style={[styles.statusPillText, book.reading_status === s && styles.statusPillTextActive]}>
                  {s === 'reading' ? 'Reading' : s === 'paused' ? 'Paused' : s === 'finished' ? 'Finished' : 'Archive'}
                </Text>
              </Pressable>
            ))}
          </View>
          <View style={styles.significanceRow}>
            {(['skimmed', 'read', 'essential'] as const).map(s => (
              <Pressable
                key={s}
                style={[styles.significancePill, (book.significance || 'read') === s && styles.significancePillActive]}
                onPress={async () => {
                  await updatePhysicalBook(book.id, { significance: s });
                  logEvent('book_significance_changed', { book_id: book.id, significance: s });
                  setRefreshKey(k => k + 1);
                }}
              >
                <Text style={[styles.significancePillText, (book.significance || 'read') === s && styles.significancePillTextActive]}>
                  {s === 'skimmed' ? 'Skimmed' : s === 'read' ? 'Read' : 'Essential'}
                </Text>
              </Pressable>
            ))}
          </View>
        </View>
      </View>
      <DoubleRule />

      {/* Reading position */}
      <View style={styles.positionSection}>
        <Text style={styles.sectionLabel}>{'\u2726'} Reading position</Text>
        {book.chapters.length > 0 && (
          <>
            <View style={styles.positionRow}>
              <Text style={styles.fieldLabel}>Chapter</Text>
              <Pressable style={styles.dropdown} onPress={() => setChapterDropdownOpen(!chapterDropdownOpen)}>
                <Text style={styles.dropdownText} numberOfLines={1}>{selectedChapter || 'Select chapter...'}</Text>
                <Text style={styles.dropdownArrow}>{chapterDropdownOpen ? '\u25B4' : '\u25BE'}</Text>
              </Pressable>
            </View>
            {chapterDropdownOpen && (
              <View style={styles.dropdownList}>
                {book.chapters.map((ch) => (
                  <Pressable key={ch.number} style={[styles.dropdownItem, selectedChapter === `Ch ${ch.number}: ${ch.title}` && styles.dropdownItemActive]}
                    onPress={() => handleChapterSelect(ch)}>
                    <Text style={styles.dropdownItemNumber}>{ch.number}</Text>
                    <Text style={styles.dropdownItemTitle}>{ch.title}</Text>
                    {ch.start_page != null && <Text style={styles.dropdownItemPage}>p. {ch.start_page}</Text>}
                  </Pressable>
                ))}
              </View>
            )}
            {selectedChapter && !chapterDropdownOpen && (
              <View style={styles.chapterActions}>
                <Pressable
                  style={styles.chapterActionBtn}
                  onPress={() => {
                    setChapterContextMode('preview');
                    logEvent('chapter_context_open', { book_id: book.id, mode: 'preview', chapter: selectedChapter });
                  }}
                >
                  <Text style={styles.chapterActionText}>Preview this chapter</Text>
                </Pressable>
                <Pressable
                  style={styles.chapterActionBtn}
                  onPress={() => {
                    setChapterContextMode('review');
                    logEvent('chapter_context_open', { book_id: book.id, mode: 'review', chapter: selectedChapter });
                  }}
                >
                  <Text style={styles.chapterActionText}>Review this chapter</Text>
                </Pressable>
                <Pressable
                  style={styles.chapterActionBtn}
                  onPress={() => {
                    const chNum = selectedChapter.replace(/^Ch (\d+):.*/, '$1');
                    const chTitle = selectedChapter.replace(/^Ch \d+:\s*/, '');
                    logEvent('chapter_recall_from_book', { book_id: book.id, chapter: chNum });
                    router.push({
                      pathname: '/voice-elicitation',
                      params: {
                        chapter_recall: '1',
                        book_id: book.id,
                        book_title: book.title,
                        chapter_number: chNum,
                        chapter_title: chTitle,
                        domain_id: '',
                      },
                    } as any);
                  }}
                >
                  <Text style={styles.chapterActionText}>{'\u25CE'} Recall this chapter</Text>
                </Pressable>
              </View>
            )}
          </>
        )}
        {chapterCompleteText && (
          <View style={{ backgroundColor: '#2a7a4a15', borderLeftWidth: 2, borderLeftColor: '#2a7a4a', padding: 10, marginBottom: 8, borderRadius: 3 }}>
            <Text style={{ fontFamily: 'DMSans_400Regular', fontSize: 12, color: '#2a7a4a' }}>
              {'\u2726'} {chapterCompleteText}
            </Text>
          </View>
        )}
        {reviewDueCount > 0 && (
          <Pressable onPress={() => router.push('/(tabs)')} style={styles.reviewBadge}>
            <Text style={styles.reviewBadgeText}>
              {'\u2726'} {reviewDueCount} review item{reviewDueCount !== 1 ? 's' : ''} due
            </Text>
          </Pressable>
        )}
        <Pressable
          style={styles.bookRecallBtn}
          onPress={() => {
            logEvent('book_recall', { book_id: book.id, title: book.title });
            router.push({
              pathname: '/voice-elicitation',
              params: {
                book_id: book.id,
                book_title: book.title,
                domain_id: '',
                book_recall: '1',
              },
            } as any);
          }}
        >
          <Text style={styles.bookRecallBtnText}>{'\u25CE'} Record what I remember</Text>
        </Pressable>
        <View style={styles.positionRow}>
          <Text style={styles.fieldLabel}>Page</Text>
          <TextInput style={styles.pageInput} value={pageInput} onChangeText={setPageInput}
            keyboardType="numeric" placeholder="Page #" placeholderTextColor={colors.textMuted}
            onBlur={handlePageUpdate} onSubmitEditing={handlePageUpdate} />
          {book.page_count ? <Text style={styles.pageTotal}>/ {book.page_count}</Text> : null}
        </View>
      </View>

      {/* Capture bar */}
      <View style={styles.captureSection}>
        <Text style={styles.sectionLabel}>{'\u2726'} Capture</Text>
        {(processing || voiceUploading) && (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <ActivityIndicator size="small" color={colors.rubric} />
            <Text style={styles.processingText}>{voiceUploading ? 'Transcribing voice note…' : 'Processing…'}</Text>
          </View>
        )}
        {voiceRecording ? (
          <View style={styles.voiceBar}>
            <View style={styles.voicePulseDot} />
            <Text style={styles.voiceTimer}>{fmtDuration(voiceDuration)}</Text>
            <View style={{ flex: 1 }} />
            <Pressable style={styles.voiceCancelBtn} onPress={handleVoiceCancel}>
              <Text style={styles.voiceCancelText}>Cancel</Text>
            </Pressable>
            <Pressable style={styles.voiceSendBtn} onPress={handleVoiceStop}>
              <Text style={styles.voiceSendText}>Done</Text>
            </Pressable>
          </View>
        ) : (
          <View style={styles.captureBar}>
            <Pressable style={styles.captureButton} onPress={handleVoiceStart}>
              <Text style={styles.captureIcon}>🎙</Text>
              <Text style={styles.captureLabel}>Voice</Text>
            </Pressable>
            <Pressable style={styles.captureButton} onPress={handlePhotoCapture}>
              <Text style={styles.captureIcon}>📷</Text>
              <Text style={styles.captureLabel}>Photo</Text>
            </Pressable>
            <Pressable style={styles.captureButton} onPress={() => setShowTextInput(!showTextInput)}>
              <Text style={styles.captureIcon}>✎</Text>
              <Text style={styles.captureLabel}>Text</Text>
            </Pressable>
          </View>
        )}
        {showTextInput && (
          <View style={styles.textNoteArea}>
            <TextInput style={styles.textNoteInput} value={textNoteInput} onChangeText={setTextNoteInput}
              placeholder="Type a note about what you're reading..." placeholderTextColor={colors.textMuted}
              multiline numberOfLines={3} />
            <Pressable style={[styles.saveNoteButton, !textNoteInput.trim() && { opacity: 0.4 }]} onPress={handleTextNote}>
              <Text style={styles.saveNoteText}>Save Note</Text>
            </Pressable>
          </View>
        )}
      </View>

      {/* Research: thesis + manual kickoff (always visible so Generate / Regenerate are reachable) */}
      <View style={styles.researchSection}>
        <View style={styles.researchSectionHeader}>
          <Text style={styles.sectionLabel}>{'\u2726'} About this book</Text>
          {hasResearchThesis && !researchBusy ? (
            <Pressable onPress={handleRegenerateResearch} hitSlop={10}>
              <Text style={styles.regenerateLink}>Wrong? Regenerate</Text>
            </Pressable>
          ) : null}
          {!hasResearchThesis && !researchBusy ? (
            <Pressable onPress={handleKickoffResearch} hitSlop={10}>
              <Text style={styles.regenerateLink}>Generate summary</Text>
            </Pressable>
          ) : null}
        </View>
        {researchBusy ? (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 8 }}>
            <ActivityIndicator size="small" color={colors.rubric} />
            <Text style={styles.researchLoadingText}>
              {researchRegenerating ? 'Regenerating summary…' : 'Researching this book…'}
            </Text>
          </View>
        ) : hasResearchThesis && research ? (
          <>
            <Text style={styles.thesisText}>{research.thesis}</Text>
            {research.reception ? <Text style={styles.receptionText}>{research.reception}</Text> : null}
          </>
        ) : (
          <Text style={styles.researchEmptyHint}>
            No AI summary yet. The server uses Gemini with search; tap Generate summary to run or retry (may take a few minutes).
          </Text>
        )}
      </View>

      {/* Research: Article connections */}
      {research?.article_connections && research.article_connections.length > 0 && (
        <View style={styles.researchSection}>
          <Text style={styles.sectionLabel}>{'\u2726'} Connections to your reading</Text>
          {research.article_connections.slice(0, 5).map((conn: BookArticleConnection, i: number) => (
            <View key={i} style={styles.connectionCard}>
              <View style={styles.connectionHeader}>
                <View style={[styles.connectionBadge, conn.connection_type === 'contradicts' ? styles.badgeContradicts : conn.connection_type === 'extends' ? styles.badgeExtends : styles.badgeComplements]} />
                <Text style={styles.connectionType}>{conn.connection_type}</Text>
              </View>
              <Text style={styles.connectionTitle}>{conn.article_title}</Text>
              <Text style={styles.connectionReason}>{conn.reason}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Research: Suggested reading */}
      {research?.suggested_reading && research.suggested_reading.length > 0 && (
        <View style={styles.researchSection}>
          <Text style={styles.sectionLabel}>{'\u2726'} Suggested reading</Text>
          {research.suggested_reading.slice(0, 5).map((s: SuggestedReading, i: number) => (
            <Pressable key={i} style={styles.suggestedCard} onPress={() => {
              logEvent('suggested_reading_tapped', { book_id: book.id, title: s.title, url: s.url });
            }}>
              <Text style={styles.suggestedTitle}>{s.title}</Text>
              {s.author ? <Text style={styles.suggestedAuthor}>{s.author}</Text> : null}
              <Text style={styles.suggestedReason}>{s.reason}</Text>
            </Pressable>
          ))}
        </View>
      )}

      {/* Curriculum context */}
      <BookCurriculumContext
        bookId={book.id}
        bookTitle={book.title}
        currentChapter={book.current_chapter || undefined}
      />

      {/* Deep review for finished books */}
      {book.reading_status === 'finished' && (
        <View style={styles.hamarquizenSection}>
          <Pressable
            style={styles.hamarquizenBtn}
            onPress={() => {
              logEvent('book_review_started', { book_id: book.id, title: book.title });
              router.push(`/hamarquizen?book_id=${book.id}` as any);
            }}
          >
            <Text style={styles.hamarquizenBtnText}>{'\u2726'} Book Review</Text>
            <Text style={styles.hamarquizenSubtext}>PRIME {'\u2192'} READ {'\u2192'} TEST micro-lessons</Text>
          </Pressable>
        </View>
      )}

      {/* Capture timeline */}
      <View style={styles.timelineSection}>
        <Text style={styles.sectionLabel}>{'\u2726'} Notes & captures</Text>
        {captures.length === 0 ? (
          <Text style={styles.emptyCaptures}>No captures yet — use the buttons above to start</Text>
        ) : (
          <>
            <Text style={styles.captureCount}>{captures.length} capture{captures.length !== 1 ? 's' : ''}</Text>
            {captures.map(c => <CaptureCard key={c.id} capture={c} />)}
          </>
        )}
      </View>

      {/* Story So Far overlay */}
      {showStorySoFar && storySoFar && (
        <View style={styles.storySoFarOverlay}>
          <View style={styles.storySoFarCard}>
            <Text style={styles.storySoFarTitle}>Welcome back to {book.title}</Text>
            <Text style={styles.storySoFarMeta}>Last read: {formatTimeAgo(book.last_interaction_at)}</Text>
            <View style={styles.storySoFarDivider} />
            <Text style={styles.storySoFarSummary}>{storySoFar.argument_summary}</Text>
            {storySoFar.highlights?.map((h, i) => (
              <View key={i} style={styles.storySoFarHighlight}>
                <Text style={styles.storySoFarHighlightText}>{h.text}</Text>
                <Text style={styles.storySoFarHighlightWhy}>{h.why_it_matters}</Text>
              </View>
            ))}
            {storySoFar.preview ? <Text style={styles.storySoFarPreview}>Coming up: {storySoFar.preview}</Text> : null}
            <Pressable style={styles.storySoFarDismiss} onPress={() => {
              setShowStorySoFar(false);
              logEvent('story_so_far_resume_tapped', { book_id: book.id });
            }}>
              <Text style={styles.storySoFarDismissText}>Resume reading {'\u2192'}</Text>
            </Pressable>
          </View>
        </View>
      )}

      {/* Chapter context modal (preview / review) */}
      {chapterContextMode && selectedChapter && (() => {
        const match = selectedChapter.match(/^Ch (\d+):\s*(.*)$/);
        const chNum = match ? parseInt(match[1], 10) : 0;
        const chTitle = match ? match[2] : selectedChapter;
        return (
          <ChapterContext
            bookId={book.id}
            chapterNumber={chNum}
            chapterTitle={chTitle}
            mode={chapterContextMode}
            visible
            onClose={() => setChapterContextMode(null)}
          />
        );
      })()}
    </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.parchment },
  content: { paddingBottom: 60, ...(Platform.OS === 'web' ? { maxWidth: layout.readingMeasure + 2 * layout.screenPadding, width: '100%', alignSelf: 'center' as const } : {}) },
  errorText: { fontFamily: fonts.reading, fontSize: 16, color: colors.textSecondary, padding: 40, textAlign: 'center' },
  backButton: { paddingHorizontal: layout.screenPadding, paddingTop: 12, paddingBottom: 8 },
  backText: { fontFamily: fonts.body, fontSize: 14, color: colors.rubric },
  bookHeader: { flexDirection: 'row', paddingHorizontal: layout.screenPadding, paddingBottom: 16, gap: 18 },
  headerCover: { width: 80, height: 112, borderRadius: 3 },
  headerCoverPlaceholder: { backgroundColor: colors.parchmentDark, borderWidth: 1, borderColor: colors.rule, alignItems: 'center', justifyContent: 'center' },
  coverInitial: { fontFamily: fonts.displaySemiBold, fontSize: 32, color: colors.textMuted, ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}) },
  headerInfo: { flex: 1 },
  bookTitle: { fontFamily: fonts.displaySemiBold, fontSize: 22, lineHeight: 27, color: colors.ink, marginBottom: 4, ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}) },
  bookAuthor: { fontFamily: fonts.readingItalic, fontSize: 15, color: colors.textSecondary, marginBottom: 8, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  reidentifyButton: { paddingVertical: 6, paddingHorizontal: 10, borderWidth: 1, borderColor: colors.rubric, borderRadius: 3, alignSelf: 'flex-start', marginBottom: 8 },
  reidentifyText: { fontFamily: fonts.ui, fontSize: 12, color: colors.rubric },
  topicRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 8 },
  topicTag: { fontFamily: fonts.bodyItalic, fontSize: 11, color: colors.rubric, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  progressInfo: { marginTop: 4 },
  progressTrack: { height: 3, backgroundColor: colors.rule, borderRadius: 1.5, overflow: 'hidden', marginBottom: 4 },
  progressFill: { height: '100%', backgroundColor: colors.rubric, borderRadius: 1.5 },
  progressText: { fontFamily: fonts.ui, fontSize: 10, color: colors.textMuted },
  statusRow: { flexDirection: 'row', gap: 6, marginTop: 8 },
  statusPill: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12, borderWidth: 1, borderColor: colors.rule },
  statusPillActive: { borderColor: colors.rubric, backgroundColor: 'rgba(139,37,0,0.06)' },
  statusPillText: { fontFamily: fonts.ui, fontSize: 10, color: colors.textMuted, letterSpacing: 0.3 },
  statusPillTextActive: { color: colors.rubric },
  significanceRow: { flexDirection: 'row', gap: 6, marginTop: 6 },
  significancePill: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12, borderWidth: 1, borderColor: colors.rule },
  significancePillActive: { borderColor: colors.ink, backgroundColor: 'rgba(42,36,32,0.06)' },
  significancePillText: { fontFamily: fonts.ui, fontSize: 10, color: colors.textMuted, letterSpacing: 0.3 },
  significancePillTextActive: { color: colors.ink },
  positionSection: { paddingHorizontal: layout.screenPadding, paddingTop: 18, paddingBottom: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.rule },
  sectionLabel: { fontFamily: fonts.bodyItalic, fontSize: 12, color: colors.rubric, marginBottom: 12, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  positionRow: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 10 },
  fieldLabel: { fontFamily: fonts.uiMedium, fontSize: 11, color: colors.textSecondary, letterSpacing: 0.5, textTransform: 'uppercase', width: 60, ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}) },
  dropdown: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', borderWidth: 1, borderColor: colors.rule, borderRadius: 3, paddingVertical: 10, paddingHorizontal: 12 },
  dropdownText: { fontFamily: fonts.reading, fontSize: 14, color: colors.textBody, flex: 1 },
  dropdownArrow: { fontFamily: fonts.ui, fontSize: 12, color: colors.textMuted, marginLeft: 8 },
  dropdownList: { borderWidth: 1, borderColor: colors.rule, borderRadius: 3, marginBottom: 12, marginLeft: 72, backgroundColor: colors.parchment, ...(Platform.OS === 'web' ? { maxHeight: 300, overflow: 'scroll' as any } : {}) },
  dropdownItem: { flexDirection: 'row', alignItems: 'center', paddingVertical: 10, paddingHorizontal: 12, gap: 10, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.rule },
  dropdownItemActive: { backgroundColor: 'rgba(139,37,0,0.04)' },
  dropdownItemNumber: { fontFamily: fonts.displaySemiBold, fontSize: 16, color: colors.textMuted, width: 24, textAlign: 'center', ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}) },
  dropdownItemTitle: { flex: 1, fontFamily: fonts.reading, fontSize: 14, color: colors.textBody },
  dropdownItemPage: { fontFamily: fonts.ui, fontSize: 10, color: colors.textMuted },
  pageInput: { borderWidth: 1, borderColor: colors.rule, borderRadius: 3, paddingVertical: 10, paddingHorizontal: 12, fontFamily: fonts.reading, fontSize: 14, color: colors.textBody, width: 80, textAlign: 'center' },
  pageTotal: { fontFamily: fonts.ui, fontSize: 13, color: colors.textMuted },
  captureSection: { paddingHorizontal: layout.screenPadding, paddingTop: 18, paddingBottom: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.rule },
  captureBar: { flexDirection: 'row', gap: 10 },
  captureButton: { flex: 1, alignItems: 'center', paddingVertical: 16, backgroundColor: colors.parchmentDark, borderRadius: 4, borderWidth: 1, borderColor: colors.rule, gap: 4 },
  captureIcon: { fontSize: 22 },
  captureLabel: { fontFamily: fonts.uiMedium, fontSize: 11, color: colors.ink, letterSpacing: 0.3, ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}) },
  processingText: { fontFamily: fonts.readingItalic, fontSize: 13, color: colors.textMuted, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  voiceBar: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 14, paddingHorizontal: 16, backgroundColor: colors.parchmentDark, borderRadius: 4, borderWidth: 1, borderColor: colors.rubric },
  voicePulseDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.rubric },
  voiceTimer: { fontFamily: fonts.display, fontSize: 24, color: colors.ink },
  voiceCancelBtn: { paddingHorizontal: 14, paddingVertical: 8 },
  voiceCancelText: { fontFamily: fonts.ui, fontSize: 13, color: colors.textMuted },
  voiceSendBtn: { backgroundColor: colors.rubric, paddingHorizontal: 18, paddingVertical: 10, borderRadius: 20 },
  voiceSendText: { fontFamily: fonts.uiMedium, fontSize: 13, color: colors.parchment, ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}) },
  textNoteArea: { marginTop: 12, gap: 8 },
  textNoteInput: { borderWidth: 1, borderColor: colors.rule, borderRadius: 3, paddingVertical: 10, paddingHorizontal: 12, fontFamily: fonts.reading, fontSize: 14, color: colors.textBody, minHeight: 80, textAlignVertical: 'top' },
  saveNoteButton: { backgroundColor: colors.ink, paddingVertical: 10, borderRadius: 3, alignItems: 'center' },
  saveNoteText: { fontFamily: fonts.body, fontSize: 13, color: colors.parchment },
  timelineSection: { paddingHorizontal: layout.screenPadding, paddingTop: 18 },
  captureCount: { fontFamily: fonts.ui, fontSize: 11, color: colors.textMuted, marginBottom: 4 },
  emptyCaptures: { fontFamily: fonts.readingItalic, fontSize: 14, color: colors.textMuted, paddingVertical: 20, textAlign: 'center', ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  // Research sections
  researchSection: { paddingHorizontal: layout.screenPadding, paddingTop: 18, paddingBottom: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.rule },
  researchSectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    marginBottom: 4,
  },
  regenerateLink: {
    fontFamily: fonts.ui,
    fontSize: 12,
    color: colors.rubric,
    textDecorationLine: 'underline',
  },
  researchEmptyHint: {
    fontFamily: fonts.reading,
    fontSize: 14,
    lineHeight: 21,
    color: colors.textMuted,
    marginTop: 8,
  },
  researchLoadingText: { fontFamily: fonts.readingItalic, fontSize: 13, color: colors.textMuted, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  thesisText: { fontFamily: fonts.reading, fontSize: 15, lineHeight: 22, color: colors.textBody, marginBottom: 8 },
  receptionText: { fontFamily: fonts.readingItalic, fontSize: 13, lineHeight: 19, color: colors.textSecondary, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  // Connections
  connectionCard: { paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.rule },
  connectionHeader: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 },
  connectionBadge: { width: 8, height: 8, borderRadius: 4 },
  badgeExtends: { backgroundColor: colors.claimNew },
  badgeContradicts: { backgroundColor: colors.rubric },
  badgeComplements: { backgroundColor: colors.textMuted },
  connectionType: { fontFamily: fonts.uiMedium, fontSize: 10, letterSpacing: 0.5, textTransform: 'uppercase', color: colors.textMuted, ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}) },
  connectionTitle: { fontFamily: fonts.body, fontSize: 14, color: colors.ink, marginBottom: 2 },
  connectionReason: { fontFamily: fonts.reading, fontSize: 13, lineHeight: 19, color: colors.textSecondary },
  // Suggested reading
  suggestedCard: { paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.rule },
  suggestedTitle: { fontFamily: fonts.body, fontSize: 14, color: colors.rubric, marginBottom: 2 },
  suggestedAuthor: { fontFamily: fonts.readingItalic, fontSize: 12, color: colors.textMuted, marginBottom: 4, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  suggestedReason: { fontFamily: fonts.reading, fontSize: 13, lineHeight: 19, color: colors.textSecondary },
  // Story So Far
  storySoFarOverlay: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(42,36,32,0.6)', justifyContent: 'center', alignItems: 'center', paddingHorizontal: 20, zIndex: 100 },
  storySoFarCard: { backgroundColor: colors.parchment, borderRadius: 8, padding: 24, maxWidth: 500, width: '100%', ...(Platform.OS === 'web' ? { maxHeight: '80vh' as any, overflow: 'auto' as any } : {}) },
  storySoFarTitle: { fontFamily: fonts.displaySemiBold, fontSize: 20, color: colors.ink, marginBottom: 4, ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}) },
  storySoFarMeta: { fontFamily: fonts.ui, fontSize: 11, color: colors.textMuted, marginBottom: 12 },
  storySoFarDivider: { height: 2, backgroundColor: colors.rubric, marginBottom: 2, width: 40 },
  storySoFarSummary: { fontFamily: fonts.reading, fontSize: 15, lineHeight: 22, color: colors.textBody, marginTop: 12, marginBottom: 16 },
  storySoFarHighlight: { borderLeftWidth: 2, borderLeftColor: colors.rubric, paddingLeft: 12, marginBottom: 12 },
  storySoFarHighlightText: { fontFamily: fonts.reading, fontSize: 14, lineHeight: 20, color: colors.textBody, marginBottom: 4 },
  storySoFarHighlightWhy: { fontFamily: fonts.readingItalic, fontSize: 12, lineHeight: 18, color: colors.textSecondary, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  storySoFarPreview: { fontFamily: fonts.readingItalic, fontSize: 13, lineHeight: 19, color: colors.textMuted, marginBottom: 16, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  storySoFarDismiss: { backgroundColor: colors.ink, paddingVertical: 12, borderRadius: 4, alignItems: 'center' },
  storySoFarDismissText: { fontFamily: fonts.body, fontSize: 14, color: colors.parchment },
  reviewBadge: { borderLeftWidth: 2, borderLeftColor: colors.rubric, paddingLeft: 10, paddingVertical: 8, marginTop: 4 },
  reviewBadgeText: { fontFamily: fonts.ui, fontSize: 13, color: colors.rubric },
  bookRecallBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    paddingVertical: 10, marginTop: 8, marginBottom: 4,
    borderWidth: 1, borderColor: colors.rubric, borderRadius: 4,
  },
  bookRecallBtnText: { fontFamily: fonts.ui, fontSize: 13, fontWeight: '500', color: colors.rubric },
  chapterActions: { flexDirection: 'row', gap: 10, marginTop: 4, marginBottom: 8, marginLeft: 72 },
  chapterActionBtn: { paddingVertical: 6, paddingHorizontal: 10, borderWidth: 1, borderColor: colors.rubric, borderRadius: 3 },
  chapterActionText: { fontFamily: fonts.ui, fontSize: 11, color: colors.rubric },
  // Hamarquizen
  hamarquizenSection: { paddingHorizontal: layout.screenPadding, paddingTop: 18, paddingBottom: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.rule },
  hamarquizenBtn: { backgroundColor: colors.ink, paddingVertical: 14, paddingHorizontal: 16, borderRadius: 4, alignItems: 'center' },
  hamarquizenBtnText: { fontFamily: fonts.body, fontSize: 15, color: colors.parchment },
  hamarquizenSubtext: { fontFamily: fonts.ui, fontSize: 10, color: 'rgba(247,244,236,0.5)', marginTop: 3, letterSpacing: 0.5 },
});
