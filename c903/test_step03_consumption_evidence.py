import copy
import unittest

from step03_consumption_evidence import (
    SCHEMA, UNBOUND_SCOPE, compile_required_membership, load_snapshot,
    make_evidence, semantic_fingerprint, snapshot_binding, validate_execution,
)

HEADER = [
    "OVERLAY_ID","SCOPE","REQUIREMENT","STATE","AUTHORITY_CLASS",
    "BASIS","APPLIES_TO","EFFECTIVE_FROM_SHARED_REVISION",
    "SUPERSEDES","SOURCE_PROMOTION_TARGET","NOTES",
]

def fixture_snapshot():
    return {
        "provider":{"spreadsheet_id":"fixture","sheet":"PRE_SOURCE_OVERLAY","range":"A1:K5","frontier_row":5},
        "values":[
            HEADER,
            ["PSO-BOOT-A","GLOBAL_BOOT","A","ACTIVE_REQUIRED","A","B","ALL_CEREBRO_BOOTS","1","","",""],
            ["PSO-WORKER-B","WORKER_ONLY","B","ACTIVE_REQUIRED","A","B","WORKER","1","","",""],
            ["PSO-BOOT-C","GLOBAL_BOOT","C","ACTIVE_FAIL_CLOSED","A","B","BOOT","2","PSO-OLD-C","",""],
            ["PSO-OLD-C","LEGACY","OLD","RETIRED_BY_HUMAN","A","B","WORKER","0","","",""],
        ],
    }

def fixture_execution(snapshot):
    return {
        "schema":SCHEMA,
        "execution_id":"EXEC-C903-FIXTURE",
        "boot_attempt_id":"CEREBRO-BOOT-FIXTURE",
        "snapshot_sha256":snapshot_binding(snapshot)["snapshot_sha256"],
        "scope_resolution":copy.deepcopy(UNBOUND_SCOPE),
        "scope_selector_source":"CONSUMER_SEMANTIC_EVALUATION",
        "consumer_impl_ref":"fixture:step03-consumer@1",
    }

def genuine_evidence(snapshot, execution):
    rows = {r["OVERLAY_ID"]:r for r in load_snapshot(snapshot)}
    return [
        make_evidence(execution, rows["PSO-BOOT-A"], "APPLICABLE", "ALL_CEREBRO_BOOTS"),
        make_evidence(execution, rows["PSO-WORKER-B"], "NOT_APPLICABLE", "UNBOUND_HAS_NO_WORKER_ROLE"),
        make_evidence(execution, rows["PSO-BOOT-C"], "APPLICABLE", "BOOT_CONTEXT", "REFINE"),
    ]

class Step03ConsumptionEvidenceTests(unittest.TestCase):
    def test_compiler_membership_is_not_consumption(self):
        compiled = compile_required_membership(fixture_snapshot())
        self.assertEqual(compiled["required_active_count"], 3)
        self.assertEqual(compiled["consumption_status"], "NOT_EXECUTED")
        self.assertEqual(compiled["consumed_ids"], [])

    def test_positive_genuine_consumer_evidence(self):
        snapshot = fixture_snapshot()
        execution = fixture_execution(snapshot)
        evidence = genuine_evidence(snapshot, execution)
        self.assertEqual(validate_execution(snapshot, execution, evidence), [])

    def test_missing_or_skipped_semantics_fail_closed(self):
        snapshot = fixture_snapshot()
        execution = fixture_execution(snapshot)
        evidence = genuine_evidence(snapshot, execution)[:-1]
        errors = validate_execution(snapshot, execution, evidence)
        self.assertTrue(any(x.startswith("ACTIVE_ROW_EVIDENCE_MISSING:") for x in errors))

    def test_false_consumption_from_manifest_or_assertion_fails(self):
        snapshot = fixture_snapshot()
        execution = fixture_execution(snapshot)
        evidence = genuine_evidence(snapshot, execution)
        rows = {r["OVERLAY_ID"]:r for r in load_snapshot(snapshot)}
        evidence[0]["evidence_origin"] = "CALLER_ASSERTION"
        evidence[0]["semantic_fingerprint"] = semantic_fingerprint(execution, rows["PSO-BOOT-A"], evidence[0])
        errors = validate_execution(snapshot, execution, evidence)
        self.assertIn("FALSE_CONSUMPTION_ORIGIN:PSO-BOOT-A", errors)

    def test_stale_snapshot_or_revision_fails(self):
        snapshot = fixture_snapshot()
        execution = fixture_execution(snapshot)
        execution["snapshot_sha256"] = "0" * 64
        errors = validate_execution(snapshot, execution, genuine_evidence(snapshot, fixture_execution(snapshot)))
        self.assertIn("STALE_SNAPSHOT_OR_REVISION", errors)

    def test_contradictory_supersession_fails(self):
        snapshot = fixture_snapshot()
        execution = fixture_execution(snapshot)
        evidence = genuine_evidence(snapshot, execution)
        rows = {r["OVERLAY_ID"]:r for r in load_snapshot(snapshot)}
        evidence[2]["supersession_resolution"] = "CONFLICT"
        evidence[2]["semantic_fingerprint"] = semantic_fingerprint(execution, rows["PSO-BOOT-C"], evidence[2])
        errors = validate_execution(snapshot, execution, evidence)
        self.assertIn("CONTRADICTORY_SUPERSESSION:PSO-BOOT-C", errors)

    def test_wrong_unbound_scope_fails(self):
        snapshot = fixture_snapshot()
        execution = fixture_execution(snapshot)
        evidence = genuine_evidence(snapshot, execution)
        execution["scope_resolution"] = dict(UNBOUND_SCOPE, profile_requested="WORKER")
        errors = validate_execution(snapshot, execution, evidence)
        self.assertIn("WRONG_UNBOUND_SCOPE", errors)

    def test_duplicate_overlay_rows_fail(self):
        snapshot = fixture_snapshot()
        snapshot["values"].insert(3, copy.deepcopy(snapshot["values"][1]))
        execution = fixture_execution(snapshot)
        errors = validate_execution(snapshot, execution, [])
        self.assertEqual(errors, ["DUPLICATE_OVERLAY_ID"])

    def test_unknown_applicability_blocks(self):
        snapshot = fixture_snapshot()
        execution = fixture_execution(snapshot)
        evidence = genuine_evidence(snapshot, execution)
        rows = {r["OVERLAY_ID"]:r for r in load_snapshot(snapshot)}
        evidence[1]["applicability"] = "UNKNOWN"
        evidence[1]["semantic_disposition"] = "NOT_APPLICABLE"
        evidence[1]["semantic_fingerprint"] = semantic_fingerprint(execution, rows["PSO-WORKER-B"], evidence[1])
        errors = validate_execution(snapshot, execution, evidence)
        self.assertIn("UNKNOWN_APPLICABILITY_BLOCKS_STEP03:PSO-WORKER-B", errors)

if __name__ == "__main__":
    unittest.main(verbosity=2)
