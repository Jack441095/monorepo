# Thursday Desktop Architecture V1 (DESIGN — macOS first)

## Process model
Thursday Desktop (SwiftUI app) ⇄ **NITE Runtime** (Unix socket, existing
protocol) ⇄ capabilities/providers/company store. Desktop holds no business
logic; it renders contracts.

## Windows / views
Today's Brief (DailyBriefData) · Goals · Projects · Tasks · Agents ·
Approvals (pending queue + decide) · Risks · Evidence inspector · Settings
(store path, socket path, voice) · Conversation.

## Conversation layer
Thursday-owned: model runtime turns structured payloads into calm,
evidence-led prose. Grounding rules from THURSDAY_COMPANY_CAPABILITIES.md
apply verbatim; missing sources are stated explicitly ("Calendar: not connected").

## Design system & localisation
Consume NITE DSP Design System 1.0 / EMBER tokens as an external dependency —
never forked. AI-generated text flows through the frozen localisation
architecture (machine results carry stable IDs; locale rendering at the edge).

## Voice
Reuse Thursday's existing STT/TTS workers (push-to-talk first; wake-word and
barge-in later). Voice is an input modality to the same capability routing —
not a separate stack.

## Notifications
Runtime events (approvals pending, task overdue, agent failure) → desktop
notification centre via the same socket protocol.
