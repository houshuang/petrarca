import { useState, useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, Image, Platform,
} from 'react-native';
import { useRouter, useFocusEffect } from 'expo-router';
import { logEvent } from '../../data/logger';
import { getPhysicalBooks, getBookCaptures, getBookStoreVersion } from '../../data/book-store';
import type { PhysicalBook } from '../../data/types';
import { colors, fonts, type, layout } from '../../design/tokens';
import DoubleRule from '../../components/DoubleRule';

function formatTimeAgo(timestamp: number): string {
  const hours = Math.floor((Date.now() - timestamp) / 3600000);
  if (hours < 1) return 'just now';
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return 'yesterday';
  if (days < 7) return `${days}d ago`;
  if (days < 30) return `${Math.floor(days / 7)}w ago`;
  return `${Math.floor(days / 30)}mo ago`;
}

function ProgressBar({ current, total }: { current: number; total: number }) {
  const pct = Math.min(100, Math.round((current / total) * 100));
  return (
    <View style={progressStyles.track}>
      <View style={[progressStyles.fill, { width: `${pct}%` as any }]} />
    </View>
  );
}

const progressStyles = StyleSheet.create({
  track: { height: 3, backgroundColor: colors.rule, borderRadius: 1.5, overflow: 'hidden', marginTop: 8 },
  fill: { height: '100%', backgroundColor: colors.rubric, borderRadius: 1.5 },
});

function BookRow({ book, captureCount, onPress }: { book: PhysicalBook; captureCount: number; onPress: () => void }) {
  const [hovered, setHovered] = useState(false);
  const statusLabel = book.reading_status === 'finished' ? 'Finished'
    : book.reading_status === 'want_to_read' ? 'Want to read'
    : book.reading_status === 'paused' ? 'Paused'
    : book.current_chapter || 'Reading';
  const positionText = book.current_page
    ? `p. ${book.current_page}${book.page_count ? ` / ${book.page_count}` : ''}`
    : null;
  const coverUri = book.cover_url || book.cover_image_uri;

  return (
    <Pressable
      style={[bookStyles.row, hovered && bookStyles.rowHovered]}
      onPress={onPress}
      {...(Platform.OS === 'web' ? { onHoverIn: () => setHovered(true), onHoverOut: () => setHovered(false) } : {})}
    >
      <View style={bookStyles.coverWrap}>
        {coverUri ? (
          <Image source={{ uri: coverUri }} style={bookStyles.cover} />
        ) : (
          <View style={bookStyles.coverPlaceholder}>
            <Text style={bookStyles.coverInitial}>{book.title.charAt(0)}</Text>
          </View>
        )}
      </View>
      <View style={bookStyles.info}>
        <Text style={bookStyles.title} numberOfLines={2}>{book.title}</Text>
        <Text style={bookStyles.author}>{book.author}</Text>
        <View style={bookStyles.metaRow}>
          <Text style={bookStyles.status}>{statusLabel}</Text>
          {positionText && <Text style={bookStyles.position}> · {positionText}</Text>}
        </View>
        {book.topics.length > 0 && (
          <View style={bookStyles.topicRow}>
            {book.topics.slice(0, 2).map(t => (
              <Text key={t} style={bookStyles.topic}>{t}</Text>
            ))}
          </View>
        )}
        {book.current_page && book.page_count && book.reading_status === 'reading' && (
          <ProgressBar current={book.current_page} total={book.page_count} />
        )}
      </View>
      <View style={bookStyles.sidebar}>
        <Text style={bookStyles.sideNumber}>{captureCount}</Text>
        <Text style={bookStyles.sideLabel}>notes</Text>
        <Text style={bookStyles.timeAgo}>{formatTimeAgo(book.last_interaction_at)}</Text>
      </View>
    </Pressable>
  );
}

const bookStyles = StyleSheet.create({
  row: { flexDirection: 'row', paddingVertical: 14, paddingHorizontal: layout.screenPadding, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.rule, gap: 14, ...(Platform.OS === 'web' ? { cursor: 'pointer' as any } : {}) },
  rowHovered: { backgroundColor: colors.parchmentHover },
  coverWrap: { width: 52, height: 72, borderRadius: 2, overflow: 'hidden', backgroundColor: colors.rule },
  cover: { width: 52, height: 72, borderRadius: 2 },
  coverPlaceholder: { width: 52, height: 72, backgroundColor: colors.parchmentDark, borderWidth: 1, borderColor: colors.rule, borderRadius: 2, alignItems: 'center', justifyContent: 'center' },
  coverInitial: { fontFamily: fonts.displaySemiBold, fontSize: 24, color: colors.textMuted, ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}) },
  info: { flex: 1 },
  title: { fontFamily: fonts.bodyMedium, fontSize: 15, lineHeight: 20, color: colors.textPrimary, marginBottom: 2, ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}) },
  author: { fontFamily: fonts.readingItalic, fontSize: 13, color: colors.textSecondary, marginBottom: 4, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  metaRow: { flexDirection: 'row', alignItems: 'center' },
  status: { fontFamily: fonts.ui, fontSize: 11, color: colors.textMuted },
  position: { fontFamily: fonts.ui, fontSize: 11, color: colors.textMuted },
  topicRow: { flexDirection: 'row', gap: 8, marginTop: 4 },
  topic: { fontFamily: fonts.bodyItalic, fontSize: 11, color: colors.rubric, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  sidebar: { width: 56, alignItems: 'flex-end', justifyContent: 'flex-start', paddingTop: 2 },
  sideNumber: { fontFamily: fonts.displaySemiBold, fontSize: 22, color: colors.ink, lineHeight: 26, ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}) },
  sideLabel: { fontFamily: fonts.uiMedium, fontSize: 9, letterSpacing: 0.5, textTransform: 'uppercase', color: colors.textMuted, ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}) },
  timeAgo: { fontFamily: fonts.ui, fontSize: 10, color: colors.textMuted, marginTop: 6 },
});

type FilterMode = 'active' | 'all' | 'archived';

export default function LibraryScreen() {
  const router = useRouter();
  const [filter, setFilter] = useState<FilterMode>('active');
  const [refreshKey, setRefreshKey] = useState(0);

  // Re-read books when screen is focused
  useFocusEffect(useCallback(() => {
    setRefreshKey(k => k + 1);
  }, []));

  const storeVersion = getBookStoreVersion();
  const allBooks = useMemo(() => getPhysicalBooks(), [refreshKey, storeVersion]);

  const books = useMemo(() => {
    let filtered = allBooks;
    if (filter === 'active') {
      filtered = filtered.filter(b => b.reading_status !== 'finished');
    } else if (filter === 'archived') {
      filtered = filtered.filter(b => b.reading_status === 'finished');
    }
    return filtered;
  }, [allBooks, filter]);

  const captureCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const b of allBooks) {
      counts[b.id] = getBookCaptures(b.id).length;
    }
    return counts;
  }, [allBooks, refreshKey, storeVersion]);

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
      <View style={styles.headerContainer}>
        <View style={styles.titleRow}>
          <View>
            <Text style={styles.screenTitle}>Library</Text>
            <Text style={styles.screenSubtitle}>Physical books & reading notes</Text>
          </View>
          <Pressable style={styles.addButton} onPress={() => {
            logEvent('library_add_book_tap');
            router.push('/add-book' as any);
          }}>
            <Text style={styles.addButtonText}>+ Add Book</Text>
          </Pressable>
        </View>
        <DoubleRule />
        <View style={styles.filterRow}>
          {(['active', 'all', 'archived'] as FilterMode[]).map(mode => (
            <Pressable key={mode} style={styles.filterTab} onPress={() => {
              logEvent('library_filter_change', { filter: mode });
              setFilter(mode);
            }}>
              <Text style={[styles.filterText, filter === mode && styles.filterTextActive]}>
                {mode === 'active' ? 'Reading' : mode === 'all' ? 'All' : 'Finished'}
              </Text>
              {filter === mode && <View style={styles.filterDot} />}
            </Pressable>
          ))}
        </View>
      </View>

      {books.length === 0 ? (
        <View style={styles.empty}>
          <Text style={styles.emptyIcon}>{'\u2726'}</Text>
          <Text style={styles.emptyTitle}>No books here yet</Text>
          <Text style={styles.emptySubtitle}>
            {filter === 'archived' ? 'Finished books will appear here' : 'Tap "+ Add Book" to photograph a cover'}
          </Text>
        </View>
      ) : (
        books.map(book => (
          <BookRow key={book.id} book={book} captureCount={captureCounts[book.id] || 0}
            onPress={() => { logEvent('library_book_tap', { book_id: book.id }); router.push({ pathname: '/book-detail', params: { id: book.id } } as any); }} />
        ))
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.parchment },
  content: { paddingBottom: 40, ...(Platform.OS === 'web' ? { maxWidth: layout.contentMaxWidth, width: '100%', alignSelf: 'center' as const } : {}) },
  headerContainer: { paddingTop: 12 },
  titleRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', paddingHorizontal: layout.screenPadding, marginBottom: 12 },
  screenTitle: { ...type.screenTitle, color: colors.ink },
  screenSubtitle: { ...type.screenSubtitle, color: colors.textSecondary, marginTop: 2, ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}) },
  addButton: { borderWidth: 1, borderColor: colors.rubric, paddingVertical: 8, paddingHorizontal: 16, borderRadius: 2, marginTop: 4 },
  addButtonText: { fontFamily: fonts.body, fontSize: 13, color: colors.rubric },
  filterRow: { flexDirection: 'row', paddingHorizontal: layout.screenPadding, paddingTop: 14, paddingBottom: 4, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.rule },
  filterTab: { paddingVertical: 10, paddingHorizontal: 16, alignItems: 'center', minHeight: 44, justifyContent: 'center' },
  filterText: { fontFamily: fonts.body, fontSize: 13, color: colors.textMuted },
  filterTextActive: { color: colors.ink },
  filterDot: { position: 'absolute', bottom: 0, width: 4, height: 4, borderRadius: 2, backgroundColor: colors.rubric },
  empty: { alignItems: 'center', paddingTop: 80, gap: 8 },
  emptyIcon: { fontFamily: fonts.display, fontSize: 28, color: colors.textMuted, marginBottom: 4 },
  emptyTitle: { ...type.screenTitle, color: colors.ink, fontSize: 18 },
  emptySubtitle: { ...type.entrySummary, color: colors.textSecondary, textAlign: 'center', paddingHorizontal: 40 },
});
