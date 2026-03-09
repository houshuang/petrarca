import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, Linking,
  NativeSyntheticEvent, NativeScrollEvent,
  Platform, Clipboard,
} from 'react-native';
import AskAI from '../components/AskAI';
import VoiceFeedback from '../components/VoiceFeedback';
import { spawnTopicResearch, ingestUrl, getIngestStatus } from '../lib/chat-api';
import { addToQueue, addToQueueFront } from '../data/queue';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { getArticleById, getArticles, getReadingState, updateReadingState, getHighlightBlockIndices, addHighlight, removeHighlight, markArticleRead, recordInterestSignal, recordTopicInterestSignalAtLevel, getCrossArticleConnections, getParagraphConnections } from '../data/store';
import { Article, ArticleEntity, FollowUpQuestion, InterestTopic } from '../data/types';
import type { CrossArticleConnection } from '../data/knowledge-engine';
import * as Haptics from 'expo-haptics';
import { logEvent } from '../data/logger';
import { isSectionValid, parseInlineMarkdown, splitMarkdownBlocks, parseMarkdownBlock } from '../lib/markdown-utils';
import { getDisplayTitle } from '../lib/display-utils';
import { toggleBookmark, isBookmarked } from '../data/bookmarks';
import { getQueuedArticleIds, removeFromQueue } from '../data/queue';
import RelatedArticles from '../components/RelatedArticles';
import { colors, fonts, type, spacing, layout } from '../design/tokens';
import {
  computeParagraphDimming, classifyArticleClaims,
  markArticleEncountered, markArticleReadUpTo, getArticleParagraphCount,
  isKnowledgeReady, getArticleNovelty
} from '../data/knowledge-engine';

const SCROLL_POSITION_SAVE_INTERVAL_MS = 2000;

// --- Types ---

type IngestStatus = 'processing' | 'queued' | 'failed';
interface IngestState {
  status: IngestStatus;
  ingestId: string;
  articleId: string;
}

type ReadingMode = 'full' | 'guided' | 'new_only';

interface ParagraphDimming {
  paragraph_index: number;
  opacity: number;
  novelty: 'novel' | 'mostly_novel' | 'mixed' | 'mostly_familiar' | 'familiar' | 'neutral';
  claim_counts: { new: number; extends: number; known: number };
}

interface ClaimClassification {
  claim_id: string;
  text: string;
  classification: 'NEW' | 'KNOWN' | 'EXTENDS';
  similarity_score: number;
  source_paragraphs: number[];
  claim_type: string;
}

interface ArticleNovelty {
  article_id: string;
  total_claims: number;
  new_claims: number;
  extends_claims: number;
  known_claims: number;
  novelty_ratio: number;
  curiosity_score: number;
}

// --- Paragraph to block mapping ---

function buildParagraphToBlockMap(content: string): Map<number, number[]> {
  const paragraphs = content.split('\n\n').map(p => p.trim()).filter(Boolean);
  const blocks = splitMarkdownBlocks(content);

  const map = new Map<number, number[]>();
  for (let pi = 0; pi < paragraphs.length; pi++) {
    const paraText = paragraphs[pi].toLowerCase();
    const blockIndices: number[] = [];
    for (let bi = 0; bi < blocks.length; bi++) {
      if (blocks[bi].toLowerCase().includes(paraText.slice(0, 50)) ||
          paraText.includes(blocks[bi].toLowerCase().slice(0, 50))) {
        blockIndices.push(bi);
      }
    }
    if (blockIndices.length > 0) map.set(pi, blockIndices);
  }
  return map;
}

// --- Post-Read Interest Card (Hierarchical) ---

interface TopicGroup {
  broad: string;
  specifics: Array<{ specific: string; entities: string[] }>;
}

function groupTopicsByBroad(topics: InterestTopic[]): TopicGroup[] {
  const map = new Map<string, Map<string, string[]>>();
  for (const t of topics) {
    if (!map.has(t.broad)) map.set(t.broad, new Map());
    const specificMap = map.get(t.broad)!;
    if (!specificMap.has(t.specific)) specificMap.set(t.specific, []);
    if (t.entity) {
      const entities = specificMap.get(t.specific)!;
      if (!entities.includes(t.entity)) entities.push(t.entity);
    }
  }
  return Array.from(map.entries()).map(([broad, specificMap]) => ({
    broad,
    specifics: Array.from(specificMap.entries()).map(([specific, entities]) => ({ specific, entities })),
  }));
}

function formatTopicLabel(slug: string): string {
  return slug.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function TopicLevelRow({ label, level, indent, onSignal }: {
  label: string;
  level: 'broad' | 'specific' | 'entity';
  indent: number;
  onSignal: (positive: boolean) => void;
}) {
  return (
    <View style={[interestStyles.chipRow, { paddingLeft: indent }]}>
      <Pressable
        style={interestStyles.chipMinus}
        onPress={() => onSignal(false)}
        hitSlop={8}
      >
        <Text style={interestStyles.chipButtonText}>−</Text>
      </Pressable>
      <View style={interestStyles.chipLabel}>
        {indent > 0 && <Text style={interestStyles.treeLine}>└ </Text>}
        <Text style={[
          interestStyles.chipText,
          level === 'entity' && interestStyles.chipTextEntity,
        ]} numberOfLines={1}>
          {level === 'entity' ? label : formatTopicLabel(label)}
        </Text>
        <Text style={interestStyles.levelBadge}>
          {level === 'broad' ? 'broad' : level === 'specific' ? 'topic' : 'entity'}
        </Text>
      </View>
      <Pressable
        style={interestStyles.chipPlus}
        onPress={() => onSignal(true)}
        hitSlop={8}
      >
        <Text style={interestStyles.chipButtonText}>+</Text>
      </Pressable>
    </View>
  );
}

function PostReadInterestCard({ topics, onLevelSignal, onClose }: {
  topics: InterestTopic[];
  onLevelSignal: (topicKey: string, level: 'broad' | 'specific' | 'entity', positive: boolean, parent?: string) => void;
  onClose: () => void;
}) {
  const groups = useMemo(() => groupTopicsByBroad(topics), [topics]);
  const uniqueBroadCount = groups.length;
  const [expanded, setExpanded] = useState(uniqueBroadCount <= 2);

  if (!expanded) {
    // Collapsed: show leaf-level chips only (entity if present, else specific)
    const leafTopics = topics.reduce<Array<{ key: string; label: string; level: 'specific' | 'entity'; parent: string }>>((acc, t) => {
      if (t.entity && !acc.some(a => a.key === t.entity!.toLowerCase().replace(/\s+/g, '-'))) {
        acc.push({ key: t.entity.toLowerCase().replace(/\s+/g, '-'), label: t.entity, level: 'entity', parent: t.specific });
      } else if (!t.entity && !acc.some(a => a.key === t.specific)) {
        acc.push({ key: t.specific, label: formatTopicLabel(t.specific), level: 'specific', parent: t.broad });
      }
      return acc;
    }, []);

    return (
      <View style={styles.interestCardOverlay}>
        <View style={styles.interestCard}>
          <Text style={styles.interestCardTitle}>{'✦ TOPICS IN THIS ARTICLE'}</Text>
          <Text style={styles.interestCardSubtitle}>Tap + or − to shape your feed</Text>
          <View style={interestStyles.chips}>
            {leafTopics.slice(0, 4).map((t) => (
              <TopicLevelRow
                key={t.key}
                label={t.label}
                level={t.level}
                indent={0}
                onSignal={(positive) => onLevelSignal(t.key, t.level, positive, t.parent)}
              />
            ))}
          </View>
          <Pressable
            style={interestStyles.expandButton}
            onPress={() => {
              setExpanded(true);
              logEvent('interest_card_expand');
            }}
          >
            <Text style={interestStyles.expandText}>Show topic hierarchy ▾</Text>
          </Pressable>
          <Pressable style={styles.interestCloseButton} onPress={onClose}>
            <Text style={styles.interestCloseText}>Close</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  // Expanded: show full hierarchy
  return (
    <View style={styles.interestCardOverlay}>
      <View style={styles.interestCard}>
        <Text style={styles.interestCardTitle}>{'✦ TOPICS IN THIS ARTICLE'}</Text>
        <Text style={styles.interestCardSubtitle}>Signal interest at any level of specificity</Text>
        <View style={interestStyles.chips}>
          {groups.map((group) => (
            <View key={group.broad}>
              <TopicLevelRow
                label={group.broad}
                level="broad"
                indent={0}
                onSignal={(positive) => onLevelSignal(group.broad, 'broad', positive)}
              />
              {group.specifics.map((sp) => (
                <View key={sp.specific}>
                  <TopicLevelRow
                    label={sp.specific}
                    level="specific"
                    indent={20}
                    onSignal={(positive) => onLevelSignal(sp.specific, 'specific', positive, group.broad)}
                  />
                  {sp.entities.map((ent) => {
                    const entityKey = ent.toLowerCase().replace(/\s+/g, '-');
                    return (
                      <TopicLevelRow
                        key={entityKey}
                        label={ent}
                        level="entity"
                        indent={40}
                        onSignal={(positive) => onLevelSignal(entityKey, 'entity', positive, sp.specific)}
                      />
                    );
                  })}
                </View>
              ))}
            </View>
          ))}
        </View>
        {uniqueBroadCount > 2 && (
          <Pressable
            style={interestStyles.expandButton}
            onPress={() => {
              setExpanded(false);
              logEvent('interest_card_collapse');
            }}
          >
            <Text style={interestStyles.expandText}>Collapse ▴</Text>
          </Pressable>
        )}
        <Pressable style={styles.interestCloseButton} onPress={onClose}>
          <Text style={styles.interestCloseText}>Close</Text>
        </Pressable>
      </View>
    </View>
  );
}

function stripLeadingTitle(text: string, title: string): string {
  if (!text) return '';
  const lines = text.split('\n');
  const firstLine = lines[0].replace(/^#+\s*/, '').trim();
  if (firstLine === title.trim()) {
    return lines.slice(1).join('\n').trimStart();
  }
  return text;
}

// --- Reading Mode Toggle ---

function ReadingModeToggle({ mode, onModeChange }: {
  mode: ReadingMode;
  onModeChange: (mode: ReadingMode) => void;
}) {
  const modes: { key: ReadingMode; label: string }[] = [
    { key: 'full', label: 'FULL' },
    { key: 'guided', label: 'GUIDED' },
    { key: 'new_only', label: 'NEW ONLY' },
  ];

  return (
    <View style={styles.readingModeContainer}>
      <View style={styles.readingModeTrack}>
        {modes.map(({ key, label }) => (
          <Pressable
            key={key}
            style={[
              styles.readingModeButton,
              mode === key && styles.readingModeButtonActive,
            ]}
            onPress={() => onModeChange(key)}
          >
            <Text style={[
              styles.readingModeLabel,
              mode === key && styles.readingModeLabelActive,
            ]}>
              {label}
            </Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

// --- Inline markdown rendering ---

interface LinkHandler {
  ingestStates: Record<string, IngestState>;
  onIngest: (url: string) => void;
}

function isIngestableUrl(url: string): boolean {
  if (!url.startsWith('http://') && !url.startsWith('https://')) return false;
  // Skip obvious non-article URLs
  const lower = url.toLowerCase();
  if (/\.(png|jpg|jpeg|gif|svg|webp|pdf|mp3|mp4|zip|tar|gz)(\?|$)/.test(lower)) return false;
  return true;
}

function renderInlineMarkdown(
  text: string,
  linkHandler?: LinkHandler,
): (string | React.ReactElement)[] {
  const segments = parseInlineMarkdown(text);
  return segments.map((seg, i) => {
    switch (seg.type) {
      case 'link': {
        const canIngest = linkHandler && isIngestableUrl(seg.url);
        const ingestState = canIngest ? linkHandler.ingestStates[seg.url] : undefined;

        return (
          <Text key={`link-${i}`}>
            <Text
              style={styles.markdownLink}
              onPress={() => {
                if (canIngest && !ingestState) {
                  logEvent('reader_link_ingest', { url: seg.url, link_text: seg.text?.slice(0, 80) });
                  linkHandler.onIngest(seg.url);
                } else {
                  logEvent('reader_link_tap', { url: seg.url, link_text: seg.text?.slice(0, 80) });
                  Linking.openURL(seg.url);
                }
              }}
              onLongPress={() => {
                logEvent('reader_link_open', { url: seg.url });
                Linking.openURL(seg.url);
              }}
              {...(Platform.OS === 'web' ? { accessibilityRole: 'link', href: seg.url, hrefAttrs: { target: '_blank', rel: 'noopener noreferrer' } } as any : {})}
            >
              {seg.text}
            </Text>
            {ingestState?.status === 'processing' && (
              <Text style={styles.ingestBadgeProcessing}>{' processing…'}</Text>
            )}
            {ingestState?.status === 'queued' && (
              <Text style={styles.ingestBadgeQueued}>{' queued ✓'}</Text>
            )}
            {ingestState?.status === 'failed' && (
              <Text style={styles.ingestBadgeFailed}>{' failed'}</Text>
            )}
          </Text>
        );
      }
      case 'bold':
        return <Text key={`bold-${i}`} style={styles.markdownBold}>{seg.text}</Text>;
      case 'italic':
        return <Text key={`italic-${i}`} style={styles.markdownItalic}>{seg.text}</Text>;
      case 'code':
        return <Text key={`code-${i}`} style={styles.markdownInlineCode}>{seg.text}</Text>;
      default:
        return seg.text;
    }
  });
}

// --- Collapsed familiar blocks bar ---

function CollapsedBar({ blockCount, onExpand }: {
  blockCount: number;
  onExpand: () => void;
}) {
  return (
    <Pressable style={styles.collapsedBar} onPress={onExpand}>
      <View style={styles.collapsedBarContent}>
        <View style={styles.collapsedBarDot} />
        <Text style={styles.collapsedBarText}>
          {blockCount} familiar {blockCount === 1 ? 'section' : 'sections'}
        </Text>
      </View>
      <Text style={styles.collapsedBarExpand}>{'▼'}</Text>
    </Pressable>
  );
}

// --- Entity Highlight Text ---

function EntityHighlightText({
  children,
  entities,
  onEntityLongPress,
}: {
  children: (string | React.ReactElement)[];
  entities: ArticleEntity[];
  onEntityLongPress: (entity: ArticleEntity) => void;
}) {
  if (!entities || entities.length === 0) return <>{children}</>;

  // Collect all mention strings, sorted longest-first to avoid partial matches
  const mentionMap = new Map<string, ArticleEntity>();
  for (const ent of entities) {
    for (const m of ent.mentions) {
      mentionMap.set(m.toLowerCase(), ent);
    }
  }
  const mentionKeys = Array.from(mentionMap.keys()).sort((a, b) => b.length - a.length);
  if (mentionKeys.length === 0) return <>{children}</>;

  // Build a case-insensitive regex that matches any mention
  const escaped = mentionKeys.map(k => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const pattern = new RegExp(`(${escaped.join('|')})`, 'gi');

  return (
    <>
      {children.map((child, ci) => {
        if (typeof child !== 'string') return child;
        const parts = child.split(pattern);
        if (parts.length === 1) return child;
        return parts.map((part, pi) => {
          const entity = mentionMap.get(part.toLowerCase());
          if (entity) {
            return (
              <Text
                key={`ent-${ci}-${pi}`}
                style={entityStyles.entityMention}
                onLongPress={() => {
                  Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
                  onEntityLongPress(entity);
                }}
              >
                {part}
              </Text>
            );
          }
          return part;
        });
      })}
    </>
  );
}

// --- Entity Popup ---

function EntityPopup({
  entity,
  articleTitle,
  onResearch,
  onDismiss,
}: {
  entity: ArticleEntity;
  articleTitle: string;
  onResearch: () => void;
  onDismiss: () => void;
}) {
  return (
    <View style={entityStyles.popupContainer}>
      <Text style={entityStyles.popupType}>{entity.type.toUpperCase()}</Text>
      <Text style={entityStyles.popupName}>{entity.name}</Text>
      <Text style={entityStyles.popupSynthesis}>{entity.synthesis}</Text>
      <View style={entityStyles.popupActions}>
        <Pressable
          style={entityStyles.popupAction}
          onPress={() => {
            logEvent('entity_research_tap', { entity: entity.name, article_title: articleTitle });
            onResearch();
          }}
        >
          <Text style={entityStyles.popupActionResearch}>{'Research more \u2197'}</Text>
        </Pressable>
        <Pressable style={entityStyles.popupAction} onPress={onDismiss}>
          <Text style={entityStyles.popupActionDismiss}>Dismiss</Text>
        </Pressable>
      </View>
    </View>
  );
}

// --- Follow-up Research Prompts ---

function FollowUpSection({
  questions,
  articleTitle,
  articleId,
  articleSummary,
}: {
  questions: FollowUpQuestion[];
  articleTitle: string;
  articleId: string;
  articleSummary: string;
}) {
  const [launchedIndices, setLaunchedIndices] = useState<Set<number>>(new Set());

  if (!questions || questions.length === 0) return null;

  const handleResearch = async (q: FollowUpQuestion, index: number) => {
    logEvent('research_prompt_tap', { article_id: articleId, question: q.question });
    try {
      await spawnTopicResearch(
        q.question,
        `From article: ${articleTitle}\nConnects to: ${q.connects_to}\nSummary: ${articleSummary}`,
        [articleTitle],
      );
      setLaunchedIndices(prev => new Set(prev).add(index));
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      logEvent('research_prompt_launched', { article_id: articleId, question: q.question, connects_to: q.connects_to });
    } catch (e) {
      logEvent('research_prompt_error', { article_id: articleId, error: String(e) });
    }
  };

  return (
    <View style={followUpStyles.container}>
      <Text style={followUpStyles.sectionTitle}>{'\u2726 FURTHER INQUIRY'}</Text>
      {questions.map((q, i) => (
        <View key={i} style={followUpStyles.questionCard}>
          <Text style={followUpStyles.questionText}>{q.question}</Text>
          <Text style={followUpStyles.connectsTo}>{q.connects_to}</Text>
          {launchedIndices.has(i) ? (
            <Text style={followUpStyles.launchedText}>{'\u2713 Research launched'}</Text>
          ) : (
            <Pressable
              style={followUpStyles.researchButton}
              onPress={() => handleResearch(q, i)}
            >
              <Text style={followUpStyles.researchButtonText}>{'Research this \u2197'}</Text>
            </Pressable>
          )}
        </View>
      ))}
    </View>
  );
}

// --- Connected Reading Section ---

function ConnectedReadingSection({
  connections,
  articleId,
}: {
  connections: CrossArticleConnection[];
  articleId: string;
}) {
  const [queuedIds, setQueuedIds] = useState<Set<string>>(new Set());
  const router = useRouter();
  const allArticles = getArticles();

  if (!connections || connections.length === 0) return null;

  const handleQueue = async (connArticleId: string) => {
    await addToQueueFront(connArticleId);
    setQueuedIds(prev => new Set(prev).add(connArticleId));
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    logEvent('cross_article_queue', {
      source_article_id: articleId,
      target_article_id: connArticleId,
    });
  };

  const handleNavigate = (connArticleId: string) => {
    logEvent('cross_article_navigate', {
      source_article_id: articleId,
      target_article_id: connArticleId,
    });
    router.push({ pathname: '/reader', params: { id: connArticleId } });
  };

  return (
    <View style={connectedStyles.container}>
      <Text style={connectedStyles.sectionTitle}>{'\u2726 CONNECTED READING'}</Text>
      {connections.map((conn) => {
        const targetArticle = allArticles.find(a => a.id === conn.articleId);
        if (!targetArticle) return null;
        const title = getDisplayTitle(targetArticle);
        const readingState = getReadingState(conn.articleId);
        const isRead = readingState.status === 'read';
        const isAlreadyQueued = queuedIds.has(conn.articleId);

        return (
          <Pressable
            key={conn.articleId}
            style={[connectedStyles.card, isRead && connectedStyles.cardRead]}
            onLongPress={() => handleNavigate(conn.articleId)}
          >
            <Text
              style={[connectedStyles.cardTitle, isRead && connectedStyles.cardTitleRead]}
              numberOfLines={2}
            >
              {title}
            </Text>
            <View style={connectedStyles.cardMeta}>
              <Text style={connectedStyles.cardClaimCount}>
                {conn.sharedClaimCount} shared {conn.sharedClaimCount === 1 ? 'claim' : 'claims'}
              </Text>
              {isRead ? (
                <Text style={connectedStyles.cardReadLabel}>
                  {'read ' + formatTimeAgo(readingState.completed_at || readingState.last_read_at)}
                </Text>
              ) : isAlreadyQueued ? (
                <Text style={connectedStyles.cardQueuedLabel}>{'✓ Queued'}</Text>
              ) : (
                <Pressable
                  style={connectedStyles.queueButton}
                  onPress={() => handleQueue(conn.articleId)}
                  hitSlop={8}
                >
                  <Text style={connectedStyles.queueButtonText}>+ Queue</Text>
                </Pressable>
              )}
            </View>
          </Pressable>
        );
      })}
    </View>
  );
}

function formatTimeAgo(timestamp: number): string {
  if (!timestamp) return '';
  const days = Math.floor((Date.now() - timestamp) / (1000 * 60 * 60 * 24));
  if (days === 0) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 7) return `${days} days ago`;
  if (days < 30) return `${Math.floor(days / 7)} weeks ago`;
  return `${Math.floor(days / 30)} months ago`;
}

// --- Inline Cross-Article Annotation ---

function InlineCrossArticleAnnotation({
  articleId: connArticleId,
  sourceArticleId,
}: {
  articleId: string;
  sourceArticleId: string;
}) {
  const [queued, setQueued] = useState(false);
  const router = useRouter();
  const allArticles = getArticles();
  const targetArticle = allArticles.find(a => a.id === connArticleId);

  if (!targetArticle) return null;

  const title = getDisplayTitle(targetArticle);
  const readingState = getReadingState(connArticleId);
  const isRead = readingState.status === 'read';

  return (
    <View style={connectedStyles.inlineAnnotation}>
      <Pressable
        onPress={async () => {
          if (!isRead && !queued) {
            await addToQueueFront(connArticleId);
            setQueued(true);
            Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
            logEvent('inline_cross_article_queue', {
              source_article_id: sourceArticleId,
              target_article_id: connArticleId,
            });
          }
        }}
        onLongPress={() => {
          logEvent('inline_cross_article_navigate', {
            source_article_id: sourceArticleId,
            target_article_id: connArticleId,
          });
          router.push({ pathname: '/reader', params: { id: connArticleId } });
        }}
      >
        <Text style={connectedStyles.inlineAnnotationText}>
          <Text style={connectedStyles.inlineAnnotationPrefix}>Also in: </Text>
          <Text style={[
            connectedStyles.inlineAnnotationTitle,
            isRead && connectedStyles.inlineAnnotationTitleRead,
          ]}>
            {title}
          </Text>
          {isRead ? (
            <Text style={connectedStyles.inlineAnnotationRead}>{' (read)'}</Text>
          ) : queued ? (
            <Text style={connectedStyles.inlineAnnotationQueued}>{' ✓ queued'}</Text>
          ) : (
            <Text style={connectedStyles.inlineAnnotationQueue}>{' · tap to queue'}</Text>
          )}
        </Text>
      </Pressable>
    </View>
  );
}

// --- Markdown renderer ---

function MarkdownText({ content, highlightedBlocks, onBlockLongPress, blockDimming, readingMode = 'full', entities, onEntityLongPress, linkHandler, paragraphConnections, sourceArticleId }: {
  content: string;
  highlightedBlocks?: Set<number>;
  onBlockLongPress?: (blockIndex: number, text: string) => void;
  blockDimming?: Map<number, { opacity: number; novelty: string }> | null;
  readingMode?: ReadingMode;
  entities?: ArticleEntity[];
  onEntityLongPress?: (entity: ArticleEntity) => void;
  linkHandler?: LinkHandler;
  paragraphConnections?: Map<number, Array<{ articleId: string; claimText: string }>> | null;
  sourceArticleId?: string;
}) {
  const [expandedCollapsedRanges, setExpandedCollapsedRanges] = useState(new Set<number>());

  if (!content) return null;
  const blocks = splitMarkdownBlocks(content);

  // Build collapsed ranges for new_only mode
  type RenderItem =
    | { type: 'block'; index: number }
    | { type: 'collapsed'; startIndex: number; count: number; blockIndices: number[] };

  const renderBlocks: RenderItem[] = [];

  if (readingMode === 'new_only' && blockDimming) {
    let i = 0;
    while (i < blocks.length) {
      const dimming = blockDimming.get(i);
      const isFamiliar = dimming && dimming.opacity < 0.7;

      if (isFamiliar) {
        const startIndex = i;
        const familiarIndices: number[] = [];
        while (i < blocks.length) {
          const d = blockDimming.get(i);
          if (d && d.opacity < 0.7) {
            familiarIndices.push(i);
            i++;
          } else {
            break;
          }
        }
        renderBlocks.push({ type: 'collapsed', startIndex, count: familiarIndices.length, blockIndices: familiarIndices });
      } else {
        renderBlocks.push({ type: 'block', index: i });
        i++;
      }
    }
  } else {
    for (let i = 0; i < blocks.length; i++) {
      renderBlocks.push({ type: 'block', index: i });
    }
  }

  function renderSingleBlock(raw: string, i: number, opacityOverride?: number) {
    const block = parseMarkdownBlock(raw);
    const isHighlighted = highlightedBlocks?.has(i);
    const dimming = blockDimming?.get(i);

    // In guided mode, apply opacity from the dimming map
    const blockOpacity = readingMode === 'guided' && dimming ? dimming.opacity : opacityOverride ?? 1;
    const opacityStyle = blockOpacity < 1 ? { opacity: blockOpacity } : undefined;

    // Novel marker: green left border on novel paragraphs in guided/new_only modes
    const isNovel = dimming && (dimming.novelty === 'novel' || dimming.novelty === 'mostly_novel') && readingMode !== 'full';
    const novelMarkerStyle = isNovel ? { borderLeftWidth: 2, borderLeftColor: colors.claimNew, paddingLeft: 8 } as const : undefined;

    switch (block.type) {
      case 'heading':
        return (
          <View key={i} style={[opacityStyle, novelMarkerStyle]}>
            <Text style={[
              styles.markdownHeading,
              block.level === 1 && { fontSize: 22 },
              block.level === 2 && { fontSize: 19 },
              (block.level ?? 3) >= 3 && { fontSize: 17 },
            ]}>
              {renderInlineMarkdown(block.content, linkHandler)}
            </Text>
          </View>
        );

      case 'hr':
        return <View key={i} style={[styles.markdownHr, opacityStyle, novelMarkerStyle]} />;

      case 'ul':
        return (
          <Pressable
            key={i}
            style={[styles.markdownList, isHighlighted && styles.paragraphHighlight, opacityStyle, novelMarkerStyle]}
            onLongPress={onBlockLongPress ? () => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium); onBlockLongPress(i, raw); } : undefined}
          >
            {(block.items || []).map((item, j) => (
              <View key={j} style={styles.markdownListItem}>
                <Text style={styles.markdownBullet}>{'·'}</Text>
                <Text style={styles.markdownText}>{renderInlineMarkdown(item, linkHandler)}</Text>
              </View>
            ))}
          </Pressable>
        );

      case 'ol':
        return (
          <Pressable
            key={i}
            style={[styles.markdownList, isHighlighted && styles.paragraphHighlight, opacityStyle, novelMarkerStyle]}
            onLongPress={onBlockLongPress ? () => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium); onBlockLongPress(i, raw); } : undefined}
          >
            {(block.items || []).map((item, j) => (
              <View key={j} style={styles.markdownListItem}>
                <Text style={styles.markdownOrderedBullet}>{j + 1}.</Text>
                <Text style={styles.markdownText}>{renderInlineMarkdown(item, linkHandler)}</Text>
              </View>
            ))}
          </Pressable>
        );

      case 'code':
        return (
          <View key={i} style={[styles.codeBlock, isHighlighted && styles.paragraphHighlight, opacityStyle, novelMarkerStyle]}>
            <Text style={styles.codeText}>{block.content}</Text>
          </View>
        );

      case 'blockquote':
        return (
          <Pressable
            key={i}
            onLongPress={onBlockLongPress ? () => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium); onBlockLongPress(i, raw); } : undefined}
            style={[styles.markdownBlockquote, isHighlighted && styles.paragraphHighlight, opacityStyle, novelMarkerStyle]}
          >
            <Text style={styles.markdownBlockquoteText}>{renderInlineMarkdown(block.content, linkHandler)}</Text>
          </Pressable>
        );

      case 'table':
        return (
          <View key={i} style={[styles.tableContainer, opacityStyle, novelMarkerStyle]}>
            {block.headers && block.headers.length > 0 && (
              <View style={styles.tableRow}>
                {block.headers.map((h, hi) => (
                  <View key={hi} style={[styles.tableCell, styles.tableHeaderCell]}>
                    <Text style={styles.tableHeaderText}>{renderInlineMarkdown(h, linkHandler)}</Text>
                  </View>
                ))}
              </View>
            )}
            {(block.rows || []).map((row, ri) => (
              <View key={ri} style={[styles.tableRow, ri % 2 === 1 && styles.tableRowAlt]}>
                {row.map((cell, ci) => (
                  <View key={ci} style={styles.tableCell}>
                    <Text style={styles.tableCellText}>{renderInlineMarkdown(cell, linkHandler)}</Text>
                  </View>
                ))}
              </View>
            ))}
          </View>
        );

      default: {
        const inlineContent = renderInlineMarkdown(block.content, linkHandler);
        const blockConnections = paragraphConnections?.get(i);
        // Deduplicate connections per article (show max 1 annotation per article per paragraph)
        const uniqueConnections = blockConnections
          ? Array.from(new Map(blockConnections.map(c => [c.articleId, c])).values()).slice(0, 2)
          : [];
        return (
          <View key={i}>
            <Pressable
              onLongPress={onBlockLongPress ? () => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium); onBlockLongPress(i, block.content); } : undefined}
              style={[isHighlighted ? styles.paragraphHighlight : undefined, opacityStyle, novelMarkerStyle]}
            >
              <Text style={styles.markdownText}>
                {entities && entities.length > 0 && onEntityLongPress ? (
                  <EntityHighlightText entities={entities} onEntityLongPress={onEntityLongPress}>
                    {inlineContent}
                  </EntityHighlightText>
                ) : inlineContent}
              </Text>
            </Pressable>
            {uniqueConnections.map(conn => (
              <InlineCrossArticleAnnotation
                key={conn.articleId}
                articleId={conn.articleId}
                sourceArticleId={sourceArticleId || ''}
              />
            ))}
          </View>
        );
      }
    }
  }

  return (
    <View>
      {renderBlocks.map((item, idx) => {
        if (item.type === 'collapsed') {
          const isExpanded = expandedCollapsedRanges.has(item.startIndex);
          if (isExpanded) {
            return (
              <View key={`collapsed-${item.startIndex}`}>
                {item.blockIndices.map((bi) => renderSingleBlock(blocks[bi], bi, colors.claimKnownOpacity))}
                <Pressable
                  style={styles.collapseBar}
                  onPress={() => {
                    setExpandedCollapsedRanges((prev: Set<number>) => {
                      const next = new Set(prev);
                      next.delete(item.startIndex);
                      return next;
                    });
                    logEvent('collapsed_bar_collapse', { block_count: item.count });
                  }}
                >
                  <Text style={styles.collapsedBarText}>{'▲ Collapse'}</Text>
                </Pressable>
              </View>
            );
          }
          return (
            <CollapsedBar
              key={`collapsed-${item.startIndex}`}
              blockCount={item.count}
              onExpand={() => {
                setExpandedCollapsedRanges((prev: Set<number>) => new Set(prev).add(item.startIndex));
                logEvent('collapsed_bar_expand', { block_count: item.count });
              }}
            />
          );
        }
        return renderSingleBlock(blocks[item.index], item.index);
      })}
    </View>
  );
}

// --- AI Chat context builder ---

function buildAIChatContext(article: Article): string {
  const parts = [
    `Title: ${article.title}`,
    `Author: ${article.author}`,
    `Source: ${article.hostname} (${article.source_url})`,
    `Type: ${article.content_type}`,
    `Summary: ${article.one_line_summary}`,
    '',
    `Full summary: ${article.full_summary}`,
  ];
  if (article.key_claims?.length) {
    parts.push('', 'Key claims:', ...article.key_claims.map(c => `- ${c}`));
  }
  if (article.interest_topics?.length) {
    parts.push('', 'Topics:', ...article.interest_topics.map(t => `- ${t.broad}: ${t.specific}`));
  }
  // Include article text (truncated to ~4000 chars to stay within context limits)
  if (article.content_markdown) {
    parts.push('', '--- Article text (truncated) ---', article.content_markdown.slice(0, 4000));
  }
  return parts.join('\n');
}

// --- Main Reader Screen ---

export default function ReaderScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const article = getArticleById(id || '');

  const scrollRef = useRef<ScrollView>(null);
  const enterTime = useRef(Date.now());
  const lastScrollY = useRef(0);
  const lastPositionSaveTime = useRef(0);
  const scrollMilestone = useRef(0);
  const [highlightedBlocks, setHighlightedBlocks] = useState<Set<number>>(new Set());
  const [showInterestCard, setShowInterestCard] = useState(false);
  const [readingMode, setReadingMode] = useState<ReadingMode>('full');
  const [scrollProgress, setScrollProgress] = useState(0);
  const [bookmarked, setBookmarked] = useState(() => article ? isBookmarked(article.id) : false);
  const [showMenu, setShowMenu] = useState(false);
  const [showAIChat, setShowAIChat] = useState(false);
  const [showVoiceFeedback, setShowVoiceFeedback] = useState(false);
  const [activeEntity, setActiveEntity] = useState<ArticleEntity | null>(null);

  // Cross-article connections
  const crossArticleConnections = useMemo(() => {
    if (!article) return [];
    return getCrossArticleConnections(article.id);
  }, [article]);

  const paragraphConnections = useMemo(() => {
    if (!article) return null;
    return getParagraphConnections(article.id);
  }, [article]);

  const contentHeight = useRef(0);
  const viewportHeight = useRef(0);
  const maxScrollY = useRef(0);

  // Link ingestion state
  const [ingestStates, setIngestStates] = useState<Record<string, IngestState>>({});
  const pollTimers = useRef<Record<string, ReturnType<typeof setInterval>>>({});

  const handleLinkIngest = useCallback(async (url: string) => {
    if (ingestStates[url]) return; // Already ingesting
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);

    try {
      const result = await ingestUrl(url, 'reader_link');
      setIngestStates(prev => ({
        ...prev,
        [url]: { status: 'processing', ingestId: result.ingest_id, articleId: result.article_id },
      }));

      // Poll for completion
      const timer = setInterval(async () => {
        try {
          const status = await getIngestStatus(result.ingest_id);
          if (status.status === 'completed') {
            clearInterval(timer);
            delete pollTimers.current[url];
            setIngestStates(prev => ({
              ...prev,
              [url]: { ...prev[url], status: 'queued' },
            }));
            await addToQueue(result.article_id);
            Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
          } else if (status.status === 'failed') {
            clearInterval(timer);
            delete pollTimers.current[url];
            setIngestStates(prev => ({
              ...prev,
              [url]: { ...prev[url], status: 'failed' },
            }));
          }
        } catch {
          // Poll errors are transient, keep trying
        }
      }, 5000);
      pollTimers.current[url] = timer;
    } catch {
      setIngestStates(prev => ({
        ...prev,
        [url]: { status: 'failed', ingestId: '', articleId: '' },
      }));
    }
  }, [ingestStates]);

  // Clean up polling timers on unmount
  useEffect(() => {
    return () => {
      Object.values(pollTimers.current).forEach(clearInterval);
    };
  }, []);

  const linkHandler = useMemo<LinkHandler>(() => ({
    ingestStates,
    onIngest: handleLinkIngest,
  }), [ingestStates, handleLinkIngest]);

  // Next queued article for "Up next" footer
  const nextQueuedArticle = useMemo(() => {
    const queuedIds = getQueuedArticleIds();
    const nextId = queuedIds.find(qId => qId !== id);
    if (!nextId) return null;
    return getArticleById(nextId) || null;
  }, [id]);

  // Knowledge engine data
  const paragraphDimming = useMemo(() => {
    if (!article || !isKnowledgeReady()) return null;
    return computeParagraphDimming(article.id) as ParagraphDimming[] | null;
  }, [article?.id]);

  const claimClassifications = useMemo(() => {
    if (!article || !isKnowledgeReady()) return null;
    return classifyArticleClaims(article.id) as ClaimClassification[] | null;
  }, [article?.id]);

  const articleNovelty = useMemo(() => {
    if (!article || !isKnowledgeReady()) return null;
    return getArticleNovelty(article.id) as ArticleNovelty | null;
  }, [article?.id]);

  // Build full article content — prefer sections if available
  const fullContent = useMemo(() => {
    if (!article) return '';
    return article.sections && article.sections.length > 0
      ? article.sections
          .filter(isSectionValid)
          .map(s => `## ${s.heading}\n\n${s.content}`)
          .join('\n\n')
      : stripLeadingTitle(article.content_markdown, article.title);
  }, [article?.id]);

  // Map paragraph-level dimming to block-level dimming
  const blockDimming = useMemo(() => {
    if (!paragraphDimming || !fullContent) return null;
    const paraToBlock = buildParagraphToBlockMap(fullContent);
    const blockMap = new Map<number, { opacity: number; novelty: string }>();
    for (const pd of paragraphDimming) {
      const blockIndices = paraToBlock.get(pd.paragraph_index) || [];
      for (const bi of blockIndices) {
        blockMap.set(bi, { opacity: pd.opacity, novelty: pd.novelty });
      }
    }
    return blockMap;
  }, [paragraphDimming, fullContent]);

  // Initialize reading state
  useEffect(() => {
    if (!article) return;
    const state = getReadingState(article.id);
    if (state.status === 'unread') {
      updateReadingState(article.id, { status: 'reading', started_at: Date.now(), last_read_at: Date.now() });
    } else {
      updateReadingState(article.id, { status: 'reading', last_read_at: Date.now() });
    }
    logEvent('reader_open', { article_id: article.id, title: article.title });

    // Restore scroll position
    const savedY = state.scroll_position_y || 0;
    if (savedY > 0) {
      setTimeout(() => {
        scrollRef.current?.scrollTo({ y: savedY, animated: false });
      }, 300);
    }

    return () => {
      const elapsed = Date.now() - enterTime.current;
      const currentState = getReadingState(article.id);
      updateReadingState(article.id, {
        time_spent_ms: (currentState.time_spent_ms || 0) + elapsed,
        last_read_at: Date.now(),
        scroll_position_y: lastScrollY.current,
      });

      // Mark claims as encountered based on how far the user actually scrolled
      if (isKnowledgeReady() && contentHeight.current > 0) {
        const totalParas = getArticleParagraphCount(article.id);
        if (totalParas > 0) {
          const readUpToY = maxScrollY.current + viewportHeight.current;
          const readFraction = Math.min(1, readUpToY / contentHeight.current);
          const maxPara = Math.floor(readFraction * totalParas);
          const engagement = elapsed > 60000 ? 'read' : 'skim';
          markArticleReadUpTo(article.id, maxPara, engagement);
        }
      }

      logEvent('reader_close', { article_id: article.id, time_spent_ms: elapsed });
    };
  }, []);

  // Load highlights
  useEffect(() => {
    if (!article) return;
    setHighlightedBlocks(getHighlightBlockIndices(article.id));
  }, [article?.id]);

  // Scroll handler — save position periodically + track progress
  const handleScroll = useCallback((event: NativeSyntheticEvent<NativeScrollEvent>) => {
    if (!article) return;
    const { contentOffset, contentSize, layoutMeasurement } = event.nativeEvent;
    const scrollY = contentOffset.y;
    const now = Date.now();

    if (now - lastPositionSaveTime.current >= SCROLL_POSITION_SAVE_INTERVAL_MS) {
      lastPositionSaveTime.current = now;
      updateReadingState(article.id, { scroll_position_y: Math.round(scrollY) });
    }

    lastScrollY.current = scrollY;
    if (scrollY > maxScrollY.current) maxScrollY.current = scrollY;
    contentHeight.current = contentSize.height;
    viewportHeight.current = layoutMeasurement.height;

    const maxScroll = contentSize.height - layoutMeasurement.height;
    if (maxScroll > 0) {
      const pct = Math.min(100, Math.max(0, (scrollY / maxScroll) * 100));
      setScrollProgress(pct);
      // Log scroll milestones (25%, 50%, 75%, 100%)
      const milestone = Math.floor(pct / 25) * 25;
      if (milestone > 0 && milestone > (scrollMilestone.current || 0)) {
        scrollMilestone.current = milestone;
        logEvent('reader_scroll_milestone', { article_id: article.id, pct: milestone });
      }
    }
  }, [article]);

  // Highlight handler
  const handleBlockLongPress = useCallback((blockIndex: number, text: string) => {
    if (!article) return;
    const indices = getHighlightBlockIndices(article.id);
    if (indices.has(blockIndex)) {
      removeHighlight(article.id, blockIndex);
      setHighlightedBlocks((prev: Set<number>) => {
        const next = new Set(prev);
        next.delete(blockIndex);
        return next;
      });
      logEvent('reader_highlight_remove', { article_id: article.id, block_index: blockIndex });
    } else {
      addHighlight({
        id: `hl_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
        article_id: article.id,
        block_index: blockIndex,
        text: text.slice(0, 500),
        highlighted_at: Date.now(),
        zone: 'full',
      });
      setHighlightedBlocks((prev: Set<number>) => new Set(prev).add(blockIndex));
      recordInterestSignal('highlight_paragraph', article.id);
      logEvent('reader_highlight_add', { article_id: article.id, block_index: blockIndex, text_preview: text.slice(0, 80) });
    }
  }, [article]);

  // Entity long-press handler
  const handleEntityLongPress = useCallback((entity: ArticleEntity) => {
    setActiveEntity(entity);
    logEvent('entity_popup_open', { article_id: article?.id, entity: entity.name, entity_type: entity.type });
  }, [article]);

  const handleEntityResearch = useCallback(async () => {
    if (!article || !activeEntity) return;
    try {
      await spawnTopicResearch(
        activeEntity.name,
        `Entity: ${activeEntity.name} (${activeEntity.type})\n${activeEntity.synthesis}\nFrom article: ${article.title}`,
        [article.title],
      );
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      logEvent('entity_research_launched', { article_id: article.id, entity: activeEntity.name });
    } catch (e) {
      logEvent('entity_research_error', { article_id: article.id, entity: activeEntity.name, error: String(e) });
    }
    setActiveEntity(null);
  }, [article, activeEntity]);

  // Done handler — user explicitly finished, so mark ALL claims
  const handleDone = useCallback(() => {
    if (!article) return;
    markArticleRead(article.id);
    markArticleEncountered(article.id, 'read');
    recordInterestSignal('tap_done', article.id);
    logEvent('reader_done', { article_id: article.id });

    // Show interest card if article has interest_topics
    const topics = article.interest_topics || [];
    if (topics.length > 0) {
      setShowInterestCard(true);
      logEvent('interest_card_shown', { article_id: article.id, topic_count: topics.length });
    } else {
      router.back();
    }
  }, [article, router]);

  // Up next handler — navigate to next queued article
  const handleUpNext = useCallback(async () => {
    if (!article || !nextQueuedArticle) return;
    markArticleRead(article.id);
    markArticleEncountered(article.id, 'read');
    recordInterestSignal('tap_done', article.id);
    await removeFromQueue(article.id);
    logEvent('reader_up_next', { from_article_id: article.id, to_article_id: nextQueuedArticle.id });
    router.replace({ pathname: '/reader', params: { id: nextQueuedArticle.id } });
  }, [article, nextQueuedArticle, router]);

  const handleLevelSignal = useCallback((topicKey: string, level: 'broad' | 'specific' | 'entity', positive: boolean, parent?: string) => {
    if (!article) return;
    const action = positive ? 'interest_chip_positive' : 'interest_chip_negative';
    recordTopicInterestSignalAtLevel(action, topicKey, level, parent);
    logEvent('interest_chip_tap', { article_id: article.id, topic: topicKey, level, positive });
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
  }, [article]);

  const handleInterestClose = useCallback(() => {
    logEvent('interest_card_close', { article_id: article?.id });
    setShowInterestCard(false);
    router.back();
  }, [article, router]);

  if (!article) {
    return (
      <View style={styles.container}>
        <Text style={styles.errorText}>Article not found</Text>
        <Pressable onPress={() => router.back()}>
          <Text style={styles.backLink}>Back to feed</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Top bar */}
      <View style={styles.topBar}>
        <Pressable onPress={() => {
          logEvent('reader_back', { article_id: article.id });
          router.back();
        }} style={styles.backButton}>
          <Text style={styles.backLinkText}>{'← Feed'}</Text>
        </Pressable>
        <View style={{ flex: 1 }} />
        <Pressable onPress={async () => {
          const nowBookmarked = await toggleBookmark(article.id);
          setBookmarked(nowBookmarked);
          recordInterestSignal(nowBookmarked ? 'bookmark_add' : 'bookmark_remove', article.id);
          Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
        }} style={styles.bookmarkButton}>
          <Text style={[styles.bookmarkText, bookmarked && styles.bookmarkTextActive]}>
            {bookmarked ? '★' : '☆'}
          </Text>
        </Pressable>
        <Pressable onPress={() => {
          setShowMenu(!showMenu);
          logEvent('reader_menu_toggle', { article_id: article.id });
        }} style={styles.menuButton}>
          <Text style={styles.menuButtonText}>⋯</Text>
        </Pressable>
      </View>

      {/* Dropdown menu */}
      {showMenu && (
        <View style={styles.menuDropdown}>
          {/* Article ID */}
          <Pressable onPress={() => {
            Clipboard.setString(article.id);
            Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
            logEvent('reader_copy_id', { article_id: article.id });
          }} style={styles.menuItem}>
            <Text style={styles.menuItemLabel}>ID</Text>
            <Text style={styles.menuItemValue} numberOfLines={1}>{article.id}</Text>
          </Pressable>

          {/* Source */}
          <View style={styles.menuItem}>
            <Text style={styles.menuItemLabel}>Source</Text>
            <Text style={styles.menuItemValue} numberOfLines={1}>{article.hostname}</Text>
          </View>

          {/* Content type */}
          <View style={styles.menuItem}>
            <Text style={styles.menuItemLabel}>Type</Text>
            <Text style={styles.menuItemValue}>{article.content_type}</Text>
          </View>

          {/* Word count + read time */}
          <View style={styles.menuItem}>
            <Text style={styles.menuItemLabel}>Length</Text>
            <Text style={styles.menuItemValue}>{article.word_count?.toLocaleString()} words · {article.estimated_read_minutes} min</Text>
          </View>

          {/* Date */}
          {article.date ? (
            <View style={styles.menuItem}>
              <Text style={styles.menuItemLabel}>Date</Text>
              <Text style={styles.menuItemValue}>{article.date}</Text>
            </View>
          ) : null}

          {/* Topics */}
          {article.interest_topics && article.interest_topics.length > 0 ? (
            <View style={styles.menuItem}>
              <Text style={styles.menuItemLabel}>Topics</Text>
              <Text style={styles.menuItemValue} numberOfLines={2}>
                {article.interest_topics.map(t => t.broad).join(', ')}
              </Text>
            </View>
          ) : null}

          {/* Divider */}
          <View style={styles.menuDivider} />

          {/* Open source */}
          <Pressable onPress={() => {
            logEvent('reader_open_source', { article_id: article.id, url: article.source_url });
            Linking.openURL(article.source_url);
            setShowMenu(false);
          }} style={styles.menuAction}>
            <Text style={styles.menuActionText}>Open source →</Text>
          </Pressable>

          {/* Ask AI */}
          <Pressable onPress={() => {
            setShowMenu(false);
            setShowAIChat(true);
            logEvent('ai_chat_open', { article_id: article.id });
          }} style={styles.menuAction}>
            <Text style={[styles.menuActionText, { color: colors.rubric }]}>✦ Ask AI</Text>
          </Pressable>

          {/* Voice note */}
          <Pressable onPress={() => {
            setShowMenu(false);
            setShowVoiceFeedback(true);
            logEvent('voice_note_open', { article_id: article.id });
          }} style={styles.menuAction}>
            <Text style={styles.menuActionText}>● Voice note</Text>
          </Pressable>

          {/* Research topics */}
          {article.interest_topics && article.interest_topics.length > 0 ? (
            <Pressable onPress={async () => {
              const topic = article.interest_topics![0].broad;
              setShowMenu(false);
              try {
                await spawnTopicResearch(
                  topic,
                  `Article: ${article.title}\nSummary: ${article.one_line_summary}`,
                  [article.title],
                );
                Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
                logEvent('research_spawned', { article_id: article.id, topic });
              } catch (e) {
                logEvent('research_spawn_error', { article_id: article.id, error: String(e) });
              }
            }} style={styles.menuAction}>
              <Text style={[styles.menuActionText, { color: colors.claimNew }]}>
                ↗ Research "{article.interest_topics[0].broad}"
              </Text>
            </Pressable>
          ) : null}
        </View>
      )}

      {/* Progress bar */}
      <View style={styles.progressBarTrack}>
        <View style={[styles.progressBarFill, { width: `${scrollProgress}%` as any }]} />
      </View>

      {/* Main scrollable content */}
      <ScrollView
        ref={scrollRef}
        style={styles.scroll}
        showsVerticalScrollIndicator={false}
        scrollEventThrottle={16}
        onScroll={handleScroll}
      >
        {/* Title + metadata */}
        <Text style={styles.articleTitle}>{getDisplayTitle(article)}</Text>
        <View style={styles.metaRow}>
          {article.author ? <Text style={styles.metaText}>{article.author}</Text> : null}
          <Text style={styles.metaText}>{article.hostname}</Text>
          {article.date ? <Text style={styles.metaText}>{article.date}</Text> : null}
          <Text style={styles.metaText}>{article.estimated_read_minutes} min</Text>
        </View>

        {/* "What's new for you" card — knowledge-aware, prioritizing interesting claims */}
        {claimClassifications ? (() => {
          const newClaims = claimClassifications.filter((c: ClaimClassification) => c.classification === 'NEW');
          // Prioritize non-factual claims (causal, evaluative, comparative, etc.)
          const interesting = newClaims.filter((c: ClaimClassification) => c.claim_type !== 'factual');
          const fallback = newClaims.filter((c: ClaimClassification) => c.claim_type === 'factual');
          const displayClaims = [...interesting, ...fallback].slice(0, 3);
          if (displayClaims.length === 0 && newClaims.length === 0) return null;
          return (
            <View style={styles.noveltyCard}>
              <Text style={styles.noveltyTitle}>{'✦ What\u2019s new for you'}</Text>
              {articleNovelty && (
                <View style={styles.noveltyStats}>
                  <Text style={styles.noveltyStatText}>
                    {articleNovelty.new_claims} new · {articleNovelty.extends_claims} extend · {articleNovelty.known_claims} familiar
                  </Text>
                </View>
              )}
              {displayClaims.map((c: ClaimClassification, i: number) => (
                <View key={i} style={styles.noveltyItem}>
                  <View style={styles.noveltyDot} />
                  <Text style={styles.noveltyText}>{c.text}</Text>
                </View>
              ))}
            </View>
          );
        })() : article.novelty_claims && article.novelty_claims.length > 0 ? (
          <View style={styles.noveltyCard}>
            <Text style={styles.noveltyTitle}>{'✦ What\u2019s new'}</Text>
            {article.novelty_claims.slice(0, 3).map((nc, i) => (
              <View key={i} style={styles.noveltyItem}>
                <View style={styles.noveltyDot} />
                <Text style={styles.noveltyText}>{nc.claim}</Text>
              </View>
            ))}
          </View>
        ) : null}

        {/* Reading mode toggle — only when there are familiar blocks to dim */}
        {blockDimming && Array.from(blockDimming.values()).some(d => d.opacity < 1) && (
          <ReadingModeToggle mode={readingMode} onModeChange={(mode) => {
            setReadingMode(mode);
            logEvent('reading_mode_change', { article_id: article.id, mode });
          }} />
        )}

        {/* Full article content */}
        <MarkdownText
          content={fullContent}
          highlightedBlocks={highlightedBlocks}
          onBlockLongPress={handleBlockLongPress}
          blockDimming={blockDimming}
          readingMode={readingMode}
          entities={article.entities}
          onEntityLongPress={handleEntityLongPress}
          linkHandler={linkHandler}
          paragraphConnections={paragraphConnections}
          sourceArticleId={article.id}
        />

        {/* Inline entity popup */}
        {activeEntity && (
          <EntityPopup
            entity={activeEntity}
            articleTitle={article.title}
            onResearch={handleEntityResearch}
            onDismiss={() => {
              logEvent('entity_popup_dismiss', { article_id: article.id, entity: activeEntity.name });
              setActiveEntity(null);
            }}
          />
        )}

        {/* Connected reading */}
        <ConnectedReadingSection
          connections={crossArticleConnections}
          articleId={article.id}
        />

        {/* Follow-up research prompts */}
        <FollowUpSection
          questions={article.follow_up_questions || []}
          articleTitle={article.title}
          articleId={article.id}
          articleSummary={article.one_line_summary}
        />

        {/* Related articles */}
        <RelatedArticles article={article} />

        {/* Bottom spacer for footer bar */}
        <View style={{ height: 100 }} />
      </ScrollView>

      {/* Bottom footer bar: Done + Up Next */}
      {!showInterestCard && (
        <View style={styles.footerBar}>
          <Pressable style={styles.doneButton} onPress={handleDone}>
            <Text style={styles.doneButtonText}>Done</Text>
          </Pressable>
          {nextQueuedArticle ? (
            <Pressable style={styles.upNextButton} onPress={handleUpNext}>
              <Text style={styles.upNextLabel}>UP NEXT</Text>
              <Text style={styles.upNextTitle} numberOfLines={1}>
                {getDisplayTitle(nextQueuedArticle)}
              </Text>
              <Text style={styles.upNextArrow}>{'\u2192'}</Text>
            </Pressable>
          ) : (
            <Pressable style={styles.upNextButton} onPress={() => {
              logEvent('reader_back_to_feed', { article_id: article.id });
              router.back();
            }}>
              <Text style={styles.upNextArrow}>{'\u2190'}</Text>
              <Text style={styles.upNextTitle}>Back to feed</Text>
            </Pressable>
          )}
        </View>
      )}

      {/* Post-Read Interest Card */}
      {showInterestCard && article.interest_topics && (
        <PostReadInterestCard
          topics={article.interest_topics}
          onLevelSignal={handleLevelSignal}
          onClose={handleInterestClose}
        />
      )}

      {/* AI Chat */}
      {showAIChat && (
        <AskAI
          articleId={article.id}
          context={buildAIChatContext(article)}
          onClose={() => setShowAIChat(false)}
        />
      )}

      {/* Voice Note */}
      {showVoiceFeedback && (
        <View style={styles.voiceFeedbackOverlay}>
          <VoiceFeedback
            articleId={article.id}
            articleTitle={article.title}
            topics={(article.interest_topics || []).map(t => t.broad)}
            articleContext={buildAIChatContext(article)}
            onClose={() => setShowVoiceFeedback(false)}
          />
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.parchment,
    maxWidth: layout.readingMeasure,
    alignSelf: 'center' as const,
    width: '100%' as any,
  },

  // Top bar
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: layout.screenPadding,
    paddingVertical: 10,
    gap: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.rule,
  },
  backButton: {
    paddingVertical: 4,
  },
  backLinkText: {
    fontFamily: fonts.body,
    fontSize: 14,
    color: colors.textMuted,
  },
  bookmarkButton: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    minWidth: 44,
    minHeight: 44,
    justifyContent: 'center' as const,
    alignItems: 'center' as const,
  },
  bookmarkText: {
    fontSize: 20,
    color: colors.textMuted,
  },
  bookmarkTextActive: {
    color: colors.rubric,
  },
  menuButton: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    minWidth: 44,
    minHeight: 44,
    justifyContent: 'center' as const,
    alignItems: 'center' as const,
  },
  menuButtonText: {
    fontSize: 22,
    color: colors.textMuted,
    fontFamily: fonts.display,
  },
  menuDropdown: {
    backgroundColor: colors.parchment,
    borderBottomWidth: 1,
    borderBottomColor: colors.rule,
    paddingHorizontal: 16,
    paddingVertical: 8,
    ...(Platform.OS === 'web' ? {
      boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
    } : {
      shadowColor: '#000',
      shadowOffset: { width: 0, height: 2 },
      shadowOpacity: 0.08,
      shadowRadius: 8,
      elevation: 3,
    }),
  },
  menuItem: {
    flexDirection: 'row' as const,
    alignItems: 'flex-start' as const,
    paddingVertical: 5,
    gap: 10,
  },
  menuItemLabel: {
    fontFamily: fonts.uiMedium,
    fontSize: 11,
    color: colors.textMuted,
    textTransform: 'uppercase' as const,
    letterSpacing: 0.5,
    width: 50,
    marginTop: 2,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  menuItemValue: {
    fontFamily: fonts.reading,
    fontSize: 13,
    color: colors.textBody,
    flex: 1,
  },
  menuDivider: {
    height: 1,
    backgroundColor: colors.rule,
    marginVertical: 6,
  },
  menuAction: {
    paddingVertical: 8,
    minHeight: 36,
    justifyContent: 'center' as const,
  },
  menuActionText: {
    fontFamily: fonts.ui,
    fontSize: 14,
    color: colors.textBody,
  },
  voiceFeedbackOverlay: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
  },

  // Progress bar
  progressBarTrack: {
    height: 2,
    backgroundColor: colors.rule,
  },
  progressBarFill: {
    height: 2,
    backgroundColor: colors.rubric,
  },

  // Scroll
  scroll: {
    flex: 1,
    paddingHorizontal: layout.screenPadding,
  },

  // Header
  articleTitle: {
    ...type.readerTitle,
    color: colors.ink,
    marginTop: 20,
    marginBottom: 8,
  },
  metaRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: 16,
  },
  metaText: {
    ...type.metadata,
    color: colors.textMuted,
  },

  // Novelty card
  noveltyCard: {
    backgroundColor: colors.parchmentDark,
    borderLeftWidth: 3,
    borderLeftColor: colors.rubric,
    paddingHorizontal: 14,
    paddingVertical: 12,
    marginBottom: 20,
  },
  noveltyTitle: {
    ...type.sectionHead,
    color: colors.rubric,
    marginBottom: 8,
  },
  noveltyStats: {
    marginBottom: 8,
  },
  noveltyStatText: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.textSecondary,
    letterSpacing: 0.3,
  },
  noveltyItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    marginBottom: 4,
  },
  noveltyDot: {
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.rubric,
    marginTop: 8,
  },
  noveltyText: {
    fontFamily: fonts.reading,
    fontSize: 14,
    lineHeight: 21,
    color: colors.textBody,
    flex: 1,
  },

  // Reading mode toggle
  readingModeContainer: {
    alignItems: 'center',
    marginVertical: 12,
  },
  readingModeTrack: {
    flexDirection: 'row',
    backgroundColor: colors.parchmentDark,
    borderRadius: 0,
  },
  readingModeButton: {
    paddingVertical: 8,
    paddingHorizontal: 16,
    minHeight: layout.touchTarget,
    justifyContent: 'center',
    alignItems: 'center',
  },
  readingModeButtonActive: {
    backgroundColor: colors.ink,
  },
  readingModeLabel: {
    fontFamily: fonts.ui,
    fontSize: 11,
    textTransform: 'uppercase' as const,
    letterSpacing: 0.88,
    color: colors.textMuted,
  },
  readingModeLabelActive: {
    color: colors.parchment,
  },

  // Collapsed bar (stretchtext)
  collapsedBar: {
    backgroundColor: colors.parchmentDark,
    borderLeftWidth: 2,
    borderLeftColor: colors.claimKnown,
    paddingVertical: 10,
    paddingHorizontal: 14,
    marginBottom: 14,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  collapsedBarContent: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  collapsedBarDot: {
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.textMuted,
  },
  collapsedBarText: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.textMuted,
  },
  collapsedBarExpand: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.textMuted,
  },
  collapseBar: {
    paddingVertical: 8,
    paddingHorizontal: 14,
    marginBottom: 14,
    alignItems: 'center',
  },

  // Footer bar (Done + Up Next)
  footerBar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: layout.screenPadding,
    paddingVertical: 12,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.rule,
    backgroundColor: colors.parchment,
    gap: 12,
  },
  doneButton: {
    backgroundColor: colors.ink,
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 20,
    minHeight: layout.touchTarget,
    justifyContent: 'center',
  },
  doneButtonText: {
    fontFamily: fonts.uiMedium,
    fontSize: 14,
    color: colors.parchment,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  upNextButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    minHeight: layout.touchTarget,
    paddingHorizontal: 8,
  },
  upNextLabel: {
    fontFamily: fonts.uiMedium,
    fontSize: 9,
    letterSpacing: 0.8,
    color: colors.textMuted,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  upNextTitle: {
    fontFamily: fonts.body,
    fontSize: 13,
    color: colors.textSecondary,
    flex: 1,
  },
  upNextArrow: {
    fontFamily: fonts.body,
    fontSize: 15,
    color: colors.rubric,
  },

  // Markdown styles
  markdownText: {
    ...type.readerBody,
    color: colors.textBody,
    marginBottom: 14,
  },
  markdownHeading: {
    fontFamily: fonts.displaySemiBold,
    fontSize: 19,
    lineHeight: 26,
    color: colors.ink,
    marginTop: 24,
    marginBottom: 10,
    ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}),
  },
  markdownHr: {
    height: 1,
    backgroundColor: colors.rule,
    marginVertical: 20,
  },
  markdownLink: {
    color: colors.rubric,
    textDecorationLine: 'underline' as const,
  },
  ingestBadgeProcessing: {
    fontFamily: fonts.ui,
    fontSize: 8,
    color: colors.textMuted,
    letterSpacing: 0.3,
  },
  ingestBadgeQueued: {
    fontFamily: fonts.ui,
    fontSize: 8,
    color: colors.claimNew,
    letterSpacing: 0.3,
  },
  ingestBadgeFailed: {
    fontFamily: fonts.ui,
    fontSize: 8,
    color: colors.rubric,
    letterSpacing: 0.3,
  },
  markdownBold: {
    fontFamily: fonts.readingMedium,
    ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}),
  },
  markdownItalic: {
    fontFamily: fonts.readingItalic,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}),
  },
  markdownInlineCode: {
    fontFamily: Platform.select({ web: 'monospace', default: 'Courier' }),
    backgroundColor: colors.parchmentDark,
    fontSize: 14,
    paddingHorizontal: 4,
  },
  markdownList: {
    marginBottom: 14,
    paddingLeft: 4,
  },
  markdownListItem: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 4,
  },
  markdownBullet: {
    fontFamily: fonts.reading,
    fontSize: 16,
    color: colors.textMuted,
    width: 12,
  },
  markdownOrderedBullet: {
    fontFamily: fonts.ui,
    fontSize: 13,
    color: colors.textMuted,
    width: 20,
    textAlign: 'right' as const,
  },
  markdownBlockquote: {
    borderLeftWidth: 3,
    borderLeftColor: colors.rule,
    paddingLeft: 14,
    marginBottom: 14,
    marginLeft: 4,
  },
  markdownBlockquoteText: {
    fontFamily: fonts.readingItalic,
    fontSize: 15,
    lineHeight: 24,
    color: colors.textSecondary,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}),
  },
  codeBlock: {
    backgroundColor: colors.parchmentDark,
    padding: 14,
    marginBottom: 14,
    borderRadius: 3,
  },
  codeText: {
    fontFamily: Platform.select({ web: 'monospace', default: 'Courier' }),
    fontSize: 13,
    lineHeight: 20,
    color: colors.textBody,
  },

  // Table
  tableContainer: {
    marginBottom: 14,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.rule,
  },
  tableRow: {
    flexDirection: 'row',
  },
  tableRowAlt: {
    backgroundColor: colors.parchmentDark,
  },
  tableCell: {
    flex: 1,
    padding: 8,
    borderRightWidth: StyleSheet.hairlineWidth,
    borderRightColor: colors.rule,
  },
  tableHeaderCell: {
    backgroundColor: colors.parchmentDark,
    borderBottomWidth: 1,
    borderBottomColor: colors.rule,
  },
  tableHeaderText: {
    fontFamily: fonts.uiMedium,
    fontSize: 12,
    color: colors.ink,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  tableCellText: {
    fontFamily: fonts.reading,
    fontSize: 13,
    color: colors.textBody,
    lineHeight: 18,
  },

  // Highlight
  paragraphHighlight: {
    backgroundColor: 'rgba(218, 165, 32, 0.15)',
    borderLeftWidth: 3,
    borderLeftColor: 'rgba(218, 165, 32, 0.6)',
    paddingLeft: 10,
  },

  // Post-Read Interest Card
  interestCardOverlay: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: 'rgba(0,0,0,0.3)',
    paddingTop: 100,
    flex: 1,
  },
  interestCard: {
    backgroundColor: colors.parchment,
    borderTopLeftRadius: 16,
    borderTopRightRadius: 16,
    paddingHorizontal: 24,
    paddingTop: 24,
    paddingBottom: 40,
    ...(Platform.OS === 'web' ? {
      boxShadow: '0 -4px 16px rgba(0,0,0,0.1)',
    } : {
      shadowColor: '#000',
      shadowOffset: { width: 0, height: -4 },
      shadowOpacity: 0.1,
      shadowRadius: 16,
      elevation: 8,
    }),
  },
  interestCardTitle: {
    ...type.sectionHead,
    color: colors.ink,
    marginBottom: 4,
  },
  interestCardSubtitle: {
    ...type.metadata,
    color: colors.textMuted,
    marginBottom: 16,
  },
  interestChips: {
    gap: 10,
    marginBottom: 20,
  },
  interestChipRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  interestChipMinus: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: 'rgba(180, 60, 60, 0.1)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  interestChipPlus: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: 'rgba(60, 120, 60, 0.1)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  interestChipButtonText: {
    fontFamily: fonts.uiMedium,
    fontSize: 18,
    color: colors.ink,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  interestChipLabel: {
    flex: 1,
    backgroundColor: colors.parchmentDark,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 8,
  },
  interestChipText: {
    fontFamily: fonts.ui,
    fontSize: 14,
    color: colors.textPrimary,
  },
  interestCloseButton: {
    alignSelf: 'center',
    paddingVertical: 8,
    paddingHorizontal: 24,
  },
  interestCloseText: {
    ...type.metadata,
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 1,
  },

  // Error state
  errorText: {
    ...type.screenTitle,
    color: colors.ink,
    textAlign: 'center',
    marginTop: 100,
  },
  backLink: {
    ...type.metadata,
    color: colors.rubric,
    textAlign: 'center',
    marginTop: 12,
  },
});

const entityStyles = StyleSheet.create({
  entityMention: {
    textDecorationLine: 'underline',
    textDecorationStyle: 'dotted',
    textDecorationColor: colors.textMuted,
  },
  popupContainer: {
    backgroundColor: colors.parchmentDark,
    borderLeftWidth: 3,
    borderLeftColor: colors.rubric,
    paddingHorizontal: 14,
    paddingVertical: 12,
    marginBottom: 16,
    marginTop: 4,
  },
  popupType: {
    fontFamily: fonts.ui,
    fontSize: 9,
    textTransform: 'uppercase',
    letterSpacing: 1,
    color: colors.textMuted,
    marginBottom: 4,
  },
  popupName: {
    fontFamily: fonts.body,
    fontSize: 16,
    color: colors.ink,
    marginBottom: 6,
  },
  popupSynthesis: {
    fontFamily: fonts.reading,
    fontSize: 13,
    lineHeight: 19,
    color: colors.textSecondary,
    marginBottom: 10,
  },
  popupActions: {
    flexDirection: 'row',
    gap: 16,
  },
  popupAction: {
    paddingVertical: 4,
    minHeight: layout.touchTarget,
    justifyContent: 'center',
  },
  popupActionResearch: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.rubric,
  },
  popupActionDismiss: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.textMuted,
  },
});

const followUpStyles = StyleSheet.create({
  container: {
    marginTop: 24,
    marginBottom: 8,
  },
  sectionTitle: {
    ...type.sectionHead,
    color: colors.rubric,
    marginBottom: 12,
  },
  questionCard: {
    borderLeftWidth: 2,
    borderLeftColor: colors.rule,
    paddingLeft: 14,
    marginBottom: 16,
  },
  questionText: {
    fontFamily: fonts.readingItalic,
    fontSize: 15,
    lineHeight: 22,
    color: colors.textBody,
    marginBottom: 4,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}),
  },
  connectsTo: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 8,
  },
  researchButton: {
    paddingVertical: 4,
    alignSelf: 'flex-start',
    minHeight: layout.touchTarget,
    justifyContent: 'center',
  },
  researchButtonText: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.rubric,
  },
  launchedText: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.claimNew,
  },
});

// --- Hierarchical Interest Card Styles ---

const interestStyles = StyleSheet.create({
  chips: {
    gap: 6,
    marginBottom: 16,
  },
  chipRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    minHeight: 40,
  },
  chipMinus: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: 'rgba(180, 60, 60, 0.1)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  chipPlus: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: 'rgba(60, 120, 60, 0.1)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  chipButtonText: {
    fontFamily: fonts.uiMedium,
    fontSize: 16,
    color: colors.ink,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  chipLabel: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.parchmentDark,
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 6,
    gap: 6,
  },
  treeLine: {
    fontFamily: fonts.ui,
    fontSize: 12,
    color: colors.textMuted,
  },
  chipText: {
    fontFamily: fonts.ui,
    fontSize: 13,
    color: colors.textPrimary,
    flex: 1,
  },
  chipTextEntity: {
    fontFamily: fonts.bodyItalic,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}),
  },
  levelBadge: {
    fontFamily: fonts.ui,
    fontSize: 9,
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  expandButton: {
    alignSelf: 'center',
    paddingVertical: 6,
    paddingHorizontal: 16,
    marginBottom: 8,
  },
  expandText: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.textSecondary,
  },
});

// --- Connected Reading Styles ---

const connectedStyles = StyleSheet.create({
  container: {
    marginTop: 24,
    marginBottom: 8,
  },
  sectionTitle: {
    ...type.sectionHead,
    color: colors.rubric,
    marginBottom: 12,
  },
  card: {
    borderLeftWidth: 2,
    borderLeftColor: colors.rule,
    paddingLeft: 14,
    paddingVertical: 8,
    marginBottom: 12,
  },
  cardRead: {
    opacity: 0.6,
  },
  cardTitle: {
    fontFamily: fonts.bodyMedium,
    fontSize: 14,
    lineHeight: 19,
    color: colors.textPrimary,
    marginBottom: 4,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  cardTitleRead: {
    color: colors.textSecondary,
  },
  cardMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  cardClaimCount: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: colors.textMuted,
    flex: 1,
  },
  cardReadLabel: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: colors.textMuted,
  },
  cardQueuedLabel: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: colors.claimNew,
  },
  queueButton: {
    paddingVertical: 4,
    paddingHorizontal: 10,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: colors.rubric,
    minHeight: 28,
    justifyContent: 'center',
  },
  queueButtonText: {
    fontFamily: fonts.uiMedium,
    fontSize: 10,
    color: colors.rubric,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  // Inline annotations
  inlineAnnotation: {
    paddingLeft: 16,
    paddingVertical: 4,
    marginTop: -4,
    marginBottom: 4,
  },
  inlineAnnotationText: {
    fontFamily: fonts.ui,
    fontSize: 11,
    lineHeight: 16,
  },
  inlineAnnotationPrefix: {
    color: colors.textMuted,
  },
  inlineAnnotationTitle: {
    color: colors.rubric,
    fontFamily: fonts.bodyItalic,
    fontSize: 11,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}),
  },
  inlineAnnotationTitleRead: {
    color: colors.textSecondary,
  },
  inlineAnnotationRead: {
    color: colors.textMuted,
    fontSize: 10,
  },
  inlineAnnotationQueued: {
    color: colors.claimNew,
    fontSize: 10,
  },
  inlineAnnotationQueue: {
    color: colors.textMuted,
    fontSize: 10,
  },
});
