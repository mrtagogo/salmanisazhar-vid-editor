/**
 * Caption proof, at full frame size.
 *
 * The one thing worth looking at closely: a two-line subtitle where one line
 * is Indonesian and the other Arabic. Direction is the fault that hides —
 * Arabic laid out left-to-right still draws every glyph, it just reverses the
 * word order, and only a reader of the language notices.
 *
 * The Arabic sample is ordinary vocabulary. No Qur'anic text is typed here,
 * for the same reason as in ArabicShapingProof: the engine does not write
 * scripture, and quoting it from memory would be exactly that.
 */

import React from 'react';
import { AbsoluteFill } from 'remotion';

import { FONT } from '../config/fonts';
import { DIAGNOSTIC, THEME } from '../config/theme';
import { KINETIC_CAPTION } from '../effects/KineticCaption';
import { px } from '../lib/layout';
import { proofCtx } from './ctx';
import { MiniStage } from './MiniStage';
import { ProofStamp } from './Stand';

/** "The first lesson at the school" — plain vocabulary, four words. */
const ARABIC_LINE = 'الدرس الأول في المدرسة';
const INDONESIAN_LINE = 'Pelajaran *pertama* di sekolah';

const CHECKS = [
  'Line 1 reads left-to-right; the keyword "pertama" is the accent colour, the rest is ink.',
  `Line 2 reads right-to-left: rightmost word is الدرس, then الأول, then في, leftmost المدرسة.`,
  'Arabic letters inside each word stay joined — the per-word reveal must not break a join.',
  'The whole block sits below the chin and inside the safe zone. It never crosses the face guard.',
  'Two lines only. A third line passed in is dropped, not shrunk to fit.',
];

export const CaptionProof: React.FC = () => {
  const W = 1080;
  const H = 1920;
  const c = proofCtx({
    W,
    H,
    fps: 30,
    t: 1.6,
    d: 2.6,
    options: {
      // A third line is passed deliberately: the house rule is two.
      text: `${INDONESIAN_LINE} / ${ARABIC_LINE} / baris ketiga yang harus dibuang`,
      y: 'low',
      size: 68,
    },
  });

  return (
    <AbsoluteFill style={{ backgroundColor: THEME.bg }}>
      <MiniStage def={KINETIC_CAPTION} c={c} guides />
      <ProofStamp c={c} text="PROOF — stand-in room and body, synthetic face track" />

      <div
        style={{
          position: 'absolute',
          left: px(c, 24),
          right: px(c, 24),
          // Below the bottom safe zone, which is empty: anywhere higher and
          // the panel hides the very guides it is asking you to read.
          top: px(c, 1600),
          padding: px(c, 18),
          background: 'rgba(15, 17, 21, 0.78)',
          border: `1px solid ${THEME.hairline}`,
          borderRadius: px(c, 10),
          fontFamily: FONT.ui,
        }}
      >
        <div style={{ color: DIAGNOSTIC.label, fontSize: px(c, 24), fontWeight: 700, marginBottom: px(c, 10) }}>
          What to check
        </div>
        {CHECKS.map((line, i) => (
          <div key={i} style={{ color: THEME.inkMuted, fontSize: px(c, 21), lineHeight: 1.45, marginBottom: px(c, 5) }}>
            {i + 1}. {line}
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};
