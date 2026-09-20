#pragma once

#include <JuceHeader.h>

// NITE DSP product design tokens -- Smart Sample Manager.
//
// Ports the real, already-shipping website tokens (nitedsp/website/app/globals.css,
// documented in docs/NITEDSP_WEB_DESIGN_SYSTEM.md) into the JUCE plugin UI so
// both surfaces share one identity.
//
// The original scheme was: monochrome-first, green for operational state, blue
// for product/discovery context, amber only for warnings. The WARM RETUNE pass
// keeps the monochrome-first structure and the operational green, but promotes
// amber from a narrow warning accent to THE interactive accent (selection,
// focus, favourite, map selection), warms the whole neutral ramp off its cool
// blue-grey axis, and pushes the map's category hues up in saturation. Blue is
// retained as NITE DSP's brand colour but no longer carries UI state. The
// current rule is therefore: warm neutrals, amber for "what you're working
// with", green for "what is sounding", burnt orange for caution, red for
// destructive, blue for the brand mark only. Every change below is a colour
// value -- no token was renamed or removed, so all call sites are unaffected.
//
// Before this file existed, PluginEditor.cpp/SampleCanvas.cpp hardcoded a
// *different* palette left over from an earlier "KENN" build (literally
// commented `// KENN --blue` etc. at each call site) -- a real NITE DSP
// identity inconsistency between the website and the product itself. This
// file is the single source of truth going forward; call sites should read
// `Tokens::foreground` etc. instead of a bare hex string.
namespace Tokens
{
    // -- Surfaces (darkest to lightest) --
    // WARM RETUNE: the surface ramp used to sit on a cool blue-grey axis
    // (09090B/111114/...). Every step is now nudged onto a warm neutral axis
    // -- same luminance ladder, red/green fractionally above blue -- so the
    // near-black reads as "unlit room" rather than "cold screen", and the warm
    // accent below sits on it without looking like a sticker.
    inline const juce::Colour background      = juce::Colour::fromString("FF0A0E17"); // Deep Obsidian
    inline const juce::Colour surface          = juce::Colour::fromString("FF111726"); // Surface Raised
    inline const juce::Colour surfaceRaised    = juce::Colour::fromString("FF161F33");
    inline const juce::Colour surfaceRaised2   = juce::Colour::fromString("FF201D1A");
    inline const juce::Colour surfaceHover     = juce::Colour::fromString("FF26231F");
    inline const juce::Colour surfaceActive    = juce::Colour::fromString("FF302516");
    inline const juce::Colour surfaceDisabled  = juce::Colour::fromString("FF0E0D0B");
    inline const juce::Colour lcdBackground    = juce::Colour::fromString("FF05101A"); // Inset LCD Box

    // -- Electric Cyan & Emerald Hardware Tokens --
    inline const juce::Colour electricCyan     = juce::Colour::fromString("FF00F0FF"); // Website #00F0FF
    inline const juce::Colour emeraldGreen     = juce::Colour::fromString("FF10B981"); // Website #10B981
    inline const juce::Colour amberWarning     = juce::Colour::fromString("FFF59E0B"); // Website #F59E0B
    inline const juce::Colour redError         = juce::Colour::fromString("FFEF4444"); // Website #EF4444

    // -- Borders --
    inline const juce::Colour border           = juce::Colour::fromString("FF2B2723");
    inline const juce::Colour borderStrong     = juce::Colour::fromString("FF3B352F");

    // -- Text --
    inline const juce::Colour foreground       = juce::Colour::fromString("FFF5F3EF"); // primary text; warm white rather than the old cool F4F4F5
    inline const juce::Colour muted            = juce::Colour::fromString("FFABA49B"); // secondary text
    // Accessibility fix ported from the website pass (docs/NITE_DSP_UX_SYSTEM.md):
    // the old plugin value (FF71717A) computes under 4.5:1 (WCAG AA) against
    // both `background` and `surface` at normal text sizes -- same defect the
    // website had and fixed. This is the corrected tertiary tone.
    inline const juce::Colour mutedDim         = juce::Colour::fromString("FF837C74"); // warm-neutral, luminance-matched to the old FF7D7D80
    inline const juce::Colour disabled         = juce::Colour::fromString("FF645E57");

    // -- Product / brand --
    // FINDING (warm retune pass): the comment that used to sit here claimed
    // #8AB4F8 "mirrors Website V3's product blue". It does not. The website in
    // this same repo (nitedsp/website/app/globals.css) defines NO blue token at
    // all -- its `--accent` is #f4f4f5, i.e. monochrome, and its only chromatic
    // accent is `--warning-text: #e3b34d`, an amber. Nor is #8ab4f8 present
    // anywhere in the website source. The wordmark in app/layout.tsx is drawn in
    // `var(--foreground)`. So this blue was never NITE DSP's brand colour; it was
    // an unsourced plugin-only invention that the comment retroactively
    // legitimised -- most likely a survivor of the same "KENN" palette the file
    // header says this file was created to remove.
    //
    // Consequences for this pass: there is no brand-vs-accent tension to
    // resolve. Warming the interactive accent to amber moves the plugin TOWARD
    // the website's real identity (monochrome neutrals + one amber), not away
    // from it. `brandLogoColour` is therefore set to `foreground`, matching how
    // the website actually draws its wordmark. `productBlue` is kept defined,
    // unchanged, and unreferenced, so nothing breaks and the value is recoverable
    // if the owner decides he does want a blue mark after all.
    inline const juce::Colour productBlue      = juce::Colour::fromString("FF8AB4F8"); // legacy; no longer referenced by any call site
    inline const juce::Colour brandLogoColour  = foreground;
    // Legacy: the selected-state wash for tab/filter pills. Those call sites now
    // use `selection`/`accentInteractive`; kept defined (and still blue, so the
    // name stays honest) rather than renamed, since removal is not a colour change.
    inline const juce::Colour discoveryBlue    = productBlue.withAlpha(0.16f);

    // -- Warning / experimental --
    // WARM RETUNE: amber used to be the *only* warm thing in the UI, so it
    // could carry "warning" unambiguously. Now that amber is the primary
    // interactive accent (see `accentInteractive`), warning has to move or it
    // would read as "selected". It shifts to a hotter burnt-orange -- still
    // clearly the caution family, distinct from both the gold accent and the
    // pink-red `danger`.
    inline const juce::Colour warningBorder    = juce::Colour::fromString("FF7A3E1C");
    inline const juce::Colour warningBg        = juce::Colour::fromString("FF7A3E1C").withAlpha(0.14f);
    inline const juce::Colour warningText      = juce::Colour::fromString("FFDA6E38");

    // -- Functional state colours (not brand identity -- transport/status
    // affordances a monochrome pro-audio UI still needs; kept desaturated
    // rather than neon to match the "no RGB gaming look" mandate) --
    inline const juce::Colour success          = juce::Colour::fromString("FF4ADE80"); // play / confirmation
    inline const juce::Colour danger           = juce::Colour::fromString("FFEF7A7A"); // stop / needs-review / destructive

    // Tinted control surfaces for the two functional states above. These
    // existed only as ad-hoc literals at PluginEditor call sites (FF12261C /
    // FF1E3F2E / FF2C1A1C, commented "Subtle Green"/"Subtle Red") until the
    // Phase 8.5 token migration; promoted here so a button background that
    // means "transport" or "touches real data" is a named decision rather
    // than a hand-mixed hex. Derived from success/danger at low alpha over
    // `surface`, so they stay in the same restrained family.
    inline const juce::Colour successSurface       = juce::Colour::fromString("FF12261C"); // PLAY button rest
    inline const juce::Colour successSurfaceActive = juce::Colour::fromString("FF1E3F2E"); // PLAY button while playing
    inline const juce::Colour dangerSurface        = juce::Colour::fromString("FF2C1A1C"); // STOP / write-to-disk actions

    // -- Phase 8.6B accent decision (SLO_UX_V2_IMPLEMENTATION.md / SLO_UX_V2_DESIGN_SYSTEM.md
    // section 18) --
    //
    // The design pack at Audio_Engineering_Company/docs/ (SLO_UX_STRATEGY.md,
    // SLO_COMPONENT_SYSTEM.md) proposes a dedicated SLO emerald, #00F294, as
    // the product's active-state accent. This codebase already ships a
    // `success` green (#4ADE80, above) used for Play/transport state with its
    // own accessibility history. Introducing a second, different green
    // alongside it would be exactly the "rainbow UI" this phase is supposed
    // to eliminate, and would fork NITE DSP's already-restrained identity for
    // no real product benefit -- so this is option C from the brief: amber
    // stays the NITE DSP/system accent (warning, experimental, "touches
    // real external data" -- unchanged), and the *existing* success green is
    // formalized below as SLO's one interactive/active-state accent
    // (selection, favorite, playing, similarity emphasis) rather than
    // adopting a second, separate hue. `accentInteractive` is deliberately
    // an alias of `success`, not a new value -- one token, two names, so
    // call sites can express intent ("this is the SLO active accent") without
    // implying a different colour is coming.
    //
    // WARM RETUNE (supersedes the alias decision above): `accentInteractive`
    // is no longer an alias of `success`. Green now means exactly one thing --
    // transport / "this is sounding" -- and the interactive accent (selection,
    // focus, favourite emphasis, map selection) becomes a rich amber-gold.
    // Rationale: the previous arrangement had green carrying both "playing"
    // and "selected", which is the same one-accent-two-meanings problem the
    // MAP V4 note below already identified; and the app's overall read was
    // cool and desaturated. Amber against a warm near-black gives the
    // selection state real presence without introducing a fourth hue -- it is
    // the same warm family the UI already used for `favorite`, promoted from
    // a corner case to the primary. The token NAME is unchanged, so every
    // existing call site keeps working and simply becomes warm.
    inline const juce::Colour accentInteractive = juce::Colour::fromString("FFF0A23A");

    // -- Interaction-state tokens (section 17) -- previously absent; call
    // sites hand-mixed alpha-blended one-offs instead (e.g. Tokens::foreground
    // at ad-hoc alphas for focus rings). Centralized here so hover/pressed/
    // focus/selection read as one deliberate system across every control.
    inline const juce::Colour selection   = accentInteractive.withAlpha(0.18f); // row/card selected-background wash -- a touch bolder than the old 0.16 so selection carries at a glance
    inline const juce::Colour focusRing   = accentInteractive;                  // keyboard-focus outline colour
    inline const juce::Colour hoverWash   = juce::Colour::fromString("FFFFE9CC").withAlpha(0.045f); // additive hover tint -- warm white, not neutral white
    inline const juce::Colour pressedWash = juce::Colours::black.withAlpha(0.18f); // additive pressed tint over any surface
    inline const juce::Colour favorite    = juce::Colour::fromString("FFFFC94D"); // brighter, yellower gold -- must stay separable from `accentInteractive`, which now owns the amber that `favorite` used to share with warningText

    // -- Visual Map state tokens (section 58-59) -- replaces the raw-hue
    // "rainbow" category palette (10 fully-saturated hues, no secondary
    // encoding channel) with a restrained, redundantly-encoded system.
    // NOTE: category base hues themselves are not redefined here yet --
    // that requires enumerating the real category set from AbletonTaxonomy
    // and is deferred to the 8.6G Visual Map pass; these four are the
    // cross-cutting node states that apply regardless of category.
    //
    // MAP V4 -- selection and similarity on the map are drawn in the
    // product/discovery blue rather than the interactive green. This is not a
    // new hue and not a fork of the accent decision above: `productBlue` is
    // already this file's declared "blue for product/discovery context" token,
    // and picking a point on a discovery canvas *is* discovery context.
    // Operational state (something is currently sounding) keeps the green.
    // The result is a two-channel semantic that reads correctly at a glance on
    // the canvas -- blue = "the sound I'm exploring / sounds related to it",
    // green = "the sound that is playing" -- instead of one accent carrying
    // both meanings. Every `map*` token here is referenced only by
    // SampleCanvas, so this stays scoped to the map.
    //
    // WARM RETUNE: the two-channel semantic the note above describes is kept
    // exactly -- one hue for "exploring / related", another for "sounding" --
    // but the channels swap materials. Discovery/selection moves from
    // productBlue to `accentInteractive` (amber), and playback is now pinned
    // explicitly to `success` rather than riding on the accent alias, which no
    // longer resolves to green. Net effect: amber = "the sound I'm exploring
    // and its neighbours", green = "the sound that is playing" -- the same two
    // readings, with the dominant one now warm and far more visible against a
    // dark canvas than the old pale blue was.
    inline const juce::Colour mapSelected     = accentInteractive;
    inline const juce::Colour mapSelectedHalo = accentInteractive.withAlpha(0.15f);
    inline const juce::Colour mapPlaying      = success.brighter(0.3f);
    inline const juce::Colour mapSimilar      = accentInteractive.withAlpha(0.62f); // dimmer than a hard selection -- "related", not "chosen"
    inline const juce::Colour mapMuted        = mutedDim.withAlpha(0.26f);    // filtered-out/deprioritized nodes recede instead of disappearing

    // Canvas surface + reference geometry. All deliberately near-imperceptible:
    // the map's depth should be felt rather than seen.
    inline const juce::Colour mapCentreLift = juce::Colour::fromString("FF141210"); // centre of the depth field, one hair above `background`
    inline const juce::Colour mapEdgeSink   = juce::Colour::fromString("FF060504"); // outer edge of the depth field
    inline const juce::Colour mapGrid       = juce::Colour::fromString("FFE8D9C0").withAlpha(0.048f); // reference lattice; warm-white now, no axes -- UMAP has no meaningful origin
    inline const juce::Colour mapDensity    = juce::Colour::fromString("FFE0C9A6");   // cluster density field tint, warm rather than the old cool blue (alpha applied per-cell)
    inline const juce::Colour mapPointSeat  = background.withAlpha(0.82f);            // opaque-ish "seat" punched under each dot so dense clusters stay countable

    // Category colours stay a *curated* eight, luminance-matched within a
    // narrow band so no category wins attention purely by being brighter --
    // and so the unknown-category fallback picks from this set instead of
    // generating a raw hue. That discipline is the point and is preserved.
    //
    // WARM RETUNE: saturation is pushed up roughly a third from the previous
    // pass, and the set's centre of gravity moved warm (the neutral was a cool
    // blue-grey slate; it is now a warm taupe). This is a deliberate step
    // *toward* punch and away from the washed-out read, but explicitly not a
    // return to the pre-V4 fully-saturated rainbow -- luminance is still
    // banded, and nothing here is a pure primary.
    inline const juce::Colour mapCategoryCool   = juce::Colour::fromString("FF5FA6F0"); // one cool anchor kept, for contrast against the warm majority
    inline const juce::Colour mapCategoryWarm   = juce::Colour::fromString("FFEE8A50");
    inline const juce::Colour mapCategoryGold   = juce::Colour::fromString("FFEBC24A");
    inline const juce::Colour mapCategoryRose   = juce::Colour::fromString("FFEE7C9C");
    inline const juce::Colour mapCategoryViolet = juce::Colour::fromString("FFAE85E8");
    inline const juce::Colour mapCategoryGreen  = juce::Colour::fromString("FF63C48C");
    inline const juce::Colour mapCategoryTeal   = juce::Colour::fromString("FF4FBDB6");
    inline const juce::Colour mapCategorySlate  = juce::Colour::fromString("FFA79B94"); // warm taupe neutral (was cool FF9AA3B8)

    // -- Map geometry / motion --
    constexpr float mapPointRadiusMin = 1.7f;  // far zoom: still a distinct object, never a smear
    constexpr float mapPointRadiusMax = 6.4f;  // close zoom: never an orb
    constexpr float mapPointRadiusRef = 2.6f;  // radius at zoomScale == 1
    constexpr float mapMotionTauMs    = 46.0f; // exponential time constant -> ~150ms perceived settle

    // -- Control geometry --
    constexpr float cornerRadius   = 4.0f;
    constexpr float cornerRadiusSm = 2.0f;
    constexpr float cornerRadiusLg = 6.0f;
    constexpr int controlHeight    = 24;
    constexpr int controlHeightLg  = 26;
    constexpr int controlHeightCompact = 20;

    // -- Spacing scale (section 20) -- 4px-derived, centralizes what were
    // previously arbitrary literals (5, 6, 8, 10, 15...) scattered across
    // PluginEditor::resized(). Existing call sites are not required to
    // migrate in one pass; new/touched layout code should prefer these.
    constexpr int space1 = 4;
    constexpr int space2 = 8;
    constexpr int space3 = 12;
    constexpr int space4 = 16;
    constexpr int space5 = 20;
    constexpr int space6 = 24;

    // -- Type scale (px) --
    constexpr float fontLabel   = 10.0f; // field labels, all-caps/mixed micro-copy
    constexpr float fontBody    = 12.0f; // values, control text
    constexpr float fontHeading = 14.0f; // panel/section titles
    constexpr float fontTitle   = 16.0f; // app title
}
