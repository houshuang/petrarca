import { useEffect, useState } from 'react';
import { Stack } from 'expo-router';
import { View, Text, ActivityIndicator, StyleSheet, Platform } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as Font from 'expo-font';
import { initStore } from '../data/store';
import { startNewSession } from '../data/logger';
import { colors } from '../design/tokens/colors';
import FeedbackCapture from '../components/FeedbackCapture';

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

export default function RootLayout() {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    (async () => {
      startNewSession();
      await Promise.all([
        initStore(),
        Font.loadAsync(fontAssets),
      ]);
      setReady(true);
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

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.parchment }} edges={['top']}>
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="reader" />
        <Stack.Screen name="voice-notes" />
        <Stack.Screen name="+not-found" />
      </Stack>
      <FeedbackCapture />
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
});
