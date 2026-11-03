/**
 * Contact sheet for the six vendored effects, plus the checks that are numbers
 * rather than pictures.
 *
 * The panels are scaled-down whole frames: enough to judge placement, timing
 * state and layering. The table underneath asserts the things an eye cannot
 * confirm from a still — that a punch-in returns to 1.000, that the zoom guard
 * refuses an unsafe request, that a caption asked to sit on the face is moved
 * off it.
 *
 * Checks that fail are drawn in red. A red row in this image means the engine
 * is wrong, not the image.
 */

import React from 'react';
import { AbsoluteFill } from 'remotion';

import { FONT } from '../config/fonts';
import { DIAGNOSTIC, THEME } from '../config/theme';
import { BOTTOM_FADE } from '../effects/BottomFade';
import { LEAN_IN, SLOW_PUSH, safeZoom } from '../effects/camera';
import { KINETIC_CAPTION, captionLayout } from '../effects/KineticCaption';
import { unmetRequirements } from '../effects/index';
import { NAME_TAG } from '../effects/NameTag';
import { TEXT_BEHIND } from '../effects/TextBehind';
import type { FxCtx, FxDef } from '../lib/core';
import { e } from '../lib/ease';
import { chin } from '../lib/layout';
import { useFontsReady } from '../lib/measure';
import { isRtl } from '../lib/text';
import { proofCtx } from './ctx';
import { MiniStage } from './MiniStage';

const W = 1080;
const H = 1920;
const FPS = 30;
const SCALE = 0.3;
const PANEL_W = W * SCALE;
const PANEL_H = H * SCALE;

const ARABIC_LINE = 'الدرس الأول في المدرسة';

type Panel = { title: string; note: string; def: FxDef; c: FxCtx };

const panels = (): Panel[] => [
  {
    title: 'lean-in',
    note: 'held at the midpoint, room soft',
    def: LEAN_IN,
    c: proofCtx({ W, H, fps: FPS, t: 0.8, d: 1.6, options: { zoom: 1.35 } }),
  },
  {
    title: 'slow-push',
    note: 'at the end of the push',
    def: SLOW_PUSH,
    c: proofCtx({ W, H, fps: FPS, t: 3, d: 3 }),
  },
  {
    title: 'kinetic-caption',
    note: 'mid-reveal, Arabic line',
    def: KINETIC_CAPTION,
    c: proofCtx({ W, H, fps: FPS, t: 0.42, d: 2.4, options: { text: ARABIC_LINE, size: 68 } }),
  },
  {
    title: 'name-tag',
    note: 'sliding in from the edge',
    def: NAME_TAG,
    c: proofCtx({
      W,
      H,
      fps: FPS,
      t: 0.2,
      d: 2.4,
      options: { name: 'Nama Pembicara', role: 'Peran' },
    }),
  },
  {
    title: 'bottom-fade',
    note: 'full strength',
    def: BOTTOM_FADE,
    c: proofCtx({ W, H, fps: FPS, t: 1.2, d: 2.4 }),
  },
  {
    title: 'text-behind',
    note: 'holding behind the head',
    def: TEXT_BEHIND,
    c: proofCtx({ W, H, fps: FPS, t: 1.4, d: 3, options: { text: 'TADABBUR', height: 260 } }),
  },
];

type Check = { label: string; got: string; want: string; pass: boolean };

const near = (a: number, b: number, tol = 0.005) => Math.abs(a - b) <= tol;
const f3 = (n: number) => n.toFixed(3);

function runChecks(): Check[] {
  const checks: Check[] = [];
  const add = (label: string, got: string, want: string, pass: boolean) =>
    checks.push({ label, got, want, pass });

  // --- camera ---
  const leanAt = (t: number, d = 1.6, zoom = 1.35) =>
    LEAN_IN.camera?.(proofCtx({ W, H, fps: FPS, t, d, options: { zoom } }))?.zoom ?? NaN;

  add('lean-in starts at rest', f3(leanAt(0)), '1.000', near(leanAt(0), 1));
  const peak = leanAt(0.8);
  add('lean-in holds near the asked 1.35', f3(peak), '1.34 .. 1.37', peak > 1.34 && peak < 1.37);
  add('lean-in returns to rest', f3(leanAt(1.6)), '1.000', near(leanAt(1.6), 1, 0.02));

  const pushAt = (t: number) =>
    SLOW_PUSH.camera?.(proofCtx({ W, H, fps: FPS, t, d: 3 }))?.zoom ?? NaN;
  add('slow-push starts at rest', f3(pushAt(0)), '1.000', near(pushAt(0), 1));
  add('slow-push ends at the asked 1.5', f3(pushAt(3)), '1.500', near(pushAt(3), 1.5, 0.02));

  // The guard, asked for something that would crop the head.
  const guardCtx = proofCtx({ W, H, fps: FPS, t: 0, d: 1 });
  const guarded = safeZoom(guardCtx, 3);
  add('zoom guard refuses 3.0', f3(guarded), '<= 2.200', guarded <= 2.2 && guarded < 3);

  // --- caption placement ---
  const low = captionLayout(
    proofCtx({ W, H, fps: FPS, t: 2, d: 2.4, options: { text: 'Satu baris saja', y: 'low' } }),
  );
  add(
    'caption at "low" needs no moving',
    low ? String(low.moved) : 'null',
    'false',
    low !== null && low.moved === false,
  );

  const onFaceCtx = proofCtx({
    W,
    H,
    fps: FPS,
    t: 2,
    d: 2.4,
    options: { text: 'Satu baris saja', y: 0.34 },
  });
  const onFace = captionLayout(onFaceCtx);
  add(
    'caption asked onto the face is moved off it',
    onFace ? `moved=${onFace.moved} top=${Math.round(onFace.top)}` : 'null',
    `moved=true top >= ${Math.round(chin(onFaceCtx))}`,
    onFace !== null && onFace.moved && onFace.top >= chin(onFaceCtx),
  );

  const three = captionLayout(
    proofCtx({ W, H, fps: FPS, t: 2, d: 2.4, options: { text: 'satu / dua / tiga' } }),
  );
  add(
    'a third line is dropped, not squeezed in',
    three ? `lines=${three.lines.length} dropped=${three.dropped}` : 'null',
    'lines=2 dropped=1',
    three !== null && three.lines.length === 2 && three.dropped === 1,
  );

  // --- direction ---
  add('Arabic line is right-to-left', String(isRtl(ARABIC_LINE)), 'true', isRtl(ARABIC_LINE));
  add(
    'Indonesian line is left-to-right',
    String(isRtl('Pelajaran pertama')),
    'false',
    !isRtl('Pelajaran pertama'),
  );

  // --- easing endpoints ---
  const ends = `${f3(e('expo.out', 0, 0, 1))} / ${f3(e('expo.out', 1, 0, 1))}`;
  add('expo.out is endpoint-exact', ends, '0.000 / 1.000', ends === '0.000 / 1.000');

  // --- requirements ---
  const unmet = unmetRequirements('text-behind');
  add(
    'text-behind is still refused: no person matte',
    unmet.join(', ') || 'none',
    'personMatte',
    unmet.length === 1 && unmet[0] === 'personMatte',
  );
  add(
    'the face track is now available, so lean-in is allowed',
    unmetRequirements('lean-in').join(', ') || 'none',
    'none',
    unmetRequirements('lean-in').length === 0,
  );
  add(
    'bottom-fade needs nothing we lack',
    unmetRequirements('bottom-fade').join(', ') || 'none',
    'none',
    unmetRequirements('bottom-fade').length === 0,
  );

  return checks;
}

const Panel: React.FC<{ panel: Panel }> = ({ panel }) => (
  <div style={{ width: PANEL_W }}>
    <div
      style={{
        width: PANEL_W,
        height: PANEL_H,
        position: 'relative',
        overflow: 'hidden',
        borderRadius: 8,
        border: `1px solid ${THEME.hairline}`,
      }}
    >
      <div
        style={{
          position: 'absolute',
          width: W,
          height: H,
          transform: `scale(${SCALE})`,
          transformOrigin: '0 0',
        }}
      >
        <MiniStage def={panel.def} c={panel.c} />
      </div>
    </div>
    <div style={{ fontFamily: FONT.ui, fontSize: 20, fontWeight: 700, color: THEME.accent, marginTop: 10 }}>
      {panel.title}
    </div>
    <div style={{ fontFamily: FONT.ui, fontSize: 17, color: THEME.inkMuted, lineHeight: 1.35 }}>
      {panel.note}
    </div>
  </div>
);

export const EffectsProof: React.FC = () => {
  const ready = useFontsReady();
  if (!ready) return <AbsoluteFill style={{ backgroundColor: THEME.bg }} />;

  const checks = runChecks();
  const failed = checks.filter((c) => !c.pass).length;

  return (
    <AbsoluteFill style={{ backgroundColor: THEME.bg, padding: 34 }}>
      <div style={{ fontFamily: FONT.ui, fontSize: 34, fontWeight: 800, color: THEME.ink }}>
        Vendored effects — proof
      </div>
      <div style={{ fontFamily: FONT.ui, fontSize: 18, color: THEME.inkMuted, marginTop: 6, lineHeight: 1.45 }}>
        Six effects derived from facecammaxxing (MIT, see NOTICE). Room and body are stand-ins; the face
        path is synthetic. No footage, no person matte — so this proves the editorial logic and the
        layering, not the final look.
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20, marginTop: 22 }}>
        {panels().map((p) => (
          <Panel key={p.title} panel={p} />
        ))}
      </div>

      <div style={{ marginTop: 26 }}>
        <div
          style={{
            fontFamily: FONT.ui,
            fontSize: 22,
            fontWeight: 700,
            color: failed ? DIAGNOSTIC.fail : DIAGNOSTIC.pass,
            marginBottom: 10,
          }}
        >
          {failed === 0 ? `All ${checks.length} checks pass` : `${failed} of ${checks.length} checks FAILED`}
        </div>
        {checks.map((c) => (
          <div
            key={c.label}
            style={{
              display: 'flex',
              alignItems: 'baseline',
              gap: 12,
              borderTop: `1px solid ${THEME.hairline}`,
              padding: '7px 0',
              fontFamily: FONT.ui,
              fontSize: 18,
            }}
          >
            <span style={{ color: c.pass ? DIAGNOSTIC.pass : DIAGNOSTIC.fail, fontWeight: 700, width: 54 }}>
              {c.pass ? 'PASS' : 'FAIL'}
            </span>
            <span style={{ color: THEME.ink, flex: 1 }}>{c.label}</span>
            <span style={{ color: THEME.inkMuted, fontFamily: 'monospace', fontSize: 16 }}>
              got {c.got} · want {c.want}
            </span>
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};
