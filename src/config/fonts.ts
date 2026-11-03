/**
 * Typefaces for the composition layer.
 *
 * The critical detail is `subsets: ['arabic']`. The effects library this
 * project borrows from loads every one of its six faces with
 * `subsets: ['latin']`, which means Arabic text silently falls back to
 * whatever the rendering machine happens to have. For an engine built around
 * tadabbur content that is not a cosmetic problem, so Arabic coverage is
 * declared explicitly here and proved by src/proofs/ArabicShapingProof.tsx.
 *
 * Weight 400 only for the Arabic faces: it is the weight every one of them
 * ships, and classical Arabic typesetting does not bold or slant running text.
 */

import { loadFont as amiri } from '@remotion/google-fonts/Amiri';
import { loadFont as amiriQuran } from '@remotion/google-fonts/AmiriQuran';
import { loadFont as inter } from '@remotion/google-fonts/Inter';
import { loadFont as notoNaskh } from '@remotion/google-fonts/NotoNaskhArabic';

// Classical naskh for general Arabic: terms, phrases, du'a.
const ARABIC = amiri('normal', { weights: ['400'], subsets: ['arabic'] });

// Amiri Quran is cut specifically for vocalised Qur'anic typesetting and
// covers the Qur'anic annotation blocks (U+0870-0891, U+08E3-08FF) that
// general Arabic faces leave out. It ships one weight and no italic, which is
// correct: scripture is never bolded or slanted.
//
// Using this face is not permission to typeset scripture. Verse text must come
// from an approved source and be verified by a human; the engine never writes
// it from memory.
const QURAN = amiriQuran('normal', { weights: ['400'], subsets: ['arabic'] });

// Kept as a comparison face, and as the fallback if Amiri ever fails to load.
const NASKH = notoNaskh('normal', { weights: ['400'], subsets: ['arabic'] });

// Latin UI face for labels and captions. Latin-only on purpose.
const UI = inter('normal', { weights: ['400', '700', '800'], subsets: ['latin'] });

export const FONT = {
  arabic: ARABIC.fontFamily,
  arabicQuran: QURAN.fontFamily,
  arabicAlt: NASKH.fontFamily,
  ui: UI.fontFamily,
} as const;

export type FontKey = keyof typeof FONT;

/**
 * Await this before capturing a frame. A still rendered before the webfonts
 * arrive shows fallback glyphs, which is indistinguishable from a real
 * shaping failure — so every composition that sets Arabic must gate on it.
 */
export const fontsReady = Promise.all(
  [ARABIC, QURAN, NASKH, UI].map((font) => font.waitUntilDone()),
);
