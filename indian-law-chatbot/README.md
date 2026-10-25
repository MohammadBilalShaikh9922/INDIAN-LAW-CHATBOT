# AI Powered Indian Law Chatbot

A deployable starter web application inspired by the seminar report **“AI Powered Indian Law Chat Bot”**. It provides a responsive chat UI and a FastAPI backend that searches a small, curated starter knowledge base and returns plain-language summaries with source links.

> **Important:** This is an educational legal-information prototype, not a lawyer or legal-advice service. The included knowledge base is intentionally small and is not a complete or authoritative database of Indian law. Verify current law using official sources and consult a qualified advocate for case-specific advice.

## Features

- Responsive React + Vite frontend.
- FastAPI backend with `/api/health`, `/api/chat`, and `/api/laws` endpoints.
- Basic lexical relevance scoring over a structured legal knowledge base.
- Source titles and URLs returned with responses.
- Suggested prompts, chat transcript, loading and error states.
- Legal disclaimer and privacy-minded defaults.
- Automated backend tests.
- CORS configured through environment variables.

## What is implemented vs. future work

Implemented in this starter:
- Query normalization and keyword-based retrieval.
- Relevance scoring and source attachment.
- A small set of example legal entries.
- Frontend/backend integration.

Not implemented or trained:
- BERT, IndicBERT, Sentence-BERT, a trained intent classifier, production-grade BM25/TF-IDF, voice transcription, automatic feedback-based retraining, or a comprehensive verified legal corpus.
- LLM responses are not enabled by default. You can extend the backend with a provider later; never expose API keys in frontend code.

## Requirements

- Python 3.10+
- Node.js 20+ and npm
- GitHub account for deployment

## Run locally

### 1. Start the backend

Open a terminal in the project folder:

```bash
cd backend
python -m venv .venv
```

Activate the virtual environment:

Windows PowerShell:
```powershell
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:
```bash
source .venv/bin/activate
```

Install dependencies and run:
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend runs at `http://127.0.0.1:8000`. API docs: `http://127.0.0.1:8000/docs`.

### 2. Start the frontend

Open a second terminal:
```bash
cd frontend
npm install
```

Create `frontend/.env`:
```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Then:
```bash
npm run dev
```

Open the URL shown by Vite (usually `http://localhost:5173`).

## Tests

From the `backend` directory, activate your virtual environment and run:
```bash
pip install -r requirements.txt
pytest
```

## Deploy backend to Render

1. Push this project to a GitHub repository.
2. In Render, create **New + → Web Service** and connect the repository.
3. Set **Root Directory** to `backend`.
4. Build command: `pip install -r requirements.txt`
5. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
6. Add environment variable:
   - `CORS_ORIGINS` = your deployed frontend URL, e.g. `https://your-site.pages.dev`
7. Deploy. Copy the service URL, for example `https://your-service.onrender.com`.

Render free services may sleep when idle and take time to wake. Availability and limits can change.

## Deploy frontend to Cloudflare Pages

1. Push the complete project to GitHub.
2. In Cloudflare Pages, create a project and connect the repository.
3. Framework preset: **Vite**.
4. Root directory: `frontend`.
5. Build command: `npm run build`.
6. Build output directory: `dist`.
7. Add environment variable:
   - `VITE_API_BASE_URL` = your Render backend URL, without a trailing slash.
8. Deploy, then update backend `CORS_ORIGINS` to the exact Cloudflare Pages URL and redeploy the backend.

If using a custom domain, include that origin in `CORS_ORIGINS` too. The backend accepts a comma-separated list of origins.

## GitHub web editor workflow

If you prefer editing in GitHub's website:
1. Create a new repository.
2. Upload the ZIP contents (extract ZIP first) or upload the files/folders.
3. Keep the folder structure unchanged.
4. Deploy the backend and frontend separately using the instructions above.

## API examples

Health:
```bash
curl http://127.0.0.1:8000/api/health
```

Chat:
```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Explain Article 21"}'
```

## Safety, accuracy, and privacy

- Do not enter names, addresses, case documents, passwords, or other sensitive personal information.
- Responses are generated from the included starter entries; a missing result is not proof that a law does not exist.
- Statutes and judicial interpretations can change. Confirm current wording and applicability through official sources.
- This project is not legal advice and does not create an advocate-client relationship.
- The starter dataset uses official portal links as starting points. Each linked page may not be a direct deep link to the exact section; verify the relevant provision yourself.

## Project structure

```text
indian-law-chatbot/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   └── knowledge_base.json
│   ├── tests/
│   │   └── test_api.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   └── styles.css
│   ├── index.html
│   ├── package.json
│   └── .env.example
└── .gitignore
```
