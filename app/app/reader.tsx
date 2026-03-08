import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, Linking,
  NativeSyntheticEvent, NativeScrollEvent,
  Platform, Clipboard,
} from 'react-native';
import AskAI from '../components/AskAI';
import VoiceFeedback from '../components/VoiceFeedback';
import { spawnTopicResearch } from '../lib/chat-api';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { getArticleById, getReadingState, updateReadingState, getHighlightBlockIndices, addHighlight, removeHighlight, markArticleRead, recordInterestSignal, recordTopicInterestSignal } from '../data/store';
import { Article, InterestTopic } from '../data/types';
import * as Haptics from 'expo-haptics';
import { logEvent } from '../data/logger';
import { isSectionValid, parseInlineMarkdown, splitMarkdownBlocks, parseMarkdownBlock } from '../lib/markdown-utils';
import { getDisplayTitle } from '../lib/display-utils';
import { toggleBookmark, isBookmarked } from '../data/bookmarks';
import { colors, fonts, type, spacing, layout } from '../design/tokens';
import {
  computeParagraphDimming, classifyArticleClaims,
  markArticleEncountered, isKnowledgeReady, getArticleNovelty
} from '../data/knowledge-engine';

const SCROLL_POSITION_SAVE_INTERVAL_MS = 2000;

// --- Types ---

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

// --- Post-Read Interest Card ---

function PostReadInterestCard({ topics, onChipSignal, onClose }: {
  topics: InterestTopic[];
  onChipSignal: (topic: InterestTopic, positive: boolean) => void;
  onClose: () => void;
}) {
  const [votes, setVotes] = useState<Record<string, 'positive' | 'negative'>>({});

  const handleVote = (topic: InterestTopic, positive: boolean) => {
    const key = topic.specific;
    const currentVote = votes[key];
    const newPositive = positive ? 'positive' : 'negative';
    // Toggle off if same vote, otherwise set
    if (currentVote === newPositive) {
      setVotes(prev => { const next = { ...prev }; delete next[key]; return next; });
    } else {
      setVotes(prev => ({ ...prev, [key]: newPositive }));
    }
    onChipSignal(topic, positive);
  };

  return (
    <View style={styles.interestCardOverlay}>
      <View style={styles.interestCard}>
        <Text style={styles.interestCardTitle}>Topics in this article</Text>
        <Text style={styles.interestCardSubtitle}>Tap + or - to shape your feed</Text>
        <View style={styles.interestChips}>
          {topics.map((t, i) => {
            const vote = votes[t.specific];
            return (
              <View key={i} style={styles.interestChipRow}>
                <Pressable
                  style={[styles.interestChipMinus, vote === 'negative' && styles.interestChipVotedNeg]}
                  onPress={() => handleVote(t, false)}
                >
                  <Text style={[styles.interestChipButtonText, vote === 'negative' && { color: colors.parchment }]}>-</Text>
                </Pressable>
                <View style={styles.interestChipLabel}>
                  <Text style={styles.interestChipText}>{t.entity || t.specific}</Text>
                </View>
                <Pressable
                  style={[styles.interestChipPlus, vote === 'positive' && styles.interestChipVotedPos]}
                  onPress={() => handleVote(t, true)}
                >
                  <Text style={[styles.interestChipButtonText, vote === 'positive' && { color: colors.parchment }]}>+</Text>
                </Pressable>
              </View>
            );
          })}
        </View>
        <Pressable style={styles.interestCloseButton} onPress={onClose}>
          <Text style={styles.interestCloseText}>Close</Text>
        </Pressable>
      </View>
    </View>
  );
}

function InlineTopicChips({ topics, onChipSignal }: {
  topics: InterestTopic[];
  onChipSignal: (topic: InterestTopic, positive: boolean) => void;
}) {
  const [votes, setVotes] = useState<Record<string, 'positive' | 'negative'>>({});

  const handleVote = (topic: InterestTopic, positive: boolean) => {
    const key = topic.specific;
    const currentVote = votes[key];
    const newVal = positive ? 'positive' : 'negative';
    if (currentVote === newVal) {
      setVotes(prev => { const next = { ...prev }; delete next[key]; return next; });
    } else {
      setVotes(prev => ({ ...prev, [key]: newVal }));
    }
    onChipSignal(topic, positive);
  };

  return (
    <View style={styles.inlineTopicsSection}>
      <Text style={styles.inlineTopicsTitle}>
        <Text style={{ color: colors.rubric }}>{'\u2726'} </Text>
        Topics
      </Text>
      <View style={styles.inlineTopicsGrid}>
        {topics.map((t, i) => {
          const vote = votes[t.specific];
          return (
            <View key={i} style={styles.inlineTopicRow}>
              <Pressable
                style={[styles.inlineTopicBtn, vote === 'negative' && { backgroundColor: colors.rubric }]}
                onPress={() => handleVote(t, false)}
              >
                <Text style={[styles.inlineTopicBtnText, vote === 'negative' && { color: colors.parchment }]}>−</Text>
              </Pressable>
              <Text style={styles.inlineTopicLabel} numberOfLines={1}>{t.entity || t.specific}</Text>
              <Pressable
                style={[styles.inlineTopicBtn, vote === 'positive' && { backgroundColor: colors.claimNew }]}
                onPress={() => handleVote(t, true)}
              >
                <Text style={[styles.inlineTopicBtnText, vote === 'positive' && { color: colors.parchment }]}>+</Text>
              </Pressable>
            </View>
          );
        })}
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

function renderInlineMarkdown(text: string): (string | React.ReactElement)[] {
  const segments = parseInlineMarkdown(text);
  return segments.map((seg, i) => {
    switch (seg.type) {
      case 'link':
        return (
          <Text
            key={`link-${i}`}
            style={styles.markdownLink}
            onPress={() => {
              logEvent('reader_link_tap', { url: seg.url, link_text: seg.text?.slice(0, 80) });
              Linking.openURL(seg.url);
            }}
            {...(Platform.OS === 'web' ? { accessibilityRole: 'link', href: seg.url, hrefAttrs: { target: '_blank', rel: 'noopener noreferrer' } } as any : {})}
          >
            {seg.text}
          </Text>
        );
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

// --- Markdown renderer ---

function MarkdownText({ content, highlightedBlocks, onBlockLongPress, blockDimming, readingMode = 'full' }: {
  content: string;
  highlightedBlocks?: Set<number>;
  onBlockLongPress?: (blockIndex: number, text: string) => void;
  blockDimming?: Map<number, { opacity: number; novelty: string }> | null;
  readingMode?: ReadingMode;
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

    switch (block.type) {
      case 'heading':
        return (
          <View key={i} style={opacityStyle}>
            <Text style={[
              styles.markdownHeading,
              block.level === 1 && { fontSize: 22 },
              block.level === 2 && { fontSize: 19 },
              (block.level ?? 3) >= 3 && { fontSize: 17 },
            ]}>
              {renderInlineMarkdown(block.content)}
            </Text>
          </View>
        );

      case 'hr':
        return <View key={i} style={[styles.markdownHr, opacityStyle]} />;

      case 'ul':
        return (
          <Pressable
            key={i}
            style={[styles.markdownList, isHighlighted && styles.paragraphHighlight, opacityStyle]}
            onLongPress={onBlockLongPress ? () => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium); onBlockLongPress(i, raw); } : undefined}
          >
            {(block.items || []).map((item, j) => (
              <View key={j} style={styles.markdownListItem}>
                <Text style={styles.markdownBullet}>{'·'}</Text>
                <Text style={styles.markdownText}>{renderInlineMarkdown(item)}</Text>
              </View>
            ))}
          </Pressable>
        );

      case 'ol':
        return (
          <Pressable
            key={i}
            style={[styles.markdownList, isHighlighted && styles.paragraphHighlight, opacityStyle]}
            onLongPress={onBlockLongPress ? () => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium); onBlockLongPress(i, raw); } : undefined}
          >
            {(block.items || []).map((item, j) => (
              <View key={j} style={styles.markdownListItem}>
                <Text style={styles.markdownOrderedBullet}>{j + 1}.</Text>
                <Text style={styles.markdownText}>{renderInlineMarkdown(item)}</Text>
              </View>
            ))}
          </Pressable>
        );

      case 'code':
        return (
          <View key={i} style={[styles.codeBlock, isHighlighted && styles.paragraphHighlight, opacityStyle]}>
            <Text style={styles.codeText}>{block.content}</Text>
          </View>
        );

      case 'blockquote':
        return (
          <Pressable
            key={i}
            onLongPress={onBlockLongPress ? () => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium); onBlockLongPress(i, raw); } : undefined}
            style={[styles.markdownBlockquote, isHighlighted && styles.paragraphHighlight, opacityStyle]}
          >
            <Text style={styles.markdownBlockquoteText}>{renderInlineMarkdown(block.content)}</Text>
          </Pressable>
        );

      case 'table':
        return (
          <View key={i} style={[styles.tableContainer, opacityStyle]}>
            {block.headers && block.headers.length > 0 && (
              <View style={styles.tableRow}>
                {block.headers.map((h, hi) => (
                  <View key={hi} style={[styles.tableCell, styles.tableHeaderCell]}>
                    <Text style={styles.tableHeaderText}>{renderInlineMarkdown(h)}</Text>
                  </View>
                ))}
              </View>
            )}
            {(block.rows || []).map((row, ri) => (
              <View key={ri} style={[styles.tableRow, ri % 2 === 1 && styles.tableRowAlt]}>
                {row.map((cell, ci) => (
                  <View key={ci} style={styles.tableCell}>
                    <Text style={styles.tableCellText}>{renderInlineMarkdown(cell)}</Text>
                  </View>
                ))}
              </View>
            ))}
          </View>
        );

      default:
        return (
          <Pressable
            key={i}
            onLongPress={onBlockLongPress ? () => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium); onBlockLongPress(i, block.content); } : undefined}
            style={[isHighlighted ? styles.paragraphHighlight : undefined, opacityStyle]}
          >
            <Text style={styles.markdownText}>{renderInlineMarkdown(block.content)}</Text>
          </Pressable>
        );
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
  const [longPressContext, setLongPressContext] = useState<{ blockIndex: number; text: string } | null>(null);
  const contentHeight = useRef(0);
  const viewportHeight = useRef(0);

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

  // Long-press handler — shows action menu
  const handleBlockLongPress = useCallback((blockIndex: number, text: string) => {
    if (!article) return;
    setLongPressContext({ blockIndex, text });
    logEvent('reader_long_press', { article_id: article.id, block_index: blockIndex });
  }, [article]);

  const handleHighlightBlock = useCallback(() => {
    if (!article || !longPressContext) return;
    const { blockIndex, text } = longPressContext;
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
    setLongPressContext(null);
  }, [article, longPressContext]);

  const [researchQuestion, setResearchQuestion] = useState<string | undefined>();

  const handleResearchPassage = useCallback(() => {
    if (!article || !longPressContext) return;
    const question = `The user is reading this passage and wants to learn more:\n\n"${longPressContext.text.slice(0, 800)}"\n\nIdentify the most interesting entity, concept, or reference mentioned (person, book, company, theory, etc.) and provide a concise but informative summary. Suggest 2-3 follow-up questions.`;
    setResearchQuestion(question);
    setLongPressContext(null);
    setShowAIChat(true);
    logEvent('research_passage', { article_id: article.id, text_preview: longPressContext.text.slice(0, 80) });
  }, [article, longPressContext]);

  // Done handler
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

  const handleChipSignal = useCallback((topic: InterestTopic, positive: boolean) => {
    if (!article) return;
    const action = positive ? 'interest_chip_positive' : 'interest_chip_negative';
    recordTopicInterestSignal(action, topic);
    logEvent('interest_chip_tap', { article_id: article.id, topic: topic.specific, positive });
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

        {/* "What's new for you" card — knowledge-aware version */}
        {claimClassifications ? (
          <View style={styles.noveltyCard}>
            <Text style={styles.noveltyTitle}>{'✦ What\u2019s new for you'}</Text>
            {articleNovelty && (
              <View style={styles.noveltyStats}>
                <Text style={styles.noveltyStatText}>
                  {articleNovelty.new_claims} new · {articleNovelty.extends_claims} extend · {articleNovelty.known_claims} familiar
                </Text>
              </View>
            )}
            {claimClassifications
              .filter((c: ClaimClassification) => c.classification === 'NEW')
              .slice(0, 5)
              .map((c: ClaimClassification, i: number) => (
                <View key={i} style={styles.noveltyItem}>
                  <View style={styles.noveltyDot} />
                  <Text style={styles.noveltyText}>{c.text}</Text>
                </View>
              ))
            }
          </View>
        ) : article.novelty_claims && article.novelty_claims.length > 0 ? (
          <View style={styles.noveltyCard}>
            <Text style={styles.noveltyTitle}>{'✦ What\u2019s new'}</Text>
            {article.novelty_claims.map((nc, i) => (
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
        />

        {/* Inline topic interest chips at end of article */}
        {article.interest_topics && article.interest_topics.length > 0 && (
          <InlineTopicChips
            topics={article.interest_topics.slice(0, 6)}
            onChipSignal={handleChipSignal}
          />
        )}

        {/* Bottom spacer for Done button */}
        <View style={{ height: 100 }} />
      </ScrollView>

      {/* Floating Done button */}
      {!showInterestCard && (
        <Pressable style={styles.doneButton} onPress={handleDone}>
          <Text style={styles.doneButtonText}>Done</Text>
        </Pressable>
      )}

      {/* Post-Read Interest Card */}
      {showInterestCard && article.interest_topics && (
        <PostReadInterestCard
          topics={article.interest_topics.slice(0, 4)}
          onChipSignal={handleChipSignal}
          onClose={handleInterestClose}
        />
      )}

      {/* Long-press action menu */}
      {longPressContext && (
        <View style={styles.longPressOverlay}>
          <Pressable style={styles.longPressBackdrop} onPress={() => setLongPressContext(null)} />
          <View style={styles.longPressMenu}>
            <Text style={styles.longPressPreview} numberOfLines={2}>
              {longPressContext.text.slice(0, 120)}...
            </Text>
            <View style={styles.longPressActions}>
              <Pressable style={styles.longPressAction} onPress={handleHighlightBlock}>
                <Text style={styles.longPressActionText}>
                  {highlightedBlocks.has(longPressContext.blockIndex) ? 'Unhighlight' : 'Highlight'}
                </Text>
              </Pressable>
              <Pressable style={styles.longPressAction} onPress={handleResearchPassage}>
                <Text style={[styles.longPressActionText, { color: colors.claimNew }]}>Research</Text>
              </Pressable>
              <Pressable style={styles.longPressAction} onPress={() => {
                setLongPressContext(null);
                setShowAIChat(true);
              }}>
                <Text style={[styles.longPressActionText, { color: colors.rubric }]}>Ask AI</Text>
              </Pressable>
            </View>
          </View>
        </View>
      )}

      {/* AI Chat */}
      {showAIChat && (
        <AskAI
          articleId={article.id}
          context={buildAIChatContext(article)}
          initialQuestion={researchQuestion}
          onClose={() => {
            setShowAIChat(false);
            setResearchQuestion(undefined);
          }}
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

  // Done button
  doneButton: {
    position: 'absolute',
    bottom: 24,
    right: 24,
    backgroundColor: colors.ink,
    paddingHorizontal: 28,
    paddingVertical: 12,
    borderRadius: 24,
    ...(Platform.OS === 'web' ? {
      boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
    } : {
      shadowColor: '#000',
      shadowOffset: { width: 0, height: 2 },
      shadowOpacity: 0.15,
      shadowRadius: 8,
      elevation: 4,
    }),
  },
  doneButtonText: {
    fontFamily: fonts.uiMedium,
    fontSize: 15,
    color: colors.parchment,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
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
  interestChipVotedNeg: {
    backgroundColor: colors.rubric,
  },
  interestChipPlus: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: 'rgba(60, 120, 60, 0.1)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  interestChipVotedPos: {
    backgroundColor: colors.claimNew,
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

  // Long-press action menu
  longPressOverlay: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: 'flex-end',
    zIndex: 50,
  },
  longPressBackdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.2)',
  },
  longPressMenu: {
    backgroundColor: colors.parchment,
    borderTopWidth: 1,
    borderTopColor: colors.rule,
    paddingHorizontal: layout.screenPadding,
    paddingVertical: 16,
  },
  longPressPreview: {
    fontFamily: fonts.reading,
    fontSize: 13,
    color: colors.textSecondary,
    lineHeight: 18,
    marginBottom: 12,
  },
  longPressActions: {
    flexDirection: 'row',
    gap: 12,
  },
  longPressAction: {
    backgroundColor: colors.parchmentDark,
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 20,
    minWidth: 80,
    alignItems: 'center',
  },
  longPressActionText: {
    fontFamily: fonts.uiMedium,
    fontSize: 14,
    color: colors.ink,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  // Inline topic chips
  inlineTopicsSection: {
    marginTop: 24,
    paddingTop: 16,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.rule,
  },
  inlineTopicsTitle: {
    ...type.sectionHead,
    color: colors.rubric,
    marginBottom: 12,
  },
  inlineTopicsGrid: {
    gap: 8,
  },
  inlineTopicRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  inlineTopicBtn: {
    width: 30,
    height: 30,
    borderRadius: 15,
    backgroundColor: colors.parchmentDark,
    justifyContent: 'center',
    alignItems: 'center',
  },
  inlineTopicBtnText: {
    fontFamily: fonts.uiMedium,
    fontSize: 16,
    color: colors.ink,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  inlineTopicLabel: {
    flex: 1,
    fontFamily: fonts.bodyItalic,
    fontSize: 14,
    color: colors.textBody,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}),
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
