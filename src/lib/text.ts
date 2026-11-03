/**
 * Script detection for subtitle lines.
 *
 * A kajian mixes Indonesian and Arabic, often line by line, so direction is
 * decided per line rather than once for the whole caption. Getting this wrong
 * does not look like a bug: Arabic laid out left-to-right still renders every
 * glyph, it just puts the words in the wrong order, which only a reader of the
 * language notices.
 */

/**
 * Arabic and Arabic-adjacent blocks: Arabic, Arabic Supplement, Arabic
 * Extended-B and -A, and the presentation forms.
 */
const ARABIC = /[؀-ۿݐ-ݿࡰ-࢟ࢠ-ࣿﭐ-﷿ﹰ-﻿]/;

export const hasArabic = (text: string) => ARABIC.test(text);

/**
 * True when a line should be laid out right-to-left.
 *
 * Based on the first strong character rather than a count, which is how the
 * Unicode bidi algorithm picks a paragraph's direction: a mostly-Arabic line
 * that opens with a Latin name is still an Arabic line, and a mostly-Latin
 * line quoting one Arabic term is not.
 */
export function isRtl(text: string): boolean {
  for (const ch of text) {
    if (ARABIC.test(ch)) return true;
    if (/[A-Za-z]/.test(ch)) return false;
  }
  return false;
}

/**
 * Split a line into words for a word-by-word reveal.
 *
 * Splitting NEVER goes below word level. Arabic letters join to their
 * neighbours inside a word, so revealing a word letter by letter would break
 * the cursive join and change the shapes on screen. Between words there is no
 * join, so per-word spans are safe in both scripts.
 */
export const words = (line: string) => line.split(/\s+/).filter(Boolean);
