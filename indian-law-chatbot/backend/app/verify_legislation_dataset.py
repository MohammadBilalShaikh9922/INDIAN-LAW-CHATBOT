
import json
import re
from collections import Counter
from pathlib import Path

DATASET_PATH = (
    Path(__file__).parent / "data" / "central_acts.json"
)


def main():
    try:
        data = json.loads(
            DATASET_PATH.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: Cannot read dataset: {exc}")
        return

    if not isinstance(data, list):
        print("ERROR: Expected the dataset to be a list.")
        return

    print("NYAYAAI DATASET STRUCTURE REPORT")
    print("=" * 42)
    print(f"Acts found: {len(data)}")

    for index, act in enumerate(data, start=1):
        if not isinstance(act, dict):
            print(f"ERROR: Act {index} is not an object.")
            continue

        title = act.get("act_title", "Untitled Act")
        provisions = act.get("provisions", [])

        print(f"\nAct {index}: {title}")
        print(f"Act status in file: {act.get('status', 'missing')}")

        if not isinstance(provisions, list):
            print("ERROR: provisions is not a list.")
            continue

        labels = []
        blank_labels = 0
        blank_headings = 0
        blank_text = 0

        for provision in provisions:
            if not isinstance(provision, dict):
                blank_labels += 1
                continue

            label = str(
                provision.get("provision_label", "")
            ).strip()

            if not label:
                blank_labels += 1
            else:
                labels.append(label)

            if not str(provision.get("heading", "")).strip():
                blank_headings += 1

            if not str(
                provision.get("provision_text", "")
            ).strip():
                blank_text += 1

        counts = Counter(labels)
        duplicates = sorted(
            label for label, count in counts.items()
            if count > 1
        )

        print(f"Provision records: {len(provisions)}")
        print(f"Labels found: {len(labels)}")
        print(f"Unique labels: {len(set(labels))}")
        print(f"Duplicate labels: {duplicates or 'None'}")
        print(f"Blank labels: {blank_labels}")
        print(f"Blank headings: {blank_headings}")
        print(f"Blank provision text: {blank_text}")
        print(f"First labels: {labels[:15]}")
        print(f"Last labels: {labels[-10:]}")

        # Flag obvious label-format anomalies for manual inspection.
        unusual = [
            label for label in labels
            if not re.fullmatch(
                r"\d+[A-Za-z]?", label
            )
        ]
        print(
            "Labels needing manual inspection:",
            unusual[:30] or "None detected"
        )

    print("\n" + "=" * 42)
    print("STRUCTURE CHECK ONLY — NOT LEGAL VERIFICATION.")
    print("No database writes or publishing were performed.")


if __name__ == "__main__":
    main()
