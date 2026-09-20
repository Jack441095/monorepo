# NITE Submit native UI alignment v1

Validation date: 25 August 2026

The AppKit interface now uses a native translation of the website's Palette B
design language:

| Website token | Native app use |
| --- | --- |
| `#070A12` background | Main document surface and window content |
| `#0D1322` surface | PDF drop zone and editable metadata fields |
| `#121B2D` raised surface | Pop-up controls and secondary actions |
| `#397BFF` / `#56A8FF` | Primary action, focus, and active drop-zone border |
| `#7148E8` | Reserved for future processing state; not used decoratively |
| semantic green/amber/red | Found, review, and blocking/error states |

The app intentionally keeps native AppKit controls, keyboard behavior, the
system title bar, and reduced-motion-friendly behavior. Website pointer motion,
magnetic controls, and decorative loops are not copied into the document tool.

## Verification

- Builds against the product minimum of macOS 13.
- Packaged app opens the real Berklee PDF directly.
- Detected name, student number, university, title, review gate, and identity
  selector remain visible and functional in the dark theme.
- Drop-zone focus is communicated through both color and border weight.
- The visual pass changes presentation only; extraction, naming, approval, and
  file-operation behavior remain covered by the existing release suite.
