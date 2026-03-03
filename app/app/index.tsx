import { useState, useRef, useCallback, useEffect } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, Dimensions,
  Animated, PanResponder, LayoutAnimation, Platform, UIManager,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { getArticles, getFeedArticles, getInProgressArticles, getReadingState, getStats, getNoveltyScore, getSynthesisForTopic } from '../data/store';
import { fetchResearchResults, getResearchResults } from '../data/research';
import { Article, ReadingDepth } from '../data/types';
import { logEvent } from '../data/logger';

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
  summary: 'Read summary',
  claims: 'Reviewed claims',
  sections: 'Reading',
  full: 'Finished',
};

const DEPTH_COLORS: Record<ReadingDepth, string> = {
  unread: '#475569',
  summary: '#3b82f6',
  claims: '#8b5cf6',
  sections: '#f59e0b',
  full: '#10b981',
};

// --- Feed Card (used in List and Topic modes) ---

function NoveltyBadge({ articleId }: { articleId: string }) {
  const score = getNoveltyScore(articleId);
  if (score === null) return null;
  const pct = Math.round(score * 100);
  let color: string, label: string;
  if (pct >= 90) { color = '#10b981'; label = 'Mostly new'; }
  else if (pct > 60) { color = '#10b981'; label = `${pct}% new`; }
  else if (pct > 30) { color = '#f59e0b'; label = 'Partly familiar'; }
  else { color = '#64748b'; label = 'Mostly known'; }
  return (
    <View style={[styles.noveltyBadge, { borderColor: color }]}>
      <Text style={[styles.noveltyText, { color }]}>{label}</Text>
    </View>
  );
}

function FeedCard({ article }: { article: Article }) {
  const router = useRouter();
  const state = getReadingState(article.id);

  return (
    <Pressable
      style={styles.card}
      onPress={() => {
        logEvent('feed_item_tap', { article_id: article.id, title: article.title, novelty: getNoveltyScore(article.id) });
        router.push({ pathname: '/reader', params: { id: article.id } });
      }}
    >
      <View style={styles.cardHeader}>
        <Text style={styles.hostname}>{article.hostname}</Text>
        <Text style={styles.readTime}>{article.estimated_read_minutes} min</Text>
      </View>

      <Text style={styles.title}>{article.title}</Text>

      {article.one_line_summary && article.one_line_summary !== '[dry run]' && (
        <Text style={styles.summary} numberOfLines={2}>{article.one_line_summary}</Text>
      )}

      <View style={styles.cardFooter}>
        <View style={styles.topics}>
          {article.topics.slice(0, 3).map(t => (
            <View key={t} style={styles.topicPill}>
              <Text style={styles.topicText}>{t}</Text>
            </View>
          ))}
        </View>

        <NoveltyBadge articleId={article.id} />

        {state.depth !== 'unread' && (
          <View style={[styles.depthBadge, { borderColor: DEPTH_COLORS[state.depth] }]}>
            <Text style={[styles.depthText, { color: DEPTH_COLORS[state.depth] }]}>
              {DEPTH_LABELS[state.depth]}
            </Text>
          </View>
        )}
      </View>

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

      {article.author ? (
        <Text style={styles.author}>{article.author}</Text>
      ) : null}
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
      {...(isTop ? panResponder.panHandlers : {})}
    >
      <View style={styles.triageCard}>
        {/* Action labels */}
        {isTop && (
          <>
            <Animated.View style={[styles.actionLabel, styles.actionLabelRight, { opacity: rightOpacity }]}>
              <Ionicons name="bookmark" size={28} color="#10b981" />
              <Text style={[styles.actionLabelText, { color: '#10b981' }]}>Read Later</Text>
            </Animated.View>
            <Animated.View style={[styles.actionLabel, styles.actionLabelLeft, { opacity: leftOpacity }]}>
              <Ionicons name="close-circle" size={28} color="#ef4444" />
              <Text style={[styles.actionLabelText, { color: '#ef4444' }]}>Skip</Text>
            </Animated.View>
            <Animated.View style={[styles.actionLabel, styles.actionLabelTop, { opacity: upOpacity }]}>
              <Ionicons name="book" size={28} color="#60a5fa" />
              <Text style={[styles.actionLabelText, { color: '#60a5fa' }]}>Read Now</Text>
            </Animated.View>
          </>
        )}

        {/* Card content */}
        <View style={styles.triageCardContent}>
          <View style={styles.triageSourceRow}>
            <Text style={styles.triageHostname}>{article.hostname}</Text>
            <Text style={styles.triageReadTime}>{article.estimated_read_minutes} min read</Text>
          </View>

          <Text style={styles.triageTitle}>{article.title}</Text>

          {article.one_line_summary && article.one_line_summary !== '[dry run]' && (
            <Text style={styles.triageSummary}>{article.one_line_summary}</Text>
          )}

          <View style={styles.triageTopics}>
            {article.topics.slice(0, 5).map(t => (
              <View key={t} style={styles.triageTopicPill}>
                <Text style={styles.triageTopicText}>{t}</Text>
              </View>
            ))}
          </View>

          {article.author ? (
            <Text style={styles.triageAuthor}>by {article.author}</Text>
          ) : null}
        </View>

        {/* Swipe hints */}
        {isTop && (
          <View style={styles.swipeHints}>
            <View style={styles.swipeHint}>
              <Ionicons name="arrow-back" size={14} color="#64748b" />
              <Text style={styles.swipeHintText}>Skip</Text>
            </View>
            <View style={styles.swipeHint}>
              <Ionicons name="arrow-up" size={14} color="#64748b" />
              <Text style={styles.swipeHintText}>Read Now</Text>
            </View>
            <View style={styles.swipeHint}>
              <Ionicons name="arrow-forward" size={14} color="#64748b" />
              <Text style={styles.swipeHintText}>Save</Text>
            </View>
          </View>
        )}
      </View>
    </Animated.View>
  );
}

// --- Triage Mode ---

function TriageModeView() {
  const router = useRouter();
  const articles = getArticles();
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

  const untriagedArticles = articles.filter(a => getTriageState(a.id) === 'untriaged');
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
      });
    } else if (direction === 'left') {
      setTriageState(article.id, 'skipped');
      logEvent('triage_swipe', {
        direction: 'left',
        decision: 'skipped',
        article_id: article.id,
        title: article.title,
      });
    } else if (direction === 'up') {
      setTriageState(article.id, 'read_later');
      logEvent('triage_swipe', {
        direction: 'up',
        decision: 'read_now',
        article_id: article.id,
        title: article.title,
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
        <Ionicons name="checkmark-circle" size={64} color="#10b981" />
        <Text style={styles.triageCompleteTitle}>All caught up!</Text>
        <Text style={styles.triageCompleteSubtitle}>
          {readLaterCount} saved{readLaterCount > 0 ? '' : ''} · {skippedCount} skipped
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
          {processedCount + 1} of {articles.length} remaining
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
        <Ionicons name="layers" size={16} color="#a78bfa" />
        <Text style={styles.synthesisTitle}>
          Synthesis across {articleCount} articles
        </Text>
        <Ionicons
          name={expanded ? 'chevron-up' : 'chevron-down'}
          size={16}
          color="#94a3b8"
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
  const articles = getArticles();
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
                  size={18}
                  color="#94a3b8"
                />
                <Text style={styles.clusterTopic}>{cluster.topic}</Text>
              </View>
              <View style={styles.clusterBadge}>
                <Text style={styles.clusterCount}>{cluster.articles.length}</Text>
              </View>
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
  const [viewMode, setViewMode] = useState<ViewMode>('list');
  const [showAll, setShowAll] = useState(false);
  const [, forceUpdate] = useState(0);
  const [triageReady, setTriageReady] = useState(false);
  const [newResearchCount, setNewResearchCount] = useState(0);

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

  const allArticles = getArticles();
  const feed = showAll ? allArticles : getFeedArticles();
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
  })();

  const handleViewModeChange = (mode: ViewMode) => {
    setViewMode(mode);
    logEvent('feed_view_mode', { mode });
  };

  return (
    <View style={styles.container}>
      {/* View mode toggle */}
      <View style={styles.viewModeRow}>
        {(['list', 'topics', 'triage'] as ViewMode[]).map(mode => (
          <Pressable
            key={mode}
            style={[styles.viewModeButton, viewMode === mode && styles.viewModeButtonActive]}
            onPress={() => handleViewModeChange(mode)}
          >
            <Ionicons
              name={
                mode === 'list' ? 'list' :
                mode === 'topics' ? 'grid-outline' :
                'layers-outline'
              }
              size={16}
              color={viewMode === mode ? '#f8fafc' : '#64748b'}
            />
            <Text style={[styles.viewModeText, viewMode === mode && styles.viewModeTextActive]}>
              {mode === 'list' ? 'List' : mode === 'topics' ? 'Topics' : 'Triage'}
            </Text>
          </Pressable>
        ))}
      </View>

      {viewMode === 'list' && (
        <>
          <View style={styles.headerRow}>
            <Text style={styles.headerTitle}>
              {listArticles.length} article{listArticles.length !== 1 ? 's' : ''}
            </Text>
            <Pressable onPress={() => {
              logEvent('feed_toggle_filter', { show_all: !showAll });
              setShowAll(!showAll);
            }}>
              <Text style={styles.filterToggle}>{showAll ? 'Unread only' : 'Show all'}</Text>
            </Pressable>
            <Pressable onPress={() => forceUpdate(n => n + 1)}>
              <Ionicons name="refresh" size={18} color="#64748b" />
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
                <Ionicons name="flask-outline" size={16} color="#a78bfa" />
                <Text style={styles.researchResultsBannerText}>
                  {newResearchCount} research result{newResearchCount !== 1 ? 's' : ''} ready
                </Text>
                <Ionicons name="chevron-forward" size={14} color="#64748b" />
              </Pressable>
            )}

            {/* Continue Reading section */}
            {(() => {
              const inProgress = getInProgressArticles();
              if (inProgress.length === 0) return null;
              return (
                <View style={styles.continueSection}>
                  <Text style={styles.continueSectionTitle}>Continue Reading</Text>
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 16 }}>
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
                          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 4 }}>
                            <View style={[styles.depthDot, { backgroundColor: DEPTH_COLORS[state.depth] }]} />
                            <Text style={styles.continueCardDepth}>{DEPTH_LABELS[state.depth]}</Text>
                          </View>
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
                      <Ionicons name="compass-outline" size={16} color="#10b981" />
                      <Text style={styles.explorationTitle}>Exploring: {tag}</Text>
                      <Text style={styles.explorationCount}>{explorationArticles.length}</Text>
                    </View>
                    {sorted.slice(0, 8).map(a => <FeedCard key={a.id} article={a} />)}
                  </View>
                );
              });
            })()}

            {listArticles.length === 0 ? (
              <View style={styles.empty}>
                <Ionicons name="checkmark-circle" size={48} color="#10b981" />
                <Text style={styles.emptyTitle}>All caught up!</Text>
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
  container: { flex: 1, backgroundColor: '#0f172a' },

  // View mode toggle
  viewModeRow: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingTop: 8,
    paddingBottom: 4,
    gap: 8,
  },
  viewModeButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
    backgroundColor: '#1e293b',
  },
  viewModeButtonActive: {
    backgroundColor: '#2563eb',
  },
  viewModeText: {
    color: '#64748b',
    fontSize: 13,
    fontWeight: '500',
  },
  viewModeTextActive: {
    color: '#f8fafc',
  },

  // List mode header
  headerRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingTop: 8, paddingBottom: 4, gap: 12 },
  headerTitle: { color: '#f8fafc', fontSize: 16, fontWeight: '600', flex: 1 },
  filterToggle: { color: '#60a5fa', fontSize: 13 },
  progressRow: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingBottom: 8, gap: 8 },
  progressBar: { flex: 1, height: 4, backgroundColor: '#1e293b', borderRadius: 2, overflow: 'hidden' },
  progressFill: { height: '100%', backgroundColor: '#2563eb', borderRadius: 2 },
  progressLabel: { color: '#64748b', fontSize: 12 },
  scroll: { flex: 1, paddingHorizontal: 16 },

  // Feed card
  card: {
    backgroundColor: '#1e293b',
    borderRadius: 12,
    padding: 16,
    marginBottom: 10,
  },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 },
  hostname: { color: '#60a5fa', fontSize: 12, fontWeight: '500' },
  readTime: { color: '#64748b', fontSize: 12 },
  title: { color: '#f8fafc', fontSize: 17, fontWeight: '600', lineHeight: 23, marginBottom: 4 },
  summary: { color: '#94a3b8', fontSize: 14, lineHeight: 20, marginBottom: 8 },
  author: { color: '#64748b', fontSize: 12, marginTop: 4 },
  cardFooter: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  topics: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, flex: 1 },
  topicPill: { backgroundColor: '#334155', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10 },
  topicText: { color: '#94a3b8', fontSize: 11 },
  depthBadge: { borderWidth: 1, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8 },
  depthText: { fontSize: 11, fontWeight: '500' },
  noveltyBadge: { borderWidth: 1, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8, marginRight: 4 },
  noveltyText: { fontSize: 11, fontWeight: '500' },
  dedupIndicator: { color: '#f59e0b', fontSize: 11, marginTop: 6, fontStyle: 'italic' as const },
  // Continue Reading
  continueSection: { marginBottom: 8, paddingHorizontal: 16 },
  continueSectionTitle: { color: '#94a3b8', fontSize: 13, fontWeight: '600', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 },
  continueCard: { width: 200, backgroundColor: '#1e293b', borderRadius: 12, padding: 12, marginRight: 10, borderLeftWidth: 3, borderLeftColor: '#f59e0b' },
  continueCardTitle: { color: '#f8fafc', fontSize: 14, fontWeight: '600', lineHeight: 18 },
  continueCardDepth: { color: '#94a3b8', fontSize: 11 },
  depthDot: { width: 6, height: 6, borderRadius: 3 },

  empty: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingTop: 100, gap: 8 },
  emptyTitle: { color: '#f8fafc', fontSize: 20, fontWeight: '700' },
  emptySubtitle: { color: '#94a3b8', fontSize: 14 },

  // Topic clustering
  clusterContainer: {
    marginBottom: 4,
  },
  clusterHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#1e293b',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 10,
    marginBottom: 2,
  },
  clusterHeaderLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flex: 1,
  },
  clusterTopic: {
    color: '#f8fafc',
    fontSize: 15,
    fontWeight: '600',
  },
  clusterBadge: {
    backgroundColor: '#334155',
    paddingHorizontal: 10,
    paddingVertical: 3,
    borderRadius: 12,
  },
  clusterCount: {
    color: '#94a3b8',
    fontSize: 12,
    fontWeight: '600',
  },
  clusterArticles: {
    paddingLeft: 8,
    paddingTop: 4,
  },

  // Synthesis card
  synthesisCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    padding: 14,
    marginBottom: 10,
    borderLeftWidth: 3,
    borderLeftColor: '#a78bfa',
  },
  synthesisHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  synthesisTitle: {
    color: '#a78bfa',
    fontSize: 13,
    fontWeight: '600',
    flex: 1,
  },
  synthesisText: {
    color: '#cbd5e1',
    fontSize: 14,
    lineHeight: 22,
    marginTop: 12,
  },

  // Triage mode
  triageContainer: {
    flex: 1,
    paddingHorizontal: 16,
  },
  triageCounter: {
    alignItems: 'center',
    paddingVertical: 12,
  },
  triageCounterText: {
    color: '#94a3b8',
    fontSize: 14,
    fontWeight: '500',
  },
  triageStack: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  triageCardWrapper: {
    position: 'absolute',
    width: SCREEN_WIDTH - 32,
    maxHeight: SCREEN_HEIGHT * 0.65,
  },
  triageCard: {
    backgroundColor: '#1e293b',
    borderRadius: 16,
    padding: 24,
    borderWidth: 1,
    borderColor: '#334155',
  },
  triageCardContent: {
    gap: 12,
  },
  triageSourceRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  triageHostname: {
    color: '#60a5fa',
    fontSize: 14,
    fontWeight: '500',
  },
  triageReadTime: {
    color: '#64748b',
    fontSize: 13,
  },
  triageTitle: {
    color: '#f8fafc',
    fontSize: 22,
    fontWeight: '700',
    lineHeight: 30,
  },
  triageSummary: {
    color: '#94a3b8',
    fontSize: 16,
    lineHeight: 24,
  },
  triageTopics: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 4,
  },
  triageTopicPill: {
    backgroundColor: '#334155',
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
  },
  triageTopicText: {
    color: '#94a3b8',
    fontSize: 13,
  },
  triageAuthor: {
    color: '#64748b',
    fontSize: 14,
    marginTop: 4,
  },

  // Action labels
  actionLabel: {
    position: 'absolute',
    zIndex: 20,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    padding: 8,
  },
  actionLabelRight: {
    top: 16,
    left: 16,
  },
  actionLabelLeft: {
    top: 16,
    right: 16,
  },
  actionLabelTop: {
    bottom: 16,
    alignSelf: 'center',
    left: 0,
    right: 0,
    justifyContent: 'center',
  },
  actionLabelText: {
    fontSize: 18,
    fontWeight: '700',
  },

  // Swipe hints
  swipeHints: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 16,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#334155',
  },
  swipeHint: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  swipeHintText: {
    color: '#64748b',
    fontSize: 12,
  },

  // Triage complete
  triageComplete: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 32,
  },
  triageCompleteTitle: {
    color: '#f8fafc',
    fontSize: 24,
    fontWeight: '700',
  },
  triageCompleteSubtitle: {
    color: '#94a3b8',
    fontSize: 16,
    textAlign: 'center',
  },
  triageResetButton: {
    marginTop: 16,
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 8,
    backgroundColor: '#1e293b',
  },
  triageResetText: {
    color: '#60a5fa',
    fontSize: 14,
    fontWeight: '500',
  },

  // Research results banner
  researchResultsBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: '#1a1a2e',
    borderLeftWidth: 3,
    borderLeftColor: '#a78bfa',
    padding: 12,
    borderRadius: 10,
    marginBottom: 10,
  },
  researchResultsBannerText: {
    color: '#a78bfa',
    fontSize: 13,
    fontWeight: '600',
    flex: 1,
  },

  // Exploration section
  explorationSection: {
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#10b98133',
    borderRadius: 12,
    padding: 12,
  },
  explorationHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 12,
  },
  explorationTitle: {
    color: '#10b981',
    fontSize: 15,
    fontWeight: '600',
    flex: 1,
  },
  explorationCount: {
    color: '#64748b',
    fontSize: 12,
    backgroundColor: '#1e293b',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 10,
    overflow: 'hidden',
  },
});
