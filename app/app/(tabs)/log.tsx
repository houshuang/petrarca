import { useState, useEffect, useMemo, useCallback } from 'react';
import {
  View, Text, StyleSheet, FlatList, Pressable, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { logEvent } from '../../data/logger';
import { colors, fonts, type, spacing, layout } from '../../design/tokens';

const API_BASE = 'http://alifstian.duckdns.org:8090';

type ActivityEvent = {
  id: string;
  type: 'reading' | 'system' | 'research' | 'interest';
  subtype: string;
  ts: string;
  title: string;
  subtitle?: string;
  article_id?: string;
  topics_positive?: string[];
  topics_negative?: string[];
  meta?: Record<string, any>;
};

type FilterKey = 'all' | 'reading' | 'system' | 'research';

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'reading', label: 'Reading' },
  { key: 'system', label: 'System' },
  { key: 'research', label: 'Research' },
];

const DOT_COLORS: Record<string, string> = {
  'reading/finished': colors.claimNew,
  'reading/in_progress': colors.rubric,
  'reading/dismissed': colors.textMuted,
  'system': colors.info,
  'research/dispatched': colors.research,
  'research/completed': colors.research,
};

function getDotColor(event: ActivityEvent): string {
  const specific = `${event.type}/${event.subtype}`;
  return DOT_COLORS[specific] || DOT_COLORS[event.type] || colors.textMuted;
}

function isRingDot(event: ActivityEvent): boolean {
  return event.type === 'reading' && event.subtype === 'in_progress';
}

function isInterestEvent(event: ActivityEvent): boolean {
  return event.type === 'interest';
}

function isTappable(event: ActivityEvent): boolean {
  return (event.type === 'reading' && !!event.article_id);
}

function getDayLabel(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const eventDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const diffMs = today.getTime() - eventDay.getTime();
  const diffDays = Math.round(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function getTimeLabel(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
}

type ListItem =
  | { kind: 'day'; label: string; key: string }
  | { kind: 'event'; event: ActivityEvent; isLast: boolean; key: string };

function buildListItems(events: ActivityEvent[]): ListItem[] {
  const items: ListItem[] = [];
  let currentDay = '';

  for (let i = 0; i < events.length; i++) {
    const ev = events[i];
    const dayLabel = getDayLabel(ev.ts);
    if (dayLabel !== currentDay) {
      currentDay = dayLabel;
      items.push({ kind: 'day', label: dayLabel, key: `day-${dayLabel}` });
    }
    const nextDay = i + 1 < events.length ? getDayLabel(events[i + 1].ts) : null;
    const isLast = nextDay !== currentDay;
    items.push({ kind: 'event', event: ev, isLast, key: ev.id });
  }

  return items;
}

// --- Components ---

function DaySeparator({ label }: { label: string }) {
  return (
    <View style={styles.daySeparator}>
      <View style={styles.daySeparatorLine} />
      <Text style={styles.daySeparatorText}>{label}</Text>
      <View style={styles.daySeparatorLine} />
    </View>
  );
}

function TimelineNode({ event, isLast, onPress }: {
  event: ActivityEvent;
  isLast: boolean;
  onPress?: () => void;
}) {
  const interest = isInterestEvent(event);
  const ring = isRingDot(event);
  const dotColor = getDotColor(event);
  const tappable = isTappable(event);

  const content = (
    <View style={styles.nodeRow}>
      {/* Timeline column */}
      <View style={styles.timelineColumn}>
        {interest ? (
          <Text style={styles.interestMarker}>{'\u2726'}</Text>
        ) : ring ? (
          <View style={[styles.dotRing, { borderColor: dotColor }]} />
        ) : (
          <View style={[styles.dotFilled, { backgroundColor: dotColor }]} />
        )}
        {!isLast && <View style={styles.verticalLine} />}
      </View>

      {/* Content column */}
      <View style={styles.contentColumn}>
        {interest ? (
          <InterestContent event={event} />
        ) : (
          <>
            <Text style={[
              styles.nodeTitle,
              event.type === 'system' && styles.nodeTitleSystem,
            ]} numberOfLines={2}>
              {event.title}
            </Text>
            {event.subtitle ? (
              <Text style={styles.nodeSubtitle} numberOfLines={1}>
                {event.subtitle}
              </Text>
            ) : null}
          </>
        )}
        <Text style={styles.nodeTime}>{getTimeLabel(event.ts)}</Text>
      </View>
    </View>
  );

  if (tappable) {
    return (
      <Pressable
        onPress={onPress}
        style={({ pressed }) => pressed ? { opacity: 0.7 } : undefined}
      >
        {content}
      </Pressable>
    );
  }

  return content;
}

function InterestContent({ event }: { event: ActivityEvent }) {
  return (
    <View style={styles.interestContent}>
      {(event.topics_positive || []).map(t => (
        <Text key={`pos-${t}`} style={styles.interestPositive}>{t}</Text>
      ))}
      {(event.topics_negative || []).map(t => (
        <Text key={`neg-${t}`} style={styles.interestNegative}>{t}</Text>
      ))}
      {event.title ? (
        <Text style={styles.nodeSubtitle}>{event.title}</Text>
      ) : null}
    </View>
  );
}

// --- Main Screen ---

export default function LogScreen() {
  const router = useRouter();
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [filter, setFilter] = useState<FilterKey>('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const fetchEvents = useCallback(async (days: number, replace = false) => {
    try {
      const res = await fetch(`${API_BASE}/activity/feed?days=${days}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const fetched: ActivityEvent[] = data.events || [];
      if (replace) {
        setEvents(fetched);
      } else {
        setEvents(prev => {
          // Merge: new data replaces any overlapping IDs
          const newIds = new Set(fetched.map(e => e.id));
          const kept = prev.filter(e => !newIds.has(e.id));
          const merged = [...fetched, ...kept];
          merged.sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime());
          return merged;
        });
      }
      setError(false);
      return true;
    } catch {
      setError(true);
      return false;
    }
  }, []);

  useEffect(() => {
    logEvent('log_screen_open');
    let cancelled = false;

    (async () => {
      setLoading(true);
      const ok = await fetchEvents(1, true);
      if (cancelled) return;
      setLoading(false);

      if (ok) {
        // Background fetch for full week
        await fetchEvents(7);
      }
    })();

    return () => { cancelled = true; };
  }, [fetchEvents]);

  const filteredEvents = useMemo(() => {
    if (filter === 'all') return events;
    if (filter === 'reading') return events.filter(e => e.type === 'reading');
    if (filter === 'system') return events.filter(e => e.type === 'system');
    if (filter === 'research') return events.filter(e => e.type === 'research' || e.type === 'interest');
    return events;
  }, [events, filter]);

  const listItems = useMemo(() => buildListItems(filteredEvents), [filteredEvents]);

  const handleFilterChange = useCallback((key: FilterKey) => {
    setFilter(key);
    logEvent('log_filter_change', { filter: key });
  }, []);

  const handleNodeTap = useCallback((event: ActivityEvent) => {
    logEvent('log_node_tap', { event_type: event.type, event_id: event.id, article_id: event.article_id });
    if (event.type === 'reading' && event.article_id) {
      router.push({ pathname: '/reader', params: { id: event.article_id } });
    }
  }, [router]);

  const renderItem = useCallback(({ item }: { item: ListItem }) => {
    if (item.kind === 'day') {
      return <DaySeparator label={item.label} />;
    }
    return (
      <TimelineNode
        event={item.event}
        isLast={item.isLast}
        onPress={isTappable(item.event) ? () => handleNodeTap(item.event) : undefined}
      />
    );
  }, [handleNodeTap]);

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Petrarca</Text>
        <Text style={styles.headerSubtitle}>activity log</Text>
      </View>

      <View style={styles.doubleRule}>
        <View style={styles.doubleRuleTop} />
        <View style={styles.doubleRuleGap} />
        <View style={styles.doubleRuleBottom} />
      </View>

      {/* Filter row */}
      <View style={styles.filterRow}>
        {FILTERS.map(f => (
          <Pressable
            key={f.key}
            onPress={() => handleFilterChange(f.key)}
            style={styles.filterItem}
          >
            <Text style={[
              styles.filterLabel,
              filter === f.key && styles.filterLabelActive,
            ]}>
              {f.label}
            </Text>
            {filter === f.key && <View style={styles.filterUnderline} />}
          </Pressable>
        ))}
      </View>

      {loading ? (
        <View style={styles.statusContainer}>
          <Text style={styles.loadingText}>Loading...</Text>
        </View>
      ) : error && events.length === 0 ? (
        <View style={styles.statusContainer}>
          <Text style={styles.errorText}>Could not load activity</Text>
          <Pressable
            onPress={() => {
              setLoading(true);
              setError(false);
              fetchEvents(7, true).then(() => setLoading(false));
            }}
            style={styles.retryButton}
          >
            <Text style={styles.retryText}>Retry</Text>
          </Pressable>
        </View>
      ) : filteredEvents.length === 0 ? (
        <View style={styles.statusContainer}>
          <Text style={styles.emptyText}>No activity yet</Text>
        </View>
      ) : (
        <FlatList
          data={listItems}
          keyExtractor={item => item.key}
          renderItem={renderItem}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
        />
      )}
    </View>
  );
}

const DOT_SIZE = 8;
const TIMELINE_WIDTH = 28;

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.parchment,
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

  // Double rule
  doubleRule: {
    paddingHorizontal: layout.screenPadding,
  },
  doubleRuleTop: {
    borderTopWidth: layout.doubleRuleTop,
    borderTopColor: colors.ink,
  },
  doubleRuleGap: {
    height: layout.doubleRuleGap,
  },
  doubleRuleBottom: {
    borderTopWidth: layout.doubleRuleBottom,
    borderTopColor: colors.ink,
  },

  // Filter row
  filterRow: {
    flexDirection: 'row',
    paddingHorizontal: layout.screenPadding,
    paddingTop: spacing.md,
    paddingBottom: spacing.sm,
    gap: spacing.lg,
  },
  filterItem: {
    alignItems: 'center',
    minHeight: 32,
  },
  filterLabel: {
    fontFamily: fonts.body,
    fontSize: 13,
    color: colors.textMuted,
  },
  filterLabelActive: {
    color: colors.ink,
  },
  filterUnderline: {
    marginTop: 3,
    width: '100%',
    height: 2,
    backgroundColor: colors.rubric,
  },

  // Status states
  statusContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingBottom: 100,
  },
  loadingText: {
    fontFamily: fonts.readingItalic,
    fontSize: 15,
    color: colors.textSecondary,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' } : {}),
  },
  errorText: {
    fontFamily: fonts.reading,
    fontSize: 15,
    color: colors.textSecondary,
    marginBottom: spacing.md,
  },
  retryButton: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: colors.rubric,
  },
  retryText: {
    fontFamily: fonts.ui,
    fontSize: 12,
    color: colors.rubric,
  },
  emptyText: {
    fontFamily: fonts.readingItalic,
    fontSize: 15,
    color: colors.textMuted,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' } : {}),
  },

  // List
  listContent: {
    paddingHorizontal: layout.screenPadding,
    paddingBottom: 40,
  },

  // Day separator
  daySeparator: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.md,
    gap: spacing.md,
  },
  daySeparatorLine: {
    flex: 1,
    height: StyleSheet.hairlineWidth,
    backgroundColor: colors.rule,
  },
  daySeparatorText: {
    ...type.sectionHead,
    color: colors.textMuted,
  },

  // Timeline node
  nodeRow: {
    flexDirection: 'row',
    minHeight: 48,
  },
  timelineColumn: {
    width: TIMELINE_WIDTH,
    alignItems: 'center',
    paddingTop: 4,
  },
  dotFilled: {
    width: DOT_SIZE,
    height: DOT_SIZE,
    borderRadius: DOT_SIZE / 2,
  },
  dotRing: {
    width: DOT_SIZE,
    height: DOT_SIZE,
    borderRadius: DOT_SIZE / 2,
    borderWidth: 1.5,
    backgroundColor: 'transparent',
  },
  interestMarker: {
    fontSize: 12,
    color: colors.rubric,
    lineHeight: 14,
    marginTop: -1,
  },
  verticalLine: {
    flex: 1,
    width: 1,
    backgroundColor: colors.rule,
    marginTop: 4,
  },
  contentColumn: {
    flex: 1,
    paddingBottom: spacing.md,
    paddingLeft: spacing.sm,
  },
  nodeTitle: {
    fontFamily: fonts.bodyMedium,
    fontSize: 14,
    lineHeight: 19,
    color: colors.textPrimary,
    ...(Platform.OS === 'web' ? { fontWeight: '500' } : {}),
  },
  nodeTitleSystem: {
    fontFamily: fonts.reading,
    fontSize: 13.5,
    ...(Platform.OS === 'web' ? { fontWeight: 'normal' } : {}),
  },
  nodeSubtitle: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.textMuted,
    marginTop: 2,
  },
  nodeTime: {
    ...type.metadata,
    color: colors.textMuted,
    marginTop: spacing.xs,
  },

  // Interest-specific
  interestContent: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  interestPositive: {
    fontFamily: fonts.ui,
    fontSize: 12,
    color: colors.claimNew,
  },
  interestNegative: {
    fontFamily: fonts.ui,
    fontSize: 12,
    color: colors.textMuted,
    textDecorationLine: 'line-through',
  },
});
