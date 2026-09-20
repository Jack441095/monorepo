// NITE DSP Design System 1.0 — JUCE-facing token adapter (DS-I02).
//
// Architecture notes:
//  - Semantic accessors over generated constexpr data (NiteDesignTokens.h).
//    No string lookup in hot paths; no allocation; HiDPI-safe numeric tokens.
//  - ColourId registry with documented per-family numeric ranges to avoid
//    collisions across products (DESIGN_SYSTEM_V1 §16).
//  - Product aliases resolve through this layer only. Products never hardcode hex.
//
// This file is hand-written architecture (not generated); it consumes the
// generated header and must remain in sync with the token schema.

#pragma once

#include "NiteDesignTokens.h"

#include <atomic>

namespace nite::design {

//==============================================================================
// Semantic colour roles — the ONLY sanctioned way for product UI to obtain colour.

enum class ColourRole {
    // Surfaces
    SurfaceBase, SurfaceRaised, SurfaceOverlay, SurfaceInset, SurfaceHover, SurfaceModal,
    // Borders
    HairlineSubtle, HairlineStrong,
    // Text
    TextPrimary, TextSecondary, TextTertiary, TextDisabled, TextInverse,
    // Interaction (copper)
    InteractiveBase, InteractiveBright, InteractiveDim, InteractiveInk,
    // States
    Playing, Success, Warning, Error, Destructive, Favorite, Unknown, Disabled,
};

inline Rgba resolve(ColourRole role) noexcept
{
    using namespace colour;
    switch (role) {
        case ColourRole::SurfaceBase:       return k_color_surface_base;
        case ColourRole::SurfaceRaised:     return k_color_surface_raised;
        case ColourRole::SurfaceOverlay:    return k_color_surface_overlay;
        case ColourRole::SurfaceInset:      return k_color_surface_inset;
        case ColourRole::SurfaceHover:      return k_color_surface_hover;
        case ColourRole::SurfaceModal:      return k_color_elevation_modal;
        case ColourRole::HairlineSubtle:    return k_color_border_hairline_subtle;
        case ColourRole::HairlineStrong:    return k_color_border_hairline_strong;
        case ColourRole::TextPrimary:       return k_color_text_primary;
        case ColourRole::TextSecondary:     return k_color_text_secondary;
        case ColourRole::TextTertiary:      return k_color_text_tertiary;
        case ColourRole::TextDisabled:      return k_color_text_disabled;
        case ColourRole::TextInverse:       return k_color_text_inverse;
        case ColourRole::InteractiveBase:   return k_color_interactive_base;
        case ColourRole::InteractiveBright: return k_color_interactive_bright;
        case ColourRole::InteractiveDim:    return k_color_interactive_dim;
        case ColourRole::InteractiveInk:    return k_color_interactive_ink;
        case ColourRole::Playing:           return k_color_semantic_playing;
        case ColourRole::Success:           return k_color_semantic_success;
        case ColourRole::Warning:           return k_color_semantic_warning;
        case ColourRole::Error:             return k_color_semantic_error;
        case ColourRole::Destructive:       return k_color_semantic_destructive;
        case ColourRole::Favorite:          return k_color_semantic_favorite;
        case ColourRole::Unknown:           return k_color_semantic_unknown;
        case ColourRole::Disabled:          return k_color_semantic_disabled;
    }
    return k_color_text_primary;
}

//==============================================================================
// SLO category palette (classification ONLY — never interaction/status, DS §6).

enum class SloCategory { Kick, Snare, Clap, Hihat, Percussion, Bass, Synth, Vocal, Unknown };

inline Rgba categoryColour(SloCategory cat) noexcept
{
    using namespace colour;
    switch (cat) {
        case SloCategory::Kick:       return k_slo_category_kick;
        case SloCategory::Snare:      return k_slo_category_snare;
        case SloCategory::Clap:       return k_slo_category_clap;
        case SloCategory::Hihat:      return k_slo_category_hihat;
        case SloCategory::Percussion: return k_slo_category_percussion;
        case SloCategory::Bass:       return k_slo_category_bass;
        case SloCategory::Synth:      return k_slo_category_synth;
        case SloCategory::Vocal:      return k_slo_category_vocal;
        case SloCategory::Unknown:    return k_slo_category_unknown;
    }
    return k_slo_category_unknown;
}

//==============================================================================
// Typography tokens (DS §7). Sizes are design-px; scale at draw time for HiDPI.

enum class TypeRole { Display, Heading, Section, Body, Control, Metadata, Caption, Numerical };

struct TypeSpec {
    float sizePx;
    float lineHeightPx;
    int   weight;            // 400 regular / 500 medium / 600 semibold
    bool  uppercase;
    float trackingPct;       // +6% for captions
    bool  monospace;
    bool  tabularNumerals;
};

inline TypeSpec typeSpec(TypeRole role) noexcept
{
    switch (role) {
        case TypeRole::Display:   return { 24.0f, 30.0f, 600, false, 0.0f, false, false };
        case TypeRole::Heading:   return { 17.0f, 24.0f, 600, false, 0.0f, false, false };
        case TypeRole::Section:   return { 13.0f, 18.0f, 500, false, 0.0f, false, false };
        case TypeRole::Body:      return { 12.5f, 17.0f, 400, false, 0.0f, false, false };
        case TypeRole::Control:   return { 11.0f, 15.0f, 500, false, 0.0f, false, false };
        case TypeRole::Metadata:  return { 11.0f, 15.0f, 400, false, 0.0f, false, true };
        case TypeRole::Caption:   return { 10.0f, 13.0f, 600, true, 6.0f, false, false };
        case TypeRole::Numerical: return { 11.0f, 15.0f, 500, false, 0.0f, true, true };
    }
    return { 12.5f, 17.0f, 400, false, 0.0f, false, false };
}

//==============================================================================
// Motion tokens (DS §12).

struct MotionSpec { int durationMs; };

inline MotionSpec motionFast()     noexcept { return { duration::k_motion_fast_duration }; }
inline MotionSpec motionStandard() noexcept { return { duration::k_motion_standard_duration }; }
inline MotionSpec motionSlow()     noexcept { return { duration::k_motion_slow_duration }; }
inline MotionSpec motionPulse()    noexcept { return { duration::k_motion_pulse_duration }; }

/** Reduced-motion policy: transforms become instant; opacity transitions remain. */
class ReducedMotionPreference {
public:
    static ReducedMotionPreference& instance() noexcept
    {
        static ReducedMotionPreference pref;
        return pref;
    }
    void setEnabled(bool enabled) noexcept { flag.store(enabled, std::memory_order_relaxed); }
    bool enabled() const noexcept { return flag.load(std::memory_order_relaxed); }
    /** Effective duration: 0 when reduced motion is on (transform-class animation). */
    int effectiveDurationMs(MotionSpec spec) const noexcept
    {
        return enabled() ? 0 : spec.durationMs;
    }
private:
    std::atomic<bool> flag { false };
};

//==============================================================================
// ColourId registry — documented numeric ranges prevent cross-product collisions.
//
//   0x0001'0000–0x0001'FFFF   shared NiteLookAndFeel base family
//   0x0002'0000–0x0002'FFFF   SLO product components
//   0x0003'0000–0x0003'FFFF   KENN product components
//   0x0004'0000–0x0004'FFFF   reserved (future synth)
//
// Products allocate within their own band only.

namespace colourIds {
    constexpr int baseFirst   = 0x00010000;
    constexpr int sloFirst    = 0x00020000;
    constexpr int kennFirst   = 0x00030000;

    // Shared base family
    constexpr int niteWindowBackground = baseFirst + 0x01;
    constexpr int niteToolbar          = baseFirst + 0x02;
    constexpr int niteTabBackground    = baseFirst + 0x03;
    constexpr int niteTabActive        = baseFirst + 0x04;
    constexpr int niteButtonPrimary    = baseFirst + 0x05;
    constexpr int niteButtonGhost      = baseFirst + 0x06;
    constexpr int niteButtonDanger     = baseFirst + 0x07;
    constexpr int niteInspectorSheet   = baseFirst + 0x08;
    constexpr int niteTooltip          = baseFirst + 0x09;
    constexpr int nitePopover          = baseFirst + 0x0A;
    constexpr int niteModal            = baseFirst + 0x0B;
    constexpr int niteScrollbarThumb   = baseFirst + 0x0C;
    constexpr int niteTextField        = baseFirst + 0x0D;
    constexpr int niteComboBox         = baseFirst + 0x0E;
    constexpr int niteToggle           = baseFirst + 0x0F;
}  // namespace colourIds

//==============================================================================
// MAP shape grammar (R-CVD-1) — geometry constants, frozen.
// Family shape coding is DEFAULT-ON at ALL zoom levels; identification never
// depends on hue alone (EMBER_CVD_VALIDATION_REPORT.md).

enum class MapFamilyShape { Circle, Square, Triangle, HollowCircle, DashedHollow };

struct MapFamily { enum Value { Drums, Bass, Synth, Vocal }; };

inline MapFamilyShape familyShape(MapFamily::Value family) noexcept
{
    switch (family) {
        case MapFamily::Drums: return MapFamilyShape::Circle;
        case MapFamily::Bass:  return MapFamilyShape::Square;
        case MapFamily::Synth: return MapFamilyShape::Triangle;
        case MapFamily::Vocal: return MapFamilyShape::HollowCircle;
    }
    return MapFamilyShape::DashedHollow;
}

inline MapFamilyShape categoryShape(SloCategory cat) noexcept
{
    switch (cat) {
        case SloCategory::Kick:
        case SloCategory::Snare:
        case SloCategory::Clap:
        case SloCategory::Hihat:
        case SloCategory::Percussion:
            return familyShape(MapFamily::Drums);
        case SloCategory::Bass:   return familyShape(MapFamily::Bass);
        case SloCategory::Synth:  return familyShape(MapFamily::Synth);
        case SloCategory::Vocal:  return familyShape(MapFamily::Vocal);
        case SloCategory::Unknown: return MapFamilyShape::DashedHollow;
    }
    return MapFamilyShape::DashedHollow;
}

//==============================================================================
// Icon system metadata (DS-I05) — semantic IDs; SVG assets resolved by loader.
// Language: 1.5px stroke geometric, rounded caps, 16/20 grid.

namespace iconIds {
    constexpr const char* Play         = "action.play";
    constexpr const char* Stop         = "action.stop";
    constexpr const char* Favorite     = "state.favorite";
    constexpr const char* Search       = "action.search";
    constexpr const char* Filter       = "action.filter";
    constexpr const char* History      = "view.history";
    constexpr const char* Map          = "view.map";
    constexpr const char* List         = "view.list";
    constexpr const char* Split        = "view.split";
    constexpr const char* FindSimilar  = "action.find_similar";
    constexpr const char* Settings     = "action.settings";
    constexpr const char* Analysis     = "mode.analysis";
    constexpr const char* Recommendation = "ai.proposal";
    constexpr const char* Warning      = "state.warning";
}  // namespace iconIds

}  // namespace nite::design
