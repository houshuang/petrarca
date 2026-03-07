import { useState } from 'react';
import { View, Text, Pressable, ScrollView, StyleSheet, Platform, Linking } from 'react-native';
import { usePathname, useRouter } from 'expo-router';
import { getArticles, getConcepts, getStats, getCurrentReaderArticle, getConceptsForArticleWithState, getArticleById, updateConceptState, getConceptState } from '../data/store';
import { ConceptKnowledgeLevel } from '../data/types';
import { logEvent } from '../data/logger';
import { colors, layout } from '../design/tokens';

const NAV_ITEMS = [
  { label: 'Feed', path: '/' },
  { label: 'Library', path: '/library' },
  { label: 'Review', path: '/review' },
  { label: 'Progress', path: '/stats' },
] as const;

function getTopTopics(limit = 8): string[] {
  const topicCount = new Map<string, number>();
  for (const a of getArticles()) {
    for (const t of a.topics) {
      topicCount.set(t, (topicCount.get(t) || 0) + 1);
    }
  }
  return [...topicCount.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([topic]) => topic);
}

const STATE_DOT_COLORS: Record<ConceptKnowledgeLevel, string> = {
  unknown: colors.rubric,
  encountered: colors.claimNew,
  known: colors.textMuted,
};

function ConceptBrowserView() {
  const articleId = getCurrentReaderArticle();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [, forceUpdate] = useState(0);

  if (!articleId) return null;
  const article = getArticleById(articleId);
  if (!article) return null;

  const conceptsWithState = getConceptsForArticleWithState(articleId);

  const groups: { label: string; state: ConceptKnowledgeLevel; items: typeof conceptsWithState }[] = [
    { label: 'NEW', state: 'unknown', items: conceptsWithState.filter(c => c.state === 'unknown') },
    { label: 'LEARNING', state: 'encountered', items: conceptsWithState.filter(c => c.state === 'encountered') },
    { label: 'KNOWN', state: 'known', items: conceptsWithState.filter(c => c.state === 'known') },
  ];

  return (
    <ScrollView style={styles.conceptBrowser} showsVerticalScrollIndicator={false}>
      <Text style={styles.sectionLabel}>ARTICLE CONCEPTS</Text>
      <Text style={styles.conceptArticleTitle} numberOfLines={2}>{article.title}</Text>

      {groups.map(({ label, state, items }) => {
        if (items.length === 0) return null;
        return (
          <View key={label} style={styles.conceptGroup}>
            <Text style={styles.conceptGroupLabel}>{label} ({items.length})</Text>
            {items.map(({ concept }) => {
              const isExpanded = expandedId === concept.id;
              const currentState = getConceptState(concept.id)?.state || 'unknown';
              return (
                <View key={concept.id}>
                  <Pressable
                    style={({ hovered }: any) => [
                      styles.conceptRow,
                      hovered && styles.conceptRowHover,
                    ]}
                    onPress={() => {
                      setExpandedId(isExpanded ? null : concept.id);
                      logEvent('sidebar_concept_tap', { concept_id: concept.id, article_id: articleId });
                    }}
                  >
                    <View style={[styles.conceptDot, { backgroundColor: STATE_DOT_COLORS[currentState] }]} />
                    <Text style={[
                      styles.conceptName,
                      currentState === 'known' && { color: colors.textMuted, opacity: 0.7 },
                    ]}>
                      {concept.name || concept.text}
                    </Text>
                  </Pressable>

                  {isExpanded && (
                    <View style={styles.conceptDetail}>
                      {concept.description ? (
                        <Text style={styles.conceptDesc}>{concept.description}</Text>
                      ) : null}
                      <View style={styles.conceptStateToggle}>
                        {(['unknown', 'encountered', 'known'] as ConceptKnowledgeLevel[]).map(level => (
                          <Pressable
                            key={level}
                            style={[
                              styles.conceptStateBtn,
                              currentState === level && styles.conceptStateBtnActive,
                            ]}
                            onPress={() => {
                              updateConceptState(concept.id, level);
                              logEvent('sidebar_concept_state_change', { concept_id: concept.id, to: level });
                              forceUpdate(n => n + 1);
                            }}
                          >
                            <Text style={[
                              styles.conceptStateBtnText,
                              currentState === level && styles.conceptStateBtnTextActive,
                            ]}>
                              {level === 'unknown' ? 'New' : level === 'encountered' ? 'Learning' : 'Known'}
                            </Text>
                          </Pressable>
                        ))}
                      </View>
                    </View>
                  )}
                </View>
              );
            })}
          </View>
        );
      })}
    </ScrollView>
  );
}

function TopicsView() {
  const topics = getTopTopics();
  return (
    <>
      <Text style={styles.sectionLabel}>TOPICS</Text>
      <View style={styles.topicsList}>
        {topics.map(topic => (
          <Pressable key={topic}>
            <Text style={styles.topicItem}>{topic}</Text>
          </Pressable>
        ))}
      </View>
    </>
  );
}

export function WebSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const stats = getStats();
  const conceptCount = getConcepts().length;

  const isReaderView = pathname.includes('/reader');
  const readerArticleId = getCurrentReaderArticle();

  return (
    <View style={styles.sidebar}>
      {/* Wordmark */}
      <Text style={styles.wordmark}>PETRARCA</Text>

      {/* Navigation */}
      <View style={styles.nav}>
        {NAV_ITEMS.map(({ label, path }) => {
          const active = pathname === path || (path === '/' && pathname === '');
          return (
            <Pressable
              key={path}
              style={({ hovered }: any) => [
                styles.navItem,
                active && styles.navItemActive,
                hovered && !active && styles.navItemHover,
              ]}
              onPress={() => router.push(path as any)}
            >
              <Text style={[styles.navLabel, active && styles.navLabelActive]}>
                {label}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {/* Double rule divider */}
      <View style={styles.divider}>
        <View style={styles.dividerThick} />
        <View style={styles.dividerThin} />
      </View>

      {/* Context-aware content */}
      {isReaderView && readerArticleId ? (
        <ConceptBrowserView />
      ) : (
        <TopicsView />
      )}

      {/* Stats + guide at bottom */}
      <View style={styles.statsContainer}>
        <Text style={styles.statsText}>{stats.total} articles</Text>
        <Text style={styles.statsText}>{conceptCount} concepts</Text>
        <Pressable
          style={({ hovered }: any) => [
            styles.guideLink,
            hovered && styles.guideLinkHover,
          ]}
          onPress={() => Linking.openURL('/guide/')}
        >
          <Text style={styles.guideLinkText}>User Guide</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  sidebar: {
    width: layout.sidebarNavWidth,
    minWidth: layout.sidebarNavWidth,
    backgroundColor: colors.parchmentDark,
    borderRightWidth: 1,
    borderRightColor: colors.rule,
    paddingTop: 28,
    display: 'flex' as any,
    flexDirection: 'column',
  },
  wordmark: {
    fontFamily: Platform.OS === 'web' ? "'Cormorant Garamond', Georgia, serif" : 'CormorantGaramond-SemiBold',
    fontSize: 14,
    color: colors.ink,
    letterSpacing: 3,
    paddingHorizontal: 24,
    marginBottom: 32,
    ...(Platform.OS === 'web' ? { fontWeight: '600' as any } : {}),
  },
  nav: {
    marginBottom: 4,
  },
  navItem: {
    paddingVertical: 8,
    paddingHorizontal: 24,
    borderLeftWidth: 3,
    borderLeftColor: 'transparent',
  },
  navItemActive: {
    borderLeftColor: colors.rubric,
  },
  navItemHover: {
    backgroundColor: colors.parchmentHover,
  },
  navLabel: {
    fontFamily: Platform.OS === 'web' ? "'EB Garamond', Georgia, serif" : 'EBGaramond',
    fontSize: 15,
    color: colors.textMuted,
  },
  navLabelActive: {
    color: colors.ink,
    fontFamily: Platform.OS === 'web' ? "'EB Garamond', Georgia, serif" : 'EBGaramond-Medium',
    ...(Platform.OS === 'web' ? { fontWeight: '500' as any } : {}),
  },
  divider: {
    marginHorizontal: 24,
    marginTop: 4,
    marginBottom: 16,
    gap: 5,
  },
  dividerThick: {
    height: 2,
    backgroundColor: colors.rule,
  },
  dividerThin: {
    height: 1,
    backgroundColor: colors.rule,
  },
  sectionLabel: {
    fontFamily: Platform.OS === 'web' ? "'DM Sans', sans-serif" : 'DMSans-SemiBold',
    fontSize: 10,
    letterSpacing: 1.5,
    color: colors.textMuted,
    paddingHorizontal: 24,
    marginBottom: 8,
    ...(Platform.OS === 'web' ? { fontWeight: '600' as any } : {}),
  },
  topicsList: {
    paddingHorizontal: 24,
    marginBottom: 24,
  },
  topicItem: {
    fontFamily: Platform.OS === 'web' ? "'EB Garamond', Georgia, serif" : 'EBGaramond-Italic',
    fontSize: 13,
    color: colors.textSecondary,
    paddingVertical: 4,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' as any } : {}),
  },
  statsContainer: {
    marginTop: 'auto' as any,
    paddingHorizontal: 24,
    paddingBottom: 24,
  },
  statsText: {
    fontFamily: Platform.OS === 'web' ? "'DM Sans', sans-serif" : 'DMSans',
    fontSize: 11,
    color: colors.textMuted,
    lineHeight: 19,
  },
  guideLink: {
    marginTop: 12,
    paddingVertical: 4,
    borderRadius: 3,
  },
  guideLinkHover: {
    backgroundColor: colors.parchmentHover,
  },
  guideLinkText: {
    fontFamily: Platform.OS === 'web' ? "'EB Garamond', Georgia, serif" : 'EBGaramond',
    fontSize: 13,
    color: colors.textMuted,
  },

  // Concept browser styles
  conceptBrowser: {
    flex: 1,
    paddingHorizontal: 24,
  },
  conceptArticleTitle: {
    fontFamily: Platform.OS === 'web' ? "'EB Garamond', Georgia, serif" : 'EBGaramond',
    fontSize: 13,
    color: colors.textSecondary,
    marginBottom: 16,
    lineHeight: 18,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' as any } : {}),
  },
  conceptGroup: {
    marginBottom: 16,
  },
  conceptGroupLabel: {
    fontFamily: Platform.OS === 'web' ? "'DM Sans', sans-serif" : 'DMSans-SemiBold',
    fontSize: 9,
    letterSpacing: 1.2,
    color: colors.textMuted,
    marginBottom: 6,
    ...(Platform.OS === 'web' ? { fontWeight: '600' as any } : {}),
  },
  conceptRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 5,
    paddingHorizontal: 4,
    borderRadius: 3,
    gap: 8,
  },
  conceptRowHover: {
    backgroundColor: colors.parchmentHover,
  },
  conceptDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  conceptName: {
    fontFamily: Platform.OS === 'web' ? "'EB Garamond', Georgia, serif" : 'EBGaramond',
    fontSize: 13,
    color: colors.ink,
    flex: 1,
  },
  conceptDetail: {
    paddingLeft: 18,
    paddingBottom: 8,
  },
  conceptDesc: {
    fontFamily: Platform.OS === 'web' ? "'EB Garamond', Georgia, serif" : 'EBGaramond',
    fontSize: 12,
    color: colors.textSecondary,
    lineHeight: 17,
    marginBottom: 8,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' as any } : {}),
  },
  conceptStateToggle: {
    flexDirection: 'row',
    gap: 4,
  },
  conceptStateBtn: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 3,
    borderWidth: 1,
    borderColor: colors.rule,
  },
  conceptStateBtnActive: {
    backgroundColor: colors.rubric,
    borderColor: colors.rubric,
  },
  conceptStateBtnText: {
    fontFamily: Platform.OS === 'web' ? "'DM Sans', sans-serif" : 'DMSans',
    fontSize: 10,
    color: colors.textMuted,
  },
  conceptStateBtnTextActive: {
    color: colors.parchment,
  },
});
