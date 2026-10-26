
"""
NyayaAI legislation importer.

Imports verified Indian legislation metadata and provision text
from a prepared JSON dataset into Supabase.

This module does not scrape India Code or assume that a URL alone
proves the contents are authentic. Dataset records must include
official source details and actual provision text.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


def validate_act(record: dict[str, Any]) -> list[str]:
    """Return validation errors for an Act record."""
    errors = []

    for field in REQUIRED_ACT_FIELDS:
        if not str(record.get(field, "")).strip():
            errors.append(f"Missing required Act field: {field}")

    if record.get("jurisdiction") not in {
        "central",
        "state",
        "union_territory",
    }:
        errors.append(
            "jurisdiction must be central, state, or union_territory"
        )

    source_url = str(record.get("source_url", "")).strip()
    if source_url and not source_url.startswith("https://"):
        errors.append("source_url must use HTTPS")

    return errors


def validate_provision(record: dict[str, Any]) -> list[str]:
    """Return validation errors for a provision record."""
    errors = []

    for field in REQUIRED_PROVISION_FIELDS:
        if not str(record.get(field, "")).strip():
            errors.append(f"Missing required provision field: {field}")

    return errors


def load_dataset(file_path: str) -> list[dict[str, Any]]:
    """Load a JSON array of legislation records."""
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(
            f"Dataset file not found: {path}"
        )

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError(
            "Dataset root must be a JSON array of Acts."
        )

    if not all(isinstance(item, dict) for item in data):
        raise ValueError(
            "Every dataset item must be a JSON object."
        )

    return data



def _upsert_act(client: Any, act: dict[str, Any]) -> dict[str, Any]:
    """Insert a new Act, or return the existing Act without modifying it."""
    source_url = act["source_url"].strip()

    existing = (
        client.table("law_acts")
        .select("id, act_title, status")
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
        "source_url": source_url,
        "source_name": act["source_name"].strip(),
        "published_on": act.get("published_on"),
        "effective_from": act.get("effective_from"),
        "effective_to": act.get("effective_to"),
        "updated_at": now,
        "created_at": now,
    }

    # Do not set last_verified_at during import.
    result = client.table("law_acts").insert(payload).execute()

    if not result.data:
        raise RuntimeError(
            f"Could not insert Act: {payload['act_title']}"
        )

    return {
        **result.data[0],
        "_already_exists": False,
    }


    # Use the official source URL as a lookup key to avoid inserting
    # the same Act again when it has already been imported.
    existing = (
        client.table("law_acts")
        .select("id")
        .eq("source_url", payload["source_url"])
        .limit(1)
        .execute()
    )

    if existing.data:
        act_id = existing.data[0]["id"]
        result = (
            client.table("law_acts")
            .update(payload)
            .eq("id", act_id)
            .execute()
        )
        if not result.data:
            raise RuntimeError(
                f"Could not update Act: {payload['act_title']}"
            )
        return result.data[0]

    payload["created_at"] = now
    result = client.table("law_acts").insert(payload).execute()

    if not result.data:
        raise RuntimeError(
            f"Could not insert Act: {payload['act_title']}"
        )

    return result.data[0]


def _upsert_provision(
    client: Any,
    act_id: Any,
    provision: dict[str, Any],
    default_source_url: str,
    default_language: str,
) -> None:
    """Insert or update a provision by Act ID and provision label."""
    now = datetime.now(timezone.utc).isoformat()
    label = str(provision["provision_label"]).strip()

    payload = {
        "act_id": act_id,
        "provision_label": label,
        "heading": provision.get("heading"),
        "provision_text": provision["provision_text"].strip(),
        "source_url": (
            provision.get("source_url") or default_source_url
        ),
        "page_number": provision.get("page_number"),
        "language": provision.get("language", default_language),
        "updated_at": now,
    }

    existing = (
        client.table("law_provisions")
        .select("id")
        .eq("act_id", act_id)
        .eq("provision_label", label)
        .limit(1)
        .execute()
    )

    if existing.data:
        (
            client.table("law_provisions")
            .update(payload)
            .eq("id", existing.data[0]["id"])
            .execute()
        )
    else:
        payload["created_at"] = now
        client.table("law_provisions").insert(payload).execute()


def import_dataset(
    file_path: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    """
    Validate and optionally import a JSON dataset.

    dry_run=True validates the data without writing to Supabase.
    """
    records = load_dataset(file_path)

    
    report: dict[str, Any] = {
        "status": "validated",
        "dry_run": dry_run,
        "acts_seen": len(records),
        "acts_validated": 0,
        "provisions_seen": sum(
            len(act.get("provisions", []))
            for act in records
            if isinstance(act.get("provisions", []), list)
        ),
        "provisions_validated": 0,
        "provisions_invalid": 0,
        "acts_imported": 0,
        "provisions_imported": 0,
        "errors": [],
    }


    valid_records = []

    for index, act in enumerate(records):
        errors = validate_act(act)

        provisions = act.get("provisions", [])
        if not isinstance(provisions, list):
            errors.append("provisions must be a JSON array.")
            provisions = []

        
        for provision_index, provision in enumerate(provisions):
            if not isinstance(provision, dict):
                errors.append(
                    f"Provision {provision_index} must be an object."
                )
                report["provisions_invalid"] += 1
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
            "Supabase is not configured. Check Render environment variables."
        )

    for act in valid_records:
        saved_act = _upsert_act(client, act)
        report["acts_imported"] += 1

        for provision in act.get("provisions", []):
            _upsert_provision(
                client=client,
                act_id=saved_act["id"],
                provision=provision,
                default_source_url=act["source_url"],
                default_language=act.get("language", "English"),
            )
            report["provisions_imported"] += 1

    report["status"] = "import_completed"
    return report


def default_dataset_path() -> str:
    """Return the conventional dataset path."""
    return os.path.join(
        os.path.dirname(__file__),
        "data",
        "central_acts.json",
    )
