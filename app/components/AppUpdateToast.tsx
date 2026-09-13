import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { colors, fonts } from '../design/tokens';
import { logEvent } from '../data/logger';
import { detectNewlyAppliedUpdate } from '../lib/app-version';

type Notice = NonNullable<Awaited<ReturnType<typeof detectNewlyAppliedUpdate>>>;

export default function AppUpdateToast() {
  const insets = useSafeAreaInsets();
  const [notice, setNotice] = useState<Notice | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    detectNewlyAppliedUpdate().then(update => {
      if (!update || cancelled) return;
      setNotice(update);
      logEvent('app_update_notice_shown', { update_id: update.updateId });
      timer = setTimeout(() => setNotice(null), 8000);
    });
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  if (!notice) return null;
  return (
    <Pressable
      style={[styles.toast, { top: insets.top + 8 }]}
      accessibilityRole="button"
      accessibilityLabel={`Petrarca er oppdatert. ${notice.label}. Lukk meldingen.`}
      accessibilityLiveRegion="polite"
      onPress={() => {
        logEvent('app_update_notice_dismissed', { update_id: notice.updateId });
        setNotice(null);
      }}
    >
      <Text style={styles.check}>✓</Text>
      <View style={styles.copy}>
        <Text style={styles.title}>Petrarca er oppdatert</Text>
        <Text style={styles.version}>{notice.label}</Text>
      </View>
      <Text style={styles.close}>×</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  toast: {
    position: 'absolute', left: 16, right: 16, zIndex: 400, elevation: 6,
    flexDirection: 'row', alignItems: 'center', gap: 12,
    paddingHorizontal: 16, paddingVertical: 12,
    backgroundColor: colors.ink, borderRadius: 4,
  },
  copy: { flex: 1 },
  title: { fontFamily: fonts.ui, fontSize: 14, color: colors.parchment },
  version: { fontFamily: fonts.ui, fontSize: 11, color: colors.parchment, marginTop: 3 },
  check: { fontSize: 20, color: colors.parchment },
  close: { fontSize: 24, color: colors.parchment },
});
