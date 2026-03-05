/**
 * Petrarca "Annotated Folio" color tokens
 * Renaissance-inspired palette: warm parchment ground, ink text, red rubric accent
 */

export const colors = {
  // Surfaces
  parchment: '#f7f4ec',
  parchmentDark: '#f0ece2',
  parchmentHover: 'rgba(139, 37, 0, 0.03)',

  // Text
  ink: '#2a2420',
  textPrimary: '#1a1a18',
  textBody: '#333333',
  textSecondary: '#6a6458',
  textMuted: '#b0a898',
  textFaint: '#cccccc',

  // Accent
  rubric: '#8b2500',

  // Structural
  rule: '#e4dfd4',
  ruleDark: '#2a2420',

  // Claim states
  claimDefault: '#e4dfd4',
  claimNew: '#2a7a4a',
  claimKnown: '#d0ccc0',
  claimSaved: '#8b2500',

  // Semantic
  success: '#2a7a4a',
  warning: '#92600e',
  info: '#2a4a6a',
  danger: '#8b2500',

  // Rating
  ratingAgain: '#8b2500',
  ratingAgainBorder: '#e0c0b8',
  ratingHard: '#7a5a20',
  ratingHardBorder: '#e0d8c0',
  ratingGood: '#2a6a3a',
  ratingGoodBorder: '#c0dcc8',
  ratingEasy: '#2a4a6a',
  ratingEasyBorder: '#c0d0e0',

  // Opacity modifiers
  claimKnownOpacity: 0.55,
} as const;
