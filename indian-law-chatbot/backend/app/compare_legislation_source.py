
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader


# --------------------------------------------------
# Paths and source information
# --------------------------------------------------

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"

DATASET_PATH = DATA_DIR / "central_acts.json"
OFFICIAL_PDF_PATH = DATA_DIR / "it_act_2000_as_on_2025-06-27.pdf"
REPORT_PATH = APP_DIR / "legislation_source_comparison_report.md"

OFFICIAL_PDF_URL = (
    "https://upload.indiacode.nic.in/showfile?"
    "actid=AC_CEN_45_76_00001_200021_1517807324077"
    "&filename=a2000-21.pdf&type=actfile"
)

PDF_VERSION_DESCRIPTION = (
    "Original PDF supplied for comparison; cover states "
    "'As on the 27th June, 2025'."
)


# --------------------------------------------------
# Text normalization
# --------------------------------------------------

def normalize_text(value):
    """Normalize text for preliminary comparison only."""
    value = str(value or "").lower()
    return re.sub(r"[^a-z0-9]", "", value)


def escape_markdown_table(value):
    """Escape values before inserting them into Markdown tables."""
    return (
        str(value or "")
        .replace("|", "\\|")
        .replace("\r", " ")
        .replace("\n", " ")
    )


# --------------------------------------------------
# Read and validate the local source PDF
# --------------------------------------------------

def load_source_pdf():
    """
    Load the fixed local PDF.

    No network download or database operation is performed.
    """
    if not OFFICIAL_PDF_PATH.is_file():
        raise FileNotFoundError(
            "The comparison PDF was not found.\n"
            f"Expected location: {OFFICIAL_PDF_PATH}\n"
            "Upload the original PDF to the data folder using "
            "the filename: it_act_2000_as_on_2025-06-27.pdf"
        )

    print(f"Using local comparison PDF: {OFFICIAL_PDF_PATH}")

    reader = PdfReader(str(OFFICIAL_PDF_PATH))

    if reader.is_encrypted:
        raise ValueError(
            "The comparison PDF is encrypted. "
            "Use an accessible copy of the original PDF."
        )

    if not reader.pages:
        raise ValueError("The comparison PDF contains no pages.")

    page_text = []

    for page_number, page in enumerate(reader.pages, start=1):
        try:
            page_text.append(page.extract_text() or "")
        except Exception as exc:
            print(
                f"Warning: Could not extract text from PDF page "
                f"{page_number}: {exc}"
            )
            page_text.append("")

    pdf_text = "\n".join(page_text)
    normalized_pdf = normalize_text(pdf_text)

    if not normalized_pdf:
        raise ValueError(
            "No searchable text could be extracted from the PDF. "
            "OCR or manual review may be required."
        )

    return reader, normalized_pdf


# --------------------------------------------------
# Load dataset
# --------------------------------------------------

def load_dataset():
    if not DATASET_PATH.is_file():
        raise FileNotFoundError(
            f"Dataset not found: {DATASET_PATH}"
        )

    with DATASET_PATH.open("r", encoding="utf-8") as file:
        dataset = json.load(file)

    if not isinstance(dataset, list) or not dataset:
        raise ValueError(
            "Expected central_acts.json to contain a "
            "non-empty JSON list of Acts."
        )

    return dataset


# --------------------------------------------------
# Build comparison report
# --------------------------------------------------

def generate_report(dataset, reader, normalized_pdf):
    lines = [
        "# NyayaAI — Preliminary Legislation Source Comparison",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Comparison source",
        "",
        f"- PDF file: `{OFFICIAL_PDF_PATH.name}`",
        f"- Version description: {PDF_VERSION_DESCRIPTION}",
        f"- Official source URL: {OFFICIAL_PDF_URL}",
        f"- PDF pages: {len(reader.pages)}",
        "",
        "> IMPORTANT: This report performs an automated text-presence "
        "check only. A match does not establish legal accuracy, "
        "completeness, current validity, commencement, or the "
        "applicability of amendments. A missing match may result from "
        "formatting, OCR, or PDF text-extraction differences. "
        "Human legal review is required.",
        "",
    ]

    total = 0
    matches = 0
    review_items = 0

    for act_index, act in enumerate(dataset, start=1):
        if not isinstance(act, dict):
            lines.extend(
                [
                    f"## Dataset entry {act_index}",
                    "",
                    "**REVIEW:** Entry is not a JSON object.",
                    "",
                ]
            )
            review_items += 1
            continue

        act_name = (
            act.get("act_title")
            or act.get("short_title")
            or act.get("act_name")
            or act.get("title")
            or f"Unnamed Act {act_index}"
        )

        provisions = act.get("provisions", [])

        lines.extend(
            [
                f"## {escape_markdown_table(act_name)}",
                "",
                f"- Dataset source URL: {act.get('source_url') or 'MISSING'}",
                f"- Dataset source name: {act.get('source_name') or 'MISSING'}",
                "",
            ]
        )

        if not isinstance(provisions, list):
            lines.extend(
                [
                    "**REVIEW:** `provisions` is not a list.",
                    "",
                ]
            )
            review_items += 1
            continue

        lines.extend(
            [
                "| Label | Heading | Snippet found | Result |",
                "|---|---|---|---|",
            ]
        )

        for provision_index, provision in enumerate(
            provisions, start=1
        ):
            total += 1

            if not isinstance(provision, dict):
                lines.append(
                    f"| Entry {provision_index} | Invalid record "
                    "| No | REVIEW |"
                )
                review_items += 1
                continue

            label = str(
                provision.get("provision_label", "")
            ).strip()

            heading = str(
                provision.get("heading", "")
            ).strip()

            provision_text = str(
                provision.get("provision_text", "")
            ).strip()

            safe_label = escape_markdown_table(label or "MISSING")
            safe_heading = escape_markdown_table(
                heading or "MISSING"
            )

            if not label or not heading or not provision_text:
                lines.append(
                    f"| {safe_label} | {safe_heading} "
                    "| No | REVIEW — required field missing |"
                )
                review_items += 1
                continue

            # Check the first 180 characters of the provision text.
            # This is a heuristic, not a full legal-text comparison.
            excerpt = normalize_text(provision_text[:180])
            found = bool(excerpt) and excerpt in normalized_pdf

            if found:
                matches += 1
                result = "MATCH — inspect manually"
                found_text = "Yes"
            else:
                review_items += 1
                result = "REVIEW — snippet not located"
                found_text = "No"

            lines.append(
                f"| {safe_label} | {safe_heading} "
                f"| {found_text} | {result} |"
            )

        lines.append("")

    lines.extend(
        [
            "## Summary",
            "",
            f"- Acts in dataset: {len(dataset)}",
            f"- Provision records checked: {total}",
            f"- Opening snippets located: {matches}",
            f"- Items requiring review: {review_items}",
            "",
            "## Required manual checks",
            "",
            "- Compare complete provision wording with the PDF.",
            "- Confirm that each provision belongs to the correct section.",
            "- Check amendments, inserted sections, footnotes, and schedules.",
            "- Check applicable commencement and amendment dates.",
            "- Confirm the current legal position using authoritative sources.",
            "- Record the reviewer's decision and evidence separately.",
            "",
            "## Processing safeguards",
            "",
            "- The source PDF was read locally.",
            "- No remote PDF download was performed.",
            "- No database writes were performed.",
            "- No legislation was approved or published.",
            "- This report is not a legal opinion.",
            "",
        ]
    )

    REPORT_PATH.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    return total, matches, review_items


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():
    print("Starting preliminary legislation source comparison.")

    dataset = load_dataset()
    print(f"Loaded Acts from dataset: {len(dataset)}")

    reader, normalized_pdf = load_source_pdf()

    total, matches, review_items = generate_report(
        dataset,
        reader,
        normalized_pdf,
    )

    print("")
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
