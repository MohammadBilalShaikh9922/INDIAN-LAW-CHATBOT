
from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pypdf import PdfReader

from app.database import get_supabase_client
from app.legislation_importer import (
    default_dataset_path,
    import_dataset,
    preview_dataset,
)


APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
KB_PATH = APP_DIR / "knowledge_base.json"
PDF_PATH = BACKEND_DIR / "constitution_of_india.pdf"

PDF_SOURCE_URL = (
    "https://github.com/MohammadBilalShaikh9922/INDIAN-LAW-CHATBOT/"
    "blob/main/indian-law-chatbot/backend/constitution_of_india.pdf"
)

DISCLAIMER = (
    "This is general legal information for education only, not legal advice. "
    "Laws and their application can change. Verify sources and consult a "
    "qualified advocate."
)


# ---------------------------------------------------------------------
# Knowledge base
# ---------------------------------------------------------------------

def load_knowledge_base() -> list[dict[str, Any]]:
    """Load the local starter knowledge base."""
    try:
        with KB_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


KNOWLEDGE_BASE = load_knowledge_base()


def extract_constitution_articles() -> list[dict[str, Any]]:
    """Extract searchable numbered provisions from the Constitution PDF."""
    if not PDF_PATH.exists():
        print(f"Constitution PDF not found: {PDF_PATH}")
        return []

    try:
        reader = PdfReader(str(PDF_PATH))
        text = "\n".join(
            page.extract_text() or "" for page in reader.pages
        )
    except Exception as exc:
        print(f"Could not read Constitution PDF: {type(exc).__name__}")
        return []

    if not text.strip():
        print("The Constitution PDF did not produce extractable text.")
        return []

    heading_pattern = re.compile(
        r"(?m)^[ \t]*(?:Article[ \t]+)?"
        r"(\d{1,3}[A-Z]?)\s*\.\s*"
        r"([^\n]{3,180})[ \t]*$",
        re.IGNORECASE,
    )

    headings = []

    for match in heading_pattern.finditer(text):
        number = match.group(1).upper()
        numeric_part = re.match(r"\d+", number)

        if not numeric_part:
            continue

        numeric_value = int(numeric_part.group())

        if not 1 <= numeric_value <= 395:
            continue

        headings.append(
            (match.start(), match.end(), number, match.group(2).strip())
        )

    unique_headings = []
    seen_positions = set()

    for heading in headings:
        if heading[0] not in seen_positions:
            unique_headings.append(heading)
            seen_positions.add(heading[0])

    articles = []

    for index, (start, body_start, number, title) in enumerate(
        unique_headings
    ):
        end = (
            unique_headings[index + 1][0]
            if index + 1 < len(unique_headings)
            else len(text)
        )

        body = text[body_start:end].strip()

        if len(body) < 20:
            continue

        articles.append({
            "id": f"constitution-article-{number.lower()}",
            "title": f"Article {number} — {title}",
            "act": "Constitution of India",
            "provision": f"Article {number}",
            "summary": body[:10000],
            "keywords": [
                f"article {number}",
                f"article {number.lower()}",
                "constitution of india",
                title,
            ],
            "source_title": "Constitution of India PDF (uploaded edition)",
            "source_url": PDF_SOURCE_URL,
        })

    print(f"Extracted {len(articles)} numbered Constitution provisions.")
    return articles


CONSTITUTION_ENTRIES = extract_constitution_articles()


app = FastAPI(
    title="AI Powered Indian Law Chatbot API",
    description=(
        "Educational legal-information retrieval prototype. Not legal advice."
    ),
    version="1.4.0",
)


origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=[
        "Content-Type",
        "x-import-token",
        "x-review-token",
    ],
)


# ---------------------------------------------------------------------
# Request and response models
# ---------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str = Field(pattern=r"^(user|assistant)$")
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=10)



class Source(BaseModel):
    title: str
    url: str
    act: str | None = None
    provision: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    confidence: str
    disclaimer: str


class LegislationReviewRequest(BaseModel):
    decision: str = Field(pattern=r"^(approve|reject)$")
    reviewed_by: str = Field(min_length=2, max_length=120)
    review_notes: str = Field(min_length=20, max_length=4000)


# ---------------------------------------------------------------------
# Published legislation retrieval
# ---------------------------------------------------------------------

def load_published_database_entries() -> list[dict[str, Any]]:
    """
    Load only provisions whose parent Act and provision are published.

    The parent Act must also be legally verified. Import status and
    legal-verification status are separate fields.
    """
    try:
        client = get_supabase_client()

        if client is None:
            return []

        acts_result = (
            client.table("law_acts")
            .select(
                "id, act_title, source_url, source_name, status, import_status"
            )
            .eq("import_status", "published")
            .eq("status", "verified")
            .execute()
        )

        published_acts = acts_result.data or []

        if not published_acts:
            return []

        acts_by_id = {
            str(act["id"]): act
            for act in published_acts
        }

        provisions_result = (
            client.table("law_provisions")
            .select(
                "act_id, provision_label, heading, provision_text, "
                "source_url, language, import_status"
            )
            .eq("import_status", "published")
            .execute()
        )

        entries = []

        for provision in provisions_result.data or []:
            act = acts_by_id.get(str(provision.get("act_id")))

            if act is None:
                continue

            label = str(provision.get("provision_label") or "").strip()
            heading = str(provision.get("heading") or "").strip()
            body = str(provision.get("provision_text") or "").strip()

            if not label or not body:
                continue

            title = f"{act['act_title']} — {label}"

            if heading:
                title += f": {heading}"

            entries.append({
                "id": f"law-{act['id']}-{label}",
                "title": title,
                "act": act["act_title"],
                "provision": label,
                "summary": body[:10000],
                "keywords": [
                    act["act_title"],
                    label,
                    heading,
                    provision.get("language") or "English",
                ],
                "source_title": act.get("source_name") or act["act_title"],
                "source_url": (
                    provision.get("source_url")
                    or act.get("source_url")
                    or ""
                ),
            })

        return entries

    except Exception as exc:
        print(
            "Published legislation retrieval failed: "
            f"{type(exc).__name__}"
        )
        return []


def get_all_entries() -> list[dict[str, Any]]:
    """Combine local entries with explicitly published database provisions."""
    return (
        KNOWLEDGE_BASE
        + CONSTITUTION_ENTRIES
        + load_published_database_entries()
    )


# ---------------------------------------------------------------------
# Retrieval and ranking
# ---------------------------------------------------------------------

def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", " ", text.lower()).strip()


STOP_WORDS = {
    "what", "is", "the", "a", "an", "of", "and", "or", "to", "in",
    "for", "about", "my", "me", "i", "can", "how", "do", "does",
    "are", "be", "with", "please", "explain", "tell", "show",
}


def requested_article(query: str) -> str | None:
    match = re.search(
        r"\b(?:article|art\.?)\s*(\d{1,3}[a-z]?)\b",
        query,
        re.IGNORECASE,
    )
    return match.group(1).upper() if match else None


def score_entry(query: str, entry: dict[str, Any]) -> float:
    q_tokens = set(normalize(query).split()) - STOP_WORDS

    keywords = entry.get("keywords", [])
    if not isinstance(keywords, list):
        keywords = []

    searchable = " ".join([
        str(entry.get("title", "")),
        str(entry.get("act", "")),
        str(entry.get("provision", "")),
        str(entry.get("summary", "")),
        " ".join(str(word) for word in keywords),
    ])

    tokens = set(normalize(searchable).split())

    if not q_tokens or not tokens:
        return 0.0

    overlap = len(q_tokens & tokens)

    title_tokens = set(normalize(
        str(entry.get("title", "")) + " "
        + str(entry.get("provision", ""))
    ).split())

    title_overlap = len(q_tokens & title_tokens)

    return overlap / (len(q_tokens) ** 0.5) + 0.75 * title_overlap


def retrieve(
    query: str,
    limit: int = 3,
) -> list[tuple[float, dict[str, Any]]]:
    article_number = requested_article(query)
    entries = get_all_entries()

    if article_number:
        exact = [
            item
            for item in entries
            if str(item.get("provision", "")).upper()
            == f"ARTICLE {article_number}"
        ]

        if exact:
            return [(1000.0, exact[0])]

        return []

    scored = [
        (score_entry(query, item), item)
        for item in entries
    ]

    scored = [
        (score, item)
        for score, item in scored
        if score > 0
    ]

    scored.sort(key=lambda pair: pair[0], reverse=True)

    return scored[:limit]


# ---------------------------------------------------------------------
# Shared review and publication safeguards
# ---------------------------------------------------------------------

def require_review_token(token: str | None) -> None:
    """Require the separate private legislation review token."""
    expected = os.getenv("LEGISLATION_REVIEW_TOKEN", "")

    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Legislation review is not configured.",
        )

    if not token or not secrets.compare_digest(token, expected):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing review token.",
        )


def get_batch_or_404(client: Any, batch_id: UUID) -> dict[str, Any]:
    """Fetch an import batch without exposing database error details."""
    try:
        result = (
            client.table("law_import_batches")
            .select("*")
            .eq("id", str(batch_id))
            .limit(1)
            .execute()
        )
    except Exception as exc:
        print(f"Batch lookup failed: {type(exc).__name__}")
        raise HTTPException(
            status_code=503,
            detail="Could not check the import batch.",
        ) from None

    if not result.data:
        raise HTTPException(
            status_code=404,
            detail="Import batch not found.",
        )

    return result.data[0]


def check_batch_completeness(
    client: Any,
    batch_id: UUID,
    batch: dict[str, Any],
) -> None:
    """
    Fail closed unless recorded counts match and every record belongs
    to the batch. This does not replace human legal review.
    """
    expected_acts = batch.get("expected_acts")
    expected_provisions = batch.get("expected_provisions")
    imported_acts = batch.get("imported_acts")
    imported_provisions = batch.get("imported_provisions")

    if any(
        value is None
        for value in (
            expected_acts,
            expected_provisions,
            imported_acts,
            imported_provisions,
        )
    ):
        raise HTTPException(
            status_code=409,
            detail="Batch completeness counts are missing.",
        )

    if (
        expected_acts != imported_acts
        or expected_provisions != imported_provisions
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Expected and imported counts differ. "
                "This batch cannot be approved."
            ),
        )

    try:
        acts_result = (
            client.table("law_acts")
            .select("id, status, import_status, import_batch_id")
            .eq("import_batch_id", str(batch_id))
            .execute()
        )

        provisions_result = (
            client.table("law_provisions")
            .select("id, act_id, import_status, import_batch_id")
            .eq("import_batch_id", str(batch_id))
            .execute()
        )
    except Exception as exc:
        print(f"Batch completeness check failed: {type(exc).__name__}")
        raise HTTPException(
            status_code=503,
            detail="Could not verify batch completeness.",
        ) from None

    acts = acts_result.data or []
    provisions = provisions_result.data or []

    if len(acts) != imported_acts:
        raise HTTPException(
            status_code=409,
            detail="The Act count does not match the batch record.",
        )

    if len(provisions) != imported_provisions:
        raise HTTPException(
            status_code=409,
            detail="The provision count does not match the batch record.",
        )

    if not acts or not provisions:
        raise HTTPException(
            status_code=409,
            detail="The batch has no eligible Acts or provisions.",
        )

    act_ids = {str(act["id"]) for act in acts}

    for act in acts:
        if (
            act.get("status") != "verified"
            or act.get("import_status") != "staged"
            or str(act.get("import_batch_id")) != str(batch_id)
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Every Act must be verified and staged before approval."
                ),
            )

    for provision in provisions:
        if (
            provision.get("import_status") != "staged"
            or str(provision.get("import_batch_id")) != str(batch_id)
            or str(provision.get("act_id")) not in act_ids
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "A provision is unstaged or does not belong "
                    "to an Act in this batch."
                ),
            )


# ---------------------------------------------------------------------
# General API endpoints
# ---------------------------------------------------------------------

@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "AI Powered Indian Law Chatbot",
        "docs": "/docs",
        "status": "ok",
    }


@app.get("/api/health")
def health() -> dict[str, str | int]:
    entries = get_all_entries()

    return {
        "name": "AI Powered Indian Law Chatbot",
        "status": "ok",
        "knowledge_entries": len(entries),
        "constitution_articles_loaded": len(CONSTITUTION_ENTRIES),
    }


@app.get("/api/db-health")
def database_health() -> dict[str, Any]:
    """Verify Supabase credentials and both law tables are accessible."""
    try:
        client = get_supabase_client()

        if client is None:
            raise HTTPException(
                status_code=503,
                detail="Supabase environment variables are missing.",
            )

        acts_result = (
            client.table("law_acts")
            .select("id")
            .limit(1)
            .execute()
        )

        provisions_result = (
            client.table("law_provisions")
            .select("id")
            .limit(1)
            .execute()
        )

        return {
            "status": "ok",
            "database": "connected",
            "tables": {
                "law_acts": "accessible",
                "law_provisions": "accessible",
            },
            "sample_rows": {
                "law_acts": len(acts_result.data),
                "law_provisions": len(provisions_result.data),
            },
        }

    except HTTPException:
        raise
    except Exception as exc:
        print(f"Supabase health check failed: {type(exc).__name__}")
        raise HTTPException(
            status_code=503,
            detail=(
                "Supabase connection or table access failed. "
                "Check the Render logs."
            ),
        ) from None


@app.get("/api/laws")
def laws() -> dict[str, Any]:
    """Return local entries and explicitly published database provisions."""
    entries = get_all_entries()

    return {
        "count": len(entries),
        "notice": (
            "Includes the starter dataset, numbered provisions extracted "
            "from the uploaded Constitution PDF, and provisions from "
            "database Acts explicitly marked verified and published. "
            "PDF extraction requires verification."
        ),
        "items": [
            {
                "id": item.get("id", ""),
                "title": item.get("title", ""),
                "act": item.get("act"),
                "provision": item.get("provision"),
                "source_url": item.get("source_url", ""),
            }
            for item in entries
        ],
    }



@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    query = request.message.strip()

    # Use recent conversation only to clarify short follow-up questions.
    history = request.history[-10:]
    previous_user_questions = [
        item.content.strip()
        for item in history
        if item.role == "user" and item.content.strip()
    ]

    follow_up_starters = (
        "what about", "what is the punishment", "what is its punishment",
        "what are the penalties", "explain that", "tell me more",
        "what does this mean", "and what about", "what happens if",
        "is it legal", "can i", "does this also", "what is the process"
    )

    standalone_query = query.lower()
    is_short_follow_up = (
        len(query.split()) <= 12
        and any(standalone_query.startswith(s) for s in follow_up_starters)
    )

    # If the question is clearly a follow-up, add the latest user question
    # as context. The legal database still determines the answer and sources.
    search_query = query
    if is_short_follow_up and previous_user_questions:
        search_query = (
            f"{previous_user_questions[-1]} {query}"
        )

    matches = retrieve(search_query)

    if not matches and search_query != query:
        matches = retrieve(query)

    if not matches:
        if requested_article(query):
            answer = (
                "I could not reliably locate that exact Article in the "
                "available local and published text. No unrelated Article "
                "has been substituted. The source edition or its heading "
                "format may need checking."
            )
        else:
            answer = (
                "I could not find a sufficiently relevant provision in the "
                "available knowledge base. That does not mean the law or "
                "right does not exist. Try naming the Act, Article, section, "
                "or topic and verify the result against an authoritative source."
            )

        return ChatResponse(
            answer=answer,
            sources=[],
            confidence="low",
            disclaimer=DISCLAIMER,
        )

    top_score, top = matches[0]
    sources = []

    for _, item in matches:
        sources.append(Source(
            title=str(
                item.get("source_title", item.get("title", "Legal source"))
            ),
            url=str(item.get("source_url", PDF_SOURCE_URL)),
            act=item.get("act"),
            provision=item.get("provision"),
        ))

    if top.get("act") == "Constitution of India" and top.get("provision"):
        answer = (
            f"**{top['title']}**\n\n"
            f"{top['summary']}\n\n"
            "This text was extracted from the uploaded PDF and has not "
            "been independently checked for extraction errors or edition "
            "currency. Compare it with the official published Constitution."
        )
    else:
        answer = (
            f"**{top['title']}**\n\n{top['summary']}\n\n"
            "This is a short starter summary, not a full statement of the law. "
            "Check the linked source for authoritative text and current status."
        )

    confidence = "moderate" if top_score >= 2.0 else "low"

    return ChatResponse(
        answer=answer,
        sources=sources,
        confidence=confidence,
        disclaimer=DISCLAIMER,
    )


# ---------------------------------------------------------------------
# Legislation validation, import, and preview
# ---------------------------------------------------------------------

@app.get("/api/legislation/validate")
def validate_legislation_dataset() -> dict[str, Any]:
    try:
        return import_dataset(
            file_path=default_dataset_path(),
            dry_run=True,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Legislation dataset file was not found.",
        ) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except Exception as exc:
        print(f"Dataset validation failed: {type(exc).__name__}")
        raise HTTPException(
            status_code=500,
            detail="Dataset validation failed. Check backend logs.",
        ) from None


@app.post("/api/legislation/import")
def import_legislation(
    x_import_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Import legislation only when a valid private import token is supplied."""
    expected_token = os.getenv("LEGISLATION_IMPORT_TOKEN", "")

    if not expected_token:
        raise HTTPException(
            status_code=503,
            detail="Legislation import is not configured.",
        )

    if (
        not x_import_token
        or not secrets.compare_digest(x_import_token, expected_token)
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing import token.",
        )

    try:
        return import_dataset(
            file_path=default_dataset_path(),
            dry_run=False,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Legislation dataset file was not found.",
        ) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except Exception as exc:
        print(f"Legislation import failed: {type(exc).__name__}")
        raise HTTPException(
            status_code=500,
            detail="Legislation import failed. Check backend logs.",
        ) from None


@app.get("/api/legislation/preview")
def preview_legislation_import() -> dict[str, Any]:
    """Preview a legislation import without writing to Supabase."""
    try:
        return preview_dataset(file_path=default_dataset_path())
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Legislation dataset file was not found.",
        ) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except Exception as exc:
        print(f"Legislation preview failed: {type(exc).__name__}")
        raise HTTPException(
            status_code=500,
            detail="Legislation preview failed. Check backend logs.",
        ) from None


# ---------------------------------------------------------------------
# Protected legislation review
# ---------------------------------------------------------------------

@app.post("/api/legislation/{batch_id}/review")
def review_legislation_batch(
    batch_id: UUID,
    request: LegislationReviewRequest,
    x_review_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Approve or reject a batch using the separate private review token."""
    require_review_token(x_review_token)

    client = get_supabase_client()

    if client is None:
        raise HTTPException(
            status_code=503,
            detail="Supabase is not configured.",
        )

    batch = get_batch_or_404(client, batch_id)

    if batch.get("status") not in {"staged", "partial"}:
        raise HTTPException(
            status_code=409,
            detail="Only staged or partial batches can be reviewed.",
        )

    if request.decision == "approve":
        if batch.get("status") != "staged":
            raise HTTPException(
                status_code=409,
                detail="Partial batches cannot be approved.",
            )

        check_batch_completeness(client, batch_id, batch)
        new_status = "reviewed"
    else:
        new_status = "rejected"

    now = datetime.now(timezone.utc).isoformat()

    update_payload = {
        "status": new_status,
        "reviewed_at": now,
        "reviewed_by": request.reviewed_by.strip(),
        "review_notes": request.review_notes.strip(),
    }

    try:
        result = (
            client.table("law_import_batches")
            .update(update_payload)
            .eq("id", str(batch_id))
            .eq("status", batch["status"])
            .execute()
        )
    except Exception as exc:
        print(f"Batch review update failed: {type(exc).__name__}")
        raise HTTPException(
            status_code=503,
            detail="Could not save the review decision.",
        ) from None

    if not result.data:
        raise HTTPException(
            status_code=409,
            detail="Batch status changed; reload it before reviewing.",
        )

    return {
        "status": new_status,
        "import_batch_id": str(batch_id),
        "reviewed_at": now,
        "publishing_performed": False,
        "message": (
            "Batch reviewed. Publication requires a separate request."
            if new_status == "reviewed"
            else "Batch rejected and not published."
        ),
    }


# ---------------------------------------------------------------------
# Protected legislation publication
# ---------------------------------------------------------------------

@app.post("/api/legislation/{batch_id}/publish")
def publish_legislation_batch(
    batch_id: UUID,
    x_review_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Publish a reviewed batch through the guarded database function."""
    require_review_token(x_review_token)

    client = get_supabase_client()

    if client is None:
        raise HTTPException(
            status_code=503,
            detail="Supabase is not configured.",
        )

    batch = get_batch_or_404(client, batch_id)

    if batch.get("status") != "reviewed":
        raise HTTPException(
            status_code=409,
            detail="Only reviewed batches can be published.",
        )

    check_batch_completeness(client, batch_id, batch)

    try:
        result = client.rpc(
            "publish_law_import_batch",
            {"p_batch_id": str(batch_id)},
        ).execute()
    except Exception as exc:
        print(f"Batch publication failed: {type(exc).__name__}")
        raise HTTPException(
            status_code=409,
            detail=(
                "Publication was refused or failed. "
                "Check the batch state and backend logs."
            ),
        ) from None

    return {
        "result": result.data,
        "import_batch_id": str(batch_id),
    }
