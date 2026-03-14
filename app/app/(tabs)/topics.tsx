import { useState, useMemo, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { getArticles, getArticleById, getReadingState, getSyntheses, isSynthesisCompleted } from '../../data/store';
import { Article, TopicSynthesis } from '../../data/types';
import { logEvent } from '../../data/logger';
import { getDisplayTitle, normalizeTopic, displayTopic } from '../../lib/display-utils';
import { colors, fonts, type, spacing, layout } from '../../design/tokens';
import { isKnowledgeReady, getDeltaReportForTopic } from '../../data/knowledge-engine';
import { spawnTopicResearch } from '../../lib/chat-api';
import DoubleRule from '../../components/DoubleRule';
import { useKeyboardShortcuts, type ShortcutMap } from '../../hooks/useKeyboardShortcuts';

// --- Compact Article Row ---

function CompactArticleRow({ article }: { article: Article }) {
  const router = useRouter();
  const state = getReadingState(article.id);
  const dotColor = state.status === 'reading'
    ? colors.rubric
    : state.status === 'read'
      ? colors.claimNew
      : colors.rule;

  return (
    <Pressable
      style={({ pressed }) => [
        styles.compactRow,
        pressed && { opacity: 0.9 },
      ]}
      onPress={() => {
        logEvent('topics_article_tap', { article_id: article.id });
        router.push({ pathname: '/reader', params: { id: article.id } });
      }}
    >
      <View style={[styles.statusDot, { backgroundColor: dotColor }]} />
      <View style={styles.compactContent}>
        <Text style={styles.compactTitle} numberOfLines={1}>
          {getDisplayTitle(article)}
        </Text>
        <Text style={styles.compactMeta}>
          {article.hostname} {'\u00b7'} {article.estimated_read_minutes} min
        </Text>
      </View>
    </Pressable>
  );
}

// --- Extract first prose paragraph from synthesis markdown ---

function extractPreview(markdown: string, maxLen = 200): string {
  const lines = markdown.split('\n');
  for (const line of lines) {
    const t = line.trim();
    if (t && !t.startsWith('#') && !t.startsWith('>') && !t.startsWith('<!--') && !t.startsWith('- ') && !t.startsWith('*') && t.length > 40) {
      // Strip markdown links: [text](url) → text
      const clean = t.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1').replace(/\*\*/g, '');
      return clean.length > maxLen ? clean.slice(0, maxLen).replace(/\s\S*$/, '') + '…' : clean;
    }
  }
  return '';
}

function extractTensionLabels(tensions: TopicSynthesis['tensions']): string[] {
  return tensions.slice(0, 3).map(t => {
    if (typeof t === 'string') return t.length > 60 ? t.slice(0, 60) + '…' : t;
    return t.label;
  });
}

// --- Synthesis Card (compact, for mobile + inline use) ---

function SynthesisCard({ synthesis }: { synthesis: TopicSynthesis }) {
  const router = useRouter();
  const completed = isSynthesisCompleted(synthesis.cluster_id);
  const [hovered, setHovered] = useState(false);

  const claimCoverage = synthesis.total_claims_in_cluster > 0
    ? Math.round((synthesis.total_claims_covered / synthesis.total_claims_in_cluster) * 100)
    : 0;

  return (
    <Pressable
      style={[
        synthesisStyles.card,
        completed && synthesisStyles.cardCompleted,
        hovered && { backgroundColor: colors.parchmentHover },
      ]}
      onPress={() => {
        logEvent('synthesis_card_tap', { cluster_id: synthesis.cluster_id, label: synthesis.label });
        router.push({ pathname: '/synthesis-reader', params: { clusterId: synthesis.cluster_id } });
      }}
      {...(Platform.OS === 'web' ? {
        onMouseEnter: () => setHovered(true),
        onMouseLeave: () => setHovered(false),
      } as any : {})}
    >
      <View style={synthesisStyles.cardHeader}>
        <Text style={synthesisStyles.cardLabel}>
          <Text style={{ color: colors.rubric }}>{'\u2726'} </Text>
          Synthesis
        </Text>
        {completed && (
          <Text style={synthesisStyles.completedBadge}>{'\u2713'} Read</Text>
        )}
      </View>
      <Text style={synthesisStyles.cardTitle} numberOfLines={2}>{synthesis.label}</Text>
      <Text style={synthesisStyles.cardStats}>
        {synthesis.total_articles} articles {'\u00b7'} {synthesis.total_claims_covered} claims
        {claimCoverage > 0 ? ` \u00b7 ${claimCoverage}% coverage` : ''}
      </Text>
      {!completed && (
        <Text style={synthesisStyles.cardAction}>Read synthesis {'\u2192'}</Text>
      )}
    </Pressable>
  );
}

// --- Rich Synthesis Card (2-col grid on web) ---

function RichSynthesisCard({ synthesis }: { synthesis: TopicSynthesis }) {
  const router = useRouter();
  const completed = isSynthesisCompleted(synthesis.cluster_id);
  const [hovered, setHovered] = useState(false);

  const preview = useMemo(() => extractPreview(synthesis.synthesis_markdown, 220), [synthesis]);
  const tensionLabels = useMemo(() => extractTensionLabels(synthesis.tensions), [synthesis]);

  const articleTitles = useMemo(() => {
    return synthesis.article_ids.slice(0, 4).map(id => {
      const a = getArticleById(id);
      return a ? getDisplayTitle(a) : null;
    }).filter(Boolean) as string[];
  }, [synthesis]);

  const remaining = synthesis.article_ids.length - articleTitles.length;

  return (
    <Pressable
      style={[
        richCardStyles.card,
        completed && richCardStyles.cardCompleted,
        hovered && richCardStyles.cardHovered,
      ] as any}
      onPress={() => {
        logEvent('synthesis_card_tap', { cluster_id: synthesis.cluster_id, label: synthesis.label });
        router.push({ pathname: '/synthesis-reader', params: { clusterId: synthesis.cluster_id } });
      }}
      {...(Platform.OS === 'web' ? {
        onMouseEnter: () => setHovered(true),
        onMouseLeave: () => setHovered(false),
      } as any : {})}
    >
      {/* Title */}
      <Text style={richCardStyles.title} numberOfLines={2}>{synthesis.label}</Text>

      {/* Preview paragraph */}
      {preview ? (
        <Text style={richCardStyles.preview} numberOfLines={3}>{preview}</Text>
      ) : null}

      {/* Tensions as pills */}
      {tensionLabels.length > 0 && (
        <View style={richCardStyles.tensionRow}>
          <Text style={richCardStyles.tensionIcon}>{'\u26A1'}</Text>
          <Text style={richCardStyles.tensionText} numberOfLines={2}>
            {tensionLabels.join(' · ')}
          </Text>
        </View>
      )}

      {/* Source articles */}
      <View style={richCardStyles.sourcesSection}>
        {articleTitles.map((title, i) => (
          <Text key={i} style={richCardStyles.sourceTitle} numberOfLines={1}>
            {'\u00b7'} {title}
          </Text>
        ))}
        {remaining > 0 && (
          <Text style={richCardStyles.sourceMore}>+{remaining} more</Text>
        )}
      </View>

      {/* Footer */}
      <View style={richCardStyles.footer}>
        {completed ? (
          <Text style={richCardStyles.completedBadge}>{'\u2713'} Read</Text>
        ) : (
          <Text style={richCardStyles.readLink}>Read {'\u2192'}</Text>
        )}
        <Text style={richCardStyles.articleCount}>{synthesis.total_articles} articles</Text>
      </View>
    </Pressable>
  );
}

// --- Topic Cluster ---

function TopicCluster({ topic, articles, expanded, onToggle, matchingSynthesis }: {
  topic: string;
  articles: Article[];
  expanded: boolean;
  onToggle: () => void;
  matchingSynthesis?: TopicSynthesis;
}) {
  const knowledgeReady = isKnowledgeReady();
  const delta = knowledgeReady ? getDeltaReportForTopic(topic) : null;
  const label = displayTopic(topic);

  // Count reading states
  const readCount = articles.filter(a => getReadingState(a.id).status === 'read').length;
  const readingCount = articles.filter(a => getReadingState(a.id).status === 'reading').length;

  return (
    <View style={styles.cluster}>
      <Pressable
        style={({ pressed }) => [
          styles.clusterHeader,
          pressed && { opacity: 0.85 },
        ]}
        onPress={() => {
          onToggle();
          logEvent('topics_cluster_toggle', { topic, expanded: !expanded });
        }}
      >
        <View style={styles.clusterHeaderLeft}>
          <Text style={styles.clusterName}>{label}</Text>
          <Text style={styles.clusterCount}>
            {articles.length} article{articles.length !== 1 ? 's' : ''}
            {readCount > 0 ? ` \u00b7 ${readCount} read` : ''}
            {readingCount > 0 ? ` \u00b7 ${readingCount} in progress` : ''}
          </Text>
        </View>
        <Text style={styles.clusterChevron}>{expanded ? '\u2013' : '+'}</Text>
      </Pressable>

      {/* Knowledge progress bar */}
      {delta && delta.claim_count > 0 ? (
        <View style={styles.knowledgeBar}>
          <View style={[
            styles.knowledgeBarNew,
            { flex: delta.top_claims.length },
          ]} />
          <View style={[
            styles.knowledgeBarKnown,
            { flex: delta.claim_count - delta.top_claims.length },
          ]} />
        </View>
      ) : null}

      {expanded ? (
        <View style={styles.clusterBody}>
          {/* Synthesis card */}
          {matchingSynthesis ? (
            <SynthesisCard synthesis={matchingSynthesis} />
          ) : null}

          {/* Delta report */}
          {delta && delta.summary ? (
            <View style={styles.deltaSection}
              onLayout={() => logEvent('delta_report_viewed', { topic, claim_count: delta.claim_count, article_count: delta.article_count })}
            >
              <Text style={styles.sectionHead}>
                <Text style={{ color: colors.rubric }}>{'\u2726'} </Text>
                {"What\u2019s new in "}{label}
              </Text>
              <Text style={styles.deltaSummary}>{delta.summary}</Text>
              {delta.top_claims.slice(0, 3).map((claim, i) => (
                <View key={i} style={styles.deltaClaim}>
                  <Text style={styles.deltaClaimText}>{claim.text}</Text>
                </View>
              ))}
            </View>
          ) : null}

          {/* Article list */}
          {articles.map(a => (
            <CompactArticleRow key={a.id} article={a} />
          ))}

          {/* Research button */}
          <Pressable
            onPress={async () => {
              try {
                await spawnTopicResearch(
                  topic,
                  `Topic: ${label}. ${articles.length} articles.`,
                  articles.map(a => a.title),
                );
                Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
                logEvent('topic_research_spawned', { topic });
              } catch (e) {
                logEvent('topic_research_error', { topic, error: String(e) });
              }
            }}
            style={styles.researchButton}
          >
            <Text style={styles.researchButtonText}>↗ Find more on {label}</Text>
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}

// --- Web Article Row (wider, with hover) ---

function WebArticleRow({ article }: { article: Article }) {
  const router = useRouter();
  const state = getReadingState(article.id);
  const [hovered, setHovered] = useState(false);
  const dotColor = state.status === 'reading'
    ? colors.rubric
    : state.status === 'read'
      ? colors.claimNew
      : colors.rule;

  return (
    <Pressable
      style={[
        webStyles.articleRow,
        hovered && { backgroundColor: colors.parchmentHover },
      ]}
      onPress={() => {
        logEvent('topics_article_tap', { article_id: article.id });
        router.push({ pathname: '/reader', params: { id: article.id } });
      }}
      {...Platform.select({
        web: {
          onMouseEnter: () => setHovered(true),
          onMouseLeave: () => setHovered(false),
        },
        default: {},
      })}
    >
      <View style={[styles.statusDot, { backgroundColor: dotColor }]} />
      <View style={{ flex: 1 }}>
        <Text style={webStyles.articleTitle} numberOfLines={1}>
          {getDisplayTitle(article)}
        </Text>
        {article.one_line_summary ? (
          <Text style={webStyles.articleSummary} numberOfLines={1}>
            {article.one_line_summary}
          </Text>
        ) : null}
        <Text style={styles.compactMeta}>
          {article.hostname} {'\u00b7'} {article.estimated_read_minutes} min
          {state.status === 'reading' ? ' \u00b7 in progress' : ''}
          {state.status === 'read' ? ' \u00b7 read' : ''}
        </Text>
      </View>
      {hovered ? (
        <Text style={webStyles.openHint}>Open \u2192</Text>
      ) : null}
    </Pressable>
  );
}

// --- Web Detail Panel ---

function WebDetailPanel({ topic, articles, matchingSynthesis }: { topic: string; articles: Article[]; matchingSynthesis?: TopicSynthesis }) {
  const knowledgeReady = isKnowledgeReady();
  const delta = knowledgeReady ? getDeltaReportForTopic(topic) : null;
  const label = displayTopic(topic);

  const readCount = articles.filter(a => getReadingState(a.id).status === 'read').length;
  const readingCount = articles.filter(a => getReadingState(a.id).status === 'reading').length;

  return (
    <View style={webStyles.detailContent}>
      {/* Topic header */}
      <Text style={webStyles.detailTitle}>
        <Text style={{ color: colors.rubric }}>{'\u2726'} </Text>
        {label}
        <Text style={webStyles.detailCount}> ({articles.length})</Text>
      </Text>

      <Text style={webStyles.detailMeta}>
        {articles.length} article{articles.length !== 1 ? 's' : ''}
        {readCount > 0 ? ` \u00b7 ${readCount} read` : ''}
        {readingCount > 0 ? ` \u00b7 ${readingCount} in progress` : ''}
      </Text>

      {/* Synthesis card */}
      {matchingSynthesis ? (
        <View style={{ marginTop: 8, marginBottom: 4 }}>
          <SynthesisCard synthesis={matchingSynthesis} />
        </View>
      ) : null}

      {/* Knowledge bar */}
      {delta && delta.claim_count > 0 ? (
        <View style={[styles.knowledgeBar, { marginTop: 8, marginBottom: 12 }]}>
          <View style={[
            styles.knowledgeBarNew,
            { flex: delta.top_claims.length },
          ]} />
          <View style={[
            styles.knowledgeBarKnown,
            { flex: delta.claim_count - delta.top_claims.length },
          ]} />
        </View>
      ) : null}

      {/* Delta report */}
      {delta && delta.summary ? (
        <View
          style={webStyles.deltaSection}
          onLayout={() => logEvent('delta_report_viewed', { topic, claim_count: delta.claim_count, article_count: delta.article_count })}
        >
          <Text style={styles.deltaSummary}>{delta.summary}</Text>
          {delta.top_claims.slice(0, 4).map((claim, i) => (
            <View key={i} style={styles.deltaClaim}>
              <Text style={styles.deltaClaimText}>{claim.text}</Text>
            </View>
          ))}
        </View>
      ) : null}

      {/* Divider before articles */}
      <View style={webStyles.detailDivider} />

      {/* Article list */}
      {articles.map(a => (
        <WebArticleRow key={a.id} article={a} />
      ))}

      {/* Research button */}
      <Pressable
        onPress={async () => {
          try {
            await spawnTopicResearch(
              topic,
              `Topic: ${label}. ${articles.length} articles.`,
              articles.map(a => a.title),
            );
            logEvent('topic_research_spawned', { topic });
          } catch (e) {
            logEvent('topic_research_error', { topic, error: String(e) });
          }
        }}
        style={webStyles.researchButton}
      >
        <Text style={styles.researchButtonText}>{'\u2197'} Find more on {label}</Text>
      </Pressable>
    </View>
  );
}

// --- Topics Screen ---

export default function TopicsScreen() {
  const router = useRouter();
  const [expandedTopic, setExpandedTopic] = useState<string | null>(null);
  const [selectedTopic, setSelectedTopic] = useState<string | null>(null);
  const [focusedTopicIndex, setFocusedTopicIndex] = useState(-1);

  const allSyntheses = useMemo(() => getSyntheses(), []);

  const topicGroups = useMemo(() => {
    const articles = getArticles();
    const groups = new Map<string, Article[]>();

    for (const article of articles) {
      const topics = article.interest_topics || [];
      const raw = topics[0]?.broad || article.topics[0] || 'Other';
      const key = normalizeTopic(raw);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(article);
    }

    return [...groups.entries()]
      .sort((a, b) => b[1].length - a[1].length);
  }, []);

  // Match syntheses to topic groups by article overlap
  const synthesisByTopic = useMemo(() => {
    const map = new Map<string, TopicSynthesis>();
    for (const [topic, articles] of topicGroups) {
      const articleIds = new Set(articles.map(a => a.id));
      let bestMatch: TopicSynthesis | null = null;
      let bestOverlap = 0;
      for (const s of allSyntheses) {
        const overlap = s.article_ids.filter(id => articleIds.has(id)).length;
        if (overlap > bestOverlap) {
          bestOverlap = overlap;
          bestMatch = s;
        }
      }
      if (bestMatch && bestOverlap >= 2) {
        map.set(topic, bestMatch);
      }
    }
    return map;
  }, [topicGroups, allSyntheses]);

  const selectedGroup = topicGroups.find(([t]) => t === selectedTopic);

  // Scroll focused topic row into view on web
  const scrollToTopic = useCallback((index: number) => {
    if (Platform.OS !== 'web' || index < 0 || index >= topicGroups.length) return;
    const topic = topicGroups[index][0];
    const el = document.getElementById(`topic-row-${topic}`);
    el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [topicGroups]);

  // Keyboard shortcuts (web only)
  const topicsShortcuts = useMemo((): ShortcutMap => ({
    j: { handler: () => setFocusedTopicIndex(i => {
      const next = Math.min(i + 1, topicGroups.length - 1);
      scrollToTopic(next);
      return next;
    }), label: 'next topic' },
    k: { handler: () => setFocusedTopicIndex(i => {
      const prev = Math.max(i - 1, 0);
      scrollToTopic(prev);
      return prev;
    }), label: 'prev topic' },
    Enter: { handler: () => {
      if (focusedTopicIndex >= 0 && focusedTopicIndex < topicGroups.length) {
        const topic = topicGroups[focusedTopicIndex][0];
        const wasSelected = selectedTopic === topic;
        setSelectedTopic(wasSelected ? null : topic);
        logEvent('keyboard_shortcut', { key: 'Enter', action: 'select_topic', screen: 'topics', topic });
      }
    }, label: 'select topic' },
    o: { handler: () => {
      // Prefer the selected topic (detail panel visible), fall back to focused topic
      const group = selectedGroup
        || (focusedTopicIndex >= 0 && focusedTopicIndex < topicGroups.length
          ? topicGroups[focusedTopicIndex]
          : null);
      if (group) {
        const [topic, articles] = group;
        if (articles.length > 0) {
          logEvent('keyboard_shortcut', { key: 'o', action: 'open_article', screen: 'topics', article_id: articles[0].id, topic });
          router.push({ pathname: '/reader', params: { id: articles[0].id } });
        }
      }
    }, label: 'open article' },
  }), [topicGroups, focusedTopicIndex, selectedTopic, selectedGroup, scrollToTopic, router]);

  useKeyboardShortcuts(topicsShortcuts);

  // --- Web layout ---
  if (Platform.OS === 'web') {
    return (
      <ScrollView style={styles.container} contentContainerStyle={styles.contentContainer}>
        <View style={webStyles.headerArea}>
          <Text style={styles.headerTitle}>Topics</Text>
          <Text style={styles.headerSubtitle}>
            {allSyntheses.length} syntheses across {topicGroups.length} topics
          </Text>
        </View>

        <DoubleRule />

        {/* 2-column synthesis grid */}
        <View style={webStyles.synthGrid as any}>
          {allSyntheses
            .sort((a, b) => b.total_articles - a.total_articles)
            .map(s => (
              <RichSynthesisCard key={s.cluster_id} synthesis={s} />
            ))}
        </View>

        {/* Remaining topics without syntheses */}
        {topicGroups.filter(([topic]) => !synthesisByTopic.has(topic)).length > 0 && (
          <View style={webStyles.uncoveredSection}>
            <Text style={[styles.sectionHead, { marginBottom: 12 }]}>
              <Text style={{ color: colors.rubric }}>{'\u2726'} </Text>
              Topics without syntheses
            </Text>
            <View style={webStyles.uncoveredGrid as any}>
              {topicGroups
                .filter(([topic]) => !synthesisByTopic.has(topic))
                .map(([topic, articles]) => {
                  const label = displayTopic(topic);
                  const readCount = articles.filter(a => getReadingState(a.id).status === 'read').length;
                  return (
                    <Pressable
                      key={topic}
                      style={webStyles.uncoveredRow}
                      onPress={() => {
                        setSelectedTopic(topic);
                        logEvent('topics_uncovered_tap', { topic });
                      }}
                      {...Platform.select({ web: { onMouseEnter: () => {}, onMouseLeave: () => {} }, default: {} })}
                    >
                      <Text style={webStyles.uncoveredName}>{label}</Text>
                      <Text style={webStyles.uncoveredMeta}>
                        {articles.length} article{articles.length !== 1 ? 's' : ''}
                        {readCount > 0 ? ` · ${readCount} read` : ''}
                      </Text>
                    </Pressable>
                  );
                })}
            </View>
          </View>
        )}
      </ScrollView>
    );
  }

  // --- Mobile layout (unchanged) ---
  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.contentContainer}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Topics</Text>
        <Text style={styles.headerSubtitle}>
          {topicGroups.length} topic{topicGroups.length !== 1 ? 's' : ''} across your reading
        </Text>
      </View>

      <DoubleRule />

      <View style={styles.body}>
        <Text style={styles.sectionHead}>
          <Text style={{ color: colors.rubric }}>{'\u2726'} </Text>
          Your Topics
        </Text>

        {topicGroups.length === 0 ? (
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>No topics yet</Text>
            <Text style={styles.emptySubtitle}>
              Topics will appear as articles are imported
            </Text>
          </View>
        ) : null}

        {topicGroups.map(([topic, articles]) => (
          <TopicCluster
            key={topic}
            topic={topic}
            articles={articles}
            expanded={expandedTopic === topic}
            onToggle={() => setExpandedTopic(
              expandedTopic === topic ? null : topic
            )}
            matchingSynthesis={synthesisByTopic.get(topic)}
          />
        ))}
      </View>
    </ScrollView>
  );
}

// --- Web Topic Row (left panel) ---

function TopicRow({ topic, label, articleCount, readCount, readingCount, isSelected, isFocused, onSelect }: {
  topic: string;
  label: string;
  articleCount: number;
  readCount: number;
  readingCount: number;
  isSelected: boolean;
  isFocused?: boolean;
  onSelect: () => void;
}) {
  const [hovered, setHovered] = useState(false);
  const knowledgeReady = isKnowledgeReady();
  const delta = knowledgeReady ? getDeltaReportForTopic(topic) : null;
  const hasNew = delta && delta.top_claims.length > 0;

  return (
    <Pressable
      nativeID={`topic-row-${topic}`}
      style={[
        webStyles.topicRow,
        isSelected && webStyles.topicRowSelected,
        isFocused && !isSelected && webStyles.topicRowFocused,
        hovered && !isSelected && !isFocused && { backgroundColor: colors.parchmentHover },
      ]}
      onPress={onSelect}
      {...Platform.select({
        web: {
          onMouseEnter: () => setHovered(true),
          onMouseLeave: () => setHovered(false),
        },
        default: {},
      })}
    >
      <View style={{ flex: 1 }}>
        <Text style={[
          webStyles.topicRowName,
          isSelected && { color: colors.ink },
        ]}>
          {label}
        </Text>
        <Text style={webStyles.topicRowMeta}>
          {articleCount} article{articleCount !== 1 ? 's' : ''}
          {readCount > 0 ? ` \u00b7 ${readCount} read` : ''}
          {readingCount > 0 ? ` \u00b7 ${readingCount} reading` : ''}
        </Text>
      </View>
      {hasNew ? (
        <View style={webStyles.newBadge}>
          <Text style={webStyles.newBadgeText}>{delta.top_claims.length} new</Text>
        </View>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.parchment,
  },
  contentContainer: {
    paddingBottom: 40,
  },

  // Header
  header: {
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

  // Body
  body: {
    paddingHorizontal: layout.screenPadding,
    paddingTop: 16,
  },
  sectionHead: {
    ...type.sectionHead,
    color: colors.rubric,
    marginBottom: 12,
  },

  // Topic cluster
  cluster: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.rule,
    marginBottom: 4,
  },
  clusterHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
  },
  clusterHeaderLeft: {
    flex: 1,
  },
  clusterName: {
    fontFamily: fonts.bodyItalic,
    fontSize: 16,
    color: colors.rubric,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' } : {}),
  },
  clusterCount: {
    ...type.metadata,
    color: colors.textMuted,
    marginTop: 2,
  },
  clusterChevron: {
    fontFamily: fonts.display,
    fontSize: 18,
    color: colors.textMuted,
    paddingLeft: 12,
  },

  // Knowledge bar
  knowledgeBar: {
    flexDirection: 'row',
    height: layout.progressBarHeight,
    marginBottom: 4,
  },
  knowledgeBarNew: {
    backgroundColor: colors.claimNew,
  },
  knowledgeBarKnown: {
    backgroundColor: colors.claimKnown,
  },

  // Cluster body
  clusterBody: {
    paddingBottom: 8,
  },

  // Delta report
  deltaSection: {
    paddingVertical: 8,
    marginBottom: 4,
  },
  deltaSummary: {
    fontFamily: fonts.reading,
    fontSize: 14,
    lineHeight: 20,
    color: colors.textBody,
    marginBottom: 8,
  },
  deltaClaim: {
    borderLeftWidth: layout.claimBorderWidth,
    borderLeftColor: colors.claimNew,
    paddingLeft: 10,
    marginBottom: 6,
  },
  deltaClaimText: {
    fontFamily: fonts.reading,
    fontSize: 12,
    lineHeight: 17,
    color: colors.textBody,
  },

  // Compact article row
  compactRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
    minHeight: 44,
  },
  statusDot: {
    width: 4,
    height: 4,
    borderRadius: 2,
    marginRight: 10,
  },
  compactContent: {
    flex: 1,
  },
  compactTitle: {
    ...type.entryTitle,
    color: colors.textPrimary,
    fontSize: 14,
  },
  compactMeta: {
    ...type.metadata,
    color: colors.textMuted,
    marginTop: 1,
  },

  // Research button
  researchButton: {
    paddingVertical: 10,
    paddingHorizontal: 4,
    marginTop: 4,
  },
  researchButtonText: {
    fontFamily: fonts.ui,
    fontSize: 13,
    color: colors.claimNew,
  },

  // Empty state
  empty: {
    justifyContent: 'center',
    alignItems: 'center',
    paddingTop: 60,
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
    textAlign: 'center',
  },
});

// --- Synthesis Card Styles ---

const synthesisStyles = StyleSheet.create({
  card: {
    borderLeftWidth: layout.claimBorderWidth,
    borderLeftColor: colors.rubric,
    paddingHorizontal: 14,
    paddingVertical: 12,
    marginBottom: 8,
    ...(Platform.OS === 'web' ? { background: 'linear-gradient(135deg, rgba(240,236,226,0.5), rgba(247,244,236,0))' as any, cursor: 'pointer' as any } : { backgroundColor: 'rgba(240,236,226,0.3)' }),
  },
  cardCompleted: {
    borderLeftColor: colors.claimNew,
    opacity: 0.75,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  cardLabel: {
    ...type.sectionHead,
    color: colors.rubric,
    fontSize: 9,
    letterSpacing: 1.2,
  },
  completedBadge: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: colors.claimNew,
  },
  cardTitle: {
    fontFamily: fonts.bodyMedium,
    fontSize: 15,
    lineHeight: 20,
    color: colors.textPrimary,
    marginBottom: 4,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  cardStats: {
    ...type.metadata,
    color: colors.textMuted,
    marginBottom: 4,
  },
  cardAction: {
    fontFamily: fonts.ui,
    fontSize: 12,
    color: colors.rubric,
    marginTop: 2,
  },
});

// --- Rich Synthesis Card Styles ---

const richCardStyles: Record<string, any> = Platform.OS === 'web' ? {
  card: {
    borderTopWidth: 2,
    borderTopColor: colors.rule,
    paddingTop: 16,
    paddingBottom: 14,
    paddingHorizontal: 2,
    cursor: 'pointer',
    transition: 'border-color 0.15s',
  },
  cardCompleted: {
    borderTopColor: colors.claimNew,
    opacity: 0.7,
  },
  cardHovered: {
    borderTopColor: colors.rubric,
  },
  title: {
    fontFamily: fonts.displaySemiBold,
    fontSize: 19,
    lineHeight: 24,
    color: colors.ink,
    marginBottom: 8,
    fontWeight: '600',
  },
  preview: {
    fontFamily: fonts.reading,
    fontSize: 14,
    lineHeight: 21,
    color: colors.textSecondary,
    marginBottom: 10,
  },
  tensionRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
    marginBottom: 10,
    paddingLeft: 2,
  },
  tensionIcon: {
    fontSize: 11,
    color: '#b89840',
    marginTop: 2,
  },
  tensionText: {
    fontFamily: fonts.readingItalic,
    fontSize: 12,
    lineHeight: 17,
    color: colors.textSecondary,
    fontStyle: 'italic',
    flex: 1,
  },
  sourcesSection: {
    marginBottom: 10,
  },
  sourceTitle: {
    fontFamily: fonts.ui,
    fontSize: 11,
    lineHeight: 17,
    color: colors.textMuted,
  },
  sourceMore: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.textMuted,
    marginTop: 1,
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 4,
  },
  readLink: {
    fontFamily: fonts.ui,
    fontSize: 12,
    color: colors.rubric,
  },
  completedBadge: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.claimNew,
  },
  articleCount: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.textMuted,
  },
} : {};

// --- Web Styles (plain object to allow CSS Grid properties) ---

const webStyles: Record<string, any> = {
  headerArea: {
    maxWidth: layout.webFeedMaxWidth,
    marginHorizontal: 'auto',
    width: '100%',
    paddingHorizontal: layout.screenPadding,
    paddingTop: 12,
    paddingBottom: 8,
  },
  synthGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '0 32px',
    maxWidth: layout.webFeedMaxWidth,
    marginHorizontal: 'auto',
    width: '100%',
    paddingHorizontal: layout.screenPadding,
    paddingTop: 20,
  },
  uncoveredSection: {
    maxWidth: layout.webFeedMaxWidth,
    marginHorizontal: 'auto',
    width: '100%',
    paddingHorizontal: layout.screenPadding,
    paddingTop: 32,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.rule,
    marginTop: 24,
  },
  uncoveredGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr 1fr',
    gap: 12,
  },
  uncoveredRow: {
    paddingVertical: 8,
    paddingHorizontal: 10,
    cursor: 'pointer',
  },
  uncoveredName: {
    fontFamily: fonts.bodyItalic,
    fontSize: 14,
    color: colors.rubric,
    fontStyle: 'italic',
  },
  uncoveredMeta: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: colors.textMuted,
    marginTop: 2,
  },
  backButton: {
    marginBottom: 8,
    cursor: 'pointer',
  },
  backButtonText: {
    fontFamily: fonts.ui,
    fontSize: 13,
    color: colors.rubric,
  },
  masterDetail: {
    display: 'grid',
    gridTemplateColumns: '320px 1fr',
    gap: 32,
    maxWidth: layout.webFeedMaxWidth,
    marginHorizontal: 'auto',
    width: '100%',
    minHeight: 600,
    paddingHorizontal: layout.screenPadding,
    paddingTop: 20,
  },

  // Left panel
  masterPanel: {
    borderRightWidth: StyleSheet.hairlineWidth,
    borderRightColor: colors.rule,
    paddingRight: 16,
  },
  topicRow: {
    paddingVertical: 10,
    paddingHorizontal: 10,
    paddingLeft: 12,
    borderLeftWidth: 3,
    borderLeftColor: 'transparent',
    cursor: 'pointer',
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: 2,
    marginBottom: 1,
  },
  topicRowSelected: {
    borderLeftColor: colors.rubric,
    backgroundColor: colors.parchmentDark,
  },
  topicRowFocused: {
    borderLeftColor: colors.rubric,
    backgroundColor: 'rgba(139,37,0,0.03)',
  },
  topicRowName: {
    fontFamily: fonts.bodyItalic,
    fontSize: 15,
    color: colors.rubric,
    fontStyle: 'italic',
  },
  topicRowMeta: {
    ...type.metadata,
    color: colors.textMuted,
    marginTop: 2,
  },
  newBadge: {
    backgroundColor: colors.claimNew,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 3,
    marginLeft: 8,
  },
  newBadgeText: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: '#ffffff',
  },

  // Right panel
  detailPanel: {
    minHeight: 400,
  },
  detailContent: {
    paddingTop: 4,
  },
  detailTitle: {
    ...type.sectionHead,
    color: colors.rubric,
    fontSize: 12,
    letterSpacing: 1.8,
    marginBottom: 4,
  },
  detailCount: {
    fontFamily: fonts.display,
    fontSize: 12,
    color: colors.textMuted,
    letterSpacing: 0,
    textTransform: 'none',
  },
  detailMeta: {
    ...type.metadata,
    color: colors.textMuted,
    marginBottom: 4,
  },
  deltaSection: {
    paddingVertical: 8,
    paddingBottom: 12,
  },
  detailDivider: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.rule,
    marginBottom: 8,
  },

  // Articles in detail panel
  articleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 10,
    paddingHorizontal: 8,
    borderRadius: 3,
    minHeight: layout.touchTarget,
    cursor: 'pointer',
  },
  articleTitle: {
    ...type.entryTitle,
    color: colors.textPrimary,
    fontSize: 15,
  },
  articleSummary: {
    fontFamily: fonts.reading,
    fontSize: 13,
    lineHeight: 18,
    color: colors.textSecondary,
    marginTop: 2,
  },
  openHint: {
    fontFamily: fonts.ui,
    fontSize: 12,
    color: colors.rubric,
    marginLeft: 12,
    flexShrink: 0,
  },

  // Research button (web)
  researchButton: {
    paddingVertical: 12,
    paddingHorizontal: 8,
    marginTop: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.rule,
    cursor: 'pointer',
  },

  // Placeholder
  detailPlaceholder: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingTop: 120,
  },
  placeholderIcon: {
    fontFamily: fonts.display,
    fontSize: 28,
    color: colors.rule,
    marginBottom: 12,
  },
  placeholderText: {
    fontFamily: fonts.readingItalic,
    fontSize: 16,
    color: colors.textMuted,
    fontStyle: 'italic',
  },
};
