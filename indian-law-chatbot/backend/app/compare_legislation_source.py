
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader

APP_DIR = Path(__file__).resolve().parent
DATASET_PATH = APP_DIR / "data" / "central_acts.json"
REPORT_PATH = APP_DIR / "legislation_source_comparison_report.md"

OFFICIAL_PDF_URL = (
    "https://upload.indiacode.nic.in/showfile?"
    "actid=AC_CEN_45_76_00001_200021_1517807324077"
    "&filename=a2000-21.pdf&type=actfile"
)


def normalize_text(value):
    """Normalize text for preliminary comparison only."""
    return re.sub(r"[^a-z0-9]", "", value.lower())



def download_official_pdf():
    import time
    import urllib.error

    last_error = None

    for attempt in range(1, 4):
        try:
            request = urllib.request.Request(
                OFFICIAL_PDF_URL,
                headers={
                    "User-Agent": "Mozilla/5.0 NyayaAI-Legislation-Audit/1.0",
                    "Accept": "application/pdf,*/*",
                    "Connection": "close",
                },
            )

            with urllib.request.urlopen(
                request,
                timeout=120,
            ) as response:
                content_type = response.headers.get(
                    "Content-Type", ""
                )
                pdf_bytes = response.read()

            if not pdf_bytes.startswith(b"%PDF"):
                raise ValueError(
                    "The source URL did not return PDF content. "
                    f"Content-Type: {content_type}"
                )

            print(
                f"Official PDF downloaded successfully "
                f"on attempt {attempt}."
            )
            return pdf_bytes

        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            print(
                f"PDF download attempt {attempt}/3 failed: {exc}"
            )

            if attempt < 3:
                time.sleep(5 * attempt)

    raise RuntimeError(
        "Could not download the official PDF after 3 attempts. "
        "The comparison was not completed. "
        f"Last error: {last_error}"
    )


def main():
    if not DATASET_PATH.exists():
        raise FileNotFoundError(
            f"Dataset not found: {DATASET_PATH}"
        )

    with DATASET_PATH.open("r", encoding="utf-8") as file:
        dataset = json.load(file)

    if not isinstance(dataset, list) or not dataset:
        raise ValueError("Expected a non-empty JSON list of Acts.")

    pdf_bytes = download_official_pdf()

    import io

    reader = PdfReader(io.BytesIO(pdf_bytes))

    if reader.is_encrypted:
        raise ValueError(
            "The downloaded PDF is encrypted; manual review is needed."
        )

    pdf_text = "\n".join(
        page.extract_text() or "" for page in reader.pages
    )
    normalized_pdf = normalize_text(pdf_text)

    if not normalized_pdf:
        raise ValueError(
            "No searchable text could be extracted from the PDF."
        )

    lines = [
        "# NyayaAI — Preliminary Legislation Source Comparison",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        f"Official source: {OFFICIAL_PDF_URL}",
        "",
        f"PDF pages: {len(reader.pages)}",
        "",
        "> IMPORTANT: This is an automated text-presence check, "
        "not legal verification. A match does not prove accuracy, "
        "completeness, currency, or legal validity. A missing match "
        "may result from PDF extraction or formatting differences.",
        "",
    ]

    total = 0
    matches = 0
    review_items = 0

    for act_index, act in enumerate(dataset, start=1):
        if not isinstance(act, dict):
            lines.append(
                f"- REVIEW: Dataset entry {act_index} is not an object."
            )
            review_items += 1
            continue

        act_name = act.get("act_name") or act.get("title") or "Unnamed Act"
        provisions = act.get("provisions", [])

        lines.extend(
            [
                f"## {act_name}",
                "",
                f"Dataset source URL: {act.get('source_url', 'MISSING')}",
                "",
            ]
        )

        if not isinstance(provisions, list):
            lines.extend(
                ["**REVIEW:** `provisions` is not a list.", ""]
            )
            review_items += 1
            continue

        lines.extend(
            [
                "| Label | Heading | Text snippet found | Result |",
                "|---|---|---|---|",
            ]
        )

        for provision in provisions:
            total += 1

            if not isinstance(provision, dict):
                lines.append(
                    f"| Entry {total} | Invalid record | No | REVIEW |"
                )
                review_items += 1
                continue

            label = str(provision.get("provision_label", "")).strip()
            heading = str(provision.get("heading", "")).strip()
            text = str(provision.get("provision_text", "")).strip()

            if not label or not heading or not text:
                lines.append(
                    f"| {label or 'MISSING'} | "
                    f"{heading or 'MISSING'} | No | REVIEW |"
                )
                review_items += 1
                continue

            # A short opening excerpt reduces false negatives caused
            # by footnotes or formatting differences later in a section.
            excerpt = normalize_text(text[:180])

            found = bool(excerpt) and excerpt in normalized_pdf

            if found:
                matches += 1
                result = "MATCH — inspect manually"
                found_text = "Yes"
            else:
                review_items += 1
                result = "REVIEW — snippet not located"
                found_text = "No"

            safe_label = label.replace("|", "\\|")
            safe_heading = heading.replace("|", "\\|").replace("\n", " ")

            lines.append(
                f"| {safe_label} | {safe_heading} | "
                f"{found_text} | {result} |"
            )

        lines.append("")

    lines.extend(
        [
            "## Summary",
            "",
            f"- Provision records checked: {total}",
            f"- Opening snippets located: {matches}",
            f"- Items requiring review: {review_items}",
            "",
            "## Required manual checks",
            "",
            "- Compare full provision wording against the official PDF.",
            "- Check amendments, footnotes and inserted sections.",
            "- Check applicable commencement and amendment dates.",
            "- Review schedules and any content absent from the dataset.",
            "- Confirm the current law using authoritative sources.",
            "",
            "No database writes or publication actions were performed.",
            "",
        ]
    )

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")

    print("PRELIMINARY COMPARISON REPORT GENERATED")
    print(f"Acts in dataset: {len(dataset)}")
    print(f"Provisions checked: {total}")
    print(f"Opening snippets located: {matches}")
    print(f"Items requiring review: {review_items}")
    print(f"Report: {REPORT_PATH}")
    print("No database writes or publication actions were performed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
