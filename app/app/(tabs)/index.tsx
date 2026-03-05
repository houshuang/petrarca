import { useState, useRef, useCallback, useEffect } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, Dimensions,
  Animated, PanResponder, LayoutAnimation, Platform, UIManager,
  ViewStyle,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { getArticles, getFeedArticles, getInProgressArticles, getReadingState, getStats, getNoveltyScore, getExplorationOrder, getSynthesisForTopic, isDismissed, getReviewQueue, getBooks, getBookReadingState, getBookProgress, getBooksNeedingContextRestore, getSectionReadingState } from '../../data/store';
import { fetchResearchResults, getResearchResults } from '../../data/research';
import { Article, ReadingDepth, Book } from '../../data/types';
import { logEvent } from '../../data/logger';
import { getDisplayTitle } from '../../lib/display-utils';
import { useIsDesktopWeb } from '../../lib/use-responsive';
import { colors, fonts, type, spacing, layout } from '../../design/tokens';

// Enable LayoutAnimation on Android
if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

// --- Types ---

type ViewMode = 'list' | 'topics' | 'triage';
type TriageState = 'untriaged' | 'read_later' | 'skipped';

// --- Triage persistence (local to this module) ---

const TRIAGE_KEY = '@petrarca/triage_states';

let triageCache: Record<string, TriageState> = {};
let triageLoaded = false;

async function loadTriageStates(): Promise<Record<string, TriageState>> {
  if (triageLoaded) return triageCache;
  try {
    const raw = await AsyncStorage.getItem(TRIAGE_KEY);
    if (raw) triageCache = JSON.parse(raw);
  } catch (e) {
    console.warn('[triage] failed to load:', e);
  }
  triageLoaded = true;
  return triageCache;
}

async function saveTriageStates(): Promise<void> {
  try {
    await AsyncStorage.setItem(TRIAGE_KEY, JSON.stringify(triageCache));
  } catch (e) {
    console.warn('[triage] failed to save:', e);
  }
}

function getTriageState(articleId: string): TriageState {
  return triageCache[articleId] || 'untriaged';
}

function setTriageState(articleId: string, state: TriageState) {
  triageCache[articleId] = state;
  saveTriageStates();
}

// --- Constants ---

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');
const SWIPE_THRESHOLD = SCREEN_WIDTH * 0.3;
const SWIPE_UP_THRESHOLD = SCREEN_HEIGHT * 0.15;
const ROTATION_FACTOR = 15; // degrees of rotation at full swipe

const DEPTH_LABELS: Record<ReadingDepth, string> = {
  unread: '',
  summary: 'Summary',
  claims: 'Claims',
  sections: 'Sections',
  full: 'Full',
};

const DEPTH_COLORS: Record<ReadingDepth, string> = {
  unread: colors.textMuted,
  summary: colors.info,
  claims: colors.rubric,
  sections: colors.warning,
  full: colors.success,
};

// --- Feed Card (used in List and Topic modes) ---

function NoveltyBadge({ articleId }: { articleId: string }) {
  const score = getNoveltyScore(articleId);
  if (score === null) return null;
  const pct = Math.round(score * 100);
  let label: string;
  if (pct >= 90) { label = 'Mostly new'; }
  else if (pct > 60) { label = `${pct}% new`; }
  else if (pct > 30) { label = 'Partly familiar'; }
  else { label = 'Mostly known'; }
  return (
    <Text style={styles.noveltyText}>{label}</Text>
  );
}

const TIER_CONFIG: Record<string, { label: string }> = {
  foundational: { label: 'Start here' },
  intermediate: { label: 'Building on' },
  deep: { label: 'Deep dive' },
};

function TierBadge({ readingOrder }: { readingOrder?: string }) {
  if (!readingOrder || !TIER_CONFIG[readingOrder]) return null;
  const { label } = TIER_CONFIG[readingOrder];
  return (
    <Text style={styles.tierText}>{label}</Text>
  );
}

function FeedCard({ article }: { article: Article }) {
  const router = useRouter();
  const state = getReadingState(article.id);

  const metaParts: string[] = [];
  if (article.hostname) metaParts.push(article.hostname);
  if (article.estimated_read_minutes) metaParts.push(`${article.estimated_read_minutes} min`);
  if (article.author) metaParts.push(article.author);

  return (
    <Pressable
      style={({ hovered }: any) => [
        styles.entryRow,
        hovered && Platform.OS === 'web' && { backgroundColor: colors.parchmentHover },
      ] as ViewStyle[]}
      onPress={() => {
        logEvent('feed_item_tap', { article_id: article.id, title: article.title, novelty: getNoveltyScore(article.id) });
        router.push({ pathname: '/reader', params: { id: article.id } });
      }}
    >
      <View style={styles.entryContent}>
        <Text style={styles.entryTitle}>{getDisplayTitle(article)}</Text>

        {article.one_line_summary && article.one_line_summary !== '[dry run]' && (
          <Text style={styles.entrySummary} numberOfLines={2}>{article.one_line_summary}</Text>
        )}

        <View style={styles.entryTopics}>
          {article.topics.slice(0, 3).map(t => (
            <Text key={t} style={styles.topicTag}>{t}</Text>
          ))}
          <TierBadge readingOrder={article.reading_order || article.exploration_tier} />
          <NoveltyBadge articleId={article.id} />
        </View>

        <Text style={styles.entryMeta}>{metaParts.join(' \u00B7 ')}</Text>

        {/* Dedup indicator */}
        {article.similar_articles && article.similar_articles.length > 0 && (() => {
          const readSimilar = article.similar_articles!.filter(sa => {
            const s = getReadingState(sa.id);
            return s.depth !== 'unread';
          });
          if (readSimilar.length === 0) return null;
          return (
            <Text style={styles.dedupIndicator}>
              Similar to: {readSimilar[0].title}
            </Text>
          );
        })()}
      </View>

      <View style={styles.entrySidebar}>
        <Text style={styles.sideLabel}>TIME</Text>
        <Text style={styles.sideValue}>{article.estimated_read_minutes} min</Text>

        {state.depth !== 'unread' && (
          <>
            <Text style={[styles.sideLabel, { marginTop: 8 }]}>DEPTH</Text>
            <Text style={[styles.sideNote, { color: DEPTH_COLORS[state.depth] }]}>
              {DEPTH_LABELS[state.depth]}
            </Text>
          </>
        )}
      </View>
    </Pressable>
  );
}

// --- Triage Card (swipeable) ---

function TriageCard({
  article,
  isTop,
  stackIndex,
  onSwipe,
}: {
  article: Article;
  isTop: boolean;
  stackIndex: number;
  onSwipe: (direction: 'left' | 'right' | 'up') => void;
}) {
  const pan = useRef(new Animated.ValueXY()).current;
  const isTopRef = useRef(isTop);
  const onSwipeRef = useRef(onSwipe);
  isTopRef.current = isTop;
  onSwipeRef.current = onSwipe;

  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => isTopRef.current,
      onMoveShouldSetPanResponder: (_, g) =>
        isTopRef.current && (Math.abs(g.dx) > 5 || Math.abs(g.dy) > 5),
      onPanResponderGrant: () => {
        pan.setOffset({ x: (pan.x as any)._value || 0, y: (pan.y as any)._value || 0 });
        pan.setValue({ x: 0, y: 0 });
      },
      onPanResponderMove: Animated.event([null, { dx: pan.x, dy: pan.y }], {
        useNativeDriver: false,
      }),
      onPanResponderRelease: (_, gesture) => {
        pan.flattenOffset();
        const doSwipe = onSwipeRef.current;
        if (gesture.dy < -SWIPE_UP_THRESHOLD && Math.abs(gesture.dx) < SWIPE_THRESHOLD) {
          Animated.timing(pan, {
            toValue: { x: 0, y: -SCREEN_HEIGHT },
            duration: 250,
            useNativeDriver: false,
          }).start(() => {
            pan.setValue({ x: 0, y: 0 });
            doSwipe('up');
          });
        } else if (gesture.dx > SWIPE_THRESHOLD) {
          Animated.timing(pan, {
            toValue: { x: SCREEN_WIDTH + 100, y: gesture.dy },
            duration: 250,
            useNativeDriver: false,
          }).start(() => {
            pan.setValue({ x: 0, y: 0 });
            doSwipe('right');
          });
        } else if (gesture.dx < -SWIPE_THRESHOLD) {
          Animated.timing(pan, {
            toValue: { x: -SCREEN_WIDTH - 100, y: gesture.dy },
            duration: 250,
            useNativeDriver: false,
          }).start(() => {
            pan.setValue({ x: 0, y: 0 });
            doSwipe('left');
          });
        } else {
          Animated.spring(pan, {
            toValue: { x: 0, y: 0 },
            friction: 5,
            tension: 40,
            useNativeDriver: false,
          }).start();
        }
      },
    })
  ).current;

  // Rotation interpolation
  const rotate = pan.x.interpolate({
    inputRange: [-SCREEN_WIDTH, 0, SCREEN_WIDTH],
    outputRange: [`-${ROTATION_FACTOR}deg`, '0deg', `${ROTATION_FACTOR}deg`],
    extrapolate: 'clamp',
  });

  // Opacity for action labels
  const rightOpacity = pan.x.interpolate({
    inputRange: [0, SWIPE_THRESHOLD * 0.5, SWIPE_THRESHOLD],
    outputRange: [0, 0.5, 1],
    extrapolate: 'clamp',
  });

  const leftOpacity = pan.x.interpolate({
    inputRange: [-SWIPE_THRESHOLD, -SWIPE_THRESHOLD * 0.5, 0],
    outputRange: [1, 0.5, 0],
    extrapolate: 'clamp',
  });

  const upOpacity = pan.y.interpolate({
    inputRange: [-SWIPE_UP_THRESHOLD, -SWIPE_UP_THRESHOLD * 0.5, 0],
    outputRange: [1, 0.5, 0],
    extrapolate: 'clamp',
  });

  // Stack effect for non-top cards
  const scale = isTop ? 1 : 1 - stackIndex * 0.04;
  const translateY = isTop ? 0 : stackIndex * 8;

  const cardStyle = isTop
    ? {
        transform: [
          { translateX: pan.x },
          { translateY: pan.y },
          { rotate },
        ],
        zIndex: 10,
      }
    : {
        transform: [
          { scale },
          { translateY },
        ],
        zIndex: 10 - stackIndex,
        opacity: 1 - stackIndex * 0.15,
      };

  return (
    <Animated.View
      style={[styles.triageCardWrapper, cardStyle]}
      {...(isTop && Platform.OS !== 'web' ? panResponder.panHandlers : {})}
    >
      <View style={styles.triageCard}>
        {/* Action labels */}
        {isTop && (
          <>
            <Animated.View style={[styles.actionLabel, styles.actionLabelRight, { opacity: rightOpacity }]}>
              <Text style={[styles.actionLabelText, { color: colors.success }]}>Read Later</Text>
            </Animated.View>
            <Animated.View style={[styles.actionLabel, styles.actionLabelLeft, { opacity: leftOpacity }]}>
              <Text style={[styles.actionLabelText, { color: colors.danger }]}>Skip</Text>
            </Animated.View>
            <Animated.View style={[styles.actionLabel, styles.actionLabelTop, { opacity: upOpacity }]}>
              <Text style={[styles.actionLabelText, { color: colors.info }]}>Read Now</Text>
            </Animated.View>
          </>
        )}

        {/* Card content */}
        <View style={styles.triageCardContent}>
          <View style={styles.triageSourceRow}>
            <Text style={styles.triageHostname}>{article.hostname}</Text>
            <Text style={styles.triageReadTime}>{article.estimated_read_minutes} min read</Text>
          </View>

          <Text style={styles.triageTitle}>{getDisplayTitle(article)}</Text>

          {article.one_line_summary && article.one_line_summary !== '[dry run]' && (
            <Text style={styles.triageSummary}>{article.one_line_summary}</Text>
          )}

          <View style={styles.triageTopics}>
            {article.topics.slice(0, 5).map(t => (
              <Text key={t} style={styles.triageTopicTag}>{t}</Text>
            ))}
          </View>

          {article.author ? (
            <Text style={styles.triageAuthor}>by {article.author}</Text>
          ) : null}
        </View>

        {/* Swipe hints (mobile) / Action buttons (web) */}
        {isTop && Platform.OS !== 'web' && (
          <View style={styles.swipeHints}>
            <View style={styles.swipeHint}>
              <Ionicons name="arrow-back" size={14} color={colors.textMuted} />
              <Text style={styles.swipeHintText}>Skip</Text>
            </View>
            <View style={styles.swipeHint}>
              <Ionicons name="arrow-up" size={14} color={colors.textMuted} />
              <Text style={styles.swipeHintText}>Read Now</Text>
            </View>
            <View style={styles.swipeHint}>
              <Ionicons name="arrow-forward" size={14} color={colors.textMuted} />
              <Text style={styles.swipeHintText}>Save</Text>
            </View>
          </View>
        )}
        {isTop && Platform.OS === 'web' && (
          <View style={styles.webTriageButtons}>
            <Pressable
              style={({ hovered }: any) => [
                styles.webTriageBtn,
                styles.webTriageBtnSkip,
                hovered && { backgroundColor: 'rgba(139,37,0,0.08)' },
              ] as ViewStyle[]}
              onPress={() => onSwipe('left')}
            >
              <Text style={[styles.webTriageBtnText, { color: colors.danger }]}>Skip</Text>
            </Pressable>
            <Pressable
              style={({ hovered }: any) => [
                styles.webTriageBtn,
                styles.webTriageBtnRead,
                hovered && { backgroundColor: 'rgba(42,74,106,0.08)' },
              ] as ViewStyle[]}
              onPress={() => onSwipe('up')}
            >
              <Text style={[styles.webTriageBtnText, { color: colors.info }]}>Read Now</Text>
            </Pressable>
            <Pressable
              style={({ hovered }: any) => [
                styles.webTriageBtn,
                styles.webTriageBtnSave,
                hovered && { backgroundColor: 'rgba(42,122,74,0.08)' },
              ] as ViewStyle[]}
              onPress={() => onSwipe('right')}
            >
              <Text style={[styles.webTriageBtnText, { color: colors.success }]}>Save</Text>
            </Pressable>
          </View>
        )}
      </View>
    </Animated.View>
  );
}

// --- Triage Mode ---

function TriageModeView() {
  const router = useRouter();
  const articles = getArticles().filter(a => !isDismissed(a.id));
  const [triageStates, setTriageStates] = useState<Record<string, TriageState>>({});
  const [currentIndex, setCurrentIndex] = useState(0);

  // Load triage states and compute initial index
  useEffect(() => {
    (async () => {
      const states = await loadTriageStates();
      setTriageStates({ ...states });
      // Find first untriaged article
      const firstUntriaged = articles.findIndex(a => !states[a.id] || states[a.id] === 'untriaged');
      if (firstUntriaged >= 0) setCurrentIndex(firstUntriaged);
      else setCurrentIndex(articles.length); // all triaged
    })();
    logEvent('triage_mode_enter', { total_articles: articles.length });
  }, []);

  const untriagedArticles = articles
    .filter(a => getTriageState(a.id) === 'untriaged')
    .sort((a, b) => {
      const orderA = getExplorationOrder(a);
      const orderB = getExplorationOrder(b);
      if (orderA !== orderB) return orderA - orderB;
      const scoreA = getNoveltyScore(a.id) ?? 1.0;
      const scoreB = getNoveltyScore(b.id) ?? 1.0;
      return scoreB - scoreA;
    });
  const totalUntriaged = untriagedArticles.length;
  const visibleCards = untriagedArticles.slice(0, 3);

  const handleSwipe = useCallback((direction: 'left' | 'right' | 'up') => {
    const article = untriagedArticles[0];
    if (!article) return;

    const decisionTimeMs = Date.now(); // simplified

    if (direction === 'right') {
      setTriageState(article.id, 'read_later');
      logEvent('triage_swipe', {
        direction: 'right',
        decision: 'read_later',
        article_id: article.id,
        title: article.title,
        novelty: getNoveltyScore(article.id),
      });
    } else if (direction === 'left') {
      setTriageState(article.id, 'skipped');
      logEvent('triage_swipe', {
        direction: 'left',
        decision: 'skipped',
        article_id: article.id,
        title: article.title,
        novelty: getNoveltyScore(article.id),
      });
    } else if (direction === 'up') {
      setTriageState(article.id, 'read_later');
      logEvent('triage_swipe', {
        direction: 'up',
        decision: 'read_now',
        article_id: article.id,
        title: article.title,
        novelty: getNoveltyScore(article.id),
      });
      router.push({ pathname: '/reader', params: { id: article.id } });
    }

    // Force re-render with updated triage cache
    setTriageStates({ ...triageCache });
  }, [untriagedArticles, router]);

  // Log triage complete once
  const triageCompleteLogged = useRef(false);
  useEffect(() => {
    if (totalUntriaged === 0 && !triageCompleteLogged.current) {
      triageCompleteLogged.current = true;
      const readLaterCount = articles.filter(a => getTriageState(a.id) === 'read_later').length;
      const skippedCount = articles.filter(a => getTriageState(a.id) === 'skipped').length;
      logEvent('triage_complete', { read_later: readLaterCount, skipped: skippedCount, total: articles.length });
    }
    if (totalUntriaged > 0) triageCompleteLogged.current = false;
  }, [totalUntriaged]);

  // Completion state
  if (totalUntriaged === 0) {
    const readLaterCount = articles.filter(a => getTriageState(a.id) === 'read_later').length;
    const skippedCount = articles.filter(a => getTriageState(a.id) === 'skipped').length;

    return (
      <View style={styles.triageComplete}>
        <Text style={styles.triageCompleteTitle}>All caught up</Text>
        <Text style={styles.triageCompleteSubtitle}>
          {readLaterCount} saved · {skippedCount} skipped
        </Text>
        <Pressable
          style={styles.triageResetButton}
          onPress={() => {
            // Reset all triage states
            for (const a of articles) {
              triageCache[a.id] = 'untriaged';
            }
            saveTriageStates();
            setTriageStates({ ...triageCache });
            logEvent('triage_reset');
          }}
        >
          <Text style={styles.triageResetText}>Reset triage</Text>
        </Pressable>
      </View>
    );
  }

  const processedCount = articles.length - totalUntriaged;

  return (
    <View style={styles.triageContainer}>
      <View style={styles.triageCounter}>
        <Text style={styles.triageCounterText}>
          {totalUntriaged} remaining
        </Text>
      </View>

      <View style={styles.triageStack}>
        {visibleCards.map((article, index) => (
          <TriageCard
            key={article.id}
            article={article}
            isTop={index === 0}
            stackIndex={index}
            onSwipe={handleSwipe}
          />
        )).reverse()}
      </View>
    </View>
  );
}

// --- Synthesis Card ---

function SynthesisCard({ topic, articleCount }: { topic: string; articleCount: number }) {
  const synthesis = getSynthesisForTopic(topic);
  const [expanded, setExpanded] = useState(false);

  if (!synthesis) return null;

  return (
    <Pressable
      style={styles.synthesisCard}
      onPress={() => {
        const next = !expanded;
        setExpanded(next);
        LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
        if (next) {
          logEvent('synthesis_viewed', { topic, article_count: articleCount });
        }
      }}
    >
      <View style={styles.synthesisHeader}>
        <Text style={styles.synthesisTitle}>
          Synthesis across {articleCount} articles
        </Text>
        <Ionicons
          name={expanded ? 'chevron-up' : 'chevron-down'}
          size={14}
          color={colors.textMuted}
        />
      </View>
      {expanded && (
        <Text style={styles.synthesisText}>{synthesis.synthesis_text}</Text>
      )}
    </Pressable>
  );
}

// --- Topic Clustering Mode ---

interface TopicCluster {
  topic: string;
  articles: Article[];
}

function TopicsModeView() {
  const router = useRouter();
  const articles = getArticles().filter(a => !isDismissed(a.id));
  const [expandedTopics, setExpandedTopics] = useState<Set<string>>(new Set());

  // Group by primary topic
  const clusters: TopicCluster[] = (() => {
    const map = new Map<string, Article[]>();
    for (const a of articles) {
      const topic = a.topics[0] || 'Uncategorized';
      if (!map.has(topic)) map.set(topic, []);
      map.get(topic)!.push(a);
    }
    return Array.from(map.entries())
      .map(([topic, arts]) => ({ topic, articles: arts }))
      .sort((a, b) => b.articles.length - a.articles.length);
  })();

  const toggleTopic = (topic: string) => {
    setExpandedTopics(prev => {
      const next = new Set(prev);
      if (next.has(topic)) {
        next.delete(topic);
        logEvent('cluster_collapse', { topic, article_count: clusters.find(c => c.topic === topic)?.articles.length });
      } else {
        next.add(topic);
        logEvent('cluster_expand', { topic, article_count: clusters.find(c => c.topic === topic)?.articles.length });
      }
      LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
      return next;
    });
  };

  return (
    <ScrollView style={styles.scroll} showsVerticalScrollIndicator={false}>
      {clusters.map(cluster => {
        const isExpanded = expandedTopics.has(cluster.topic);
        return (
          <View key={cluster.topic} style={styles.clusterContainer}>
            <Pressable
              style={styles.clusterHeader}
              onPress={() => toggleTopic(cluster.topic)}
            >
              <View style={styles.clusterHeaderLeft}>
                <Ionicons
                  name={isExpanded ? 'chevron-down' : 'chevron-forward'}
                  size={16}
                  color={colors.textMuted}
                />
                <Text style={styles.clusterTopic}>{cluster.topic}</Text>
              </View>
              <Text style={styles.clusterCount}>{cluster.articles.length}</Text>
            </Pressable>
            {isExpanded && (
              <View style={styles.clusterArticles}>
                <SynthesisCard topic={cluster.topic} articleCount={cluster.articles.length} />
                {cluster.articles.map(a => (
                  <FeedCard key={a.id} article={a} />
                ))}
              </View>
            )}
          </View>
        );
      })}
      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

// --- Main Feed Screen ---

export default function FeedScreen() {
  const router = useRouter();
  const isDesktop = useIsDesktopWeb();
  const [viewMode, setViewMode] = useState<ViewMode>('list');
  const [showAll, setShowAll] = useState(false);
  const [, forceUpdate] = useState(0);
  const [triageReady, setTriageReady] = useState(false);
  const [newResearchCount, setNewResearchCount] = useState(0);
  const [webBannerDismissed, setWebBannerDismissed] = useState(false);

  // Pre-load triage states + auto-fetch research results
  useEffect(() => {
    loadTriageStates().then(() => setTriageReady(true));
    fetchResearchResults().then(count => {
      if (count > 0) {
        setNewResearchCount(count);
        logEvent('research_results_fetched', { new_count: count });
      }
    }).catch(() => {});
  }, []);

  const allArticles = getArticles().filter(a => !isDismissed(a.id));
  const feed = showAll ? allArticles : getFeedArticles().filter(a => !isDismissed(a.id));
  const stats = getStats();

  // In list mode after triage, show only read_later items if any have been triaged
  const listArticles = (() => {
    if (!triageReady) return feed;
    const hasTriaged = allArticles.some(a => getTriageState(a.id) !== 'untriaged');
    if (!hasTriaged) return feed;
    // Show read_later items, plus untriaged if showAll
    if (showAll) return allArticles;
    return feed.filter(a => {
      const ts = getTriageState(a.id);
      return ts === 'read_later' || ts === 'untriaged';
    });
  })().sort((a, b) => {
    const orderA = getExplorationOrder(a);
    const orderB = getExplorationOrder(b);
    if (orderA !== orderB) return orderA - orderB;
    const scoreA = getNoveltyScore(a.id) ?? 1.0;
    const scoreB = getNoveltyScore(b.id) ?? 1.0;
    return scoreB - scoreA;
  });

  const handleViewModeChange = (mode: ViewMode) => {
    setViewMode(mode);
    logEvent('feed_view_mode', { mode });
  };

  return (
    <View style={[styles.container, isDesktop && styles.desktopContainer]}>
      {/* Compact header: title + view mode on one row */}
      <View style={styles.screenHeader}>
        <View style={styles.headerTitleRow}>
          <Text style={styles.screenTitle}>{isDesktop ? 'Feed' : 'Petrarca'}</Text>
          <View style={styles.viewModeRow}>
            {(['list', 'topics', 'triage'] as ViewMode[]).map(mode => (
              <Pressable
                key={mode}
                style={[styles.viewModeButton, viewMode === mode && styles.viewModeButtonActive]}
                onPress={() => handleViewModeChange(mode)}
              >
                <Text style={[styles.viewModeText, viewMode === mode && styles.viewModeTextActive]}>
                  {mode === 'list' ? 'List' : mode === 'topics' ? 'Topics' : 'Triage'}
                </Text>
              </Pressable>
            ))}
          </View>
        </View>
        {!isDesktop && (
          <View style={styles.sectionNav}>
            {[
              { label: 'Library', path: '/library' },
              { label: 'Review', path: '/review' },
              { label: 'Progress', path: '/stats' },
            ].map(({ label, path }, i) => (
              <Pressable key={path} onPress={() => { logEvent('section_nav', { target: path }); router.push(path as any); }}>
                <Text style={styles.sectionNavText}>{i > 0 ? ' · ' : ''}{label}</Text>
              </Pressable>
            ))}
          </View>
        )}
        <View style={styles.headerRule} />
      </View>

      {Platform.OS === 'web' && !webBannerDismissed && (() => {
        const reviewCount = getReviewQueue().length;
        if (reviewCount === 0) return null;
        return (
          <Pressable
            style={styles.webReviewBanner}
            onPress={() => {
              logEvent('web_review_banner_tap', { review_count: reviewCount });
              setWebBannerDismissed(true);
              router.push('/review');
            }}
          >
            <Text style={styles.webReviewBannerText}>
              {reviewCount} concept{reviewCount !== 1 ? 's' : ''} to review
            </Text>
            <Ionicons name="chevron-forward" size={14} color={colors.textMuted} />
          </Pressable>
        );
      })()}

      {viewMode === 'list' && (
        <>
          <View style={styles.headerRow}>
            <Pressable onPress={() => {
              logEvent('feed_toggle_filter', { show_all: !showAll });
              setShowAll(!showAll);
            }}>
              <Text style={styles.filterToggle}>{showAll ? 'Unread only' : 'Show all'}</Text>
            </Pressable>
            <Pressable onPress={() => forceUpdate(n => n + 1)}>
              <Text style={styles.filterToggle}>Refresh</Text>
            </Pressable>
          </View>

          {stats.read > 0 && (
            <View style={styles.progressRow}>
              <View style={styles.progressBar}>
                <View style={[styles.progressFill, { width: `${Math.round((stats.read / stats.total) * 100)}%` }]} />
              </View>
              <Text style={styles.progressLabel}>{stats.read}/{stats.total} read</Text>
            </View>
          )}

          <ScrollView style={styles.scroll} showsVerticalScrollIndicator={false}>
            {/* Research results banner */}
            {newResearchCount > 0 && (
              <Pressable
                style={styles.researchResultsBanner}
                onPress={() => {
                  logEvent('research_results_banner_tap', { count: newResearchCount });
                  setNewResearchCount(0);
                  router.push('/stats');
                }}
              >
                <Text style={styles.researchResultsBannerText}>
                  {newResearchCount} research result{newResearchCount !== 1 ? 's' : ''} ready
                </Text>
                <Ionicons name="chevron-forward" size={14} color={colors.textMuted} />
              </Pressable>
            )}

            {/* Continue Reading section — articles + books */}
            {(() => {
              const inProgress = getInProgressArticles();
              const booksNeedingRestore = getBooksNeedingContextRestore();
              const inProgressBooks = getBooks().filter(b => {
                const progress = getBookProgress(b.id);
                return progress.read > 0 && progress.pct < 100;
              });
              if (inProgress.length === 0 && inProgressBooks.length === 0) return null;
              return (
                <View style={styles.continueSection}>
                  <Text style={styles.sectionHeading}>{'\u2726'} CONTINUE READING</Text>
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 16 }}>
                    {inProgressBooks.map(book => {
                      const progress = getBookProgress(book.id);
                      const restoreInfo = booksNeedingRestore.find(r => r.book.id === book.id);
                      // Find next unread section
                      let nextSectionLabel = '';
                      let nextSid = '';
                      for (const ch of book.chapters.filter(c => c.processing_status === 'completed')) {
                        for (let s = 1; s <= ch.section_count; s++) {
                          const sid = `${book.id}:ch${ch.chapter_number}:s${s}`;
                          const ss = getSectionReadingState(book.id, sid);
                          if (ss.depth === 'unread') {
                            nextSectionLabel = `Ch ${ch.chapter_number}, §${s}`;
                            nextSid = sid;
                            break;
                          }
                        }
                        if (nextSid) break;
                      }
                      return (
                        <Pressable
                          key={`book-${book.id}`}
                          style={[styles.continueCard, { borderLeftColor: colors.info }]}
                          onPress={() => {
                            logEvent('continue_book_tap', { book_id: book.id, pct: progress.pct });
                            if (restoreInfo) {
                              router.push({ pathname: '/book-reader', params: { bookId: book.id, sectionId: restoreInfo.lastSectionId } });
                            } else if (nextSid) {
                              router.push({ pathname: '/book-reader', params: { bookId: book.id, sectionId: nextSid } });
                            } else {
                              router.push({ pathname: '/book-reader', params: { bookId: book.id, sectionId: '' } });
                            }
                          }}
                        >
                          <Text style={styles.continueCardLabel}>BOOK</Text>
                          <Text style={styles.continueCardTitle} numberOfLines={2}>{book.title}</Text>
                          <Text style={styles.continueCardDepth}>{progress.pct}% · {progress.read}/{progress.total} sections</Text>
                          {nextSectionLabel && (
                            <Text style={[styles.continueCardDepth, { color: colors.success }]}>Next: {nextSectionLabel}</Text>
                          )}
                          {restoreInfo && restoreInfo.daysSince >= 2 && (
                            <Text style={[styles.continueCardDepth, { color: colors.warning }]}>{restoreInfo.daysSince}d ago</Text>
                          )}
                        </Pressable>
                      );
                    })}
                    {inProgress.map(a => {
                      const state = getReadingState(a.id);
                      return (
                        <Pressable
                          key={a.id}
                          style={styles.continueCard}
                          onPress={() => {
                            logEvent('continue_reading_tap', { article_id: a.id, depth: state.depth });
                            router.push({ pathname: '/reader', params: { id: a.id } });
                          }}
                        >
                          <Text style={styles.continueCardTitle} numberOfLines={2}>{a.title}</Text>
                          <Text style={[styles.continueCardDepth, { color: DEPTH_COLORS[state.depth] }]}>{DEPTH_LABELS[state.depth]}</Text>
                        </Pressable>
                      );
                    })}
                  </ScrollView>
                </View>
              );
            })()}

            {/* Exploration sections */}
            {(() => {
              const explorationTags = new Set(
                listArticles.filter(a => a.exploration_tag).map(a => a.exploration_tag!)
              );
              if (explorationTags.size === 0) return null;
              return [...explorationTags].map(tag => {
                const explorationArticles = listArticles.filter(a => a.exploration_tag === tag);
                // Mix subtopics: show one per primary topic first
                const seenTopics = new Set<string>();
                const sorted: Article[] = [];
                for (const a of explorationArticles) {
                  const primaryTopic = a.topics[0] || '';
                  if (!seenTopics.has(primaryTopic)) {
                    seenTopics.add(primaryTopic);
                    sorted.push(a);
                  }
                }
                // Then add remaining
                for (const a of explorationArticles) {
                  if (!sorted.includes(a)) sorted.push(a);
                }

                return (
                  <View key={tag} style={styles.explorationSection}>
                    <View style={styles.explorationHeader}>
                      <Text style={styles.sectionHeading}>
                        {'\u2726'} EXPLORING: {tag.replace(/[-—]+/g, ' — ').replace(/,\s*/g, ', ').replace(/\s+/g, ' ').trim().toUpperCase()}
                      </Text>
                      <Text style={styles.explorationCount}>{explorationArticles.length}</Text>
                    </View>
                    {sorted.slice(0, 8).map(a => <FeedCard key={a.id} article={a} />)}
                  </View>
                );
              });
            })()}

            {listArticles.length === 0 ? (
              <View style={styles.empty}>
                <Text style={styles.emptyTitle}>All caught up</Text>
                <Text style={styles.emptySubtitle}>No unread articles</Text>
              </View>
            ) : (
              listArticles.filter(a => !a.exploration_tag).map(a => <FeedCard key={a.id} article={a} />)
            )}
            <View style={{ height: 40 }} />
          </ScrollView>
        </>
      )}

      {viewMode === 'topics' && <TopicsModeView />}

      {viewMode === 'triage' && <TriageModeView />}
    </View>
  );
}

// --- Styles ---

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.parchment },
  desktopContainer: { maxWidth: layout.contentMaxWidth, alignSelf: 'center' as const, width: '100%' as any },

  // Screen header — compact
  screenHeader: {
    paddingHorizontal: layout.screenPadding,
    paddingTop: spacing.xs,
  },
  headerTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  screenTitle: {
    ...type.screenTitle,
    color: colors.ink,
  },
  sectionNav: {
    flexDirection: 'row',
    marginTop: 4,
  },
  sectionNavText: {
    fontFamily: fonts.body,
    fontSize: 13,
    color: colors.textMuted,
  },
  headerRule: {
    height: 1.5,
    backgroundColor: colors.ink,
    marginTop: spacing.xs,
  },
  viewModeRow: {
    flexDirection: 'row',
    gap: 6,
  },
  viewModeButton: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
    borderRadius: 3,
    borderWidth: 1,
    borderColor: colors.textMuted,
  },
  viewModeButtonActive: {
    backgroundColor: colors.rubric,
    borderColor: colors.rubric,
  },
  viewModeText: {
    ...type.metadata,
    fontSize: 12,
    color: colors.textMuted,
  },
  viewModeTextActive: {
    color: colors.parchment,
  },

  // List mode header
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    paddingHorizontal: layout.screenPadding,
    paddingTop: spacing.xs,
    paddingBottom: 2,
    gap: spacing.lg,
  },
  filterToggle: {
    ...type.metadata,
    color: colors.rubric,
  },
  progressRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: layout.screenPadding,
    paddingBottom: spacing.sm,
    gap: spacing.sm,
  },
  progressBar: {
    flex: 1,
    height: layout.progressBarHeight,
    backgroundColor: colors.rule,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    backgroundColor: colors.ink,
  },
  progressLabel: {
    ...type.metadata,
    color: colors.textMuted,
  },
  scroll: { flex: 1, paddingHorizontal: layout.screenPadding },

  // Section heading (✦ CONTINUE READING, ✦ NEW, etc.)
  sectionHeading: {
    ...type.sectionHead,
    color: colors.rubric,
    marginBottom: spacing.sm,
    marginTop: spacing.md,
  },

  // Entry row (two-column: content + sidebar)
  entryRow: {
    flexDirection: 'row',
    borderBottomWidth: 1,
    borderBottomColor: colors.rule,
    paddingVertical: spacing.md,
  },
  entryContent: {
    flex: 1,
    paddingRight: spacing.md,
  },
  entryTitle: {
    ...type.entryTitle,
    color: colors.textPrimary,
    marginBottom: 2,
  },
  entrySummary: {
    ...type.entrySummary,
    color: colors.textSecondary,
    marginBottom: spacing.xs,
  },
  entryTopics: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    marginBottom: spacing.xs,
  },
  topicTag: {
    ...type.topicTag,
    color: colors.rubric,
    marginRight: 2,
  },
  entryMeta: {
    ...type.metadata,
    color: colors.textMuted,
  },
  entrySidebar: {
    width: layout.sidebarWidth,
    borderLeftWidth: 1,
    borderLeftColor: colors.rule,
    paddingLeft: spacing.sm,
    justifyContent: 'flex-start',
  },
  sideLabel: {
    ...type.sideLabel,
    color: colors.textMuted,
    marginBottom: 2,
  },
  sideValue: {
    ...type.sideValue,
    color: colors.ink,
  },
  sideNote: {
    ...type.sideNote,
    color: colors.rubric,
  },
  noveltyText: {
    ...type.metadata,
    color: colors.textMuted,
  },
  tierText: {
    ...type.metadata,
    color: colors.rubric,
  },
  dedupIndicator: {
    ...type.metadata,
    color: colors.warning,
    marginTop: spacing.xs,
    fontStyle: 'italic' as const,
  },

  // Continue Reading
  continueSection: { marginBottom: spacing.sm },
  continueCard: {
    width: 200,
    borderLeftWidth: 2,
    borderLeftColor: colors.rubric,
    padding: spacing.md,
    marginRight: spacing.sm,
  },
  continueCardLabel: {
    ...type.sideLabel,
    color: colors.info,
    marginBottom: 2,
  },
  continueCardTitle: {
    ...type.entryTitle,
    color: colors.textPrimary,
    fontSize: 14,
    lineHeight: 18,
  },
  continueCardDepth: {
    ...type.metadata,
    color: colors.textMuted,
    marginTop: spacing.xs,
  },

  empty: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingTop: 100, gap: spacing.sm },
  emptyTitle: {
    ...type.screenTitle,
    color: colors.ink,
  },
  emptySubtitle: {
    ...type.entrySummary,
    color: colors.textSecondary,
  },

  // Topic clustering
  clusterContainer: {
    marginBottom: 2,
  },
  clusterHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: layout.screenPadding,
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.rule,
  },
  clusterHeaderLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    flex: 1,
  },
  clusterTopic: {
    ...type.entryTitle,
    color: colors.textPrimary,
  },
  clusterCount: {
    ...type.metadata,
    color: colors.textMuted,
  },
  clusterArticles: {
    paddingLeft: spacing.sm,
    paddingTop: spacing.xs,
  },

  // Synthesis card
  synthesisCard: {
    borderLeftWidth: 2,
    borderLeftColor: colors.rubric,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  synthesisHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  synthesisTitle: {
    ...type.entrySummary,
    color: colors.rubric,
    flex: 1,
  },
  synthesisText: {
    ...type.entrySummary,
    color: colors.textBody,
    marginTop: spacing.md,
  },

  // Triage mode
  triageContainer: {
    flex: 1,
    paddingHorizontal: layout.screenPadding,
  },
  triageCounter: {
    alignItems: 'center',
    paddingVertical: spacing.md,
  },
  triageCounterText: {
    ...type.metadata,
    color: colors.textMuted,
  },
  triageStack: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  triageCardWrapper: {
    position: 'absolute',
    width: '90%',
    maxWidth: 700,
    maxHeight: SCREEN_HEIGHT * 0.65,
  },
  triageCard: {
    backgroundColor: colors.parchment,
    borderRadius: 3,
    padding: spacing.xxl,
    borderWidth: 1,
    borderColor: colors.rule,
  },
  triageCardContent: {
    gap: spacing.md,
  },
  triageSourceRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  triageHostname: {
    ...type.metadata,
    color: colors.textMuted,
  },
  triageReadTime: {
    ...type.metadata,
    color: colors.textMuted,
  },
  triageTitle: {
    ...type.screenTitle,
    color: colors.ink,
    fontSize: 22,
    lineHeight: 30,
  },
  triageSummary: {
    ...type.entrySummary,
    color: colors.textSecondary,
    fontSize: 15,
    lineHeight: 22,
  },
  triageTopics: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    marginTop: spacing.xs,
  },
  triageTopicTag: {
    ...type.topicTag,
    color: colors.rubric,
  },
  triageAuthor: {
    ...type.metadata,
    color: colors.textMuted,
    marginTop: spacing.xs,
  },

  // Action labels
  actionLabel: {
    position: 'absolute',
    zIndex: 20,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    padding: spacing.sm,
  },
  actionLabelRight: {
    top: spacing.lg,
    left: spacing.lg,
  },
  actionLabelLeft: {
    top: spacing.lg,
    right: spacing.lg,
  },
  actionLabelTop: {
    bottom: spacing.lg,
    alignSelf: 'center',
    left: 0,
    right: 0,
    justifyContent: 'center',
  },
  actionLabelText: {
    fontFamily: fonts.bodyMedium,
    fontSize: 18,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },

  // Swipe hints
  swipeHints: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: spacing.lg,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.rule,
  },
  swipeHint: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  swipeHintText: {
    ...type.metadata,
    color: colors.textMuted,
  },

  // Triage complete
  triageComplete: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.xxxl,
  },
  triageCompleteTitle: {
    ...type.screenTitle,
    color: colors.ink,
  },
  triageCompleteSubtitle: {
    ...type.entrySummary,
    color: colors.textSecondary,
    textAlign: 'center',
  },
  triageResetButton: {
    marginTop: spacing.lg,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.sm,
    borderWidth: 1,
    borderColor: colors.rubric,
    borderRadius: 3,
  },
  triageResetText: {
    ...type.metadata,
    color: colors.rubric,
  },

  // Research results banner
  researchResultsBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    borderLeftWidth: 2,
    borderLeftColor: colors.rubric,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    marginBottom: spacing.sm,
  },
  researchResultsBannerText: {
    ...type.entrySummary,
    color: colors.rubric,
    flex: 1,
  },

  // Exploration section
  explorationSection: {
    marginBottom: spacing.lg,
    paddingTop: spacing.xs,
  },
  explorationHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.sm,
  },
  explorationCount: {
    ...type.metadata,
    color: colors.textMuted,
  },

  // Web triage buttons
  webTriageButtons: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginTop: spacing.lg,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.rule,
  },
  webTriageBtn: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.sm,
    borderRadius: 3,
    borderWidth: 1,
    borderColor: colors.rule,
  },
  webTriageBtnSkip: {},
  webTriageBtnRead: {},
  webTriageBtnSave: {},
  webTriageBtnText: {
    fontFamily: fonts.bodyMedium,
    fontSize: 13,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },

  // Web review banner
  webReviewBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    borderLeftWidth: 2,
    borderLeftColor: colors.warning,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    marginHorizontal: layout.screenPadding,
    marginTop: spacing.xs,
  },
  webReviewBannerText: {
    ...type.entrySummary,
    color: colors.warning,
    flex: 1,
  },
});
