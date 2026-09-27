# P1473/C897 Human-gated Boot attempt receipt — review plan

Status: isolated passive-capture candidate. Human remains the only Boot attempt initiator.

## Authoritative Human gate
- Human action: `@google drive boot worker`
- Canonical trigger: `BOOT FULL WORKER`
- BootFull provider: `1ImzuaW0XL444L31wpLx5YYGwX6BNXYUIRZ_A-YV387U`
- Version: 1.9
- SHA256: `11915cc2e3bd0cb3ea54d0d47995ccf1ad90068767b91de77d40d517ea82dd12`
- BootEngine is not the initiator and may not autonomously mint an attempt.

## Behavior-real validation
C897 was validated against one current Human-gated Worker attempt and its provider-readback terminal receipt. Exact thread, turn, message, attempt and Drive receipt identifiers remain in the private PM provider evidence and are intentionally not copied into this public review branch.

The live attempt terminated fail-closed before generation/READY. The shared-link mapping was not used as evidence.

## Passive capture model
1. Capture the machine-readable Human `UserMessage` event only.
2. At gate time, record thread/turn/event/raw trigger; attempt_id remains null and generation is `NOT_CREATED_AT_GATE`.
3. Never generate an attempt ID, NEW_BOOT event, signer, or authority.
4. Bind an attempt only when a same-thread/same-turn allocation observation is corroborated by an authoritative Boot terminal receipt with the exact same attempt ID and trigger.
5. One Human event binds at most one attempt; one attempt binds at most one Human event.
6. Exact duplicate binding is idempotent. Changed/reused identity is HOLD.
7. Missing gate event => `HOLD_GATE_SENSOR`.
8. Wrong thread/turn or temporal order => `HOLD_STALE`.
9. Terminal mismatch => `HOLD_TERMINAL`.
10. Prior failed receipts are immutable and cannot become fresh Human-gate evidence.

## Production seam
The observed machine-readable sensor family is the local Codex session journal's Human UserMessage plus a same-turn attempt-allocation event, reconciled to provider-readback `Shared/BOOT_REPORTS`.

A production adapter must be read-only against the live worker path, expose stable event/thread/turn/time identity, never write the worker conversation, never trigger Boot, and fail closed if the gate event or attempt allocation is unavailable. No new service/store is introduced here; the JSON journal in tests is custody modeling only.

## Non-effects
No merge, deploy, Boot trigger, retry, NEW_BOOT emission, READY inference, Context mutation, or failed-receipt rewrite is authorized by this branch.