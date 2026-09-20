# SLO Beta Blocker Register V1

| ID | Severity | Blocker | Owner / exit evidence |
|---|---|---|---|
| B-001 | P0 | Developer ID signing, notarization, installer/update flow absent | Apple release owner; signed clean install |
| B-002 | P0 | Clean-machine validation incomplete | QA; fresh Mac install/launch/uninstall |
| B-003 | P0 | Production licensing endpoint/credentials absent; default is dev localhost HTTP | Backend/commercial owner; HTTPS activation/renewal tests |
| B-012 | P0 | Clean aggregate and fast qualification fail for helper-based engine tests with 13,044 duplicate JUCE symbols | Build owner; correct shared engine-core/JUCE linkage and rerun `ssm_qual_full` |
| B-004 | P1 | Ableton Live VST3 host matrix not qualified | Host QA; scan/load/render/state/drag/reopen receipt |
| B-005 | P1 | Blind AL-002 review incomplete | Evaluation owner; sealed completion receipt |
| B-006 | P1 | Cross-vendor and leakage-controlled accuracy not established | ML owner; stratified report with separate audio/fused metrics |
| B-007 | P1 | OOD false-known remains high in thin historical evidence | ML owner; cross-vendor OOD gate and visible Unknown behavior |
| B-008 | P1 | Vocal Loop failure in V4-H evidence | ML/product owner; remediate or explicitly suppress claim |
| B-009 | P1 | Peak RSS and long-soak/large-scale gates incomplete | Performance owner; 100/1k/10k and soak receipt |
| B-010 | P2 | RT timing/allocation instrumentation incomplete | Audio QA; deadline stress receipt |
| B-011 | P2 | Sort Library is move-based and rollback evidence is incomplete | Product owner; read-only default and reversible operation |

No owner audio or protected holdout was used to close any blocker.
