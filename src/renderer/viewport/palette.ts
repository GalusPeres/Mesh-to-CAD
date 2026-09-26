// Colours of the 3D scene (docs/DESIGN.md 6). This file and styles/tokens.css
// are the only places with colour literals.

export const SCENE_COLORS = {
  scan: '#B8BCC2',
  scanBackFace: '#8A6F6A',
  selection: '#3F87EE',
  pass: '#4DAF63',
  fail: '#D24B35',
  failFar: '#7A1F14',
  body: '#C4A57A',
  bodyEdgesDark: '#2A2723',
  bodyEdgesLight: '#3A3630',
  construction: '#D39B2A',
  section: '#4DAF63',
  regionBorder: '#1C1D20',
  hemisphereSky: '#FFFFFF',
  headlight: '#FFFFFF',
  hemisphereGround: '#50545C',
  axisX: '#D2524A',
  axisY: '#4E9F55',
  axisZ: '#3C78D8',
  activeHandle: '#3F87EE',
  brushLight: '#FFFFFF',
  brushDark: '#1C1D20',
} as const;

/** Mix factors over the base colour and opacities of the scene styles. */
export const SCENE_MIX = {
  selection: 0.55,
  hover: 0.25,
  passFail: 0.7,
  constructionFill: 0.45,
  patchFill: 0.35,
  xrayOpacity: 0.3,
  sketchGhostOpacity: 0.15,
  triangleEdges: 0.12,
  regionBorder: 0.6,
} as const;

/** Ten muted region colours; hues 225-290 degrees are excluded (selection blue). */
export const REGION_PALETTE = [
  '#C87979',
  '#DE9871',
  '#A59145',
  '#CDC072',
  '#68BF9B',
  '#669E9A',
  '#6CCDEA',
  '#9786C9',
  '#C398D6',
  '#F2A3C1',
] as const;

export type DeviationScheme = 'standard' | 'colorBlind';

/**
 * Deviation colours from far below to far above: out of range, three steps,
 * tolerance band, three steps, out of range. Index 9 is "no data".
 */
export const DEVIATION_COLORS: Record<DeviationScheme, readonly string[]> = {
  standard: [
    '#1E2F66',
    '#2E56B8',
    '#3C8DDB',
    '#5CC3D6',
    '#4DAF63',
    '#E6CF4F',
    '#EC9A3A',
    '#D24B35',
    '#7A1F14',
    '#8C9096',
  ],
  colorBlind: [
    '#08306B',
    '#2166AC',
    '#4393C3',
    '#92C5DE',
    '#E3E3E3',
    '#F4A582',
    '#D6604D',
    '#B2182B',
    '#67001F',
    '#8C9096',
  ],
};
