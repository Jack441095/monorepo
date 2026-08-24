# NITE DSP WEBSITE MOTION V1 — ACCESSIBILITY

Full receipt: `docs/NITE_DSP_NEXTGEN_INTERACTION_V1_ACCESSIBILITY.md`
(same programme). Summary against the V2.1 motion-pass checklist:

- REDUCED MOTION: cursor-following translation, ambient tracking, parallax,
  magnetism, continuous scanning, scroll-linked movement and grain
  animation all disabled or neutralised; hover/focus clarity and content
  preserved; reduced-motion mode remains visually premium (static light
  composition, full trace, instant states). Automated test included.
- KEYBOARD: no behaviour triggered by focus that displaces content;
  indicator state mirrored by `aria-current`; demo fully keyboard-operable.
- FOCUS-VISIBLE: global 2px brand outline preserved; decorative layers are
  `pointer-events:none` and never obscure focus rings.
- HOVER-ONLY FUNCTIONALITY: **NONE** — all hover effects decorative.
- STABLE CONTROLS: magnetic targets keep stationary hit areas (automated
  click-while-engaged test).
- CONTRAST DURING GLOW: fields/bloom sit behind content; verified at
  1440/768/390; text colours unchanged.
- ANIMATION-DEPENDENT MEANING: none (dots accompany text labels; scanner
  accompanied by text states).
- FLASHING: none (single 220 ms ring per explicit action; well within
  WCAG 2.3.1).
- KNOWN LIMITATION: demo scan animation runs while scanning (functional
  feedback for an explicit action); decorative layers around it suppress.
