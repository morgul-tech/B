# P1464/C888 NEW_BOOT producer candidate — integration plan

Status: isolated candidate only; production authority remains HOLD_AUTH.

Pinned Boot-owned source:
- repository: morgul-tech/B
- revision: 936d34ba26a6f3b4ec797120bfbf3cefb6ff6ccb
- BootEngine blob: d73d513793e186c989606da97a09514bfaee9a00
- authoritative Cerebro Source: morgul-tech/Cerebro-Source-1.0@8c503cda639838d44f29dd6e555fed7dc6e0e2ee

Current lineage boundary:
- no verified active NEW_BOOT attempt/generation exists.
- latest exact X7 failure is historical only:
  session 01a0e200-f0ce-7492-8247-972c76d46687
  attempt BOOT-FULL-WORKER-20260927-9F0A0D36
  generation NOT_CREATED
- that lineage is rejected and must not be replayed.

Minimum production integration, only after protected authority decision:
1. Keep producer in the Boot-owned path; do not move event truth into Context.
2. Bind it only after the lawful Boot lineage owner has minted exact current session_id, attempt_id, generation_id and currentness revision.
3. Supply an authenticated authority_verifier from the verified Boot event authority owner. It must verify attributable issuer, signer, exact scope boot:new_boot:emit, authority revision and exact lineage/source binding. Caller-provided strings are insufficient.
4. Reuse a verified existing Boot-owned attempt/receipt custody boundary for replay reservation; the candidate JsonReplayJournal is test-only and is not a production custody claim. If no lawful existing replay/custody adapter is verified, remain HOLD_AUTH/HOLD_SOURCE rather than invent a store.
5. Emit NEW_BOOT only after authority + currentness + replay reservation succeed. Duplicate exact lineage is idempotent no-op; conflicting lineage/event is HOLD.
6. Context may consume only the verified event interface; this candidate does not initialize Context state.
7. Distinct verifier applies frozen C890 oracle before any canonical merge/deploy.
8. Only after protected owner authority, distinct verification and behavior-real readback may PM consider a separate fresh Boot canary.

No canonical merge/deploy, Context mutation, Boot run, READY, credentials, or replay is authorized by this artifact.