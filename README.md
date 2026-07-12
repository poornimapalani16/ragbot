# Advanced RAG-Based Chatbot

An enterprise-grade, embeddable Retrieval-Augmented Generation (RAG) chatbot.
Drop one `<script>` tag into any website and it gets a chat widget that
answers questions using **your own documents and pages** as its knowledge base.

## Architecture

```
rag-chatbot/
├── backend/               FastAPI + LangChain + LangGraph + ChromaDB
│   ├── app/
│   │   ├── main.py         App entrypoint, CORS, routers
│   │   ├── config.py       All settings (env-var driven)
│   │   ├── database.py     Bot registry + per-bot ChromaDB collections
│   │   ├── ingestion.py    PDF/DOCX/TXT/URL -> chunks -> vector store
│   │   ├── rag_graph.py    LangGraph pipeline: retrieve -> generate
│   │   ├── memory.py       Per-session conversation memory
│   │   ├── llm.py          Gemini / OpenAI / Anthropic provider switch
│   │   └── routers/        /bots  /ingest  /chat  /health
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── widget/
│   ├── widget.js           The embeddable chat widget (zero build step)
│   ├── admin.html          No-build admin panel: create bots, upload docs
│   └── embed-example.html  Example of a client site using the widget
├── deploy/
│   └── render.yaml         One-click Render.com deployment blueprint
└── docker-compose.yml
```

**Why this design is "easily deployable":**
- The bot registry is a flat JSON file (atomic writes) — no Postgres/MySQL
  setup required to get running.
- Embeddings run locally via `sentence-transformers` — no embedding API key
  or extra billing needed.
- The widget is plain JavaScript with zero dependencies and no build step —
  it's literally one `<script>` tag.
- Every external call (LLM, file parsing, URL fetch) is wrapped in
  try/except with automatic retries (`tenacity`) and centralized exception
  handlers, so the API degrades gracefully instead of crashing on bad
  input, flaky networks, or provider rate limits.

## 1. Local setup (fastest way to test)

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env: set GOOGLE_API_KEY (or switch LLM_PROVIDER) and ADMIN_API_KEY

uvicorn app.main:app --reload
```

The API is now running at `http://localhost:8000` (interactive docs at
`http://localhost:8000/docs`).

Open `widget/admin.html` directly in your browser (just double-click it —
no server needed), point "API Base URL" at `http://localhost:8000`, paste
your admin key, and create your first bot.

To test the widget itself, open `widget/embed-example.html`, replace the
placeholder `data-*` attributes with real values from the admin panel, and
point `data-api-base` at `http://localhost:8000`.

## 2. Run with Docker (recommended for production-like testing)

```bash
cd backend
cp .env.example .env   # fill in your keys
cd ..
docker compose up --build -d
```

This builds the image, starts the container, and persists all data
(vector DB, uploads, logs) in a named Docker volume so nothing is lost on
restart. Check it's healthy:

```bash
curl http://localhost:8000/health
```

## 3. Deploy the backend to the cloud

### Option A — Render.com (simplest, has a free tier)
1. Push this repo to GitHub.
2. In Render: **New > Blueprint**, point it at your repo — it will read
   `deploy/render.yaml` automatically.
3. Render will prompt you for `GOOGLE_API_KEY` (marked `sync: false`); it
   auto-generates a secure `ADMIN_API_KEY` for you.
4. Once deployed, note your service URL, e.g. `https://rag-chatbot-backend.onrender.com`.

### Option B — Railway.app
1. New Project > Deploy from GitHub repo.
2. Set the root directory to `backend`.
3. Add environment variables from `.env.example` in the Railway dashboard.
4. Railway auto-detects the `Dockerfile` and builds it.
5. Attach a persistent volume mounted at `/app/data` (Railway > Settings > Volumes)
   so your knowledge bases survive redeploys.

### Option C — Any VM / VPS (DigitalOcean, AWS EC2, etc.)
```bash
git clone <your-repo-url>
cd rag-chatbot/backend
cp .env.example .env   # fill in real values
cd ..
docker compose up --build -d
```
Put Nginx or Caddy in front for HTTPS (required — browsers block mixed
content, and client sites will be HTTPS).

## 4. Host the widget files

`widget/widget.js` and `widget/admin.html` are static files — host them
anywhere that serves static content:
- The same backend (simplest — add a `StaticFiles` mount, or just serve
  `widget/` from any CDN/static host: Cloudflare Pages, Netlify, Vercel,
  GitHub Pages, or an S3 bucket).
- Point `src="https://YOUR_STATIC_HOST/widget.js"` in the embed snippet
  at wherever you host it.

## 5. Create a bot and go live
1. Open your hosted (or local) `admin.html`.
2. Enter your backend's API base URL and `ADMIN_API_KEY`.
3. Create a bot — copy the generated `bot_id` / `api_key`.
4. Upload PDFs/DOCX/TXT or ingest FAQ page URLs into that bot's knowledge base.
5. Copy the embed snippet into any website, right before `</body>`:

```html
<script
  src="https://YOUR_STATIC_HOST/widget.js"
  data-bot-id="..."
  data-api-key="..."
  data-api-base="https://YOUR_BACKEND_URL">
</script>
```

That's it — the chat bubble appears and answers questions using only the
documents you uploaded for that bot.

## Error handling & recovery built in
- **Retries with backoff** on every LLM call (`tenacity`, 3 attempts, exponential wait).
- **Global exception handler** — the API never leaks raw stack traces to a client site; it always returns clean JSON like `{"success": false, "error": "..."}`.
- **Atomic file writes** for the bot registry (no corruption on crash mid-write).
- **Graceful embedding fallback** if Chroma's relevance-scoring API changes between versions.
- **Widget-side retry** — the embed script retries failed requests twice with a short delay before showing a friendly fallback message, so a blip in your backend doesn't break the chat for visitors.
- **Rate limiting** per bot (default 60 requests/minute) to protect against abuse or runaway costs.
- **File validation** (type + size) before any parsing is attempted.
- **Self-healing directories** — required folders (`data/chroma`, `data/uploads`, `data/logs`) are created automatically if missing, so a fresh clone or empty volume never crashes the app on startup.

## Extending
- **Swap the LLM provider**: change `LLM_PROVIDER` in `.env` to `openai` or `anthropic` and set the matching API key — no code changes needed.
- **Scale conversation memory across multiple backend instances**: replace `app/memory.py`'s in-process dict with Redis (the `get_history`/`add_turn` interface is intentionally small).
- **Swap the bot registry for a real database**: replace `BotRegistry._load`/`_save` in `app/database.py` with Postgres/SQLAlchemy calls; nothing else needs to change.
