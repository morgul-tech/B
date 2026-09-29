# P1479 / C903 — STEP03 semantic consumer repair

RESULT: HOLD_OWNER  
ACTOR: A2/985CD438 temporary Bootreparatør  
EFFECT: NONE

## Current binding
- Current PM: PROJECT_MANAGER_21749D93
- Packet/claim: P1479/C903
- Failed immutable attempt: CEREBRO-BOOT-MUN5HRE8-0B2AE6F6
- Failed receipt: Drive 1MaWbiqoIEHULEqlUP8S1GN56NYON4pt9
- BootFull: v1.9 / SHA256 11915cc2e3bd0cb3ea54d0d47995ccf1ad90068767b91de77d40d517ea82dd12
- C901 N07: deterministic membership was mislabeled consumption.

## Repair implemented in this isolated branch
The candidate contract separates:
1. required current ACTIVE membership;
2. per-row semantic applicability and supersession resolution;
3. consumer-produced execution evidence.

Required membership always starts with `consumption_status=NOT_EXECUTED` and `consumed_ids=[]`.
No applicable ID can become consumed from a manifest, sheet read, caller assertion, or membership equality.

For a STEP03 execution to validate, the existing consumer must produce exactly one row-bound evidence item for every current ACTIVE row, binding:
- boot execution ID and immutable boot attempt ID;
- current provider snapshot SHA;
- provider row, OVERLAY_ID and full row SHA;
- explicit UNBOUND BOOT CEREBRO scope;
- semantic applicability basis;
- supersession field binding and semantic resolution;
- material semantic disposition;
- evidence origin CONSUMER_EXECUTION;
- semantic fingerprint bound to the above execution and row.

UNKNOWN applicability, contradictory supersession, stale snapshot, missing/skipped row semantics, duplicates, wrong UNBOUND scope, false consumption origin, or row/hash mismatch fail closed.

## UNBOUND scope
The candidate does not reuse C900's generic Worker selector.
The exact execution scope is:
PROFILE_REQUESTED=UNBOUND; PROFILE_EFFECTIVE=NONE; WORKFORM=NONE;
ROLE_REQUESTED=NONE; ROLE_BOUND=NONE; PROJECT=NONE; ASSIGNMENT=NONE;
POOL_MEMBER=NO; BOOT_CONTEXT=BOOT_CEREBRO.

Per-row applicability remains a consumer semantic decision. It is not inferred by copying the Worker 106/51 split.

## Current provider snapshot probe
Fresh PRE_SOURCE_OVERLAY A1:K231:
- populated records: 165
- ACTIVE records: 157
- snapshot SHA256: dbb166e168bc25f2a8575df0af7c0e826b562cd07c60fb153018d575ad940c30
- compiled required ACTIVE membership: 157
- consumption_status: NOT_EXECUTED
- consumed_ids: []

This is deliberately not STEP03 PASS.

## Tests
9/9 isolated tests PASS:
- compiler membership remains NOT_EXECUTED;
- positive genuine consumer-produced evidence;
- missing/skipped semantics fail closed;
- false consumption from caller/manifest assertion fails closed;
- stale snapshot/revision fails closed;
- contradictory supersession fails closed;
- wrong UNBOUND scope fails closed;
- duplicate overlay rows fail closed;
- UNKNOWN applicability fails closed.

Synthetic tests are not a live Boot PASS.

## Frozen inputs preserved
C900 input remains immutable and is not consumption proof:
- commit b254a5bf1d0e1c7deb3b89bdcc479ab2bd4d7c32
- ZIP SHA256 cc681c53e71bc64145e95e2d78b81fa174fee3d10a977bff829facd88287f57c
- manifest SHA256 46a1da163f57d388b7b5eaf31c9958a94aed55ac25cd308ff55c51abcd7f289b

The failed CEREBRO-BOOT-MUN5HRE8-0B2AE6F6 receipt is unchanged.

## Exact remaining live integration edge
FIRST_MISSING_CAPABILITY =
VERSIONED_CALLABLE_EXISTING_BOOTFULL_STEP03_OVERLAY_CONSUMER_IMPLEMENTATION_OR_PRODUCTION_ADAPTER
THAT_IS_BOUND_TO_THE_REAL_BOOT_EXECUTION_AND_CAN_EMIT_ROW_BOUND_SEMANTIC_CONSUMPTION_EVIDENCE.

Fresh source inspection:
- morgul-tech/B main@936d34ba26a6f3b4ec797120bfbf3cefb6ff6ccb contains only BootEngine, a bootstrap state/authority specification; it has no STEP03 overlay consumer implementation.
- Cerebro-Source main@b3a0e4abfe7862fcbe41ebade42bbf1261824e73 contains BootFull architecture/runtime birth code but no provider-addressable STEP03 PRE_SOURCE_OVERLAY consumer path.
- Earlier exact WATCH001 evidence PM8674 likewise found an ad-hoc chat-local request path rather than a versioned Boot-owned constructor/consumer.

Therefore wiring this validator as the consumer would invent a parallel Boot path, which this claim does not authorize.

## Way Home
Current PM21749D93 must bind/provide the exact existing production STEP03 consumer implementation/callable adapter revision (not search recursively for an actor). Apply this contract at that real callsite; then B1/C904 performs distinct verification against the exact repaired bytes. Only a later explicit Human Boot trigger with a new attempt ID may test behavior-real STEP03.

No merge, deploy, Boot trigger/replay, failed-receipt rewrite, generation creation, READY inference, or live worker-chat edit occurred.
