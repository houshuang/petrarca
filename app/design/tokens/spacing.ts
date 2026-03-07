/**
 * Petrarca spacing scale
 * Based on a 4px base unit with Renaissance-proportioned steps
 */

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  xxxl: 32,
} as const;

export const layout = {
  /** Horizontal padding for screen content */
  screenPadding: 16,
  /** Max content width for reading (web) */
  readingMeasure: 680,
  /** Entry row sidebar width */
  sidebarWidth: 76,
  /** Minimum touch target */
  touchTarget: 44,
  /** Tab bar height */
  tabBarHeight: 80,
  /** Status bar padding (safe area) */
  statusBarPadding: 48,
  /** Double rule gap */
  doubleRuleGap: 5,
  /** Double rule top thickness */
  doubleRuleTop: 2,
  /** Double rule bottom thickness */
  doubleRuleBottom: 1,
  /** Claim left border width */
  claimBorderWidth: 2,
  /** Rating button border width */
  ratingBorderWidth: 1.5,
  /** Progress bar height */
  progressBarHeight: 3,
  /** Depth nav underline height */
  depthUnderlineHeight: 2,
  /** Sidebar navigation width (desktop web) */
  sidebarNavWidth: 220,
  /** Max content width for screens (desktop web) */
  contentMaxWidth: 960,
} as const;
