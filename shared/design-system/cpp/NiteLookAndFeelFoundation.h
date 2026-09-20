// NITE DSP Design System 1.0 — Shared LookAndFeel foundation (DS-I03).
//
// Architecture only: composable helpers, NOT a God-LookAndFeel. Products
// subclass NiteLookAndFeel and override their alias layer; global identity
// (surfaces, copper, typography, states) is inherited and may not be forked.
//
// This header is JUCE-optional: it compiles against a thin juce:: forward
// surface so the design-system repo can be validated without the full JUCE
// build. In product integration, include the real juce headers first.

#pragma once

#include "NiteDesignAdapter.h"

#if NITE_DESIGN_JUCE_AVAILABLE
 #include <juce_gui_basics/juce_gui_basics.h>
#endif

namespace nite::design {

//==============================================================================
// Semantic component state model (DS-I06). Fifteen frozen states; every state
// carries mandatory redundant encoding so no visual state depends on hue alone.

enum class ComponentState {
    Resting, Hovered, Focused, Selected,
    Playing, Favorite, Disabled,
    Warning, Error, Unknown,
    AiProposal, AiAccepted,
    HardwareCyan, HardwareEmerald,
};

struct StateVisual {
    Rgba   fill;
    Rgba   stroke;
    float  strokeWidth;
    bool   dashed;
    const char* glyph;      // redundant encoding channel (never null for semantic states)
    float  opacity;
};

inline StateVisual resolveState(ComponentState state) noexcept
{
    using namespace colour;
    switch (state) {
        case ComponentState::Resting:
            return { k_color_surface_overlay, k_color_border_hairline_subtle,
                     dimension::k_stroke_hairline, false, "", 1.00f };
        case ComponentState::Hovered:
            return { k_color_surface_hover, k_color_border_hairline_strong,
                     dimension::k_stroke_hairline, false, "", 1.00f };
        case ComponentState::Focused:
            return { k_color_surface_overlay, k_color_interactive_bright,
                     dimension::k_stroke_emphasis, false, "", 1.00f };   // focus ring = interactive.bright
        case ComponentState::Selected:
            return { k_color_interactive_dim, k_color_interactive_base,
                     dimension::k_stroke_emphasis, false, "", 1.00f };   // copper edge + dim fill
        case ComponentState::Playing:
            return { k_color_surface_overlay, k_color_semantic_playing,
                     dimension::k_stroke_emphasis, false, "\u25B6", 1.00f }; // ▶ glyph mandatory
        case ComponentState::Favorite:
            return { k_color_surface_overlay, k_color_semantic_favorite,
                     dimension::k_stroke_hairline, false, "\u2605", 1.00f }; // ★ glyph mandatory
        case ComponentState::Disabled:
            return { k_color_surface_overlay, k_color_text_disabled,
                     dimension::k_stroke_hairline, false, "", 0.40f };   // reduced opacity + inert
        case ComponentState::Warning:
            return { k_color_surface_overlay, k_color_semantic_warning,
                     dimension::k_stroke_emphasis, false, "\u26A0", 1.00f }; // ▲ + text chip mandatory
        case ComponentState::Error:
            return { k_color_surface_overlay, k_color_semantic_error,
                     dimension::k_stroke_emphasis, false, "\u2715", 1.00f }; // ✕ glyph mandatory
        case ComponentState::Unknown:
            return { Rgba{0x08, 0x07, 0x06, 1.0f}, k_color_semantic_unknown,
                     dimension::k_stroke_hairline, true, "?", 1.00f };   // hollow + dashed outline
        case ComponentState::AiProposal:
            return { Rgba{0x08, 0x07, 0x06, 1.0f}, k_color_interactive_base,
                     dimension::k_stroke_emphasis, true, "provisional", 1.00f }; // dashed copper
        case ComponentState::AiAccepted:
            return { Rgba{0x08, 0x07, 0x06, 1.0f}, k_color_text_primary,
                     dimension::k_stroke_emphasis, false, "", 1.00f };   // solid authoritative, no special hue
    }
    return { k_color_surface_overlay, k_color_border_hairline_subtle,
             dimension::k_stroke_hairline, false, "", 1.00f };
}

/** MACHINE PROPOSAL = PROVISIONAL · USER DECISION = AUTHORITATIVE (DS §13). */
inline bool isProvisional(ComponentState state) noexcept
{
    return state == ComponentState::AiProposal;
}

//==============================================================================
// Accessibility helpers (task §14) — metadata + validation, not platform claims.

struct ContrastPair {
    Rgba foreground;
    Rgba background;
};

/** WCAG 2.x relative-luminance contrast ratio between two EMBER colours. */
inline double contrastRatio(const Rgba& fg, const Rgba& bg) noexcept
{
    auto channel = [](std::uint8_t c) -> double {
        double s = c / 255.0;
        return s <= 0.03928 ? s / 12.92 : std::pow((s + 0.055) / 1.055, 2.4);
    };
    auto luminance = [&](const Rgba& c) {
        return 0.2126 * channel(c.r) + 0.7152 * channel(c.g) + 0.0722 * channel(c.b);
    };
    double l1 = luminance(fg), l2 = luminance(bg);
    double lighter = l1 > l2 ? l1 : l2;
    double darker  = l1 > l2 ? l2 : l1;
    return (lighter + 0.05) / (darker + 0.05);
}

/**
 * The tertiary text floor (DS §3.2) — corrected in 1.0.1.
 *
 * The frozen 1.0.0 spec stated #6E675E was "≥4.6:1" on base, but its measured
 * WCAG 2.x contrast on #0C0B09 was 3.53:1 — a spec contradiction recorded here
 * pending owner clarification. Resolved in 1.0.1: tertiary is now #827B71
 * (measured 4.70:1), a pure-lightness lift within the same warm-grey family.
 * See docs/CHANGELOG.md for the full decision record.
 */
inline bool tertiaryTextFloorHolds() noexcept
{
    using namespace colour;
    // Validates against the WCAG AA body-text threshold the token now meets,
    // so any future regression below 4.5:1 fails loudly.
    return contrastRatio(k_color_text_tertiary, k_color_surface_base) >= 4.5;
}

/** Every semantic state must carry at least one non-colour encoding channel. */
inline bool stateHasRedundantEncoding(ComponentState state) noexcept
{
    auto v = resolveState(state);
    if (v.dashed) return true;                       // geometry channel
    if (v.glyph != nullptr && v.glyph[0] != '\0') return true;  // glyph/label channel
    if (state == ComponentState::Selected) return true;         // stroke-width change
    if (state == ComponentState::Disabled) return true;         // opacity + cursor affordance
    return false;
}

}  // namespace nite::design
