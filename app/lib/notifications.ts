import { Platform } from 'react-native';
import { logEvent } from '../data/logger';

let Notifications: typeof import('expo-notifications') | null = null;

function getNotifications() {
  if (!Notifications && Platform.OS !== 'web') {
    Notifications = require('expo-notifications');
  }
  return Notifications;
}

const DAILY_REVIEW_ID = 'daily-review-reminder';

export async function requestNotificationPermissions(): Promise<boolean> {
  if (Platform.OS === 'web') return false;

  const mod = getNotifications();
  if (!mod) return false;

  const { status: existing } = await mod.getPermissionsAsync();
  if (existing === 'granted') return true;

  const { status } = await mod.requestPermissionsAsync();
  return status === 'granted';
}

export async function scheduleDailyReviewReminder(reviewCount: number): Promise<void> {
  if (Platform.OS === 'web') return;

  const mod = getNotifications();
  if (!mod) return;

  // Cancel previous daily reminder
  await mod.cancelScheduledNotificationAsync(DAILY_REVIEW_ID).catch(() => {});

  if (reviewCount <= 0) return;

  await mod.scheduleNotificationAsync({
    identifier: DAILY_REVIEW_ID,
    content: {
      title: 'Petrarca Review',
      body: `You have ${reviewCount} concept${reviewCount !== 1 ? 's' : ''} to review`,
      sound: true,
    },
    trigger: {
      type: mod.SchedulableTriggerInputTypes.DAILY,
      hour: 8,
      minute: 0,
    },
  });

  logEvent('notification_scheduled', { type: 'daily_review', review_count: reviewCount });
}

export async function scheduleNewContentNotification(articleCount: number): Promise<void> {
  if (Platform.OS === 'web') return;
  if (articleCount <= 0) return;

  const mod = getNotifications();
  if (!mod) return;

  await mod.scheduleNotificationAsync({
    content: {
      title: 'New Content',
      body: `${articleCount} new article${articleCount !== 1 ? 's' : ''} ready to read`,
      sound: true,
    },
    trigger: null, // immediate
  });

  logEvent('notification_scheduled', { type: 'new_content', article_count: articleCount });
}

export async function cancelAllNotifications(): Promise<void> {
  if (Platform.OS === 'web') return;

  const mod = getNotifications();
  if (!mod) return;

  await mod.cancelAllScheduledNotificationsAsync();
}
