import { useState, useMemo } from 'react';
import { View, Text, ScrollView, Pressable, StyleSheet, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import { colors, fonts, layout } from '../design/tokens';
import { logEvent } from '../data/logger';
import { getActiveThreads, getCrossThreadBridges } from '../lib/reading-insights';
import type { ReadingThread } from '../lib/reading-insights';

export default function TrailsScreen() {
  const router = useRouter();
  const threads = useMemo(() => getActiveThreads(6), []);
  const bridges = useMemo(() => getCrossThreadBridges(3), []);
  const [expandedThread, setExpandedThread] = useState<string | null>(
    threads[0]?.topic || null
  );

  logEvent('trails_open');

  const expanded = threads.find(t => t.topic === expandedThread);

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Header */}
      <Pressable onPress={() => router.back()} style={styles.backBtn} hitSlop={12}>
        <Text style={styles.backText}>← Feed</Text>
      </Pressable>

      <Text style={styles.pageTitle}>Reading Trails</Text>
      <Text style={styles.pageSub}>Follow threads of connected ideas through your library</Text>
      <View style={styles.doubleRule}>
        <View style={styles.ruleTop} />
        <View style={styles.ruleGap} />
        <View style={styles.ruleBottom} />
      </View>

      {/* Thread cards */}
      <Text style={styles.sectionLabel}>✦ Your active threads</Text>
      <View style={styles.threadGrid}>
        {threads.map(thread => (
          <Pressable
            key={thread.topic}
            style={[
              styles.threadCard,
              expandedThread === thread.topic && styles.threadCardActive,
            ]}
            onPress={() => {
              setExpandedThread(expandedThread === thread.topic ? null : thread.topic);
              logEvent('trail_thread_tap', { topic: thread.topic });
            }}
          >
            <Text style={styles.tcTopic}>{thread.topic}</Text>
            {thread.description ? (
              <Text style={styles.tcDesc} numberOfLines={2}>{thread.description}</Text>
            ) : null}
            <View style={styles.tcDotRow}>
              {thread.articles.slice(0, 8).map((a, i) => (
                <View
                  key={i}
                  style={[
                    styles.tcDot,
                    a.status === 'read' && styles.tcDotRead,
                    a.status === 'reading' && styles.tcDotReading,
                    a.status === 'unread' && styles.tcDotUnread,
                  ]}
                />
              ))}
            </View>
            <Text style={styles.tcMeta}>
              {thread.unreadCount > 0 && (
                <Text style={styles.tcMetaGreen}>{thread.unreadCount} unread</Text>
              )}
              {thread.unreadCount > 0 ? ' · ' : ''}
              {thread.totalArticles} articles
            </Text>
          </Pressable>
        ))}
      </View>

      {/* Expanded thread detail */}
      {expanded && (
        <>
          <View style={styles.thinRule} />
          <Text style={styles.sectionLabel}>✦ {expanded.topic}</Text>
          <View style={Platform.OS === 'web' ? styles.threadDetailWeb : undefined}>
            <View style={Platform.OS === 'web' ? styles.threadDetailLeft : undefined}>
              {expanded.articles.map((article, i) => (
                <Pressable
                  key={article.id}
                  style={styles.seqItem}
                  onPress={() => {
                    logEvent('trail_article_tap', { article_id: article.id, topic: expanded.topic });
                    router.push({ pathname: '/reader', params: { id: article.id } });
                  }}
                >
                  {/* Gutter with marker and line */}
                  <View style={styles.seqGutter}>
                    <View style={[
                      styles.seqMarker,
                      article.status === 'read' && styles.seqMarkerDone,
                      article.status === 'reading' && styles.seqMarkerActive,
                      article.status === 'unread' && styles.seqMarkerNext,
                    ]}>
                      <Text style={[
                        styles.seqMarkerText,
                        article.status === 'read' && styles.seqMarkerTextDone,
                        article.status === 'reading' && styles.seqMarkerTextActive,
                      ]}>
                        {article.status === 'read' ? '✓' : String(i + 1)}
                      </Text>
                    </View>
                    {i < expanded.articles.length - 1 && (
                      <View style={[
                        styles.seqLine,
                        article.status === 'read' ? styles.seqLineSolid : styles.seqLineDashed,
                      ]} />
                    )}
                  </View>

                  {/* Content */}
                  <View style={styles.seqContent}>
                    <Text style={[
                      styles.seqTitle,
                      article.status === 'read' && styles.seqTitleDone,
                      article.status === 'reading' && styles.seqTitleActive,
                    ]} numberOfLines={2}>
                      {article.title}
                    </Text>
                    <Text style={styles.seqSource}>
                      {article.source ? `${article.source} · ` : ''}
                      {article.status === 'read' ? 'read'
                        : article.status === 'reading' ? 'in progress'
                        : article.readMinutes ? `${article.readMinutes} min` : ''}
                    </Text>
                  </View>
                </Pressable>
              ))}
            </View>

            {/* Bridge insights (web sidebar) */}
            {Platform.OS === 'web' && bridges.length > 0 && (
              <View style={styles.threadDetailRight}>
                <Text style={styles.insightLabel}>Bridges to other threads</Text>
                {bridges
                  .filter(b =>
                    b.fromTopic.toLowerCase() === expanded.topic.toLowerCase() ||
                    b.toTopic.toLowerCase() === expanded.topic.toLowerCase()
                  )
                  .slice(0, 2)
                  .map((bridge, i) => (
                    <View key={i} style={styles.bridgeBox}>
                      <Text style={styles.bridgeText}>{bridge.description}</Text>
                    </View>
                  ))
                }
                {bridges
                  .filter(b =>
                    b.fromTopic.toLowerCase() !== expanded.topic.toLowerCase() &&
                    b.toTopic.toLowerCase() !== expanded.topic.toLowerCase()
                  ).length === bridges.length && bridges.length > 0 && (
                  <View style={styles.bridgeBox}>
                    <Text style={styles.bridgeText}>
                      Connections between {bridges[0].fromTopic} and {bridges[0].toTopic}
                    </Text>
                  </View>
                )}
              </View>
            )}
          </View>
        </>
      )}

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.parchment },
  content: {
    maxWidth: 960,
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

  // Thread cards grid
  threadGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 14,
    marginBottom: 8,
  },
  threadCard: {
    borderWidth: 1,
    borderColor: colors.rule,
    borderRadius: 3,
    padding: 16,
    width: Platform.OS === 'web' ? 280 : '100%' as any,
    ...(Platform.OS === 'web' ? { cursor: 'pointer' as any } : {}),
  },
  threadCardActive: {
    borderColor: colors.rubric,
    borderLeftWidth: 3,
  },
  tcTopic: {
    fontFamily: fonts.bodyMedium,
    fontSize: 14,
    color: colors.ink,
    marginBottom: 4,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  tcDesc: {
    fontFamily: fonts.readingItalic,
    fontSize: 12,
    color: colors.textSecondary,
    lineHeight: 17,
    marginBottom: 8,
  },
  tcDotRow: {
    flexDirection: 'row',
    gap: 4,
    marginBottom: 8,
  },
  tcDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  tcDotRead: { backgroundColor: colors.ink },
  tcDotReading: {
    backgroundColor: colors.parchment,
    borderWidth: 2,
    borderColor: colors.rubric,
  },
  tcDotUnread: { backgroundColor: colors.rule },
  tcMeta: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: colors.textMuted,
  },
  tcMetaGreen: { color: colors.claimNew },

  thinRule: {
    height: 1,
    backgroundColor: colors.rule,
    marginVertical: 24,
  },

  // Thread detail (web: 2-column)
  threadDetailWeb: {
    flexDirection: 'row',
    gap: 28,
  } as any,
  threadDetailLeft: {
    flex: 1,
  } as any,
  threadDetailRight: {
    width: 260,
    paddingLeft: 24,
    borderLeftWidth: 1,
    borderLeftColor: colors.rule,
  } as any,

  // Sequence items
  seqItem: {
    flexDirection: 'row',
    ...(Platform.OS === 'web' ? { cursor: 'pointer' as any } : {}),
  },
  seqGutter: {
    width: 40,
    alignItems: 'center',
  },
  seqMarker: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 1.5,
    borderColor: colors.rule,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.parchment,
    zIndex: 1,
  },
  seqMarkerDone: {
    backgroundColor: colors.ink,
    borderColor: colors.ink,
  },
  seqMarkerActive: {
    borderColor: colors.rubric,
    borderWidth: 2,
  },
  seqMarkerNext: {
    borderStyle: 'dashed' as any,
    borderColor: colors.textMuted,
  },
  seqMarkerText: {
    fontFamily: fonts.ui,
    fontSize: 9,
    color: colors.textMuted,
  },
  seqMarkerTextDone: { color: colors.parchment },
  seqMarkerTextActive: { color: colors.rubric },
  seqLine: {
    width: 1,
    flex: 1,
    minHeight: 16,
  },
  seqLineSolid: { backgroundColor: colors.ink },
  seqLineDashed: {
    backgroundColor: colors.rule,
  },
  seqContent: {
    flex: 1,
    paddingLeft: 10,
    paddingBottom: 20,
  },
  seqTitle: {
    fontFamily: fonts.bodyMedium,
    fontSize: 13.5,
    color: colors.ink,
    lineHeight: 18,
    marginBottom: 2,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  seqTitleDone: { color: colors.textSecondary },
  seqTitleActive: { color: colors.rubric },
  seqSource: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: colors.textMuted,
  },

  // Bridge insights
  insightLabel: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: colors.textMuted,
    textTransform: 'uppercase' as any,
    letterSpacing: 0.3,
    marginBottom: 10,
  },
  bridgeBox: {
    padding: 12,
    backgroundColor: 'rgba(139, 37, 0, 0.03)',
    borderRadius: 3,
    marginBottom: 10,
  },
  bridgeText: {
    fontFamily: fonts.readingItalic,
    fontSize: 12.5,
    color: colors.textSecondary,
    lineHeight: 18,
  },
});
