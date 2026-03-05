import { useEffect, useState } from 'react';
import { Tabs } from 'expo-router';
import { View, Text, ActivityIndicator, StyleSheet, Platform } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as Font from 'expo-font';
import { initStore, getReviewQueue } from '../data/store';
import { startNewSession, logEvent } from '../data/logger';
import { requestNotificationPermissions, scheduleDailyReviewReminder } from '../lib/notifications';
import { useIsDesktopWeb } from '../lib/use-responsive';
import { WebSidebar } from '../components/WebSidebar';
import { colors } from '../design/tokens/colors';

const fontAssets = {
  'CormorantGaramond': require('../assets/fonts/CormorantGaramond-Regular.ttf'),
  'CormorantGaramond-Medium': require('../assets/fonts/CormorantGaramond-Medium.ttf'),
  'CormorantGaramond-SemiBold': require('../assets/fonts/CormorantGaramond-SemiBold.ttf'),
  'CormorantGaramond-Bold': require('../assets/fonts/CormorantGaramond-Bold.ttf'),
  'CormorantGaramond-Italic': require('../assets/fonts/CormorantGaramond-Italic.ttf'),
  'EBGaramond': require('../assets/fonts/EBGaramond-Regular.ttf'),
  'EBGaramond-Medium': require('../assets/fonts/EBGaramond-Medium.ttf'),
  'EBGaramond-SemiBold': require('../assets/fonts/EBGaramond-SemiBold.ttf'),
  'EBGaramond-Italic': require('../assets/fonts/EBGaramond-Italic.ttf'),
  'CrimsonPro': require('../assets/fonts/CrimsonPro-Regular.ttf'),
  'CrimsonPro-Italic': require('../assets/fonts/CrimsonPro-Italic.ttf'),
  'CrimsonPro-Medium': require('../assets/fonts/CrimsonPro-Medium.ttf'),
  'DMSans': require('../assets/fonts/DMSans-Regular.ttf'),
  'DMSans-Medium': require('../assets/fonts/DMSans-Medium.ttf'),
  'DMSans-SemiBold': require('../assets/fonts/DMSans-SemiBold.ttf'),
  'DMSans-Bold': require('../assets/fonts/DMSans-Bold.ttf'),
};

/** Tab bar label using EB Garamond serif font */
function TabLabel({ label, focused }: { label: string; focused: boolean }) {
  return (
    <View style={tabStyles.labelWrap}>
      {focused && <View style={tabStyles.dot} />}
      <Text style={[tabStyles.label, focused && tabStyles.labelActive]}>
        {label}
      </Text>
    </View>
  );
}

export default function Layout() {
  const [ready, setReady] = useState(false);
  const isDesktop = useIsDesktopWeb();

  useEffect(() => {
    (async () => {
      startNewSession();
      await Promise.all([
        initStore(),
        Font.loadAsync(fontAssets),
      ]);
      setReady(true);

      const granted = await requestNotificationPermissions();
      logEvent('notifications_permission', { granted });
      if (granted) {
        const reviewCount = getReviewQueue().length;
        await scheduleDailyReviewReminder(reviewCount);
      }
    })();
  }, []);

  if (!ready) {
    return (
      <View style={styles.loading}>
        <ActivityIndicator color={colors.rubric} size="large" />
        <Text style={styles.loadingText}>Loading...</Text>
      </View>
    );
  }

  const tabs = (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.ink,
        tabBarInactiveTintColor: colors.textMuted,
        tabBarStyle: isDesktop
          ? { display: 'none' }
          : {
              backgroundColor: colors.parchmentDark,
              borderTopColor: colors.ruleDark,
              borderTopWidth: 1.5,
              ...(Platform.OS === 'web' ? { height: 56 } : {}),
            },
        tabBarShowLabel: false,
      }}
      screenListeners={{
        tabPress: (e) => {
          logEvent('tab_press', { tab: e.target?.split('-')[0] });
        },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Feed',
          tabBarIcon: ({ focused }) => <TabLabel label="Feed" focused={focused} />,
        }}
      />
      <Tabs.Screen
        name="library"
        options={{
          title: 'Library',
          tabBarIcon: ({ focused }) => <TabLabel label="Library" focused={focused} />,
        }}
      />
      <Tabs.Screen
        name="review"
        options={{
          title: 'Review',
          tabBarIcon: ({ focused }) => <TabLabel label="Review" focused={focused} />,
        }}
      />
      <Tabs.Screen
        name="stats"
        options={{
          title: 'Progress',
          tabBarIcon: ({ focused }) => <TabLabel label="Progress" focused={focused} />,
        }}
      />
      <Tabs.Screen
        name="reader"
        options={{
          href: null,
          headerShown: false,
          tabBarStyle: { display: 'none' },
        }}
      />
      <Tabs.Screen
        name="book-reader"
        options={{
          href: null,
          headerShown: false,
          tabBarStyle: { display: 'none' },
        }}
      />
      <Tabs.Screen
        name="+not-found"
        options={{
          href: null,
          headerShown: false,
        }}
      />
    </Tabs>
  );

  if (isDesktop) {
    return (
      <View style={styles.desktopRoot}>
        <WebSidebar />
        <View style={styles.desktopContent}>{tabs}</View>
      </View>
    );
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.parchment }} edges={['top']}>
      {tabs}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  loading: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: colors.parchment,
    gap: 12,
  },
  loadingText: {
    color: colors.textMuted,
    fontSize: 14,
    fontFamily: Platform.OS === 'web' ? "'Cormorant Garamond', Georgia, serif" : 'CormorantGaramond',
    fontStyle: 'italic',
  },
  desktopRoot: {
    flex: 1,
    flexDirection: 'row',
  },
  desktopContent: {
    flex: 1,
  },
});

const tabStyles = StyleSheet.create({
  labelWrap: {
    alignItems: 'center',
    gap: 3,
  },
  dot: {
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.rubric,
  },
  label: {
    fontFamily: Platform.OS === 'web' ? "'EB Garamond', Georgia, serif" : 'EBGaramond',
    fontSize: 13,
    color: colors.textMuted,
  },
  labelActive: {
    color: colors.ink,
  },
});
