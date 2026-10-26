
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pypdf import PdfReader

from app.database import get_supabase_client
from app.legislation_importer import (
    default_dataset_path,
    import_dataset,
)


APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
KB_PATH = APP_DIR / "knowledge_base.json"
PDF_PATH = BACKEND_DIR / "constitution_of_india.pdf"

PDF_SOURCE_URL = (
    "https://github.com/MohammadBilalShaikh9922/INDIAN-LAW-CHATBOT/"
    "blob/main/indian-law-chatbot/backend/constitution_of_india.pdf"
)


def load_knowledge_base() -> list[dict[str, Any]]:
    try:
        with KB_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


KNOWLEDGE_BASE = load_knowledge_base()


def extract_constitution_articles() -> list[dict[str, Any]]:
    """Extract searchable numbered provisions from the uploaded PDF."""
    if not PDF_PATH.exists():
        print(f"Constitution PDF not found: {PDF_PATH}")
        return []

    try:
        reader = PdfReader(str(PDF_PATH))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
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

        title = match.group(2).strip()
        headings.append((match.start(), match.end(), number, title))

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
ALL_ENTRIES = KNOWLEDGE_BASE + CONSTITUTION_ENTRIES


app = FastAPI(
    title="AI Powered Indian Law Chatbot API",
    description=(
        "Educational legal-information retrieval prototype. Not legal advice."
    ),
    version="1.2.0",
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
    allow_headers=["Content-Type"],
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=2000)


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


DISCLAIMER = (
    "This is general legal information for education only, not legal advice. "
    "Laws and their application can change. Verify sources and consult a "
    "qualified advocate."
)


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

    if article_number:
        exact = [
            item
            for item in CONSTITUTION_ENTRIES
            if str(item.get("provision", "")).upper()
            == f"ARTICLE {article_number}"
        ]

        if exact:
            return [(1000.0, exact[0])]

        # Do not substitute an unrelated article.
        return []

    scored = [
        (score_entry(query, item), item)
        for item in ALL_ENTRIES
    ]

    scored = [
        (score, item)
        for score, item in scored
        if score > 0
    ]

    scored.sort(key=lambda pair: pair[0], reverse=True)

    return scored[:limit]


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "AI Powered Indian Law Chatbot",
        "docs": "/docs",
        "status": "ok",
    }


@app.get("/api/health")
def health() -> dict[str, str | int]:
    return {
        "name": "AI Powered Indian Law Chatbot",
        "status": "ok",
        "knowledge_entries": len(ALL_ENTRIES),
        "constitution_articles_loaded": len(CONSTITUTION_ENTRIES),
    }


@app.get("/api/db-health")
def database_health() -> dict[str, Any]:
    """Verify that Supabase credentials and both law tables are accessible."""
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
        # Do not return database credentials or raw error details to users.
        print(
            "Supabase health check failed: "
            f"{type(exc).__name__}"
        )
        raise HTTPException(
            status_code=503,
            detail=(
                "Supabase connection or table access failed. "
                "Check the Render logs."
            ),
        ) from None


@app.get("/api/laws")
def laws() -> dict[str, Any]:
    return {
        "count": len(ALL_ENTRIES),
        "notice": (
            "Includes the starter dataset and numbered provisions extracted "
            "from the uploaded Constitution PDF. Extraction requires verification."
        ),
        "items": [
            {
                "id": item.get("id", ""),
                "title": item.get("title", ""),
                "act": item.get("act"),
                "provision": item.get("provision"),
                "source_url": item.get("source_url", ""),
            }
            for item in ALL_ENTRIES
        ],
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    query = request.message.strip()
    matches = retrieve(query)

    if not matches:
        if requested_article(query):
            answer = (
                "I could not reliably locate that exact Article in the text "
                "extracted from the uploaded Constitution PDF. No unrelated "
                "Article has been substituted. The PDF edition or its heading "
                "format may need checking."
            )
        else:
            answer = (
                "I could not find a sufficiently relevant provision in the "
                "available knowledge base. That does not mean the law or right "
                "does not exist. Try naming the Act, Article, section, or topic "
                "and verify the result against an authoritative source."
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
            "This text was extracted from the uploaded PDF and has not yet "
            "been independently checked for extraction errors or edition "
            "currency. Please compare it with the official published Constitution."
        )
    else:
        answer = (
            f"**{top['title']}**\n\n{top['summary']}\n\n"
            "This is a short starter summary, not a full statement of the law. "
            "Check the linked source for the authoritative text and current status."
        )

    confidence = "moderate" if top_score >= 2.0 else "low"

    return ChatResponse(
        answer=answer,
        sources=sources,
        confidence=confidence,
        disclaimer=DISCLAIMER,
    )

@app.get("/api/legislation/validate")
def validate_legislation_dataset():
    try:
        report = import_dataset(
            file_path=default_dataset_path(),
            dry_run=True,
        )
        return report
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Legislation dataset file was not found.",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Dataset validation failed. Check the backend logs.",
        )


@app.post("/api/legislation/import")
def import_legislation(
    x_import_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Import legislation only when a valid private token is supplied."""
    import secrets

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
        report = import_dataset(
            file_path=default_dataset_path(),
            dry_run=False,
        )
        return report

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Legislation dataset file was not found.",
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except Exception as exc:
        print(
            "Legislation import failed: "
            f"{type(exc).__name__}"
        )
        raise HTTPException(
            status_code=500,
            detail="Legislation import failed. Check the backend logs.",
        ) from None
