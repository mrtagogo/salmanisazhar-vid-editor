/**
 * The brand palette, and the rules that come with it.
 *
 * Four colours, no fifth. This is what makes video and carousel read as one
 * account while the templates keep changing.
 *
 * Colour lives ONLY here. No hex literal belongs anywhere else in src/ — the
 * effects library this project borrowed from has 125 of them across 14 files,
 * which is precisely how a palette stops meaning anything.
 */

export const BRAND = {
  /** Tinta Malam — the base of almost every frame, and the block behind subtitles. */
  tintaMalam: '#1A1714',
  /** Kertas Tua — base of verse frames and the closing summary. Dark→light says "this part is slow". */
  kertasTua: '#E9E2D6',
  /** Nyala Pelita — one highlighted word, a progress line, a marker. NEVER a frame base. */
  nyalaPelita: '#E0A33C',
  /** Kapur Hangat — subtitle text, and any text sitting on Tinta Malam. */
  kapurHangat: '#F2EDE4',
} as const;

export type BrandColour = keyof typeof BRAND;

// ---------------------------------------------------------------------------
// Contrast
// ---------------------------------------------------------------------------

const channel = (value: number) =>
  value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;

/** WCAG relative luminance of a #rrggbb colour. */
export function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => channel(parseInt(hex.slice(i, i + 2), 16) / 255));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG contrast ratio between two #rrggbb colours, 1:1 to 21:1. */
export function contrastRatio(a: string, b: string): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (light + 0.05) / (dark + 0.05);
}

/**
 * The pairings that were decided, with the ratios they were decided on.
 *
 * These were computed from the brand profile and checked against this
 * implementation: all six agree to within 0.05. They are listed rather than
 * recomputed at the point of use so the DECISION is what travels, not just
 * the arithmetic — "white on amber fails" is a ruling, and a ruling should be
 * written down where someone can read it.
 */
export const CONTRAST_RULINGS: {
  foreground: string;
  background: string;
  ratio: number;
  allowed: boolean;
  note: string;
}[] = [
  {
    foreground: BRAND.kapurHangat,
    background: BRAND.tintaMalam,
    ratio: 15.3,
    allowed: true,
    note: 'The subtitle pairing.',
  },
  {
    foreground: BRAND.tintaMalam,
    background: BRAND.kertasTua,
    ratio: 13.9,
    allowed: true,
    note: 'The verse-frame pairing.',
  },
  {
    foreground: BRAND.nyalaPelita,
    background: BRAND.tintaMalam,
    ratio: 8.1,
    allowed: true,
    note: 'The only way amber becomes text.',
  },
  {
    foreground: BRAND.tintaMalam,
    background: BRAND.nyalaPelita,
    ratio: 8.1,
    allowed: true,
    note: 'Used when amber is a highlight block.',
  },
  {
    foreground: '#FFFFFF',
    background: BRAND.nyalaPelita,
    ratio: 2.2,
    allowed: false,
    note: 'Fails even at display sizes. Use Tinta Malam on amber instead.',
  },
  {
    foreground: BRAND.nyalaPelita,
    background: BRAND.kertasTua,
    ratio: 1.7,
    allowed: false,
    note: 'Amber disappears completely. Use Tinta Malam on Kertas Tua.',
  },
];

/** Smallest ratio that may appear on screen. Below it, text is not readable. */
export const MIN_CONTRAST = 4.5;

/**
 * Throw unless this pairing is allowed.
 *
 * A forbidden pairing is not a judgement call to be made again per component.
 * Amber text on Kertas Tua measures 1.7:1 — it is not "low contrast", it is
 * invisible — so this refuses rather than warns.
 */
export function requireContrast(foreground: string, background: string, where: string): number {
  const ruling = CONTRAST_RULINGS.find(
    (r) =>
      r.foreground.toLowerCase() === foreground.toLowerCase()
      && r.background.toLowerCase() === background.toLowerCase(),
  );
  const ratio = contrastRatio(foreground, background);

  if (ruling && !ruling.allowed) {
    throw new Error(
      `${where}: ${foreground} on ${background} is ruled out (${ruling.ratio}:1). ${ruling.note}`,
    );
  }
  if (ratio < MIN_CONTRAST) {
    throw new Error(
      `${where}: ${foreground} on ${background} is ${ratio.toFixed(1)}:1, below the `
        + `${MIN_CONTRAST}:1 floor. Pick a pairing from CONTRAST_RULINGS.`,
    );
  }
  return ratio;
}

// ---------------------------------------------------------------------------
// Tokens
// ---------------------------------------------------------------------------

/** Tinta Malam as an rgb triple, for composing scrims at varying alpha. */
export const TINTA_MALAM_RGB = '26, 23, 20';

export const THEME = {
  // Surfaces
  bg: BRAND.tintaMalam,
  paper: BRAND.kertasTua,
  panel: 'rgba(242, 237, 228, 0.06)',
  hairline: 'rgba(242, 237, 228, 0.14)',

  // Text
  ink: BRAND.kapurHangat,
  inkMuted: 'rgba(242, 237, 228, 0.56)',
  inkInverse: BRAND.tintaMalam,

  // The one accent. Never a frame base.
  accent: BRAND.nyalaPelita,

  /**
   * Scrims fade to Tinta Malam, never to black.
   *
   * Footage blacks are lifted to roughly this colour so that a join from
   * footage to a plain frame does not read as two different blacks. A scrim
   * that faded to #000000 would reintroduce exactly that seam.
   */
  scrimRgb: TINTA_MALAM_RGB,

  glassFill: 'rgba(26, 23, 20, 0.34)',
  glassEdge: 'rgba(242, 237, 228, 0.62)',

  shadow: 'rgba(26, 23, 20, 0.45)',
  captionShadow: '0 4px 20px rgba(26, 23, 20, 0.55)',
  displayShadowOnDark: '0 18px 50px rgba(26, 23, 20, 0.55)',
  displayShadowOnLight: '0 18px 50px rgba(26, 23, 20, 0.18)',
} as const;

export type ThemeKey = keyof typeof THEME;

/**
 * Footage grading: never let blacks reach #000000.
 *
 * A plain Tinta Malam frame next to ungraded footage shows two different
 * blacks at the join. Lifting the footage's black point to about Tinta Malam
 * removes the seam. Applied as a CSS filter so it costs nothing extra in the
 * render.
 */
export const LIFT_BLACKS = 'brightness(1.04) contrast(0.95) saturate(1.04)';

/**
 * Colours for proof and diagnostic compositions only.
 *
 * Kept apart from BRAND on purpose: these are instrument markings, they never
 * appear in a deliverable, and they must not drift into the palette.
 */
export const DIAGNOSTIC = {
  grid: 'rgba(120, 200, 255, 0.55)',
  guard: 'rgba(255, 90, 95, 0.9)',
  safe: 'rgba(120, 255, 170, 0.5)',
  pass: '#6fbf73',
  fail: '#e0574f',
  label: 'rgba(255, 255, 255, 0.78)',
} as const;
