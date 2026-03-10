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

type SourceFilter = 'all' | 'mine' | 'server';

const FILTERS: { key: SourceFilter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'mine', label: 'Mine' },
  { key: 'server', label: 'Server' },
];

/* ── helpers ── */

function isUserEvent(e: ActivityEvent) {
  return e.type === 'reading' || e.type === 'interest';
}

function isTappable(e: ActivityEvent) {
  return e.type === 'reading' && !!e.article_id;
}

const DOT_COLORS: Record<string, string> = {
  'reading/finished': colors.claimNew,
  'reading/in_progress': colors.rubric,
  'reading/dismissed': colors.textMuted,
  'reading/queued': colors.rubric,
  'system/pipeline': colors.info,
  'system/pipeline_step': colors.info,
  'system/ingest': colors.claimNew,
  'system/processed': colors.claimNew,
  'system/fetch': colors.info,
  'system/in_progress': colors.info,
  'research/dispatched': colors.research,
  'research/completed': colors.research,
};

function getDotColor(e: ActivityEvent): string {
  return DOT_COLORS[`${e.type}/${e.subtype}`] || colors.textMuted;
}

function getDayLabel(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const eventDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const diffDays = Math.round((today.getTime() - eventDay.getTime()) / 86400000);
  if (diffDays === 0) return 'TODAY';
  if (diffDays === 1) return 'YESTERDAY';
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }).toUpperCase();
}

function getTimeLabel(ts: string): string {
  return new Date(ts).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
}

function getDisplayTitle(e: ActivityEvent): string {
  if (e.type === 'interest') {
    const parts = [
      ...(e.topics_positive || []).map(t => `+${t}`),
      ...(e.topics_negative || []).map(t => `−${t}`),
    ];
    return parts.length > 0 ? parts.join('  ') : e.title;
  }
  return e.title;
}

function getRightMeta(e: ActivityEvent): string {
  const time = getTimeLabel(e.ts);
  if (e.type === 'reading' && e.subtitle) {
    const durMatch = e.subtitle.match(/^(\d+ min|<1 min)/);
    if (durMatch) return `${durMatch[1]} · ${time}`;
  }
  return time;
}

/* ── list items ── */

type ListItem =
  | { kind: 'day'; label: string; key: string }
  | { kind: 'event'; event: ActivityEvent; key: string };

function buildListItems(events: ActivityEvent[]): ListItem[] {
  const items: ListItem[] = [];
  let currentDay = '';
  for (const ev of events) {
    const day = getDayLabel(ev.ts);
    if (day !== currentDay) {
      currentDay = day;
      items.push({ kind: 'day', label: day, key: `day-${day}` });
    }
    items.push({ kind: 'event', event: ev, key: ev.id });
  }
  return items;
}

/* ── components ── */

function DaySeparator({ label }: { label: string }) {
  return (
    <View style={s.dayRow}>
      <View style={s.dayLine} />
      <Text style={s.dayText}>{label}</Text>
      <View style={s.dayLine} />
    </View>
  );
}

function EventRow({ event, onPress }: {
  event: ActivityEvent;
  onPress?: () => void;
}) {
  const server = !isUserEvent(event);
  const ring = event.type === 'reading' && event.subtype === 'in_progress';
  const interest = event.type === 'interest';
  const dismissed = event.subtype === 'dismissed';
  const dotColor = getDotColor(event);
  const title = getDisplayTitle(event);
  const meta = getRightMeta(event);
  const tappable = isTappable(event);

  const row = (
    <View style={s.row}>
      <View style={s.dotCol}>
        {interest ? (
          <Text style={s.star}>{'\u2726'}</Text>
        ) : ring ? (
          <View style={[s.dotRing, { borderColor: dotColor }]} />
        ) : (
          <View style={[s.dot, { backgroundColor: dotColor }]} />
        )}
      </View>

      <Text
        style={[
          s.title,
          server && s.titleServer,
          dismissed && s.titleDismissed,
        ]}
        numberOfLines={1}
      >
        {title}
      </Text>

      <Text style={s.meta}>{meta}</Text>
    </View>
  );

  if (tappable && onPress) {
    return (
      <Pressable
        onPress={onPress}
        style={({ pressed, hovered }: any) => [
          pressed && { opacity: 0.6 },
          hovered && Platform.OS === 'web' && s.rowHover,
        ]}
      >
        {row}
      </Pressable>
    );
  }
  return row;
}

/* ── main screen ── */

export default function LogScreen() {
  const router = useRouter();
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [filter, setFilter] = useState<SourceFilter>('all');
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
      if (ok) await fetchEvents(7);
    })();
    return () => { cancelled = true; };
  }, [fetchEvents]);

  const filteredEvents = useMemo(() => {
    if (filter === 'mine') return events.filter(isUserEvent);
    if (filter === 'server') return events.filter(e => !isUserEvent(e));
    return events;
  }, [events, filter]);

  const listItems = useMemo(() => buildListItems(filteredEvents), [filteredEvents]);

  const handleFilterChange = useCallback((key: SourceFilter) => {
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
    if (item.kind === 'day') return <DaySeparator label={item.label} />;
    return (
      <EventRow
        event={item.event}
        onPress={isTappable(item.event) ? () => handleNodeTap(item.event) : undefined}
      />
    );
  }, [handleNodeTap]);

  return (
    <View style={s.container}>
      <View style={s.header}>
        <View style={s.headerRow}>
          <Text style={s.headerTitle}>Activity</Text>
          <Pressable onPress={() => router.push('/')} hitSlop={8}>
            <Text style={s.backLink}>← Feed</Text>
          </Pressable>
        </View>
      </View>
      <View style={s.doubleRule}>
        <View style={s.ruleTop} />
        <View style={{ height: layout.doubleRuleGap }} />
        <View style={s.ruleBottom} />
      </View>

      <View style={s.filterRow}>
        {FILTERS.map(f => (
          <Pressable key={f.key} onPress={() => handleFilterChange(f.key)} style={s.filterItem}>
            <Text style={[s.filterLabel, filter === f.key && s.filterActive]}>
              {f.label}
            </Text>
          </Pressable>
        ))}
      </View>

      {loading ? (
        <View style={s.center}>
          <Text style={s.loadingText}>Loading…</Text>
        </View>
      ) : error && events.length === 0 ? (
        <View style={s.center}>
          <Text style={s.errorText}>Could not load activity</Text>
          <Pressable
            onPress={() => {
              setLoading(true);
              setError(false);
              fetchEvents(7, true).then(() => setLoading(false));
            }}
            style={s.retryBtn}
          >
            <Text style={s.retryText}>Retry</Text>
          </Pressable>
        </View>
      ) : filteredEvents.length === 0 ? (
        <View style={s.center}>
          <Text style={s.emptyText}>No activity</Text>
        </View>
      ) : (
        <FlatList
          data={listItems}
          keyExtractor={item => item.key}
          renderItem={renderItem}
          contentContainerStyle={s.listContent}
          showsVerticalScrollIndicator={false}
        />
      )}
    </View>
  );
}

/* ── styles ── */

const DOT_SIZE = 6;

const s = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.parchment,
  },

  header: {
    paddingHorizontal: layout.screenPadding,
    paddingTop: 12,
    paddingBottom: 6,
  },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
  },
  headerTitle: {
    ...type.screenTitle,
    color: colors.ink,
    fontSize: 22,
  },
  backLink: {
    fontFamily: fonts.ui,
    fontSize: 12,
    color: colors.rubric,
    letterSpacing: 0.3,
  },

  doubleRule: {
    paddingHorizontal: layout.screenPadding,
  },
  ruleTop: {
    borderTopWidth: layout.doubleRuleTop,
    borderTopColor: colors.ink,
  },
  ruleBottom: {
    borderTopWidth: layout.doubleRuleBottom,
    borderTopColor: colors.ink,
  },

  filterRow: {
    flexDirection: 'row',
    paddingHorizontal: layout.screenPadding,
    paddingTop: spacing.sm,
    paddingBottom: spacing.xs,
    gap: spacing.lg,
  },
  filterItem: {
    paddingVertical: 4,
    paddingHorizontal: 2,
  },
  filterLabel: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  filterActive: {
    color: colors.ink,
    ...(Platform.OS === 'web' ? { fontWeight: '600' } : {}),
  },

  listContent: {
    paddingBottom: 40,
  },

  dayRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    paddingHorizontal: layout.screenPadding,
    gap: spacing.sm,
  },
  dayLine: {
    flex: 1,
    height: StyleSheet.hairlineWidth,
    backgroundColor: colors.rule,
  },
  dayText: {
    fontFamily: fonts.ui,
    fontSize: 10,
    letterSpacing: 1.5,
    color: colors.textMuted,
  },

  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 5,
    paddingHorizontal: layout.screenPadding,
    minHeight: 28,
  },
  rowHover: {
    backgroundColor: 'rgba(139,37,0,0.03)',
  },
  dotCol: {
    width: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dot: {
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
  star: {
    fontSize: 10,
    color: colors.rubric,
    lineHeight: 12,
  },
  title: {
    flex: 1,
    fontFamily: fonts.body,
    fontSize: 13,
    lineHeight: 18,
    color: colors.textPrimary,
  },
  titleServer: {
    color: colors.textSecondary,
    fontFamily: fonts.reading,
    fontSize: 12.5,
  },
  titleDismissed: {
    color: colors.textMuted,
  },
  meta: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.textMuted,
    marginLeft: spacing.sm,
    flexShrink: 0,
  },

  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingBottom: 100,
  },
  loadingText: {
    fontFamily: fonts.readingItalic,
    fontSize: 14,
    color: colors.textSecondary,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' } : {}),
  },
  errorText: {
    fontFamily: fonts.reading,
    fontSize: 14,
    color: colors.textSecondary,
    marginBottom: spacing.md,
  },
  retryBtn: {
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
    fontSize: 14,
    color: colors.textMuted,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' } : {}),
  },
});
