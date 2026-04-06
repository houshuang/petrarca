import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator, Linking, Modal, Platform, Pressable,
  ScrollView, StyleSheet, Text, View,
} from 'react-native';
import { colors, fonts, layout } from '../design/tokens';
import { EntityDetails } from '../data/types';
import {
  fetchEntityDetails, recordEntityTap, fetchEntityQuestions,
  triggerEntityResearch, triggerMicrolearning,
} from '../lib/book-api';
import { logEvent } from '../data/logger';
import AncientMap from './AncientMap';
import ExplorerCapture from './ExplorerCapture';

interface Props {
  entityId: string | null;
  onClose: () => void;
  onExploreEntity?: (entityName: string) => void;
}

const TYPE_LABELS: Record<string, string> = {
  place: '\u{1F4CD} Place',
  person: '\u{1F464} Person',
  event: '\u26A1 Event',
  period: '\u{1F551} Period',
  concept: '\u{1F4A1} Concept',
};

const KNOWLEDGE_COLORS: Record<string, string> = {
  anchored: colors.claimNew,
  engaged: '#b8860b',
  mentioned: colors.textMuted,
  unknown: colors.textFaint,
};

export default function EntitySheet({ entityId, onClose, onExploreEntity }: Props) {
  const [entity, setEntity] = useState<EntityDetails | null>(null);
  const [loading, setLoading] = useState(false);
  const [tapped, setTapped] = useState<false | 'unknown' | 'interested' | 'loading'>(false);
  const [promptsQueued, setPromptsQueued] = useState(0);
  // Entity research state
  const [questions, setQuestions] = useState<string[] | null>(null);
  const [questionsLoading, setQuestionsLoading] = useState(false);
  const [researchTriggered, setResearchTriggered] = useState(false);
  const [triggeredQueries, setTriggeredQueries] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (!entityId) {
      setEntity(null);
      setTapped(false);
      setPromptsQueued(0);
      setQuestions(null);
      setQuestionsLoading(false);
      setResearchTriggered(false);
      setTriggeredQueries(new Set());
      return;
    }
    setLoading(true);
    setTapped(false);
    setPromptsQueued(0);
    setQuestions(null);
    setQuestionsLoading(false);
    setResearchTriggered(false);
    setTriggeredQueries(new Set());
    fetchEntityDetails(entityId)
      .then(setEntity)
      .catch(() => setEntity(null))
      .finally(() => setLoading(false));

    recordEntityTap(entityId, 'tap').catch(() => {});
    logEvent('entity_sheet_opened', { entity_id: entityId });
  }, [entityId]);

  if (!entityId) return null;

  const handleAction = async (action: 'unknown' | 'interested') => {
    if (!entityId) return;
    logEvent('entity_action', { entity_id: entityId, action });

    if (action === 'interested') {
      setTapped('loading');
      try {
        const resp = await recordEntityTap(entityId, action);
        setPromptsQueued(resp.prompts_created || 0);
        setTapped('interested');
      } catch {
        setTapped('interested');
      }
    } else {
      recordEntityTap(entityId, action).catch(() => {});
      setTapped('unknown');
      setTimeout(onClose, 800);
    }
  };

  const handleWikipedia = () => {
    if (entity?.wikipedia_url) {
      Linking.openURL(entity.wikipedia_url);
      logEvent('entity_wikipedia', { entity_id: entityId });
    }
  };

  const handleGetQuestions = async () => {
    if (!entity || questionsLoading) return;
    setQuestionsLoading(true);
    logEvent('entity_questions_requested', { entity_id: entityId });
    try {
      const resp = await fetchEntityQuestions(
        entityId, entity.name, entity.entity_type, entity.description);
      setQuestions(resp.questions);
    } catch (e) {
      console.warn('[entity] questions failed:', e);
      setQuestions([`What was the historical significance of ${entity.name}?`]);
    } finally {
      setQuestionsLoading(false);
    }
  };

  const handleResearch = async () => {
    if (!entity || researchTriggered) return;
    setResearchTriggered(true);
    logEvent('entity_research_triggered', { entity_id: entityId });
    try {
      await triggerEntityResearch(
        entityId, entity.name, entity.entity_type, entity.description);
    } catch (e) {
      console.warn('[entity] research failed:', e);
    }
  };

  const handleCaptureComplete = () => {
    // Refresh entity details to show new notes
    if (entityId) {
      fetchEntityDetails(entityId).then(setEntity).catch(() => {});
    }
  };

  const handleQuestionTap = (query: string, idx: number) => {
    setTriggeredQueries(prev => new Set(prev).add(idx));
    logEvent('entity_question_tapped', { entity_id: entityId, query });
    triggerMicrolearning({ query }).catch(() => {});
  };

  const bestKnowledge = entity?.curriculum_links?.reduce((best, link) => {
    const rank: Record<string, number> = { anchored: 3, engaged: 2, mentioned: 1, unknown: 0 };
    return (rank[link.knowledge || 'unknown'] || 0) > (rank[best] || 0)
      ? (link.knowledge || 'unknown') : best;
  }, 'unknown' as string) || 'unknown';

  const formatYear = (y: number | null | undefined) => {
    if (y == null) return '';
    return y < 0 ? `${Math.abs(y)} BC` : `${y} AD`;
  };

  const hasResearchContent = entity?.microlearning_backlinks && entity.microlearning_backlinks.length > 0;

  return (
    <Modal
      visible={!!entityId}
      transparent
      animationType="slide"
      onRequestClose={onClose}
    >
      <Pressable style={es.overlay} onPress={onClose}>
        <View />
      </Pressable>
      <View style={es.sheet}>
        <View style={es.handle} />
        <ScrollView style={es.scrollContent} showsVerticalScrollIndicator={false}>
          {loading ? (
            <ActivityIndicator size="small" color={colors.rubric} style={{ padding: 40 }} />
          ) : entity ? (
            <>
              {/* Header: type + name */}
              <View style={es.headerRow}>
                {entity.entity_type && (
                  <Text style={es.typeBadge}>
                    {TYPE_LABELS[entity.entity_type] || entity.entity_type}
                  </Text>
                )}
                <View style={[es.knowledgeDot, { backgroundColor: KNOWLEDGE_COLORS[bestKnowledge] || colors.textFaint }]} />
              </View>

              <Text style={es.entityName}>{entity.name}</Text>
              {entity.modern_name && entity.modern_name !== entity.name ? (
                <Text style={es.modernName}>Modern: {entity.modern_name}</Text>
              ) : null}

              {/* Dates */}
              {(entity.date_start != null || entity.dates) ? (
                <Text style={es.dates}>
                  {entity.date_start != null
                    ? `${formatYear(entity.date_start)}${entity.date_end != null ? ` – ${formatYear(entity.date_end)}` : ''}`
                    : entity.dates}
                </Text>
              ) : null}

              {/* Description */}
              {entity.description ? (
                <Text style={es.description}>{entity.description}</Text>
              ) : null}

              {/* Mini map for places */}
              {entity.entity_type === 'place' && entity.latitude != null && entity.longitude != null ? (
                <View style={es.miniMapWrap}>
                  <AncientMap
                    entities={[entity]}
                    center={[entity.latitude, entity.longitude]}
                    zoom={7}
                    tileLayer="clean"
                    showControls={false}
                    showTimeline={false}
                    showFilters={false}
                    showLegend={false}
                    showEntitySheet={false}
                    style={{ height: 160 }}
                  />
                </View>
              ) : null}

              {/* Curriculum links */}
              {entity.curriculum_links?.length > 0 ? (
                <View style={es.linksSection}>
                  <Text style={es.sectionLabel}>In your curriculum</Text>
                  {entity.curriculum_links.map((link, i) => (
                    <View key={i} style={es.linkRow}>
                      <View style={[es.linkDot, { backgroundColor: KNOWLEDGE_COLORS[link.knowledge || 'unknown'] }]} />
                      <View style={es.linkContent}>
                        <Text style={es.linkTitle}>{link.node_title || link.node_id}</Text>
                        {link.lens_emphasis ? (
                          <Text style={es.linkEmphasis}>{link.lens_emphasis}</Text>
                        ) : null}
                      </View>
                    </View>
                  ))}
                </View>
              ) : null}

              {/* Microlearning backlinks */}
              {hasResearchContent ? (
                <View style={es.linksSection}>
                  <Text style={es.sectionLabel}>In your research</Text>
                  {entity.microlearning_backlinks!.map((bl, i) => (
                    <View key={i} style={es.linkRow}>
                      <View style={[es.linkDot, { backgroundColor: '#2a4a6a' }]} />
                      <View style={es.linkContent}>
                        <Text style={es.linkTitle}>{bl.query}</Text>
                        <Text style={es.linkEmphasis} numberOfLines={2}>{bl.snippet}</Text>
                      </View>
                    </View>
                  ))}
                </View>
              ) : null}

              {/* User notes + capture */}
              <View style={es.notesSection}>
                <Text style={es.sectionLabel}>What I know</Text>
                {entity.voice_context && entity.voice_context.length > 0 && (
                  <View style={{ marginBottom: 12 }}>
                    <Text style={[es.sectionLabel, { fontSize: 11, color: colors.textMuted, marginBottom: 4 }]}>
                      From your voice recall
                    </Text>
                    {entity.voice_context.map((vc: { text: string; type: string }, i: number) => (
                      <View key={i} style={{ marginBottom: 6 }}>
                        <Text style={{ fontFamily: fonts.serif, fontSize: 13, color: colors.textSecondary, lineHeight: 18 }}>
                          {vc.text}
                        </Text>
                      </View>
                    ))}
                  </View>
                )}
                {entity.notes && entity.notes.length > 0 && entity.notes.map(n => (
                  <Text key={n.id} style={es.noteText}>{n.note}</Text>
                ))}
                <ExplorerCapture
                  mode="entity"
                  entityId={entityId}
                  entityName={entity.name}
                  onCaptureComplete={handleCaptureComplete}
                />
              </View>

              {/* Wikipedia link */}
              {entity.wikipedia_url ? (
                <Pressable style={es.wikiLink} onPress={handleWikipedia}>
                  <Text style={es.wikiLinkText}>Wikipedia {'\u2192'}</Text>
                </Pressable>
              ) : null}

              {/* Quick questions section */}
              {questions ? (
                <View style={es.questionsSection}>
                  <Text style={es.sectionLabel}>{'\uD83D\uDD0D'} Research questions</Text>
                  {questions.map((q, i) => (
                    <Pressable
                      key={i}
                      style={[es.questionBtn, triggeredQueries.has(i) && es.questionTriggered]}
                      onPress={() => !triggeredQueries.has(i) && handleQuestionTap(q, i)}
                    >
                      <Text style={[es.questionText, triggeredQueries.has(i) && es.questionTriggeredText]}>
                        {triggeredQueries.has(i) ? '\u2713 ' : ''}{q}
                      </Text>
                    </Pressable>
                  ))}
                </View>
              ) : null}

              {/* View in timeline */}
              {onExploreEntity && entity.name && (
                <Pressable style={es.timelineBtn} onPress={() => {
                  logEvent('entity_view_timeline', { entity_id: entityId, name: entity.name });
                  onClose();
                  onExploreEntity(entity.name);
                }}>
                  <Text style={es.timelineBtnText}>✦ View in timeline</Text>
                </Pressable>
              )}

              {/* Action buttons */}
              <View style={es.researchActions}>
                {!questions && !questionsLoading ? (
                  <Pressable style={es.questionsBtn} onPress={handleGetQuestions}>
                    <Text style={es.questionsBtnText}>{'\uD83D\uDD0D'} 3 questions</Text>
                  </Pressable>
                ) : questionsLoading ? (
                  <View style={[es.questionsBtn, { opacity: 0.6 }]}>
                    <ActivityIndicator size="small" color="#2a4a6a" />
                  </View>
                ) : null}

                {!researchTriggered ? (
                  <Pressable style={es.researchBtn} onPress={handleResearch}>
                    <Text style={es.researchBtnText}>{'\u2726'} Research this</Text>
                  </Pressable>
                ) : (
                  <View style={[es.researchBtn, es.researchTriggered]}>
                    <Text style={es.researchTriggeredText}>Researching... {'\u2713'}</Text>
                  </View>
                )}
              </View>

              {/* Legacy actions */}
              {tapped === 'unknown' ? (
                <Text style={es.tappedConfirm}>Noted {'\u2713'}</Text>
              ) : tapped === 'loading' ? (
                <View style={es.actionRow}>
                  <ActivityIndicator size="small" color="#b8860b" />
                  <Text style={es.explorationLoading}>Generating questions...</Text>
                </View>
              ) : tapped === 'interested' ? (
                <Text style={es.explorationConfirm}>
                  {promptsQueued > 0
                    ? `${promptsQueued} exploration questions queued for next session \u2726`
                    : 'Queued for exploration \u2726'}
                </Text>
              ) : (
                <View style={es.actionRow}>
                  <Pressable
                    style={[es.actionBtn, es.unknownBtn]}
                    onPress={() => handleAction('unknown')}
                  >
                    <Text style={es.unknownBtnText}>I don't know this</Text>
                  </Pressable>
                  <Pressable
                    style={[es.actionBtn, es.interestedBtn]}
                    onPress={() => handleAction('interested')}
                  >
                    <Text style={es.interestedBtnText}>Tell me more</Text>
                  </Pressable>
                </View>
              )}
            </>
          ) : (
            <Text style={es.errorText}>Entity not found</Text>
          )}
        </ScrollView>
      </View>
    </Modal>
  );
}

const es = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.3)',
  },
  sheet: {
    backgroundColor: colors.parchment,
    borderTopLeftRadius: 16,
    borderTopRightRadius: 16,
    maxHeight: '60%',
    paddingBottom: Platform.OS === 'ios' ? 34 : 16,
    ...(Platform.OS === 'web' ? {
      maxWidth: layout.readingMeasure + 2 * layout.screenPadding,
      alignSelf: 'center' as const,
      width: '100%',
    } : {}),
  },
  handle: {
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.rule,
    alignSelf: 'center',
    marginTop: 8,
    marginBottom: 12,
  },
  scrollContent: {
    paddingHorizontal: layout.screenPadding,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  typeBadge: {
    fontFamily: fonts.uiMedium,
    fontSize: 11,
    color: colors.textSecondary,
    letterSpacing: 0.3,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  knowledgeDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  entityName: {
    fontFamily: fonts.displaySemiBold,
    fontSize: 24,
    color: colors.ink,
    marginBottom: 2,
    ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}),
  },
  modernName: {
    fontFamily: fonts.readingItalic,
    fontSize: 14,
    color: colors.textSecondary,
    marginBottom: 4,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}),
  },
  dates: {
    fontFamily: fonts.ui,
    fontSize: 12,
    color: colors.textMuted,
    marginBottom: 10,
  },
  description: {
    fontFamily: fonts.reading,
    fontSize: 15,
    lineHeight: 22,
    color: colors.textBody,
    marginBottom: 16,
  },
  miniMapWrap: {
    height: 160,
    borderRadius: 8,
    overflow: 'hidden',
    marginBottom: 16,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.rule,
  },
  linksSection: {
    marginBottom: 16,
  },
  sectionLabel: {
    fontFamily: fonts.uiMedium,
    fontSize: 10,
    color: colors.textMuted,
    letterSpacing: 0.8,
    textTransform: 'uppercase',
    marginBottom: 8,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  linkRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    marginBottom: 6,
  },
  linkDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    marginTop: 6,
  },
  linkContent: {
    flex: 1,
  },
  linkTitle: {
    fontFamily: fonts.body,
    fontSize: 13,
    color: colors.ink,
    lineHeight: 18,
  },
  linkEmphasis: {
    fontFamily: fonts.readingItalic,
    fontSize: 12,
    color: colors.textSecondary,
    lineHeight: 16,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}),
  },
  notesSection: {
    marginBottom: 16,
  },
  noteText: {
    fontFamily: fonts.reading,
    fontSize: 13,
    lineHeight: 18,
    color: colors.textBody,
    marginBottom: 4,
    paddingLeft: 8,
    borderLeftWidth: 2,
    borderLeftColor: 'rgba(139,37,0,0.15)',
  },
  wikiLink: {
    marginBottom: 16,
  },
  wikiLinkText: {
    fontFamily: fonts.ui,
    fontSize: 13,
    color: colors.info,
    textDecorationLine: 'underline',
  },
  // Research questions
  questionsSection: {
    marginBottom: 16,
  },
  questionBtn: {
    paddingVertical: 8,
    paddingHorizontal: 12,
    marginBottom: 6,
    borderLeftWidth: 2,
    borderLeftColor: 'rgba(42,74,106,0.3)',
    backgroundColor: 'rgba(42,74,106,0.03)',
    borderRadius: 2,
  },
  questionTriggered: {
    borderLeftColor: colors.claimNew,
    backgroundColor: 'rgba(42,122,74,0.04)',
  },
  questionText: {
    fontFamily: fonts.reading,
    fontSize: 13,
    lineHeight: 18,
    color: '#2a4a6a',
  },
  questionTriggeredText: {
    color: colors.claimNew,
  },
  timelineBtn: {
    paddingVertical: 10,
    borderRadius: 4,
    alignItems: 'center' as const,
    borderWidth: 1,
    borderColor: colors.ink,
    backgroundColor: colors.ink,
    marginBottom: 10,
  },
  timelineBtnText: {
    fontFamily: fonts.ui,
    fontSize: 12,
    color: colors.parchment,
  },
  // Action buttons
  researchActions: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 14,
  },
  questionsBtn: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 4,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#2a4a6a',
    backgroundColor: 'rgba(42,74,106,0.04)',
  },
  questionsBtnText: {
    fontFamily: fonts.ui,
    fontSize: 12,
    color: '#2a4a6a',
  },
  researchBtn: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 4,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.rubric,
    backgroundColor: 'rgba(139,37,0,0.04)',
  },
  researchBtnText: {
    fontFamily: fonts.ui,
    fontSize: 12,
    color: colors.rubric,
  },
  researchTriggered: {
    borderColor: colors.claimNew,
    backgroundColor: 'rgba(42,122,74,0.04)',
  },
  researchTriggeredText: {
    fontFamily: fonts.readingItalic,
    fontSize: 12,
    color: colors.claimNew,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}),
  },
  actionRow: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 8,
  },
  actionBtn: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 4,
    alignItems: 'center',
    borderWidth: 1,
  },
  unknownBtn: {
    borderColor: colors.rubric,
    backgroundColor: 'rgba(139,37,0,0.05)',
  },
  unknownBtnText: {
    fontFamily: fonts.ui,
    fontSize: 12,
    color: colors.rubric,
  },
  interestedBtn: {
    borderColor: '#b8860b',
    backgroundColor: 'rgba(184,134,11,0.06)',
  },
  interestedBtnText: {
    fontFamily: fonts.ui,
    fontSize: 12,
    color: '#b8860b',
  },
  tappedConfirm: {
    fontFamily: fonts.readingItalic,
    fontSize: 14,
    color: colors.claimNew,
    textAlign: 'center',
    paddingVertical: 12,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}),
  },
  explorationLoading: {
    fontFamily: fonts.readingItalic,
    fontSize: 14,
    color: '#b8860b',
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}),
  },
  explorationConfirm: {
    fontFamily: fonts.readingItalic,
    fontSize: 14,
    color: '#b8860b',
    textAlign: 'center',
    paddingVertical: 12,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' as const } : {}),
  },
  errorText: {
    fontFamily: fonts.reading,
    fontSize: 14,
    color: colors.textMuted,
    textAlign: 'center',
    padding: 40,
  },
});
