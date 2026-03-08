import { useState, useRef, useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, FlatList, Pressable, Animated,
  Platform, ViewStyle, ScrollView, Linking,
} from 'react-native';
import { useRouter } from 'expo-router';
import { GestureHandlerRootView, Swipeable } from 'react-native-gesture-handler';
import {
  getRankedFeedArticles, getReadingState, dismissArticle,
  getReadArticles, getArticles, recordInterestSignal,
} from '../../data/store';
import { Article } from '../../data/types';
import { logEvent } from '../../data/logger';
import { getDisplayTitle, normalizeTopic, displayTopic } from '../../lib/display-utils';
import { colors, fonts, type, spacing, layout } from '../../design/tokens';
import { isKnowledgeReady, getArticleNovelty } from '../../data/knowledge-engine';
import { addToQueue } from '../../data/queue';

// --- Continue Reading Card ---

function ContinueReadingCard({ article }: { article: Article }) {
  const router = useRouter();
  const state = getReadingState(article.id);
  const progressRatio = state.time_spent_ms > 0
    ? Math.min(state.time_spent_ms / (article.estimated_read_minutes * 60 * 1000), 0.95)
    : 0.1;

  return (
    <Pressable
      style={({ pressed }) => [
        styles.continueCard,
        pressed && { opacity: 0.9 },
      ]}
      onPress={() => {
        logEvent('continue_reading_tap', { article_id: article.id });
        recordInterestSignal('open_article', article.id);
        router.push({ pathname: '/reader', params: { id: article.id } });
      }}
    >
      <Text style={styles.continueTitle} numberOfLines={1}>
        {getDisplayTitle(article)}
      </Text>
      <Text style={styles.continueMeta}>{article.hostname}</Text>
      <View style={styles.progressTrack}>
        <View style={[styles.progressFill, { width: `${progressRatio * 100}%` }]} />
      </View>
    </Pressable>
  );
}

// --- Article Card ---

function ArticleCard({ article, onDismiss, onQueue }: {
  article: Article;
  onDismiss: () => void;
  onQueue: () => void;
}) {
  const router = useRouter();
  const state = getReadingState(article.id);
  const isRead = state.status === 'read';

  const novelty = isKnowledgeReady() ? getArticleNovelty(article.id) : null;
  const bestClaim = (article.novelty_claims || []).find(c => c.specificity === 'high')
    || (article.novelty_claims || [])[0];

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

  const topics = (article.interest_topics || [])
    .slice(0, 3)
    .map(t => t.specific || t.broad);
  const fallbackTopics = topics.length > 0 ? topics : article.topics.slice(0, 3);

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
        <Text style={[styles.cardTitle, isRead && styles.cardTitleRead]} numberOfLines={2}>
          {getDisplayTitle(article)}
        </Text>
        {article.one_line_summary ? (
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
          <View style={styles.cardFooterLeft}>
            <Text style={styles.cardMeta}>
              {article.hostname}
              {article.author ? ` \u00b7 ${article.author}` : ''}
              {` \u00b7 ${article.estimated_read_minutes} min`}
            </Text>
            {novelty ? (
              <Text style={[
                styles.noveltyHint,
                novelty.novelty_ratio > 0.5
                  ? { color: colors.claimNew }
                  : { color: colors.textMuted },
              ]}>
                {novelty.new_claims} new claim{novelty.new_claims !== 1 ? 's' : ''}
              </Text>
            ) : null}
          </View>
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

// --- Topic Filter Chip ---

function TopicChip({ label, count, active, onPress }: {
  label: string;
  count: number;
  active: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      style={[styles.filterChip, active && styles.filterChipActive]}
      onPress={onPress}
    >
      <Text style={[styles.filterChipText, active && styles.filterChipTextActive]}>
        {label} ({count})
      </Text>
    </Pressable>
  );
}

// --- Feed Screen ---

export default function FeedScreen() {
  const [, forceUpdate] = useState(0);
  const [activeTopic, setActiveTopic] = useState<string | null>(null);

  const feedArticles = useMemo(() => {
    const base = getRankedFeedArticles();
    if (!isKnowledgeReady()) return base;

    return base
      .map((a, rank) => ({ article: a, novelty: getArticleNovelty(a.id), rank }))
      .sort((a, b) => {
        const aBoost = a.novelty?.curiosity_score || 0.5;
        const bBoost = b.novelty?.curiosity_score || 0.5;
        const scoreDiff = bBoost - aBoost;
        // Only re-rank if curiosity scores differ meaningfully
        if (Math.abs(scoreDiff) > 0.05) return scoreDiff;
        return a.rank - b.rank; // preserve interest model order as tiebreaker
      })
      .map(x => x.article);
  }, []);

  const readArticles = getReadArticles();

  // Articles currently being read (started but not finished) — show max 2
  const continueReading = useMemo(() => {
    return getArticles()
      .filter(a => {
        const state = getReadingState(a.id);
        return state.status === 'reading';
      })
      .sort((a, b) => {
        const sa = getReadingState(a.id);
        const sb = getReadingState(b.id);
        return (sb.last_read_at || 0) - (sa.last_read_at || 0);
      })
      .slice(0, 2);
  }, []);

  // Gather all topics for filter chips (normalized)
  const topicCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const a of feedArticles) {
      const topics = (a.interest_topics || []).map(t => normalizeTopic(t.broad));
      const fallback = topics.length > 0 ? topics : a.topics.slice(0, 2).map(normalizeTopic);
      for (const t of fallback) {
        counts.set(t, (counts.get(t) || 0) + 1);
      }
    }
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8);
  }, [feedArticles]);

  // Filter articles by active topic (compare normalized)
  const filteredArticles = useMemo(() => {
    if (!activeTopic) return feedArticles;
    return feedArticles.filter(a => {
      const topics = (a.interest_topics || []).map(t => normalizeTopic(t.broad));
      const fallback = topics.length > 0 ? topics : a.topics.map(normalizeTopic);
      return fallback.includes(activeTopic);
    });
  }, [feedArticles, activeTopic]);

  const handleDismiss = useCallback(() => {
    forceUpdate(n => n + 1);
  }, []);

  const handleQueue = useCallback(() => {
    forceUpdate(n => n + 1);
  }, []);

  const today = new Date();
  const dateStr = today.toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  });

  const allItems = [
    ...(continueReading.length > 0 ? [{ type: 'continue' as const, article: null as any }] : []),
    ...filteredArticles.map(a => ({ type: 'article' as const, article: a })),
    ...(readArticles.length > 0 ? [{ type: 'separator' as const, article: null as any }] : []),
    ...readArticles.map(a => ({ type: 'read' as const, article: a })),
  ];

  return (
    <GestureHandlerRootView style={styles.container}>
      <View style={styles.header}>
        <View style={{ flex: 1 }}>
          <Text style={styles.headerTitle}>Petrarca</Text>
          <Text style={styles.headerSubtitle}>{dateStr}</Text>
        </View>
        <Pressable
          onPress={() => {
            logEvent('user_guide_opened');
            const url = Platform.OS === 'web' ? '/guide/' : 'https://alifstian.duckdns.org/guide/';
            Linking.openURL(url);
          }}
          style={styles.guideLink}
        >
          <Text style={styles.guideLinkText}>Guide</Text>
        </Pressable>
      </View>

      {/* Double rule */}
      <View style={styles.doubleRule}>
        <View style={styles.doubleRuleTop} />
        <View style={styles.doubleRuleGap} />
        <View style={styles.doubleRuleBottom} />
      </View>

      {/* Topic filter chips */}
      {topicCounts.length > 0 ? (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.filterRow}
          style={styles.filterScroll}
        >
          <TopicChip
            label="All"
            count={feedArticles.length}
            active={activeTopic === null}
            onPress={() => {
              setActiveTopic(null);
              logEvent('feed_filter', { topic: 'all' });
            }}
          />
          {topicCounts.map(([topic, count]) => (
            <TopicChip
              key={topic}
              label={displayTopic(topic)}
              count={count}
              active={activeTopic === topic}
              onPress={() => {
                setActiveTopic(activeTopic === topic ? null : topic);
                logEvent('feed_filter', { topic });
              }}
            />
          ))}
        </ScrollView>
      ) : null}

      <FlatList
        data={allItems}
        keyExtractor={(item, index) => item.article?.id || `section-${item.type}-${index}`}
        onViewableItemsChanged={useCallback(({ viewableItems }: any) => {
          const articleIds = viewableItems
            .filter((v: any) => v.item?.article?.id)
            .map((v: any) => v.item.article.id);
          if (articleIds.length > 0) {
            logEvent('feed_articles_visible', { article_ids: articleIds });
          }
        }, [])}
        viewabilityConfig={{ itemVisiblePercentThreshold: 50, minimumViewTime: 1000 }}
        renderItem={({ item }) => {
          if (item.type === 'continue') {
            return (
              <View style={styles.continueSection}>
                <Text style={styles.sectionHead}>
                  <Text style={{ color: colors.rubric }}>{'\u2726'} </Text>
                  Continue Reading
                </Text>
                {continueReading.map(a => (
                  <ContinueReadingCard key={a.id} article={a} />
                ))}
              </View>
            );
          }
          if (item.type === 'separator') {
            return (
              <View style={styles.readSeparator}>
                <View style={styles.readSeparatorLine} />
                <Text style={styles.readSeparatorText}>Read</Text>
                <View style={styles.readSeparatorLine} />
              </View>
            );
          }
          return (
            <ArticleCard
              article={item.article}
              onDismiss={handleDismiss}
              onQueue={handleQueue}
            />
          );
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

  // Header
  header: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
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
  guideLink: {
    alignSelf: 'flex-start',
    paddingVertical: 4,
    paddingHorizontal: 8,
    marginTop: 2,
  },
  guideLinkText: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.rubric,
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

  // Topic filter chips
  filterScroll: {
    flexGrow: 0,
    minHeight: 44,
  },
  filterRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: layout.screenPadding,
    paddingVertical: 8,
    gap: 8,
  },
  filterChip: {
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  filterChipActive: {
    backgroundColor: colors.ink,
  },
  filterChipText: {
    fontFamily: fonts.bodyItalic,
    fontSize: 12,
    color: colors.rubric,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' } : {}),
  },
  filterChipTextActive: {
    color: colors.parchment,
  },

  // Continue reading section
  continueSection: {
    paddingTop: 12,
    paddingBottom: 4,
  },
  sectionHead: {
    ...type.sectionHead,
    color: colors.rubric,
    marginBottom: 8,
  },
  continueCard: {
    paddingVertical: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.rule,
  },
  continueTitle: {
    ...type.entryTitle,
    color: colors.textPrimary,
    fontSize: 14,
    marginBottom: 2,
  },
  continueMeta: {
    ...type.metadata,
    color: colors.textMuted,
    marginBottom: 6,
  },
  progressTrack: {
    height: layout.progressBarHeight,
    backgroundColor: colors.rule,
  },
  progressFill: {
    height: layout.progressBarHeight,
    backgroundColor: colors.rubric,
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
    alignItems: 'flex-start',
  },
  cardFooterLeft: {
    flex: 1,
    gap: 2,
  },
  cardMeta: {
    ...type.metadata,
    color: colors.textMuted,
  },
  noveltyHint: {
    ...type.metadata,
    fontSize: 10,
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
