from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

APP_DIR = Path(__file__).resolve().parent
KB_PATH = APP_DIR / "knowledge_base.json"

def load_knowledge_base() -> list[dict[str, Any]]:
    with KB_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []

KNOWLEDGE_BASE = load_knowledge_base()

app = FastAPI(
    title="AI Powered Indian Law Chatbot API",
    description="Educational legal-information retrieval prototype. Not legal advice.",
    version="1.0.0",
)

origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
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
    "Laws and their application can change. Verify sources and consult a qualified advocate."
)

def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", " ", text.lower()).strip()

STOP_WORDS = {"what", "is", "the", "a", "an", "of", "and", "or", "to", "in", "for", "about", "my", "me", "i", "can", "how", "do", "does", "are", "be", "with", "please", "explain", "tell", "show"}

def score_entry(query: str, entry: dict[str, Any]) -> float:
    q_tokens = set(normalize(query).split()) - STOP_WORDS
    searchable = " ".join([
        str(entry.get("title", "")),
        str(entry.get("act", "")),
        str(entry.get("provision", "")),
        str(entry.get("summary", "")),
        " ".join(entry.get("keywords", [])),
    ])
    tokens = set(normalize(searchable).split())
    if not q_tokens or not tokens:
        return 0.0
    overlap = len(q_tokens & tokens)
    # Lightly reward exact title/provision mentions without claiming semantic AI.
    title_tokens = set(normalize(str(entry.get("title", "")) + " " + str(entry.get("provision", ""))).split())
    title_overlap = len(q_tokens & title_tokens)
    return overlap / (len(q_tokens) ** 0.5) + 0.75 * title_overlap

def retrieve(query: str, limit: int = 3) -> list[tuple[float, dict[str, Any]]]:
    scored = [(score_entry(query, item), item) for item in KNOWLEDGE_BASE]
    scored = [(score, item) for score, item in scored if score > 0]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[:limit]

@app.get("/")
def root() -> dict[str, str]:
    return {"name": "AI Powered Indian Law Chatbot", "docs": "/docs", "status": "ok"}

@app.get("/api/health")
def health() -> dict[str, str | int]:
    return {"name": "AI Powered Indian Law Chatbot", "status": "ok", "knowledge_entries": len(KNOWLEDGE_BASE)}

@app.get("/api/laws")
def laws() -> dict[str, Any]:
    return {
        "count": len(KNOWLEDGE_BASE),
        "notice": "Starter dataset only; not a complete legal database.",
        "items": [
            {
                "id": item["id"],
                "title": item["title"],
                "act": item.get("act"),
                "provision": item.get("provision"),
                "source_url": item["source_url"],
            }
            for item in KNOWLEDGE_BASE
        ],
    }

@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    query = request.message.strip()
    if len(query) < 2:
        return ChatResponse(
            answer="Please enter a little more detail so I can search the starter legal knowledge base.",
            sources=[],
            confidence="low",
            disclaimer=DISCLAIMER,
        )

    matches = retrieve(query)
    if not matches:
        return ChatResponse(
            answer=(
                "I could not find a sufficiently relevant entry in the current starter knowledge base. "
                "That does not mean the law or right does not exist. Try naming the Act, section, article, "
                "or topic, and verify it through the official sources listed on this site."
            ),
            sources=[],
            confidence="low",
            disclaimer=DISCLAIMER,
        )

    top_score, top = matches[0]
    source_items = []
    for _, item in matches:
        source_items.append(Source(
            title=item["source_title"],
            url=item["source_url"],
            act=item.get("act"),
            provision=item.get("provision"),
        ))

    answer = (
        f"**{top['title']}**\n\n{top['summary']}\n\n"
        "This is a short starter summary, not a full statement of the law. "
        "Check the linked source for the authoritative text and current status."
    )
    confidence = "moderate" if top_score >= 2.0 else "low"
    return ChatResponse(answer=answer, sources=source_items, confidence=confidence, disclaimer=DISCLAIMER)
