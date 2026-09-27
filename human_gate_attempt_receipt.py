from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

START_SCHEMA = "cerebro-boot-human-gate-start-receipt/v0.2-candidate"
BIND_SCHEMA = "cerebro-boot-human-gate-attempt-binding/v0.2-candidate"
SEQUENCE_ID = "CEREBRO_BOOT_FULL_STRICT_V1"
CANONICAL_TRIGGER = "BOOT FULL WORKER"
ALIAS_RESOLVER_VERSION = "1.3"
BOOT_FULL_PROVIDER_ID = "1ImzuaW0XL444L31wpLx5YYGwX6BNXYUIRZ_A-YV387U"
BOOT_FULL_VERSION = "1.9"
BOOT_FULL_SHA256 = "11915cc2e3bd0cb3ea54d0d47995ccf1ad90068767b91de77d40d517ea82dd12"
ALLOWED_TERMINAL_SCHEMAS = {
    "CEREBRO_BOOT_REPORT_COMMAND_SCHEMA_COMPATIBLE",
    "cerebro-boot-full-receipt/v1",
}
INVALID = {"", "UNKNOWN", "NONE", "NULL", "N/A", "NOT_APPLICABLE", "UNBOUND"}


@dataclass(frozen=True)
class HumanGateEvent:
    event_ref: str
    thread_id: str
    turn_id: str
    raw_human_trigger: str
    observed_at_utc: str
    source_ref: str


@dataclass(frozen=True)
class AttemptAllocation:
    allocation_ref: str
    thread_id: str
    turn_id: str
    attempt_id: str
    observed_at_utc: str
    source_ref: str


@dataclass(frozen=True)
class Decision:
    status: str
    reason: str
    receipt: Mapping[str, Any] | None = None


def _canonical(obj: Mapping[str, Any]) -> bytes:
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
def _sha(obj: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(obj)).hexdigest()


def _usable(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and value.strip().upper() not in INVALID
    )


def _parse_utc(value: str) -> datetime:
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("timezone-required")
    return parsed.astimezone(timezone.utc)


def resolve_worker_trigger(raw: str) -> str | None:
    text = " ".join(raw.strip().split()).lower()
    if text == "@google drive boot worker":
        return CANONICAL_TRIGGER
    if text in {"boot worker", "boot full worker"}:
        return CANONICAL_TRIGGER
    return None
def parse_kv_receipt(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        fields[key.strip()] = value.strip()
    return fields


class JsonGateJournal:
    """Candidate-only custody model; no production-store claim."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "schema": "cerebro-boot-human-gate-journal/v0.2-candidate",
                "gate_events": {},
                "attempts": {},
            }
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(data, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, self.path)

    def capture_gate(self, event: HumanGateEvent) -> Decision:
        if not all(
            _usable(v)
            for v in (
                event.event_ref,
                event.thread_id,
                event.turn_id,
                event.raw_human_trigger,
                event.source_ref,
            )
        ):
            return Decision("HOLD_GATE_SENSOR", "HUMAN_GATE_EVENT_INCOMPLETE")
        if resolve_worker_trigger(event.raw_human_trigger) != CANONICAL_TRIGGER:
            return Decision("HOLD_GATE_INPUT", "WORKER_HUMAN_GATE_TRIGGER_NOT_EXACT")
        try:
            observed = _parse_utc(event.observed_at_utc)
        except Exception:
            return Decision("HOLD_GATE_SENSOR", "HUMAN_GATE_TIME_INVALID")

        core = {
            "schema": START_SCHEMA,
            "record_type": "HUMAN_BOOT_GATE_OPENED",
            "attempt_creator": "HUMAN",
            "boot_engine_initiator": False,
            "human_gate_event_ref": event.event_ref,
            "thread_id": event.thread_id,
            "turn_id": event.turn_id,
            "raw_human_trigger": event.raw_human_trigger.strip(),
            "resolved_canonical_trigger": CANONICAL_TRIGGER,
            "alias_resolver_version": ALIAS_RESOLVER_VERSION,
            "sequence_id": SEQUENCE_ID,
            "observed_at_utc": observed.isoformat().replace("+00:00", "Z"),
            "source_ref": event.source_ref,
            "attempt_id": None,
            "generation_state": "NOT_CREATED_AT_GATE",
        }
        core["receipt_id"] = "HBGATE-" + _sha(core)[:32].upper()
        core["receipt_digest_sha256"] = _sha(core)

        data = self._read()
        events = data.setdefault("gate_events", {})
        existing = events.get(event.event_ref)
        if existing is not None:
            if existing.get("gate_receipt") == core:
                return Decision(
                    "IDEMPOTENT_EXISTING",
                    "EXACT_HUMAN_GATE_EVENT_ALREADY_CAPTURED",
                    existing["gate_receipt"],
                )
            return Decision(
                "HOLD_GATE_REPLAY_CONFLICT",
                "HUMAN_GATE_EVENT_REF_REUSED_WITH_CHANGED_INPUT",
            )
        events[event.event_ref] = {
            "gate_receipt": core,
            "attempt_binding": None,
        }
        self._write(data)
        return Decision("CAPTURED_PENDING_ATTEMPT", "HUMAN_GATE_RECORDED", core)

    def bind_attempt(
        self,
        *,
        gate_event_ref: str,
        allocation: AttemptAllocation,
        terminal_receipt: Mapping[str, str],
        terminal_receipt_ref: str,
        terminal_observed_at_utc: str,
    ) -> Decision:
        data = self._read()
        events = data.setdefault("gate_events", {})
        attempts = data.setdefault("attempts", {})
        gate_row = events.get(gate_event_ref)
        if gate_row is None:
            return Decision("HOLD_GATE_SENSOR", "HUMAN_GATE_EVENT_NOT_CAPTURED")
        gate = gate_row["gate_receipt"]

        if not all(
            _usable(v)
            for v in (
                allocation.allocation_ref,
                allocation.thread_id,
                allocation.turn_id,
                allocation.attempt_id,
                allocation.source_ref,
                terminal_receipt_ref,
            )
        ):
            return Decision("HOLD_GATE_SENSOR", "ATTEMPT_BINDING_INPUT_INCOMPLETE")
        if allocation.thread_id != gate["thread_id"]:
            return Decision("HOLD_STALE", "ALLOCATION_THREAD_MISMATCH")
        if allocation.turn_id != gate["turn_id"]:
            return Decision("HOLD_STALE", "ALLOCATION_TURN_MISMATCH")

        try:
            gate_time = _parse_utc(gate["observed_at_utc"])
            allocation_time = _parse_utc(allocation.observed_at_utc)
            terminal_time = _parse_utc(terminal_observed_at_utc)
        except Exception:
            return Decision("HOLD_GATE_SENSOR", "BINDING_TIME_INVALID")
        if allocation_time < gate_time:
            return Decision("HOLD_STALE", "ALLOCATION_PRECEDES_HUMAN_GATE")
        if terminal_time < allocation_time:
            return Decision("HOLD_STALE", "TERMINAL_PRECEDES_ALLOCATION")

        schema = terminal_receipt.get("SCHEMA")
        if schema not in ALLOWED_TERMINAL_SCHEMAS:
            return Decision("HOLD_TERMINAL", "TERMINAL_SCHEMA_UNSUPPORTED")
        exact = {
            "BOOT_ATTEMPT_ID": allocation.attempt_id,
            "RAW_HUMAN_TRIGGER": gate["raw_human_trigger"],
            "RESOLVED_CANONICAL_TRIGGER": gate["resolved_canonical_trigger"],
            "ALIAS_RESOLVER_VERSION": ALIAS_RESOLVER_VERSION,
            "SEQUENCE_ID": SEQUENCE_ID,
            "BOOT_FULL_PROVIDER_ID": BOOT_FULL_PROVIDER_ID,
            "BOOT_FULL_VERSION": BOOT_FULL_VERSION,
            "BOOT_FULL_SHA256": BOOT_FULL_SHA256,
        }
        for field, expected in exact.items():
            if terminal_receipt.get(field) != expected:
                return Decision(
                    "HOLD_TERMINAL",
                    f"TERMINAL_BINDING_MISMATCH:{field}",
                )

        generation = terminal_receipt.get("GENERATION")
        if not (_usable(generation) or generation == "NOT_CREATED"):
            return Decision("HOLD_TERMINAL", "TERMINAL_GENERATION_MISSING")
        terminal_status = terminal_receipt.get("TERMINAL_STATUS")
        if not _usable(terminal_status):
            return Decision("HOLD_TERMINAL", "TERMINAL_STATUS_MISSING")

        binding = {
            "schema": BIND_SCHEMA,
            "record_type": "HUMAN_BOOT_ATTEMPT_BOUND",
            "attempt_creator": "HUMAN",
            "boot_engine_initiator": False,
            "human_gate_event_ref": gate_event_ref,
            "thread_id": gate["thread_id"],
            "turn_id": gate["turn_id"],
            "attempt_allocation_ref": allocation.allocation_ref,
            "boot_attempt_id": allocation.attempt_id,
            "generation": generation,
            "terminal_status": terminal_status,
            "first_nonpass_step": terminal_receipt.get("FIRST_NONPASS_STEP"),
            "ready": terminal_receipt.get("READY"),
            "terminal_receipt_ref": terminal_receipt_ref,
            "terminal_receipt_schema": schema,
            "terminal_observed_at_utc": terminal_time.isoformat().replace(
                "+00:00",
                "Z",
            ),
            "allocation_source_ref": allocation.source_ref,
            "gate_receipt_digest_sha256": gate["receipt_digest_sha256"],
        }
        binding["binding_id"] = "HBATTEMPT-" + _sha(binding)[:32].upper()
        binding["binding_digest_sha256"] = _sha(binding)

        existing_binding = gate_row.get("attempt_binding")
        if existing_binding is not None:
            if existing_binding == binding:
                return Decision(
                    "IDEMPOTENT_BOUND",
                    "EXACT_HUMAN_ATTEMPT_ALREADY_BOUND",
                    binding,
                )
            return Decision(
                "HOLD_GATE_REPLAY_CONFLICT",
                "HUMAN_GATE_EVENT_ALREADY_BOUND_TO_OTHER_ATTEMPT",
            )

        prior_event = attempts.get(allocation.attempt_id)
        if prior_event is not None and prior_event != gate_event_ref:
            return Decision(
                "HOLD_GATE_REPLAY_CONFLICT",
                "ATTEMPT_ALREADY_BOUND_TO_OTHER_HUMAN_GATE_EVENT",
            )

        gate_row["attempt_binding"] = binding
        attempts[allocation.attempt_id] = gate_event_ref
        self._write(data)
        return Decision("BOUND", "HUMAN_GATE_ATTEMPT_BOUND", binding)