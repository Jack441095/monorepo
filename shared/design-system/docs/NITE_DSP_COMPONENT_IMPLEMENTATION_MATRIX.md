# NITE DSP — Component Implementation Matrix

**Source:** DESIGN_SYSTEM_V1 §14 (frozen component architecture). This matrix classifies each component for later migration planning (DS-I10/11/12). No production code touched in this phase.

Legend — Scope: G=global/shared · S=SLO · K=KENN · W=web · JUCE candidate: LF=LookAndFeel helper, C=custom Component, P=platform/web-native.

| Component | Scope | JUCE candidate | State variants | Localisation impact | Accessibility impact | Migration priority |
|---|---|---|---|---|---|---|
| Window | G | LF (background) + product min-sizes | resize, breakpoints | title only | platform-managed | P1 (foundation) |
| Surface | G | LF colour roles | base/raised/overlay/inset/modal | none | contrast pairs | P1 |
| Toolbar | G | LF + layout helper | default/compact | button labels | keyboard order | P2 |
| Tabs (segmented) | G | LF | active/inactive/focus | labels expand +35% | role=tab, arrow nav | P2 |
| Button | G | LF | primary/ghost/danger; hover/active/focus/disabled | labels; +50% → icon+text (KENN rule) | focus ring interactive.bright | P1 |
| IconButton | G | LF | hover/focus/disabled + tooltip | tooltip carries meaning | accessible name mandatory | P2 |
| Toggle | G | LF | on/off/disabled | label | role=toggle, state announced | P2 |
| SegmentedControl | G | LF | selected/hover | segment labels | role=radio group | P2 |
| SearchField | G | C | focus/typing/cleared | placeholder | ⌘K/⌘F shortcut | P2 |
| FilterChip | S | C | active/inactive | filter names | toggle state | P3 |
| CategoryChip | S | C | dot+label (mandatory) | category display names | text label always present | P3 |
| Table | S | C | sort asc/desc; row states | column headers | tabular numerals ON | P3 |
| TableRow | S | C | compact/comfortable; playing/selected/favorite | none (content) | row role, playing ▶ glyph | P3 |
| Scrollbar | G | LF | overlay thumb | none | keyboard scroll | P4 |
| Inspector | S,K | C | right sheet / bottom-sheet | kv labels flexible width | focus containment | P3 |
| Tooltip | G | C | delay 250ms, persists | full text | announced | P2 |
| Popover | G | C | open/close | content | focus trap | P3 |
| Modal | G | C | one copper action max | grows max-width first | focus trap, ESC | P3 |
| Waveform | S,K | C | peaks+RMS+playhead+loop | none (never localised) | **never mirrors under RTL** | P4 |
| Meter | K | C | segmented past threshold, peak-hold | none | mono readouts | P4 |
| Spectrum | K | C | neutral graph | axis labels | **frequency axis never mirrors** | P4 |
| MapPoint | S | C | resting/selected/playing/favorite/OOD/hover | label card | **R-CVD-1 shape coding default-on** | P3 |
| MapCluster | S | C | aggregate/expand 200ms | count labels | count text | P3 |
| Badge | K | C | severity/confidence | text chip mandatory | text+colour (C-05) | P3 |
| Status | G | C | glyph+text | state strings | glyph redundant | P2 |
| AIProposal | K | C | provisional→accepted (dashed→solid 200ms); uncertain 60%+? | "provisional" tag | geometry-led grammar | P3 |
| ConfidenceIndicator | K | C | chip default / bar / exact % | qualitative strings | text default mode | P3 |
| EmptyState | G | C | designed, actionable | message + action | announced | P4 |
| LoadingState | G | C | regional shimmer only | none | reduced-motion → opacity | P4 |

## Cross-cutting notes

- **Accent budget** applies per context (DS §4): LIST 5–8%, MAP 3–5%, KENN 3–6%, modals ≤10%, web ≤12%.
- **Category colours** (SLO chips, MapPoint) are classification-only; never interaction/status.
- **Text expansion** hotspots: Button, Tabs, CategoryChip, Toolbar, Inspector labels, dialogs — auto-size/min-width policies per LOCALISATION §8.
