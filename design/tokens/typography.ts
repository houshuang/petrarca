import { Platform } from 'react-native';

/**
 * Petrarca "Annotated Folio" typography tokens
 *
 * Four-font system:
 * - Cormorant Garamond: Display headings, screen titles, large numbers
 * - EB Garamond: Body titles, section heads, claims, review concepts
 * - Crimson Pro: Reading text, summaries, reader body
 * - DM Sans: UI metadata, labels, small caps
 */

export const fontFamilies = {
  display: Platform.select({
    web: "'Cormorant Garamond', Georgia, serif",
    default: 'CormorantGaramond',
  }),
  body: Platform.select({
    web: "'EB Garamond', Georgia, serif",
    default: 'EBGaramond',
  }),
  reading: Platform.select({
    web: "'Crimson Pro', Georgia, serif",
    default: 'CrimsonPro',
  }),
  ui: Platform.select({
    web: "'DM Sans', -apple-system, sans-serif",
    default: 'DMSans',
  }),
} as const;

/**
 * Font assets to load with expo-font
 * Import in app root: await Font.loadAsync(fontAssets)
 */
export const fontAssets = {
  'CormorantGaramond': require('../../assets/fonts/CormorantGaramond-Regular.ttf'),
  'CormorantGaramond-Medium': require('../../assets/fonts/CormorantGaramond-Medium.ttf'),
  'CormorantGaramond-SemiBold': require('../../assets/fonts/CormorantGaramond-SemiBold.ttf'),
  'CormorantGaramond-Bold': require('../../assets/fonts/CormorantGaramond-Bold.ttf'),
  'CormorantGaramond-Italic': require('../../assets/fonts/CormorantGaramond-Italic.ttf'),
  'EBGaramond': require('../../assets/fonts/EBGaramond-Regular.ttf'),
  'EBGaramond-Medium': require('../../assets/fonts/EBGaramond-Medium.ttf'),
  'EBGaramond-SemiBold': require('../../assets/fonts/EBGaramond-SemiBold.ttf'),
  'EBGaramond-Italic': require('../../assets/fonts/EBGaramond-Italic.ttf'),
  'CrimsonPro': require('../../assets/fonts/CrimsonPro-Regular.ttf'),
  'CrimsonPro-Italic': require('../../assets/fonts/CrimsonPro-Italic.ttf'),
  'CrimsonPro-Medium': require('../../assets/fonts/CrimsonPro-Medium.ttf'),
  'DMSans': require('../../assets/fonts/DMSans-Regular.ttf'),
  'DMSans-Medium': require('../../assets/fonts/DMSans-Medium.ttf'),
  'DMSans-SemiBold': require('../../assets/fonts/DMSans-SemiBold.ttf'),
  'DMSans-Bold': require('../../assets/fonts/DMSans-Bold.ttf'),
};

/** Semantic type styles */
export const typeStyles = {
  screenTitle: {
    fontFamily: fontFamilies.display,
    fontSize: 24,
    fontWeight: '600' as const,
    lineHeight: 28,
  },
  screenSubtitle: {
    fontFamily: fontFamilies.display,
    fontSize: 13,
    fontWeight: '400' as const,
    fontStyle: 'italic' as const,
  },
  sectionHead: {
    fontFamily: fontFamilies.body,
    fontSize: 11,
    fontWeight: '500' as const,
    letterSpacing: 1.6,
    textTransform: 'uppercase' as const,
  },
  entryTitle: {
    fontFamily: fontFamilies.body,
    fontSize: 16,
    fontWeight: '500' as const,
    lineHeight: 21,
  },
  entrySummary: {
    fontFamily: fontFamilies.reading,
    fontSize: 13.5,
    fontWeight: '400' as const,
    lineHeight: 20,
  },
  claimText: {
    fontFamily: fontFamilies.reading,
    fontSize: 14,
    fontWeight: '400' as const,
    lineHeight: 20,
  },
  reviewConcept: {
    fontFamily: fontFamilies.body,
    fontSize: 18,
    fontWeight: '500' as const,
    lineHeight: 25,
  },
  readerTitle: {
    fontFamily: fontFamilies.display,
    fontSize: 24,
    fontWeight: '600' as const,
    lineHeight: 29,
  },
  readerBody: {
    fontFamily: fontFamilies.reading,
    fontSize: 16,
    fontWeight: '400' as const,
    lineHeight: 27,
  },
  metadata: {
    fontFamily: fontFamilies.ui,
    fontSize: 11,
    fontWeight: '400' as const,
  },
  topicTag: {
    fontFamily: fontFamilies.body,
    fontSize: 11.5,
    fontWeight: '400' as const,
    fontStyle: 'italic' as const,
  },
  tabLabel: {
    fontFamily: fontFamilies.body,
    fontSize: 11,
    fontWeight: '400' as const,
  },
  statNumber: {
    fontFamily: fontFamilies.display,
    fontSize: 24,
    fontWeight: '600' as const,
  },
  statLabel: {
    fontFamily: fontFamilies.ui,
    fontSize: 9,
    fontWeight: '500' as const,
    letterSpacing: 0.7,
    textTransform: 'uppercase' as const,
  },
  ratingLabel: {
    fontFamily: fontFamilies.body,
    fontSize: 13,
    fontWeight: '400' as const,
  },
  ratingHint: {
    fontFamily: fontFamilies.ui,
    fontSize: 9,
    fontWeight: '400' as const,
  },
  sideLabel: {
    fontFamily: fontFamilies.ui,
    fontSize: 9,
    fontWeight: '500' as const,
    letterSpacing: 0.5,
    textTransform: 'uppercase' as const,
  },
  sideValue: {
    fontFamily: fontFamilies.body,
    fontSize: 14,
    fontWeight: '500' as const,
  },
  sideNote: {
    fontFamily: fontFamilies.body,
    fontSize: 11,
    fontWeight: '400' as const,
    fontStyle: 'italic' as const,
  },
} as const;
