
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
    Load published provisions from verified Information Technology Act records.
    """
    try:
        client = get_supabase_client()

        if client is None:
            return []

        acts_result = (
            client.table("law_acts")
            .select(
                "id, act_title, short_title, source_url, source_name, "
                "status, import_status"
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

            # Allow only the Information Technology Act, 2000.
            act_title = str(
                act.get("act_title") or ""
            ).strip().lower()

            short_title = str(
                act.get("short_title") or ""
            ).strip().lower()

            is_it_act = (
                act_title in {
                    "the information technology act, 2000",
                    "information technology act, 2000",
                }
                or short_title in {
                    "information technology act, 2000",
                    "it act, 2000",
                }
            )

            if not is_it_act:
                continue

            label = str(
                provision.get("provision_label") or ""
            ).strip()

            heading = str(
                provision.get("heading") or ""
            ).strip()

            body = str(
                provision.get("provision_text") or ""
            ).strip()

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
                "source_title": (
                    act.get("source_name") or act["act_title"]
                ),
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
    """Return published provisions from the Information Technology Act only."""
    return load_published_database_entries()



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


def requested_section(query: str) -> str | None:
    """Extract an IT Act section number, such as 43, 66C, or 3A."""
    match = re.search(
        r"\b(?:section|sec\.?|s\.)\s*(\d{1,3}[a-z]?)\b",
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
    section_number = requested_section(query)
    article_number = requested_article(query)
    entries = get_all_entries()

    # Exact IT Act section lookup.
    if section_number:
        exact = [
            item
            for item in entries
            if str(item.get("provision", "")).strip().upper()
            in {
                section_number,
                f"SECTION {section_number}",
                f"SEC. {section_number}",
            }
        ]

        if exact:
            return [(1000.0, exact[0])]

        return []

    # Preserve existing Article lookup for now.
    if article_number:
        exact = [
            item
            for item in entries
            if str(item.get("provision", "")).strip().upper()
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


class ActVerificationRequest(BaseModel):
    verified_by: str = Field(min_length=2, max_length=120)
    verification_notes: str = Field(min_length=50, max_length=4000)
    source_checked: bool = False
    amendment_status_checked: bool = False
    provision_text_reviewed: bool = False


@app.post("/api/legislation/acts/{act_id}/verify")
def verify_legislation_act(
    act_id: int,
    request: ActVerificationRequest,
    x_review_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """
    Record human verification of an Act's source and text.
    This does not publish the Act or its provisions.
    """
    require_review_token(x_review_token)

    if not (
        request.source_checked
        and request.amendment_status_checked
        and request.provision_text_reviewed
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Verify the official source, amendment status, and "
                "provision text before marking the Act verified."
            ),
        )

    client = get_supabase_client()

    if client is None:
        raise HTTPException(
            status_code=503,
            detail="Supabase is not configured.",
        )

    try:
        result = (
            client.table("law_acts")
            .select(
                "id, act_title, source_url, status, import_status, "
                "import_batch_id"
            )
            .eq("id", act_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        print(f"Act verification lookup failed: {type(exc).__name__}")
        raise HTTPException(
            status_code=503,
            detail="Could not retrieve the Act record.",
        ) from None

    if not result.data:
        raise HTTPException(
            status_code=404,
            detail="Act not found.",
        )

    act = result.data[0]

    if act.get("import_status") != "staged":
        raise HTTPException(
            status_code=409,
            detail="Only a staged Act can enter this verification workflow.",
        )

    if not act.get("import_batch_id"):
        raise HTTPException(
            status_code=409,
            detail="The Act is not associated with an import batch.",
        )

    notes = request.verification_notes.strip()

    if len(notes) < 50:
        raise HTTPException(
            status_code=422,
            detail="Provide at least 50 characters of verification notes.",
        )

    now = datetime.now(timezone.utc).isoformat()

    try:
        update_result = (
            client.table("law_acts")
            .update({
                "status": "verified",
                "verified_by": request.verified_by.strip(),
                "verification_notes": notes,
                "last_verified_at": now,
                "updated_at": now,
            })
            .eq("id", act_id)
            .eq("import_status", "staged")
            .execute()
        )
    except Exception as exc:
        print(f"Act verification update failed: {type(exc).__name__}")
        raise HTTPException(
            status_code=503,
            detail="Could not save Act verification.",
        ) from None

    if not update_result.data:
        raise HTTPException(
            status_code=409,
            detail="The Act changed during verification. Reload and retry.",
        )

    return {
        "act_id": act_id,
        "act_title": act.get("act_title"),
        "status": "verified",
        "import_status": "staged",
        "verified_by": request.verified_by.strip(),
        "verification_notes": notes,
        "last_verified_at": now,
        "published": False,
        "message": (
            "Act verification recorded. The import batch still requires "
            "review and separate publication."
        ),
    }


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


# ---------------------------------------------------------------------
# Chat endpoint with basic conversation context
# ---------------------------------------------------------------------


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    query = request.message.strip().strip("\"'“”‘’").strip()

    if not query:
        return ChatResponse(
            answer="Please enter a question about the Information Technology Act, 2000.",
            sources=[],
            confidence="low",
            disclaimer=DISCLAIMER,
        )

    query_lower = query.lower()

    # Explicitly reject questions asking about other laws or court judgments.
    out_of_scope_terms = (
        "constitution of india",
        "article 21",
        "bharatiya nyaya sanhita",
        "indian penal code",
        "code of criminal procedure",
        "civil procedure code",
        "supreme court judgment",
        "high court judgment",
        "court judgment",
        "case law",
        "case-law",
        "precedent",
    )

    if any(term in query_lower for term in out_of_scope_terms):
        return ChatResponse(
            answer=(
                "I am KANOON AI CHATBOT, an assistant limited to the "
                "Information Technology Act, 2000. I cannot explain other "
                "Acts, constitutional provisions, or court judgments. "
                "Please ask a question specifically about a provision or "
                "topic covered by the Information Technology Act, 2000."
            ),
            sources=[],
            confidence="low",
            disclaimer=DISCLAIMER,
        )

    # Use conversation history only to clarify short follow-up questions.
    history = request.history[-10:]
    previous_user_questions = [
        item.content.strip().strip("\"'“”‘’").strip()
        for item in history
        if item.role == "user" and item.content.strip()
    ]

    previous_question = ""
    for question in reversed(previous_user_questions):
        if question.lower() != query_lower:
            previous_question = question
            break

    follow_up_starters = (
        "what about",
        "what is the punishment",
        "what is its punishment",
        "what are the penalties",
        "explain that",
        "tell me more",
        "what does this mean",
        "and what about",
        "what happens if",
        "is it legal",
        "can i",
        "does this also",
        "what is the process",
    )

    is_short_follow_up = (
        len(query.split()) <= 12
        and any(query_lower.startswith(s) for s in follow_up_starters)
    )

    search_query = query

    if is_short_follow_up and previous_question:
        search_query = f"{previous_question} {query}"

    matches = retrieve(search_query)

    # Retry without conversation context if it did not find a result.
    if not matches and search_query != query:
        matches = retrieve(query)

    if not matches:
        section_number = requested_section(query)

        if section_number:
            answer = (
                f"I could not find an exact published, verified IT Act "
                f"provision for Section {section_number} in the available "
                "database. No substitute section has been used. The "
                "Information Technology Act dataset may still require "
                "review and publication."
            )
        else:
            answer = (
                "I could not find a sufficiently relevant provision in "
                "the available published, verified text of the Information "
                "Technology Act, 2000. I will not guess or use another "
                "Act to fill the gap. Try specifying an IT Act section "
                "number or a topic covered by the Act."
            )

        return ChatResponse(
            answer=answer,
            sources=[],
            confidence="low",
            disclaimer=DISCLAIMER,
        )

    top_score, top = matches[0]

    if top_score < 1.0 and not requested_section(query):
        return ChatResponse(
            answer=(
                "The available IT Act provisions do not match your question "
                "closely enough for a reliable answer. Please provide a "
                "specific section number or a more focused topic from the "
                "Information Technology Act, 2000."
            ),
            sources=[],
            confidence="low",
            disclaimer=DISCLAIMER,
        )

    sources = []
    seen_urls = set()

    for _, item in matches:
        source_url = str(item.get("source_url") or "").strip()

        if (
            not source_url.startswith(("https://", "http://"))
            or source_url in seen_urls
        ):
            continue

        seen_urls.add(source_url)

        sources.append(
            Source(
                title=str(
                    item.get(
                        "source_title",
                        item.get("title", "Information Technology Act, 2000"),
                    )
                ),
                url=source_url,
                act=item.get("act"),
                provision=item.get("provision"),
            )
        )

    title = str(top.get("title") or "Information Technology Act provision")
    summary = str(top.get("summary") or "").strip()
    provision = str(top.get("provision") or "").strip()

    if not summary:
        return ChatResponse(
            answer=(
                "A matching IT Act record was found, but it does not contain "
                "enough provision text to produce a reliable explanation. "
                "Please verify the source text before relying on it."
            ),
            sources=sources,
            confidence="low",
            disclaimer=DISCLAIMER,
        )

    answer = f"**{title}**\n\n{summary}"

    if provision:
        answer += f"\n\n**Provision:** {provision}"

    answer += (
        "\n\nThis response is based only on the available published IT Act "
        "dataset. Verify the provision against the official Act text before "
        "relying on it."
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
