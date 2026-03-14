import React, { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, Linking, Platform,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';
import {
  getSynthesisForCluster, getArticleById, getArticles, markClaimsEncountered,
  markSynthesisCompleted, isSynthesisCompleted, bumpFeedVersion,
} from '../data/store';
import { logEvent } from '../data/logger';
import { getDisplayTitle } from '../lib/display-utils';
import {
  splitMarkdownBlocks, parseMarkdownBlock, parseInlineMarkdown,
} from '../lib/markdown-utils';
import { spawnTopicResearch } from '../lib/chat-api';
import DoubleRule from '../components/DoubleRule';
import { useKeyboardShortcuts, type ShortcutMap } from '../hooks/useKeyboardShortcuts';
import { fonts } from '../design/tokens';

let SynthesisChat: any = null;
try {
  SynthesisChat = require('../components/SynthesisChat').default;
} catch (_) {}

// --- Folio color palette ---

const fc = {
  bg: '#f5f1e8',
  ink: '#2e2924',
  accent: '#8b2500',
  body: '#3a3632',
  secondary: '#6e675e',
  muted: '#a69e90',
  line: '#ddd8cc',
  surface: '#edeade',
  green: '#2a7a4a',
  amber: '#b89840',
};

// --- Resolve raw article IDs and quoted titles in synthesis markdown ---

function buildArticleTitleMap(): Map<string, { id: string; title: string }> {
  const map = new Map<string, { id: string; title: string }>();
  const articles = getArticles();
  for (const a of articles) {
    const title = getDisplayTitle(a);
    // Map by ID prefix (12-char hex hashes used in synthesis text)
    map.set(a.id.slice(0, 12), { id: a.id, title });
    // Map by full ID
    map.set(a.id, { id: a.id, title });
    // Map by title (lowercase for matching quoted titles)
    if (title) map.set(title.toLowerCase(), { id: a.id, title });
  }
  return map;
}

let _articleTitleMap: Map<string, { id: string; title: string }> | null = null;
function getArticleTitleMap() {
  if (!_articleTitleMap) _articleTitleMap = buildArticleTitleMap();
  return _articleTitleMap;
}

function resolveArticleReferences(text: string): string {
  const map = getArticleTitleMap();

  // Replace [hex_hash] patterns with article links
  // Matches 8-16 char hex strings in brackets
  text = text.replace(/\[([0-9a-f]{8,16})\]/gi, (match, id) => {
    const entry = map.get(id);
    if (entry) return `[${entry.title}](article:${entry.id})`;
    return ''; // Strip unresolvable IDs
  });

  // Replace "Article Title" (in quotes) with links when they match known articles
  // Only match titles that are at least 15 chars to avoid false positives
  text = text.replace(/"([^"]{15,})"/g, (match, title) => {
    const entry = map.get(title.toLowerCase());
    if (entry) return `[${title}](article:${entry.id})`;
    return match; // Keep quotes if no match
  });

  return text;
}

// --- Extract ## headings from markdown for TOC ---

function extractHeadings(markdown: string): string[] {
  const headings: string[] = [];
  for (const line of markdown.split('\n')) {
    const m = line.match(/^##\s+(.+)$/);
    if (m) headings.push(m[1]);
  }
  return headings;
}

// --- Inline markdown renderer ---

function renderInlineMarkdown(text: string, router?: any): (string | React.ReactElement)[] {
  const segments = parseInlineMarkdown(text);
  return segments.map((seg, i) => {
    switch (seg.type) {
      case 'link':
        if (seg.url.startsWith('article:')) {
          const articleId = seg.url.slice(8);
          if (Platform.OS === 'web') {
            return (
              <Text
                key={`alink-${i}`}
                style={s.articleRef}
                {...{ 'data-article-id': articleId } as any}
                onPress={() => {
                  logEvent('synthesis_article_ref_tap', { article_id: articleId });
                  router?.push({ pathname: '/reader', params: { id: articleId } });
                }}
                {...{ cursor: 'pointer' } as any}
              >
                {seg.text}
              </Text>
            );
          }
          return (
            <Text
              key={`alink-${i}`}
              style={s.articleRef}
              onPress={() => {
                logEvent('synthesis_article_ref_tap', { article_id: articleId });
                router?.push({ pathname: '/reader', params: { id: articleId } });
              }}
            >
              {seg.text}
            </Text>
          );
        }
        return (
          <Text
            key={`link-${i}`}
            style={s.markdownLink}
            onPress={() => {
              logEvent('synthesis_link_tap', { url: seg.url });
              Linking.openURL(seg.url);
            }}
            {...(Platform.OS === 'web' ? { accessibilityRole: 'link', href: seg.url, hrefAttrs: { target: '_blank', rel: 'noopener noreferrer' } } as any : {})}
          >
            {seg.text}
          </Text>
        );
      case 'bold':
        return <Text key={`bold-${i}`} style={s.markdownBold}>{seg.text}</Text>;
      case 'italic':
        return <Text key={`italic-${i}`} style={s.markdownItalic}>{seg.text}</Text>;
      case 'code':
        return <Text key={`code-${i}`} style={s.markdownInlineCode}>{seg.text}</Text>;
      default:
        return seg.text;
    }
  });
}

// --- TensionBlock ---

function TensionBlock({ content, label }: { content: string; label?: string }) {
  const router = useRouter();
  return (
    <View style={s.tensionBlock}>
      {label && <Text style={s.tensionLabel}>{label}</Text>}
      <Text style={s.tensionText}>{renderInlineMarkdown(content, router)}</Text>
    </View>
  );
}

// --- ExcerptBlock ---

function ExcerptBlock({ content }: { content: string }) {
  const router = useRouter();
  return (
    <View style={s.excerptBlock}>
      <Text style={s.excerptLabel}>From the article</Text>
      <Text style={s.excerptText}>{renderInlineMarkdown(content, router)}</Text>
    </View>
  );
}

// --- Collapsible detail section ---

function DetailSection({ children }: { children: React.ReactNode }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <View style={s.detailSection}>
      <Pressable
        onPress={() => {
          setExpanded(!expanded);
          logEvent('synthesis_detail_toggle', { expanded: !expanded });
        }}
        style={s.detailToggle}
      >
        <Text style={s.detailToggleText}>
          {expanded ? '\u25BE Detail' : '\u25B8 Detail'}
        </Text>
      </Pressable>
      {expanded && <View style={s.detailContent}>{children}</View>}
    </View>
  );
}

// --- Enhanced MarkdownContent ---

function MarkdownContent({
  content,
  headingIdPrefix,
}: {
  content: string;
  headingIdPrefix?: string;
}) {
  const router = useRouter();
  if (!content) return null;

  const resolved = resolveArticleReferences(content);

  // Split on <!-- detail --> / <!-- /detail --> markers
  const detailRe = /<!--\s*detail\s*-->([\s\S]*?)<!--\s*\/detail\s*-->/g;
  const segments: Array<{ type: 'normal' | 'detail'; text: string }> = [];
  let lastIdx = 0;
  let match: RegExpExecArray | null;
  const resolvedCopy = resolved;
  while ((match = detailRe.exec(resolvedCopy)) !== null) {
    if (match.index > lastIdx) {
      segments.push({ type: 'normal', text: resolvedCopy.slice(lastIdx, match.index) });
    }
    segments.push({ type: 'detail', text: match[1] });
    lastIdx = match.index + match[0].length;
  }
  if (lastIdx < resolvedCopy.length) {
    segments.push({ type: 'normal', text: resolvedCopy.slice(lastIdx) });
  }

  let headingCounter = 0;

  function renderBlocks(text: string) {
    const blocks = splitMarkdownBlocks(text);
    return blocks.map((raw, i) => {
      const block = parseMarkdownBlock(raw);

      switch (block.type) {
        case 'heading': {
          const isH2 = block.level === 2;
          const hIdx = isH2 ? headingCounter++ : undefined;
          const idProp = isH2 && headingIdPrefix && Platform.OS === 'web'
            ? { nativeID: `${headingIdPrefix}-${hIdx}`, id: `${headingIdPrefix}-${hIdx}` } as any
            : {};
          return (
            <Text
              key={i}
              style={[
                s.markdownHeading,
                block.level === 2 && s.markdownH2,
                (block.level ?? 3) >= 3 && s.markdownH3,
              ]}
              {...idProp}
            >
              {block.level === 2 && (
                <Text style={{ color: fc.accent }}>{'\u2726'} </Text>
              )}
              {renderInlineMarkdown(block.content, router)}
            </Text>
          );
        }

        case 'hr':
          return <View key={i} style={s.markdownHr} />;

        case 'ul':
          return (
            <View key={i} style={s.markdownList}>
              {(block.items || []).map((item, j) => (
                <View key={j} style={s.markdownListItem}>
                  <Text style={s.markdownBullet}>{'\u00b7'}</Text>
                  <Text style={s.markdownText}>{renderInlineMarkdown(item, router)}</Text>
                </View>
              ))}
            </View>
          );

        case 'ol':
          return (
            <View key={i} style={s.markdownList}>
              {(block.items || []).map((item, j) => (
                <View key={j} style={s.markdownListItem}>
                  <Text style={s.markdownOrderedBullet}>{j + 1}.</Text>
                  <Text style={s.markdownText}>{renderInlineMarkdown(item, router)}</Text>
                </View>
              ))}
            </View>
          );

        case 'blockquote': {
          const isTension = block.content.startsWith('\u26A1');
          if (isTension) {
            const tensionContent = block.content.replace(/^\u26A1\s*/, '');
            return <TensionBlock key={i} content={tensionContent} label={'\u26A1 Tension'} />;
          }
          return <ExcerptBlock key={i} content={block.content} />;
        }

        case 'code':
          return (
            <View key={i} style={s.codeBlock}>
              <Text style={s.codeText}>{block.content}</Text>
            </View>
          );

        case 'table': {
          const headers = block.headers || [];
          const rows = block.rows || [];
          return (
            <View key={i} style={s.tableWrap}>
              {headers.length > 0 && (
                <View style={s.tableRow}>
                  {headers.map((h, hi) => (
                    <Text key={hi} style={[s.tableCell, s.tableHeader]}>{h}</Text>
                  ))}
                </View>
              )}
              {rows.map((row, ri) => (
                <View key={ri} style={s.tableRow}>
                  {row.map((cell, ci) => (
                    <Text key={ci} style={s.tableCell}>
                      {renderInlineMarkdown(cell, router)}
                    </Text>
                  ))}
                </View>
              ))}
            </View>
          );
        }

        default:
          return (
            <Text key={i} style={s.markdownText}>
              {renderInlineMarkdown(block.content, router)}
            </Text>
          );
      }
    });
  }

  return (
    <>
      {segments.map((seg, si) => {
        if (seg.type === 'detail') {
          return (
            <DetailSection key={`d-${si}`}>
              {renderBlocks(seg.text)}
            </DetailSection>
          );
        }
        return <React.Fragment key={`n-${si}`}>{renderBlocks(seg.text)}</React.Fragment>;
      })}
    </>
  );
}

// --- Source Article for sidebar ---

function SidebarSourceArticle({ articleId, coverage }: {
  articleId: string;
  coverage: number;
}) {
  const router = useRouter();
  const article = getArticleById(articleId);
  const [hovered, setHovered] = useState(false);

  if (!article) return null;

  const pct = Math.round(coverage * 100);

  return (
    <Pressable
      style={[s.sidebarSource, hovered && { opacity: 0.8 }]}
      onPress={() => {
        logEvent('synthesis_source_article_tap', { article_id: articleId, coverage: pct });
        router.push({ pathname: '/reader', params: { id: articleId } });
      }}
      {...(Platform.OS === 'web' ? {
        onMouseEnter: () => setHovered(true),
        onMouseLeave: () => setHovered(false),
      } as any : {})}
    >
      <Text style={s.sidebarSourceTitle} numberOfLines={2}>
        {getDisplayTitle(article)}
      </Text>
      <View style={s.sidebarCoverageBar}>
        <View style={[s.sidebarCoverageFill, { width: `${pct}%` as any }]} />
      </View>
      <Text style={s.sidebarSourceMeta}>
        {article.hostname} {'\u00b7'} {pct}% covered
      </Text>
    </Pressable>
  );
}

// --- Mobile source article row ---

function MobileSourceRow({ articleId, coverage }: {
  articleId: string;
  coverage: number;
}) {
  const router = useRouter();
  const article = getArticleById(articleId);

  if (!article) return null;
  const pct = Math.round(coverage * 100);

  return (
    <Pressable
      style={s.mobileSourceRow}
      onPress={() => {
        logEvent('synthesis_source_article_tap', { article_id: articleId, coverage: pct });
        router.push({ pathname: '/reader', params: { id: articleId } });
      }}
    >
      <Text style={s.mobileSourceTitle} numberOfLines={1}>
        {getDisplayTitle(article)}
      </Text>
      <View style={s.mobileCoverageBar}>
        <View style={[s.mobileCoverageFill, { width: `${pct}%` as any }]} />
      </View>
      <Text style={s.mobileSourceMeta}>
        {article.hostname} {'\u00b7'} {pct}% covered
      </Text>
    </Pressable>
  );
}

// --- Research Prompt Item ---

function ResearchPromptItem({ question, researchPrompt, relatedTopics, onResearch, onChat }: {
  question: string;
  researchPrompt: string;
  relatedTopics: string[];
  onResearch: () => void;
  onChat: () => void;
}) {
  const [dispatched, setDispatched] = useState(false);

  const handleResearch = useCallback(async () => {
    if (dispatched) return;
    try {
      await spawnTopicResearch(researchPrompt, question, relatedTopics);
      setDispatched(true);
      if (Platform.OS !== 'web') {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      }
      logEvent('synthesis_follow_up_dispatched', { question, research_prompt: researchPrompt });
      onResearch();
    } catch (e) {
      logEvent('synthesis_follow_up_error', { question, error: String(e) });
    }
  }, [dispatched, question, researchPrompt, relatedTopics, onResearch]);

  return (
    <View style={s.researchPromptItem}>
      <Text style={s.researchPromptText}>{question}</Text>
      <View style={s.researchPromptActions}>
        <Pressable onPress={handleResearch}>
          <Text style={dispatched ? s.researchDispatched : s.researchActionLink}>
            {dispatched ? 'Dispatched \u2713' : '\u2197 Research'}
          </Text>
        </Pressable>
        <Pressable onPress={() => {
          logEvent('synthesis_chat_from_prompt', { question });
          onChat();
        }}>
          <Text style={s.researchActionLink}>{'\uD83D\uDCAC'} Chat</Text>
        </Pressable>
      </View>
    </View>
  );
}

// --- SynthesisTopBar ---

function SynthesisTopBar({
  completed,
  onBack,
  onDone,
  onChat,
}: {
  completed: boolean;
  onBack: () => void;
  onDone: () => void;
  onChat: () => void;
}) {
  const [backHovered, setBackHovered] = useState(false);
  const webHover = Platform.OS === 'web' ? {
    onMouseEnter: () => setBackHovered(true),
    onMouseLeave: () => setBackHovered(false),
  } as any : {};

  return (
    <View style={s.topBar}>
      <Pressable onPress={onBack} style={s.topBarBack} {...webHover}>
        <Text style={[s.topBarBackText, backHovered && { color: fc.ink }]}>
          {'\u2190'} Topics
        </Text>
      </Pressable>
      <View style={{ flex: 1 }} />
      <Pressable
        onPress={onChat}
        style={s.topBarBtn}
      >
        <Text style={s.topBarBtnText}>Ask about this</Text>
      </Pressable>
      {!completed ? (
        <Pressable onPress={onDone} style={s.topBarDoneBtn}>
          <Text style={s.topBarDoneBtnText}>Mark as read</Text>
        </Pressable>
      ) : (
        <Text style={s.topBarCompleted}>{'\u2713'} Completed</Text>
      )}
    </View>
  );
}

// --- SynthesisSidebar (web only) ---

function SynthesisSidebar({
  headings,
  activeHeadingIndex,
  sourceArticles,
  synthesis,
  onFollowUpResearch,
  onFollowUpChat,
}: {
  headings: string[];
  activeHeadingIndex: number;
  sourceArticles: { id: string; coverage: number }[];
  synthesis: any;
  onFollowUpResearch: () => void;
  onFollowUpChat: (question: string) => void;
}) {
  const stickyStyle = Platform.OS === 'web' ? {
    position: 'sticky' as any,
    top: 49,
    alignSelf: 'start' as any,
    height: 'calc(100vh - 49px)' as any,
    overflowY: 'auto' as any,
  } as any : {};

  return (
    <View style={[s.sidebar, stickyStyle]}>
      {/* TOC */}
      {headings.length > 0 && (
        <View style={s.sidebarSection}>
          <Text style={s.sidebarLabel}>Contents</Text>
          {headings.map((h, i) => (
            <Pressable
              key={i}
              onPress={() => {
                if (Platform.OS === 'web') {
                  const el = document.getElementById(`sh-${i}`);
                  el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                  logEvent('synthesis_toc_click', { heading: h, index: i });
                }
              }}
              style={s.tocItem}
            >
              <Text
                style={[
                  s.tocText,
                  i === activeHeadingIndex && { color: fc.accent },
                ]}
                numberOfLines={2}
              >
                {h}
              </Text>
            </Pressable>
          ))}
        </View>
      )}

      {/* Source articles */}
      <View style={s.sidebarSection}>
        <Text style={s.sidebarLabel}>Sources</Text>
        {sourceArticles.map(({ id, coverage }) => (
          <SidebarSourceArticle key={id} articleId={id} coverage={coverage} />
        ))}
      </View>

      {/* Research prompts */}
      {synthesis.follow_up_questions?.length > 0 && (
        <View style={s.sidebarSection}>
          <Text style={s.sidebarLabel}>Further inquiry</Text>
          {synthesis.follow_up_questions.map((q: any, i: number) => (
            <ResearchPromptItem
              key={i}
              question={q.question}
              researchPrompt={q.research_prompt}
              relatedTopics={q.related_topics}
              onResearch={onFollowUpResearch}
              onChat={() => onFollowUpChat(q.question)}
            />
          ))}
        </View>
      )}
    </View>
  );
}

// --- Web grid style ---

const webGridStyle = Platform.OS === 'web' ? {
  display: 'grid' as any,
  gridTemplateColumns: '1fr 190px' as any,
  maxWidth: 830,
  margin: '0 auto' as any,
  minHeight: '100vh' as any,
  gap: 0,
} as any : undefined;

// --- Main Screen ---

export default function SynthesisReaderScreen() {
  const { clusterId } = useLocalSearchParams<{ clusterId: string }>();
  const router = useRouter();
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [showChat, setShowChat] = useState(false);
  const [chatInitialQuestion, setChatInitialQuestion] = useState<string | undefined>(undefined);
  const [activeHeadingIndex, setActiveHeadingIndex] = useState(0);
  const observerRef = useRef<any>(null);

  const synthesis = clusterId ? getSynthesisForCluster(clusterId) : undefined;
  const completed = clusterId ? isSynthesisCompleted(clusterId) : false;

  const sourceArticles = useMemo(() => {
    if (!synthesis) return [];
    return synthesis.article_ids
      .map(id => ({
        id,
        coverage: synthesis.article_coverage[id] || 0,
      }))
      .sort((a, b) => b.coverage - a.coverage);
  }, [synthesis]);

  const headings = useMemo(() => {
    if (!synthesis) return [];
    return extractHeadings(synthesis.synthesis_markdown);
  }, [synthesis]);

  const handleDone = useCallback(() => {
    if (!synthesis || !clusterId) return;

    const count = markClaimsEncountered(synthesis.claims_covered, 'read');
    markSynthesisCompleted(clusterId);
    bumpFeedVersion();

    logEvent('synthesis_done', {
      cluster_id: clusterId,
      claims_marked: count,
      article_count: synthesis.article_ids.length,
    });

    setStatusMessage(`Marked ${count} claims from ${synthesis.article_ids.length} articles as read`);

    if (Platform.OS !== 'web') {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    }

    setTimeout(() => {
      router.back();
    }, 1200);
  }, [synthesis, clusterId, router]);

  const handleFollowUpResearch = useCallback(() => {
    setStatusMessage('Research dispatched');
    setTimeout(() => setStatusMessage(null), 2000);
  }, []);

  const handleOpenChat = useCallback((initialQuestion?: string) => {
    setChatInitialQuestion(initialQuestion);
    setShowChat(true);
    logEvent('synthesis_chat_open', { cluster_id: clusterId, initial_question: initialQuestion });
  }, [clusterId]);

  // Keyboard shortcuts
  const shortcuts = useMemo((): ShortcutMap => {
    return {
      Escape: { handler: () => router.back(), label: 'back' },
      d: { handler: () => { if (!completed) handleDone(); }, label: 'done' },
      a: { handler: () => handleOpenChat(), label: 'ask' },
      gi: { handler: () => router.replace('/'), label: 'go to index' },
    };
  }, [router, completed, handleDone, handleOpenChat]);

  useKeyboardShortcuts(shortcuts);

  // Body overflow fix for browser-native scrolling
  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'auto';
    setTimeout(() => {
      (document.activeElement as HTMLElement)?.blur();
      document.body.focus();
    }, 100);
    const styleEl = document.createElement('style');
    styleEl.textContent = 'div:focus, body:focus { outline: none !important; }';
    document.head.appendChild(styleEl);
    return () => {
      document.body.style.overflow = prevOverflow;
      document.head.removeChild(styleEl);
    };
  }, []);

  // IntersectionObserver for TOC active heading (web only)
  useEffect(() => {
    if (Platform.OS !== 'web' || headings.length === 0) return;

    const timer = setTimeout(() => {
      if (observerRef.current) observerRef.current.disconnect();

      const observer = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            if (entry.isIntersecting) {
              const id = entry.target.getAttribute('id');
              if (id) {
                const idx = parseInt(id.replace('sh-', ''), 10);
                if (!isNaN(idx)) setActiveHeadingIndex(idx);
              }
            }
          }
        },
        { rootMargin: '-80px 0px -70% 0px', threshold: 0 },
      );

      for (let i = 0; i < headings.length; i++) {
        const el = document.getElementById(`sh-${i}`);
        if (el) observer.observe(el);
      }

      observerRef.current = observer;
    }, 300);

    return () => {
      clearTimeout(timer);
      if (observerRef.current) observerRef.current.disconnect();
    };
  }, [headings]);

  if (!synthesis) {
    return (
      <View style={s.container}>
        <View style={s.errorArea}>
          <Text style={s.errorText}>Synthesis not found</Text>
          <Pressable onPress={() => router.back()}>
            <Text style={s.topBarBackText}>{'\u2190'} Back</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  const claimCoverage = synthesis.total_claims_in_cluster > 0
    ? Math.round((synthesis.total_claims_covered / synthesis.total_claims_in_cluster) * 100)
    : 0;

  const isWeb = Platform.OS === 'web';

  // Normalize tensions to handle both string and object formats
  const tensions: Array<{ label?: string; description: string }> = (synthesis.tensions || []).map(
    (t: any) => typeof t === 'string' ? { description: t } : t
  );

  // --- Web: 2-column grid layout ---
  if (isWeb) {
    return (
      <View style={s.container}>
        {statusMessage && (
          <View style={s.statusToast}>
            <Text style={s.statusToastText}>{statusMessage}</Text>
          </View>
        )}

        <SynthesisTopBar
          completed={completed}
          onBack={() => router.back()}
          onDone={handleDone}
          onChat={() => handleOpenChat()}
        />

        <View style={webGridStyle as any}>
          {/* Content column */}
          <View style={s.contentColumn}>
            {/* Title */}
            <Text style={s.title}>{synthesis.label}</Text>
            <Text style={s.subtitle}>
              {synthesis.total_articles} articles {'\u00b7'} {synthesis.total_claims_covered} claims
              {claimCoverage > 0 ? ` \u00b7 ${claimCoverage}% of topic` : ''}
            </Text>

            <DoubleRule />

            {/* Body */}
            <View style={s.bodySection}>
              <MarkdownContent
                content={synthesis.synthesis_markdown}
                headingIdPrefix="sh"
              />
            </View>

            {/* Structured tensions at bottom */}
            {tensions.length > 0 && (
              <View style={s.tensionsFooter}>
                <Text style={s.sectionHeading}>
                  <Text style={{ color: fc.accent }}>{'\u2726'} </Text>
                  Points of Tension
                </Text>
                {tensions.map((t, i) => (
                  <TensionBlock
                    key={i}
                    content={t.description}
                    label={t.label ? `\u26A1 ${t.label}` : undefined}
                  />
                ))}
              </View>
            )}

            <View style={{ height: 80 }} />
          </View>

          {/* Sidebar */}
          <SynthesisSidebar
            headings={headings}
            activeHeadingIndex={activeHeadingIndex}
            sourceArticles={sourceArticles}
            synthesis={synthesis}
            onFollowUpResearch={handleFollowUpResearch}
            onFollowUpChat={(q) => handleOpenChat(q)}
          />
        </View>

        {showChat && SynthesisChat && (
          <SynthesisChat
            synthesis={synthesis}
            onClose={() => setShowChat(false)}
            initialQuestion={chatInitialQuestion}
          />
        )}
      </View>
    );
  }

  // --- Mobile: single-column layout ---
  return (
    <View style={s.container}>
      {statusMessage && (
        <View style={s.statusToast}>
          <Text style={s.statusToastText}>{statusMessage}</Text>
        </View>
      )}

      <ScrollView
        style={s.mobileScroll}
        contentContainerStyle={s.mobileScrollContent}
      >
        {/* Top bar */}
        <View style={s.mobileTopBar}>
          <Pressable onPress={() => router.back()} style={s.topBarBack}>
            <Text style={s.topBarBackText}>{'\u2190'} Back</Text>
          </Pressable>
          <View style={{ flex: 1 }} />
          <Pressable onPress={() => handleOpenChat()} style={s.topBarBtn}>
            <Text style={s.topBarBtnText}>Ask</Text>
          </Pressable>
          {!completed ? (
            <Pressable style={s.topBarDoneBtn} onPress={handleDone}>
              <Text style={s.topBarDoneBtnText}>Done</Text>
            </Pressable>
          ) : (
            <Text style={s.topBarCompleted}>{'\u2713'} Completed</Text>
          )}
        </View>

        {/* Title */}
        <Text style={s.title}>{synthesis.label}</Text>
        <Text style={s.subtitle}>
          {synthesis.total_articles} articles {'\u00b7'} {synthesis.total_claims_covered} claims
          {claimCoverage > 0 ? ` \u00b7 ${claimCoverage}% of topic` : ''}
        </Text>

        <DoubleRule />

        {/* Body */}
        <View style={s.bodySection}>
          <MarkdownContent content={synthesis.synthesis_markdown} />
        </View>

        {/* Structured tensions at bottom */}
        {tensions.length > 0 && (
          <View style={s.tensionsFooter}>
            <Text style={s.sectionHeading}>
              <Text style={{ color: fc.accent }}>{'\u2726'} </Text>
              Points of Tension
            </Text>
            {tensions.map((t, i) => (
              <TensionBlock
                key={i}
                content={t.description}
                label={t.label ? `\u26A1 ${t.label}` : undefined}
              />
            ))}
          </View>
        )}

        {/* Source articles (inline on mobile) */}
        <View style={s.mobileSourcesSection}>
          <Text style={s.sectionHeading}>
            <Text style={{ color: fc.accent }}>{'\u2726'} </Text>
            Sources
          </Text>
          {sourceArticles.map(({ id, coverage }) => (
            <MobileSourceRow key={id} articleId={id} coverage={coverage} />
          ))}
        </View>

        {/* Follow-up questions (mobile) */}
        {synthesis.follow_up_questions?.length > 0 && (
          <View style={s.mobileFollowUpSection}>
            <Text style={s.sectionHeading}>
              <Text style={{ color: fc.accent }}>{'\u2726'} </Text>
              Further Inquiry
            </Text>
            {synthesis.follow_up_questions.map((q: any, i: number) => (
              <View key={i} style={s.mobileFollowUpRow}>
                <Text style={s.mobileFollowUpQuestion}>{q.question}</Text>
                <View style={s.mobileFollowUpActions}>
                  <Pressable
                    onPress={async () => {
                      try {
                        await spawnTopicResearch(q.research_prompt, q.question, q.related_topics);
                        if (Platform.OS !== 'web') {
                          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
                        }
                        logEvent('synthesis_follow_up_dispatched', { question: q.question });
                        handleFollowUpResearch();
                      } catch (e) {
                        logEvent('synthesis_follow_up_error', { question: q.question, error: String(e) });
                      }
                    }}
                  >
                    <Text style={s.researchActionLink}>{'\u2197'} Research</Text>
                  </Pressable>
                  <Pressable onPress={() => handleOpenChat(q.question)}>
                    <Text style={s.researchActionLink}>{'\uD83D\uDCAC'} Chat</Text>
                  </Pressable>
                </View>
              </View>
            ))}
          </View>
        )}

        {/* Bottom done button */}
        {!completed && (
          <View style={s.mobileBottomDone}>
            <Pressable style={s.mobileBottomDoneBtn} onPress={handleDone}>
              <Text style={s.mobileBottomDoneBtnText}>
                Mark {synthesis.total_claims_covered} claims as read
              </Text>
            </Pressable>
          </View>
        )}

        <View style={{ height: 60 }} />
      </ScrollView>

      {showChat && SynthesisChat && (
        <SynthesisChat
          synthesis={synthesis}
          onClose={() => setShowChat(false)}
          initialQuestion={chatInitialQuestion}
        />
      )}
    </View>
  );
}

// --- Styles ---

const s = StyleSheet.create({
  container: {
    flex: Platform.OS === 'web' ? undefined as any : 1,
    backgroundColor: fc.bg,
    ...(Platform.OS === 'web' ? { outline: 'none' } as any : {}),
  },

  errorArea: {
    flex: 1,
    justifyContent: 'center' as const,
    alignItems: 'center' as const,
    padding: 32,
  },
  errorText: {
    fontFamily: fonts.displaySemiBold,
    fontSize: 20,
    color: fc.ink,
    marginBottom: 16,
    ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}),
  },

  // --- Top bar ---
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 10,
    paddingHorizontal: 20,
    maxWidth: 830,
    alignSelf: 'center' as const,
    width: '100%' as any,
    gap: 10,
    ...(Platform.OS === 'web' ? {
      position: 'sticky',
      top: 0,
      zIndex: 10,
      backgroundColor: fc.bg,
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderBottomColor: fc.line,
    } as any : {}),
  },
  mobileTopBar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    gap: 10,
  },
  topBarBack: {
    paddingVertical: 4,
  },
  topBarBackText: {
    fontFamily: fonts.reading,
    fontSize: 14,
    color: fc.muted,
  },
  topBarBtn: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderWidth: 1,
    borderColor: fc.line,
    borderRadius: 4,
  },
  topBarBtnText: {
    fontFamily: fonts.reading,
    fontSize: 13,
    color: fc.secondary,
  },
  topBarDoneBtn: {
    backgroundColor: fc.ink,
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 4,
  },
  topBarDoneBtnText: {
    fontFamily: fonts.reading,
    fontSize: 13,
    color: fc.bg,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  topBarCompleted: {
    fontFamily: fonts.reading,
    fontSize: 13,
    color: fc.green,
  },

  // --- Content column ---
  contentColumn: {
    paddingHorizontal: 28,
    paddingTop: 28,
    paddingRight: 36,
  },

  // --- Title section ---
  title: {
    fontFamily: fonts.displaySemiBold,
    fontSize: 30,
    lineHeight: 36,
    color: fc.ink,
    marginBottom: 8,
    ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}),
  },
  subtitle: {
    fontFamily: fonts.reading,
    fontSize: 13,
    color: fc.muted,
    marginBottom: 16,
  },

  // --- Section headings (Crimson Pro 19px with star prefix) ---
  sectionHeading: {
    fontFamily: fonts.reading,
    fontSize: 19,
    lineHeight: 26,
    color: fc.ink,
    marginBottom: 14,
    marginTop: 8,
  },

  // --- Body ---
  bodySection: {
    paddingTop: 24,
    paddingBottom: 8,
  },

  // --- Markdown rendering ---
  markdownText: {
    fontFamily: fonts.reading,
    fontSize: 17,
    lineHeight: 31,
    color: fc.body,
    marginBottom: 22,
  },
  markdownHeading: {
    fontFamily: fonts.reading,
    fontSize: 19,
    lineHeight: 26,
    color: fc.ink,
    marginTop: 36,
    marginBottom: 14,
  },
  markdownH2: {
    fontSize: 19,
  },
  markdownH3: {
    fontSize: 17,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  markdownHr: {
    height: 1,
    backgroundColor: fc.line,
    marginVertical: 20,
  },
  markdownLink: {
    color: fc.accent,
    textDecorationLine: 'underline' as const,
    textDecorationColor: 'rgba(139,37,0,0.15)' as any,
  },
  articleRef: {
    color: fc.accent,
    textDecorationLine: 'underline' as const,
    textDecorationStyle: 'dotted' as const,
    textDecorationColor: 'rgba(139,37,0,0.35)' as any,
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
    backgroundColor: fc.surface,
    fontSize: 14,
    paddingHorizontal: 4,
  },
  markdownList: {
    marginBottom: 22,
    paddingLeft: 4,
  },
  markdownListItem: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 5,
  },
  markdownBullet: {
    fontFamily: fonts.reading,
    fontSize: 17,
    color: fc.accent,
    width: 12,
    fontWeight: 'bold' as const,
  },
  markdownOrderedBullet: {
    fontFamily: fonts.reading,
    fontSize: 14,
    color: fc.muted,
    width: 20,
    textAlign: 'right' as const,
  },

  // --- Tension block ---
  tensionBlock: {
    borderLeftWidth: 2,
    borderLeftColor: fc.amber,
    paddingLeft: 12,
    marginBottom: 14,
  },
  tensionLabel: {
    fontFamily: fonts.readingMedium,
    fontSize: 13,
    color: fc.amber,
    marginBottom: 4,
    ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}),
  },
  tensionText: {
    fontFamily: fonts.readingItalic,
    fontSize: 16,
    lineHeight: 25,
    color: fc.secondary,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}),
  },
  tensionsFooter: {
    paddingTop: 16,
    paddingBottom: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: fc.line,
    marginTop: 16,
  },

  // --- Excerpt block ---
  excerptBlock: {
    borderLeftWidth: 2,
    borderLeftColor: fc.green,
    paddingLeft: 16,
    paddingVertical: 10,
    marginBottom: 20,
  },
  excerptLabel: {
    fontFamily: fonts.readingItalic,
    fontSize: 11,
    color: fc.muted,
    marginBottom: 4,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}),
  },
  excerptText: {
    fontFamily: fonts.readingItalic,
    fontSize: 16,
    lineHeight: 25,
    color: fc.secondary,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}),
  },

  // --- Detail section ---
  detailSection: {
    marginBottom: 16,
  },
  detailToggle: {
    paddingVertical: 6,
  },
  detailToggleText: {
    fontFamily: fonts.reading,
    fontSize: 13,
    color: fc.muted,
  },
  detailContent: {
    paddingLeft: 8,
    paddingTop: 4,
    borderLeftWidth: 1,
    borderLeftColor: fc.line,
  },

  // --- Code block ---
  codeBlock: {
    backgroundColor: 'rgba(237,234,222,0.5)',
    borderLeftWidth: 2,
    borderLeftColor: fc.line,
    padding: 16,
    paddingLeft: 18,
    marginBottom: 20,
  },
  codeText: {
    fontFamily: Platform.select({ web: "'JetBrains Mono', monospace", default: 'Courier' }),
    fontSize: 12.5,
    lineHeight: 20,
    color: fc.secondary,
  },

  // --- Table ---
  tableWrap: {
    marginBottom: 20,
    borderWidth: 1,
    borderColor: fc.line,
  },
  tableRow: {
    flexDirection: 'row',
    borderBottomWidth: 1,
    borderBottomColor: fc.line,
  },
  tableCell: {
    flex: 1,
    fontFamily: fonts.reading,
    fontSize: 14,
    lineHeight: 20,
    color: fc.body,
    padding: 8,
  },
  tableHeader: {
    fontFamily: fonts.readingMedium,
    backgroundColor: fc.surface,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },

  // --- Sidebar ---
  sidebar: {
    paddingTop: 28,
    paddingLeft: 20,
    paddingRight: 16,
    paddingBottom: 48,
    borderLeftWidth: 1,
    borderLeftColor: fc.line,
  },
  sidebarSection: {
    marginBottom: 24,
  },
  sidebarLabel: {
    fontFamily: fonts.readingItalic,
    fontSize: 12,
    color: fc.muted,
    marginBottom: 10,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}),
  },

  // TOC
  tocItem: {
    paddingVertical: 3,
  },
  tocText: {
    fontFamily: fonts.reading,
    fontSize: 12,
    lineHeight: 17,
    color: fc.secondary,
  },

  // Sidebar source articles
  sidebarSource: {
    marginBottom: 12,
    ...(Platform.OS === 'web' ? { cursor: 'pointer' } as any : {}),
  },
  sidebarSourceTitle: {
    fontFamily: fonts.reading,
    fontSize: 13,
    lineHeight: 18,
    color: fc.secondary,
  },
  sidebarCoverageBar: {
    height: 2,
    backgroundColor: fc.line,
    marginTop: 4,
    marginBottom: 2,
  },
  sidebarCoverageFill: {
    height: 2,
    backgroundColor: fc.green,
  },
  sidebarSourceMeta: {
    fontFamily: fonts.reading,
    fontSize: 9,
    color: fc.muted,
  },

  // Research prompts
  researchPromptItem: {
    marginBottom: 14,
  },
  researchPromptText: {
    fontFamily: fonts.readingItalic,
    fontSize: 12,
    lineHeight: 17,
    color: fc.secondary,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}),
  },
  researchPromptActions: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 4,
  },
  researchActionLink: {
    fontFamily: fonts.reading,
    fontSize: 10,
    color: fc.accent,
  },
  researchDispatched: {
    fontFamily: fonts.reading,
    fontSize: 10,
    color: fc.green,
  },

  // --- Mobile styles ---
  mobileScroll: {
    flex: 1,
    paddingHorizontal: 16,
  },
  mobileScrollContent: {
    paddingBottom: 40,
  },
  mobileSourcesSection: {
    paddingTop: 16,
    paddingBottom: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: fc.line,
  },
  mobileSourceRow: {
    paddingVertical: 10,
    paddingHorizontal: 4,
    minHeight: 44,
  },
  mobileSourceTitle: {
    fontFamily: fonts.reading,
    fontSize: 14,
    lineHeight: 20,
    color: fc.ink,
  },
  mobileCoverageBar: {
    height: 2,
    backgroundColor: fc.line,
    marginTop: 6,
    marginBottom: 2,
  },
  mobileCoverageFill: {
    height: 2,
    backgroundColor: fc.green,
  },
  mobileSourceMeta: {
    fontFamily: fonts.reading,
    fontSize: 11,
    color: fc.muted,
    marginTop: 2,
  },
  mobileFollowUpSection: {
    paddingTop: 16,
    paddingBottom: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: fc.line,
  },
  mobileFollowUpRow: {
    paddingVertical: 10,
    paddingHorizontal: 4,
    minHeight: 44,
  },
  mobileFollowUpQuestion: {
    fontFamily: fonts.reading,
    fontSize: 14,
    lineHeight: 21,
    color: fc.body,
    marginBottom: 4,
  },
  mobileFollowUpActions: {
    flexDirection: 'row',
    gap: 16,
  },
  mobileBottomDone: {
    alignItems: 'center' as const,
    paddingVertical: 24,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: fc.line,
    marginTop: 16,
  },
  mobileBottomDoneBtn: {
    backgroundColor: fc.ink,
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 4,
    alignItems: 'center' as const,
  },
  mobileBottomDoneBtnText: {
    fontFamily: fonts.reading,
    fontSize: 14,
    color: fc.bg,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },

  // --- Status toast ---
  statusToast: {
    position: 'absolute' as const,
    top: 60,
    alignSelf: 'center' as const,
    backgroundColor: fc.ink,
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 4,
    zIndex: 200,
  },
  statusToastText: {
    fontFamily: fonts.reading,
    fontSize: 13,
    color: fc.bg,
  },
});
