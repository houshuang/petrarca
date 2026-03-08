import { useState, useEffect, useCallback } from 'react';
import {
  View, Text, StyleSheet, FlatList, Pressable, Animated, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { GestureHandlerRootView, Swipeable } from 'react-native-gesture-handler';
import { getArticleById, recordInterestSignal } from '../../data/store';
import { Article } from '../../data/types';
import { logEvent } from '../../data/logger';
import { getDisplayTitle } from '../../lib/display-utils';
import { colors, fonts, type, spacing, layout } from '../../design/tokens';
import { loadQueue, getQueuedArticleIds, removeFromQueue } from '../../data/queue';

// --- Queue Article Card ---

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
  const [, forceUpdate] = useState(0);
  const [ready, setReady] = useState(false);

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

  if (!ready) return <View style={styles.container} />;

  return (
    <GestureHandlerRootView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Queue</Text>
        <Text style={styles.headerSubtitle}>
          {queuedArticles.length} article{queuedArticles.length !== 1 ? 's' : ''} saved to read
        </Text>
      </View>

      {/* Double rule */}
      <View style={styles.doubleRule}>
        <View style={styles.doubleRuleTop} />
        <View style={styles.doubleRuleGap} />
        <View style={styles.doubleRuleBottom} />
      </View>

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

  // Double rule
  doubleRule: {
    paddingHorizontal: layout.screenPadding,
  },
  doubleRuleTop: {
    borderTopWidth: layout.doubleRuleTop,
    borderTopColor: colors.ink,
  },
  doubleRuleGap: {
    height: layout.doubleRuleGap,
  },
  doubleRuleBottom: {
    borderTopWidth: layout.doubleRuleBottom,
    borderTopColor: colors.ink,
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
