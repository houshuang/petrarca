import { useMemo } from 'react';
import { View, Text, Pressable, StyleSheet, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import { colors, fonts, layout } from '../design/tokens';
import { logEvent } from '../data/logger';
import { getDisplayTitle } from '../lib/display-utils';
import { getDeskArticle, getActiveThreads, getReadingStats } from '../lib/reading-insights';
import type { ReadingThread } from '../lib/reading-insights';

interface Props {
  onDrawerOpen: () => void;
}

export default function ReadingDeskHeader({ onDrawerOpen }: Props) {
  const router = useRouter();
  const desk = useMemo(() => getDeskArticle(), []);
  const threads = useMemo(() => getActiveThreads(4), []);
  const stats = useMemo(() => getReadingStats(7), []);

  // Only show desk card if there's an in-progress article
  if (!desk) return null;

  const { article, state, excerpt } = desk;
  const title = getDisplayTitle(article);
  const source = article.source_url?.replace(/^https?:\/\/(www\.)?/, '').split('/')[0] || '';
  const contentLength = article.content_markdown?.length || 5000;
  const progress = state.scroll_position_y
    ? Math.min(99, Math.round((state.scroll_position_y / (contentLength / 50)) * 100))
    : 0;
  const lastReadAgo = state.last_read_at
    ? formatTimeAgo(state.last_read_at)
    : '';

  return (
    <View style={styles.container}>
      {/* Open on your desk */}
      <Text style={styles.sectionLabel}>✦ Open on your desk</Text>
      <Pressable
        style={styles.deskCard}
        onPress={() => {
          logEvent('desk_resume_tap', { article_id: article.id });
          router.push({ pathname: '/reader', params: { id: article.id } });
        }}
      >
        <View style={styles.deskMain}>
          <Text style={styles.deskTitle} numberOfLines={2}>{title}</Text>
          <Text style={styles.deskMeta}>
            {source}{source ? ' · ' : ''}{article.estimated_read_minutes} min{lastReadAgo ? ` · started ${lastReadAgo}` : ''}
          </Text>
          {excerpt && (
            <Text style={styles.deskExcerpt} numberOfLines={2}>
              <Text style={styles.excerptMarker}>↳ </Text>{excerpt}
            </Text>
          )}
          <View style={styles.deskActions}>
            <View style={styles.btnPrimary}>
              <Text style={styles.btnPrimaryText}>Continue reading</Text>
            </View>
          </View>
        </View>

        {Platform.OS === 'web' && (
          <View style={styles.deskSidebar}>
            <View style={styles.progressBarTrack}>
              <View style={[styles.progressBarFill, { width: `${Math.max(5, progress)}%` as any }]} />
            </View>
            <Text style={styles.sidebarStat}>{progress > 0 ? `${progress}% read` : 'Just started'}</Text>
            <Text style={styles.sidebarStat}>~{Math.max(1, article.estimated_read_minutes - Math.round(state.time_spent_ms / 60000))} min left</Text>
          </View>
        )}
      </Pressable>

      {/* Threads you're following */}
      {threads.length > 1 && (
        <>
          <Text style={[styles.sectionLabel, { marginTop: 24 }]}>✦ Threads you're following</Text>
          <View style={styles.threadList}>
            {threads.slice(0, 3).map(thread => (
              <ThreadRow key={thread.topic} thread={thread} />
            ))}
          </View>
          {threads.length > 3 && (
            <Pressable onPress={() => {
              logEvent('desk_see_all_trails');
              router.push('/trails' as any);
            }}>
              <Text style={styles.seeAll}>See all trails ›</Text>
            </Pressable>
          )}
        </>
      )}
    </View>
  );
}

function ThreadRow({ thread }: { thread: ReadingThread }) {
  const router = useRouter();
  return (
    <Pressable
      style={styles.threadItem}
      onPress={() => {
        logEvent('desk_thread_tap', { topic: thread.topic });
        router.push('/trails' as any);
      }}
    >
      <View style={styles.threadLeft}>
        <Text style={styles.threadTopic}>{thread.topic}</Text>
        <View style={styles.threadDotRow}>
          {thread.articles.slice(0, 8).map((a, i) => (
            <View
              key={i}
              style={[
                styles.threadDot,
                a.status === 'read' && styles.threadDotRead,
                a.status === 'reading' && styles.threadDotReading,
                a.status === 'unread' && styles.threadDotUnread,
              ]}
            />
          ))}
        </View>
      </View>
      <View style={styles.threadRight}>
        <Text style={styles.threadCount}>{thread.totalArticles}</Text>
        {thread.unreadCount > 0 && (
          <Text style={styles.threadUnread}>{thread.unreadCount} unread</Text>
        )}
      </View>
    </Pressable>
  );
}

function formatTimeAgo(timestamp: number): string {
  const hours = Math.floor((Date.now() - timestamp) / 3600000);
  if (hours < 1) return 'just now';
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return 'yesterday';
  return `${days}d ago`;
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: layout.screenPadding,
    paddingBottom: 8,
  },
  sectionLabel: {
    fontFamily: fonts.bodyItalic,
    fontSize: 12,
    color: colors.rubric,
    marginBottom: 12,
  },

  // Desk card
  deskCard: {
    flexDirection: 'row',
    gap: 20,
    paddingBottom: 20,
    borderBottomWidth: 1,
    borderBottomColor: colors.rule,
    ...(Platform.OS === 'web' ? { cursor: 'pointer' as any } : {}),
  },
  deskMain: { flex: 1 },
  deskTitle: {
    fontFamily: fonts.displaySemiBold,
    fontSize: 20,
    color: colors.ink,
    lineHeight: 26,
    marginBottom: 6,
    ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}),
  },
  deskMeta: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.textMuted,
    marginBottom: 10,
  },
  deskExcerpt: {
    fontFamily: fonts.readingItalic,
    fontSize: 14,
    lineHeight: 21,
    color: colors.textSecondary,
    marginBottom: 14,
  },
  excerptMarker: {
    color: colors.rubric,
    fontStyle: 'normal',
  },
  deskActions: {
    flexDirection: 'row',
    gap: 14,
    alignItems: 'center',
  },
  btnPrimary: {
    backgroundColor: colors.ink,
    paddingVertical: 8,
    paddingHorizontal: 20,
    borderRadius: 2,
  },
  btnPrimaryText: {
    fontFamily: fonts.body,
    fontSize: 13,
    color: colors.parchment,
  },

  // Sidebar (web only)
  deskSidebar: {
    width: 140,
    alignItems: 'flex-end',
    gap: 4,
  } as any,
  progressBarTrack: {
    width: '100%',
    height: 4,
    backgroundColor: colors.rule,
    borderRadius: 2,
    overflow: 'hidden',
    marginBottom: 4,
  } as any,
  progressBarFill: {
    height: '100%',
    backgroundColor: colors.rubric,
    borderRadius: 2,
  } as any,
  sidebarStat: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: colors.textMuted,
    textAlign: 'right',
  } as any,

  // Threads
  threadList: {
    gap: 0,
  },
  threadItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.rule,
    ...(Platform.OS === 'web' ? { cursor: 'pointer' as any } : {}),
  },
  threadLeft: { flex: 1 },
  threadTopic: {
    fontFamily: fonts.bodyMedium,
    fontSize: 14,
    color: colors.ink,
    marginBottom: 4,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  threadDotRow: {
    flexDirection: 'row',
    gap: 3,
  },
  threadDot: {
    width: 7,
    height: 7,
    borderRadius: 3.5,
  },
  threadDotRead: { backgroundColor: colors.ink },
  threadDotReading: {
    backgroundColor: colors.parchment,
    borderWidth: 1.5,
    borderColor: colors.rubric,
  },
  threadDotUnread: { backgroundColor: colors.rule },
  threadRight: {
    alignItems: 'flex-end',
  },
  threadCount: {
    fontFamily: fonts.displaySemiBold,
    fontSize: 18,
    color: colors.ink,
    lineHeight: 22,
    ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}),
  },
  threadUnread: {
    fontFamily: fonts.ui,
    fontSize: 9,
    color: colors.claimNew,
  },
  seeAll: {
    fontFamily: fonts.body,
    fontSize: 12,
    color: colors.rubric,
    paddingVertical: 8,
    ...(Platform.OS === 'web' ? { cursor: 'pointer' as any } : {}),
  },
});
