import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, FlatList, Pressable, Animated, Platform, ScrollView,
} from 'react-native';
import { useRouter } from 'expo-router';
import { GestureHandlerRootView, Swipeable } from 'react-native-gesture-handler';
import { getArticleById, recordInterestSignal } from '../../data/store';
import { Article } from '../../data/types';
import { logEvent } from '../../data/logger';
import { getDisplayTitle } from '../../lib/display-utils';
import { colors, fonts, type, spacing, layout } from '../../design/tokens';
import { loadQueue, getQueuedArticleIds, removeFromQueue } from '../../data/queue';
import DoubleRule from '../../components/DoubleRule';
import { useKeyboardShortcuts, type ShortcutMap } from '../../hooks/useKeyboardShortcuts';

// --- Web Hover Card Wrapper ---

function WebHoverCard({ article, onRemove, onPress, focused }: {
  article: Article;
  onRemove: () => void;
  onPress: () => void;
  focused?: boolean;
}) {
  const [hovered, setHovered] = useState(false);

  const topics = (article.interest_topics || [])
    .slice(0, 3)
    .map(t => t.specific || t.broad);
  const fallbackTopics = topics.length > 0 ? topics : article.topics.slice(0, 3);

  const handleRemove = async () => {
    await removeFromQueue(article.id);
    logEvent('queue_web_remove', { article_id: article.id });
    onRemove();
  };

  return (
    <Pressable
      onPress={onPress}
      // @ts-ignore — web-only mouse events
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={[
        styles.card,
        hovered && !focused && { backgroundColor: colors.parchmentHover },
        focused && styles.cardFocused,
      ]}
      nativeID={`queue-article-${article.id}`}
    >
      <View style={webStyles.cardRow}>
        <View style={webStyles.cardContent}>
          <Text style={styles.cardTitle} numberOfLines={2}>
            {getDisplayTitle(article)}
          </Text>
          {article.one_line_summary ? (
            <Text style={styles.cardSummary} numberOfLines={2}>
              {article.one_line_summary}
            </Text>
          ) : null}
          <View style={styles.cardFooter}>
            <Text style={styles.cardMeta}>
              {article.hostname}
              {article.author ? ` \u00b7 ${article.author}` : ''}
              {` \u00b7 ${article.estimated_read_minutes} min`}
            </Text>
            <View style={styles.topicTags}>
              {fallbackTopics.map(t => (
                <Text key={t} style={styles.topicTagText}>{t}</Text>
              ))}
            </View>
          </View>
        </View>
        {hovered && (
          <Pressable
            onPress={(e) => {
              e.stopPropagation();
              handleRemove();
            }}
            style={webStyles.removeButton}
          >
            <Text style={webStyles.removeText}>{'\u2715'} Remove</Text>
          </Pressable>
        )}
      </View>
    </Pressable>
  );
}

// --- Queue Article Card (mobile) ---

function QueueArticleCard({ article, onRemove }: {
  article: Article;
  onRemove: () => void;
}) {
  const router = useRouter();

  const renderRightActions = (_progress: Animated.AnimatedInterpolation<number>, dragX: Animated.AnimatedInterpolation<number>) => {
    const scale = dragX.interpolate({
      inputRange: [-100, 0],
      outputRange: [1, 0],
      extrapolate: 'clamp',
    });
    return (
      <Animated.View style={[styles.swipeAction, { transform: [{ scale }] }]}>
        <Text style={styles.swipeActionText}>Remove</Text>
      </Animated.View>
    );
  };

  const handleSwipe = async () => {
    await removeFromQueue(article.id);
    logEvent('queue_swipe_remove', { article_id: article.id });
    onRemove();
  };

  const topics = (article.interest_topics || [])
    .slice(0, 3)
    .map(t => t.specific || t.broad);
  const fallbackTopics = topics.length > 0 ? topics : article.topics.slice(0, 3);

  return (
    <Swipeable
      renderRightActions={renderRightActions}
      onSwipeableOpen={handleSwipe}
      overshootRight={false}
    >
      <Pressable
        style={({ pressed }) => [
          styles.card,
          pressed && { opacity: 0.9 },
        ]}
        onPress={() => {
          logEvent('queue_article_tap', { article_id: article.id });
          recordInterestSignal('open_article', article.id);
          router.push({ pathname: '/reader', params: { id: article.id } });
        }}
      >
        <Text style={styles.cardTitle} numberOfLines={2}>
          {getDisplayTitle(article)}
        </Text>
        {article.one_line_summary ? (
          <Text style={styles.cardSummary} numberOfLines={2}>
            {article.one_line_summary}
          </Text>
        ) : null}
        <View style={styles.cardFooter}>
          <Text style={styles.cardMeta}>
            {article.hostname}
            {article.author ? ` \u00b7 ${article.author}` : ''}
            {` \u00b7 ${article.estimated_read_minutes} min`}
          </Text>
          <View style={styles.topicTags}>
            {fallbackTopics.map(t => (
              <Text key={t} style={styles.topicTagText}>{t}</Text>
            ))}
          </View>
        </View>
      </Pressable>
    </Swipeable>
  );
}

// --- Queue Screen ---

export default function QueueScreen() {
  const router = useRouter();
  const [, forceUpdate] = useState(0);
  const [ready, setReady] = useState(false);
  const [focusedIndex, setFocusedIndex] = useState(-1);

  useEffect(() => {
    loadQueue().then(() => {
      setReady(true);
      forceUpdate(n => n + 1);
    });
  }, []);

  const handleRemove = useCallback(() => {
    forceUpdate(n => n + 1);
  }, []);

  const queuedIds = getQueuedArticleIds();
  const queuedArticles = queuedIds
    .map(id => getArticleById(id))
    .filter((a): a is Article => a != null);

  // Clamp focusedIndex when queue shrinks
  useEffect(() => {
    if (focusedIndex >= queuedArticles.length) {
      setFocusedIndex(queuedArticles.length - 1);
    }
  }, [queuedArticles.length, focusedIndex]);

  const scrollToQueueArticle = useCallback((index: number) => {
    if (Platform.OS !== 'web') return;
    const article = queuedArticles[index];
    if (article) {
      const el = document.getElementById(`queue-article-${article.id}`);
      el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [queuedArticles]);

  const queueShortcuts = useMemo((): ShortcutMap => ({
    j: { handler: () => setFocusedIndex(i => {
      const maxIdx = queuedArticles.length - 1;
      if (maxIdx < 0) return -1;
      const next = Math.min(i + 1, maxIdx);
      scrollToQueueArticle(next);
      return next;
    }), label: 'next' },
    k: { handler: () => setFocusedIndex(i => {
      if (i <= 0) {
        window.scrollTo({ top: 0, behavior: 'smooth' });
        return -1;
      }
      const prev = i - 1;
      scrollToQueueArticle(prev);
      return prev;
    }), label: 'prev' },
    Enter: { handler: () => {
      if (focusedIndex >= 0 && focusedIndex < queuedArticles.length) {
        const article = queuedArticles[focusedIndex];
        logEvent('queue_article_tap', { article_id: article.id, via: 'keyboard' });
        recordInterestSignal('open_article', article.id);
        router.push({ pathname: '/reader', params: { id: article.id } });
      }
    }, label: 'open' },
    x: { handler: async () => {
      if (focusedIndex >= 0 && focusedIndex < queuedArticles.length) {
        const article = queuedArticles[focusedIndex];
        await removeFromQueue(article.id);
        logEvent('queue_keyboard_remove', { article_id: article.id });
        handleRemove();
      }
    }, label: 'remove' },
  }), [queuedArticles, focusedIndex, scrollToQueueArticle, router, handleRemove]);

  useKeyboardShortcuts(queueShortcuts);

  if (!ready) return <View style={styles.container} />;

  // --- Web layout ---
  if (Platform.OS === 'web') {
    return (
      <View style={styles.container}>
        <ScrollView
          style={webStyles.scrollView}
          contentContainerStyle={webStyles.scrollContent}
        >
          <View style={webStyles.centeredColumn}>
            <Pressable
              onPress={() => router.back()}
              style={webStyles.backButton}
            >
              <Text style={webStyles.backText}>{'\u2190'} Feed</Text>
            </Pressable>

            <View style={styles.header}>
              <Text style={styles.headerTitle}>Queue</Text>
              <Text style={styles.headerSubtitle}>
                {queuedArticles.length} article{queuedArticles.length !== 1 ? 's' : ''} saved to read
              </Text>
            </View>

            <DoubleRule />

            {queuedArticles.length > 0 ? (
              <>
                <Text style={[styles.sectionHead, { marginTop: 24 }]}>
                  <Text style={{ color: colors.rubric }}>{'\u2726'} </Text>
                  Up Next
                </Text>
                {queuedArticles.map((article, idx) => (
                  <WebHoverCard
                    key={article.id}
                    article={article}
                    onRemove={handleRemove}
                    onPress={() => {
                      logEvent('queue_article_tap', { article_id: article.id });
                      recordInterestSignal('open_article', article.id);
                      router.push({ pathname: '/reader', params: { id: article.id } });
                    }}
                    focused={idx === focusedIndex}
                  />
                ))}
              </>
            ) : (
              <View style={styles.empty}>
                <Text style={styles.emptyTitle}>Your reading queue is empty</Text>
                <Text style={styles.emptySubtitle}>
                  Bookmark articles in the feed to add them here
                </Text>
              </View>
            )}
          </View>
        </ScrollView>
      </View>
    );
  }

  // --- Mobile layout ---
  return (
    <GestureHandlerRootView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Queue</Text>
        <Text style={styles.headerSubtitle}>
          {queuedArticles.length} article{queuedArticles.length !== 1 ? 's' : ''} saved to read
        </Text>
      </View>

      <DoubleRule />

      <FlatList
        data={queuedArticles}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => (
          <QueueArticleCard article={item} onRemove={handleRemove} />
        )}
        contentContainerStyle={styles.listContent}
        showsVerticalScrollIndicator={false}
        ListHeaderComponent={
          queuedArticles.length > 0 ? (
            <Text style={styles.sectionHead}>
              <Text style={{ color: colors.rubric }}>{'\u2726'} </Text>
              Up Next
            </Text>
          ) : null
        }
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>Your reading queue is empty</Text>
            <Text style={styles.emptySubtitle}>
              Swipe right on articles in the feed to add them here
            </Text>
          </View>
        }
      />
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.parchment,
  },

  // Header
  header: {
    paddingHorizontal: layout.screenPadding,
    paddingTop: 12,
    paddingBottom: 8,
  },
  headerTitle: {
    ...type.screenTitle,
    color: colors.ink,
  },
  headerSubtitle: {
    ...type.screenSubtitle,
    color: colors.textMuted,
    marginTop: 2,
  },

  // Section head
  sectionHead: {
    ...type.sectionHead,
    color: colors.rubric,
    marginTop: 16,
    marginBottom: 4,
  },

  listContent: {
    paddingHorizontal: layout.screenPadding,
    paddingBottom: 40,
  },

  // Article card
  card: {
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.rule,
  },
  cardFocused: {
    borderLeftWidth: 3,
    borderLeftColor: colors.rubric,
    paddingLeft: 12,
    backgroundColor: 'rgba(139,37,0,0.03)',
  },
  cardTitle: {
    ...type.entryTitle,
    color: colors.textPrimary,
    marginBottom: 3,
  },
  cardSummary: {
    ...type.entrySummary,
    color: colors.textSecondary,
    marginBottom: 6,
  },
  cardFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  cardMeta: {
    ...type.metadata,
    color: colors.textMuted,
    flex: 1,
  },
  topicTags: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginLeft: 8,
  },
  topicTagText: {
    ...type.topicTag,
    color: colors.rubric,
  },

  // Swipe action
  swipeAction: {
    backgroundColor: colors.rubric,
    justifyContent: 'center',
    alignItems: 'flex-end',
    paddingHorizontal: 20,
    marginVertical: 2,
  },
  swipeActionText: {
    fontFamily: fonts.ui,
    fontSize: 12,
    color: colors.parchment,
  },

  // Empty state
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
    textAlign: 'center',
    paddingHorizontal: 20,
  },
});

// --- Web-specific styles ---
const webStyles = StyleSheet.create({
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    paddingBottom: 60,
  },
  centeredColumn: {
    maxWidth: layout.readingMeasure,
    marginHorizontal: 'auto' as any,
    paddingHorizontal: spacing.xxxl,
    width: '100%' as any,
  },
  backButton: {
    paddingVertical: spacing.xs,
    marginTop: spacing.sm,
    marginBottom: spacing.xs,
    alignSelf: 'flex-start',
    minHeight: layout.touchTarget,
    justifyContent: 'center',
  },
  backText: {
    fontFamily: fonts.ui,
    fontSize: 13,
    color: colors.textMuted,
    cursor: 'pointer' as any,
  },
  cardRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  cardContent: {
    flex: 1,
  },
  removeButton: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    marginLeft: 12,
    alignSelf: 'center',
    cursor: 'pointer' as any,
  },
  removeText: {
    fontFamily: fonts.ui,
    fontSize: 12,
    color: colors.rubric,
  },
});
