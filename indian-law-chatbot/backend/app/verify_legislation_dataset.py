
import json
import re
from collections import Counter
from pathlib import Path


DATASET_PATH = Path(__file__).parent / "data" / "central_acts.json"


def main():
    if not DATASET_PATH.exists():
        print(f"ERROR: Dataset not found: {DATASET_PATH}")
        return

    try:
        data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: Could not read dataset: {exc}")
        return

    acts = data.get("acts", []) if isinstance(data, dict) else data

    if not isinstance(acts, list):
        print("ERROR: Expected a list of Acts.")
        return

    print("NYAYAAI DATASET STRUCTURE REPORT")
    print("=" * 40)
    print(f"Dataset: {DATASET_PATH.name}")
    print(f"Acts found: {len(acts)}")

    for act_index, act in enumerate(acts, start=1):
        if not isinstance(act, dict):
            print(f"ERROR: Act entry {act_index} is not an object.")
            continue

        title = act.get("title", act.get("name", "Untitled Act"))
        provisions = act.get(
            "provisions",
            act.get("sections", [])
        )

        if not isinstance(provisions, list):
            print(f"ERROR: Provisions for {title} are not a list.")
            continue

        print(f"\nAct {act_index}: {title}")
        print(f"Provision records: {len(provisions)}")

        labels = []
        for provision in provisions:
            if not isinstance(provision, dict):
                continue

            label = provision.get(
                "section_number",
                provision.get(
                    "section",
                    provision.get("number", "")
                )
            )
            if label != "":
                labels.append(str(label).strip())

        counts = Counter(labels)
        duplicates = sorted(
            label for label, count in counts.items() if count > 1
        )

        print(f"Records with section labels: {len(labels)}")
        print(f"Unique section labels: {len(set(labels))}")
        print(f"Duplicate labels: {duplicates or 'None detected'}")

        missing_labels = [
            index for index, label in enumerate(labels, start=1)
            if not label
        ]
        print(f"Blank section labels: {len(missing_labels)}")

        print("Sample labels:", labels[:15])
        print("Final labels:", labels[-10:])

    print("\n" + "=" * 40)
    print("This report checks structure only.")
    print("It does NOT verify legal accuracy or current law.")
    print("It does NOT modify the database or publish anything.")


if __name__ == "__main__":
    main()
