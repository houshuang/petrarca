import { useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, Image, Platform, TextInput,
  ActivityIndicator, Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import { logEvent } from '../data/logger';
import { addPhysicalBook, generateBookId } from '../data/book-store';
import { identifyBookCover } from '../lib/book-api';
import type { PhysicalBook, PhysicalBookChapter } from '../data/types';
import { colors, fonts, type, layout } from '../design/tokens';
import DoubleRule from '../components/DoubleRule';

type Step = 'capture' | 'identifying' | 'confirm';

export default function AddBookScreen() {
  const router = useRouter();
  const [step, setStep] = useState<Step>('capture');
  const [title, setTitle] = useState('');
  const [author, setAuthor] = useState('');
  const [coverUrl, setCoverUrl] = useState<string | undefined>();
  const [coverPhotoUri, setCoverPhotoUri] = useState<string | undefined>();
  const [isbn, setIsbn] = useState<string | undefined>();
  const [publisher, setPublisher] = useState<string | undefined>();
  const [year, setYear] = useState<number | undefined>();
  const [pageCount, setPageCount] = useState<string>('');
  const [topics, setTopics] = useState<string[]>([]);
  const [chapters, setChapters] = useState<PhysicalBookChapter[]>([]);
  const [error, setError] = useState('');
  const [editMode, setEditMode] = useState(false);

  const takePhoto = useCallback(async () => {
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Camera permission needed', 'Please allow camera access to photograph book covers.');
      return undefined;
    }
    const result = await ImagePicker.launchCameraAsync({ quality: 0.8, allowsEditing: false });
    if (!result.canceled && result.assets[0]) return result.assets[0].uri;
    return undefined;
  }, []);

  const pickFromLibrary = useCallback(async () => {
    const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: 'images', quality: 0.8 });
    if (!result.canceled && result.assets[0]) return result.assets[0].uri;
    return undefined;
  }, []);

  const identifyFromPhoto = useCallback(async (photoUri: string) => {
    setCoverPhotoUri(photoUri);
    setStep('identifying');
    setError('');
    logEvent('book_add_photo_taken');

    try {
      const result = await identifyBookCover(photoUri);
      setTitle(result.title || '');
      setAuthor(result.author || '');
      setCoverUrl(result.cover_url);
      setIsbn(result.isbn || undefined);
      setPublisher(result.publisher || undefined);
      setYear(result.year || undefined);
      setPageCount(result.page_count?.toString() || '');
      setTopics(result.topics || []);
      setChapters(result.chapters || []);
      setStep('confirm');
      logEvent('book_add_identified', { title: result.title });
    } catch (e: any) {
      setError(e.message || 'Failed to identify book');
      setStep('capture');
      logEvent('book_add_identify_failed', { error: e.message });
    }
  }, []);

  const handleCapture = useCallback(async (source: 'camera' | 'library') => {
    const uri = source === 'camera' ? await takePhoto() : await pickFromLibrary();
    if (uri) await identifyFromPhoto(uri);
  }, [takePhoto, pickFromLibrary, identifyFromPhoto]);

  const handleSave = useCallback(async () => {
    if (!title.trim()) {
      setError('Title is required');
      return;
    }
    const book: PhysicalBook = {
      id: generateBookId(),
      title: title.trim(),
      author: author.trim(),
      cover_url: coverUrl,
      cover_image_uri: coverPhotoUri,
      isbn,
      publisher,
      year,
      page_count: pageCount ? parseInt(pageCount, 10) : undefined,
      language: 'en',
      topics,
      chapters,
      reading_status: 'reading',
      added_at: Date.now(),
      last_interaction_at: Date.now(),
      metadata_source: editMode ? 'manual' : 'photo',
    };
    await addPhysicalBook(book);
    logEvent('book_add_confirmed', { book_id: book.id, title: book.title });
    router.back();
  }, [title, author, coverUrl, coverPhotoUri, isbn, publisher, year, pageCount, topics, chapters, editMode, router]);

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
      <Pressable style={styles.backButton} onPress={() => router.back()}>
        <Text style={styles.backText}>{'\u2039'} Cancel</Text>
      </Pressable>
      <View style={styles.headerSection}>
        <Text style={styles.screenTitle}>Add Book</Text>
        <Text style={styles.screenSubtitle}>Photograph the cover or title page</Text>
      </View>
      <DoubleRule />

      {error ? (
        <View style={styles.errorBanner}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      ) : null}

      {/* Step 1: Capture */}
      {step === 'capture' && (
        <View style={styles.captureStep}>
          <View style={styles.cameraPlaceholder}>
            <Text style={styles.cameraIcon}>{'\u2726'}</Text>
            <Text style={styles.cameraLabel}>Photograph the cover</Text>
            <Text style={styles.cameraHint}>We'll identify the book and find metadata automatically</Text>
          </View>
          <View style={styles.captureActions}>
            <Pressable style={styles.primaryButton} onPress={() => handleCapture('camera')}>
              <Text style={styles.primaryButtonText}>Take Photo</Text>
            </Pressable>
            <Pressable style={styles.secondaryButton} onPress={() => handleCapture('library')}>
              <Text style={styles.secondaryButtonText}>Choose from Photos</Text>
            </Pressable>
          </View>
          <View style={styles.dividerRow}>
            <View style={styles.dividerLine} />
            <Text style={styles.dividerText}>or</Text>
            <View style={styles.dividerLine} />
          </View>
          <Pressable style={styles.manualEntry} onPress={() => { setStep('confirm'); setEditMode(true); logEvent('book_add_manual_entry'); }}>
            <Text style={styles.manualEntryText}>Enter details manually</Text>
          </Pressable>
        </View>
      )}

      {/* Step 2: Identifying */}
      {step === 'identifying' && (
        <View style={styles.identifyingStep}>
          <ActivityIndicator size="large" color={colors.rubric} />
          <Text style={styles.identifyingText}>Identifying book...</Text>
          <Text style={styles.identifyingSubtext}>Analyzing image, searching for metadata and cover</Text>
        </View>
      )}

      {/* Step 3: Confirm */}
      {step === 'confirm' && (
        <View style={styles.confirmStep}>
          <View style={styles.bookCard}>
            {!editMode && coverUrl && (
              <Image source={{ uri: coverUrl }} style={styles.bookCardCover} />
            )}
            <View style={styles.bookCardInfo}>
              {editMode ? (
                <>
                  <Text style={styles.fieldLabel}>Title</Text>
                  <TextInput style={styles.textInput} value={title} onChangeText={setTitle} placeholder="Book title" placeholderTextColor={colors.textMuted} autoFocus />
                  <Text style={[styles.fieldLabel, { marginTop: 12 }]}>Author</Text>
                  <TextInput style={styles.textInput} value={author} onChangeText={setAuthor} placeholder="Author name" placeholderTextColor={colors.textMuted} />
                  <Text style={[styles.fieldLabel, { marginTop: 12 }]}>Pages</Text>
                  <TextInput style={styles.textInput} value={pageCount} onChangeText={setPageCount} placeholder="Total pages" placeholderTextColor={colors.textMuted} keyboardType="numeric" />
                </>
              ) : (
                <>
                  <Text style={styles.bookCardTitle}>{title}</Text>
                  <Text style={styles.bookCardAuthor}>{author}</Text>
                  {(publisher || year) && (
                    <Text style={styles.metaText}>
                      {[publisher, year].filter(Boolean).join(' · ')}
                      {pageCount ? ` · ${pageCount} pages` : ''}
                    </Text>
                  )}
                  {isbn && <Text style={styles.metaText}>ISBN: {isbn}</Text>}
                  {topics.length > 0 && (
                    <View style={styles.topicRow}>
                      {topics.map(t => <Text key={t} style={styles.topicTag}>{t}</Text>)}
                    </View>
                  )}
                </>
              )}
            </View>
          </View>

          {chapters.length > 0 && (
            <View style={styles.tocPreview}>
              <Text style={styles.tocPreviewTitle}>{'\u2726'} {chapters.length} chapters found</Text>
              {chapters.slice(0, 8).map(ch => (
                <View key={ch.number} style={styles.tocRow}>
                  <Text style={styles.tocNumber}>{ch.number}</Text>
                  <Text style={styles.tocChapterTitle}>{ch.title}</Text>
                  {ch.start_page && <Text style={styles.tocPage}>p. {ch.start_page}</Text>}
                </View>
              ))}
              {chapters.length > 8 && <Text style={styles.metaText}>+ {chapters.length - 8} more</Text>}
            </View>
          )}

          {!editMode && (
            <Pressable style={styles.editLink} onPress={() => { setEditMode(true); }}>
              <Text style={styles.editLinkText}>Edit details</Text>
            </Pressable>
          )}

          <View style={styles.confirmActions}>
            <Pressable style={styles.primaryButton} onPress={handleSave}>
              <Text style={styles.primaryButtonText}>Add to Library</Text>
            </Pressable>
          </View>
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.parchment },
  content: { paddingBottom: 60, ...(Platform.OS === 'web' ? { maxWidth: layout.readingMeasure + 2 * layout.screenPadding, width: '100%', alignSelf: 'center' as const } : {}) },
  backButton: { paddingHorizontal: layout.screenPadding, paddingTop: 12, paddingBottom: 8 },
  backText: { fontFamily: fonts.body, fontSize: 14, color: colors.rubric },
  headerSection: { paddingHorizontal: layout.screenPadding, paddingBottom: 12 },
  screenTitle: { ...type.screenTitle, color: colors.ink },
  screenSubtitle: { ...type.screenSubtitle, color: colors.textSecondary, marginTop: 2, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  errorBanner: { backgroundColor: 'rgba(139,37,0,0.08)', paddingVertical: 10, paddingHorizontal: layout.screenPadding, marginTop: 8 },
  errorText: { fontFamily: fonts.ui, fontSize: 13, color: colors.rubric },
  captureStep: { paddingHorizontal: layout.screenPadding, paddingTop: 24 },
  cameraPlaceholder: { height: 280, backgroundColor: colors.parchmentDark, borderWidth: 1, borderColor: colors.rule, borderRadius: 4, borderStyle: 'dashed', alignItems: 'center', justifyContent: 'center', gap: 8, marginBottom: 20 },
  cameraIcon: { fontFamily: fonts.display, fontSize: 36, color: colors.textMuted },
  cameraLabel: { fontFamily: fonts.reading, fontSize: 15, color: colors.textSecondary },
  cameraHint: { fontFamily: fonts.ui, fontSize: 12, color: colors.textMuted, textAlign: 'center', paddingHorizontal: 40 },
  captureActions: { gap: 10, marginBottom: 20 },
  primaryButton: { backgroundColor: colors.ink, paddingVertical: 14, borderRadius: 3, alignItems: 'center' },
  primaryButtonText: { fontFamily: fonts.body, fontSize: 14, color: colors.parchment },
  secondaryButton: { borderWidth: 1, borderColor: colors.rule, paddingVertical: 14, borderRadius: 3, alignItems: 'center' },
  secondaryButtonText: { fontFamily: fonts.body, fontSize: 14, color: colors.ink },
  dividerRow: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 16 },
  dividerLine: { flex: 1, height: StyleSheet.hairlineWidth, backgroundColor: colors.rule },
  dividerText: { fontFamily: fonts.ui, fontSize: 12, color: colors.textMuted },
  manualEntry: { alignItems: 'center', paddingVertical: 10 },
  manualEntryText: { fontFamily: fonts.body, fontSize: 13, color: colors.rubric },
  identifyingStep: { alignItems: 'center', paddingTop: 80, gap: 16 },
  identifyingText: { fontFamily: fonts.displaySemiBold, fontSize: 18, color: colors.ink, ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}) },
  identifyingSubtext: { fontFamily: fonts.reading, fontSize: 14, color: colors.textSecondary },
  confirmStep: { paddingHorizontal: layout.screenPadding, paddingTop: 24 },
  bookCard: { flexDirection: 'row', gap: 18, paddingBottom: 20, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.rule },
  bookCardCover: { width: 100, height: 140, borderRadius: 3 },
  bookCardInfo: { flex: 1 },
  bookCardTitle: { fontFamily: fonts.displaySemiBold, fontSize: 20, lineHeight: 25, color: colors.ink, marginBottom: 4, ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}) },
  bookCardAuthor: { fontFamily: fonts.readingItalic, fontSize: 15, color: colors.textSecondary, marginBottom: 8, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  metaText: { fontFamily: fonts.ui, fontSize: 11, color: colors.textMuted, marginBottom: 2 },
  topicRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 6 },
  topicTag: { fontFamily: fonts.bodyItalic, fontSize: 11, color: colors.rubric, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  fieldLabel: { fontFamily: fonts.uiMedium, fontSize: 11, color: colors.textSecondary, letterSpacing: 0.5, textTransform: 'uppercase', marginBottom: 6, ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}) },
  textInput: { borderWidth: 1, borderColor: colors.rule, borderRadius: 3, paddingVertical: 10, paddingHorizontal: 12, fontFamily: fonts.reading, fontSize: 15, color: colors.textBody, backgroundColor: colors.parchment },
  editLink: { paddingVertical: 10 },
  editLinkText: { fontFamily: fonts.body, fontSize: 13, color: colors.rubric },
  confirmActions: { gap: 10, marginTop: 20 },
  tocPreview: { marginTop: 16, marginBottom: 8 },
  tocPreviewTitle: { fontFamily: fonts.bodyItalic, fontSize: 12, color: colors.rubric, marginBottom: 12, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  tocRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 8, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.rule, gap: 10 },
  tocNumber: { fontFamily: fonts.displaySemiBold, fontSize: 16, color: colors.textMuted, width: 24, textAlign: 'center', ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}) },
  tocChapterTitle: { flex: 1, fontFamily: fonts.reading, fontSize: 14, color: colors.textBody },
  tocPage: { fontFamily: fonts.ui, fontSize: 10, color: colors.textMuted },
});
