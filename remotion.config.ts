import { Config } from '@remotion/cli/config';

// Both output formats are 30 FPS; see `output` in engine.config.json. The
// composition layer is the only place that deals in frames — project data
// keeps every timestamp in seconds.
Config.setVideoImageFormat('jpeg');
Config.setOverwriteOutput(true);

// Text shaping is the whole point of the Arabic proof, so stills must be
// captured losslessly: JPEG artefacts around harakat would be impossible to
// tell apart from real rendering faults.
Config.setStillImageFormat('png');

// Chromium does the Arabic shaping. Keeping the default font rendering means
// what we verify here is what a render on another machine produces.
Config.setChromiumOpenGlRenderer('angle');
