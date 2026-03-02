import { useState, useRef } from 'react';
import {
  View, Text, StyleSheet, Dimensions, Pressable, Animated, PanResponder, Linking, ScrollView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { getUntriaged, addSignal, getStats, getBookmarks } from '../data/store';
import { Bookmark } from '../data/types';
import { logEvent } from '../data/logger';

const { width, height } = Dimensions.get('window');
const SWIPE_THRESHOLD = width * 0.25;

function ContentTypeTag({ type }: { type: string }) {
  const colors: Record<string, string> = {
    tool_comparison: '#f59e0b',
    experience_report: '#10b981',
    tip: '#3b82f6',
    workflow: '#8b5cf6',
    announcement: '#ef4444',
    tutorial: '#06b6d4',
    opinion: '#f97316',
    thread: '#6366f1',
  };
  return (
    <View style={[styles.tag, { backgroundColor: (colors[type] ?? '#64748b') + '30', borderColor: colors[type] ?? '#64748b' }]}>
      <Text style={[styles.tagText, { color: colors[type] ?? '#64748b' }]}>{type.replace('_', ' ')}</Text>
    </View>
  );
}

function TriageCard({ bookmark, onSwipe, expanded, onToggleExpand }: {
  bookmark: Bookmark;
  onSwipe: (dir: 'left' | 'right' | 'up') => void;
  expanded: boolean;
  onToggleExpand: () => void;
}) {
  const pan = useRef(new Animated.ValueXY()).current;
  const opacity = useRef(new Animated.Value(1)).current;

  const panResponder = PanResponder.create({
    onMoveShouldSetPanResponder: (_, g) => Math.abs(g.dx) > 10 || Math.abs(g.dy) > 10,
    onPanResponderMove: Animated.event([null, { dx: pan.x, dy: pan.y }], { useNativeDriver: false }),
    onPanResponderRelease: (_, g) => {
      if (g.dx > SWIPE_THRESHOLD) {
        Animated.parallel([
          Animated.timing(pan.x, { toValue: width, duration: 200, useNativeDriver: false }),
          Animated.timing(opacity, { toValue: 0, duration: 200, useNativeDriver: false }),
        ]).start(() => onSwipe('right'));
      } else if (g.dx < -SWIPE_THRESHOLD) {
        Animated.parallel([
          Animated.timing(pan.x, { toValue: -width, duration: 200, useNativeDriver: false }),
          Animated.timing(opacity, { toValue: 0, duration: 200, useNativeDriver: false }),
        ]).start(() => onSwipe('left'));
      } else if (g.dy < -SWIPE_THRESHOLD) {
        Animated.parallel([
          Animated.timing(pan.y, { toValue: -height, duration: 200, useNativeDriver: false }),
          Animated.timing(opacity, { toValue: 0, duration: 200, useNativeDriver: false }),
        ]).start(() => onSwipe('up'));
      } else {
        Animated.spring(pan, { toValue: { x: 0, y: 0 }, useNativeDriver: false }).start();
      }
    },
  });

  const rotate = pan.x.interpolate({ inputRange: [-width, 0, width], outputRange: ['-15deg', '0deg', '15deg'] });
  const leftIndicator = pan.x.interpolate({ inputRange: [-width, 0], outputRange: [1, 0], extrapolate: 'clamp' });
  const rightIndicator = pan.x.interpolate({ inputRange: [0, width], outputRange: [0, 1], extrapolate: 'clamp' });
  const upIndicator = pan.y.interpolate({ inputRange: [-height, 0], outputRange: [1, 0], extrapolate: 'clamp' });

  const summary = bookmark._llm_summary;
  const claims = summary?.key_claims ?? [];
  const topics = summary?.topics ?? [];

  return (
    <Animated.View
      {...panResponder.panHandlers}
      style={[styles.card, { transform: [{ translateX: pan.x }, { translateY: pan.y }, { rotate }], opacity }]}
    >
      {/* Swipe indicators */}
      <Animated.View style={[styles.indicator, styles.indicatorLeft, { opacity: leftIndicator }]}>
        <Text style={styles.indicatorText}>KNEW IT</Text>
      </Animated.View>
      <Animated.View style={[styles.indicator, styles.indicatorRight, { opacity: rightIndicator }]}>
        <Text style={[styles.indicatorText, { color: '#10b981' }]}>INTERESTING</Text>
      </Animated.View>
      <Animated.View style={[styles.indicator, styles.indicatorUp, { opacity: upIndicator }]}>
        <Text style={[styles.indicatorText, { color: '#f59e0b' }]}>DEEP DIVE</Text>
      </Animated.View>

      <ScrollView style={styles.cardScroll} showsVerticalScrollIndicator={false}>
        {/* Header */}
        <View style={styles.cardHeader}>
          <Text style={styles.author}>@{bookmark.author_username}</Text>
          <View style={styles.meta}>
            {summary?.content_type && summary.content_type !== 'unknown' && (
              <ContentTypeTag type={summary.content_type} />
            )}
            <Text style={styles.score}>{bookmark._relevance_score.toFixed(1)}</Text>
          </View>
        </View>

        {/* Summary */}
        {summary?.summary && summary.summary !== '[dry run]' ? (
          <Text style={styles.summary}>{summary.summary}</Text>
        ) : (
          <Text style={styles.tweetText}>{bookmark.text}</Text>
        )}

        {/* Key claims */}
        {claims.length > 0 && (
          <View style={styles.claimsSection}>
            <Text style={styles.claimsTitle}>Key claims:</Text>
            {claims.slice(0, expanded ? undefined : 2).map((c, i) => (
              <View key={i} style={styles.claimRow}>
                <Text style={styles.claimBullet}>•</Text>
                <Text style={styles.claimText}>{c}</Text>
              </View>
            ))}
            {claims.length > 2 && !expanded && (
              <Pressable onPress={onToggleExpand}>
                <Text style={styles.showMore}>+{claims.length - 2} more claims</Text>
              </Pressable>
            )}
          </View>
        )}

        {/* Topics */}
        {topics.length > 0 && (
          <View style={styles.topicsRow}>
            {topics.slice(0, 5).map((t, i) => (
              <View key={i} style={styles.topicPill}>
                <Text style={styles.topicText}>{t}</Text>
              </View>
            ))}
          </View>
        )}

        {/* Original tweet (expandable) */}
        {expanded && (
          <View style={styles.originalSection}>
            <Text style={styles.originalLabel}>Original tweet:</Text>
            <Text style={styles.originalText}>{bookmark.text}</Text>
            {bookmark.urls?.length > 0 && (
              <Pressable onPress={() => {
                logEvent('link_open', { bookmark_id: bookmark.id, url: bookmark.urls[0], screen: 'triage' });
                Linking.openURL(bookmark.urls[0]);
              }}>
                <Text style={styles.linkText}>Open link ↗</Text>
              </Pressable>
            )}
          </View>
        )}

        {/* Tap to expand */}
        <Pressable onPress={onToggleExpand} style={styles.expandButton}>
          <Text style={styles.expandText}>{expanded ? 'Show less' : 'Tap for more'}</Text>
        </Pressable>
      </ScrollView>
    </Animated.View>
  );
}

export default function TriageScreen() {
  const [cardIndex, setCardIndex] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const untriaged = getUntriaged();
  const stats = getStats();

  const handleSwipe = (dir: 'left' | 'right' | 'up') => {
    const current = untriaged[0];
    if (!current) return;
    const signal = dir === 'right' ? 'interesting' : dir === 'up' ? 'deep_dive' : 'knew_it';
    logEvent('triage_swipe', {
      direction: dir,
      signal,
      bookmark_id: current.id,
      card_position: cardIndex,
      was_expanded: expanded,
      remaining: untriaged.length - 1,
    });
    addSignal({ bookmarkId: current.id, signal, timestamp: Date.now() });
    setCardIndex(i => i + 1);
    setExpanded(false);
  };

  if (untriaged.length === 0) {
    logEvent('triage_complete', {
      total: stats.total,
      interesting: stats.interesting,
      deep_dive: stats.deepDive,
      knew_it: stats.knewIt,
    });
    return (
      <View style={styles.container}>
        <View style={styles.doneCard}>
          <Ionicons name="checkmark-circle" size={64} color="#10b981" />
          <Text style={styles.doneTitle}>All triaged!</Text>
          <Text style={styles.doneSubtitle}>{stats.total} items processed</Text>
          <Text style={styles.doneStats}>
            {stats.interesting} interesting · {stats.deepDive} deep dive · {stats.knewIt} knew it
          </Text>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.progress}>
        <Text style={styles.progressText}>
          {stats.triaged}/{stats.total} · <Text style={{ color: '#10b981' }}>{stats.interesting} interesting</Text> · <Text style={{ color: '#f59e0b' }}>{stats.deepDive} deep dive</Text>
        </Text>
      </View>

      <View style={styles.cardContainer}>
        {/* Background card (next card preview) */}
        {untriaged.length > 1 && (
          <View style={[styles.card, { opacity: 0.5, transform: [{ scale: 0.95 }] }]}>
            <Text style={styles.author}>@{untriaged[1].author_username}</Text>
            <Text style={styles.summary} numberOfLines={3}>
              {untriaged[1]._llm_summary?.summary ?? untriaged[1].text.slice(0, 150)}
            </Text>
          </View>
        )}
        {/* Active card */}
        <TriageCard
          key={untriaged[0].id}
          bookmark={untriaged[0]}
          onSwipe={handleSwipe}
          expanded={expanded}
          onToggleExpand={() => {
            logEvent('card_toggle_expand', {
              bookmark_id: untriaged[0].id,
              expanded: !expanded,
              screen: 'triage',
            });
            setExpanded(!expanded);
          }}
        />
      </View>

      <View style={styles.legend}>
        <Text style={styles.legendItem}>← Knew it</Text>
        <Text style={[styles.legendItem, { color: '#f59e0b' }]}>↑ Deep dive</Text>
        <Text style={[styles.legendItem, { color: '#10b981' }]}>Interesting →</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f172a' },
  progress: { paddingHorizontal: 20, paddingTop: 8, paddingBottom: 4 },
  progressText: { color: '#94a3b8', fontSize: 13, textAlign: 'center' },
  cardContainer: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  card: {
    position: 'absolute',
    width: width - 32,
    maxHeight: height * 0.65,
    backgroundColor: '#1e293b',
    borderRadius: 16,
    padding: 20,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 5,
  },
  cardScroll: { maxHeight: height * 0.6 },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  author: { color: '#60a5fa', fontSize: 15, fontWeight: '600' },
  meta: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  score: { color: '#64748b', fontSize: 13 },
  tag: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8, borderWidth: 1 },
  tagText: { fontSize: 11, fontWeight: '600' },
  summary: { color: '#e2e8f0', fontSize: 16, lineHeight: 24, marginBottom: 12 },
  tweetText: { color: '#cbd5e1', fontSize: 15, lineHeight: 22, marginBottom: 12 },
  claimsSection: { marginBottom: 12 },
  claimsTitle: { color: '#94a3b8', fontSize: 12, fontWeight: '600', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 },
  claimRow: { flexDirection: 'row', marginBottom: 4, paddingRight: 8 },
  claimBullet: { color: '#60a5fa', marginRight: 8, fontSize: 14 },
  claimText: { color: '#cbd5e1', fontSize: 14, lineHeight: 20, flex: 1 },
  showMore: { color: '#60a5fa', fontSize: 13, marginTop: 4 },
  topicsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 8 },
  topicPill: { backgroundColor: '#334155', paddingHorizontal: 10, paddingVertical: 3, borderRadius: 12 },
  topicText: { color: '#94a3b8', fontSize: 12 },
  originalSection: { marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: '#334155' },
  originalLabel: { color: '#64748b', fontSize: 12, marginBottom: 4 },
  originalText: { color: '#94a3b8', fontSize: 13, lineHeight: 19 },
  linkText: { color: '#60a5fa', fontSize: 14, marginTop: 8 },
  expandButton: { alignItems: 'center', paddingTop: 8 },
  expandText: { color: '#475569', fontSize: 13 },
  indicator: { position: 'absolute', top: 20, zIndex: 10, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, borderWidth: 2 },
  indicatorLeft: { left: 16, borderColor: '#64748b' },
  indicatorRight: { right: 16, borderColor: '#10b981' },
  indicatorUp: { alignSelf: 'center', left: '30%', borderColor: '#f59e0b' },
  indicatorText: { color: '#64748b', fontSize: 14, fontWeight: '800' },
  legend: { flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: 32, paddingVertical: 12 },
  legendItem: { color: '#64748b', fontSize: 13 },
  doneCard: { flex: 1, justifyContent: 'center', alignItems: 'center', gap: 12 },
  doneTitle: { color: '#f8fafc', fontSize: 24, fontWeight: '700' },
  doneSubtitle: { color: '#94a3b8', fontSize: 16 },
  doneStats: { color: '#64748b', fontSize: 14 },
});
