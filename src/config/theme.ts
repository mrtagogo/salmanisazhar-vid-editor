/**
 * Design tokens for the composition layer.
 *
 * This file exists so that colour lives in ONE place. Effects must read from
 * here and never write a hex literal inline — the reference implementation we
 * borrowed effects from has 125 colour literals spread over 14 files, and that
 * is precisely the mistake this layer avoids.
 *
 * The values below are deliberate PLACEHOLDERS: neutral, readable, and not a
 * brand. Replace them with the real palette (the 60/30/10 split and locked
 * contrast ratios from the brand system) so that video and carousel use the
 * same numbers rather than two separate tastes.
 */

export const THEME = {
  // Surfaces
  bg: '#0f1115',
  panel: 'rgba(255, 255, 255, 0.04)',
  hairline: 'rgba(255, 255, 255, 0.10)',

  // Text
  ink: '#f4ece0',
  inkMuted: 'rgba(244, 236, 224, 0.52)',
  inkInverse: '#141418',

  // Emphasis — one accent only, until the brand palette lands
  accent: '#c8a24a',

  shadow: 'rgba(0, 0, 0, 0.45)',

  /**
   * The scrim is composed at many alphas (a gradient fading to dark), so it is
   * stored as an rgb triple to be used as `rgba(${THEME.scrimRgb}, a)`.
   */
  scrimRgb: '0, 0, 0',

  // Frosted panel, the one material every overlay card shares
  glassFill: 'rgba(16, 16, 16, 0.28)',
  glassEdge: 'rgba(244, 236, 224, 0.62)',

  // Type shadows: enough separation from footage to stay readable
  captionShadow: '0 4px 20px rgba(0, 0, 0, 0.38)',
  displayShadowOnDark: '0 18px 50px rgba(0, 0, 0, 0.45)',
  displayShadowOnLight: '0 18px 50px rgba(0, 0, 0, 0.16)',
} as const;

export type ThemeKey = keyof typeof THEME;

/**
 * Colours for proof and diagnostic compositions only.
 *
 * Kept apart from THEME on purpose: these are instrument markings, they are
 * never part of a deliverable, and they must not drift into the brand palette.
 */
export const DIAGNOSTIC = {
  grid: 'rgba(120, 200, 255, 0.55)',
  guard: 'rgba(255, 90, 95, 0.9)',
  safe: 'rgba(120, 255, 170, 0.5)',
  pass: '#6fbf73',
  fail: '#e0574f',
  label: 'rgba(255, 255, 255, 0.78)',
} as const;
