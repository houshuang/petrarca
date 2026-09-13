import { useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, Platform, Linking,
} from 'react-native';
import { useRouter, useFocusEffect, type Href } from 'expo-router';
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
    (item: string, path: Href) => {
      logEvent('more_item_tap', { item });
      router.push(path);
    },
    [router],
  );

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <View style={styles.header}>
        <Text accessibilityRole="header" style={styles.title}>Mer</Text>
        <Text style={styles.subtitle}>Verktøy du ikke trenger i den daglige økten.</Text>
      </View>

      <DoubleRule />

      <Text style={styles.sectionLabel}>Forstå sammenhenger</Text>
      <NavItem
        title="Kunnskapskart"
        subtitle="Se hva du har møtt og hvordan stoffet henger sammen"
        onPress={() => navigate('knowledge_map', '/knowledge-map')}
      />
      <NavItem
        title="Tidslinje og personer"
        subtitle="Utforsk tid, personer og steder"
        onPress={() => navigate('timeline', '/timeline')}
      />
      <NavItem
        title="Kart"
        subtitle="Finn steder fra læringsstoffet"
        onPress={() => navigate('map', '/map')}
      />

      <Text style={styles.sectionLabel}>Arbeid med stoffet</Text>
      <NavItem
        title="Prosjekter"
        subtitle="Samle notater rundt et tema"
        onPress={() => navigate('projects', '/projects')}
      />
      <NavItem
        title="Aktivitetslogg"
        subtitle="Se nylige hendelser og behandling"
        onPress={() => navigate('activity_log', '/(tabs)/log')}
      />

      <Text style={styles.sectionLabel}>Hjelp</Text>
      <NavItem
        title="Slik virker Petrarca"
        subtitle="Kort forklaring av appen"
        onPress={() => {
          logEvent('more_item_tap', { item: 'user_guide' });
          Linking.openURL(getGuideUrl());
        }}
      />
      <NavItem
        title="Vis tilbakemeldingsknappen"
        subtitle="Slå på \u2726-knappen igjen"
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
    <Pressable accessibilityRole="button" style={({pressed}) => [styles.navItem, pressed && styles.navItemPressed]} onPress={onPress}>
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
  subtitle: {
    ...type.screenSubtitle,
    color: colors.textSecondary,
    marginTop: 4,
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
  navItemPressed: {
    backgroundColor: colors.parchmentDark,
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
