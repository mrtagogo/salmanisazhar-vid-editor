/**
 * The uncut recording, with every proposed cut marked by its number.
 *
 * The decision sheet asks for an answer in numbers. This is where a number
 * can be looked at: scrub to it, see what is inside it, and hear it, before
 * deciding whether it should go.
 *
 * It shows the UNCUT recording on purpose. The sheet's timecodes are on that
 * timeline, so reviewing them against a rough cut would be reading the right
 * numbers off the wrong clock.
 *
 * This is an instrument, not a deliverable. Nothing here belongs in a render
 * meant for publishing.
 */

import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';

import { FONT } from '../config/fonts';
import { BRAND, DIAGNOSTIC, THEME } from '../config/theme';
import { Kajian, type ProjectData } from './Kajian';

export type Mark = {
  number: string | null;
  id: string;
  kind: string | null;
  status: string;
  start: number;
  end: number;
};

/** What the engine currently intends to do with a span. */
const statusColour = (status: string) =>
  status === 'auto'
    ? BRAND.nyalaPelita
    : status === 'blocked'
      ? DIAGNOSTIC.safe
      : THEME.ink;

const statusWord = (status: string) =>
  status === 'auto' ? 'AKAN DIPOTONG' : status === 'blocked' ? 'DITOLAK MESIN' : 'PERLU DIPUTUSKAN';

const clock = (seconds: number) => {
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, '0')}:${(seconds - minutes * 60).toFixed(2).padStart(5, '0')}`;
};

export const Review: React.FC<{
  /** Read by calculateMetadata; the component works from `data`. */
  slug?: string;
  data?: ProjectData;
  marks?: Mark[];
}> = ({ data, marks }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();

  if (!data) return <AbsoluteFill style={{ backgroundColor: THEME.bg }} />;

  const all = marks ?? [];
  const t = frame / fps;
  const here = all.find((m) => t >= m.start && t < m.end);
  const total = data.durationSeconds || 1;
  const scale = width / 1080;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: THEME.bg,
        scale: 1.036
      }}
    >
      {/* The talk itself, subtitles and all, so nothing is judged in isolation. */}
      <Kajian data={data} showWithheld />

      {/* Inside a proposed cut, the picture is tinted and the span named. */}
      {here ? (
        <AbsoluteFill
          style={{
            border: `${8 * scale}px solid ${statusColour(here.status)}`,
            backgroundColor:
              here.status === 'auto' ? 'rgba(224, 163, 60, 0.10)' : 'transparent',
          }}
        />
      ) : null}

      <div
        style={{
          position: 'absolute',
          left: 28 * scale,
          right: 28 * scale,
          top: 28 * scale,
          padding: `${16 * scale}px ${20 * scale}px`,
          borderRadius: 12 * scale,
          background: BRAND.tintaMalam,
          fontFamily: FONT.ui,
          color: THEME.ink,
        }}
      >
        <div style={{ fontSize: 30 * scale, fontWeight: 500 }}>
          {clock(t)}
          <span style={{ color: THEME.inkMuted, fontSize: 24 * scale }}>
            {' '}/ {clock(total)}
          </span>
        </div>
        {here ? (
          <div style={{ marginTop: 8 * scale, color: statusColour(here.status) }}>
            <span style={{ fontSize: 44 * scale, fontWeight: 500 }}>
              #{here.number ?? '?'}
            </span>
            <span style={{ fontSize: 26 * scale, marginLeft: 12 * scale }}>
              {statusWord(here.status)} · {here.kind} · {(here.end - here.start).toFixed(2)}s
            </span>
            <div style={{ fontSize: 22 * scale, color: THEME.inkMuted }}>
              {clock(here.start)} – {clock(here.end)}
            </div>
          </div>
        ) : (
          <div style={{ marginTop: 8 * scale, fontSize: 24 * scale, color: THEME.inkMuted }}>
            di luar usulan potong
          </div>
        )}
      </div>

      {/* Where every proposal sits in the talk, and where you are in it. */}
      <div
        style={{
          position: 'absolute',
          left: 28 * scale,
          right: 28 * scale,
          bottom: 28 * scale,
          height: 56 * scale,
          borderRadius: 10 * scale,
          background: BRAND.tintaMalam,
          overflow: 'hidden',
        }}
      >
        {all.map((m) => (
          <div
            key={m.id}
            title={m.id}
            style={{
              position: 'absolute',
              left: `${(m.start / total) * 100}%`,
              width: `${Math.max(0.35, ((m.end - m.start) / total) * 100)}%`,
              top: 0,
              bottom: 0,
              background: statusColour(m.status),
              opacity: here && here.id === m.id ? 1 : 0.45,
            }}
          />
        ))}
        <div
          style={{
            position: 'absolute',
            left: `${(t / total) * 100}%`,
            top: 0,
            bottom: 0,
            width: 3 * scale,
            background: BRAND.kapurHangat,
          }}
        />
      </div>
    </AbsoluteFill>
  );
};
