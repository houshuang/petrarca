import { Platform, TextStyle } from 'react-native';

/**
 * Petrarca "Annotated Folio" typography tokens
 *
 * Four-font system:
 * - Cormorant Garamond: Display headings, screen titles, large numbers
 * - EB Garamond: Body titles, section heads, claims, review concepts
 * - Crimson Pro: Reading text, summaries, reader body
 * - DM Sans: UI metadata, labels, small caps
 */

export const fonts = {
  display: Platform.select({
    web: "'Cormorant Garamond', Georgia, serif",
    default: 'CormorantGaramond',
  })!,
  displaySemiBold: Platform.select({
    web: "'Cormorant Garamond', Georgia, serif",
    default: 'CormorantGaramond-SemiBold',
  })!,
  displayItalic: Platform.select({
    web: "'Cormorant Garamond', Georgia, serif",
    default: 'CormorantGaramond-Italic',
  })!,
  body: Platform.select({
    web: "'EB Garamond', Georgia, serif",
    default: 'EBGaramond',
  })!,
  bodyMedium: Platform.select({
    web: "'EB Garamond', Georgia, serif",
    default: 'EBGaramond-Medium',
  })!,
  bodyItalic: Platform.select({
    web: "'EB Garamond', Georgia, serif",
    default: 'EBGaramond-Italic',
  })!,
  reading: Platform.select({
    web: "'Crimson Pro', Georgia, serif",
    default: 'CrimsonPro',
  })!,
  readingItalic: Platform.select({
    web: "'Crimson Pro', Georgia, serif",
    default: 'CrimsonPro-Italic',
  })!,
  readingMedium: Platform.select({
    web: "'Crimson Pro', Georgia, serif",
    default: 'CrimsonPro-Medium',
  })!,
  ui: Platform.select({
    web: "'DM Sans', -apple-system, sans-serif",
    default: 'DMSans',
  })!,
  uiMedium: Platform.select({
    web: "'DM Sans', -apple-system, sans-serif",
    default: 'DMSans-Medium',
  })!,
  uiSemiBold: Platform.select({
    web: "'DM Sans', -apple-system, sans-serif",
    default: 'DMSans-SemiBold',
  })!,
};

/** Semantic type styles — ready to spread into StyleSheet */
export const type: Record<string, TextStyle> = {
  screenTitle: {
    fontFamily: fonts.displaySemiBold,
    fontSize: 24,
    lineHeight: 28,
    ...(Platform.OS === 'web' ? { fontWeight: '600' } : {}),
  },
  screenSubtitle: {
    fontFamily: fonts.displayItalic,
    fontSize: 13,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' } : {}),
  },
  sectionHead: {
    fontFamily: fonts.bodyMedium,
    fontSize: 11,
    letterSpacing: 1.6,
    textTransform: 'uppercase',
    ...(Platform.OS === 'web' ? { fontWeight: '500' } : {}),
  },
  entryTitle: {
    fontFamily: fonts.bodyMedium,
    fontSize: 16,
    lineHeight: 21,
    ...(Platform.OS === 'web' ? { fontWeight: '500' } : {}),
  },
  entrySummary: {
    fontFamily: fonts.reading,
    fontSize: 13.5,
    lineHeight: 20,
  },
  claimText: {
    fontFamily: fonts.reading,
    fontSize: 14,
    lineHeight: 20,
  },
  reviewConcept: {
    fontFamily: fonts.bodyMedium,
    fontSize: 18,
    lineHeight: 25,
    ...(Platform.OS === 'web' ? { fontWeight: '500' } : {}),
  },
  readerTitle: {
    fontFamily: fonts.displaySemiBold,
    fontSize: 24,
    lineHeight: 29,
    ...(Platform.OS === 'web' ? { fontWeight: '600' } : {}),
  },
  readerBody: {
    fontFamily: fonts.reading,
    fontSize: 16,
    lineHeight: 27,
  },
  metadata: {
    fontFamily: fonts.ui,
    fontSize: 11,
  },
  topicTag: {
    fontFamily: fonts.bodyItalic,
    fontSize: 11.5,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' } : {}),
  },
  statNumber: {
    fontFamily: fonts.displaySemiBold,
    fontSize: 24,
    ...(Platform.OS === 'web' ? { fontWeight: '600' } : {}),
  },
  statLabel: {
    fontFamily: fonts.uiMedium,
    fontSize: 9,
    letterSpacing: 0.7,
    textTransform: 'uppercase',
    ...(Platform.OS === 'web' ? { fontWeight: '500' } : {}),
  },
  ratingLabel: {
    fontFamily: fonts.body,
    fontSize: 13,
  },
  ratingHint: {
    fontFamily: fonts.ui,
    fontSize: 9,
  },
  sideLabel: {
    fontFamily: fonts.uiMedium,
    fontSize: 9,
    letterSpacing: 0.5,
    textTransform: 'uppercase',
    ...(Platform.OS === 'web' ? { fontWeight: '500' } : {}),
  },
  sideValue: {
    fontFamily: fonts.bodyMedium,
    fontSize: 14,
    ...(Platform.OS === 'web' ? { fontWeight: '500' } : {}),
  },
  sideNote: {
    fontFamily: fonts.bodyItalic,
    fontSize: 11,
    ...(Platform.OS === 'web' ? { fontStyle: 'italic' } : {}),
  },
};
