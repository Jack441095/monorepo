// GENERATED FILE — derived from tokens/nite_design_tokens.json. DO NOT EDIT BY HAND.
Regenerate with: python3 tools/generate_tokens.py
// NITE DSP Design System 1.0.1 — EMBER — Warm Technical Minimalism

export const NITE_DESIGN_SYSTEM_VERSION = '1.0.1' as const;

export const color = {
  color_surface_base: '#0C0B09',
  color_surface_raised: '#14120F',
  color_surface_overlay: '#1C1915',
  color_surface_inset: '#080706',
  color_surface_hover: '#191612',
  color_elevation_modal: '#201C16',
  color_border_hairline_subtle: '#2A261F',
  color_border_hairline_strong: '#2A261F',
  color_text_primary: '#EDE8E0',
  color_text_secondary: '#A39B8F',
  color_text_tertiary: '#827B71',
  color_text_disabled: '#4A453D',
  color_text_inverse: '#1A1207',
  color_interactive_base: '#E89B3C',
  color_interactive_bright: '#F7B955',
  color_interactive_dim: '#8A5F28',
  color_interactive_ink: '#1A1207',
  color_semantic_playing: '#7FB069',
  color_semantic_success: '#7FB069',
  color_semantic_warning: '#E5B84B',
  color_semantic_error: '#E5484D',
  color_semantic_destructive: '#E5484D',
  color_semantic_favorite: '#D9A75A',
  color_semantic_unknown: '#4A453D',
  color_semantic_disabled: '#4A453D',
  state_playing: '#7FB069',
  state_success: '#7FB069',
  state_warning: '#E5B84B',
  state_error: '#E5484D',
  state_favorite: '#D9A75A',
  state_unknown: '#4A453D',
  state_disabled: '#4A453D',
  interactive_default: '#E89B3C',
  interactive_hover: '#F7B955',
  interactive_selected: '#E89B3C',
  text_onAccent: '#1A1207',
  slo_category_kick: '#C96F4A',
  slo_category_snare: '#E3C567',
  slo_category_clap: '#D98BA6',
  slo_category_hihat: '#9FC2A5',
  slo_category_percussion: '#B98BD6',
  slo_category_bass: '#6E93B8',
  slo_category_synth: '#7FB0C4',
  slo_category_vocal: '#E0A96B',
  slo_category_unknown: '#4A453D',
  kenn_severity_high: '#E5484D',
  kenn_severity_medium: '#E5B84B',
  kenn_severity_low: '#7FB069',
} as const;

export const dimension = {
  space_xs: 4,
  space_s: 8,
  space_m: 12,
  space_l: 16,
  space_xl: 24,
  space_xxl: 32,
  radius_s: 3,
  radius_m: 6,
  radius_l: 8,
  stroke_hairline: 1,
  stroke_icon: 1.5,
  stroke_emphasis: 2,
  stroke_heavy: 3,
  comp_row_height: 27,
  comp_map_point_size: 7,
  comp_type_minSizePx: 10,
} as const;

export const duration = {
  motion_fast_duration: 120,
  motion_standard_duration: 180,
  motion_slow_duration: 300,
  motion_pulse_duration: 400,
  comp_tooltip_delayMs: 250,
} as const;

export const opacity = {
  opacity_dimmedFocusMode: 0.15,
  opacity_proposalUncertain: 0.6,
  opacity_similarityEdgeMax: 0.75,
  opacity_softFill: 0.55,
  opacity_vizFillMax: 0.6,
} as const;

export const motion = {
  easing: 'cubic-bezier(0.25, 1, 0.5, 1)',
} as const;
