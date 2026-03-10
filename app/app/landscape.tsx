import { useMemo } from 'react';
import { View, Text, ScrollView, Pressable, StyleSheet, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import { colors, fonts, layout } from '../design/tokens';
import { logEvent } from '../data/logger';
import { getTopicBubbles, getRecentSessions, getReadingStats, getCrossThreadBridges } from '../lib/reading-insights';
import { getDisplayTitle } from '../lib/display-utils';

export default function LandscapeScreen() {
  const router = useRouter();

  const bubbles = useMemo(() => getTopicBubbles(), []);
  const sessions = useMemo(() => getRecentSessions(5), []);
  const stats = useMemo(() => getReadingStats(7), []);
  const bridges = useMemo(() => getCrossThreadBridges(3), []);

  logEvent('landscape_open');

  // Compute bubble sizes and colors
  const maxCount = Math.max(...bubbles.map(b => b.articleCount), 1);
  const bubbleData = bubbles.slice(0, 8).map((b, i) => {
    const size = 50 + (b.articleCount / maxCount) * 60;
    const trendColor = b.trend === 'active' ? colors.rubric
      : b.trend === 'growing' ? colors.claimNew
      : b.trend === 'new' ? colors.claimNew
      : colors.textMuted;
    const trendLabel = b.trend === 'active' ? 'active'
      : b.trend === 'growing' ? 'growing'
      : b.trend === 'new' ? 'new'
      : b.lastReadDaysAgo < 999 ? `${b.lastReadDaysAgo}d ago` : '';
    return { ...b, size, trendColor, trendLabel, index: i };
  });

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Header */}
      <Pressable onPress={() => router.back()} style={styles.backBtn} hitSlop={12}>
        <Text style={styles.backText}>← Feed</Text>
      </Pressable>

      <Text style={styles.pageTitle}>Your Landscape</Text>
      <Text style={styles.pageSub}>The territory you're exploring</Text>
      <View style={styles.doubleRule}>
        <View style={styles.ruleTop} />
        <View style={styles.ruleGap} />
        <View style={styles.ruleBottom} />
      </View>

      {/* Topic bubbles */}
      <Text style={styles.sectionLabel}>✦ Topic map</Text>
      <View style={styles.bubbleGrid}>
        {bubbleData.map(b => (
          <View key={b.topic} style={[styles.bubble, { width: b.size, height: b.size }]}>
            <View style={[
              styles.bubbleInner,
              { width: b.size, height: b.size, borderRadius: b.size / 2 },
              b.trend === 'active' && styles.bubbleActive,
              b.trend === 'growing' && styles.bubbleGrowing,
              b.trend === 'new' && styles.bubbleNew,
              b.trend === 'quiet' && styles.bubbleQuiet,
            ]}>
              <Text style={[styles.bubbleName, b.size < 65 && { fontSize: 10 }]} numberOfLines={2}>
                {b.topic}
              </Text>
              <Text style={[styles.bubbleCount, { color: b.trendColor }]}>
                {b.articleCount} · {b.trendLabel}
              </Text>
            </View>
          </View>
        ))}
      </View>

      {/* Narrative */}
      {sessions.length > 0 && (
        <>
          <Text style={styles.sectionLabel}>✦ This week in your reading</Text>
          <Text style={styles.narrativeText}>
            You explored {stats.articlesExplored} article{stats.articlesExplored !== 1 ? 's' : ''} across{' '}
            {stats.topicsTouched} topic{stats.topicsTouched !== 1 ? 's' : ''} this week
            {stats.totalHours > 0 ? `, spending about ${stats.totalHours} hours reading` : ''}.
            {bridges.length > 0 && ` Found ${bridges.length} unexpected connection${bridges.length !== 1 ? 's' : ''} between different threads.`}
          </Text>
        </>
      )}

      {/* Cross-thread bridges */}
      {bridges.length > 0 && (
        <>
          <View style={styles.thinRule} />
          <Text style={styles.sectionLabel}>✦ Connections between threads</Text>
          {bridges.map((bridge, i) => (
            <View key={i} style={styles.bridgeCard}>
              <Text style={styles.bridgeFrom}>{bridge.fromTopic} ↔ {bridge.toTopic}</Text>
              <Text style={styles.bridgeDesc}>{bridge.description}</Text>
            </View>
          ))}
        </>
      )}

      {/* Recent sessions */}
      <View style={styles.thinRule} />
      <Text style={styles.sectionLabel}>✦ Recent sessions</Text>
      {sessions.map(session => (
        <View key={session.dateKey} style={styles.sessionItem}>
          <Text style={styles.sessionDate}>{session.date}</Text>
          <View style={styles.sessionContent}>
            {session.articles.map((a, i) => (
              <Text key={a.id} style={styles.sessionText}>
                {i > 0 ? '. ' : ''}
                <Text style={styles.sessionAction}>{a.action}</Text>{' '}
                <Text style={styles.sessionTitle}>{a.title}</Text>
              </Text>
            ))}
          </View>
          <Text style={styles.sessionDuration}>{session.totalMinutes} min</Text>
        </View>
      ))}

      {/* Footer stats */}
      <View style={styles.thinRule} />
      <View style={styles.statsFooter}>
        <View style={styles.statBox}>
          <Text style={styles.statNum}>{stats.articlesExplored}</Text>
          <Text style={styles.statLabel}>Explored</Text>
        </View>
        <View style={styles.statBox}>
          <Text style={styles.statNum}>{stats.topicsTouched}</Text>
          <Text style={styles.statLabel}>Topics</Text>
        </View>
        <View style={styles.statBox}>
          <Text style={styles.statNum}>{stats.totalHours}h</Text>
          <Text style={styles.statLabel}>Reading</Text>
        </View>
      </View>

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.parchment },
  content: {
    maxWidth: 900,
    width: '100%',
    alignSelf: 'center',
    paddingHorizontal: layout.screenPadding,
    paddingTop: 16,
  },
  backBtn: { marginBottom: 16 },
  backText: {
    fontFamily: fonts.body,
    fontSize: 13,
    color: colors.rubric,
    ...(Platform.OS === 'web' ? { cursor: 'pointer' as any } : {}),
  },
  pageTitle: {
    fontFamily: fonts.displaySemiBold,
    fontSize: 24,
    color: colors.ink,
    ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}),
  },
  pageSub: {
    fontFamily: fonts.readingItalic,
    fontSize: 14,
    color: colors.textMuted,
    marginBottom: 8,
  },
  doubleRule: { marginBottom: 28 },
  ruleTop: { height: 2, backgroundColor: colors.ink },
  ruleGap: { height: layout.doubleRuleGap },
  ruleBottom: { height: 1, backgroundColor: colors.ink },

  sectionLabel: {
    fontFamily: fonts.bodyItalic,
    fontSize: 12,
    color: colors.rubric,
    marginBottom: 14,
  },

  // Topic bubbles — flex wrap grid
  bubbleGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
    justifyContent: 'center',
    marginBottom: 32,
    paddingVertical: 16,
  },
  bubble: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  bubbleInner: {
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: colors.rule,
    padding: 6,
  },
  bubbleActive: {
    borderColor: 'rgba(139, 37, 0, 0.3)',
    backgroundColor: 'rgba(139, 37, 0, 0.05)',
  },
  bubbleGrowing: {
    borderColor: 'rgba(42, 122, 74, 0.25)',
    backgroundColor: 'rgba(42, 122, 74, 0.04)',
  },
  bubbleNew: {
    borderColor: 'rgba(42, 122, 74, 0.25)',
    backgroundColor: 'rgba(42, 122, 74, 0.03)',
    borderStyle: 'dashed' as any,
  },
  bubbleQuiet: {
    borderColor: colors.rule,
    backgroundColor: 'transparent',
  },
  bubbleName: {
    fontFamily: fonts.bodyMedium,
    fontSize: 11.5,
    color: colors.ink,
    textAlign: 'center',
    lineHeight: 14,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  bubbleCount: {
    fontFamily: fonts.ui,
    fontSize: 9,
    textAlign: 'center',
    marginTop: 2,
  },

  // Narrative
  narrativeText: {
    fontFamily: fonts.reading,
    fontSize: 15.5,
    lineHeight: 26,
    color: colors.textBody,
    marginBottom: 28,
  },

  // Bridges
  bridgeCard: {
    borderWidth: 1,
    borderColor: colors.rule,
    borderRadius: 3,
    padding: 14,
    marginBottom: 10,
  },
  bridgeFrom: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: colors.textMuted,
    textTransform: 'uppercase' as any,
    letterSpacing: 0.3,
    marginBottom: 6,
  },
  bridgeDesc: {
    fontFamily: fonts.readingItalic,
    fontSize: 13,
    color: colors.textSecondary,
    lineHeight: 19,
  },

  thinRule: {
    height: 1,
    backgroundColor: colors.rule,
    marginVertical: 28,
  },

  // Sessions
  sessionItem: {
    flexDirection: 'row',
    gap: 14,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.rule,
    alignItems: 'baseline',
  },
  sessionDate: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.textMuted,
    width: 72,
    flexShrink: 0,
  },
  sessionContent: { flex: 1 },
  sessionText: {
    fontFamily: fonts.reading,
    fontSize: 14,
    color: colors.textBody,
    lineHeight: 20,
  },
  sessionAction: { color: colors.textSecondary },
  sessionTitle: { color: colors.rubric },
  sessionDuration: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.textMuted,
    width: 48,
    textAlign: 'right',
    flexShrink: 0,
  },

  // Footer stats
  statsFooter: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    paddingVertical: 16,
  },
  statBox: { alignItems: 'center' },
  statNum: {
    fontFamily: fonts.displaySemiBold,
    fontSize: 32,
    color: colors.ink,
    lineHeight: 36,
    ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}),
  },
  statLabel: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: colors.textMuted,
    textTransform: 'uppercase' as any,
    letterSpacing: 0.3,
    marginTop: 2,
  },
});
