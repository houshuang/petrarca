import { useState, useEffect, useRef, useCallback } from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable, Linking, Dimensions } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { getArticleById, getReadingState, updateReadingState, addSignal } from '../data/store';
import { ReadingDepth, ArticleSection } from '../data/types';
import { logEvent } from '../data/logger';

const { width } = Dimensions.get('window');

const DEPTHS: ReadingDepth[] = ['summary', 'claims', 'sections', 'full'];
const DEPTH_LABELS: Record<string, string> = {
  summary: 'Summary',
  claims: 'Claims',
  sections: 'Sections',
  full: 'Full',
};

function DepthIndicator({ depth, onChangeDepth, sectionCount }: {
  depth: ReadingDepth;
  onChangeDepth: (d: ReadingDepth) => void;
  sectionCount: number;
}) {
  return (
    <View style={styles.depthBar}>
      {DEPTHS.map(d => {
        const active = d === depth;
        const idx = DEPTHS.indexOf(d);
        const currentIdx = DEPTHS.indexOf(depth);
        const reached = idx <= currentIdx;

        // Skip sections tab if article has <= 1 section
        if (d === 'sections' && sectionCount <= 1) return null;

        return (
          <Pressable
            key={d}
            style={[styles.depthTab, active && styles.depthTabActive]}
            onPress={() => onChangeDepth(d)}
          >
            <Text style={[
              styles.depthTabText,
              active && styles.depthTabTextActive,
              reached && !active && styles.depthTabTextReached,
            ]}>
              {DEPTH_LABELS[d]}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

function MarkdownText({ content }: { content: string }) {
  if (!content) return null;

  const paragraphs = content.split('\n\n').filter(Boolean);

  return (
    <View>
      {paragraphs.map((p, i) => {
        const trimmed = p.trim();

        // Heading
        const headingMatch = trimmed.match(/^(#{1,3})\s+(.+)$/m);
        if (headingMatch) {
          const level = headingMatch[1].length;
          return (
            <Text key={i} style={[
              styles.markdownHeading,
              level === 1 && { fontSize: 20 },
              level === 2 && { fontSize: 18 },
              level === 3 && { fontSize: 16 },
            ]}>
              {headingMatch[2]}
            </Text>
          );
        }

        // List item
        if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
          const items = trimmed.split('\n').filter(l => l.trim().startsWith('- ') || l.trim().startsWith('* '));
          return (
            <View key={i} style={styles.markdownList}>
              {items.map((item, j) => (
                <View key={j} style={styles.markdownListItem}>
                  <Text style={styles.markdownBullet}>•</Text>
                  <Text style={styles.markdownText}>{item.replace(/^[-*]\s+/, '')}</Text>
                </View>
              ))}
            </View>
          );
        }

        // Code block
        if (trimmed.startsWith('```')) {
          const code = trimmed.replace(/^```\w*\n?/, '').replace(/\n?```$/, '');
          return (
            <View key={i} style={styles.codeBlock}>
              <Text style={styles.codeText}>{code}</Text>
            </View>
          );
        }

        // Regular paragraph
        return (
          <Text key={i} style={styles.markdownText}>{trimmed}</Text>
        );
      })}
    </View>
  );
}

function SectionView({ section, index, expanded, onToggle }: {
  section: ArticleSection;
  index: number;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <View style={styles.sectionCard}>
      <Pressable onPress={onToggle} style={styles.sectionHeader}>
        <View style={{ flex: 1 }}>
          <Text style={styles.sectionHeading}>{section.heading}</Text>
          {!expanded && section.summary && (
            <Text style={styles.sectionSummary} numberOfLines={2}>{section.summary}</Text>
          )}
        </View>
        <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={18} color="#64748b" />
      </Pressable>

      {expanded && (
        <View style={styles.sectionContent}>
          {section.key_claims.length > 0 && (
            <View style={styles.sectionClaims}>
              {section.key_claims.map((c, i) => (
                <View key={i} style={styles.claimRow}>
                  <Text style={styles.claimBullet}>→</Text>
                  <Text style={styles.claimText}>{c}</Text>
                </View>
              ))}
            </View>
          )}
          <MarkdownText content={section.content} />
        </View>
      )}
    </View>
  );
}

export default function ReaderScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const article = getArticleById(id || '');
  const [depth, setDepth] = useState<ReadingDepth>('summary');
  const [expandedSections, setExpandedSections] = useState<Set<number>>(new Set());
  const enterTime = useRef(Date.now());
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    if (!article) return;
    const state = getReadingState(article.id);
    if (state.depth !== 'unread') {
      setDepth(state.depth);
    } else {
      updateReadingState(article.id, { depth: 'summary', started_at: Date.now(), last_read_at: Date.now() });
    }
    logEvent('reader_open', { article_id: article.id, title: article.title, previous_depth: state.depth });

    return () => {
      const elapsed = Date.now() - enterTime.current;
      const currentState = getReadingState(article.id);
      updateReadingState(article.id, {
        time_spent_ms: (currentState.time_spent_ms || 0) + elapsed,
        last_read_at: Date.now(),
      });
      logEvent('reader_close', { article_id: article.id, time_spent_ms: elapsed, depth });
    };
  }, []);

  const changeDepth = useCallback((newDepth: ReadingDepth) => {
    if (!article) return;
    logEvent('reader_depth_change', { article_id: article.id, from: depth, to: newDepth });
    setDepth(newDepth);
    updateReadingState(article.id, { depth: newDepth, last_read_at: Date.now() });
    scrollRef.current?.scrollTo({ y: 0, animated: true });
  }, [article, depth]);

  const toggleSection = useCallback((index: number) => {
    if (!article) return;
    setExpandedSections(prev => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      logEvent('reader_section_toggle', {
        article_id: article.id,
        section_index: index,
        heading: article.sections[index]?.heading,
        expanded: next.has(index),
      });
      return next;
    });
    updateReadingState(article.id, { current_section_index: index });
  }, [article]);

  if (!article) {
    return (
      <View style={styles.container}>
        <Text style={styles.errorText}>Article not found</Text>
        <Pressable onPress={() => router.back()}>
          <Text style={styles.backLink}>← Back to feed</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Top bar */}
      <View style={styles.topBar}>
        <Pressable onPress={() => router.back()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={22} color="#f8fafc" />
        </Pressable>
        <View style={{ flex: 1 }} />
        <Pressable onPress={() => {
          logEvent('reader_open_source', { article_id: article.id, url: article.source_url });
          Linking.openURL(article.source_url);
        }}>
          <Ionicons name="open-outline" size={20} color="#60a5fa" />
        </Pressable>
      </View>

      {/* Depth indicator */}
      <DepthIndicator
        depth={depth}
        onChangeDepth={changeDepth}
        sectionCount={article.sections.length}
      />

      <ScrollView
        ref={scrollRef}
        style={styles.scroll}
        showsVerticalScrollIndicator={false}
      >
        {/* Always show title */}
        <Text style={styles.articleTitle}>{article.title}</Text>
        <View style={styles.metaRow}>
          {article.author ? <Text style={styles.metaText}>{article.author}</Text> : null}
          <Text style={styles.metaText}>{article.hostname}</Text>
          {article.date ? <Text style={styles.metaText}>{article.date}</Text> : null}
          <Text style={styles.metaText}>{article.estimated_read_minutes} min · {article.word_count} words</Text>
        </View>

        {/* Topics */}
        <View style={styles.topicsRow}>
          {article.topics.map(t => (
            <View key={t} style={styles.topicPill}>
              <Text style={styles.topicText}>{t}</Text>
            </View>
          ))}
        </View>

        {/* SUMMARY depth */}
        {depth === 'summary' && (
          <View style={styles.depthContent}>
            <Text style={styles.fullSummary}>{article.full_summary}</Text>

            {article.key_claims.length > 0 && (
              <View style={styles.previewClaims}>
                <Text style={styles.previewLabel}>{article.key_claims.length} key claims</Text>
              </View>
            )}

            <Pressable style={styles.goDeeper} onPress={() => changeDepth('claims')}>
              <Text style={styles.goDeeperText}>Go deeper</Text>
              <Ionicons name="arrow-forward" size={16} color="#60a5fa" />
            </Pressable>
          </View>
        )}

        {/* CLAIMS depth */}
        {depth === 'claims' && (
          <View style={styles.depthContent}>
            <Text style={styles.summaryCollapsed} numberOfLines={2}>{article.full_summary}</Text>

            <Text style={styles.claimsHeader}>Key Claims</Text>
            {article.key_claims.map((claim, i) => (
              <View key={i} style={styles.claimCard}>
                <Text style={styles.claimCardText}>{claim}</Text>
                <View style={styles.claimActions}>
                  <Pressable
                    style={styles.claimBtn}
                    onPress={() => {
                      addSignal({ article_id: article.id, signal: 'knew_it', timestamp: Date.now(), depth: 'claims' });
                      logEvent('claim_signal', { article_id: article.id, claim_index: i, signal: 'knew_it' });
                    }}
                  >
                    <Text style={styles.claimBtnText}>Knew this</Text>
                  </Pressable>
                  <Pressable
                    style={[styles.claimBtn, styles.claimBtnNew]}
                    onPress={() => {
                      addSignal({ article_id: article.id, signal: 'interesting', timestamp: Date.now(), depth: 'claims' });
                      logEvent('claim_signal', { article_id: article.id, claim_index: i, signal: 'interesting' });
                    }}
                  >
                    <Text style={[styles.claimBtnText, { color: '#10b981' }]}>New to me</Text>
                  </Pressable>
                </View>
              </View>
            ))}

            <Pressable style={styles.goDeeper} onPress={() => changeDepth(article.sections.length > 1 ? 'sections' : 'full')}>
              <Text style={styles.goDeeperText}>Read more</Text>
              <Ionicons name="arrow-forward" size={16} color="#60a5fa" />
            </Pressable>
          </View>
        )}

        {/* SECTIONS depth */}
        {depth === 'sections' && (
          <View style={styles.depthContent}>
            {article.sections.map((section, i) => (
              <SectionView
                key={i}
                section={section}
                index={i}
                expanded={expandedSections.has(i)}
                onToggle={() => toggleSection(i)}
              />
            ))}

            <Pressable style={styles.goDeeper} onPress={() => changeDepth('full')}>
              <Text style={styles.goDeeperText}>Read full article</Text>
              <Ionicons name="arrow-forward" size={16} color="#60a5fa" />
            </Pressable>
          </View>
        )}

        {/* FULL depth */}
        {depth === 'full' && (
          <View style={styles.depthContent}>
            <MarkdownText content={article.content_markdown} />
          </View>
        )}

        {/* Source attribution */}
        {article.sources.length > 0 && article.sources[0].tweet_text && (
          <View style={styles.sourceBox}>
            <Text style={styles.sourceLabel}>
              Found via @{article.sources[0].author_username}
            </Text>
            <Text style={styles.sourceText} numberOfLines={3}>
              {article.sources[0].tweet_text}
            </Text>
          </View>
        )}

        <View style={{ height: 60 }} />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f172a' },
  topBar: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingTop: 56, paddingBottom: 8, gap: 12 },
  backButton: { padding: 4 },
  scroll: { flex: 1, paddingHorizontal: 16 },
  errorText: { color: '#ef4444', fontSize: 16, textAlign: 'center', marginTop: 100 },
  backLink: { color: '#60a5fa', fontSize: 14, textAlign: 'center', marginTop: 12 },

  // Depth bar
  depthBar: { flexDirection: 'row', paddingHorizontal: 16, paddingBottom: 8, gap: 4 },
  depthTab: { paddingHorizontal: 14, paddingVertical: 6, borderRadius: 16, backgroundColor: '#1e293b' },
  depthTabActive: { backgroundColor: '#2563eb' },
  depthTabText: { color: '#475569', fontSize: 13, fontWeight: '500' },
  depthTabTextActive: { color: '#f8fafc' },
  depthTabTextReached: { color: '#94a3b8' },

  // Article header
  articleTitle: { color: '#f8fafc', fontSize: 24, fontWeight: '700', lineHeight: 32, marginBottom: 8 },
  metaRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 8 },
  metaText: { color: '#64748b', fontSize: 13 },
  topicsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 16 },
  topicPill: { backgroundColor: '#334155', paddingHorizontal: 10, paddingVertical: 3, borderRadius: 12 },
  topicText: { color: '#94a3b8', fontSize: 12 },

  // Depth content
  depthContent: { marginBottom: 16 },

  // Summary depth
  fullSummary: { color: '#e2e8f0', fontSize: 16, lineHeight: 26, marginBottom: 16 },
  previewClaims: { backgroundColor: '#1e293b', borderRadius: 8, padding: 12, marginBottom: 16 },
  previewLabel: { color: '#94a3b8', fontSize: 13 },

  // Claims depth
  summaryCollapsed: { color: '#94a3b8', fontSize: 14, lineHeight: 20, marginBottom: 16 },
  claimsHeader: { color: '#f8fafc', fontSize: 16, fontWeight: '600', marginBottom: 12 },
  claimCard: { backgroundColor: '#1e293b', borderRadius: 10, padding: 14, marginBottom: 8 },
  claimCardText: { color: '#e2e8f0', fontSize: 15, lineHeight: 22, marginBottom: 8 },
  claimActions: { flexDirection: 'row', gap: 8 },
  claimBtn: { paddingHorizontal: 12, paddingVertical: 5, borderRadius: 8, backgroundColor: '#334155' },
  claimBtnNew: { borderColor: '#10b981', borderWidth: 1, backgroundColor: 'transparent' },
  claimBtnText: { color: '#94a3b8', fontSize: 12 },

  // Sections depth
  sectionCard: { backgroundColor: '#1e293b', borderRadius: 10, marginBottom: 8, overflow: 'hidden' },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', padding: 14, gap: 8 },
  sectionHeading: { color: '#f8fafc', fontSize: 15, fontWeight: '600' },
  sectionSummary: { color: '#94a3b8', fontSize: 13, lineHeight: 18, marginTop: 2 },
  sectionContent: { paddingHorizontal: 14, paddingBottom: 14 },
  sectionClaims: { marginBottom: 12, paddingLeft: 4 },
  claimRow: { flexDirection: 'row', marginBottom: 4 },
  claimBullet: { color: '#60a5fa', marginRight: 8, fontSize: 13 },
  claimText: { color: '#94a3b8', fontSize: 13, lineHeight: 18, flex: 1 },

  // Go deeper
  goDeeper: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 14, marginTop: 8 },
  goDeeperText: { color: '#60a5fa', fontSize: 15, fontWeight: '500' },

  // Markdown rendering
  markdownHeading: { color: '#f8fafc', fontWeight: '700', marginTop: 16, marginBottom: 8 },
  markdownText: { color: '#cbd5e1', fontSize: 15, lineHeight: 24, marginBottom: 12 },
  markdownList: { marginBottom: 12 },
  markdownListItem: { flexDirection: 'row', marginBottom: 4, paddingRight: 8 },
  markdownBullet: { color: '#60a5fa', marginRight: 8, fontSize: 14 },
  codeBlock: { backgroundColor: '#0f172a', borderRadius: 8, padding: 12, marginBottom: 12 },
  codeText: { color: '#94a3b8', fontSize: 13, fontFamily: 'monospace' },

  // Source
  sourceBox: { backgroundColor: '#1e293b', borderRadius: 10, padding: 14, marginTop: 16, borderLeftWidth: 3, borderLeftColor: '#334155' },
  sourceLabel: { color: '#60a5fa', fontSize: 12, marginBottom: 4 },
  sourceText: { color: '#64748b', fontSize: 13, lineHeight: 18 },
});
