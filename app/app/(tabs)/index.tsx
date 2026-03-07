import { useState, useRef, useCallback } from 'react';
import {
  View, Text, StyleSheet, FlatList, Pressable, Animated,
  Platform, ViewStyle,
} from 'react-native';
import { useRouter } from 'expo-router';
import { GestureHandlerRootView, Swipeable } from 'react-native-gesture-handler';
import { getRankedFeedArticles, getReadingState, dismissArticle, getReadArticles, recordInterestSignal } from '../../data/store';
import { Article } from '../../data/types';
import { logEvent } from '../../data/logger';
import { getDisplayTitle } from '../../lib/display-utils';
import { colors, fonts, type, spacing, layout } from '../../design/tokens';

function ArticleCard({ article, onDismiss }: { article: Article; onDismiss: () => void }) {
  const router = useRouter();
  const state = getReadingState(article.id);
  const isRead = state.status === 'read';

  const renderRightActions = (_progress: Animated.AnimatedInterpolation<number>, dragX: Animated.AnimatedInterpolation<number>) => {
    const scale = dragX.interpolate({
      inputRange: [-100, 0],
      outputRange: [1, 0],
      extrapolate: 'clamp',
    });
    return (
      <Animated.View style={[styles.swipeAction, { transform: [{ scale }] }]}>
        <Text style={styles.swipeActionText}>Dismiss</Text>
      </Animated.View>
    );
  };

  const handleSwipe = () => {
    dismissArticle(article.id, 'swiped');
    recordInterestSignal('swipe_dismiss', article.id);
    onDismiss();
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
        style={({ pressed }: any) => [
          styles.card,
          isRead && styles.cardRead,
          pressed && { opacity: 0.9 },
        ] as ViewStyle[]}
        onPress={() => {
          logEvent('feed_article_tap', { article_id: article.id });
          recordInterestSignal('open_article', article.id);
          router.push({ pathname: '/reader', params: { id: article.id } });
        }}
      >
        <Text style={[styles.cardTitle, isRead && styles.cardTitleRead]} numberOfLines={2}>
          {getDisplayTitle(article)}
        </Text>
        <Text style={styles.cardHostname}>{article.hostname}</Text>
        {article.one_line_summary ? (
          <Text style={[styles.cardSummary, isRead && styles.cardSummaryRead]} numberOfLines={2}>
            {article.one_line_summary}
          </Text>
        ) : null}
        <View style={styles.cardFooter}>
          <View style={styles.topicChips}>
            {fallbackTopics.map(t => (
              <View key={t} style={styles.topicChip}>
                <Text style={styles.topicChipText}>{t}</Text>
              </View>
            ))}
          </View>
          <Text style={styles.cardReadTime}>{article.estimated_read_minutes} min</Text>
        </View>
      </Pressable>
    </Swipeable>
  );
}

export default function FeedScreen() {
  const [, forceUpdate] = useState(0);
  const feedArticles = getRankedFeedArticles();
  const readArticles = getReadArticles();

  const handleDismiss = useCallback(() => {
    forceUpdate(n => n + 1);
  }, []);

  const allItems = [
    ...feedArticles.map(a => ({ type: 'article' as const, article: a })),
    ...(readArticles.length > 0 ? [{ type: 'separator' as const, article: null as any }] : []),
    ...readArticles.map(a => ({ type: 'read' as const, article: a })),
  ];

  return (
    <GestureHandlerRootView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Petrarca</Text>
        <Text style={styles.headerCount}>{feedArticles.length} articles</Text>
      </View>

      <FlatList
        data={allItems}
        keyExtractor={(item, index) => item.article?.id || `sep-${index}`}
        renderItem={({ item }) => {
          if (item.type === 'separator') {
            return (
              <View style={styles.readSeparator}>
                <View style={styles.readSeparatorLine} />
                <Text style={styles.readSeparatorText}>Read</Text>
                <View style={styles.readSeparatorLine} />
              </View>
            );
          }
          return <ArticleCard article={item.article} onDismiss={handleDismiss} />;
        }}
        contentContainerStyle={styles.listContent}
        showsVerticalScrollIndicator={false}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>No articles yet</Text>
            <Text style={styles.emptySubtitle}>Content will appear here once synced</Text>
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
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    paddingHorizontal: layout.screenPadding,
    paddingTop: 12,
    paddingBottom: 8,
    borderBottomWidth: 2,
    borderBottomColor: colors.ink,
  },
  headerTitle: {
    ...type.screenTitle,
    color: colors.ink,
  },
  headerCount: {
    ...type.metadata,
    color: colors.textMuted,
  },
  listContent: {
    paddingHorizontal: layout.screenPadding,
    paddingBottom: 40,
  },

  // Card
  card: {
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.rule,
  },
  cardRead: {
    opacity: 0.5,
  },
  cardTitle: {
    ...type.entryTitle,
    color: colors.textPrimary,
    marginBottom: 2,
  },
  cardTitleRead: {
    color: colors.textSecondary,
  },
  cardHostname: {
    ...type.metadata,
    color: colors.textMuted,
    marginBottom: 4,
  },
  cardSummary: {
    ...type.entrySummary,
    color: colors.textSecondary,
    marginBottom: 6,
  },
  cardSummaryRead: {
    color: colors.textMuted,
  },
  cardFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  topicChips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 4,
    flex: 1,
  },
  topicChip: {
    backgroundColor: colors.parchmentDark,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 10,
  },
  topicChipText: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: colors.textSecondary,
  },
  cardReadTime: {
    ...type.metadata,
    color: colors.textMuted,
    marginLeft: 8,
  },

  // Swipe
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

  // Read separator
  readSeparator: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 16,
    gap: 12,
  },
  readSeparatorLine: {
    flex: 1,
    height: StyleSheet.hairlineWidth,
    backgroundColor: colors.rule,
  },
  readSeparatorText: {
    ...type.metadata,
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 1.5,
  },

  // Empty
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
});
