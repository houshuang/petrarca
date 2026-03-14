import { useState, useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, Image, Platform, TextInput,
  Alert, ActivityIndicator,
} from 'react-native';
import { useRouter, useLocalSearchParams, useFocusEffect } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import { logEvent } from '../data/logger';
import {
  getPhysicalBook, getBookCaptures, updateReadingPosition,
  addBookCapture, generateCaptureId, updatePhysicalBook, getBookStoreVersion,
} from '../data/book-store';
import { ocrPage, uploadBookVoiceNote } from '../lib/book-api';
import type { PhysicalBook, BookCapture } from '../data/types';
import { colors, fonts, type, layout } from '../design/tokens';
import DoubleRule from '../components/DoubleRule';

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
  const [chapterDropdownOpen, setChapterDropdownOpen] = useState(false);

  useFocusEffect(useCallback(() => { setRefreshKey(k => k + 1); }, []));

  const storeVersion = getBookStoreVersion();
  const book = useMemo(() => id ? getPhysicalBook(id) : undefined, [id, refreshKey, storeVersion]);
  const captures = useMemo(() => id ? getBookCaptures(id) : [], [id, refreshKey, storeVersion]);

  const [pageInput, setPageInput] = useState(book?.current_page?.toString() || '');
  const [selectedChapter, setSelectedChapter] = useState(book?.current_chapter || '');

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

  const handlePageUpdate = async () => {
    const page = parseInt(pageInput, 10);
    if (!isNaN(page) && page > 0) {
      await updateReadingPosition(book.id, page, undefined);
      setRefreshKey(k => k + 1);
    }
  };

  const handleChapterSelect = async (ch: { number: number; title: string }) => {
    const chapterLabel = `Ch ${ch.number}: ${ch.title}`;
    setSelectedChapter(chapterLabel);
    setChapterDropdownOpen(false);
    await updateReadingPosition(book.id, undefined, chapterLabel);
    logEvent('book_chapter_select', { book_id: book.id, chapter: ch.number });
    setRefreshKey(k => k + 1);
  };

  const handlePhotoCapture = async () => {
    const result = await ImagePicker.launchCameraAsync({ quality: 0.8 });
    if (result.canceled || !result.assets[0]) return;
    const photoUri = result.assets[0].uri;
    setProcessing(true);
    logEvent('book_capture_photo_taken', { book_id: book.id });

    const captureId = generateCaptureId();
    // Save capture immediately with pending status
    await addBookCapture({
      id: captureId, book_id: book.id, type: 'page_photo', created_at: Date.now(),
      photo_uri: photoUri, ocr_status: 'processing', upload_status: 'pending',
      page_number: book.current_page || undefined, chapter: book.current_chapter || undefined,
    });
    setRefreshKey(k => k + 1);

    try {
      const ocrResult = await ocrPage(photoUri, book.id, book.title, book.current_page || undefined, book.current_chapter || undefined);
      const { updateBookCapture } = require('../data/book-store');
      await updateBookCapture(captureId, {
        ocr_text: ocrResult.text,
        extracted_ideas: ocrResult.extracted_ideas,
        topics: ocrResult.topics,
        ocr_status: 'completed',
        upload_status: 'uploaded',
        page_number: ocrResult.detected_page_number || book.current_page || undefined,
      });
    } catch (e: any) {
      const { updateBookCapture } = require('../data/book-store');
      await updateBookCapture(captureId, { ocr_status: 'failed', upload_status: 'failed' });
    }
    setProcessing(false);
    setRefreshKey(k => k + 1);
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

  return (
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
          </>
        )}
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
        {processing && <ActivityIndicator size="small" color={colors.rubric} style={{ marginBottom: 8 }} />}
        <View style={styles.captureBar}>
          <Pressable style={styles.captureButton} onPress={() => { logEvent('book_capture_voice_tap', { book_id: book.id }); Alert.alert('Voice notes', 'Voice capture coming soon — use text notes for now.'); }}>
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
    </ScrollView>
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
  topicRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 8 },
  topicTag: { fontFamily: fonts.bodyItalic, fontSize: 11, color: colors.rubric, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  progressInfo: { marginTop: 4 },
  progressTrack: { height: 3, backgroundColor: colors.rule, borderRadius: 1.5, overflow: 'hidden', marginBottom: 4 },
  progressFill: { height: '100%', backgroundColor: colors.rubric, borderRadius: 1.5 },
  progressText: { fontFamily: fonts.ui, fontSize: 10, color: colors.textMuted },
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
  textNoteArea: { marginTop: 12, gap: 8 },
  textNoteInput: { borderWidth: 1, borderColor: colors.rule, borderRadius: 3, paddingVertical: 10, paddingHorizontal: 12, fontFamily: fonts.reading, fontSize: 14, color: colors.textBody, minHeight: 80, textAlignVertical: 'top' },
  saveNoteButton: { backgroundColor: colors.ink, paddingVertical: 10, borderRadius: 3, alignItems: 'center' },
  saveNoteText: { fontFamily: fonts.body, fontSize: 13, color: colors.parchment },
  timelineSection: { paddingHorizontal: layout.screenPadding, paddingTop: 18 },
  captureCount: { fontFamily: fonts.ui, fontSize: 11, color: colors.textMuted, marginBottom: 4 },
  emptyCaptures: { fontFamily: fonts.readingItalic, fontSize: 14, color: colors.textMuted, paddingVertical: 20, textAlign: 'center', ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
});
