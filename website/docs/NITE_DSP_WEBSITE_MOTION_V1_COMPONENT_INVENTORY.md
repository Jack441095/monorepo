# NITE DSP WEBSITE MOTION V1 — COMPONENT INVENTORY

Identical registry to `docs/NITE_DSP_NEXTGEN_INTERACTION_V1_MOTION_INVENTORY.md`
(one programme, one inventory — 20 registered behaviours, 6 rejected
experiments). Machine-readable:
`docs/website_motion_v1_components.json` (mirror of
`docs/nextgen_interaction_components.json`).

New files:

    lib/motion.ts                              (shared pointer engine + gates)
    components/motion/LightField.tsx           (DEPTH 1 ambient field)
    components/motion/Magnetic.tsx             (DEPTH 3 magnetic content)
    components/motion/TiltSurface.tsx          (DEPTH 2 micro-3D frame)
    components/motion/Reveal.tsx               (one-shot scroll reveal)
    components/motion/WorkflowFlow.tsx         (signal-flow storytelling)
    components/motion/StatusDot.tsx            (status energy system)
    scripts/capture-visual-review.mjs          (static review captures)
    scripts/capture-motion-review.mjs          (local motion recordings)
    scripts/capture-utility-check.mjs          (utility-route spot checks)
    tests/motion.spec.ts                       (6 regression contracts)

Modified files:

    app/globals.css        (interaction layer CSS + @theme token fix)
    app/layout.tsx         (js-class script, grain body class, suppressHydrationWarning)
    app/page.tsx           (homepage integration)
    app/products/page.tsx  (flagship tilt card, status dots, depth hover)
    app/products/smart-sample-manager/page.tsx (SLO integration)
    components/SiteHeader.tsx  (morphing nav indicator, aria-current)
    components/AudioAnalysisDemo.tsx (premium interaction pass)

Untouched: backend, SLO/Submit/KENN sources, pricing/support/learn/account/
legal pages, all copy, all tests except the added file.
