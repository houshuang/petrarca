import { useState, useRef, useCallback, useMemo, useEffect } from 'react';
import {
  View, Text, StyleSheet, FlatList, Pressable, Animated,
  Platform, ViewStyle, RefreshControl, ScrollView,
} from 'react-native';
import { useRouter, useFocusEffect } from 'expo-router';
import { GestureHandlerRootView, Swipeable } from 'react-native-gesture-handler';
import {
  getArticlesByLens, getReadingState, dismissArticle, markArticleRead,
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
import KeyboardHintBar from '../../components/KeyboardHintBar';
import { useKeyboardShortcuts, type ShortcutMap } from '../../hooks/useKeyboardShortcuts';

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

function ArticleCard({ article, onDismiss, onQueue, compact, showIngestInfo, isFocused, lens }: {
  article: Article;
  onDismiss: () => void;
  onQueue: () => void;
  compact?: boolean;
  showIngestInfo?: boolean;
  isFocused?: boolean;
  lens?: FeedLens;
}) {
  const router = useRouter();
  const state = getReadingState(article.id);
  const isRead = state.status === 'read';
  const [hovered, setHovered] = useState(false);

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

  const handleDismissCard = () => {
    dismissArticle(article.id, 'hover_dismiss');
    recordInterestSignal('swipe_dismiss', article.id);
    logEvent('feed_hover_dismiss', { article_id: article.id });
    onDismiss();
  };

  const handleArchiveCard = () => {
    markArticleRead(article.id);
    logEvent('feed_hover_archive', { article_id: article.id });
    onDismiss();
  };

  const topics = [...new Set(
    (article.interest_topics || [])
      .slice(0, 2)
      .map(t => t.specific || t.broad)
  )];
  const fallbackTopics = topics.length > 0 ? topics : [...new Set(article.topics.slice(0, 2))];

  const isWeb = Platform.OS === 'web';

  const cardContent = (
    <Pressable
      style={({ pressed }: any) => [
        styles.card,
        isRead && styles.cardRead,
        isFocused && styles.cardFocused,
        isWeb && hovered && !isFocused && styles.cardHovered,
        pressed && { opacity: 0.9 },
      ] as ViewStyle[]}
      onPress={() => {
        logEvent('feed_article_tap', { article_id: article.id });
        recordInterestSignal('open_article', article.id);
        router.push({ pathname: '/reader', params: { id: article.id, lens: lens || 'best' } });
      }}
      {...(isWeb ? {
        onMouseEnter: () => setHovered(true),
        onMouseLeave: () => setHovered(false),
      } as any : {})}
    >
      {isWeb && hovered && (
        <View style={styles.hoverActions}>
          <Pressable
            style={styles.hoverActionBtn}
            onPress={(e) => {
              e.stopPropagation();
              handleArchiveCard();
            }}
            {...{ onMouseEnter: () => setHovered(true) } as any}
          >
            <Text style={styles.hoverActionText}>{'✓'}</Text>
          </Pressable>
          <Pressable
            style={styles.hoverActionBtn}
            onPress={(e) => {
              e.stopPropagation();
              handleDismissCard();
            }}
            {...{ onMouseEnter: () => setHovered(true) } as any}
          >
            <Text style={styles.hoverActionText}>{'✕'}</Text>
          </Pressable>
        </View>
      )}
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
  );

  // On web, skip the Swipeable wrapper (not useful for desktop)
  if (isWeb) return cardContent;

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
      {cardContent}
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
  // -1 = Up Next focused (web default), >= 0 = article grid, -2 = nothing focused (mobile default)
  const [focusedIndex, setFocusedIndex] = useState(Platform.OS === 'web' ? -1 : -2);
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

  // Get article items for keyboard navigation
  const articleItems = useMemo(() =>
    listData.filter((item): item is Extract<ListItem, { type: 'article' }> => item.type === 'article'),
    [listData]
  );

  // Compute the Up Next article ID (needed by keyboard shortcuts + Recommended exclusion)
  const upNextArticleId = useMemo(() => {
    const inProgress = getInProgressArticles();
    if (inProgress[0]) return inProgress[0].id;
    const nextQueuedId = getNextQueued();
    if (nextQueuedId) return nextQueuedId;
    const top = getTopRecommendedArticle();
    return top?.id;
  }, [feedVersion]);

  // The recommended article (top ranked excluding Up Next)
  const recommendedArticle = useMemo(() => {
    const ranked = getArticlesByLens('best');
    return ranked.find(a => a.id !== upNextArticleId) || null;
  }, [upNextArticleId, feedVersion]);

  // IDs to exclude from the article grid (shown in hero sections)
  const heroArticleIds = useMemo(() => {
    const ids = new Set<string>();
    if (upNextArticleId) ids.add(upNextArticleId);
    if (recommendedArticle) ids.add(recommendedArticle.id);
    return ids;
  }, [upNextArticleId, recommendedArticle]);

  // Web grid articles (exclude hero articles shown in Up Next / Recommended)
  const webArticles = useMemo(() => {
    if (activeLens === 'topics') return [];
    return getArticlesByLens(activeLens, topicFilter).filter(a => !heroArticleIds.has(a.id));
  }, [activeLens, topicFilter, feedVersion, heroArticleIds]);

  // All navigable articles on web: recommended first, then grid articles
  const allNavArticles = useMemo(() => {
    const list: Article[] = [];
    if (recommendedArticle) list.push(recommendedArticle);
    list.push(...webArticles);
    return list;
  }, [recommendedArticle, webArticles]);

  const getFocusedArticle = useCallback(() => {
    const items = Platform.OS === 'web' ? allNavArticles : articleItems.map(i => i.article);
    if (focusedIndex < 0 || focusedIndex >= items.length) return null;
    return items[focusedIndex];
  }, [focusedIndex, articleItems, allNavArticles]);

  // Reset focused index on lens change
  useEffect(() => { setFocusedIndex(Platform.OS === 'web' ? -1 : -2); }, [activeLens]);

  const focusedArticleId = focusedIndex >= 0 && focusedIndex < articleItems.length
    ? articleItems[focusedIndex].article.id
    : null;

  // Scroll to focused article — uses DOM on web, FlatList on mobile
  const scrollToArticle = useCallback((index: number) => {
    if (Platform.OS === 'web') {
      const article = allNavArticles[index];
      if (article) {
        const el = document.getElementById(`article-${article.id}`);
        el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    } else {
      try { flatListRef.current?.scrollToIndex({ index: index + 1, viewPosition: 0.3, animated: true }); } catch {}
    }
  }, [allNavArticles, articleItems]);

  // Keyboard shortcuts (web only)
  const feedShortcuts = useMemo((): ShortcutMap => ({
    j: { handler: () => setFocusedIndex(i => {
      // From Up Next (-1), go to first article (0)
      if (i < 0) {
        scrollToArticle(0);
        return 0;
      }
      const maxIdx = (Platform.OS === 'web' ? allNavArticles.length : articleItems.length) - 1;
      const next = Math.min(i + 1, maxIdx);
      scrollToArticle(next);
      return next;
    }), label: 'next' },
    k: { handler: () => setFocusedIndex(i => {
      // From first article (0), go back to Up Next (-1)
      if (i <= 0) {
        if (Platform.OS === 'web') {
          window.scrollTo({ top: 0, behavior: 'smooth' });
        }
        return -1;
      }
      const prev = i - 1;
      scrollToArticle(prev);
      return prev;
    }), label: 'prev' },
    Enter: { handler: () => {
      // If Up Next is focused (-1), open the up next article
      if (focusedIndex === -1 && upNextArticleId) {
        const upNextArticle = getArticleById(upNextArticleId);
        if (upNextArticle) {
          logEvent('up_next_tap', { article_id: upNextArticle.id, via: 'keyboard' });
          recordInterestSignal('open_article', upNextArticle.id);
          router.push({ pathname: '/reader', params: { id: upNextArticle.id } });
          return;
        }
      }
      const a = getFocusedArticle();
      if (a) {
        logEvent('feed_article_tap', { article_id: a.id, via: 'keyboard' });
        recordInterestSignal('open_article', a.id);
        router.push({ pathname: '/reader', params: { id: a.id, lens: activeLens } });
      }
    }, label: 'open' },
    o: { handler: () => {
      if (focusedIndex === -1 && upNextArticleId) {
        const upNextArticle = getArticleById(upNextArticleId);
        if (upNextArticle) {
          logEvent('up_next_tap', { article_id: upNextArticle.id, via: 'keyboard' });
          recordInterestSignal('open_article', upNextArticle.id);
          router.push({ pathname: '/reader', params: { id: upNextArticle.id } });
          return;
        }
      }
      const a = getFocusedArticle();
      if (a) {
        logEvent('feed_article_tap', { article_id: a.id, via: 'keyboard' });
        recordInterestSignal('open_article', a.id);
        router.push({ pathname: '/reader', params: { id: a.id, lens: activeLens } });
      }
    }, label: 'open' },
    e: { handler: () => {
      const a = getFocusedArticle();
      if (a) {
        dismissArticle(a.id, 'keyboard');
        recordInterestSignal('swipe_dismiss', a.id);
        handleDismiss();
      }
    }, label: 'dismiss' },
    q: { handler: () => {
      const a = getFocusedArticle();
      if (a) { addToQueue(a.id); handleQueue(); }
    }, label: 'queue' },
    '1': { handler: () => handleLensChange('latest'), label: 'Latest' },
    '2': { handler: () => handleLensChange('best'), label: 'Best' },
    '3': { handler: () => handleLensChange('topics'), label: 'Topics' },
    '4': { handler: () => handleLensChange('quick'), label: 'Quick' },
    r: { handler: () => { if (!refreshing) handleRefresh(); }, label: 'refresh' },
    gi: { handler: () => {
      window.scrollTo({ top: 0, behavior: 'smooth' });
      setFocusedIndex(-1);
    }, label: 'go to index' },
    '?': { handler: () => {}, label: 'shortcuts' },
  }), [articleItems, allNavArticles, getFocusedArticle, activeLens, refreshing, handleLensChange, handleDismiss, handleQueue, handleRefresh, router, scrollToArticle, upNextArticleId]);

  useKeyboardShortcuts(feedShortcuts, !drawerOpen);

  const renderHeader = useCallback(() => (
    <View style={Platform.OS === 'web' ? styles.webFeedContainer : undefined}>
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
      <UpNextSection onDrawerOpen={() => setDrawerOpen(true)} isFocused={focusedIndex === -1} />
      <View nativeID={recommendedArticle ? `article-${recommendedArticle.id}` : undefined}>
        <RecommendedSection onSeeAll={handleSeeAllBest} excludeArticleId={upNextArticleId} />
      </View>
      <TopicPillsSection onTopicPress={handleTopicPress} onSeeAll={handleSeeAllTopics} />
      <DoubleRule />
    </View>
  ), [refreshing, spinAnim, handleSeeAllBest, handleTopicPress, handleSeeAllTopics, upNextArticleId, focusedIndex]);

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
              isFocused={item.article.id === focusedArticleId}
              lens={activeLens}
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
  }, [activeLens, handleLensChange, handleDismiss, handleQueue, focusedArticleId]);

  const keyExtractor = useCallback((item: ListItem, index: number) => {
    if (item.type === 'article' || item.type === 'read') return item.article.id;
    return `${item.type}-${index}`;
  }, []);

  const webReadArticles = useMemo(() => {
    if (activeLens === 'topics') return [];
    return getReadArticles();
  }, [activeLens, feedVersion]);

  // Effective focused article ID for highlighting
  const effectiveFocusedArticleId = focusedIndex >= 0 && focusedIndex < (Platform.OS === 'web' ? allNavArticles.length : articleItems.length)
    ? (Platform.OS === 'web' ? allNavArticles[focusedIndex]?.id : articleItems[focusedIndex]?.article.id)
    : null;

  // --- Web layout ---
  if (Platform.OS === 'web') {
    const webGridStyle = {
      display: 'grid' as any,
      gridTemplateColumns: '1fr 1fr' as any,
      gap: '0px 32px' as any,
      paddingLeft: 32,
      paddingRight: 32,
    } as any;

    const webStickyTabsStyle = {
      position: 'sticky' as any,
      top: 0,
      zIndex: 10,
      backgroundColor: colors.parchment,
    } as any;

    return (
      <GestureHandlerRootView style={styles.container}>
        <ScrollView
          style={styles.webScrollContainer}
          contentContainerStyle={styles.webScrollContent}
          showsVerticalScrollIndicator={false}
        >
          {renderHeader()}

          <View style={webStickyTabsStyle}>
            <LensTabs activeLens={activeLens} onLensChange={handleLensChange} />
          </View>

          <View style={styles.webFeedContainer}>
            {activeLens === 'topics' ? (
              <View style={styles.webContentPadding}>
                <TopicsGroupedList topicFilter={topicFilter} />
              </View>
            ) : webArticles.length === 0 ? (
              <View style={styles.empty}>
                <Text style={styles.emptyTitle}>No articles yet</Text>
                <Text style={styles.emptySubtitle}>Content will appear here once synced</Text>
              </View>
            ) : (
              <>
                <View style={webGridStyle}>
                  {webArticles.map(article => (
                    <View key={article.id} nativeID={`article-${article.id}`}>
                      <ArticleCard
                        article={article}
                        onDismiss={handleDismiss}
                        onQueue={handleQueue}
                        compact={activeLens === 'latest'}
                        showIngestInfo={activeLens === 'latest'}
                        isFocused={article.id === effectiveFocusedArticleId}
                        lens={activeLens}
                      />
                    </View>
                  ))}
                </View>

                {webReadArticles.length > 0 && (
                  <>
                    <View style={[styles.readSeparator, styles.webContentPadding]}>
                      <View style={styles.readSeparatorLine} />
                      <Text style={styles.readSeparatorText}>Read</Text>
                      <View style={styles.readSeparatorLine} />
                    </View>
                    <View style={webGridStyle}>
                      {webReadArticles.map(article => (
                        <View key={article.id}>
                          <ArticleCard
                            article={article}
                            onDismiss={handleDismiss}
                            onQueue={handleQueue}
                            compact
                          />
                        </View>
                      ))}
                    </View>
                  </>
                )}
              </>
            )}
          </View>
        </ScrollView>

        <KeyboardHintBar shortcuts={feedShortcuts} />
        <PetrarcaDrawer visible={drawerOpen} onClose={() => setDrawerOpen(false)} />
      </GestureHandlerRootView>
    );
  }

  // --- Mobile layout (FlatList, unchanged) ---
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
        extraData={focusedArticleId}
        contentContainerStyle={styles.listContent}
        showsVerticalScrollIndicator={false}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>No articles yet</Text>
            <Text style={styles.emptySubtitle}>Content will appear here once synced</Text>
          </View>
        }
      />

      <KeyboardHintBar shortcuts={feedShortcuts} />
      <PetrarcaDrawer visible={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.parchment,
  },
  webFeedContainer: {
    maxWidth: layout.webFeedMaxWidth,
    width: '100%',
    alignSelf: 'center' as const,
  },
  webScrollContainer: {
    flex: 1,
    backgroundColor: colors.parchment,
  },
  webScrollContent: {
    paddingBottom: 40,
  },
  webContentPadding: {
    paddingHorizontal: 32,
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
  cardFocused: {
    borderLeftWidth: 3,
    borderLeftColor: colors.rubric,
    paddingLeft: 12,
    backgroundColor: 'rgba(139,37,0,0.03)',
  },
  cardHovered: {
    backgroundColor: 'rgba(139,37,0,0.02)',
  },
  hoverActions: {
    position: 'absolute' as const,
    top: 8,
    right: 0,
    flexDirection: 'row' as const,
    gap: 4,
    zIndex: 5,
  },
  hoverActionBtn: {
    width: 26,
    height: 26,
    borderRadius: 3,
    borderWidth: 1,
    borderColor: colors.rule,
    backgroundColor: colors.parchment,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
  },
  hoverActionText: {
    fontFamily: fonts.ui,
    fontSize: 12,
    color: colors.textMuted,
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
