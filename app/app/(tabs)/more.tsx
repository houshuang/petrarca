import { useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, Platform, Linking,
} from 'react-native';
import { useRouter, useFocusEffect } from 'expo-router';
import { colors, fonts, type, layout } from '../../design/tokens';
import { logEvent } from '../../data/logger';
import { setFeedbackContext } from '../../lib/feedback-context';
import { showFeedbackButton } from '../../components/FeedbackCapture';
import DoubleRule from '../../components/DoubleRule';
import { getGuideUrl } from '../../lib/server-urls';

export default function MoreTab() {
  const router = useRouter();

  useFocusEffect(
    useCallback(() => {
      logEvent('more_tab_open');
      setFeedbackContext({ screen: 'more-tab' });
    }, [])
  );

  const navigate = useCallback(
    (item: string, path: string) => {
      logEvent('more_item_tap', { item });
      router.push(path as any);
    },
    [router],
  );

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <View style={styles.header}>
        <Text style={styles.title}>More</Text>
      </View>

      <DoubleRule />

      {/* Explore */}
      <Text style={styles.sectionLabel}>Explore</Text>
      <NavItem
        title="Knowledge Map"
        subtitle="Your learning progress & gaps"
        onPress={() => navigate('knowledge_map', '/knowledge-map')}
      />
      <NavItem
        title="Knowledge Explorer"
        subtitle="Timeline, persons & places"
        onPress={() => navigate('timeline', '/timeline')}
      />
      <NavItem
        title="Ancient Map"
        subtitle="Places from your curriculum"
        onPress={() => navigate('map', '/map')}
      />

      {/* Tools */}
      <Text style={styles.sectionLabel}>Tools</Text>
      <NavItem
        title="Projects"
        subtitle="Collect notes around a theme"
        onPress={() => navigate('projects', '/projects')}
      />
      <NavItem
        title="Activity Log"
        subtitle="Pipeline activity & events"
        onPress={() => navigate('activity_log', '/(tabs)/log')}
      />

      {/* System */}
      <Text style={styles.sectionLabel}>System</Text>
      <NavItem
        title="User Guide"
        subtitle="How everything works"
        onPress={() => {
          logEvent('more_item_tap', { item: 'user_guide' });
          Linking.openURL(getGuideUrl());
        }}
      />
      <NavItem
        title="Show Feedback Button"
        subtitle="Re-enable the \u2726 feedback capture"
        onPress={() => {
          logEvent('more_item_tap', { item: 'show_feedback' });
          showFeedbackButton();
        }}
      />
    </ScrollView>
  );
}

function NavItem({
  title,
  subtitle,
  onPress,
}: {
  title: string;
  subtitle: string;
  onPress: () => void;
}) {
  return (
    <Pressable style={styles.navItem} onPress={onPress}>
      <View style={styles.navLeft}>
        <Text style={styles.navTitle}>{title}</Text>
        <Text style={styles.navSubtitle}>{subtitle}</Text>
      </View>
      <Text style={styles.navChevron}>{'\u203A'}</Text>
    </Pressable>
  );
}

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
  sectionLabel: {
    ...type.sectionHead,
    color: colors.textMuted,
    paddingHorizontal: layout.screenPadding,
    marginTop: 20,
    marginBottom: 4,
  },
  navItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 14,
    paddingHorizontal: layout.screenPadding,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.rule,
  },
  navLeft: {
    flex: 1,
  },
  navTitle: {
    fontFamily: fonts.body,
    fontSize: 15,
    color: colors.ink,
  },
  navSubtitle: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: colors.textMuted,
    marginTop: 2,
  },
  navChevron: {
    fontFamily: fonts.ui,
    fontSize: 18,
    color: colors.textMuted,
    marginLeft: 8,
  },
});
