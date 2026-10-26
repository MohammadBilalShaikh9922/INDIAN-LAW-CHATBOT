
"""
NyayaAI legislation importer.

New legislation records are staged and never published automatically.
Existing Acts and provisions are never overwritten.

Structural validation does not establish legal authenticity, accuracy,
completeness, or currentness.

Supabase REST operations are not atomic. Failed imports may leave
staged records that require review.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.database import get_supabase_client


REQUIRED_ACT_FIELDS = {
    "act_title",
    "jurisdiction",
    "instrument_type",
    "source_url",
    "source_name",
}

REQUIRED_PROVISION_FIELDS = {
    "provision_label",
    "provision_text",
}

ALLOWED_JURISDICTIONS = {
    "central",
    "state",
    "union_territory",
}


def validate_act(record: dict[str, Any]) -> list[str]:
    errors = []

    for field in REQUIRED_ACT_FIELDS:
        if not str(record.get(field, "")).strip():
            errors.append(f"Missing required Act field: {field}")

    if record.get("jurisdiction") not in ALLOWED_JURISDICTIONS:
        errors.append(
            "jurisdiction must be central, state, or union_territory"
        )

    source_url = str(record.get("source_url", "")).strip()
    if source_url and not source_url.startswith("https://"):
        errors.append("source_url must use HTTPS")

    provisions = record.get("provisions", [])

    if not isinstance(provisions, list):
        errors.append("provisions must be a JSON array.")
    else:
        seen_labels = set()

        for index, provision in enumerate(provisions):
            if not isinstance(provision, dict):
                errors.append(
                    f"Provision {index} must be a JSON object."
                )
                continue

            label = str(
                provision.get("provision_label", "")
            ).strip()

            if label and label in seen_labels:
                errors.append(
                    f"Duplicate provision label in Act: {label}"
                )

            if label:
                seen_labels.add(label)

    return errors


def validate_provision(record: dict[str, Any]) -> list[str]:
    errors = []

    for field in REQUIRED_PROVISION_FIELDS:
        if not str(record.get(field, "")).strip():
            errors.append(f"Missing required provision field: {field}")

    return errors


def load_dataset(file_path: str) -> list[dict[str, Any]]:
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(f"Dataset file not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError("Dataset root must be a JSON array of Acts.")

    if not all(isinstance(item, dict) for item in data):
        raise ValueError("Every dataset item must be a JSON object.")

    return data


def _register_batch(
    client: Any,
    batch_id: str,
    expected_acts: int,
    expected_provisions: int,
) -> None:
    """Register only records planned for this batch."""
    result = (
        client.table("law_import_batches")
        .insert({
            "id": batch_id,
            "status": "staged",
            "expected_acts": expected_acts,
            "expected_provisions": expected_provisions,
            "imported_acts": 0,
            "imported_provisions": 0,
        })
        .execute()
    )

    if not result.data:
        raise RuntimeError("Could not register the import batch.")


def _finish_batch(
    client: Any,
    batch_id: str,
    status: str,
    imported_acts: int,
    imported_provisions: int,
) -> None:
    """Save actual inserted counts; never publish records here."""
    if status not in {"staged", "partial"}:
        raise ValueError("Invalid import completion status.")

    result = (
        client.table("law_import_batches")
        .update({
            "status": status,
            "imported_acts": imported_acts,
            "imported_provisions": imported_provisions,
        })
        .eq("id", batch_id)
        .execute()
    )

    if not result.data:
        raise RuntimeError("Could not update the import batch.")


def _find_existing_act(
    client: Any,
    source_url: str,
) -> dict[str, Any] | None:
    """Find an existing Act without changing it."""
    result = (
        client.table("law_acts")
        .select("id, act_title, status, import_status, import_batch_id")
        .eq("source_url", source_url.strip())
        .limit(1)
        .execute()
    )

    if result.data:
        return result.data[0]

    return None


def _insert_act(
    client: Any,
    act: dict[str, Any],
    batch_id: str,
) -> dict[str, Any]:
    """Insert a new, unverified, staged Act."""
    now = datetime.now(timezone.utc).isoformat()

    payload = {
        "act_title": act["act_title"].strip(),
        "short_title": act.get("short_title"),
        "act_number": act.get("act_number"),
        "act_year": act.get("act_year"),
        "jurisdiction": act["jurisdiction"],
        "state_or_ut": act.get("state_or_ut"),
        "instrument_type": act["instrument_type"],
        "language": act.get("language", "English"),
        "status": "unverified",
        "import_status": "staged",
        "import_batch_id": batch_id,
        "source_url": act["source_url"].strip(),
        "source_name": act["source_name"].strip(),
        "published_on": act.get("published_on"),
        "effective_from": act.get("effective_from"),
        "effective_to": act.get("effective_to"),
        "created_at": now,
        "updated_at": now,
    }

    result = client.table("law_acts").insert(payload).execute()

    if not result.data:
        raise RuntimeError("Could not insert the Act.")

    return result.data[0]


def _upsert_provision(
    client: Any,
    act_id: Any,
    provision: dict[str, Any],
    default_source_url: str,
    default_language: str,
    batch_id: str,
) -> bool:
    """
    Insert a staged provision if it does not already exist.

    An existing provision is never updated. An unexpected duplicate
    means the batch's actual counts will not match its expected counts.
    """
    label = str(provision["provision_label"]).strip()

    existing = (
        client.table("law_provisions")
        .select("id")
        .eq("act_id", act_id)
        .eq("provision_label", label)
        .limit(1)
        .execute()
    )

    if existing.data:
        return False

    now = datetime.now(timezone.utc).isoformat()

    payload = {
        "act_id": act_id,
        "import_status": "staged",
        "import_batch_id": batch_id,
        "provision_label": label,
        "heading": provision.get("heading"),
        "provision_text": provision["provision_text"].strip(),
        "source_url": (
            provision.get("source_url") or default_source_url
        ),
        "page_number": provision.get("page_number"),
        "language": provision.get("language", default_language),
        "created_at": now,
        "updated_at": now,
    }

    result = client.table("law_provisions").insert(payload).execute()

    if not result.data:
        raise RuntimeError("Could not insert a provision.")

    return True


def _validate_dataset(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Validate every Act and provision before database writes."""
    report: dict[str, Any] = {
        "status": "validated",
        "acts_seen": len(records),
        "acts_validated": 0,
        "provisions_seen": 0,
        "provisions_validated": 0,
        "provisions_invalid": 0,
        "errors": [],
    }

    valid_records = []

    for index, act in enumerate(records):
        errors = validate_act(act)
        provisions = act.get("provisions", [])

        if isinstance(provisions, list):
            report["provisions_seen"] += len(provisions)

            for provision_index, provision in enumerate(provisions):
                if not isinstance(provision, dict):
                    report["provisions_invalid"] += 1
                    errors.append(
                        f"Provision {provision_index} must be an object."
                    )
                    continue

                provision_errors = validate_provision(provision)

                if provision_errors:
                    report["provisions_invalid"] += 1
                    errors.extend(
                        f"Provision {provision_index}: {error}"
                        for error in provision_errors
                    )
                else:
                    report["provisions_validated"] += 1

        if errors:
            report["errors"].append({
                "record_index": index,
                "act_title": act.get("act_title", "Unknown"),
                "messages": errors,
            })
        else:
            valid_records.append(act)

    report["acts_validated"] = len(valid_records)

    if report["errors"]:
        report["status"] = "validation_failed"

    return valid_records, report


def import_dataset(
    file_path: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    """
    Validate and optionally stage new Acts and their provisions.

    Existing Acts are skipped as a whole. Their provisions are not
    inserted into another batch. Publication is never performed here.
    """
    records = load_dataset(file_path)
    valid_records, validation = _validate_dataset(records)

    report: dict[str, Any] = {
        **validation,
        "dry_run": dry_run,
        "import_batch_id": None,
        "acts_imported": 0,
        "acts_skipped": 0,
        "provisions_imported": 0,
        "provisions_skipped": 0,
        "import_errors": [],
        "publishing_performed": False,
    }

    if validation["status"] != "validated":
        return report

    if dry_run:
        return report

    client = get_supabase_client()

    if client is None:
        raise RuntimeError(
            "Supabase is not configured. Check Render environment variables."
        )

    # Plan the batch using Acts that do not already exist.
    # Existing Acts and all their provisions are excluded from this batch.
    new_acts = []

    for act in valid_records:
        existing = _find_existing_act(client, act["source_url"])

        if existing:
            report["acts_skipped"] += 1
            report["provisions_skipped"] += len(act.get("provisions", []))
        else:
            new_acts.append(act)

    expected_acts = len(new_acts)
    expected_provisions = sum(
        len(act.get("provisions", [])) for act in new_acts
    )

    report["expected_acts"] = expected_acts
    report["expected_provisions"] = expected_provisions

    # Do not create an empty batch when everything already exists.
    if not new_acts:
        report["status"] = "no_new_acts"
        report["note"] = (
            "No new Acts were staged. Existing Acts and their provisions "
            "were left unchanged."
        )
        return report

    batch_id = str(uuid4())
    report["import_batch_id"] = batch_id

    _register_batch(
        client=client,
        batch_id=batch_id,
        expected_acts=expected_acts,
        expected_provisions=expected_provisions,
    )

    report["status"] = "import_in_progress"

    for act in new_acts:
        try:
            # Recheck before insertion to reduce the chance of a race.
            # If another import created this Act after planning, skip it
            # and let the final count check fail closed.
            existing = _find_existing_act(client, act["source_url"])

            if existing:
                report["import_errors"].append({
                    "act_title": act.get("act_title", "Unknown"),
                    "error_type": "ActAppearedDuringImport",
                })
                continue

            saved_act = _insert_act(
                client=client,
                act=act,
                batch_id=batch_id,
            )

            report["acts_imported"] += 1
            act_id = saved_act["id"]

            for provision in act.get("provisions", []):
                inserted = _upsert_provision(
                    client=client,
                    act_id=act_id,
                    provision=provision,
                    default_source_url=act["source_url"],
                    default_language=act.get("language", "English"),
                    batch_id=batch_id,
                )

                if inserted:
                    report["provisions_imported"] += 1
                else:
                    report["import_errors"].append({
                        "act_title": act.get("act_title", "Unknown"),
                        "provision_label": provision.get(
                            "provision_label", "Unknown"
                        ),
                        "error_type": "UnexpectedExistingProvision",
                    })

        except Exception as exc:
            # Do not expose database messages or credentials.
            report["import_errors"].append({
                "act_title": act.get("act_title", "Unknown"),
                "error_type": type(exc).__name__,
            })

    # Compare actual inserts against the exact records planned for this
    # batch. Skipped records are deliberately not counted as imported.
    counts_match = (
        report["acts_imported"] == expected_acts
        and report["provisions_imported"] == expected_provisions
    )

    if not counts_match:
        report["import_errors"].append({
            "operation": "completeness_check",
            "error_type": "IncompleteImport",
        })

    final_status = (
        "staged"
        if counts_match and not report["import_errors"]
        else "partial"
    )

    try:
        _finish_batch(
            client=client,
            batch_id=batch_id,
            status=final_status,
            imported_acts=report["acts_imported"],
            imported_provisions=report["provisions_imported"],
        )
    except Exception as exc:
        report["import_errors"].append({
            "operation": "batch_status_update",
            "error_type": type(exc).__name__,
        })
        final_status = "partial"

    report["status"] = (
        "import_completed_staged"
        if final_status == "staged" and not report["import_errors"]
        else "import_partial_or_failed"
    )
    report["publishing_performed"] = False

    return report


def preview_dataset(file_path: str) -> dict[str, Any]:
    """Preview an import without writing to Supabase."""
    validation = import_dataset(file_path=file_path, dry_run=True)

    if validation["status"] != "validated":
        return {
            "status": "validation_failed",
            "writes_performed": False,
            "validation": validation,
        }

    client = get_supabase_client()

    if client is None:
        raise RuntimeError(
            "Supabase is not configured. Check Render environment variables."
        )

    records = load_dataset(file_path)
    results = []

    totals = {
        "acts_new": 0,
        "acts_existing": 0,
        "provisions_new": 0,
        "provisions_existing": 0,
    }

    for act in records:
        existing = _find_existing_act(client, act["source_url"])
        provisions = act.get("provisions", [])

        if not existing:
            totals["acts_new"] += 1
            totals["provisions_new"] += len(provisions)

            results.append({
                "act_title": act["act_title"],
                "act_exists": False,
                "provisions_in_dataset": len(provisions),
                "provisions_new": len(provisions),
                "provisions_existing": 0,
                "action": "would_stage",
            })
            continue

        totals["acts_existing"] += 1

        existing_provisions = (
            client.table("law_provisions")
            .select("provision_label")
            .eq("act_id", existing["id"])
            .execute()
        )

        existing_labels = {
            str(row["provision_label"]).strip()
            for row in (existing_provisions.data or [])
        }

        # Existing Acts are skipped as a whole, so none of their
        # provisions will be inserted by this dataset import.
        totals["provisions_existing"] += len(provisions)

        results.append({
            "act_title": act["act_title"],
            "act_exists": True,
            "provisions_in_dataset": len(provisions),
            "provisions_new": 0,
            "provisions_existing": len(provisions),
            "database_provisions_found": len(existing_labels),
            "action": "skip_existing_act",
        })

    return {
        "status": "preview_completed",
        "writes_performed": False,
        "validation": "passed",
        "totals": totals,
        "acts": results,
        "note": (
            "Read-only preview. Existing Acts are skipped together with "
            "their dataset provisions. Database contents may change before "
            "a later import. Import operations are not atomic."
        ),
    }


def default_dataset_path() -> str:
    """Return the conventional legislation dataset path."""
    return os.path.join(
        os.path.dirname(__file__),
        "data",
        "central_acts.json",
    )
