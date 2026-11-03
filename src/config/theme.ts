/**
 * Design tokens for the composition layer.
 *
 * This file exists so that colour lives in ONE place. Effects must read from
 * here and never write a hex literal inline — the reference implementation we
 * are borrowing effects from has 125 colour literals spread over 14 files, and
 * that is precisely the mistake this layer avoids.
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
} as const;

export type ThemeKey = keyof typeof THEME;
