import { useState, useRef, useCallback, useMemo, useEffect } from 'react';
import {
  View, Text, StyleSheet, FlatList, Pressable, Animated,
  Platform, ViewStyle, RefreshControl,
} from 'react-native';
import { useRouter, useFocusEffect } from 'expo-router';
import { GestureHandlerRootView, Swipeable } from 'react-native-gesture-handler';
import {
  getArticlesByLens, getReadingState, dismissArticle,
  getReadArticles, recordInterestSignal, refreshContent,
  bumpFeedVersion, getFeedVersion, getInProgressArticles,
  getTopRecommendedArticle, getArticleById,
} from '../../data/store';
import type { FeedLens } from '../../data/store';
import { Article } from '../../data/types';
import { logEvent } from '../../data/logger';
import { getDisplayTitle, displayTopic } from '../../lib/display-utils';
import { colors, fonts, type, layout } from '../../design/tokens';
import { isKnowledgeReady, getArticleNovelty } from '../../data/knowledge-engine';
import { addToQueue, getNextQueued } from '../../data/queue';
import UpNextSection from '../../components/UpNextSection';
import RecommendedSection from '../../components/RecommendedSection';
import TopicPillsSection from '../../components/TopicPillsSection';
import DoubleRule from '../../components/DoubleRule';
import LensTabs from '../../components/LensTabs';
import TopicsGroupedList from '../../components/TopicsGroupedList';
import PetrarcaDrawer from '../../components/PetrarcaDrawer';

// --- Article Card ---

function formatRelativeDate(isoOrDate: string): string {
  const date = new Date(isoOrDate.includes('T') ? isoOrDate : isoOrDate + 'T00:00:00');
  const now = Date.now();
  const diffMs = now - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 60) return `${Math.max(1, diffMins)}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays === 1) return 'yesterday';
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
  return `${Math.floor(diffDays / 30)}mo ago`;
}

function formatSourceLabel(sources: Article['sources']): string | null {
  const type = sources?.[0]?.type;
  if (!type || type === 'manual') return null;
  const labels: Record<string, string> = {
    twitter_bookmark: 'Twitter',
    readwise: 'Readwise',
    rss: 'RSS',
    exploration: 'Explored',
    research_recommendation: 'Research',
  };
  return labels[type] || null;
}

function ArticleCard({ article, onDismiss, onQueue, compact, showIngestInfo }: {
  article: Article;
  onDismiss: () => void;
  onQueue: () => void;
  compact?: boolean;
  showIngestInfo?: boolean;
}) {
  const router = useRouter();
  const state = getReadingState(article.id);
  const isRead = state.status === 'read';

  const novelty = isKnowledgeReady() ? getArticleNovelty(article.id) : null;
  const bestClaim = !compact
    ? ((article.novelty_claims || []).find(c => c.specificity === 'high')
      || (article.novelty_claims || [])[0])
    : null;

  const renderRightActions = (_progress: Animated.AnimatedInterpolation<number>, dragX: Animated.AnimatedInterpolation<number>) => {
    const scale = dragX.interpolate({
      inputRange: [-100, 0],
      outputRange: [1, 0],
      extrapolate: 'clamp',
    });
    return (
      <Animated.View style={[styles.swipeAction, styles.swipeActionDismiss, { transform: [{ scale }] }]}>
        <Text style={styles.swipeActionText}>Dismiss</Text>
      </Animated.View>
    );
  };

  const renderLeftActions = (_progress: Animated.AnimatedInterpolation<number>, dragX: Animated.AnimatedInterpolation<number>) => {
    const scale = dragX.interpolate({
      inputRange: [0, 100],
      outputRange: [0, 1],
      extrapolate: 'clamp',
    });
    return (
      <Animated.View style={[styles.swipeAction, styles.swipeActionQueue, { transform: [{ scale }] }]}>
        <Text style={styles.swipeActionText}>Queue</Text>
      </Animated.View>
    );
  };

  const handleSwipeRight = () => {
    dismissArticle(article.id, 'swiped');
    recordInterestSignal('swipe_dismiss', article.id);
    logEvent('feed_swipe_dismiss', { article_id: article.id });
    onDismiss();
  };

  const handleSwipeLeft = () => {
    addToQueue(article.id);
    logEvent('feed_swipe_queue', { article_id: article.id });
    onQueue();
  };

  const topics = [...new Set(
    (article.interest_topics || [])
      .slice(0, 2)
      .map(t => t.specific || t.broad)
  )];
  const fallbackTopics = topics.length > 0 ? topics : [...new Set(article.topics.slice(0, 2))];

  return (
    <Swipeable
      renderRightActions={renderRightActions}
      renderLeftActions={renderLeftActions}
      onSwipeableOpen={(direction) => {
        if (direction === 'right') handleSwipeRight();
        else if (direction === 'left') handleSwipeLeft();
      }}
      overshootRight={false}
      overshootLeft={false}
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
        <Text style={[styles.cardTitle, isRead && styles.cardTitleRead]} numberOfLines={compact ? 1 : 2}>
          {getDisplayTitle(article)}
        </Text>
        {!compact && article.one_line_summary ? (
          <Text style={[styles.cardSummary, isRead && styles.cardSummaryRead]} numberOfLines={2}>
            {article.one_line_summary}
          </Text>
        ) : null}

        {bestClaim && !isRead ? (
          <View style={styles.claimPreview}>
            <Text style={styles.claimPreviewText} numberOfLines={2}>
              {bestClaim.claim}
            </Text>
          </View>
        ) : null}

        <View style={styles.cardFooter}>
          <Text style={styles.cardMeta}>
            {article.hostname}
            {` · ${article.estimated_read_minutes} min`}
            {novelty && novelty.new_claims > 0
              ? ` · ${novelty.new_claims} new`
              : ''}
            {showIngestInfo && (article.ingested_at || article.date) ? ` · ${formatRelativeDate(article.ingested_at || article.date)}` : ''}
            {showIngestInfo && formatSourceLabel(article.sources) ? ` · ${formatSourceLabel(article.sources)}` : ''}
          </Text>
          <View style={styles.topicTags}>
            {fallbackTopics.map(t => (
              <Text key={t} style={styles.topicTagText}>{displayTopic(t)}</Text>
            ))}
          </View>
        </View>
      </Pressable>
    </Swipeable>
  );
}

// --- Feed Screen ---

type ListItem =
  | { type: 'lens-tabs' }
  | { type: 'topics-grouped'; topicFilter?: string }
  | { type: 'article'; article: Article }
  | { type: 'separator' }
  | { type: 'read'; article: Article };

export default function FeedScreen() {
  const router = useRouter();
  const [, forceUpdate] = useState(0);
  const [activeLens, setActiveLens] = useState<FeedLens>('best');
  const [topicFilter, setTopicFilter] = useState<string | undefined>(undefined);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const spinAnim = useRef(new Animated.Value(0)).current;
  const flatListRef = useRef<FlatList>(null);

  // Re-rank feed when screen regains focus (e.g. returning from reader)
  // This ensures reading an article deprioritizes similar content via the knowledge model
  useFocusEffect(
    useCallback(() => {
      bumpFeedVersion();
      forceUpdate(n => n + 1);
    }, [])
  );

  useEffect(() => {
    if (refreshing) {
      spinAnim.setValue(0);
      Animated.loop(
        Animated.timing(spinAnim, {
          toValue: 1,
          duration: 1200,
          useNativeDriver: true,
        }),
      ).start();
    } else {
      spinAnim.stopAnimation();
    }
  }, [refreshing]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    logEvent('feed_pull_refresh');
    try {
      await refreshContent();
    } finally {
      setRefreshing(false);
      bumpFeedVersion();
      forceUpdate(n => n + 1);
    }
  }, []);

  const handleLensChange = useCallback((lens: FeedLens) => {
    setActiveLens(lens);
    setTopicFilter(undefined);
  }, []);

  const handleTopicPress = useCallback((topic: string) => {
    setActiveLens('topics');
    setTopicFilter(topic);
  }, []);

  const handleSeeAllBest = useCallback(() => {
    setActiveLens('best');
    setTopicFilter(undefined);
  }, []);

  const handleSeeAllTopics = useCallback(() => {
    setActiveLens('topics');
    setTopicFilter(undefined);
  }, []);

  const feedVersion = getFeedVersion();

  // Build the list data based on active lens
  const listData = useMemo((): ListItem[] => {
    const items: ListItem[] = [];

    // Lens tabs are always first (will be sticky)
    items.push({ type: 'lens-tabs' });

    if (activeLens === 'topics') {
      items.push({ type: 'topics-grouped', topicFilter });
    } else {
      const articles = getArticlesByLens(activeLens, topicFilter);
      for (const a of articles) {
        items.push({ type: 'article', article: a });
      }

      // Read articles at the bottom
      const readArticles = getReadArticles();
      if (readArticles.length > 0) {
        items.push({ type: 'separator' });
        for (const a of readArticles) {
          items.push({ type: 'read', article: a });
        }
      }
    }

    return items;
  }, [activeLens, topicFilter, feedVersion]);

  const handleDismiss = useCallback(() => {
    bumpFeedVersion();
    forceUpdate(n => n + 1);
  }, []);

  const handleQueue = useCallback(() => {
    bumpFeedVersion();
    forceUpdate(n => n + 1);
  }, []);

  // Compute the Up Next article ID so Recommended can skip it
  const upNextArticleId = useMemo(() => {
    const inProgress = getInProgressArticles();
    if (inProgress[0]) return inProgress[0].id;
    const nextQueuedId = getNextQueued();
    if (nextQueuedId) return nextQueuedId;
    const top = getTopRecommendedArticle();
    return top?.id;
  }, [feedVersion]);

  const renderHeader = useCallback(() => (
    <View style={Platform.OS === 'web' ? styles.webContainer : undefined}>
      {refreshing && (
        <View style={styles.refreshOrnament}>
          <Animated.Text style={[
            styles.refreshStar,
            {
              transform: [{
                rotate: spinAnim.interpolate({
                  inputRange: [0, 1],
                  outputRange: ['0deg', '360deg'],
                }),
              }],
            },
          ]}>
            {'\u2726'}
          </Animated.Text>
        </View>
      )}
      <UpNextSection onDrawerOpen={() => setDrawerOpen(true)} />
      <RecommendedSection onSeeAll={handleSeeAllBest} excludeArticleId={upNextArticleId} />
      <TopicPillsSection onTopicPress={handleTopicPress} onSeeAll={handleSeeAllTopics} />
      <DoubleRule />
    </View>
  ), [refreshing, spinAnim, handleSeeAllBest, handleTopicPress, handleSeeAllTopics, upNextArticleId]);

  const renderItem = useCallback(({ item }: { item: ListItem }) => {
    switch (item.type) {
      case 'lens-tabs':
        return (
          <LensTabs activeLens={activeLens} onLensChange={handleLensChange} />
        );
      case 'topics-grouped':
        return (
          <View style={styles.listPadding}>
            <TopicsGroupedList topicFilter={item.topicFilter} />
          </View>
        );
      case 'article':
        return (
          <View style={styles.listPadding}>
            <ArticleCard
              article={item.article}
              onDismiss={handleDismiss}
              onQueue={handleQueue}
              compact={activeLens === 'latest'}
              showIngestInfo={activeLens === 'latest'}
            />
          </View>
        );
      case 'separator':
        return (
          <View style={[styles.readSeparator, styles.listPadding]}>
            <View style={styles.readSeparatorLine} />
            <Text style={styles.readSeparatorText}>Read</Text>
            <View style={styles.readSeparatorLine} />
          </View>
        );
      case 'read':
        return (
          <View style={styles.listPadding}>
            <ArticleCard
              article={item.article}
              onDismiss={handleDismiss}
              onQueue={handleQueue}
              compact
            />
          </View>
        );
      default:
        return null;
    }
  }, [activeLens, handleLensChange, handleDismiss, handleQueue]);

  const keyExtractor = useCallback((item: ListItem, index: number) => {
    if (item.type === 'article' || item.type === 'read') return item.article.id;
    return `${item.type}-${index}`;
  }, []);

  return (
    <GestureHandlerRootView style={styles.container}>
      <FlatList
        ref={flatListRef}
        data={listData}
        keyExtractor={keyExtractor}
        ListHeaderComponent={renderHeader}
        stickyHeaderIndices={[0]}
        renderItem={renderItem}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={handleRefresh}
            tintColor="transparent"
            colors={['transparent']}
            style={{ backgroundColor: 'transparent' }}
          />
        }
        onViewableItemsChanged={useCallback(({ viewableItems }: any) => {
          const articleIds = viewableItems
            .filter((v: any) => v.item?.article?.id)
            .map((v: any) => v.item.article.id);
          if (articleIds.length > 0) {
            logEvent('feed_articles_visible', { article_ids: articleIds });
          }
        }, [])}
        viewabilityConfig={{ itemVisiblePercentThreshold: 50, minimumViewTime: 1000 }}
        contentContainerStyle={styles.listContent}
        showsVerticalScrollIndicator={false}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>No articles yet</Text>
            <Text style={styles.emptySubtitle}>Content will appear here once synced</Text>
          </View>
        }
      />

      <PetrarcaDrawer visible={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.parchment,
  },
  webContainer: {
    maxWidth: layout.contentMaxWidth,
    width: '100%',
    alignSelf: 'center',
  },

  listContent: {
    paddingBottom: 40,
    ...(Platform.OS === 'web' ? { maxWidth: layout.contentMaxWidth, width: '100%', alignSelf: 'center' as const } : {}),
  },
  listPadding: {
    paddingHorizontal: layout.screenPadding,
  },

  // Pull-to-refresh ornament
  refreshOrnament: {
    alignItems: 'center' as const,
    paddingVertical: 12,
  },
  refreshStar: {
    fontFamily: fonts.display,
    fontSize: 22,
    color: colors.rubric,
  },

  // Article card
  card: {
    paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.rule,
  },
  cardRead: {
    opacity: 0.5,
  },
  cardTitle: {
    ...type.entryTitle,
    color: colors.textPrimary,
    marginBottom: 3,
  },
  cardTitleRead: {
    color: colors.textSecondary,
  },
  cardSummary: {
    ...type.entrySummary,
    color: colors.textSecondary,
    marginBottom: 6,
  },
  cardSummaryRead: {
    color: colors.textMuted,
  },

  // Claim preview
  claimPreview: {
    borderLeftWidth: layout.claimBorderWidth,
    borderLeftColor: colors.claimNew,
    paddingLeft: 10,
    marginBottom: 8,
    marginTop: 2,
  },
  claimPreviewText: {
    fontFamily: fonts.reading,
    fontSize: 12,
    lineHeight: 17,
    color: colors.textBody,
  },

  // Card footer
  cardFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
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

  // Swipe actions
  swipeAction: {
    justifyContent: 'center',
    paddingHorizontal: 20,
    marginVertical: 2,
  },
  swipeActionDismiss: {
    backgroundColor: colors.rubric,
    alignItems: 'flex-end',
  },
  swipeActionQueue: {
    backgroundColor: colors.claimNew,
    alignItems: 'flex-start',
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
  },
});
