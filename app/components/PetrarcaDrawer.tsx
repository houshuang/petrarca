import { useCallback } from 'react';
import { View, Text, StyleSheet, Pressable, Modal, Platform, Linking, ScrollView } from 'react-native';
import { useRouter, type Href } from 'expo-router';
import { logEvent } from '../data/logger';
import { colors, fonts } from '../design/tokens';
import { showFeedbackButton } from './FeedbackCapture';
import { getGuideUrl, getStatsDashboardUrl } from '../lib/server-urls';

interface PetrarcaDrawerProps {
  visible: boolean;
  onClose: () => void;
}

export default function PetrarcaDrawer({ visible, onClose }: PetrarcaDrawerProps) {
  const router = useRouter();

  const close = useCallback(() => {
    logEvent('drawer_close');
    onClose();
  }, [onClose]);

  const navigate = useCallback(
    (item: string, path: Href) => {
      logEvent('drawer_item_tap', { item });
      onClose();
      router.push(path);
    },
    [onClose, router],
  );

  const quickAction = useCallback(
    (item: string) => {
      logEvent('drawer_item_tap', { item });
      onClose();
      if (item === 'review') {
        router.push('/');
      } else if (item === 'voice_capture') {
        router.push('/voice-capture');
      }
    },
    [onClose, router],
  );

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={close}>
      <Pressable style={styles.backdrop} onPress={close}>
        <Pressable style={styles.sheet} onPress={(e) => e.stopPropagation()}>
          {/* Handle */}
          <View style={styles.handleWrap}>
            <View style={styles.handle} />
          </View>

          <ScrollView bounces={false} showsVerticalScrollIndicator={false}>
            {/* Header */}
            <View style={styles.header}>
              <Text style={styles.headerOrnament}>{'\u2726'}</Text>
              <Text style={styles.headerTitle}>Petrarca</Text>
            </View>

            {/* Quick actions */}
            <View style={styles.quickActions}>
              <Pressable accessibilityRole="button" style={({pressed}) => [styles.quickBox, pressed && styles.pressed]} onPress={() => quickAction('review')}>
                <Text style={styles.quickTitle}>Dagens økt</Text>
                <Text style={styles.quickSubtitle}>Fortsett der du slapp</Text>
              </Pressable>
              <Pressable accessibilityRole="button" style={({pressed}) => [styles.quickBox, pressed && styles.pressed]} onPress={() => quickAction('voice_capture')}>
                <Text style={styles.quickTitle}>Ta opp en tanke</Text>
                <Text style={styles.quickSubtitle}>Lagre det du nettopp lærte</Text>
              </Pressable>
            </View>

            <Text style={styles.sectionLabel}>Forstå sammenhenger</Text>
            <NavItem
              title="Kunnskapskart"
              subtitle="Se hva du har møtt og hvordan stoffet henger sammen"
              onPress={() => navigate('knowledge_map', '/knowledge-map')}
            />
            <NavItem
              title="Kunnskapssveip"
              subtitle="Fortell hva du husker på tvers av et tema"
              onPress={() => navigate('knowledge_sweep', '/knowledge-sweep')}
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

            <Text style={styles.sectionLabel}>Lesing</Text>
            <NavItem
              title="Kindle-bibliotek"
              subtitle="Se og organiser Kindle-bøkene dine"
              onPress={() => navigate('kindle_browse', '/kindle-browse')}
            />
            <NavItem
              title="Stemmeopptak"
              subtitle="Tanker du har spilt inn"
              onPress={() => navigate('voice_notes', '/voice-notes')}
            />
            <NavItem
              title="Prosjekter"
              subtitle="Samle notater rundt et tema"
              onPress={() => navigate('projects', '/projects')}
            />

            <Text style={styles.sectionLabel}>Hjelp og oversikt</Text>
            <NavItem
              title="Statistikk"
              subtitle="Fremgang og repetisjoner"
              onPress={() => {
                logEvent('drawer_item_tap', { item: 'statistics' });
                onClose();
                Linking.openURL(getStatsDashboardUrl());
              }}
            />
            <NavItem
              title="Aktivitetslogg"
              subtitle="Nylige hendelser og behandling"
              onPress={() => navigate('activity_log', '/log')}
            />
            <NavItem
              title="Slik virker Petrarca"
              subtitle="Kort forklaring av appen"
              onPress={() => {
                logEvent('drawer_item_tap', { item: 'user_guide' });
                onClose();
                Linking.openURL(getGuideUrl());
              }}
            />
            <NavItem
              title="Vis tilbakemeldingsknappen"
              subtitle="Slå på \u2726-knappen igjen"
              onPress={() => {
                logEvent('drawer_item_tap', { item: 'show_feedback' });
                showFeedbackButton();
                onClose();
              }}
            />
          </ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

function NavItem({
  title,
  subtitle,
  badge,
  onPress,
}: {
  title: string;
  subtitle: string;
  badge?: number;
  onPress: () => void;
}) {
  return (
    <Pressable accessibilityRole="button" style={({pressed}) => [styles.navItem, pressed && styles.pressed]} onPress={onPress}>
      <View style={styles.navLeft}>
        <View style={styles.navTitleRow}>
          <Text style={styles.navTitle}>{title}</Text>
          {badge !== undefined && (
            <Text style={styles.navBadge}>{badge}</Text>
          )}
        </View>
        <Text style={styles.navSubtitle}>{subtitle}</Text>
      </View>
      <Text style={styles.navChevron}>{'\u203A'}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.3)',
    justifyContent: 'flex-end',
    alignItems: 'center',
  },
  sheet: {
    backgroundColor: colors.ink,
    borderTopLeftRadius: 16,
    borderTopRightRadius: 16,
    paddingHorizontal: 20,
    paddingBottom: 36,
    width: '100%',
    maxWidth: 600,
    maxHeight: '85%',
  },

  handleWrap: {
    alignItems: 'center',
    paddingTop: 10,
    paddingBottom: 16,
  },
  handle: {
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: 'rgba(247, 244, 236, 0.2)',
  },

  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 20,
  },
  headerOrnament: {
    fontFamily: fonts.display,
    fontSize: 22,
    color: colors.rubric,
    ...(Platform.OS === 'web' ? {} : {}),
  },
  headerTitle: {
    fontFamily: fonts.displaySemiBold,
    fontSize: 20,
    color: colors.parchment,
    ...(Platform.OS === 'web' ? { fontWeight: '600' as const } : {}),
  },

  quickActions: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 20,
  },
  quickBox: {
    flex: 1,
    backgroundColor: 'rgba(247, 244, 236, 0.08)',
    padding: 14,
    borderRadius: 8,
  },
  pressed: {
    opacity: 0.68,
  },
  quickTitle: {
    fontFamily: fonts.body,
    fontSize: 14,
    color: colors.parchment,
  },
  quickSubtitle: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: 'rgba(247, 244, 236, 0.4)',
    marginTop: 2,
  },

  navItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 14,
    borderTopWidth: 1,
    borderTopColor: 'rgba(247, 244, 236, 0.08)',
  },
  navLeft: {
    flex: 1,
  },
  navTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  navTitle: {
    fontFamily: fonts.body,
    fontSize: 15,
    color: colors.parchment,
  },
  navBadge: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: 'rgba(247, 244, 236, 0.4)',
  },
  navSubtitle: {
    fontFamily: fonts.ui,
    fontSize: 10,
    color: 'rgba(247, 244, 236, 0.35)',
    marginTop: 2,
  },
  navChevron: {
    fontFamily: fonts.ui,
    fontSize: 14,
    color: 'rgba(247, 244, 236, 0.2)',
  },
  sectionLabel: {
    fontFamily: fonts.uiMedium,
    fontSize: 10,
    color: 'rgba(247, 244, 236, 0.3)',
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginTop: 16,
    marginBottom: 4,
    ...(Platform.OS === 'web' ? { fontWeight: '500' as const } : {}),
  },
});
