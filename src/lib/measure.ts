/**
 * Text measurement, for type that has to fit a given width.
 *
 * The reference measures text with an async hook called once per line, inside
 * the loop that renders the lines. That breaks React's rules of hooks (the
 * reference silences the lint rule), and it has a second, quieter fault: the
 * hook's cached value is keyed by text but read without checking the key, so a
 * caption whose words change between frames can be laid out at the previous
 * line's size.
 *
 * Both faults come from measuring asynchronously. Measuring is only async
 * because the fonts have to arrive first — so that is the only thing awaited
 * here, exactly once, and measurement itself is a plain synchronous function
 * that may be called anywhere, including inside a loop.
 */

import { useEffect, useState } from 'react';
import { cancelRender, continueRender, delayRender } from 'remotion';

import { fontsReady } from '../config/fonts';

let fontsArrived = false;
const arrival = fontsReady
  .then(() => document.fonts.ready)
  .then(() => {
    fontsArrived = true;
  });

/**
 * False until the webfonts are in the document, and the frame is held until
 * they are. Measuring before that returns fallback-font widths, which would
 * size every caption wrongly in a way that looks like a layout bug.
 */
export function useFontsReady(): boolean {
  const [ok, setOk] = useState(fontsArrived);
  const [handle] = useState(() => (fontsArrived ? null : delayRender('waiting for webfonts')));

  useEffect(() => {
    if (ok) return;
    arrival
      .then(() => {
        setOk(true);
        if (handle !== null) continueRender(handle);
      })
      .catch((err) => cancelRender(err));
  }, [ok, handle]);

  return ok;
}

let ctx: CanvasRenderingContext2D | null = null;
const widths = new Map<string, number>();

/** Width of `text` at 100 px in `family`, cached. Letter spacing is in em. */
export function measureWidth(text: string, family: string, weight = '400', spacing = 0): number {
  const key = `${family}|${weight}|${spacing}|${text}`;
  const hit = widths.get(key);
  if (hit !== undefined) return hit;

  if (!ctx) {
    const canvas = document.createElement('canvas');
    const got = canvas.getContext('2d');
    if (!got) throw new Error('no 2d canvas context: cannot measure text');
    ctx = got;
  }
  ctx.font = `${weight} 100px "${family}"`;
  // measureText ignores letter-spacing, so the gaps are added back by hand.
  const w = ctx.measureText(text).width + spacing * 100 * Math.max(0, [...text].length - 1);
  widths.set(key, w);
  return w;
}

/**
 * The font size at which `text` is exactly `maxW` wide, or null if there is
 * nothing to measure. Call only once useFontsReady() is true.
 */
export function fitSize(
  text: string,
  family: string,
  maxW: number,
  weight = '400',
  spacing = 0,
): number | null {
  if (!text) return null;
  const w = measureWidth(text, family, weight, spacing);
  return w > 0 ? (100 * maxW) / w : null;
}
