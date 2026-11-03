/**
 * Arabic shaping proof.
 *
 * Renders Arabic text that is hard to get right, so a human can confirm by eye
 * that Chromium shaped it correctly before any Arabic is put on screen in a
 * real video. Render it with:
 *
 *   npm run proof:arabic
 *
 * Every sample below is ordinary Arabic vocabulary or a standard grammar
 * paradigm. NO Qur'anic text is used anywhere in this file, on purpose: the
 * engine is not permitted to generate or reproduce scripture, and quoting it
 * from memory would be exactly that. Real verses must come from an approved
 * source, verified by a human, and are never typed by the engine.
 */

import React, { useEffect, useState } from 'react';
import { AbsoluteFill, cancelRender, continueRender, delayRender } from 'remotion';

import { FONT, fontsReady } from '../config/fonts';
import { THEME } from '../config/theme';

const PAD = 56;

/** One labelled check: what to look at, and what correct looks like. */
const Row: React.FC<{
  index: number;
  label: string;
  expect: string;
  children: React.ReactNode;
}> = ({ index, label, expect, children }) => (
  <div
    style={{
      borderTop: `1px solid ${THEME.hairline}`,
      paddingTop: 16,
      display: 'flex',
      flexDirection: 'column',
      gap: 10,
    }}
  >
    <div
      style={{
        fontFamily: FONT.ui,
        fontSize: 19,
        fontWeight: 700,
        color: THEME.accent,
        letterSpacing: 0.4,
      }}
    >
      {index}. {label}
    </div>
    {children}
    <div style={{ fontFamily: FONT.ui, fontSize: 16, color: THEME.inkMuted }}>
      Expect: {expect}
    </div>
  </div>
);

/** An Arabic sample. Direction is explicit so bidi is never left to chance. */
const Sample: React.FC<{
  text: string;
  family?: string;
  size?: number;
  ltr?: boolean;
}> = ({ text, family = FONT.arabic, size = 58, ltr = false }) => (
  <div
    style={{
      fontFamily: family,
      fontSize: size,
      lineHeight: 1.55,
      color: THEME.ink,
      direction: ltr ? 'ltr' : 'rtl',
      textAlign: ltr ? 'left' : 'right',
      // Harakat sit above and below the baseline; without room they clip.
      paddingBottom: 6,
    }}
  >
    {text}
  </div>
);

const Caption: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div style={{ fontFamily: FONT.ui, fontSize: 15, color: THEME.inkMuted }}>
    {children}
  </div>
);

export const ArabicShapingProof: React.FC = () => {
  // Without this guard the still can be captured before the webfonts arrive,
  // which would show fallback glyphs and look exactly like a shaping failure.
  const [handle] = useState(() => delayRender('loading Arabic webfonts'));
  useEffect(() => {
    fontsReady
      .then(() => continueRender(handle))
      .catch((err) => cancelRender(err));
  }, [handle]);

  return (
    <AbsoluteFill style={{ backgroundColor: THEME.bg, padding: PAD }}>
      <div style={{ marginBottom: 22 }}>
        <div
          style={{
            fontFamily: FONT.ui,
            fontSize: 34,
            fontWeight: 800,
            color: THEME.ink,
          }}
        >
          Arabic shaping proof
        </div>
        <div
          style={{
            fontFamily: FONT.ui,
            fontSize: 17,
            color: THEME.inkMuted,
            marginTop: 6,
          }}
        >
          Non-scriptural samples only. Primary face: Amiri.
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
        <Row
          index={1}
          label="Cursive joining"
          expect="the top line is ONE connected word; the lower line is separate letters"
        >
          <Sample text="العربية" />
          <Sample text="ا ل ع ر ب ي ة" size={46} />
        </Row>

        <Row
          index={2}
          label="Lam-alef ligature"
          expect="lam+alef fuses into a single crossed glyph, not two upright strokes"
        >
          <Sample text="لا — طلاب" />
        </Row>

        <Row
          index={3}
          label="Simple harakat"
          expect="three fatha strokes, one above each letter, none drifting"
        >
          <Sample text="كَتَبَ" />
        </Row>

        <Row
          index={4}
          label="Stacked harakat (hardest case)"
          expect="shadda sits above the ra with the kasra below the letter, and the final dammatan is a double curl"
        >
          <Sample text="مُدَرِّسٌ" />
          <Sample text="الْكِتَابُ" />
          <Caption>
            Second line checks sukun over the lam and a final damma.
          </Caption>
        </Row>

        <Row
          index={5}
          label="RTL order and digits"
          expect="text begins at the RIGHT edge; the number reads 42 in both lines"
        >
          <Sample text="الصَّفْحَة ٤٢" />
          <Sample text="الصفحة 42" />
        </Row>

        <Row
          index={6}
          label="Mixed Latin and Arabic (bidi)"
          expect="Latin runs left-to-right, Arabic right-to-left, in one line"
        >
          <Sample text="Tadabbur Motion — الحَرَكَة" ltr />
        </Row>

        <Row
          index={7}
          label="Font control"
          expect="lines 1-2 (Amiri) look visibly lighter than lines 3-4; if all four match, no Arabic webfont loaded"
        >
          <Sample text="مُدَرِّسٌ" family={FONT.arabic} size={46} />
          <Caption>↑ Amiri — general Arabic</Caption>
          <Sample text="مُدَرِّسٌ" family={FONT.arabicQuran} size={46} />
          <Caption>↑ Amiri Quran — vocalised mushaf face</Caption>
          <Sample text="مُدَرِّسٌ" family={FONT.arabicAlt} size={46} />
          <Caption>↑ Noto Naskh Arabic — fallback face</Caption>
          <Sample text="مُدَرِّسٌ" family={FONT.ui} size={46} />
          <Caption>↑ Latin-only UI face, so this one falls back</Caption>
          <Caption>
            Note: lines 1 and 2 looking alike is correct — Amiri Quran is a
            Qur'an-specific cut of Amiri and differs only in the annotation
            marks, not the letterforms. Line 4 is the warning: a face with no
            Arabic subset still renders Arabic, using whatever the machine
            happens to have. Missing Arabic coverage therefore never looks
            broken — it looks different on every machine, which is worse.
          </Caption>
        </Row>
      </div>
    </AbsoluteFill>
  );
};
