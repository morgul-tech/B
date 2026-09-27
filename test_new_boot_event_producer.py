from __future__ import annotations

import tempfile
from pathlib import Path

from new_boot_event_producer import (
    AuthorityProof,
    BOOT_SOURCE_REVISION,
    CEREBRO_SOURCE_REVISION,
    JsonReplayJournal,
    Lineage,
    REQUIRED_SCOPE,
    produce_new_boot,
)


def lineage(**kw):
    base = dict(
        session_id="session-current-001",
        attempt_id="attempt-current-001",
        generation_id="generation-current-001",
        currentness_revision="provider-rev-42",
        currentness_state="CURRENT",
        boot_source_revision=BOOT_SOURCE_REVISION,
        cerebro_source_revision=CEREBRO_SOURCE_REVISION,
    )
    base.update(kw)
    return Lineage(**base)


def proof(l: Lineage, **kw):
    base = dict(
        issuer_id="TEST_ONLY_BOOT_AUTHORITY",
        signer_id="TEST_ONLY_SIGNER",
        authority_revision="test-auth-rev-1",
        proof_ref="test-only:verified-authority-fixture",
        signature_verified=True,
        scopes=(REQUIRED_SCOPE,),
        session_id=l.session_id,
        attempt_id=l.attempt_id,
        generation_id=l.generation_id,
        currentness_revision=l.currentness_revision,
        boot_source_revision=l.boot_source_revision,
        cerebro_source_revision=l.cerebro_source_revision,
    )
    base.update(kw)
    return AuthorityProof(**base)


def verified_test_only(p: AuthorityProof) -> bool:
    return (
        p.proof_ref.startswith("test-only:")
        and p.issuer_id == "TEST_ONLY_BOOT_AUTHORITY"
        and p.signer_id.startswith("TEST_ONLY_SIGNER")
    )


def run():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        cases = {}

        l = lineage()
        cases["default_hold_auth"] = produce_new_boot(
            l, None, authority_verifier=None, journal=JsonReplayJournal(root / "a.json")
        )
        cases["no_verifier_hold_auth"] = produce_new_boot(
            l, proof(l), authority_verifier=None, journal=JsonReplayJournal(root / "b.json")
        )
        cases["unauthenticated_issuer"] = produce_new_boot(
            l,
            proof(l, signature_verified=False),
            authority_verifier=verified_test_only,
            journal=JsonReplayJournal(root / "c.json"),
        )
        cases["wrong_attempt"] = produce_new_boot(
            l,
            proof(l, attempt_id="attempt-wrong"),
            authority_verifier=verified_test_only,
            journal=JsonReplayJournal(root / "d.json"),
        )
        cases["wrong_generation"] = produce_new_boot(
            l,
            proof(l, generation_id="generation-wrong"),
            authority_verifier=verified_test_only,
            journal=JsonReplayJournal(root / "dg.json"),
        )
        cases["stale_currentness"] = produce_new_boot(
            lineage(currentness_state="STALE"),
            proof(lineage(currentness_state="STALE")),
            authority_verifier=verified_test_only,
            journal=JsonReplayJournal(root / "e.json"),
        )
        cases["broad_scope"] = produce_new_boot(
            l,
            proof(l, scopes=(REQUIRED_SCOPE, "project_state:write")),
            authority_verifier=verified_test_only,
            journal=JsonReplayJournal(root / "f.json"),
        )

        historical = lineage(
            session_id="01a0e200-f0ce-7492-8247-972c76d46687",
            attempt_id="BOOT-FULL-WORKER-20260927-9F0A0D36",
            generation_id="NOT_CREATED",
            currentness_revision="historical-terminal",
        )
        cases["historical_not_created_generation"] = produce_new_boot(
            historical,
            proof(historical),
            authority_verifier=verified_test_only,
            journal=JsonReplayJournal(root / "hist.json"),
        )

        j = JsonReplayJournal(root / "positive.json")
        pos = produce_new_boot(l, proof(l), authority_verifier=verified_test_only, journal=j)
        dup = produce_new_boot(l, proof(l), authority_verifier=verified_test_only, journal=j)
        cases["synthetic_positive"] = pos
        cases["exact_duplicate"] = dup

        cases["changed_same_lineage_conflict"] = produce_new_boot(
            l,
            proof(l, signer_id="TEST_ONLY_SIGNER_2", authority_revision="test-auth-rev-2"),
            authority_verifier=verified_test_only,
            journal=j,
        )

        expected = {
            "default_hold_auth": ("HOLD_AUTH", "VERIFIED_ISSUER_SIGNER_SCOPE_UNBOUND"),
            "no_verifier_hold_auth": ("HOLD_AUTH", "VERIFIED_ISSUER_SIGNER_SCOPE_UNBOUND"),
            "unauthenticated_issuer": ("HOLD_AUTH", "ISSUER_SIGNATURE_UNVERIFIED"),
            "wrong_attempt": ("HOLD_AUTH", "BINDING_MISMATCH:attempt_id"),
            "wrong_generation": ("HOLD_AUTH", "BINDING_MISMATCH:generation_id"),
            "stale_currentness": ("HOLD_STALE", "CURRENTNESS_NOT_CURRENT"),
            "broad_scope": ("HOLD_AUTH", "ISSUER_SCOPE_NOT_EXACT"),
            "historical_not_created_generation": ("HOLD_AUTH", "LINEAGE_UNPROVEN:generation_id"),
            "synthetic_positive": ("CANDIDATE_EVENT_READY", "VERIFIED_SYNTHETIC_OR_EXTERNAL_AUTHORITY_ONLY"),
            "exact_duplicate": ("IDEMPOTENT_NOOP", "EXACT_DUPLICATE"),
            "changed_same_lineage_conflict": ("HOLD_REPLAY_CONFLICT", "LINEAGE_ALREADY_BOUND_TO_DIFFERENT_EVENT"),
        }

        failed = []
        for name, (status, reason) in expected.items():
            got = cases[name]
            if (got.status, got.reason) != (status, reason):
                failed.append((name, got.status, got.reason, status, reason))

        assert pos.event and pos.event["event_type"] == "NEW_BOOT"
        assert dup.event_id == pos.event_id
        assert not failed, failed

        return {
            "result": "PASS",
            "tests": len(expected),
            "passed": len(expected),
            "historical_boundary": {
                "session_id": historical.session_id,
                "attempt_id": historical.attempt_id,
                "generation": historical.generation_id,
                "expected": "HOLD_AUTH",
                "reason": "LINEAGE_UNPROVEN:generation_id",
            },
            "positive_event_id": pos.event_id,
            "positive_fixture_is_test_only": True,
            "live_authority_claimed": False,
        }


if __name__ == "__main__":
    import json

    print(json.dumps(run(), sort_keys=True))