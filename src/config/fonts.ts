/**
 * Typefaces, and the jobs each one is allowed to do.
 *
 * Three faces with a hard division of labour: Fraunces for large still text,
 * Work Sans for anything read quickly or in motion, Amiri for Arabic.
 *
 * The critical detail on the Arabic faces is `subsets: ['arabic']`. A face
 * loaded without it still RENDERS Arabic — Chromium falls back to whatever
 * the machine has — so missing coverage never looks broken, it just differs
 * from machine to machine. See docs/arabic-shaping.md.
 */

import { loadFont as amiri } from '@remotion/google-fonts/Amiri';
import { loadFont as amiriQuran } from '@remotion/google-fonts/AmiriQuran';
import { loadFont as fraunces } from '@remotion/google-fonts/Fraunces';
import { loadFont as notoNaskh } from '@remotion/google-fonts/NotoNaskhArabic';
import { loadFont as workSans } from '@remotion/google-fonts/WorkSans';

// Large, still text only — see requireDisplayType below.
const DISPLAY = fraunces('normal', { weights: ['600'], subsets: ['latin'] });

// Everything read quickly: subtitles, labels, translations, corner branding.
const UI = workSans('normal', { weights: ['400', '500'], subsets: ['latin'] });

// Classical naskh for Arabic.
const ARABIC = amiri('normal', { weights: ['400'], subsets: ['arabic'] });

// Cut for vocalised Qur'anic typesetting; covers the annotation blocks
// (U+0870-0891, U+08E3-08FF) that general Arabic faces leave out. Using it is
// not permission to typeset scripture: verse text comes from an approved
// source, verified by a human, never written by the engine.
const QURAN = amiriQuran('normal', { weights: ['400'], subsets: ['arabic'] });

// A comparison face, used by the shaping proof to show that the Arabic
// webfonts really loaded. Not part of the brand.
const NASKH = notoNaskh('normal', { weights: ['400'], subsets: ['arabic'] });

export const FONT = {
  display: DISPLAY.fontFamily,
  ui: UI.fontFamily,
  arabic: ARABIC.fontFamily,
  arabicQuran: QURAN.fontFamily,
  arabicAlt: NASKH.fontFamily,
} as const;

export type FontKey = keyof typeof FONT;

export const fontsReady = Promise.all(
  [DISPLAY, UI, ARABIC, QURAN, NASKH].map((font) => font.waitUntilDone()),
);

// ---------------------------------------------------------------------------
// The type scale, for a 1080 x 1920 canvas
// ---------------------------------------------------------------------------

export const TYPE = {
  hook: { family: FONT.display, weight: 600, min: 96, max: 120 },
  subtitle: { family: FONT.ui, weight: 500, min: 56, max: 72 },
  verse: { family: FONT.arabic, weight: 400, min: 72, max: 96 },
  verseTranslation: { family: FONT.ui, weight: 400, min: 40, max: 48 },
  verseLabel: { family: FONT.ui, weight: 500, min: 32, max: 40 },
  corner: { family: FONT.ui, weight: 500, min: 28, max: 32 },
} as const;

export type TypeRole = keyof typeof TYPE;

/**
 * The floor for a subtitle. Below this it stops being readable while someone
 * is scrolling, and no layout reason is good enough to go under it.
 */
export const SUBTITLE_FLOOR = 48;

/** Fraunces holds together at this size and above, and nowhere below it. */
export const DISPLAY_FLOOR = 96;

/**
 * A verse frame is held still for at least this long, with no zoom and no pan.
 *
 * Amiri's harakat sit close together and some are already lost to Instagram's
 * compression. Movement makes an encoder throw away fine detail faster, so a
 * moving verse loses the marks that change what it says.
 */
export const VERSE_FRAME_MIN_SECONDS = 4;

/**
 * Refuse Fraunces where it will fall apart.
 *
 * Not taste — compression. Fraunces is a serif with high thick/thin contrast,
 * and its thin strokes disintegrate once Instagram re-encodes the video. At
 * 96 px and still it holds. At 60 px, or moving, it turns to mud. So the rule
 * is: Fraunces only for text that is large AND stationary. Anything that
 * moves or shrinks is Work Sans.
 */
export function requireDisplayType(size: number, moving: boolean, where: string): void {
  if (moving) {
    throw new Error(
      `${where}: Fraunces may not be used on moving text. Its thin strokes break up `
        + 'under compression once the frame changes. Use FONT.ui (Work Sans).',
    );
  }
  if (size < DISPLAY_FLOOR) {
    throw new Error(
      `${where}: Fraunces at ${size}px is below the ${DISPLAY_FLOOR}px floor, where its `
        + 'thin strokes stop surviving compression. Use FONT.ui (Work Sans).',
    );
  }
}

/** Refuse a subtitle too small to read while scrolling. */
export function requireSubtitleSize(size: number, where: string): void {
  if (size < SUBTITLE_FLOOR) {
    throw new Error(
      `${where}: a subtitle at ${size}px is under the ${SUBTITLE_FLOOR}px floor and `
        + 'becomes hard to read while scrolling.',
    );
  }
}
