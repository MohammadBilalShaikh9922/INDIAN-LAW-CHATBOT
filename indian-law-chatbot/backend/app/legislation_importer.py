
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
    """Return structural validation errors for an Act."""
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
    """Return structural validation errors for a provision."""
    errors = []

    for field in REQUIRED_PROVISION_FIELDS:
        if not str(record.get(field, "")).strip():
            errors.append(f"Missing required provision field: {field}")

    return errors


def load_dataset(file_path: str) -> list[dict[str, Any]]:
    """Load a JSON array containing Act records."""
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


def _register_batch(client: Any, batch_id: str) -> None:
    """Register a batch before importing any legislation records."""
    result = (
        client.table("law_import_batches")
        .insert({
            "id": batch_id,
            "status": "staged",
        })
        .execute()
    )

    if not result.data:
        raise RuntimeError("Could not register the import batch.")


def _finish_batch(
    client: Any,
    batch_id: str,
    status: str,
) -> None:
    """Update the batch status without publishing its records."""
    if status not in {"staged", "partial"}:
        raise ValueError("Invalid import completion status.")

    result = (
        client.table("law_import_batches")
        .update({"status": status})
        .eq("id", batch_id)
        .execute()
    )

    if not result.data:
        raise RuntimeError("Could not update the import batch status.")


def _upsert_act(
    client: Any,
    act: dict[str, Any],
    batch_id: str,
) -> dict[str, Any]:
    """Insert a staged Act or return an existing Act unchanged."""
    source_url = act["source_url"].strip()

    existing = (
        client.table("law_acts")
        .select("id, act_title, status, import_status")
        .eq("source_url", source_url)
        .limit(1)
        .execute()
    )

    if existing.data:
        return {
            **existing.data[0],
            "_already_exists": True,
        }

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
        "source_url": source_url,
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

    return {
        **result.data[0],
        "_already_exists": False,
    }


def _upsert_provision(
    client: Any,
    act_id: Any,
    provision: dict[str, Any],
    default_source_url: str,
    default_language: str,
    batch_id: str,
) -> bool:
    """Insert a staged provision if its label does not already exist."""
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


def import_dataset(
    file_path: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    """
    Validate and optionally import a dataset.

    Real imports are registered in law_import_batches before data writes.
    New records remain staged. This function never publishes legislation.
    """
    records = load_dataset(file_path)

    report: dict[str, Any] = {
        "status": "validated",
        "dry_run": dry_run,
        "import_batch_id": None,
        "acts_seen": len(records),
        "acts_validated": 0,
        "provisions_seen": 0,
        "provisions_validated": 0,
        "provisions_invalid": 0,
        "acts_imported": 0,
        "acts_skipped": 0,
        "provisions_imported": 0,
        "provisions_skipped": 0,
        "errors": [],
        "import_errors": [],
        "publishing_performed": False,
    }

    valid_records = []

    # Validate the entire dataset before database writes.
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
        return report

    if dry_run:
        return report

    client = get_supabase_client()

    if client is None:
        raise RuntimeError(
            "Supabase is not configured. "
            "Check Render environment variables."
        )

    batch_id = str(uuid4())
    report["import_batch_id"] = batch_id

    # Register the batch before inserting any Act or provision.
    _register_batch(client, batch_id)
    report["status"] = "import_in_progress"

    for act in valid_records:
        try:
            saved_act = _upsert_act(
                client=client,
                act=act,
                batch_id=batch_id,
            )

            act_id = saved_act["id"]
            provisions = act.get("provisions", [])

            if saved_act.get("_already_exists"):
                report["acts_skipped"] += 1
            else:
                report["acts_imported"] += 1

            for provision in provisions:
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
                    report["provisions_skipped"] += 1

        except Exception as exc:
            # Do not return database messages or credentials to clients.
            report["import_errors"].append({
                "act_title": act.get("act_title", "Unknown"),
                "error_type": type(exc).__name__,
            })

    final_status = (
        "partial" if report["import_errors"] else "staged"
    )

    try:
        _finish_batch(client, batch_id, final_status)
    except Exception as exc:
        report["import_errors"].append({
            "operation": "batch_status_update",
            "error_type": type(exc).__name__,
        })

    if report["import_errors"]:
        report["status"] = "import_partial_or_failed"
    else:
        report["status"] = "import_completed_staged"

    return report


def preview_dataset(file_path: str) -> dict[str, Any]:
    """Preview an import without writing anything to Supabase."""
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
            "Supabase is not configured. "
            "Check Render environment variables."
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
        source_url = act["source_url"].strip()

        existing = (
            client.table("law_acts")
            .select("id, act_title")
            .eq("source_url", source_url)
            .limit(1)
            .execute()
        )

        provisions = act.get("provisions", [])

        if not existing.data:
            totals["acts_new"] += 1
            totals["provisions_new"] += len(provisions)

            results.append({
                "act_title": act["act_title"],
                "act_exists": False,
                "provisions_in_dataset": len(provisions),
                "provisions_new": len(provisions),
                "provisions_existing": 0,
            })
            continue

        totals["acts_existing"] += 1
        act_id = existing.data[0]["id"]

        existing_provisions = (
            client.table("law_provisions")
            .select("provision_label")
            .eq("act_id", act_id)
            .execute()
        )

        existing_labels = {
            str(row["provision_label"]).strip()
            for row in (existing_provisions.data or [])
        }

        new_count = sum(
            1
            for provision in provisions
            if str(provision["provision_label"]).strip()
            not in existing_labels
        )

        existing_count = len(provisions) - new_count

        totals["provisions_new"] += new_count
        totals["provisions_existing"] += existing_count

        results.append({
            "act_title": act["act_title"],
            "act_exists": True,
            "provisions_in_dataset": len(provisions),
            "provisions_new": new_count,
            "provisions_existing": existing_count,
        })

    return {
        "status": "preview_completed",
        "writes_performed": False,
        "validation": "passed",
        "totals": totals,
        "acts": results,
        "note": (
            "Read-only preview only. Database contents can change "
            "before a later import. Import operations are not atomic."
        ),
    }


def default_dataset_path() -> str:
    """Return the conventional legislation dataset path."""
    return os.path.join(
        os.path.dirname(__file__),
        "data",
        "central_acts.json",
    )
