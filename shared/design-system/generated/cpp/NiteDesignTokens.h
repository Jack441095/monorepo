// GENERATED FILE — derived from tokens/nite_design_tokens.json. DO NOT EDIT BY HAND.
// Regenerate with: python3 tools/generate_tokens.py
//
#pragma once
//
// NITE DSP Design System 1.0.1 — EMBER — Warm Technical Minimalism
// Frozen: 2026-08-22. Change control: DESIGN_SYSTEM_V1 §21.
//
// Compile-time constants. No allocation; safe for paint paths.

#include <cstdint>

namespace nite::design {

struct Version { static constexpr const char* kString = "1.0.1"; };

struct Rgba {
    std::uint8_t r, g, b;
    float a;
};

namespace colour {
inline constexpr Rgba k_color_surface_base { 0x0c, 0x0b, 0x09, 1.00f }; // #0C0B09
inline constexpr Rgba k_color_surface_raised { 0x14, 0x12, 0x0f, 1.00f }; // #14120F
inline constexpr Rgba k_color_surface_overlay { 0x1c, 0x19, 0x15, 1.00f }; // #1C1915
inline constexpr Rgba k_color_surface_inset { 0x08, 0x07, 0x06, 1.00f }; // #080706
inline constexpr Rgba k_color_surface_hover { 0x19, 0x16, 0x12, 1.00f }; // #191612
inline constexpr Rgba k_color_elevation_modal { 0x20, 0x1c, 0x16, 1.00f }; // #201C16
inline constexpr Rgba k_color_border_hairline_subtle { 0x2a, 0x26, 0x1f, 0.55f }; // #2A261F
inline constexpr Rgba k_color_border_hairline_strong { 0x2a, 0x26, 0x1f, 0.90f }; // #2A261F
inline constexpr Rgba k_color_text_primary { 0xed, 0xe8, 0xe0, 1.00f }; // #EDE8E0
inline constexpr Rgba k_color_text_secondary { 0xa3, 0x9b, 0x8f, 1.00f }; // #A39B8F
inline constexpr Rgba k_color_text_tertiary { 0x82, 0x7b, 0x71, 1.00f }; // #827B71
inline constexpr Rgba k_color_text_disabled { 0x4a, 0x45, 0x3d, 1.00f }; // #4A453D
inline constexpr Rgba k_color_text_inverse { 0x1a, 0x12, 0x07, 1.00f }; // #1A1207
inline constexpr Rgba k_color_interactive_base { 0xe8, 0x9b, 0x3c, 1.00f }; // #E89B3C
inline constexpr Rgba k_color_interactive_bright { 0xf7, 0xb9, 0x55, 1.00f }; // #F7B955
inline constexpr Rgba k_color_interactive_dim { 0x8a, 0x5f, 0x28, 0.35f }; // #8A5F28
inline constexpr Rgba k_color_interactive_ink { 0x1a, 0x12, 0x07, 1.00f }; // #1A1207
inline constexpr Rgba k_color_semantic_playing { 0x7f, 0xb0, 0x69, 1.00f }; // #7FB069
inline constexpr Rgba k_color_semantic_success { 0x7f, 0xb0, 0x69, 1.00f }; // #7FB069
inline constexpr Rgba k_color_semantic_warning { 0xe5, 0xb8, 0x4b, 1.00f }; // #E5B84B
inline constexpr Rgba k_color_semantic_error { 0xe5, 0x48, 0x4d, 1.00f }; // #E5484D
inline constexpr Rgba k_color_semantic_destructive { 0xe5, 0x48, 0x4d, 1.00f }; // #E5484D
inline constexpr Rgba k_color_semantic_favorite { 0xd9, 0xa7, 0x5a, 1.00f }; // #D9A75A
inline constexpr Rgba k_color_semantic_unknown { 0x4a, 0x45, 0x3d, 1.00f }; // #4A453D
inline constexpr Rgba k_color_semantic_disabled { 0x4a, 0x45, 0x3d, 1.00f }; // #4A453D
inline constexpr Rgba k_state_playing { 0x7f, 0xb0, 0x69, 1.00f }; // #7FB069
inline constexpr Rgba k_state_success { 0x7f, 0xb0, 0x69, 1.00f }; // #7FB069
inline constexpr Rgba k_state_warning { 0xe5, 0xb8, 0x4b, 1.00f }; // #E5B84B
inline constexpr Rgba k_state_error { 0xe5, 0x48, 0x4d, 1.00f }; // #E5484D
inline constexpr Rgba k_state_favorite { 0xd9, 0xa7, 0x5a, 1.00f }; // #D9A75A
inline constexpr Rgba k_state_unknown { 0x4a, 0x45, 0x3d, 1.00f }; // #4A453D
inline constexpr Rgba k_state_disabled { 0x4a, 0x45, 0x3d, 1.00f }; // #4A453D
inline constexpr Rgba k_interactive_default { 0xe8, 0x9b, 0x3c, 1.00f }; // #E89B3C
inline constexpr Rgba k_interactive_hover { 0xf7, 0xb9, 0x55, 1.00f }; // #F7B955
inline constexpr Rgba k_interactive_selected { 0xe8, 0x9b, 0x3c, 1.00f }; // #E89B3C
inline constexpr Rgba k_text_onAccent { 0x1a, 0x12, 0x07, 1.00f }; // #1A1207
inline constexpr Rgba k_slo_category_kick { 0xc9, 0x6f, 0x4a, 1.00f }; // #C96F4A
inline constexpr Rgba k_slo_category_snare { 0xe3, 0xc5, 0x67, 1.00f }; // #E3C567
inline constexpr Rgba k_slo_category_clap { 0xd9, 0x8b, 0xa6, 1.00f }; // #D98BA6
inline constexpr Rgba k_slo_category_hihat { 0x9f, 0xc2, 0xa5, 1.00f }; // #9FC2A5
inline constexpr Rgba k_slo_category_percussion { 0xb9, 0x8b, 0xd6, 1.00f }; // #B98BD6
inline constexpr Rgba k_slo_category_bass { 0x6e, 0x93, 0xb8, 1.00f }; // #6E93B8
inline constexpr Rgba k_slo_category_synth { 0x7f, 0xb0, 0xc4, 1.00f }; // #7FB0C4
inline constexpr Rgba k_slo_category_vocal { 0xe0, 0xa9, 0x6b, 1.00f }; // #E0A96B
inline constexpr Rgba k_slo_category_unknown { 0x4a, 0x45, 0x3d, 1.00f }; // #4A453D
inline constexpr Rgba k_kenn_severity_high { 0xe5, 0x48, 0x4d, 1.00f }; // #E5484D
inline constexpr Rgba k_kenn_severity_medium { 0xe5, 0xb8, 0x4b, 1.00f }; // #E5B84B
inline constexpr Rgba k_kenn_severity_low { 0x7f, 0xb0, 0x69, 1.00f }; // #7FB069
}  // namespace colour

namespace dimension {
inline constexpr float k_space_xs = 4.000000f;  // px
inline constexpr float k_space_s = 8.000000f;  // px
inline constexpr float k_space_m = 12.000000f;  // px
inline constexpr float k_space_l = 16.000000f;  // px
inline constexpr float k_space_xl = 24.000000f;  // px
inline constexpr float k_space_xxl = 32.000000f;  // px
inline constexpr float k_radius_s = 3.000000f;  // px
inline constexpr float k_radius_m = 6.000000f;  // px
inline constexpr float k_radius_l = 8.000000f;  // px
inline constexpr float k_stroke_hairline = 1.000000f;  // px
inline constexpr float k_stroke_icon = 1.500000f;  // px
inline constexpr float k_stroke_emphasis = 2.000000f;  // px
inline constexpr float k_stroke_heavy = 3.000000f;  // px
inline constexpr float k_comp_row_height = 27.000000f;  // px
inline constexpr float k_comp_map_point_size = 7.000000f;  // px
inline constexpr float k_comp_type_minSizePx = 10.000000f;  // px
}  // namespace dimension

namespace duration {
inline constexpr int k_motion_fast_duration = 120;  // ms
inline constexpr int k_motion_standard_duration = 180;  // ms
inline constexpr int k_motion_slow_duration = 300;  // ms
inline constexpr int k_motion_pulse_duration = 400;  // ms
inline constexpr int k_comp_tooltip_delayMs = 250;  // ms
}  // namespace duration

namespace opacity {
inline constexpr float k_opacity_dimmedFocusMode = 0.15f;
inline constexpr float k_opacity_proposalUncertain = 0.60f;
inline constexpr float k_opacity_similarityEdgeMax = 0.75f;
inline constexpr float k_opacity_softFill = 0.55f;
inline constexpr float k_opacity_vizFillMax = 0.60f;
}  // namespace opacity

namespace motion {
inline constexpr const char* k_easing = "cubic-bezier(0.25, 1, 0.5, 1)";
}  // namespace motion

}  // namespace nite::design
