import { View, Text, Pressable, StyleSheet, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import { colors, fonts, type, layout } from '../design/tokens';
import { logEvent } from '../data/logger';
import { getInProgressArticles, getArticleById, getTopRecommendedArticle, getReadingState, recordInterestSignal } from '../data/store';
import { getNextQueued } from '../data/queue';
import { getDisplayTitle } from '../lib/display-utils';

interface UpNextSectionProps {
  onDrawerOpen: () => void;
  isFocused?: boolean;
}

export default function UpNextSection({ onDrawerOpen, isFocused }: UpNextSectionProps) {
  const router = useRouter();

  const inProgress = getInProgressArticles();
  const current = inProgress[0];
  const nextQueuedId = getNextQueued();
  const nextQueued = nextQueuedId ? getArticleById(nextQueuedId) : null;

  // Determine what to show
  const displayArticle = current || nextQueued || getTopRecommendedArticle();
  const upNextType: 'resume' | 'queued' | 'algorithmic' = current
    ? 'resume'
    : nextQueued
      ? 'queued'
      : 'algorithmic';

  // Progress for in-progress articles
  const progressRatio = current
    ? (() => {
        const state = getReadingState(current.id);
        return state.time_spent_ms > 0
          ? Math.min(state.time_spent_ms / (current.estimated_read_minutes * 60 * 1000), 0.95)
          : 0.1;
      })()
    : 0;

  const subtitle = current && nextQueued
    ? `then: ${getDisplayTitle(nextQueued)}`
    : upNextType === 'queued'
      ? 'From your queue'
      : upNextType === 'algorithmic'
        ? 'Recommended for you'
        : undefined;

  if (!displayArticle) return null;

  return (
    <View style={[styles.container, isFocused && styles.containerFocused]}>
      <Pressable
        style={styles.content}
        onPress={() => {
          logEvent('up_next_tap', { article_id: displayArticle.id, type: upNextType });
          recordInterestSignal('open_article', displayArticle.id);
          router.push({ pathname: '/reader', params: { id: displayArticle.id } });
        }}
      >
        <View style={styles.left}>
          <Text style={styles.label}>
            {upNextType === 'resume' ? 'Continue' : 'Up Next'}
          </Text>
          <Text style={styles.title} numberOfLines={1}>
            {getDisplayTitle(displayArticle)}
          </Text>
          {subtitle && (
            <Text style={styles.subtitle} numberOfLines={1}>{subtitle}</Text>
          )}
          {current && (
            <View style={styles.progressTrack}>
              <View style={[styles.progressFill, { width: `${progressRatio * 100}%` }]} />
            </View>
          )}
        </View>
        <View style={styles.meta}>
          <Text style={styles.readTime}>
            {displayArticle.estimated_read_minutes} min
          </Text>
        </View>
      </Pressable>
      <Pressable
        style={styles.drawerButton}
        onPress={() => {
          logEvent('drawer_open');
          onDrawerOpen();
        }}
        hitSlop={8}
      >
        <Text style={styles.drawerIcon}>{'\u2726'}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: layout.screenPadding,
    paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.rule,
    gap: 12,
  },
  containerFocused: {
    borderLeftWidth: 3,
    borderLeftColor: colors.rubric,
    backgroundColor: 'rgba(139,37,0,0.03)',
  },
  content: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    minHeight: 44,
  },
  left: {
    flex: 1,
  },
  label: {
    fontFamily: fonts.uiMedium,
    fontSize: 9,
    letterSpacing: 1,
    textTransform: 'uppercase',
    color: colors.rubric,
    marginBottom: 2,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  title: {
    fontFamily: fonts.bodyMedium,
    fontSize: 14,
    lineHeight: 19,
    color: colors.textPrimary,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  subtitle: {
    fontFamily: fonts.reading,
    fontSize: 11,
    color: colors.textMuted,
    marginTop: 1,
  },
  meta: {
    alignItems: 'flex-end',
  },
  readTime: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: colors.textMuted,
  },
  progressTrack: {
    height: layout.progressBarHeight,
    backgroundColor: colors.rule,
    marginTop: 4,
  },
  progressFill: {
    height: layout.progressBarHeight,
    backgroundColor: colors.rubric,
  },
  drawerButton: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
  drawerIcon: {
    fontFamily: fonts.display,
    fontSize: 22,
    color: colors.rubric,
  },
});
