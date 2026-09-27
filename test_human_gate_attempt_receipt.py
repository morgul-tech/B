from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from pathlib import Path

from human_gate_attempt_receipt import (
    AttemptAllocation,
    HumanGateEvent,
    JsonGateJournal,
    parse_kv_receipt,
)

THREAD = "thread-human-gate-fixture"
TURN = "turn-human-gate-fixture"
EVENT = "human-message-fixture-001"
ALLOC_REF = "attempt-allocation-fixture-001"
ATTEMPT = "attempt-fixture-001"
DRIVE_REF = "provider:terminal-receipt-fixture-001"

LIVE_RECEIPT = """SCHEMA=CEREBRO_BOOT_REPORT_COMMAND_SCHEMA_COMPATIBLE
BOOT_ATTEMPT_ID=attempt-fixture-001
RAW_HUMAN_TRIGGER=@google drive boot worker
RESOLVED_CANONICAL_TRIGGER=BOOT FULL WORKER
ALIAS_RESOLVER_VERSION=1.3
SEQUENCE_ID=CEREBRO_BOOT_FULL_STRICT_V1
GENERATION=NOT_CREATED
BOOT_FULL_PROVIDER_ID=1ImzuaW0XL444L31wpLx5YYGwX6BNXYUIRZ_A-YV387U
BOOT_FULL_VERSION=1.9
BOOT_FULL_SHA256=11915cc2e3bd0cb3ea54d0d47995ccf1ad90068767b91de77d40d517ea82dd12
STEP_03=EXECUTED_NONPASS
FIRST_NONPASS_STEP=STEP_03
TERMINAL_STATUS=BOOT_ATTEMPT_TERMINATED_NONPASS
READY=NO
"""

FAILED_X7 = """SCHEMA=cerebro-boot-full-receipt/v1
BOOT_ATTEMPT_ID=historical-failed-x7-attempt
RAW_HUMAN_TRIGGER=@google drive boot worker
RESOLVED_CANONICAL_TRIGGER=BOOT FULL WORKER
ALIAS_RESOLVER_VERSION=1.3
SEQUENCE_ID=CEREBRO_BOOT_FULL_STRICT_V1
GENERATION=NOT_CREATED
BOOT_FULL_PROVIDER_ID=1ImzuaW0XL444L31wpLx5YYGwX6BNXYUIRZ_A-YV387U
BOOT_FULL_VERSION=1.9
BOOT_FULL_SHA256=11915cc2e3bd0cb3ea54d0d47995ccf1ad90068767b91de77d40d517ea82dd12
FIRST_NONPASS_STEP=STEP_11
TERMINAL_STATUS=BOOT_NONPASS
READY=NO
"""


def gate(**kw) -> HumanGateEvent:
    base = dict(
        event_ref=EVENT,
        thread_id=THREAD,
        turn_id=TURN,
        raw_human_trigger="@google drive boot worker",
        observed_at_utc="2026-09-27T21:26:02.666Z",
        source_ref="codex-session:event_msg/UserMessage",
    )
    base.update(kw)
    return HumanGateEvent(**base)


def allocation(**kw) -> AttemptAllocation:
    base = dict(
        allocation_ref=ALLOC_REF,
        thread_id=THREAD,
        turn_id=TURN,
        attempt_id=ATTEMPT,
        observed_at_utc="2026-09-27T21:38:47.440Z",
        source_ref="codex-session:CommandExecution",
    )
    base.update(kw)
    return AttemptAllocation(**base)


def digest(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def run():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        results = {}

        j = JsonGateJournal(root / "live.json")
        start = j.capture_gate(gate())
        results["live_gate_capture"] = start.status
        assert start.status == "CAPTURED_PENDING_ATTEMPT"
        assert start.receipt["attempt_id"] is None
        assert start.receipt["boot_engine_initiator"] is False
        assert start.receipt["attempt_creator"] == "HUMAN"

        bound = j.bind_attempt(
            gate_event_ref=EVENT,
            allocation=allocation(),
            terminal_receipt=parse_kv_receipt(LIVE_RECEIPT),
            terminal_receipt_ref=DRIVE_REF,
            terminal_observed_at_utc="2026-09-27T21:40:16.169Z",
        )
        results["live_exact_binding"] = bound.status
        assert bound.status == "BOUND"
        assert bound.receipt["boot_attempt_id"] == ATTEMPT
        assert bound.receipt["thread_id"] == THREAD
        assert bound.receipt["generation"] == "NOT_CREATED"
        assert bound.receipt["ready"] == "NO"

        duplicate = j.bind_attempt(
            gate_event_ref=EVENT,
            allocation=allocation(),
            terminal_receipt=parse_kv_receipt(LIVE_RECEIPT),
            terminal_receipt_ref=DRIVE_REF,
            terminal_observed_at_utc="2026-09-27T21:40:16.169Z",
        )
        results["exact_duplicate"] = duplicate.status
        assert duplicate.status == "IDEMPOTENT_BOUND"

        j2 = JsonGateJournal(root / "missing.json")
        missing = j2.capture_gate(gate(event_ref=""))
        results["missing_human_start"] = missing.status
        assert missing.status == "HOLD_GATE_SENSOR"
        j3 = JsonGateJournal(root / "wrong-thread.json")
        assert j3.capture_gate(gate()).status == "CAPTURED_PENDING_ATTEMPT"
        wrong_thread = j3.bind_attempt(
            gate_event_ref=EVENT,
            allocation=allocation(thread_id="wrong-thread"),
            terminal_receipt=parse_kv_receipt(LIVE_RECEIPT),
            terminal_receipt_ref=DRIVE_REF,
            terminal_observed_at_utc="2026-09-27T21:40:16.169Z",
        )
        results["wrong_thread"] = wrong_thread.status
        assert wrong_thread.status == "HOLD_STALE"

        j4 = JsonGateJournal(root / "wrong-turn.json")
        assert j4.capture_gate(gate()).status == "CAPTURED_PENDING_ATTEMPT"
        wrong_turn = j4.bind_attempt(
            gate_event_ref=EVENT,
            allocation=allocation(turn_id="wrong-turn"),
            terminal_receipt=parse_kv_receipt(LIVE_RECEIPT),
            terminal_receipt_ref=DRIVE_REF,
            terminal_observed_at_utc="2026-09-27T21:40:16.169Z",
        )
        results["wrong_turn"] = wrong_turn.status
        assert wrong_turn.status == "HOLD_STALE"

        j5 = JsonGateJournal(root / "stale.json")
        assert j5.capture_gate(gate()).status == "CAPTURED_PENDING_ATTEMPT"
        stale = j5.bind_attempt(
            gate_event_ref=EVENT,
            allocation=allocation(
                observed_at_utc="2026-09-27T21:25:00Z"
            ),
            terminal_receipt=parse_kv_receipt(LIVE_RECEIPT),
            terminal_receipt_ref=DRIVE_REF,
            terminal_observed_at_utc="2026-09-27T21:40:16.169Z",
        )
        results["stale_allocation"] = stale.status
        assert stale.status == "HOLD_STALE"

        j6 = JsonGateJournal(root / "changed.json")
        assert j6.capture_gate(gate()).status == "CAPTURED_PENDING_ATTEMPT"
        changed = j6.capture_gate(
            gate(raw_human_trigger="boot full worker")
        )
        results["event_ref_changed_input"] = changed.status
        assert changed.status == "HOLD_GATE_REPLAY_CONFLICT"

        j7 = JsonGateJournal(root / "old-x7.json")
        assert j7.capture_gate(gate()).status == "CAPTURED_PENDING_ATTEMPT"
        old_receipt = parse_kv_receipt(FAILED_X7)
        old_before = copy.deepcopy(old_receipt)
        old_hash = digest(old_receipt)
        old = j7.bind_attempt(
            gate_event_ref=EVENT,
            allocation=allocation(),
            terminal_receipt=old_receipt,
            terminal_receipt_ref="provider:historical-failed-x7-receipt",
            terminal_observed_at_utc="2026-09-27T21:40:16.169Z",
        )
        results["failed_x7_reuse"] = old.status
        assert old.status == "HOLD_TERMINAL"
        assert old_receipt == old_before
        assert digest(old_receipt) == old_hash

        j8 = JsonGateJournal(root / "other-event.json")
        assert j8.capture_gate(gate()).status == "CAPTURED_PENDING_ATTEMPT"
        assert j8.bind_attempt(
            gate_event_ref=EVENT,
            allocation=allocation(),
            terminal_receipt=parse_kv_receipt(LIVE_RECEIPT),
            terminal_receipt_ref=DRIVE_REF,
            terminal_observed_at_utc="2026-09-27T21:40:16.169Z",
        ).status == "BOUND"
        other = gate(
            event_ref="human-message-fixture-002",
            observed_at_utc="2026-09-27T21:27:00Z",
        )
        assert j8.capture_gate(other).status == "CAPTURED_PENDING_ATTEMPT"
        reused_attempt = j8.bind_attempt(
            gate_event_ref=other.event_ref,
            allocation=allocation(),
            terminal_receipt=parse_kv_receipt(LIVE_RECEIPT),
            terminal_receipt_ref=DRIVE_REF,
            terminal_observed_at_utc="2026-09-27T21:40:16.169Z",
        )
        results["attempt_reused_by_other_gate"] = reused_attempt.status
        assert reused_attempt.status == "HOLD_GATE_REPLAY_CONFLICT"

        wrong_trigger = JsonGateJournal(root / "trigger.json").capture_gate(
            gate(raw_human_trigger="@google drive boot researcher")
        )
        results["wrong_human_trigger"] = wrong_trigger.status
        assert wrong_trigger.status == "HOLD_GATE_INPUT"

        return {
            "result": "PASS",
            "tests": len(results),
            "passed": len(results),
            "results": results,
            "live_fixture": {
                "thread_id": THREAD,
                "turn_id": TURN,
                "human_gate_event_ref": EVENT,
                "attempt_allocation_ref": ALLOC_REF,
                "boot_attempt_id": ATTEMPT,
                "terminal_receipt_drive_id": DRIVE_REF.split(":", 1)[1],
                "generation": "NOT_CREATED",
                "first_nonpass_step": "STEP_03",
                "ready": "NO",
            },
            "autonomous_attempt_minting": False,
            "new_boot_event_emission": False,
            "failed_x7_mutated": False,
        }


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True))