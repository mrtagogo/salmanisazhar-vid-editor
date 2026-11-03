/**
 * Stand-ins for the footage.
 *
 * There is no video here. A proof needs something in the frame so that camera
 * moves, parallax and occlusion can be seen at all, so the room is a measured
 * grid and the presenter is a flat silhouette built from the synthetic face.
 *
 * Both are labelled on screen. Nothing in this file may ever appear in a
 * render meant for publishing.
 */

import React from 'react';
import { AbsoluteFill } from 'remotion';

import { FONT } from '../config/fonts';
import { DIAGNOSTIC, THEME } from '../config/theme';
import type { Face, FxCtx } from '../lib/core';
import { faceBox } from '../lib/core';
import { chin, px, zones } from '../lib/layout';

/** A ruled wall, so a zoom or a parallax shift is measurable rather than felt. */
export const Room: React.FC<{ W: number; H: number }> = ({ W, H }) => {
  const step = 120;
  const lines: React.ReactNode[] = [];
  for (let x = 0; x <= W; x += step) {
    lines.push(<line key={`v${x}`} x1={x} y1={0} x2={x} y2={H} stroke={DIAGNOSTIC.grid} strokeWidth={x % 600 === 0 ? 3 : 1} />);
  }
  for (let y = 0; y <= H; y += step) {
    lines.push(<line key={`h${y}`} x1={0} y1={y} x2={W} y2={y} stroke={DIAGNOSTIC.grid} strokeWidth={y % 600 === 0 ? 3 : 1} />);
  }
  return (
    <AbsoluteFill style={{ background: '#1b2330' }}>
      <svg width={W} height={H} style={{ position: 'absolute', inset: 0 }}>
        {lines}
        {Array.from({ length: Math.floor(H / 600) + 1 }, (_, i) => (
          <text key={i} x={14} y={i * 600 + 44} fill={DIAGNOSTIC.grid} fontSize={34} fontFamily="monospace">
            {i * 600}
          </text>
        ))}
      </svg>
    </AbsoluteFill>
  );
};

/** A flat body, so a Behind layer is actually covered by something. */
export const Presenter: React.FC<{ face: Face; W: number; H: number }> = ({ face, W, H }) => {
  const headRx = face.w * 0.5;
  const headRy = face.w * 0.66;
  const headCy = face.y - face.w * 0.04;
  const shoulderY = headCy + headRy + face.w * 0.3;
  return (
    <svg width={W} height={H} style={{ position: 'absolute', inset: 0 }}>
      <g fill="#2f3a46">
        <ellipse cx={face.x} cy={headCy} rx={headRx} ry={headRy} />
        <rect x={face.x - face.w * 0.19} y={headCy + headRy * 0.6} width={face.w * 0.38} height={face.w * 0.5} />
        <path
          d={`M${face.x - face.w * 1.25},${H} Q${face.x - face.w * 1.1},${shoulderY} ${face.x},${shoulderY} Q${face.x + face.w * 1.1},${shoulderY} ${face.x + face.w * 1.25},${H} Z`}
        />
      </g>
      <text x={face.x} y={headCy + 10} fill="rgba(255,255,255,0.35)" fontSize={face.w * 0.11} textAnchor="middle" fontFamily="monospace">
        STAND-IN
      </text>
    </svg>
  );
};

/** The safe zones and the face guard, drawn so placement can be checked by eye. */
export const Guides: React.FC<{ c: FxCtx }> = ({ c }) => {
  const z = zones(c);
  const g = faceBox(c.face);
  const label = (text: string, y: number) => (
    <text x={z.margin + 8} y={y - 10} fill={DIAGNOSTIC.label} fontSize={px(c, 22)} fontFamily={FONT.ui}>
      {text}
    </text>
  );
  return (
    <svg width={c.W} height={c.H} style={{ position: 'absolute', inset: 0 }}>
      <line x1={0} y1={z.top} x2={c.W} y2={z.top} stroke={DIAGNOSTIC.safe} strokeWidth={2} strokeDasharray="12 10" />
      <line x1={0} y1={z.bottom} x2={c.W} y2={z.bottom} stroke={DIAGNOSTIC.safe} strokeWidth={2} strokeDasharray="12 10" />
      {label('safe zone top', z.top)}
      {label('safe zone bottom', z.bottom)}
      <line x1={0} y1={chin(c)} x2={c.W} y2={chin(c)} stroke={DIAGNOSTIC.label} strokeWidth={1} strokeDasharray="4 8" />
      <ellipse
        cx={(g.left + g.right) / 2}
        cy={(g.top + g.bottom) / 2}
        rx={(g.right - g.left) / 2}
        ry={(g.bottom - g.top) / 2}
        fill="none"
        stroke={DIAGNOSTIC.guard}
        strokeWidth={3}
        strokeDasharray="16 12"
      />
      <text x={(g.left + g.right) / 2} y={g.top - px(c, 12)} fill={DIAGNOSTIC.guard} fontSize={px(c, 24)} textAnchor="middle" fontFamily={FONT.ui}>
        face guard — nothing may cross this
      </text>
    </svg>
  );
};

/** A corner stamp, so a proof frame can never be mistaken for a deliverable. */
export const ProofStamp: React.FC<{ c: FxCtx; text: string }> = ({ c, text }) => (
  <div
    style={{
      position: 'absolute',
      left: px(c, 24),
      top: px(c, 24),
      padding: `${px(c, 8)}px ${px(c, 16)}px`,
      background: THEME.panel,
      border: `1px solid ${THEME.hairline}`,
      borderRadius: px(c, 8),
      color: THEME.inkMuted,
      fontFamily: FONT.ui,
      fontSize: px(c, 22),
    }}
  >
    {text}
  </div>
);
