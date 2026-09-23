# KENN Investor Demo FAQ

Status: operator draft; product-owner review required before an investor demo.

Use these answers for audience discussion after the scripted walkthrough. Keep
live typing on the rehearsed demo path. Claims below distinguish shipped,
qualified behavior from roadmap work.

1. **What is KENN?**

   KENN is a local-first studio assistant that reads an Ableton Live session,
   answers grounded questions, presents evidence-labelled mix advice, and can
   prepare tightly scoped DAW changes for producer confirmation.

2. **Why does KENN use OSC instead of MCP to control Ableton?**

   Ableton Live does not natively expose MCP. AbletonOSC is the transport that
   reaches Live today. MCP is complementary: KENN can expose its safe tools to
   an AI client through MCP, but the final control path remains
   `MCP/client -> KENN policy and receipts -> OSC -> Live`. OSC is the wire;
   KENN supplies identity checks, confirmation, readback, receipts, and undo.

3. **What is actually shipped in this demo?**

   Fresh session Q&A, exact track and qualified device proposals, explicit
   confirmation, Live readback, receipt history, exact bounded undo, measured
   WAV analysis, arrangement fallback advice, and a polished local web UI are
   implemented. The runbook identifies every remaining qualification gate.

4. **Is this just a chatbot sending MIDI or keystrokes?**

   No. KENN resolves typed track/device/parameter identities from a fresh Live
   snapshot and uses a dedicated OSC control surface. It does not rely on
   screen coordinates or blindly replay UI automation for DAW mutations.

5. **Why keep a deterministic parser if you have an LLM?**

   The deterministic path gives the safety system a stable, testable baseline.
   The model must emit the same typed contract and pass identity, range, and
   policy validation; fluent language never grants extra execution authority.

6. **Is the LLM controlling Live during this demo?**

   No. The production promotion state remains evidence-gated. Shadow mode is
   observational, propose mode can only create a normal confirmation-bound
   proposal after validation, and active promotion requires reviewed volume,
   acceptance, and zero-safety-violation thresholds.

7. **Can KENN change the wrong track when names are duplicated?**

   It refuses ambiguous identity. Proposals bind the exact track index and
   observed name, and execution checks that identity again before writing.
   Duplicate-name questions are also available directly from the session.

8. **What prevents accidental or automatic changes?**

   A proposal has a short-lived token bound to its exact action and observed
   state. The user must explicitly confirm that proposal. A token for one
   action cannot authorize another, and a stale or replayed proposal is
   rejected.

9. **How do you handle UDP or OSC acknowledgement loss?**

   KENN treats an uncertain acknowledgement as ambiguous rather than retrying a
   write blindly. It performs authoritative readback, reconciles the observed
   state, records the outcome, and classifies whether a retry is safe.

10. **Is undo just Ableton's global Cmd-Z?**

    No. KENN records the exact before value and target identity in a receipt,
    creates a new confirmation-bound inverse, applies it, and independently
    reads Live again. It uses native undo only where explicitly qualified; the
    demo safety story is receipt-backed restoration.

11. **Can KENN delete tracks or overwrite the set?**

    Destructive content operations are outside the assistant boundary and are
    refused in plain English. Structural features are enabled only when a
    narrow operation and its verification/rollback contract have been
    qualified.

12. **Does KENN really listen to the mix?**

    The demo analyzes exact manifest-bound WAV captures with KENN's production
    analyzer. Responses carry the source SHA-256, measured findings,
    confidence, severity, and a listening test. KENN does not claim continuous
    real-time hearing when no current capture is available.

13. **Does a finding automatically change the mix?**

    Never. Analysis is advisory-only. If the producer chooses a change, that
    request re-enters the normal proposal, confirmation, execution, readback,
    receipt, and undo path.

14. **How do you avoid generic “AI mixing” claims?**

    Findings cite bounded measurements and uncertainty. For example, spectral
    overlap is presented as a masking candidate to audition, not proof that an
    EQ cut is correct. The UI shows confidence and a suggested listening test.

15. **How many Ableton devices are supported?**

    The current evidence-backed display-unit registry has 11 exact parameter
    profiles. KENN can inspect more raw parameters, but it does not pretend a
    raw knob value equals a user-facing unit without qualification. Expanding
    to 20+ profiles is an active real-Live evidence sprint, not a demo claim.

16. **How do you qualify a new parameter?**

    A disposable Live set is probed through the same companion boundary. Each
    point uses a confirmation-bound write, readback, replay rejection, and
    exact inverse restoration. Multi-point sweeps emit raw/display pairs for
    human review and never auto-promote a mapping.

17. **What data leaves the studio?**

    The demonstrated command and analysis path is local-first. KENN can run
    deterministic planning and local retrieval without sending the Live set or
    demo audio to a hosted model. Any future external integration must have an
    explicit product and privacy boundary.

18. **How is model training kept from weakening safety?**

    Training and holdout data produce typed plans, not direct DAW writes.
    Synthetic records are labelled as synthetic, natural holdouts are kept
    distinct, shadow comparisons are reviewed, and runtime validators remain
    authoritative regardless of model quality.

19. **What about MIDI generation or AudioGen?**

    Those are roadmap features for a preview-approve-insert workflow. They are
    not presented as shipped in this demo. Generated material will need the
    same explicit target, confirmation, verification, receipt, and undo story.

20. **What evidence says the demo is reliable?**

    The backend currently passes 1,393 tests, and the 13 automatable scripted
    prompt contracts passed 10 consecutive real-companion runs under the
    650 ms response budget. That is supporting evidence, not the final claim:
    the complete UI/audio/mutation demo still needs 10 consecutive 20-step
    rehearsals, cold-boot preflight, recovery timing, reset verification, and
    projector review on the disposable session.

## Operator boundary

If a question would require a new Live mutation, do not improvise it during an
investor showing. Explain the boundary, answer verbally, and offer a supervised
follow-up qualification after the demo.
