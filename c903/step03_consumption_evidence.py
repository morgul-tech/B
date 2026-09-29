import hashlib
import json

SCHEMA = "cerebro.boot.step03-consumption-evidence/v1-candidate"
EXPECTED_HEADER = [
    "OVERLAY_ID","SCOPE","REQUIREMENT","STATE","AUTHORITY_CLASS",
    "BASIS","APPLIES_TO","EFFECTIVE_FROM_SHARED_REVISION",
    "SUPERSEDES","SOURCE_PROMOTION_TARGET","NOTES",
]
UNBOUND_SCOPE = {
    "profile_requested":"UNBOUND","profile_effective":"NONE","workform":"NONE",
    "role_requested":"NONE","role_bound":"NONE","project":"NONE",
    "assignment":"NONE","pool_member":"NO","boot_context":"BOOT_CEREBRO",
}
ALLOWED_APPLICABILITY = {"APPLICABLE","NOT_APPLICABLE","UNKNOWN"}
ALLOWED_SUPERSESSION = {"NONE","COMPOSE","REFINE","REPLACE_IN_SCOPE","NO_CURRENT_TARGET","CONFLICT"}
ALLOWED_APPLICABLE_DISPOSITIONS = {"CONSUMED_ENFORCED","CONSUMED_NO_EFFECT"}

def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",",":")).encode("utf-8")

def sha256(value):
    raw = value if isinstance(value, bytes) else _canonical(value)
    return hashlib.sha256(raw).hexdigest()

def normalize_cells(cells):
    values = [str(x) for x in list(cells or [])]
    return (values + [""] * 11)[:11]

def load_snapshot(snapshot):
    values = snapshot.get("values")
    if not isinstance(values, list) or not values:
        raise ValueError("SNAPSHOT_VALUES_REQUIRED")
    if normalize_cells(values[0]) != EXPECTED_HEADER:
        raise ValueError("SNAPSHOT_HEADER_MISMATCH")
    rows = []
    for provider_row, cells in enumerate(values[1:], start=2):
        c = normalize_cells(cells)
        if not c[0].strip():
            continue
        row = dict(zip(EXPECTED_HEADER, c))
        row["provider_row"] = provider_row
        row["row_sha256"] = sha256({"provider_row":provider_row,"cells":c})
        rows.append(row)
    ids = [r["OVERLAY_ID"] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("DUPLICATE_OVERLAY_ID")
    return rows

def snapshot_binding(snapshot):
    physical = [
        {"provider_row":i,"cells":normalize_cells(c)}
        for i,c in enumerate(snapshot["values"], start=1)
    ]
    return {
        "provider":snapshot.get("provider",{}),
        "snapshot_sha256":sha256(physical),
        "physical_rows_returned":len(snapshot["values"]),
    }

def compile_required_membership(snapshot):
    rows = load_snapshot(snapshot)
    active = [r for r in rows if r["STATE"].startswith("ACTIVE_")]
    return {
        "schema":"cerebro.boot.step03-required-membership/v1-candidate",
        "binding":snapshot_binding(snapshot),
        "required_active_rows":[
            {"provider_row":r["provider_row"],"overlay_id":r["OVERLAY_ID"],"row_sha256":r["row_sha256"]}
            for r in active
        ],
        "required_active_count":len(active),
        "consumption_status":"NOT_EXECUTED",
        "consumed_ids":[],
    }

def supersession_field_hash(row):
    return sha256({"SUPERSEDES":row["SUPERSEDES"]})

def semantic_fingerprint(execution, row, evidence):
    return sha256({
        "execution_id":execution["execution_id"],
        "boot_attempt_id":execution["boot_attempt_id"],
        "snapshot_sha256":execution["snapshot_sha256"],
        "provider_row":row["provider_row"],
        "overlay_id":row["OVERLAY_ID"],
        "row_sha256":row["row_sha256"],
        "scope_resolution":execution["scope_resolution"],
        "applicability":evidence["applicability"],
        "applicability_basis":evidence["applicability_basis"],
        "supersession_resolution":evidence["supersession_resolution"],
        "supersession_basis_sha256":evidence["supersession_basis_sha256"],
        "semantic_disposition":evidence["semantic_disposition"],
        "evidence_origin":evidence["evidence_origin"],
    })

def validate_execution(snapshot, execution, evidence_rows):
    errors = []
    try:
        rows = load_snapshot(snapshot)
    except ValueError as exc:
        return [str(exc)]
    binding = snapshot_binding(snapshot)
    if execution.get("schema") != SCHEMA:
        errors.append("EXECUTION_SCHEMA_MISMATCH")
    if execution.get("snapshot_sha256") != binding["snapshot_sha256"]:
        errors.append("STALE_SNAPSHOT_OR_REVISION")
    if execution.get("scope_resolution") != UNBOUND_SCOPE:
        errors.append("WRONG_UNBOUND_SCOPE")
    if execution.get("scope_selector_source") == "GENERIC_WORKER_SELECTOR":
        errors.append("GENERIC_WORKER_SELECTOR_REUSE_PROHIBITED")
    if not execution.get("execution_id"):
        errors.append("EXECUTION_ID_REQUIRED")
    if not execution.get("consumer_impl_ref"):
        errors.append("CONSUMER_IMPLEMENTATION_REF_REQUIRED")
    by_id = {r["OVERLAY_ID"]:r for r in rows}
    active = [r for r in rows if r["STATE"].startswith("ACTIVE_")]
    seen = set()
    for ev in evidence_rows:
        oid = ev.get("overlay_id")
        if oid in seen:
            errors.append("DUPLICATE_EVIDENCE_ROW:"+str(oid))
            continue
        seen.add(oid)
        row = by_id.get(oid)
        if row is None:
            errors.append("UNKNOWN_EVIDENCE_OVERLAY_ID:"+str(oid))
            continue
        if not row["STATE"].startswith("ACTIVE_"):
            errors.append("NONACTIVE_ROW_CLAIMED_EXECUTED:"+oid)
        if ev.get("provider_row") != row["provider_row"]:
            errors.append("ROW_BINDING_MISMATCH:"+oid)
        if ev.get("row_sha256") != row["row_sha256"]:
            errors.append("ROW_HASH_MISMATCH:"+oid)
        app = ev.get("applicability")
        if app not in ALLOWED_APPLICABILITY:
            errors.append("APPLICABILITY_VALUE_INVALID:"+oid)
        basis = ev.get("applicability_basis")
        if not isinstance(basis, dict) or not basis:
            errors.append("APPLICABILITY_BASIS_REQUIRED:"+oid)
        else:
            if basis.get("scope_resolution") != UNBOUND_SCOPE:
                errors.append("ROW_UNBOUND_BASIS_MISMATCH:"+oid)
            if basis.get("decision_source") in {"MANIFEST_MEMBERSHIP","SHEET_READ_ONLY","CALLER_ASSERTION"}:
                errors.append("FALSE_APPLICABILITY_BASIS:"+oid)
        sup = ev.get("supersession_resolution")
        if sup not in ALLOWED_SUPERSESSION:
            errors.append("SUPERSESSION_RESOLUTION_REQUIRED:"+oid)
        if ev.get("supersession_basis_sha256") != supersession_field_hash(row):
            errors.append("SUPERSESSION_BASIS_MISMATCH:"+oid)
        if sup == "CONFLICT":
            errors.append("CONTRADICTORY_SUPERSESSION:"+oid)
        if ev.get("evidence_origin") != "CONSUMER_EXECUTION":
            errors.append("FALSE_CONSUMPTION_ORIGIN:"+oid)
        disp = ev.get("semantic_disposition")
        if app == "APPLICABLE" and disp not in ALLOWED_APPLICABLE_DISPOSITIONS:
            errors.append("APPLICABLE_ROW_NOT_CONSUMED:"+oid)
        elif app == "NOT_APPLICABLE" and disp != "NOT_APPLICABLE":
            errors.append("NOT_APPLICABLE_DISPOSITION_MISMATCH:"+oid)
        elif app == "UNKNOWN":
            errors.append("UNKNOWN_APPLICABILITY_BLOCKS_STEP03:"+oid)
        if ev.get("semantic_fingerprint") != semantic_fingerprint(execution,row,ev):
            errors.append("SEMANTIC_FINGERPRINT_MISMATCH:"+oid)
    active_ids = {r["OVERLAY_ID"] for r in active}
    missing = sorted(active_ids-seen)
    if missing:
        errors.append("ACTIVE_ROW_EVIDENCE_MISSING:"+",".join(missing))
    extra = sorted(seen-active_ids)
    if extra:
        errors.append("NONACTIVE_OR_UNKNOWN_EVIDENCE_PRESENT:"+",".join(extra))
    return errors

def make_evidence(execution, row, applicability, reason_code,
                  supersession_resolution="NONE", semantic_disposition=None):
    if semantic_disposition is None:
        semantic_disposition = "CONSUMED_NO_EFFECT" if applicability == "APPLICABLE" else "NOT_APPLICABLE"
    ev = {
        "provider_row":row["provider_row"],
        "overlay_id":row["OVERLAY_ID"],
        "row_sha256":row["row_sha256"],
        "applicability":applicability,
        "applicability_basis":{
            "scope_resolution":UNBOUND_SCOPE,
            "decision_source":"CONSUMER_SEMANTIC_EVALUATION",
            "reason_code":reason_code,
            "applies_to_raw_sha256":sha256({"APPLIES_TO":row["APPLIES_TO"]}),
        },
        "supersession_resolution":supersession_resolution,
        "supersession_basis_sha256":supersession_field_hash(row),
        "semantic_disposition":semantic_disposition,
        "evidence_origin":"CONSUMER_EXECUTION",
    }
    ev["semantic_fingerprint"] = semantic_fingerprint(execution,row,ev)
    return ev
