import { useState, useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator,
  Platform, Linking,
} from 'react-native';
import { useFocusEffect } from 'expo-router';
import { colors, fonts, type, layout } from '../../design/tokens';
import { logEvent } from '../../data/logger';
import { setFeedbackContext } from '../../lib/feedback-context';
import { RESEARCH_BASE, fetchWithTimeout } from '../../lib/chat-api';
import { getStatsDashboardUrl } from '../../lib/server-urls';
import DoubleRule from '../../components/DoubleRule';

// ── Types ─────────────────────────────────────────────────────────────────

interface StructuralProgress {
  domain_id: string;
  domain_title: string;
  total: number;
  reviewed: number;
}

interface KnowledgeLevel {
  domain_id: string;
  title: string;
  node_count: number;
  distribution: { unknown: number; mentioned: number; engaged: number; anchored: number };
}

interface NativeStats {
  today: { reviewed: number; due: number };
  structural_progress: StructuralProgress[];
  card_type_counts: Record<string, { total: number; reviewed: number }>;
  knowledge_levels: KnowledgeLevel[];
  heatmap: Record<string, number>;
  review_by_type: Record<string, number>;
  scores: { knew: number; partly: number; missed: number };
  totals: {
    knowledge_items: number;
    microlearning_cards: number;
    quizzes: number;
    structural_positions: number;
  };
}

async function fetchNativeStats(): Promise<NativeStats> {
  const res = await fetchWithTimeout(`${RESEARCH_BASE}/stats/native`, { timeout: 15000 });
  if (!res.ok) throw new Error(`/stats/native failed: ${res.status}`);
  return res.json();
}

// ── Short domain names ────────────────────────────────────────────────────

function shortDomain(title: string): string {
  if (title.startsWith('Ancient Greece')) return 'Greece';
  if (title.startsWith('Byzantine')) return 'Byzantine';
  if (title.startsWith('Islamic')) return 'Islamic';
  if (title.startsWith('Rome') || title.includes('Republic')) return 'Rome';
  if (title.startsWith('Sicily')) return 'Sicily';
  if (title.includes('Architecture')) return 'Architecture';
  if (title.includes('Literature')) return 'Literature';
  if (title.includes('Music')) return 'Music';
  if (title.includes('Philosophy')) return 'Philosophy';
  if (title.includes('AP World')) return 'AP World';
  // Fallback: first two words
  return title.split(/[:(]/)[0].trim().split(' ').slice(0, 2).join(' ');
}

// ── Main Component ────────────────────────────────────────────────────────

export default function StatsTab() {
  const [stats, setStats] = useState<NativeStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadStats = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await fetchNativeStats();
      setStats(data);
    } catch (e: any) {
      setError(e.message || 'Failed to load stats');
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      logEvent('stats_tab_open');
      setFeedbackContext({ screen: 'stats-tab' });
      loadStats();
    }, [])
  );

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <View style={styles.header}>
        <Text style={styles.title}>Statistics</Text>
        <Text style={styles.subtitle}>Your knowledge at a glance</Text>
      </View>

      <DoubleRule />

      {loading && (
        <View style={styles.loadingWrap}>
          <ActivityIndicator size="small" color={colors.rubric} />
        </View>
      )}

      {error ? <Text style={styles.errorText}>{error}</Text> : null}

      {stats && !loading && (
        <>
          {/* Today's summary */}
          <View style={styles.statGrid}>
            <StatBox label="Reviewed Today" value={stats.today.reviewed} accent />
            <StatBox label="Due Today" value={stats.today.due} />
            <StatBox label="Knowledge Items" value={stats.totals.knowledge_items} />
            <StatBox label="Structural Pos." value={stats.totals.structural_positions} />
          </View>

          {/* Structural card progress — the most motivating section */}
          {stats.structural_progress.length > 0 && (
            <View style={styles.section}>
              <Text style={styles.sectionLabel}>Structural Card Progress</Text>
              {stats.structural_progress.map((d) => (
                <ProgressRow
                  key={d.domain_id}
                  label={shortDomain(d.domain_title)}
                  reviewed={d.reviewed}
                  total={d.total}
                />
              ))}

              {/* Card type sub-counts */}
              {Object.keys(stats.card_type_counts).length > 0 && (
                <View style={styles.cardTypeRow}>
                  {Object.entries(stats.card_type_counts)
                    .sort(([, a], [, b]) => b.total - a.total)
                    .map(([ct, counts]) => (
                      <View key={ct} style={styles.cardTypePill}>
                        <Text style={styles.cardTypeLabel}>
                          {ct} {counts.reviewed}/{counts.total}
                        </Text>
                      </View>
                    ))}
                </View>
              )}
            </View>
          )}

          {/* Knowledge levels per domain */}
          {stats.knowledge_levels.length > 0 && (
            <View style={styles.section}>
              <Text style={styles.sectionLabel}>Knowledge Levels</Text>
              <View style={styles.legendRow}>
                <LegendDot color={LEVEL_COLORS.anchored} label="Anchored" />
                <LegendDot color={LEVEL_COLORS.engaged} label="Engaged" />
                <LegendDot color={LEVEL_COLORS.mentioned} label="Mentioned" />
                <LegendDot color={LEVEL_COLORS.unknown} label="Unknown" />
              </View>
              {stats.knowledge_levels.map((d) => (
                <KnowledgeBar key={d.domain_id} data={d} />
              ))}
            </View>
          )}

          {/* Activity heatmap */}
          <ActivityHeatmap heatmap={stats.heatmap} />

          {/* Score distribution */}
          <ScoreDistribution scores={stats.scores} />
        </>
      )}

      {/* Link to full dashboard */}
      <Pressable
        style={styles.dashboardLink}
        onPress={() => {
          logEvent('stats_full_dashboard_tap');
          Linking.openURL(getStatsDashboardUrl());
        }}
      >
        <Text style={styles.dashboardText}>Open Full Dashboard {'\u203A'}</Text>
        <Text style={styles.dashboardHint}>Detailed charts, activity timeline, knowledge growth</Text>
      </Pressable>
    </ScrollView>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────

function StatBox({ label, value, accent }: { label: string; value: number; accent?: boolean }) {
  return (
    <View style={styles.statBox}>
      <Text style={[styles.statNumber, accent && { color: colors.rubric }]}>
        {value}
      </Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

function ProgressRow({ label, reviewed, total }: { label: string; reviewed: number; total: number }) {
  const pct = total > 0 ? (reviewed / total) * 100 : 0;
  return (
    <View style={styles.progressRow}>
      <View style={styles.progressLabelRow}>
        <Text style={styles.progressLabel} numberOfLines={1}>{label}</Text>
        <Text style={styles.progressCount}>{reviewed}/{total}</Text>
      </View>
      <View style={styles.progressTrack}>
        <View style={[styles.progressFill, { width: `${Math.max(pct, 1)}%` }]} />
      </View>
    </View>
  );
}

const LEVEL_COLORS = {
  anchored: colors.success,
  engaged: colors.info,
  mentioned: colors.warning,
  unknown: colors.rule,
};

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <View style={styles.legendItem}>
      <View style={[styles.legendDot, { backgroundColor: color }]} />
      <Text style={styles.legendText}>{label}</Text>
    </View>
  );
}

function KnowledgeBar({ data }: { data: KnowledgeLevel }) {
  const { distribution: d, node_count } = data;
  const total = node_count || 1;
  const segments = [
    { key: 'anchored', count: d.anchored, color: LEVEL_COLORS.anchored },
    { key: 'engaged', count: d.engaged, color: LEVEL_COLORS.engaged },
    { key: 'mentioned', count: d.mentioned, color: LEVEL_COLORS.mentioned },
    { key: 'unknown', count: d.unknown, color: LEVEL_COLORS.unknown },
  ];
  return (
    <View style={styles.knowledgeRow}>
      <Text style={styles.knowledgeDomain} numberOfLines={1}>{shortDomain(data.title)}</Text>
      <View style={styles.knowledgeBarTrack}>
        {segments.map((s) =>
          s.count > 0 ? (
            <View
              key={s.key}
              style={[styles.knowledgeSegment, {
                width: `${(s.count / total) * 100}%`,
                backgroundColor: s.color,
              }]}
            />
          ) : null,
        )}
      </View>
      <Text style={styles.knowledgeCount}>{d.anchored + d.engaged}/{total}</Text>
    </View>
  );
}

function ActivityHeatmap({ heatmap }: { heatmap: Record<string, number> }) {
  const weeks = useMemo(() => buildHeatmapWeeks(heatmap), [heatmap]);
  const maxCount = useMemo(
    () => Math.max(1, ...Object.values(heatmap)),
    [heatmap],
  );

  return (
    <View style={styles.section}>
      <Text style={styles.sectionLabel}>Activity (Last 8 Weeks)</Text>
      <View style={styles.heatmapDayLabels}>
        <Text style={styles.heatmapDayLabel}>M</Text>
        <Text style={styles.heatmapDayLabel}>W</Text>
        <Text style={styles.heatmapDayLabel}>F</Text>
        <Text style={styles.heatmapDayLabel}>S</Text>
      </View>
      <View style={styles.heatmapGrid}>
        {weeks.map((week, wi) => (
          <View key={wi} style={styles.heatmapCol}>
            {week.map((day, di) => (
              <View
                key={di}
                style={[
                  styles.heatmapCell,
                  { backgroundColor: day.count > 0
                    ? heatColor(day.count, maxCount)
                    : colors.parchmentDark,
                  },
                ]}
              />
            ))}
          </View>
        ))}
      </View>
    </View>
  );
}

function ScoreDistribution({ scores }: { scores: { knew: number; partly: number; missed: number } }) {
  const total = scores.knew + scores.partly + scores.missed;
  if (total === 0) return null;
  const segments = [
    { label: 'Knew', count: scores.knew, color: colors.ratingEasy },
    { label: 'Partly', count: scores.partly, color: colors.ratingHard },
    { label: 'Missed', count: scores.missed, color: colors.ratingAgain },
  ];
  return (
    <View style={styles.section}>
      <Text style={styles.sectionLabel}>Score Distribution (All Time)</Text>
      <View style={styles.scoreBarTrack}>
        {segments.map((s) =>
          s.count > 0 ? (
            <View
              key={s.label}
              style={[styles.scoreSegment, {
                flex: s.count,
                backgroundColor: s.color,
              }]}
            />
          ) : null,
        )}
      </View>
      <View style={styles.scoreLabelRow}>
        {segments.map((s) => (
          <Text key={s.label} style={styles.scoreLabel}>
            {s.label}: {s.count} ({total > 0 ? Math.round((s.count / total) * 100) : 0}%)
          </Text>
        ))}
      </View>
    </View>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────

function buildHeatmapWeeks(heatmap: Record<string, number>): { date: string; count: number }[][] {
  const weeks: { date: string; count: number }[][] = [];
  const today = new Date();
  // Go back to the most recent Monday
  const dayOfWeek = today.getDay();
  const mondayOffset = dayOfWeek === 0 ? 6 : dayOfWeek - 1;
  const startOfThisWeek = new Date(today);
  startOfThisWeek.setDate(today.getDate() - mondayOffset);

  // 8 weeks back
  const start = new Date(startOfThisWeek);
  start.setDate(start.getDate() - 7 * 7); // 7 more weeks back

  for (let w = 0; w < 8; w++) {
    const week: { date: string; count: number }[] = [];
    for (let d = 0; d < 7; d++) {
      const date = new Date(start);
      date.setDate(start.getDate() + w * 7 + d);
      const key = date.toISOString().slice(0, 10);
      week.push({ date: key, count: heatmap[key] || 0 });
    }
    weeks.push(week);
  }
  return weeks;
}

function heatColor(count: number, max: number): string {
  const intensity = Math.min(count / max, 1);
  if (intensity > 0.7) return colors.rubric;
  if (intensity > 0.4) return 'rgba(139, 37, 0, 0.6)';
  if (intensity > 0.15) return 'rgba(139, 37, 0, 0.35)';
  return 'rgba(139, 37, 0, 0.15)';
}

// ── Styles ────────────────────────────────────────────────────────────────

const CELL_SIZE = 14;
const CELL_GAP = 3;

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.parchment,
  },
  content: {
    paddingBottom: 40,
  },
  header: {
    paddingHorizontal: layout.screenPadding,
    paddingTop: 12,
    paddingBottom: 8,
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
  loadingWrap: {
    paddingVertical: 32,
    alignItems: 'center',
  },
  errorText: {
    fontFamily: fonts.reading,
    fontSize: 14,
    color: colors.danger,
    paddingHorizontal: layout.screenPadding,
    paddingTop: 16,
  },

  // Stat grid
  statGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    paddingHorizontal: layout.screenPadding,
    paddingTop: 20,
    gap: 12,
  },
  statBox: {
    flex: 1,
    minWidth: 140,
    backgroundColor: colors.parchmentDark,
    borderRadius: 8,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.rule,
    padding: 16,
    alignItems: 'center',
  },
  statNumber: {
    ...type.statNumber,
    color: colors.ink,
  },
  statLabel: {
    ...type.statLabel,
    color: colors.textMuted,
    marginTop: 4,
  },

  // Sections
  section: {
    marginTop: 24,
    paddingHorizontal: layout.screenPadding,
  },
  sectionLabel: {
    ...type.sectionHead,
    color: colors.textMuted,
    marginBottom: 8,
  },

  // Progress bars
  progressRow: {
    marginBottom: 12,
  },
  progressLabelRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    marginBottom: 4,
  },
  progressLabel: {
    fontFamily: fonts.body,
    fontSize: 14,
    color: colors.ink,
    flex: 1,
  },
  progressCount: {
    fontFamily: fonts.uiMedium,
    fontSize: 12,
    color: colors.textSecondary,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  progressTrack: {
    height: 6,
    backgroundColor: colors.parchmentDark,
    borderRadius: 3,
    overflow: 'hidden',
  },
  progressFill: {
    height: 6,
    backgroundColor: colors.rubric,
    borderRadius: 3,
  },

  // Card type pills
  cardTypeRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 8,
  },
  cardTypePill: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    backgroundColor: colors.parchmentDark,
    borderRadius: 4,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.rule,
  },
  cardTypeLabel: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: colors.textSecondary,
    textTransform: 'capitalize',
  },

  // Knowledge bars
  legendRow: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 10,
  },
  legendItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  legendDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  legendText: {
    fontFamily: fonts.ui,
    fontSize: 9,
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  knowledgeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
    gap: 8,
  },
  knowledgeDomain: {
    fontFamily: fonts.body,
    fontSize: 13,
    color: colors.ink,
    width: 80,
  },
  knowledgeBarTrack: {
    flex: 1,
    height: 10,
    borderRadius: 5,
    flexDirection: 'row',
    overflow: 'hidden',
    backgroundColor: colors.parchmentDark,
  },
  knowledgeSegment: {
    height: 10,
  },
  knowledgeCount: {
    fontFamily: fonts.uiMedium,
    fontSize: 11,
    color: colors.textSecondary,
    width: 36,
    textAlign: 'right',
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },

  // Heatmap
  heatmapGrid: {
    flexDirection: 'row',
    gap: CELL_GAP,
  },
  heatmapCol: {
    gap: CELL_GAP,
  },
  heatmapCell: {
    width: CELL_SIZE,
    height: CELL_SIZE,
    borderRadius: 2,
  },
  heatmapDayLabels: {
    position: 'absolute',
    left: layout.screenPadding - 14,
    top: 28,
    height: 7 * (CELL_SIZE + CELL_GAP),
    justifyContent: 'space-between',
  },
  heatmapDayLabel: {
    fontFamily: fonts.ui,
    fontSize: 8,
    color: colors.textMuted,
  },

  // Score distribution
  scoreBarTrack: {
    height: 12,
    borderRadius: 6,
    flexDirection: 'row',
    overflow: 'hidden',
  },
  scoreSegment: {
    height: 12,
  },
  scoreLabelRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 6,
  },
  scoreLabel: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: colors.textSecondary,
  },

  // Dashboard link
  dashboardLink: {
    marginHorizontal: layout.screenPadding,
    marginTop: 28,
    padding: 16,
    backgroundColor: colors.ink,
    borderRadius: 8,
    alignItems: 'center',
  },
  dashboardText: {
    fontFamily: fonts.bodyMedium,
    fontSize: 15,
    color: colors.parchment,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  dashboardHint: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: 'rgba(247, 244, 236, 0.5)',
    marginTop: 4,
  },
});
