import { useState, useMemo } from 'react';
import { View, Text, ScrollView, Pressable, StyleSheet, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import { colors, fonts, layout } from '../design/tokens';
import { logEvent } from '../data/logger';
import { getActiveThreads, getCrossThreadBridges } from '../lib/reading-insights';
import type { ReadingThread } from '../lib/reading-insights';
import DoubleRule from '../components/DoubleRule';

export default function TrailsScreen() {
  const router = useRouter();
  const threads = useMemo(() => getActiveThreads(6), []);
  const bridges = useMemo(() => getCrossThreadBridges(3), []);
  const [expandedThread, setExpandedThread] = useState<string | null>(
    threads[0]?.topic || null
  );
  const [hoveredThread, setHoveredThread] = useState<string | null>(null);
  const [hoveredArticle, setHoveredArticle] = useState<string | null>(null);

  logEvent('trails_open');

  const expanded = threads.find(t => t.topic === expandedThread);

  // --- Shared article sequence renderer ---
  const renderArticleSequence = (thread: ReadingThread, showHoverAction: boolean) =>
    thread.articles.map((article, i) => (
      <Pressable
        key={article.id}
        style={[
          styles.seqItem,
          showHoverAction && hoveredArticle === article.id && styles.seqItemHover,
        ]}
        onPress={() => {
          logEvent('trail_article_tap', { article_id: article.id, topic: thread.topic });
          router.push({ pathname: '/reader', params: { id: article.id } });
        }}
        {...(Platform.OS === 'web' ? {
          onMouseEnter: () => setHoveredArticle(article.id),
          onMouseLeave: () => setHoveredArticle(null),
        } as any : {})}
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
          {i < thread.articles.length - 1 && (
            <View style={[
              styles.seqLine,
              article.status === 'read' ? styles.seqLineSolid : styles.seqLineDashed,
            ]} />
          )}
        </View>

        {/* Content */}
        <View style={styles.seqContent}>
          <View style={styles.seqTitleRow}>
            <Text style={[
              styles.seqTitle,
              article.status === 'read' && styles.seqTitleDone,
              article.status === 'reading' && styles.seqTitleActive,
            ]} numberOfLines={2}>
              {article.title}
            </Text>
            {showHoverAction && hoveredArticle === article.id && (
              <Text style={styles.seqOpenHint}>Open →</Text>
            )}
          </View>
          <Text style={styles.seqSource}>
            {article.source ? `${article.source} · ` : ''}
            {article.status === 'read' ? 'read'
              : article.status === 'reading' ? 'in progress'
              : article.readMinutes ? `${article.readMinutes} min` : ''}
          </Text>
        </View>
      </Pressable>
    ));

  // --- Web master-detail layout ---
  if (Platform.OS === 'web') {
    return (
      <View style={webStyles.container}>
        <View style={webStyles.contentWrap}>
          {/* Header */}
          <Pressable onPress={() => router.back()} style={styles.backBtn} hitSlop={12}>
            <Text style={styles.backText}>← Feed</Text>
          </Pressable>

          <Text style={styles.pageTitle}>Reading Trails</Text>
          <Text style={styles.pageSub}>Follow threads of connected ideas through your library</Text>
          <View style={webStyles.doubleRuleWrap}>
            <DoubleRule />
          </View>

          {/* Master-detail grid */}
          <View style={webStyles.masterDetail}>
            {/* Left panel — thread list */}
            <View style={webStyles.threadList}>
              <Text style={styles.sectionLabel}>✦ Threads</Text>
              {threads.map(thread => (
                <Pressable
                  key={thread.topic}
                  style={[
                    webStyles.threadListCard,
                    expandedThread === thread.topic && webStyles.threadListCardActive,
                    hoveredThread === thread.topic && expandedThread !== thread.topic && webStyles.threadListCardHover,
                  ]}
                  onPress={() => {
                    setExpandedThread(thread.topic);
                    logEvent('trail_thread_tap', { topic: thread.topic });
                  }}
                  {...{
                    onMouseEnter: () => setHoveredThread(thread.topic),
                    onMouseLeave: () => setHoveredThread(null),
                  } as any}
                >
                  <Text style={[
                    styles.tcTopic,
                    expandedThread === thread.topic && webStyles.tcTopicActive,
                  ]}>{thread.topic}</Text>
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

              {/* Bridges below thread list */}
              {bridges.length > 0 && (
                <>
                  <View style={styles.thinRule} />
                  <Text style={styles.sectionLabel}>✦ Bridges</Text>
                  {bridges.map((bridge, i) => (
                    <View key={i} style={styles.bridgeBox}>
                      <Text style={webStyles.bridgeTopics}>{bridge.fromTopic} ↔ {bridge.toTopic}</Text>
                      <Text style={styles.bridgeText}>{bridge.description}</Text>
                    </View>
                  ))}
                </>
              )}
            </View>

            {/* Right panel — thread detail */}
            <View style={webStyles.threadDetail}>
              {expanded ? (
                <>
                  <Text style={webStyles.detailTitle}>✦ {expanded.topic}</Text>
                  {expanded.description ? (
                    <Text style={webStyles.detailDesc}>{expanded.description}</Text>
                  ) : null}
                  <View style={webStyles.detailArticles}>
                    {renderArticleSequence(expanded, true)}
                  </View>
                </>
              ) : (
                <View style={webStyles.emptyDetail}>
                  <Text style={webStyles.emptyText}>Select a thread to see its articles</Text>
                </View>
              )}
            </View>
          </View>

          <View style={{ height: 40 }} />
        </View>
      </View>
    );
  }

  // --- Mobile layout ---
  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Header */}
      <Pressable onPress={() => router.back()} style={styles.backBtn} hitSlop={12}>
        <Text style={styles.backText}>← Feed</Text>
      </Pressable>

      <Text style={styles.pageTitle}>Reading Trails</Text>
      <Text style={styles.pageSub}>Follow threads of connected ideas through your library</Text>
      <View style={styles.doubleRuleWrap}>
        <DoubleRule />
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
          {renderArticleSequence(expanded, false)}
        </>
      )}

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

// --- Mobile styles ---
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
  doubleRuleWrap: {
    marginHorizontal: -layout.screenPadding,
    marginBottom: 28,
  },

  sectionLabel: {
    fontFamily: fonts.bodyItalic,
    fontSize: 12,
    color: colors.rubric,
    marginBottom: 14,
  },

  // Thread cards grid (mobile)
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
    width: '100%' as any,
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

  // Sequence items (shared mobile + web)
  seqItem: {
    flexDirection: 'row',
    ...(Platform.OS === 'web' ? { cursor: 'pointer' as any } : {}),
  },
  seqItemHover: {
    backgroundColor: colors.parchmentHover,
    borderRadius: 3,
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
  seqTitleRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
  },
  seqTitle: {
    fontFamily: fonts.bodyMedium,
    fontSize: 13.5,
    color: colors.ink,
    lineHeight: 18,
    marginBottom: 2,
    flex: 1,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  seqTitleDone: { color: colors.textSecondary },
  seqTitleActive: { color: colors.rubric },
  seqOpenHint: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.rubric,
    marginLeft: 8,
    flexShrink: 0,
  },
  seqSource: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: colors.textMuted,
  },

  // Bridge insights (mobile)
  bridgeBox: {
    padding: 12,
    backgroundColor: colors.parchmentHover,
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

// --- Web-only styles (plain object to support CSS Grid properties) ---
const webStyles: Record<string, any> = Platform.OS === 'web' ? {
  container: {
    flex: 1,
    backgroundColor: colors.parchment,
    overflow: 'auto',
  },
  contentWrap: {
    maxWidth: 1100,
    width: '100%',
    alignSelf: 'center',
    paddingHorizontal: 32,
    paddingTop: 16,
  },
  doubleRuleWrap: {
    marginHorizontal: -32,
    marginBottom: 28,
  },
  masterDetail: {
    display: 'grid',
    gridTemplateColumns: '320px 1fr',
    gap: 32,
  },
  threadList: {
    borderRightWidth: 1,
    borderRightColor: colors.rule,
    paddingRight: 24,
  },
  threadListCard: {
    borderWidth: 1,
    borderColor: colors.rule,
    borderRadius: 3,
    padding: 14,
    marginBottom: 10,
    cursor: 'pointer',
    transition: 'background-color 0.15s',
  },
  threadListCardActive: {
    borderColor: colors.rubric,
    borderLeftWidth: 3,
    backgroundColor: 'rgba(139, 37, 0, 0.04)',
  },
  threadListCardHover: {
    backgroundColor: colors.parchmentHover,
  },
  tcTopicActive: {
    color: colors.rubric,
  },
  threadDetail: {
    minHeight: 400,
  },
  detailTitle: {
    fontFamily: fonts.displaySemiBold,
    fontSize: 20,
    color: colors.ink,
    marginBottom: 8,
    fontWeight: '600',
  },
  detailDesc: {
    fontFamily: fonts.readingItalic,
    fontSize: 14,
    color: colors.textSecondary,
    lineHeight: 22,
    marginBottom: 24,
  },
  detailArticles: {},
  bridgeTopics: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.3,
    marginBottom: 6,
  },
  emptyDetail: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingTop: 80,
  },
  emptyText: {
    fontFamily: fonts.readingItalic,
    fontSize: 15,
    color: colors.textMuted,
  },
} : {};
