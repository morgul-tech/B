from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

SCHEMA = "cerebro.boot.new-boot-event/v0.1-candidate"
BOOT_SOURCE_REVISION = "936d34ba26a6f3b4ec797120bfbf3cefb6ff6ccb"
CEREBRO_SOURCE_REVISION = "8c503cda639838d44f29dd6e555fed7dc6e0e2ee"
REQUIRED_SCOPE = "boot:new_boot:emit"
INVALID_SENTINELS = {"UNKNOWN", "NOT_CREATED", "NONE", "NULL", "N/A", "NOT_APPLICABLE", "UNBOUND"}


@dataclass(frozen=True)
class Lineage:
    session_id: str
    attempt_id: str
    generation_id: str
    currentness_revision: str
    currentness_state: str
    boot_source_revision: str = BOOT_SOURCE_REVISION
    cerebro_source_revision: str = CEREBRO_SOURCE_REVISION


@dataclass(frozen=True)
class AuthorityProof:
    issuer_id: str
    signer_id: str
    authority_revision: str
    proof_ref: str
    signature_verified: bool
    scopes: tuple[str, ...]
    session_id: str
    attempt_id: str
    generation_id: str
    currentness_revision: str
    boot_source_revision: str
    cerebro_source_revision: str


@dataclass(frozen=True)
class ProducerDecision:
    status: str
    reason: str
    event: Mapping[str, Any] | None = None
    event_id: str | None = None
    replay_state: str | None = None


def _usable_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip().upper() not in INVALID_SENTINELS


def _canonical(obj: Mapping[str, Any]) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha(obj: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(obj)).hexdigest()


def lineage_key(lineage: Lineage) -> str:
    return _sha({
        "session_id": lineage.session_id,
        "attempt_id": lineage.attempt_id,
        "generation_id": lineage.generation_id,
    })


class JsonReplayJournal:
    """Candidate-local replay journal. It grants no production custody or authority."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema": "cerebro.boot.new-boot-journal/v0.1-candidate", "lineages": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def record_once(self, *, lineage: Lineage, event: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]]:
        data = self._read()
        rows = data.setdefault("lineages", {})
        key = lineage_key(lineage)
        digest = _sha(dict(event))
        existing = rows.get(key)
        if existing:
            if existing["event_digest_sha256"] == digest and existing["event_id"] == event["event_id"]:
                return "DUPLICATE_NOOP", existing
            return "CONFLICT_HOLD", existing
        rows[key] = {"event_id": event["event_id"], "event_digest_sha256": digest}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)
        return "RECORDED", rows[key]


def _binding_mismatch(lineage: Lineage, proof: AuthorityProof) -> str | None:
    pairs = {
        "session_id": (lineage.session_id, proof.session_id),
        "attempt_id": (lineage.attempt_id, proof.attempt_id),
        "generation_id": (lineage.generation_id, proof.generation_id),
        "currentness_revision": (lineage.currentness_revision, proof.currentness_revision),
        "boot_source_revision": (lineage.boot_source_revision, proof.boot_source_revision),
        "cerebro_source_revision": (lineage.cerebro_source_revision, proof.cerebro_source_revision),
    }
    for name, (expected, actual) in pairs.items():
        if expected != actual:
            return f"BINDING_MISMATCH:{name}"
    return None


def produce_new_boot(
    lineage: Lineage,
    authority_proof: AuthorityProof | None,
    *,
    authority_verifier: Callable[[AuthorityProof], bool] | None,
    journal: JsonReplayJournal,
) -> ProducerDecision:
    if lineage.currentness_state != "CURRENT":
        return ProducerDecision("HOLD_STALE", "CURRENTNESS_NOT_CURRENT")
    if lineage.boot_source_revision != BOOT_SOURCE_REVISION:
        return ProducerDecision("HOLD_STALE", "BOOT_SOURCE_REVISION_MISMATCH")
    if lineage.cerebro_source_revision != CEREBRO_SOURCE_REVISION:
        return ProducerDecision("HOLD_STALE", "CEREBRO_SOURCE_REVISION_MISMATCH")

    for name in ("session_id", "attempt_id", "generation_id", "currentness_revision"):
        if not _usable_text(getattr(lineage, name)):
            return ProducerDecision("HOLD_AUTH", f"LINEAGE_UNPROVEN:{name}")

    if authority_proof is None or authority_verifier is None:
        return ProducerDecision("HOLD_AUTH", "VERIFIED_ISSUER_SIGNER_SCOPE_UNBOUND")
    if not authority_proof.signature_verified:
        return ProducerDecision("HOLD_AUTH", "ISSUER_SIGNATURE_UNVERIFIED")
    if tuple(sorted(authority_proof.scopes)) != (REQUIRED_SCOPE,):
        return ProducerDecision("HOLD_AUTH", "ISSUER_SCOPE_NOT_EXACT")

    for name in ("issuer_id", "signer_id", "authority_revision", "proof_ref"):
        if not _usable_text(getattr(authority_proof, name)):
            return ProducerDecision("HOLD_AUTH", f"AUTHORITY_UNPROVEN:{name}")

    mismatch = _binding_mismatch(lineage, authority_proof)
    if mismatch:
        return ProducerDecision("HOLD_AUTH", mismatch)
    if authority_verifier(authority_proof) is not True:
        return ProducerDecision("HOLD_AUTH", "AUTHORITY_VERIFIER_REJECTED")

    core = {
        "schema": SCHEMA,
        "event_type": "NEW_BOOT",
        "session_id": lineage.session_id,
        "attempt_id": lineage.attempt_id,
        "generation_id": lineage.generation_id,
        "currentness": {
            "state": lineage.currentness_state,
            "revision": lineage.currentness_revision,
            "boot_source_revision": lineage.boot_source_revision,
            "cerebro_source_revision": lineage.cerebro_source_revision,
        },
        "issuer": {
            "issuer_id": authority_proof.issuer_id,
            "signer_id": authority_proof.signer_id,
            "authority_revision": authority_proof.authority_revision,
            "proof_ref": authority_proof.proof_ref,
            "scope": REQUIRED_SCOPE,
        },
    }
    event_id = "NEWBOOT-" + _sha(core)[:32].upper()
    event = dict(core)
    event["event_id"] = event_id
    event["event_digest_sha256"] = _sha(event)

    replay, _ = journal.record_once(lineage=lineage, event=event)
    if replay == "DUPLICATE_NOOP":
        return ProducerDecision("IDEMPOTENT_NOOP", "EXACT_DUPLICATE", event=event, event_id=event_id, replay_state=replay)
    if replay == "CONFLICT_HOLD":
        return ProducerDecision("HOLD_REPLAY_CONFLICT", "LINEAGE_ALREADY_BOUND_TO_DIFFERENT_EVENT", event_id=event_id, replay_state=replay)
    return ProducerDecision(
        "CANDIDATE_EVENT_READY",
        "VERIFIED_SYNTHETIC_OR_EXTERNAL_AUTHORITY_ONLY",
        event=event,
        event_id=event_id,
        replay_state=replay,
    )