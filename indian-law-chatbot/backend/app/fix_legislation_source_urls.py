
import json
import sys
from pathlib import Path

OFFICIAL_SOURCE_URL = (
    "https://upload.indiacode.nic.in/showfile?"
    "actid=AC_CEN_45_76_00001_200021_1517807324077"
    "&filename=a2000-21.pdf&type=actfile"
)

OLD_SOURCE_URL = "https://www.indiacode.gov.in/"

DATASET_PATH = (
    Path(__file__).parent / "data" / "central_acts.json"
)


def main():
    if not DATASET_PATH.exists():
        print(f"ERROR: Dataset not found: {DATASET_PATH}")
        sys.exit(1)

    try:
        with DATASET_PATH.open("r", encoding="utf-8") as file:
            dataset = json.load(file)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: Could not read dataset: {exc}")
        sys.exit(1)

    if not isinstance(dataset, list):
        print("ERROR: Expected the dataset to be a JSON list.")
        sys.exit(1)

    provisions_checked = 0
    urls_fixed = 0

    for act in dataset:
        if not isinstance(act, dict):
            continue

        # Correct the Act-level URL if it uses the old homepage.
        if act.get("source_url") == OLD_SOURCE_URL:
            act["source_url"] = OFFICIAL_SOURCE_URL
            urls_fixed += 1

        provisions = act.get("provisions", [])

        if not isinstance(provisions, list):
            print(
                "ERROR: Invalid provisions list for:",
                act.get("act_name", act.get("title", "Unknown Act")),
            )
            sys.exit(1)

        for provision in provisions:
            if not isinstance(provision, dict):
                continue

            provisions_checked += 1

            if provision.get("source_url") == OLD_SOURCE_URL:
                provision["source_url"] = OFFICIAL_SOURCE_URL
                urls_fixed += 1

    # Validate the serialized JSON before writing.
    try:
        serialized = json.dumps(
            dataset,
            ensure_ascii=False,
            indent=2,
        )
        json.loads(serialized)
    except (TypeError, ValueError) as exc:
        print(f"ERROR: JSON validation failed: {exc}")
        sys.exit(1)

    if urls_fixed == 0:
        print("No matching old URLs were found.")
        print("No changes were written.")
        print(f"Provisions checked: {provisions_checked}")
        return

    try:
        DATASET_PATH.write_text(
            serialized + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        print(f"ERROR: Could not write dataset: {exc}")
        sys.exit(1)

    print("SOURCE URL CORRECTION COMPLETE")
    print(f"Provisions checked: {provisions_checked}")
    print(f"URLs corrected: {urls_fixed}")
    print(f"Dataset: {DATASET_PATH}")
    print("Legal provision text was not intentionally modified.")
    print("Review the changes before committing or importing.")


if __name__ == "__main__":
    main()
