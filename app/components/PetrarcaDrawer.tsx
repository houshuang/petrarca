import { useCallback, useMemo } from 'react';
import { View, Text, StyleSheet, Pressable, Modal, Platform, Linking } from 'react-native';
import { useRouter } from 'expo-router';
import { logEvent } from '../data/logger';
import { getReadArticles } from '../data/store';
import { getQueuedArticleIds } from '../data/queue';
import { colors, fonts } from '../design/tokens';

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
      } else if (item === 'voice_note') {
        router.push('/voice-notes' as any);
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

          {/* Header */}
          <View style={styles.header}>
            <Text style={styles.headerOrnament}>{'\u2726'}</Text>
            <Text style={styles.headerTitle}>Petrarca</Text>
          </View>

          {/* Quick actions */}
          <View style={styles.quickActions}>
            <Pressable style={styles.quickBox} onPress={() => quickAction('triage')}>
              <Text style={styles.quickTitle}>Triage</Text>
              <Text style={styles.quickSubtitle}>Card-by-card decisions</Text>
            </Pressable>
            <Pressable style={styles.quickBox} onPress={() => quickAction('voice_note')}>
              <Text style={styles.quickTitle}>Voice Note</Text>
              <Text style={styles.quickSubtitle}>Record a thought</Text>
            </Pressable>
          </View>

          {/* Navigation items */}
          <NavItem
            title="Voice Notes"
            subtitle="3 notes"
            onPress={() => navigate('voice_notes', '/voice-notes')}
          />
          <NavItem
            title="Activity Log"
            subtitle="Pipeline activity & events"
            onPress={() => navigate('activity_log', '/log')}
          />
          <NavItem
            title="Your Landscape"
            subtitle={`${readCount} articles · topics & connections`}
            onPress={() => navigate('landscape', '/landscape')}
          />
          <NavItem
            title="Reading Trails"
            subtitle="Follow threads of ideas"
            onPress={() => navigate('trails', '/trails')}
          />
          <NavItem
            title="Queue"
            subtitle={`${queueCount} articles queued`}
            onPress={() => navigate('queue', '/queue')}
          />
          <NavItem
            title="User Guide"
            subtitle="How everything works"
            onPress={() => {
              logEvent('drawer_item_tap', { item: 'user_guide' });
              onClose();
              const url = Platform.OS === 'web' ? '/guide/' : 'https://alifstian.duckdns.org:8084/guide/';
              Linking.openURL(url);
            }}
          />
        </Pressable>
      </Pressable>
    </Modal>
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
  navTitle: {
    fontFamily: fonts.body,
    fontSize: 15,
    color: colors.parchment,
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
});
