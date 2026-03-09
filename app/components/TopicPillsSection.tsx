import { View, Text, Pressable, StyleSheet, ScrollView, Platform } from 'react-native';
import { colors, fonts, layout } from '../design/tokens';
import { logEvent } from '../data/logger';
import { getArticlesGroupedByTopic } from '../data/store';
import { displayTopic } from '../lib/display-utils';

interface TopicPillsSectionProps {
  onTopicPress: (topic: string) => void;
  onSeeAll: () => void;
}

export default function TopicPillsSection({ onTopicPress, onSeeAll }: TopicPillsSectionProps) {
  const groups = getArticlesGroupedByTopic();
  if (groups.length === 0) return null;

  const topGroups = groups.slice(0, 8);

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.sectionLabel}>
          <Text style={{ color: colors.rubric }}>{'\u2726'} </Text>
          Topics
        </Text>
        <Pressable onPress={onSeeAll} hitSlop={8}>
          <Text style={styles.seeAll}>All topics ›</Text>
        </Pressable>
      </View>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.pills}
      >
        {topGroups.map(({ topic, articles }, index) => (
          <Pressable
            key={topic}
            style={[styles.pill, index === 0 && styles.pillPrimary]}
            onPress={() => {
              logEvent('topic_pill_tap', { topic });
              onTopicPress(topic);
            }}
          >
            <Text
              style={[styles.pillLabel, index === 0 && styles.pillLabelPrimary]}
              numberOfLines={1}
            >
              {displayTopic(topic)}
            </Text>
            {/* No article counts — "this is a river, not a todo list" */}
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingTop: 10,
    paddingBottom: 6,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: layout.screenPadding,
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
  pills: {
    paddingHorizontal: layout.screenPadding,
    gap: 8,
  },
  pill: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.rule,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  pillPrimary: {
    backgroundColor: colors.ink,
    borderColor: colors.ink,
  },
  pillLabel: {
    fontFamily: fonts.body,
    fontSize: 13,
    color: colors.textBody,
  },
  pillLabelPrimary: {
    color: colors.parchment,
  },
});
