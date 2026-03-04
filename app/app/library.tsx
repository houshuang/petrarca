import { useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable, Platform, ViewStyle } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { getLibraryArticles, getByTopic, getReadingState, getArticles, getHighlights, getArticleById, getBooks, getBookById, getBooksByTopic, getBookProgress, getBookReadingState, getBookChapterSections, getCachedBookSections, getBooksNeedingContextRestore, getSectionReadingState } from '../data/store';
import { Article, ReadingDepth, Highlight, Book, BookChapterMeta, BookReadingDepth } from '../data/types';
import { logEvent } from '../data/logger';

const DEPTH_COLORS: Record<ReadingDepth, string> = {
  unread: '#475569',
  summary: '#3b82f6',
  claims: '#8b5cf6',
  sections: '#f59e0b',
  full: '#10b981',
};

const DEPTH_ICONS: Record<ReadingDepth, string> = {
  unread: 'ellipse-outline',
  summary: 'eye-outline',
  claims: 'list-outline',
  sections: 'book-outline',
  full: 'checkmark-circle',
};

function LibraryItem({ article }: { article: Article }) {
  const router = useRouter();
  const state = getReadingState(article.id);
  const timeMin = Math.round(state.time_spent_ms / 60000);
  const lastRead = state.last_read_at ? new Date(state.last_read_at).toLocaleDateString() : '';

  return (
    <Pressable
      style={({ hovered }: any) => [
        styles.item,
        hovered && Platform.OS === 'web' && { backgroundColor: '#253347' },
      ] as ViewStyle[]}
      onPress={() => {
        logEvent('library_item_tap', { article_id: article.id, depth: state.depth });
        router.push({ pathname: '/reader', params: { id: article.id } });
      }}
    >
      <View style={styles.itemLeft}>
        <Ionicons
          name={DEPTH_ICONS[state.depth] as any}
          size={20}
          color={DEPTH_COLORS[state.depth]}
        />
      </View>
      <View style={styles.itemContent}>
        <Text style={styles.itemTitle} numberOfLines={2}>{article.title}</Text>
        <View style={styles.itemMeta}>
          <Text style={styles.itemMetaText}>{article.hostname}</Text>
          {timeMin > 0 && <Text style={styles.itemMetaText}>{timeMin} min spent</Text>}
          {lastRead && <Text style={styles.itemMetaText}>{lastRead}</Text>}
        </View>
      </View>
    </Pressable>
  );
}

function HighlightItem({ highlight }: { highlight: Highlight }) {
  const router = useRouter();
  const article = getArticleById(highlight.article_id);
  if (!article) return null;

  const date = new Date(highlight.highlighted_at).toLocaleDateString();

  return (
    <Pressable
      style={({ hovered }: any) => [
        styles.highlightItem,
        hovered && Platform.OS === 'web' && { backgroundColor: '#253347' },
      ] as ViewStyle[]}
      onPress={() => {
        logEvent('library_highlight_tap', { article_id: highlight.article_id, block_index: highlight.block_index });
        router.push({ pathname: '/reader', params: { id: highlight.article_id } });
      }}
    >
      <Text style={styles.highlightArticleTitle} numberOfLines={1}>{article.title}</Text>
      <Text style={styles.highlightText} numberOfLines={2}>{highlight.text}</Text>
      <Text style={styles.highlightMeta}>{date}</Text>
    </Pressable>
  );
}

function HighlightsView() {
  const allHighlights = getHighlights();

  if (allHighlights.length === 0) {
    return (
      <View style={styles.empty}>
        <Ionicons name="color-wand-outline" size={48} color="#475569" />
        <Text style={styles.emptyTitle}>No highlights yet</Text>
        <Text style={styles.emptySubtitle}>Long-press paragraphs while reading to highlight</Text>
      </View>
    );
  }

  // Group by article, sorted by most recent highlight
  const byArticle = new Map<string, Highlight[]>();
  for (const h of allHighlights) {
    if (!byArticle.has(h.article_id)) byArticle.set(h.article_id, []);
    byArticle.get(h.article_id)!.push(h);
  }
  const groups = [...byArticle.entries()]
    .map(([articleId, highlights]) => ({
      articleId,
      highlights: highlights.sort((a, b) => b.highlighted_at - a.highlighted_at),
      latest: Math.max(...highlights.map(h => h.highlighted_at)),
    }))
    .sort((a, b) => b.latest - a.latest);

  return (
    <>
      {groups.map(({ articleId, highlights }) => (
        <View key={articleId}>
          {highlights.map(h => <HighlightItem key={h.id} highlight={h} />)}
        </View>
      ))}
    </>
  );
}

function ContextRestoreBanner({ items }: { items: Array<{ book: Book; lastSectionId: string; daysSince: number }> }) {
  const router = useRouter();

  return (
    <View style={shelfStyles.restoreBanner}>
      <Text style={shelfStyles.restoreTitle}>Pick up where you left off</Text>
      {items.map(({ book, lastSectionId, daysSince }) => (
        <Pressable
          key={book.id}
          style={shelfStyles.restoreItem}
          onPress={() => {
            logEvent('context_restore_tap', { book_id: book.id, section_id: lastSectionId, days_since: daysSince });
            router.push({ pathname: '/book-reader', params: { bookId: book.id, sectionId: lastSectionId } });
          }}
        >
          <Ionicons name="bookmark" size={14} color="#f59e0b" />
          <View style={{ flex: 1 }}>
            <Text style={shelfStyles.restoreBookTitle} numberOfLines={1}>{book.title}</Text>
            <Text style={shelfStyles.restoreMeta}>{daysSince} days ago</Text>
          </View>
          <Ionicons name="chevron-forward" size={14} color="#64748b" />
        </Pressable>
      ))}
    </View>
  );
}

function ChapterRow({ bookId, chapter }: { bookId: string; chapter: BookChapterMeta }) {
  const router = useRouter();
  const bookState = getBookReadingState(bookId);

  const sectionIds = Array.from({ length: chapter.section_count }, (_, i) =>
    `${bookId}:ch${chapter.chapter_number}:s${i + 1}`
  );

  return (
    <View style={shelfStyles.chapterRow}>
      <Text style={shelfStyles.chapterTitle}>Ch {chapter.chapter_number}: {chapter.title}</Text>
      <View style={shelfStyles.sectionDots}>
        {sectionIds.map((sid) => {
          const state = bookState.section_states[sid];
          const depth = state?.depth || 'unread';
          const color = depth === 'unread' ? '#334155'
            : depth === 'reflected' ? '#10b981'
            : '#3b82f6';
          return (
            <Pressable
              key={sid}
              style={[shelfStyles.sectionDot, { backgroundColor: color }]}
              onPress={() => {
                logEvent('shelf_section_tap', { book_id: bookId, section_id: sid });
                router.push({ pathname: '/book-reader', params: { bookId, sectionId: sid } });
              }}
            />
          );
        })}
      </View>
    </View>
  );
}

function BookShelfItem({ book }: { book: Book }) {
  const [expanded, setExpanded] = useState(false);
  const router = useRouter();
  const progress = getBookProgress(book.id);
  const bookState = getBookReadingState(book.id);
  const timeMin = Math.round(bookState.total_time_spent_ms / 60000);

  // Find next unread section
  const nextSection = (() => {
    for (const ch of book.chapters.filter(c => c.processing_status === 'completed')) {
      for (let s = 1; s <= ch.section_count; s++) {
        const sid = `${book.id}:ch${ch.chapter_number}:s${s}`;
        const state = getSectionReadingState(book.id, sid);
        if (state.depth === 'unread') {
          return { sectionId: sid, chapterNum: ch.chapter_number, sectionNum: s, chapterTitle: ch.title };
        }
      }
    }
    return null;
  })();

  return (
    <View style={shelfStyles.bookItem}>
      <Pressable onPress={() => setExpanded(!expanded)} style={shelfStyles.bookHeader}>
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <Ionicons name="book" size={16} color="#60a5fa" />
            <Text style={shelfStyles.bookTitle} numberOfLines={1}>{book.title}</Text>
          </View>
          <Text style={shelfStyles.bookAuthor}>{book.author}</Text>
          <View style={{ flexDirection: 'row', gap: 12, marginTop: 4 }}>
            <Text style={shelfStyles.bookMeta}>{progress.pct}% read</Text>
            <Text style={shelfStyles.bookMeta}>{progress.read}/{progress.total} sections</Text>
            {timeMin > 0 && <Text style={shelfStyles.bookMeta}>{timeMin} min</Text>}
          </View>
          <View style={shelfStyles.progressBar}>
            <View style={[shelfStyles.progressFill, { width: `${progress.pct}%` }]} />
          </View>
        </View>
        <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={16} color="#64748b" />
      </Pressable>

      {/* Suggested next section */}
      {nextSection && progress.pct > 0 && progress.pct < 100 && (
        <Pressable
          style={shelfStyles.suggestedNext}
          onPress={() => {
            logEvent('shelf_suggested_next_tap', { book_id: book.id, section_id: nextSection.sectionId });
            router.push({ pathname: '/book-reader', params: { bookId: book.id, sectionId: nextSection.sectionId } });
          }}
        >
          <Ionicons name="play-circle-outline" size={16} color="#34d399" />
          <Text style={shelfStyles.suggestedNextText}>
            Continue: Ch {nextSection.chapterNum}, §{nextSection.sectionNum}
          </Text>
          <Ionicons name="arrow-forward" size={12} color="#34d399" />
        </Pressable>
      )}

      {expanded && (
        <View style={shelfStyles.chapterList}>
          <Pressable
            style={shelfStyles.openLandingBtn}
            onPress={() => {
              logEvent('shelf_book_landing_tap', { book_id: book.id });
              router.push({ pathname: '/book-reader', params: { bookId: book.id, sectionId: '' } });
            }}
          >
            <Ionicons name="map-outline" size={14} color="#60a5fa" />
            <Text style={shelfStyles.openLandingText}>Book overview</Text>
          </Pressable>
          {book.chapters
            .filter(ch => ch.processing_status === 'completed')
            .map(ch => (
              <ChapterRow
                key={ch.chapter_number}
                bookId={book.id}
                chapter={ch}
              />
            ))}
        </View>
      )}
    </View>
  );
}

function ShelfTopicGroup({ topic, books, articles }: { topic: string; books: Book[]; articles: Article[] }) {
  const [collapsed, setCollapsed] = useState(true);
  const router = useRouter();

  return (
    <View style={styles.topicGroup}>
      <Pressable onPress={() => setCollapsed(!collapsed)} style={styles.topicHeader}>
        <Text style={styles.topicTitle}>{topic}</Text>
        <View style={styles.topicRight}>
          <Text style={styles.topicCount}>{books.length} books · {articles.length} articles</Text>
          <Ionicons name={collapsed ? 'chevron-down' : 'chevron-up'} size={16} color="#64748b" />
        </View>
      </Pressable>
      {!collapsed && (
        <View>
          {books.map(book => <BookShelfItem key={book.id} book={book} />)}
          {articles.slice(0, 5).map(a => <LibraryItem key={a.id} article={a} />)}
          {articles.length > 5 && (
            <Text style={{ color: '#64748b', fontSize: 12, padding: 14, textAlign: 'center' }}>
              +{articles.length - 5} more articles
            </Text>
          )}
        </View>
      )}
    </View>
  );
}

function ShelfView() {
  const books = getBooks();
  const booksByTopic = getBooksByTopic();
  const topicMap = getByTopic();

  if (books.length === 0) {
    return (
      <View style={styles.empty}>
        <Ionicons name="book-outline" size={48} color="#475569" />
        <Text style={styles.emptyTitle}>No books yet</Text>
        <Text style={styles.emptySubtitle}>Books will appear here once ingested</Text>
      </View>
    );
  }

  const needsRestore = getBooksNeedingContextRestore();

  return (
    <>
      {needsRestore.length > 0 && <ContextRestoreBanner items={needsRestore} />}
      {[...booksByTopic.entries()]
        .sort((a, b) => b[1].length - a[1].length)
        .map(([topic, topicBooks]) => (
          <ShelfTopicGroup
            key={topic}
            topic={topic}
            books={topicBooks}
            articles={topicMap.get(topic) || []}
          />
        ))}
    </>
  );
}

export default function LibraryScreen() {
  const [viewMode, setViewMode] = useState<'recent' | 'topic' | 'highlights' | 'shelf'>('recent');
  const [, forceUpdate] = useState(0);
  const library = getLibraryArticles();
  const allArticles = getArticles();
  const topicMap = getByTopic();

  return (
    <View style={styles.container}>
      <View style={styles.toggleRow}>
        <Pressable
          style={[styles.toggleBtn, viewMode === 'recent' && styles.toggleActive]}
          onPress={() => { logEvent('library_view_mode', { mode: 'recent' }); setViewMode('recent'); }}
        >
          <Text style={[styles.toggleText, viewMode === 'recent' && styles.toggleTextActive]}>Recent</Text>
        </Pressable>
        <Pressable
          style={[styles.toggleBtn, viewMode === 'topic' && styles.toggleActive]}
          onPress={() => { logEvent('library_view_mode', { mode: 'topic' }); setViewMode('topic'); }}
        >
          <Text style={[styles.toggleText, viewMode === 'topic' && styles.toggleTextActive]}>By Topic</Text>
        </Pressable>
        <Pressable
          style={[styles.toggleBtn, viewMode === 'shelf' && styles.toggleActive]}
          onPress={() => { logEvent('library_view_mode', { mode: 'shelf' }); setViewMode('shelf'); }}
        >
          <Text style={[styles.toggleText, viewMode === 'shelf' && styles.toggleTextActive]}>Shelf</Text>
        </Pressable>
        <Pressable
          style={[styles.toggleBtn, viewMode === 'highlights' && styles.toggleActive]}
          onPress={() => { logEvent('library_view_mode', { mode: 'highlights' }); setViewMode('highlights'); }}
        >
          <Text style={[styles.toggleText, viewMode === 'highlights' && styles.toggleTextActive]}>Highlights</Text>
        </Pressable>
        <View style={{ flex: 1 }} />
        <Pressable onPress={() => forceUpdate(n => n + 1)}>
          <Ionicons name="refresh" size={18} color="#64748b" />
        </Pressable>
      </View>

      <ScrollView style={styles.scroll} showsVerticalScrollIndicator={false}>
        {viewMode === 'recent' ? (
          library.length === 0 ? (
            <View style={styles.empty}>
              <Ionicons name="library-outline" size={48} color="#475569" />
              <Text style={styles.emptyTitle}>Nothing here yet</Text>
              <Text style={styles.emptySubtitle}>Articles you read will appear here</Text>
            </View>
          ) : (
            library.map(a => <LibraryItem key={a.id} article={a} />)
          )
        ) : viewMode === 'topic' ? (
          [...topicMap.entries()]
            .sort((a, b) => b[1].length - a[1].length)
            .map(([topic, articles]) => (
              <TopicGroup key={topic} topic={topic} articles={articles} />
            ))
        ) : viewMode === 'shelf' ? (
          <ShelfView />
        ) : (
          <HighlightsView />
        )}
        <View style={{ height: 40 }} />
      </ScrollView>
    </View>
  );
}

function TopicGroup({ topic, articles }: { topic: string; articles: Article[] }) {
  const [collapsed, setCollapsed] = useState(true);

  return (
    <View style={styles.topicGroup}>
      <Pressable
        onPress={() => {
          logEvent('library_topic_toggle', { topic, collapsed: !collapsed });
          setCollapsed(!collapsed);
        }}
        style={({ hovered }: any) => [
          styles.topicHeader,
          hovered && Platform.OS === 'web' && { backgroundColor: '#253347' },
        ] as ViewStyle[]}
      >
        <Text style={styles.topicTitle}>{topic}</Text>
        <View style={styles.topicRight}>
          <Text style={styles.topicCount}>{articles.length}</Text>
          <Ionicons name={collapsed ? 'chevron-down' : 'chevron-up'} size={16} color="#64748b" />
        </View>
      </Pressable>
      {!collapsed && articles.map(a => <LibraryItem key={a.id} article={a} />)}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f172a' },
  toggleRow: { flexDirection: 'row', paddingHorizontal: 16, paddingTop: 8, paddingBottom: 4, gap: 8, alignItems: 'center' },
  toggleBtn: { paddingHorizontal: 16, paddingVertical: 6, borderRadius: 20, backgroundColor: '#1e293b' },
  toggleActive: { backgroundColor: '#2563eb' },
  toggleText: { color: '#94a3b8', fontSize: 14 },
  toggleTextActive: { color: '#f8fafc' },
  scroll: { flex: 1, paddingHorizontal: 16, paddingTop: 8 },

  item: { flexDirection: 'row', backgroundColor: '#1e293b', borderRadius: 10, padding: 14, marginBottom: 8, gap: 12 },
  itemLeft: { paddingTop: 2 },
  itemContent: { flex: 1 },
  itemTitle: { color: '#f8fafc', fontSize: 15, fontWeight: '500', lineHeight: 20, marginBottom: 4 },
  itemMeta: { flexDirection: 'row', gap: 8 },
  itemMetaText: { color: '#64748b', fontSize: 12 },

  topicGroup: { marginBottom: 4, borderRadius: 10, overflow: 'hidden', backgroundColor: '#1e293b' },
  topicHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 14 },
  topicTitle: { color: '#f8fafc', fontSize: 15, fontWeight: '600' },
  topicRight: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  topicCount: { color: '#64748b', fontSize: 13, backgroundColor: '#334155', paddingHorizontal: 8, paddingVertical: 1, borderRadius: 10 },

  empty: { justifyContent: 'center', alignItems: 'center', paddingTop: 100, gap: 8 },
  emptyTitle: { color: '#f8fafc', fontSize: 20, fontWeight: '700' },
  emptySubtitle: { color: '#94a3b8', fontSize: 14 },

  highlightItem: {
    backgroundColor: '#1e293b',
    borderRadius: 10,
    padding: 14,
    marginBottom: 8,
    borderLeftWidth: 3,
    borderLeftColor: '#f59e0b',
  },
  highlightArticleTitle: { color: '#60a5fa', fontSize: 12, fontWeight: '500', marginBottom: 4 },
  highlightText: { color: '#e2e8f0', fontSize: 14, lineHeight: 20, marginBottom: 4 },
  highlightMeta: { color: '#64748b', fontSize: 11 },
});

const shelfStyles = StyleSheet.create({
  bookItem: {
    backgroundColor: '#1e293b',
    borderRadius: 10,
    marginHorizontal: 0,
    marginBottom: 4,
    borderLeftWidth: 3,
    borderLeftColor: '#60a5fa',
  },
  bookHeader: {
    flexDirection: 'row',
    padding: 14,
    alignItems: 'center',
    gap: 12,
  },
  bookTitle: { color: '#f8fafc', fontSize: 15, fontWeight: '600' },
  bookAuthor: { color: '#94a3b8', fontSize: 13 },
  bookMeta: { color: '#64748b', fontSize: 12 },
  progressBar: {
    height: 3,
    backgroundColor: '#334155',
    borderRadius: 2,
    marginTop: 6,
  },
  progressFill: {
    height: 3,
    backgroundColor: '#3b82f6',
    borderRadius: 2,
  },
  chapterList: { paddingHorizontal: 14, paddingBottom: 10 },
  openLandingBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 8,
    paddingHorizontal: 10,
    backgroundColor: '#0f172a',
    borderRadius: 8,
    marginBottom: 8,
  },
  openLandingText: { color: '#60a5fa', fontSize: 13, fontWeight: '500' },
  chapterRow: { paddingVertical: 6 },
  chapterTitle: { color: '#94a3b8', fontSize: 13, marginBottom: 4 },
  sectionDots: { flexDirection: 'row', gap: 4, flexWrap: 'wrap' },
  sectionDot: {
    width: 12,
    height: 12,
    borderRadius: 6,
  },
  restoreBanner: {
    backgroundColor: '#1e293b',
    borderRadius: 10,
    padding: 14,
    marginBottom: 12,
    borderLeftWidth: 3,
    borderLeftColor: '#f59e0b',
  },
  restoreTitle: { color: '#f59e0b', fontSize: 14, fontWeight: '600', marginBottom: 8 },
  restoreItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 6,
  },
  restoreBookTitle: { color: '#f8fafc', fontSize: 14 },
  restoreMeta: { color: '#64748b', fontSize: 12 },
  suggestedNext: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: 6,
    paddingHorizontal: 14,
    paddingVertical: 8,
    backgroundColor: '#052e16',
    borderTopWidth: 1,
    borderTopColor: '#064e3b',
  },
  suggestedNextText: {
    color: '#34d399',
    fontSize: 13,
    fontWeight: '500' as const,
    flex: 1,
  },
});
