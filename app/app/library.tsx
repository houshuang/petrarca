import { useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable, Platform, ViewStyle } from 'react-native';
import { useRouter } from 'expo-router';
import { getLibraryArticles, getByTopic, getReadingState, getArticles, getHighlights, getArticleById, getBooks, getBookById, getBooksByTopic, getBookProgress, getBookReadingState, getBookChapterSections, getCachedBookSections, getBooksNeedingContextRestore, getSectionReadingState } from '../data/store';
import { Article, ReadingDepth, Highlight, Book, BookChapterMeta, BookReadingDepth } from '../data/types';
import { logEvent } from '../data/logger';
import { colors, fonts, type } from '../design/tokens';

const DEPTH_LABELS: Record<ReadingDepth, string> = {
  unread: '—',
  summary: 'Sum',
  claims: 'Clm',
  sections: 'Sec',
  full: 'Full',
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
        hovered && Platform.OS === 'web' && { backgroundColor: colors.parchmentHover },
      ] as ViewStyle[]}
      onPress={() => {
        logEvent('library_item_tap', { article_id: article.id, depth: state.depth });
        router.push({ pathname: '/reader', params: { id: article.id } });
      }}
    >
      <View style={styles.itemContent}>
        <Text style={styles.itemTitle} numberOfLines={2}>{article.title}</Text>
        <View style={styles.itemMeta}>
          <Text style={styles.itemMetaText}>{article.hostname}</Text>
          {timeMin > 0 && <Text style={styles.itemMetaText}>{timeMin} min spent</Text>}
          {lastRead && <Text style={styles.itemMetaText}>{lastRead}</Text>}
        </View>
      </View>
      <View style={styles.sidebar}>
        <Text style={styles.sideLabel}>DEPTH</Text>
        <Text style={[
          styles.sideValue,
          { color: state.depth === 'unread' ? colors.textMuted : state.depth === 'full' ? colors.rubric : colors.ink },
        ]}>{DEPTH_LABELS[state.depth]}</Text>
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
        hovered && Platform.OS === 'web' && { backgroundColor: colors.parchmentHover },
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
          <View style={shelfStyles.restoreDot} />
          <View style={{ flex: 1 }}>
            <Text style={shelfStyles.restoreBookTitle} numberOfLines={1}>{book.title}</Text>
            <Text style={shelfStyles.restoreMeta}>{daysSince} days ago</Text>
          </View>
          <Text style={shelfStyles.restoreChevron}>›</Text>
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
          const color = depth === 'unread' ? colors.textMuted
            : depth === 'reflected' ? colors.success
            : colors.ink;
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
          <Text style={shelfStyles.bookTitle} numberOfLines={1}>{book.title}</Text>
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
        <Text style={shelfStyles.chevron}>{expanded ? '‹' : '›'}</Text>
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
          <Text style={shelfStyles.suggestedNextText}>
            Continue: Ch {nextSection.chapterNum}, §{nextSection.sectionNum}
          </Text>
          <Text style={shelfStyles.suggestedNextArrow}>→</Text>
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
          <Text style={styles.chevronText}>{collapsed ? '›' : '‹'}</Text>
        </View>
      </Pressable>
      {!collapsed && (
        <View>
          {books.map(book => <BookShelfItem key={book.id} book={book} />)}
          {articles.slice(0, 5).map(a => <LibraryItem key={a.id} article={a} />)}
          {articles.length > 5 && (
            <Text style={styles.moreText}>
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
      {/* Screen title */}
      <View style={styles.header}>
        <Text style={styles.screenTitle}>Library</Text>
        <Text style={styles.screenSubtitle}>your reading collection</Text>
        <View style={styles.doubleRule}>
          <View style={styles.ruleThick} />
          <View style={styles.ruleThin} />
        </View>
      </View>

      {/* View mode pills */}
      <View style={styles.toggleRow}>
        {(['recent', 'topic', 'shelf', 'highlights'] as const).map((mode) => {
          const labels = { recent: 'Recent', topic: 'By Topic', shelf: 'Shelf', highlights: 'Highlights' };
          const active = viewMode === mode;
          return (
            <Pressable
              key={mode}
              style={[styles.toggleBtn, active && styles.toggleActive]}
              onPress={() => { logEvent('library_view_mode', { mode }); setViewMode(mode); }}
            >
              <Text style={[styles.toggleText, active && styles.toggleTextActive]}>{labels[mode]}</Text>
            </Pressable>
          );
        })}
        <View style={{ flex: 1 }} />
        <Pressable onPress={() => forceUpdate(n => n + 1)}>
          <Text style={styles.refreshText}>✦</Text>
        </Pressable>
      </View>

      <ScrollView style={styles.scroll} showsVerticalScrollIndicator={false}>
        {viewMode === 'recent' ? (
          library.length === 0 ? (
            <View style={styles.empty}>
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
          hovered && Platform.OS === 'web' && { backgroundColor: colors.parchmentHover },
        ] as ViewStyle[]}
      >
        <Text style={styles.topicTitle}>{topic}</Text>
        <View style={styles.topicRight}>
          <Text style={styles.topicCount}>{articles.length}</Text>
          <Text style={styles.chevronText}>{collapsed ? '›' : '‹'}</Text>
        </View>
      </Pressable>
      {!collapsed && articles.map(a => <LibraryItem key={a.id} article={a} />)}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.parchment,
  },
  header: {
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 0,
  },
  screenTitle: {
    ...type.screenTitle,
    color: colors.ink,
  },
  screenSubtitle: {
    ...type.screenSubtitle,
    color: colors.textMuted,
    marginTop: 2,
  },
  doubleRule: {
    marginTop: 10,
    gap: 5,
  },
  ruleThick: {
    height: 2,
    backgroundColor: colors.ruleDark,
  },
  ruleThin: {
    height: 1,
    backgroundColor: colors.ruleDark,
  },

  toggleRow: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 8,
    gap: 8,
    alignItems: 'center',
  },
  toggleBtn: {
    paddingHorizontal: 14,
    paddingVertical: 5,
    borderRadius: 20,
    backgroundColor: 'transparent',
  },
  toggleActive: {
    backgroundColor: colors.rubric,
  },
  toggleText: {
    fontFamily: fonts.bodyMedium,
    fontSize: 13,
    color: colors.textMuted,
    ...(Platform.OS === 'web' ? { fontWeight: '500' } : {}),
  },
  toggleTextActive: {
    color: colors.parchment,
  },
  refreshText: {
    fontSize: 16,
    color: colors.rubric,
  },

  scroll: {
    flex: 1,
    paddingHorizontal: 16,
    paddingTop: 4,
  },

  // Entry rows
  item: {
    flexDirection: 'row',
    borderBottomWidth: 1,
    borderBottomColor: colors.rule,
    paddingVertical: 12,
  },
  itemContent: {
    flex: 1,
    paddingRight: 12,
  },
  itemTitle: {
    ...type.entryTitle,
    color: colors.textPrimary,
    marginBottom: 4,
  },
  itemMeta: {
    flexDirection: 'row',
    gap: 8,
  },
  itemMetaText: {
    ...type.metadata,
    color: colors.textMuted,
  },
  sidebar: {
    width: 48,
    alignItems: 'center',
    justifyContent: 'center',
    borderLeftWidth: 1,
    borderLeftColor: colors.rule,
    paddingLeft: 8,
  },
  sideLabel: {
    ...type.sideLabel,
    color: colors.textMuted,
  },
  sideValue: {
    ...type.sideValue,
    color: colors.ink,
    marginTop: 2,
  },

  // Topic groups
  topicGroup: {
    marginBottom: 4,
  },
  topicHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.rule,
  },
  topicTitle: {
    fontFamily: fonts.bodyMedium,
    fontSize: 16,
    color: colors.ink,
    ...(Platform.OS === 'web' ? { fontWeight: '500' } : {}),
  },
  topicRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  topicCount: {
    fontFamily: fonts.bodyMedium,
    fontSize: 13,
    color: colors.rubric,
    ...(Platform.OS === 'web' ? { fontWeight: '500' } : {}),
  },
  chevronText: {
    fontFamily: fonts.body,
    fontSize: 18,
    color: colors.textMuted,
  },
  moreText: {
    ...type.metadata,
    color: colors.textMuted,
    padding: 14,
    textAlign: 'center',
  },

  // Empty states
  empty: {
    justifyContent: 'center',
    alignItems: 'center',
    paddingTop: 100,
    gap: 8,
  },
  emptyTitle: {
    ...type.screenTitle,
    color: colors.ink,
    fontSize: 20,
  },
  emptySubtitle: {
    ...type.entrySummary,
    color: colors.textSecondary,
  },

  // Highlights
  highlightItem: {
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.rule,
    borderLeftWidth: 3,
    borderLeftColor: colors.warning,
    paddingLeft: 12,
  },
  highlightArticleTitle: {
    ...type.metadata,
    color: colors.rubric,
    marginBottom: 4,
  },
  highlightText: {
    fontFamily: fonts.readingItalic,
    fontSize: 14,
    lineHeight: 20,
    color: colors.textBody,
    marginBottom: 4,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' } : {}),
  },
  highlightMeta: {
    ...type.metadata,
    color: colors.textMuted,
  },
});

const shelfStyles = StyleSheet.create({
  bookItem: {
    borderLeftWidth: 3,
    borderLeftColor: colors.rubric,
    marginBottom: 4,
    paddingLeft: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.rule,
  },
  bookHeader: {
    flexDirection: 'row',
    paddingVertical: 12,
    alignItems: 'center',
    gap: 12,
  },
  bookTitle: {
    ...type.entryTitle,
    color: colors.textPrimary,
  },
  bookAuthor: {
    ...type.entrySummary,
    color: colors.textSecondary,
  },
  bookMeta: {
    ...type.metadata,
    color: colors.textMuted,
  },
  chevron: {
    fontFamily: fonts.body,
    fontSize: 18,
    color: colors.textMuted,
  },
  progressBar: {
    height: 3,
    backgroundColor: colors.rule,
    marginTop: 6,
  },
  progressFill: {
    height: 3,
    backgroundColor: colors.ink,
  },
  chapterList: {
    paddingHorizontal: 0,
    paddingBottom: 10,
  },
  openLandingBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 8,
  },
  openLandingText: {
    fontFamily: fonts.bodyMedium,
    fontSize: 13,
    color: colors.rubric,
    ...(Platform.OS === 'web' ? { fontWeight: '500' } : {}),
  },
  chapterRow: {
    paddingVertical: 6,
  },
  chapterTitle: {
    ...type.entrySummary,
    color: colors.textSecondary,
    marginBottom: 4,
  },
  sectionDots: {
    flexDirection: 'row',
    gap: 4,
    flexWrap: 'wrap',
  },
  sectionDot: {
    width: 12,
    height: 12,
    borderRadius: 6,
  },
  restoreBanner: {
    paddingVertical: 12,
    marginBottom: 8,
    borderLeftWidth: 3,
    borderLeftColor: colors.warning,
    paddingLeft: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.rule,
  },
  restoreTitle: {
    ...type.sectionHead,
    color: colors.rubric,
    marginBottom: 8,
  },
  restoreDot: {
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.rubric,
  },
  restoreItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 6,
  },
  restoreBookTitle: {
    ...type.entryTitle,
    fontSize: 14,
    color: colors.textPrimary,
  },
  restoreMeta: {
    ...type.metadata,
    color: colors.textMuted,
  },
  restoreChevron: {
    fontFamily: fonts.body,
    fontSize: 16,
    color: colors.textMuted,
  },
  suggestedNext: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: 6,
    paddingVertical: 8,
    borderTopWidth: 1,
    borderTopColor: colors.rule,
  },
  suggestedNextText: {
    fontFamily: fonts.readingMedium,
    fontSize: 13,
    color: colors.rubric,
    flex: 1,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  suggestedNextArrow: {
    fontFamily: fonts.body,
    fontSize: 14,
    color: colors.rubric,
  },
});
