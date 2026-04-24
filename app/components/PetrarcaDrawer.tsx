import { useCallback, useMemo } from 'react';
import { View, Text, StyleSheet, Pressable, Modal, Platform, Linking, ScrollView } from 'react-native';
import { useRouter } from 'expo-router';
import { logEvent } from '../data/logger';
import { getReadArticles } from '../data/store';
import { getQueuedArticleIds } from '../data/queue';
import { colors, fonts } from '../design/tokens';
import { showFeedbackButton } from './FeedbackCapture';
import { getGuideUrl, getStatsDashboardUrl } from '../lib/server-urls';

interface PetrarcaDrawerProps {
  visible: boolean;
  onClose: () => void;
}

export default function PetrarcaDrawer({ visible, onClose }: PetrarcaDrawerProps) {
  const router = useRouter();

  const readCount = useMemo(
    () => (visible ? getReadArticles().length : 0),
    [visible],
  );
  const queueCount = useMemo(
    () => (visible ? getQueuedArticleIds().length : 0),
    [visible],
  );

  const close = useCallback(() => {
    logEvent('drawer_close');
    onClose();
  }, [onClose]);

  const navigate = useCallback(
    (item: string, path: string) => {
      logEvent('drawer_item_tap', { item });
      onClose();
      router.push(path as any);
    },
    [onClose, router],
  );

  const quickAction = useCallback(
    (item: string) => {
      logEvent('drawer_item_tap', { item });
      onClose();
      if (item === 'triage') {
        router.push('/' as any);
      } else if (item === 'voice_capture') {
        router.push('/voice-capture' as any);
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
              <Pressable style={styles.quickBox} onPress={() => quickAction('voice_capture')}>
                <Text style={styles.quickTitle}>Capture Voice</Text>
                <Text style={styles.quickSubtitle}>Record what you learned</Text>
              </Pressable>
              <Pressable style={styles.quickBox} onPress={() => navigate('queue', '/queue')}>
                <Text style={styles.quickTitle}>Queue</Text>
                <Text style={styles.quickSubtitle}>{queueCount} articles</Text>
              </Pressable>
            </View>

            {/* Explore */}
            <Text style={styles.sectionLabel}>Explore</Text>
            <NavItem
              title="Knowledge Map"
              subtitle="Your learning progress & gaps"
              onPress={() => navigate('knowledge_map', '/knowledge-map')}
            />
            <NavItem
              title="Knowledge Sweep"
              subtitle="Test your recall across a domain"
              onPress={() => navigate('knowledge_sweep', '/knowledge-sweep')}
            />
            <NavItem
              title="Knowledge Explorer"
              subtitle="Timeline, persons & places"
              onPress={() => navigate('timeline', '/timeline')}
            />
            <NavItem
              title="Your Landscape"
              subtitle={`${readCount} articles · topics & connections`}
              onPress={() => navigate('landscape', '/landscape')}
            />
            <NavItem
              title="Ancient Map"
              subtitle="Places from your curriculum"
              onPress={() => navigate('map', '/map')}
            />

            {/* Reading */}
            <Text style={styles.sectionLabel}>Reading</Text>
            <NavItem
              title="Kindle Library"
              subtitle="Browse & manage your full Kindle library"
              onPress={() => navigate('kindle_browse', '/kindle-browse')}
            />
            <NavItem
              title="Reading Trails"
              subtitle="Follow threads of ideas"
              onPress={() => navigate('trails', '/trails')}
            />
            <NavItem
              title="Voice Notes"
              subtitle="Your recorded thoughts"
              onPress={() => navigate('voice_notes', '/voice-notes')}
            />
            <NavItem
              title="Projects"
              subtitle="Collect notes around a theme"
              onPress={() => navigate('projects', '/projects')}
            />

            {/* System */}
            <Text style={styles.sectionLabel}>System</Text>
            <NavItem
              title="Statistics"
              subtitle="Knowledge progress & review stats"
              onPress={() => {
                logEvent('drawer_item_tap', { item: 'statistics' });
                onClose();
                Linking.openURL(getStatsDashboardUrl());
              }}
            />
            <NavItem
              title="Activity Log"
              subtitle="Pipeline activity & events"
              onPress={() => navigate('activity_log', '/log')}
            />
            <NavItem
              title="User Guide"
              subtitle="How everything works"
              onPress={() => {
                logEvent('drawer_item_tap', { item: 'user_guide' });
                onClose();
                Linking.openURL(getGuideUrl());
              }}
            />
            <NavItem
              title="Show Feedback Button"
              subtitle="Re-enable the \u2726 feedback capture"
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
    <Pressable style={styles.navItem} onPress={onPress}>
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
