/**
 * Remotion entry point. Remotion loads this file, which registers the
 * composition tree; nothing else should run from here.
 */

import { registerRoot } from 'remotion';

import { RemotionRoot } from './Root';

registerRoot(RemotionRoot);
