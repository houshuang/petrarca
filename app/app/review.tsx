import { useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput,
  KeyboardAvoidingView, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import {
  getReviewQueue, submitReview, getConceptReview,
  getArticleById, getConcepts, getStats,
} from '../data/store';
import { Concept, ConceptReview, ReviewRating } from '../data/types';
import { logEvent } from '../data/logger';

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

  const lastNote = review.notes.length > 0
    ? review.notes[review.notes.length - 1]
    : null;

  const handleRate = useCallback((rating: ReviewRating) => {
    submitReview(concept.id, rating, noteText || undefined);
    onComplete();
  }, [concept.id, noteText, onComplete]);

  return (
    <ScrollView style={styles.cardScroll} showsVerticalScrollIndicator={false}>
      <View style={styles.card}>
        {/* Concept header */}
        <View style={styles.conceptHeader}>
          <View style={styles.topicPill}>
            <Text style={styles.topicText}>{concept.topic}</Text>
          </View>
          <Text style={styles.reasonText}>{reason}</Text>
        </View>

        <Text style={styles.conceptText}>{concept.text}</Text>

        {/* Engagement stats */}
        <View style={styles.statsRow}>
          {review.engagement_count > 0 && (
            <Text style={styles.statText}>
              Reviewed {review.engagement_count}× ·
              Next in {Math.round(review.stability_days)}d
            </Text>
          )}
          {review.engagement_count === 0 && (
            <Text style={styles.statText}>First review</Text>
          )}
        </View>

        {/* Last note (if any) */}
        {lastNote && (
          <View style={styles.lastNoteBox}>
            <Text style={styles.lastNoteLabel}>Your last note</Text>
            <Text style={styles.lastNoteText}>{lastNote.text}</Text>
            <Text style={styles.lastNoteDate}>
              {new Date(lastNote.created_at).toLocaleDateString()}
            </Text>
          </View>
        )}

        {/* Source articles */}
        {sourceArticles.length > 0 && (
          <View style={styles.sourcesSection}>
            <Text style={styles.sourcesLabel}>From articles:</Text>
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
                <Ionicons name="chevron-forward" size={14} color="#64748b" />
              </Pressable>
            ))}
          </View>
        )}

        {/* Phase: Prompt */}
        {phase === 'prompt' && (
          <View style={styles.phaseSection}>
            <Text style={styles.promptText}>
              How does this concept connect to what you've been reading?
            </Text>
            <View style={styles.promptActions}>
              <Pressable
                style={styles.actionBtn}
                onPress={() => setPhase('respond')}
              >
                <Ionicons name="create-outline" size={18} color="#60a5fa" />
                <Text style={styles.actionBtnText}>Add a note</Text>
              </Pressable>
              <Pressable
                style={styles.actionBtn}
                onPress={() => setPhase('rate')}
              >
                <Ionicons name="checkmark-circle-outline" size={18} color="#10b981" />
                <Text style={[styles.actionBtnText, { color: '#10b981' }]}>Just rate</Text>
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
              placeholderTextColor="#475569"
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
            <Text style={styles.rateLabel}>How well do you understand this?</Text>
            <View style={styles.ratingGrid}>
              {([
                [1, 'Again', 'Confused or forgot', '#ef4444'],
                [2, 'Hard', 'Getting it but fuzzy', '#f59e0b'],
                [3, 'Good', 'Solid understanding', '#10b981'],
                [4, 'Easy', 'Could teach this', '#3b82f6'],
              ] as const).map(([rating, label, desc, color]) => (
                <Pressable
                  key={rating}
                  style={[styles.ratingBtn, { borderColor: color }]}
                  onPress={() => handleRate(rating)}
                >
                  <Text style={[styles.ratingLabel, { color }]}>{label}</Text>
                  <Text style={styles.ratingDesc}>{desc}</Text>
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

export default function ReviewScreen() {
  const [, forceUpdate] = useState(0);
  const queue = getReviewQueue(10);
  const [currentIndex, setCurrentIndex] = useState(0);
  const stats = getStats();

  const dueCount = queue.length;
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
        <View style={styles.emptyState}>
          <Ionicons name="bulb-outline" size={48} color="#334155" />
          <Text style={styles.emptyTitle}>No concepts yet</Text>
          <Text style={styles.emptySubtitle}>
            Start reading and signaling on claims to build your knowledge map
          </Text>
        </View>
      </View>
    );
  }

  // Queue complete
  if (currentIndex >= queue.length || queue.length === 0) {
    return (
      <View style={styles.container}>
        <ScrollView style={styles.scroll} showsVerticalScrollIndicator={false}>
          <View style={styles.completedSection}>
            <Ionicons name="checkmark-circle" size={48} color="#10b981" />
            <Text style={styles.completedTitle}>
              {dueCount === 0 ? 'Nothing due right now' : 'Session complete!'}
            </Text>
            <Text style={styles.completedSubtitle}>
              {stats.knownConcepts + stats.encounteredConcepts} of {allConcepts.length} concepts engaged
              {reviewedCount > 0 ? ` · ${reviewedCount} reviewed` : ''}
            </Text>

            {dueCount === 0 && (
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
              <Ionicons name="refresh" size={16} color="#60a5fa" />
              <Text style={styles.refreshQueueText}>Check again</Text>
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
      {/* Progress header */}
      <View style={styles.progressHeader}>
        <Text style={styles.progressText}>
          {currentIndex + 1} of {queue.length} concepts
        </Text>
        <Pressable onPress={() => { setCurrentIndex(queue.length); }}>
          <Text style={styles.skipAllText}>End session</Text>
        </Pressable>
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
  container: { flex: 1, backgroundColor: '#0f172a' },
  scroll: { flex: 1 },
  cardScroll: { flex: 1, paddingHorizontal: 16 },

  // Progress header
  progressHeader: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: 16, paddingVertical: 10,
    borderBottomWidth: 1, borderBottomColor: '#1e293b',
  },
  progressText: { color: '#94a3b8', fontSize: 13 },
  skipAllText: { color: '#64748b', fontSize: 13 },

  // Review card
  card: { paddingTop: 16, paddingBottom: 40 },
  conceptHeader: {
    flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12,
  },
  topicPill: {
    backgroundColor: '#334155', paddingHorizontal: 10, paddingVertical: 3, borderRadius: 10,
  },
  topicText: { color: '#94a3b8', fontSize: 12 },
  reasonText: { color: '#64748b', fontSize: 12, fontStyle: 'italic' },
  conceptText: {
    color: '#f8fafc', fontSize: 18, fontWeight: '600', lineHeight: 26, marginBottom: 12,
  },
  statsRow: { marginBottom: 16 },
  statText: { color: '#64748b', fontSize: 12 },

  // Last note
  lastNoteBox: {
    backgroundColor: '#1e293b', borderRadius: 12, padding: 14,
    marginBottom: 16, borderLeftWidth: 3, borderLeftColor: '#8b5cf6',
  },
  lastNoteLabel: { color: '#a78bfa', fontSize: 11, marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 },
  lastNoteText: { color: '#cbd5e1', fontSize: 14, lineHeight: 20 },
  lastNoteDate: { color: '#475569', fontSize: 11, marginTop: 6 },

  // Source articles
  sourcesSection: { marginBottom: 16 },
  sourcesLabel: { color: '#64748b', fontSize: 12, marginBottom: 6 },
  sourceLink: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingVertical: 8, paddingHorizontal: 12,
    backgroundColor: '#1e293b', borderRadius: 8, marginBottom: 4,
  },
  sourceLinkText: { color: '#cbd5e1', fontSize: 13, flex: 1, marginRight: 8 },

  // Phase sections
  phaseSection: { marginTop: 8 },
  promptText: { color: '#94a3b8', fontSize: 15, lineHeight: 22, marginBottom: 16 },
  promptActions: { flexDirection: 'row', gap: 12 },
  actionBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: 16, paddingVertical: 12,
    backgroundColor: '#1e293b', borderRadius: 12, flex: 1, justifyContent: 'center',
  },
  actionBtnText: { color: '#60a5fa', fontSize: 14, fontWeight: '500' },

  // Note input
  noteInput: {
    backgroundColor: '#1e293b', borderRadius: 12, padding: 14,
    color: '#f8fafc', fontSize: 15, lineHeight: 22,
    minHeight: 100, textAlignVertical: 'top',
    marginBottom: 12,
  },
  submitBtn: {
    backgroundColor: '#2563eb', borderRadius: 10, paddingVertical: 12,
    alignItems: 'center',
  },
  submitBtnDisabled: { opacity: 0.4 },
  submitBtnText: { color: '#ffffff', fontSize: 14, fontWeight: '600' },

  // Rating
  rateLabel: { color: '#94a3b8', fontSize: 14, marginBottom: 12 },
  ratingGrid: { gap: 8 },
  ratingBtn: {
    borderWidth: 1, borderRadius: 12, padding: 14,
    backgroundColor: '#1e293b',
  },
  ratingLabel: { fontSize: 16, fontWeight: '700', marginBottom: 2 },
  ratingDesc: { color: '#64748b', fontSize: 13 },

  // Empty / completed states
  emptyState: {
    flex: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 32, gap: 12,
  },
  emptyTitle: { color: '#f8fafc', fontSize: 20, fontWeight: '700' },
  emptySubtitle: { color: '#94a3b8', fontSize: 14, textAlign: 'center', lineHeight: 20 },

  completedSection: { alignItems: 'center', paddingTop: 60, paddingBottom: 32, gap: 8 },
  completedTitle: { color: '#f8fafc', fontSize: 20, fontWeight: '700' },
  completedSubtitle: { color: '#94a3b8', fontSize: 14 },
  completedHint: { color: '#475569', fontSize: 13, textAlign: 'center', paddingHorizontal: 32, marginTop: 8, lineHeight: 18 },
  refreshQueueBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: 16, paddingVertical: 10,
    marginTop: 16,
  },
  refreshQueueText: { color: '#60a5fa', fontSize: 14 },

  // Topic overview
  topicOverview: { paddingHorizontal: 16, paddingBottom: 40 },
  overviewTitle: { color: '#f8fafc', fontSize: 16, fontWeight: '700', marginBottom: 12 },
  topicOverviewRow: {
    flexDirection: 'row', alignItems: 'center', marginBottom: 8, gap: 8,
  },
  topicOverviewName: { color: '#cbd5e1', fontSize: 13, width: 120 },
  topicOverviewBar: {
    flex: 1, height: 8, backgroundColor: '#1e293b', borderRadius: 4, overflow: 'hidden',
  },
  topicOverviewFill: { height: '100%', backgroundColor: '#10b981', borderRadius: 4 },
  topicOverviewCount: { color: '#64748b', fontSize: 12, width: 32, textAlign: 'right' },
});
