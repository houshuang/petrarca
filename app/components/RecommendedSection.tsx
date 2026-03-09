import { View, Text, Pressable, StyleSheet, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import { colors, fonts, type, layout } from '../design/tokens';
import { logEvent } from '../data/logger';
import { getRankedFeedArticles, recordInterestSignal } from '../data/store';
import { getDisplayTitle } from '../lib/display-utils';
import { isKnowledgeReady, getArticleNovelty } from '../data/knowledge-engine';

interface RecommendedSectionProps {
  onSeeAll: () => void;
  excludeArticleId?: string;
}

export default function RecommendedSection({ onSeeAll, excludeArticleId }: RecommendedSectionProps) {
  const router = useRouter();
  // Pick the top-ranked article that isn't already shown in Up Next
  const ranked = getRankedFeedArticles();
  const article = ranked.find(a => a.id !== excludeArticleId) || ranked[0] || null;

  if (!article) return null;

  const novelty = isKnowledgeReady() ? getArticleNovelty(article.id) : null;
  const bestClaim = (article.novelty_claims || []).find(c => c.specificity === 'high')
    || (article.novelty_claims || [])[0];

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.sectionLabel}>
          <Text style={{ color: colors.rubric }}>{'\u2726'} </Text>
          Recommended
        </Text>
        <Pressable onPress={onSeeAll} hitSlop={8}>
          <Text style={styles.seeAll}>See all ›</Text>
        </Pressable>
      </View>

      <Pressable
        style={styles.card}
        onPress={() => {
          logEvent('recommended_tap', { article_id: article.id });
          recordInterestSignal('open_article', article.id);
          router.push({ pathname: '/reader', params: { id: article.id } });
        }}
      >
        <Text style={styles.title} numberOfLines={2}>
          {getDisplayTitle(article)}
        </Text>
        {article.one_line_summary ? (
          <Text style={styles.summary} numberOfLines={2}>
            {article.one_line_summary}
          </Text>
        ) : null}

        {bestClaim ? (
          <View style={styles.claimPreview}>
            <Text style={styles.claimText} numberOfLines={2}>
              {bestClaim.claim}
            </Text>
          </View>
        ) : null}

        <View style={styles.meta}>
          <Text style={styles.metaText}>
            {article.hostname}
            {` · ${article.estimated_read_minutes} min`}
          </Text>
          {novelty && novelty.novelty_ratio > 0.5 ? (
            <Text style={styles.noveltyBadge}>
              {Math.round(novelty.novelty_ratio * 100)}% new
            </Text>
          ) : null}
        </View>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: layout.screenPadding,
    paddingTop: 14,
    paddingBottom: 6,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  sectionLabel: {
    fontFamily: fonts.bodyMedium,
    fontSize: 11,
    letterSpacing: 1.6,
    textTransform: 'uppercase',
    color: colors.rubric,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
  seeAll: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.rubric,
  },
  card: {
    paddingBottom: 4,
  },
  title: {
    fontFamily: fonts.displaySemiBold,
    fontSize: 20,
    lineHeight: 25,
    color: colors.ink,
    marginBottom: 4,
    ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}),
  },
  summary: {
    fontFamily: fonts.reading,
    fontSize: 14,
    lineHeight: 20,
    color: colors.textSecondary,
    marginBottom: 8,
  },
  claimPreview: {
    borderLeftWidth: layout.claimBorderWidth,
    borderLeftColor: colors.claimNew,
    paddingLeft: 10,
    marginBottom: 8,
  },
  claimText: {
    fontFamily: fonts.reading,
    fontSize: 12.5,
    lineHeight: 18,
    color: colors.textBody,
  },
  meta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  metaText: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.textMuted,
  },
  noveltyBadge: {
    fontFamily: fonts.uiMedium,
    fontSize: 10,
    color: colors.claimNew,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
});
