import { useState, useEffect, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput,
  KeyboardAvoidingView, Platform, ViewStyle,
} from 'react-native';
import { useRouter } from 'expo-router';
import {
  getReviewQueue, submitReview, getConceptReview,
  getArticleById, getConcepts, getStats, getVoiceNoteById,
  getMatchingClaims,
} from '../data/store';
import { Concept, ConceptReview, ReviewRating } from '../data/types';
import { logEvent } from '../data/logger';
import { colors, fonts, type } from '../design/tokens';

// --- Prompt Tiers ---

type PromptTier = 'first_encounter' | 'building_familiarity' | 'cross_referencing' | 'mastery_check';

function getPromptTier(engagementCount: number): PromptTier {
  if (engagementCount === 0) return 'first_encounter';
  if (engagementCount <= 2) return 'building_familiarity';
  if (engagementCount <= 4) return 'cross_referencing';
  return 'mastery_check';
}

function getPromptText(
  tier: PromptTier,
  sourceArticles: Array<{ id: string; title: string }>,
): string {
  switch (tier) {
    case 'first_encounter':
      return sourceArticles.length === 1
        ? `You recently encountered this in "${sourceArticles[0].title}". What stands out?`
        : 'You recently encountered this. What stands out?';
    case 'building_familiarity':
      return sourceArticles.length >= 2
        ? `You've seen this in "${sourceArticles[0].title}" and ${sourceArticles.length - 1} other ${sourceArticles.length - 1 === 1 ? 'article' : 'articles'}. How has your understanding evolved?`
        : 'How does this connect to what you\'ve been reading?';
    case 'cross_referencing':
      return `You've seen this across ${sourceArticles.length} article${sourceArticles.length !== 1 ? 's' : ''}. What patterns do you notice?`;
    case 'mastery_check':
      return 'Could you explain this to someone? What would you emphasize?';
  }
}

const RATING_LABELS: Record<number, { emoji: string; label: string }> = {
  1: { emoji: '\u2753', label: 'Confused' },
  2: { emoji: '\u{1F324}\uFE0F', label: 'Fuzzy' },
  3: { emoji: '\u2705', label: 'Solid' },
  4: { emoji: '\u{1F393}', label: 'Expert' },
};

function daysAgoText(dueAt: number, stabilityDays: number): string {
  const lastReviewedAt = dueAt - stabilityDays * 86400000;
  const daysAgo = Math.round((Date.now() - lastReviewedAt) / 86400000);
  if (daysAgo <= 0) return 'Today';
  if (daysAgo === 1) return '1 day ago';
  return `${daysAgo} days ago`;
}

const RATING_CONFIG = [
  { rating: 1 as const, label: 'Again', hint: '<1d', borderColor: colors.ratingAgainBorder, textColor: colors.ratingAgain },
  { rating: 2 as const, label: 'Hard', hint: '2d', borderColor: colors.ratingHardBorder, textColor: colors.ratingHard },
  { rating: 3 as const, label: 'Good', hint: '8d', borderColor: colors.ratingGoodBorder, textColor: colors.ratingGood },
  { rating: 4 as const, label: 'Easy', hint: '21d', borderColor: colors.ratingEasyBorder, textColor: colors.ratingEasy },
] as const;

// --- Review Card ---

function ReviewCard({ concept, review, reason, onComplete }: {
  concept: Concept;
  review: ConceptReview;
  reason: string;
  onComplete: () => void;
}) {
  const router = useRouter();
  const [phase, setPhase] = useState<'prompt' | 'respond' | 'rate'>('prompt');
  const [noteText, setNoteText] = useState('');

  const sourceArticles = concept.source_article_ids
    .map(id => getArticleById(id))
    .filter(Boolean);

  const promptTier = getPromptTier(review.engagement_count);

  // Log prompt tier on mount
  useEffect(() => {
    logEvent('review_prompt_tier', {
      concept_id: concept.id,
      tier: promptTier,
      engagement_count: review.engagement_count,
    });
  }, [concept.id]);

  const matchingClaims = getMatchingClaims(concept.id, 3);

  const recentNotes = review.notes
    .filter(n => !n.voice_note_id)
    .slice(-3)
    .reverse();

  const handleRate = useCallback((rating: ReviewRating) => {
    submitReview(concept.id, rating, noteText || undefined);
    onComplete();
  }, [concept.id, noteText, onComplete]);

  return (
    <ScrollView style={styles.cardScroll} showsVerticalScrollIndicator={false}>
      <View style={styles.card}>
        {/* Topic tag */}
        <Text style={styles.topicTag}>{concept.topic}</Text>

        {/* Concept text */}
        <Text style={styles.conceptText}>{concept.text}</Text>

        {/* Review history info */}
        <View style={styles.statsRow}>
          {review.engagement_count > 0 ? (
            <Text style={styles.statText}>
              Review #{review.engagement_count + 1} · Last reviewed {daysAgoText(review.due_at, review.stability_days)}
              {review.understanding > 0 && RATING_LABELS[review.understanding]
                ? ` · Previous: ${RATING_LABELS[review.understanding].label}`
                : ''}
            </Text>
          ) : (
            <Text style={styles.statText}>First review</Text>
          )}
        </View>

        {/* Recent notes */}
        {recentNotes.length > 0 && (
          <View style={{ marginBottom: 16 }}>
            {recentNotes.map(note => (
              <View key={note.id} style={styles.noteBox}>
                <Text style={styles.noteText}>{note.text}</Text>
                <Text style={styles.noteDate}>
                  {new Date(note.created_at).toLocaleDateString()}
                </Text>
              </View>
            ))}
          </View>
        )}

        {/* Voice note transcripts linked to this concept */}
        {(() => {
          const voiceNotes = review.notes
            .filter(n => n.voice_note_id)
            .map(n => ({ note: n, voiceNote: getVoiceNoteById(n.voice_note_id!) }))
            .filter((v): v is { note: typeof review.notes[0]; voiceNote: NonNullable<ReturnType<typeof getVoiceNoteById>> } => !!v.voiceNote?.transcript);
          if (voiceNotes.length === 0) return null;
          return voiceNotes.map(({ note, voiceNote }) => (
            <View key={note.id} style={styles.voiceNoteBox}>
              <Text style={styles.voiceNoteLabel}>
                Voice note · {Math.round(voiceNote.duration_ms / 1000)}s · {new Date(voiceNote.recorded_at).toLocaleDateString()}
              </Text>
              <Text style={styles.noteText}>{voiceNote.transcript}</Text>
            </View>
          ));
        })()}

        {/* Matching claims from articles */}
        {matchingClaims.length > 0 && (
          <View style={styles.claimsSection}>
            <Text style={styles.claimsLabel}>Related claims</Text>
            {matchingClaims.map((match, i) => (
              <Pressable
                key={i}
                style={styles.claimBox}
                onPress={() => {
                  logEvent('review_claim_tap', { concept_id: concept.id, article_id: match.articleId });
                  router.push({ pathname: '/reader', params: { id: match.articleId } });
                }}
              >
                <Text style={styles.claimText}>{match.claim}</Text>
                <Text style={styles.claimSource}>from {match.articleTitle}</Text>
              </Pressable>
            ))}
          </View>
        )}

        {/* Source articles */}
        {sourceArticles.length > 0 && (
          <View style={styles.sourcesSection}>
            <Text style={styles.sourcesLabel}>From:</Text>
            {sourceArticles.slice(0, 3).map(a => a && (
              <Pressable
                key={a.id}
                style={styles.sourceLink}
                onPress={() => {
                  logEvent('review_source_tap', { concept_id: concept.id, article_id: a.id });
                  router.push({ pathname: '/reader', params: { id: a.id } });
                }}
              >
                <Text style={styles.sourceLinkText} numberOfLines={1}>{a.title}</Text>
              </Pressable>
            ))}
          </View>
        )}

        {/* Phase: Prompt */}
        {phase === 'prompt' && (
          <View style={styles.phaseSection}>
            <Text style={styles.promptText}>
              {getPromptText(promptTier, sourceArticles as Array<{ id: string; title: string }>)}
            </Text>
            <View style={styles.promptActions}>
              <Pressable
                style={({ pressed }: any) => [
                  styles.actionBtn,
                  pressed && { opacity: 0.7 },
                ] as ViewStyle[]}
                onPress={() => setPhase('respond')}
              >
                <Text style={styles.actionBtnText}>Add a note</Text>
              </Pressable>
              <Pressable
                style={({ pressed }: any) => [
                  styles.actionBtn,
                  styles.actionBtnPrimary,
                  pressed && { opacity: 0.7 },
                ] as ViewStyle[]}
                onPress={() => setPhase('rate')}
              >
                <Text style={[styles.actionBtnText, { color: colors.rubric }]}>Just rate</Text>
              </Pressable>
            </View>
          </View>
        )}

        {/* Phase: Respond with note */}
        {phase === 'respond' && (
          <View style={styles.phaseSection}>
            <TextInput
              style={styles.noteInput}
              placeholder="Your thoughts on this concept..."
              placeholderTextColor={colors.textMuted}
              multiline
              value={noteText}
              onChangeText={setNoteText}
              autoFocus
            />
            <Pressable
              style={[styles.submitBtn, !noteText && styles.submitBtnDisabled]}
              onPress={() => { if (noteText) setPhase('rate'); }}
            >
              <Text style={styles.submitBtnText}>Continue to rating</Text>
            </Pressable>
          </View>
        )}

        {/* Phase: Rate understanding */}
        {phase === 'rate' && (
          <View style={styles.phaseSection}>
            <Text style={styles.ratePrompt}>How well do you understand this?</Text>
            <View style={styles.ratingGrid}>
              {RATING_CONFIG.map(({ rating, label, hint, borderColor, textColor }) => (
                <Pressable
                  key={rating}
                  style={({ pressed }: any) => [
                    styles.ratingBtn,
                    { borderColor },
                    pressed && { borderWidth: 2, backgroundColor: `${textColor}1a` },
                  ] as ViewStyle[]}
                  onPress={() => handleRate(rating)}
                >
                  <Text style={[styles.ratingLabel, { color: textColor }]}>{label}</Text>
                  <Text style={styles.ratingHint}>{hint}</Text>
                </Pressable>
              ))}
            </View>
          </View>
        )}
      </View>
    </ScrollView>
  );
}

// --- Main Review Screen ---

const SESSION_CAP = 7;

export default function ReviewScreen() {
  const [, forceUpdate] = useState(0);
  const fullQueue = getReviewQueue(50);
  const queue = fullQueue.slice(0, SESSION_CAP);
  const [currentIndex, setCurrentIndex] = useState(0);
  const stats = getStats();

  const totalDueCount = fullQueue.length;
  const allConcepts = getConcepts();
  const reviewedCount = [...new Set(
    allConcepts
      .map(c => getConceptReview(c.id))
      .filter(r => r && r.engagement_count > 0)
  )].length;

  const handleComplete = useCallback(() => {
    setCurrentIndex(i => i + 1);
    forceUpdate(n => n + 1);
  }, []);

  // No concepts at all
  if (allConcepts.length === 0) {
    return (
      <View style={styles.container}>
        <View style={styles.header}>
          <Text style={styles.title}>Review</Text>
          <Text style={styles.subtitle}>Spaced attention</Text>
          <View style={styles.doubleRule}>
            <View style={styles.ruleThick} />
            <View style={styles.ruleThin} />
          </View>
        </View>
        <View style={styles.emptyState}>
          <Text style={styles.emptyTitle}>No concepts yet</Text>
          <Text style={styles.emptySubtitle}>
            Start reading and signaling on claims to build your knowledge map
          </Text>
        </View>
      </View>
    );
  }

  // How many were not shown because of the cap
  const extraDue = Math.max(0, totalDueCount - SESSION_CAP);

  // Queue complete
  if (currentIndex >= queue.length || queue.length === 0) {
    return (
      <View style={styles.container}>
        <View style={styles.header}>
          <Text style={styles.title}>Review</Text>
          <Text style={styles.subtitle}>Spaced attention</Text>
          <View style={styles.doubleRule}>
            <View style={styles.ruleThick} />
            <View style={styles.ruleThin} />
          </View>
        </View>
        <ScrollView style={styles.scroll} showsVerticalScrollIndicator={false}>
          <View style={styles.completedSection}>
            <Text style={styles.completedTitle}>
              {totalDueCount === 0 ? 'Nothing due right now' : 'Done for now'}
            </Text>
            <Text style={styles.completedSubtitle}>
              {stats.knownConcepts + stats.encounteredConcepts} of {allConcepts.length} concepts engaged
              {reviewedCount > 0 ? ` · ${reviewedCount} reviewed` : ''}
            </Text>

            {extraDue > 0 && (
              <Text style={styles.completedHint}>
                {extraDue} more available whenever you're ready
              </Text>
            )}

            {totalDueCount === 0 && (
              <Text style={styles.completedHint}>
                Read more articles and signal on claims to add concepts to your review queue
              </Text>
            )}

            <Pressable
              style={styles.refreshQueueBtn}
              onPress={() => {
                setCurrentIndex(0);
                forceUpdate(n => n + 1);
              }}
            >
              <Text style={styles.refreshQueueText}>
                {extraDue > 0 ? 'Continue reviewing' : 'Check again'}
              </Text>
            </Pressable>
          </View>

          {/* Topic overview */}
          <View style={styles.topicOverview}>
            <Text style={styles.overviewTitle}>Your Knowledge</Text>
            {(() => {
              const topicCounts = new Map<string, { total: number; engaged: number }>();
              for (const c of allConcepts) {
                if (!topicCounts.has(c.topic)) topicCounts.set(c.topic, { total: 0, engaged: 0 });
                const entry = topicCounts.get(c.topic)!;
                entry.total++;
                const review = getConceptReview(c.id);
                if (review && review.engagement_count > 0) entry.engaged++;
              }
              return [...topicCounts.entries()]
                .sort((a, b) => b[1].total - a[1].total)
                .slice(0, 10)
                .map(([topic, counts]) => (
                  <View key={topic} style={styles.topicOverviewRow}>
                    <Text style={styles.topicOverviewName} numberOfLines={1}>{topic}</Text>
                    <View style={styles.topicOverviewBar}>
                      <View style={[
                        styles.topicOverviewFill,
                        { width: `${counts.total > 0 ? (counts.engaged / counts.total) * 100 : 0}%` },
                      ]} />
                    </View>
                    <Text style={styles.topicOverviewCount}>{counts.engaged}/{counts.total}</Text>
                  </View>
                ));
            })()}
          </View>
        </ScrollView>
      </View>
    );
  }

  const current = queue[currentIndex];

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerRow}>
          <View>
            <Text style={styles.title}>Review</Text>
            <Text style={styles.subtitle}>
              Spaced attention — {currentIndex + 1} of {queue.length}
            </Text>
          </View>
          <Pressable onPress={() => {
            logEvent('review_session_end_early', {
              reviewed: currentIndex,
              session_size: queue.length,
              total_due: totalDueCount,
            });
            setCurrentIndex(queue.length);
          }}>
            <Text style={styles.skipAllText}>Done</Text>
          </Pressable>
        </View>
        <View style={styles.doubleRule}>
          <View style={styles.ruleThick} />
          <View style={styles.ruleThin} />
        </View>
      </View>

      <ReviewCard
        key={current.concept.id}
        concept={current.concept}
        review={current.review}
        reason={current.reason}
        onComplete={handleComplete}
      />
    </KeyboardAvoidingView>
  );
}

// --- Styles ---

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.parchment },
  scroll: { flex: 1 },
  cardScroll: { flex: 1, paddingHorizontal: 20 },

  // Header
  header: {
    paddingHorizontal: 20,
    paddingTop: 16,
  },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  title: {
    ...type.screenTitle,
    color: colors.ink,
  },
  subtitle: {
    ...type.screenSubtitle,
    color: colors.textMuted,
    marginTop: 2,
  },
  doubleRule: {
    marginTop: 12,
    marginBottom: 4,
    gap: 5,
  },
  ruleThick: {
    height: 2,
    backgroundColor: colors.ink,
  },
  ruleThin: {
    height: 1,
    backgroundColor: colors.ink,
  },
  skipAllText: {
    ...type.metadata,
    color: colors.textMuted,
    marginTop: 6,
  },

  // Review card
  card: { paddingTop: 20, paddingBottom: 40 },
  topicTag: {
    ...type.topicTag,
    color: colors.rubric,
    marginBottom: 10,
  },
  conceptText: {
    ...type.reviewConcept,
    color: colors.textPrimary,
    marginBottom: 12,
  },
  statsRow: { marginBottom: 16 },
  statText: {
    ...type.metadata,
    color: colors.textMuted,
  },

  // Notes
  noteBox: {
    borderLeftWidth: 2,
    borderLeftColor: colors.rubric,
    paddingLeft: 12,
    marginBottom: 10,
  },
  noteText: {
    fontFamily: fonts.readingItalic,
    fontSize: 13,
    lineHeight: 19,
    color: colors.textSecondary,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}),
  },
  noteDate: {
    ...type.metadata,
    color: colors.textMuted,
    marginTop: 4,
  },
  voiceNoteBox: {
    borderLeftWidth: 2,
    borderLeftColor: colors.rubric,
    paddingLeft: 12,
    marginBottom: 16,
  },
  voiceNoteLabel: {
    ...type.metadata,
    color: colors.textMuted,
    marginBottom: 4,
  },

  // Claims
  claimsSection: { marginBottom: 16 },
  claimsLabel: {
    ...type.sectionHead,
    color: colors.rubric,
    marginBottom: 8,
  },
  claimBox: {
    borderLeftWidth: 2,
    borderLeftColor: colors.rule,
    paddingLeft: 12,
    paddingVertical: 6,
    marginBottom: 4,
  },
  claimText: {
    ...type.claimText,
    color: colors.textBody,
    fontStyle: 'italic',
  },
  claimSource: {
    ...type.metadata,
    color: colors.textMuted,
    marginTop: 2,
  },

  // Source articles
  sourcesSection: { marginBottom: 16 },
  sourcesLabel: {
    ...type.metadata,
    color: colors.textMuted,
    marginBottom: 6,
  },
  sourceLink: {
    paddingVertical: 4,
  },
  sourceLinkText: {
    ...type.metadata,
    color: colors.rubric,
  },

  // Phase sections
  phaseSection: { marginTop: 12 },
  promptText: {
    fontFamily: fonts.readingItalic,
    fontSize: 14,
    lineHeight: 21,
    color: colors.textSecondary,
    marginBottom: 16,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}),
  },
  promptActions: { flexDirection: 'row', gap: 12 },
  actionBtn: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: 12,
    borderWidth: 1.5,
    borderColor: colors.rule,
    borderRadius: 3,
  },
  actionBtnPrimary: {
    borderColor: colors.ratingAgainBorder,
  },
  actionBtnText: {
    fontFamily: fonts.body,
    fontSize: 13,
    color: colors.textSecondary,
  },

  // Note input
  noteInput: {
    borderWidth: 1,
    borderColor: colors.rule,
    borderRadius: 3,
    padding: 14,
    fontFamily: fonts.reading,
    color: colors.textBody,
    fontSize: 15,
    lineHeight: 22,
    minHeight: 100,
    textAlignVertical: 'top',
    marginBottom: 12,
    backgroundColor: colors.parchment,
  },
  submitBtn: {
    backgroundColor: colors.ink,
    borderRadius: 3,
    paddingVertical: 12,
    alignItems: 'center',
  },
  submitBtnDisabled: { opacity: 0.3 },
  submitBtnText: {
    fontFamily: fonts.uiMedium,
    color: colors.parchment,
    fontSize: 13,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },

  // Rating
  ratePrompt: {
    fontFamily: fonts.readingItalic,
    fontSize: 14,
    color: colors.textSecondary,
    marginBottom: 12,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}),
  },
  ratingGrid: {
    flexDirection: 'row',
    gap: 8,
  },
  ratingBtn: {
    flex: 1,
    borderWidth: 1.5,
    borderRadius: 3,
    paddingVertical: 10,
    alignItems: 'center',
    backgroundColor: 'transparent',
  },
  ratingLabel: {
    ...type.ratingLabel,
    marginBottom: 2,
  },
  ratingHint: {
    ...type.ratingHint,
    color: colors.textMuted,
  },

  // Empty / completed states
  emptyState: {
    flex: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 32, gap: 8,
  },
  emptyTitle: {
    fontFamily: fonts.bodyMedium,
    fontSize: 18,
    color: colors.textMuted,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  emptySubtitle: {
    fontFamily: fonts.reading,
    fontSize: 14,
    color: colors.textMuted,
    textAlign: 'center',
    lineHeight: 20,
  },

  completedSection: { alignItems: 'center', paddingTop: 48, paddingBottom: 32, gap: 6 },
  completedTitle: {
    fontFamily: fonts.bodyMedium,
    fontSize: 18,
    color: colors.textSecondary,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  completedSubtitle: {
    ...type.metadata,
    color: colors.textMuted,
  },
  completedHint: {
    fontFamily: fonts.reading,
    fontSize: 13,
    color: colors.textMuted,
    textAlign: 'center',
    paddingHorizontal: 32,
    marginTop: 4,
    lineHeight: 18,
  },
  refreshQueueBtn: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    marginTop: 12,
    borderWidth: 1.5,
    borderColor: colors.rule,
    borderRadius: 3,
  },
  refreshQueueText: {
    fontFamily: fonts.body,
    fontSize: 13,
    color: colors.rubric,
  },

  // Topic overview
  topicOverview: { paddingHorizontal: 20, paddingBottom: 40 },
  overviewTitle: {
    ...type.sectionHead,
    color: colors.rubric,
    marginBottom: 12,
  },
  topicOverviewRow: {
    flexDirection: 'row', alignItems: 'center', marginBottom: 8, gap: 8,
  },
  topicOverviewName: {
    fontFamily: fonts.body,
    fontSize: 13,
    color: colors.textBody,
    width: 120,
  },
  topicOverviewBar: {
    flex: 1, height: 3, backgroundColor: colors.rule, overflow: 'hidden',
  },
  topicOverviewFill: {
    height: '100%',
    backgroundColor: colors.ink,
  },
  topicOverviewCount: {
    ...type.metadata,
    color: colors.textMuted,
    width: 32,
    textAlign: 'right',
  },
});
