/**
 * Easing curves.
 *
 * The effects borrowed from facecammaxxing name their curves the way GSAP does
 * ('expo.out', 'power2.in', 'sine.inOut'). GSAP itself is NOT a dependency
 * here: it ships under the GreenSock "Standard 'no charge' License", which is
 * not MIT, and the six effects we took use only named curves — none of them
 * uses gsap's timeline. So the names stay and the curves are implemented from
 * the standard formulas.
 *
 * Two deliberate differences from gsap.parseEase:
 *
 *   1. These are endpoint-exact: f(0) is exactly 0 and f(1) exactly 1. GSAP's
 *      expo family is off by about a thousandth at the ends.
 *   2. An unknown name throws. gsap.parseEase quietly returns undefined, and a
 *      typo then animates linearly, which is the kind of fault you only notice
 *      months later in a render you have already published.
 */

/** power1 = quadratic, power2 = cubic, power3 = quartic, power4 = quintic. */
const POWER_EXPONENT: Record<string, number> = {
  power0: 1,
  power1: 2,
  power2: 3,
  power3: 4,
  power4: 5,
};

type Curve = (p: number) => number;

/** Build the in / out / inOut trio from a single "in" curve. */
const variants = (easeIn: Curve): Record<string, Curve> => ({
  in: easeIn,
  out: (p) => 1 - easeIn(1 - p),
  inOut: (p) => (p < 0.5 ? easeIn(p * 2) / 2 : 1 - easeIn((1 - p) * 2) / 2),
});

// 2^(10*(p-1)) is 2^-10 at p = 0, not 0. Dividing the shifted curve by 1023
// pins both ends exactly while keeping the shape.
const expoIn: Curve = (p) => (p <= 0 ? 0 : p >= 1 ? 1 : (Math.pow(2, 10 * p) - 1) / 1023);

const FAMILIES: Record<string, Record<string, Curve>> = {
  linear: { in: (p) => p, out: (p) => p, inOut: (p) => p },
  sine: variants((p) => 1 - Math.cos((p * Math.PI) / 2)),
  expo: variants(expoIn),
  ...Object.fromEntries(
    Object.entries(POWER_EXPONENT).map(([name, n]) => [name, variants((p) => Math.pow(p, n))]),
  ),
};

const cache = new Map<string, Curve>();

/** Look up a curve by its GSAP-style name, e.g. 'expo.out' or 'power2.inOut'. */
export function curve(name: string): Curve {
  const hit = cache.get(name);
  if (hit) return hit;

  const [family, variant = 'out'] = name.split('.');
  const found = FAMILIES[family]?.[variant];
  if (!found) {
    throw new Error(
      `unknown easing "${name}" — expected <${Object.keys(FAMILIES).join(' | ')}>.<in | out | inOut>`,
    );
  }
  cache.set(name, found);
  return found;
}

export const clamp = (x: number, a = 0, b = 1) => Math.max(a, Math.min(b, x));
export const lerp = (a: number, b: number, k: number) => a + (b - a) * k;

/**
 * Eased 0..1 progress of a move that starts at `t0` and lasts `dur`.
 *
 * Named `e` to match the reference, where it appears in nearly every line of
 * effect code and a longer name would drown the geometry.
 */
export const e = (name: string, t: number, t0: number, dur: number) =>
  dur <= 0 ? (t >= t0 ? 1 : 0) : curve(name)(clamp((t - t0) / dur));

/** Eased 0..1 between two reference frames. */
export const fr = (f: number, a: number, b: number, name = 'power2.inOut') => e(name, f, a, b - a);
