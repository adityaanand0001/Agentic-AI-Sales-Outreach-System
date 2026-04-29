<div align="center">
  <br/>
  <h1>🤖 Klyro Mailing Agent</h1>
  <p>
    <strong>AI-Powered Autonomous Email Outreach System</strong>
  </p>
  <p>
    <em>Ingest leads · Generate personalised emails · Approve & send — all powered by LLMs</em>
  </p>

  <p>
    <img src="https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=fff" alt="Python"/>
    <img src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=fff" alt="FastAPI"/>
    <img src="https://img.shields.io/badge/Next.js-14-000?logo=next.js&logoColor=fff" alt="Next.js"/>
    <img src="https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=fff" alt="TypeScript"/>
    <img src="https://img.shields.io/badge/Supabase-3FCF8E?logo=supabase&logoColor=fff" alt="Supabase"/>
    <img src="https://img.shields.io/badge/OpenAI-412991?logo=openai&logoColor=fff" alt="OpenAI"/>
    <img src="https://img.shields.io/badge/LangGraph-1C3C3C?logo=langchain&logoColor=fff" alt="LangGraph"/>
    <img src="https://img.shields.io/badge/Gmail%20API-EA4335?logo=gmail&logoColor=fff" alt="Gmail API"/>
  </p>

  <br/>
</div>

---

## ✨ Overview

Klyro Mailing Agent is a full-stack, AI-powered email outreach system that automates your sales campaigns. It **discovers leads** from your database, **generates personalised emails** using OpenAI GPT-4o or Google Gemini, **creates Gmail drafts** via the Gmail API, and provides a **human-in-the-loop approval workflow** before sending.

The optional **LangGraph agent** adds autonomous decision-making — the system can intelligently decide whether to send, request human review, or skip a lead based on configurable confidence thresholds.

---

## 🚀 Features

| Capability | Description |
|---|---|
| **🧠 AI Email Generation** | Personalised emails powered by GPT-4o or Gemini, tailored to each lead's context |
| **📧 Gmail Integration** | OAuth 2.0 flow — creates drafts & sends directly through your Gmail |
| **✅ Human-in-the-Loop** | Review, approve, reject, or request regeneration before any email goes out |
| **🤖 Autonomous Agent** | LangGraph workflow with confidence scoring — auto-send or escalate to human |
| **📊 Rich Dashboard** | Next.js frontend with KPIs, send volume charts, and campaign analytics |
| **📋 Batch Processing** | Process hundreds of leads in a single run with atomic concurrency protection |
| **📁 Template Library** | Save & reuse email templates with dynamic variable placeholders |
| **📈 Warmup Dashboard** | Monitor daily send volume & domain reputation to avoid spam filters |
| **⚖️ Compliance Tracker** | Track unsubscribes, bounces, spam complaints, and GDPR requests |
| **🛡️ Concurrency Safe** | `FOR UPDATE SKIP LOCKED` — no double-sends, even with multiple workers |

---

## 🏗️ Architecture

```
┌─────────────┐     ┌──────────────────────┐     ┌──────────────┐
│  Supabase   │◄────│   FastAPI Backend     │────►│   Gmail API  │
│  (Postgres) │     │   (Python/Uvicorn)    │     │   (OAuth 2)  │
└─────────────┘     └──────────┬───────────┘     └──────────────┘
                               │
                        ┌──────┴──────┐
                        │  LLM Provider│
                        │ (OpenAI/Gemini)
                        └─────────────┘
                               │
                        ┌──────┴──────┐
                        │  Next.js     │
                        │  Frontend    │
                        └─────────────┘
```

### Directory Structure

```
├── app/                          # FastAPI backend
│   ├── main.py                   # App entry point + CORS
│   ├── config/                   # Pydantic settings, Supabase client
│   ├── models/                   # Pydantic schemas
│   ├── services/                 # Business logic (ingestion, generation, Gmail, tracking)
│   ├── routes/                   # API endpoints (auth, mail agent, LangGraph)
│   ├── deps/                     # Dependency injection container
│   └── langgraph/                # Autonomous agent workflow
├── frontend/                     # Next.js 14 dashboard
│   ├── src/
│   │   ├── components/           # Dashboard, views, widgets
│   │   ├── lib/api.ts            # API client
│   │   └── app/                  # Pages & layout
│   └── package.json
├── supabase_schema.sql           # Database schema
├── backend-schema.sql            # Extended schema (templates, compliance, warmup)
└── .env.example                  # Environment template
```

---

## 🧠 LangGraph Autonomous Agent

The intelligent workflow engine adds AI-driven decision-making to your email campaigns.

```
┌──────────┐   ┌───────────┐   ┌──────────┐   ┌──────────────┐
│ Discover │──►│ Prioritize│──►│ Evaluate │──►│ Generate     │
│ Leads    │   │ Lead      │   │ Lead     │   │ Email        │
└──────────┘   └───────────┘   └──────────┘   └──────┬───────┘
                                                      │
                                               ┌──────▼──────┐
                                               │ Quality     │
                                               │ Check       │
                                               └──────┬──────┘
                                                      │
                                          ┌───────────┼───────────┐
                                          ▼           ▼           ▼
                                      ┌──────┐  ┌────────┐  ┌──────┐
                                      │ Send │  │ Review │  │ Skip │
                                      └──────┘  └────────┘  └──────┘
```

- **Confidence Scoring** — Each email is scored; high confidence → auto-send
- **Human Escalation** — Low confidence → flagged for human review
- **Audit Trail** — Every decision logged for full transparency
- **Mermaid Visualization** — Visualize the workflow at runtime

---

## ⚡ Quick Start

### Prerequisites

- Python 3.10+
- A [Supabase](https://supabase.com) project
- A [Google Cloud](https://console.cloud.google.com) project with Gmail API enabled
- An [OpenAI](https://platform.openai.com) API key (or Gemini key)

### Setup

```bash
# 1. Clone & install
cd klyro-mailing-agent
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Fill in: Supabase URL/key, OpenAI key, Google OAuth credentials

# 3. Setup database tables
# Run supabase_schema.sql in Supabase SQL Editor

# 4. Start the server
uvicorn app.main:app --reload --port 8000
```

### Authenticate with Gmail

```bash
# Open in browser → follow OAuth flow
open http://localhost:8000/api/auth/google

# Check status
curl http://localhost:8000/api/auth/status
```

### Generate & Send Your First Email

```bash
# List pending leads
curl http://localhost:8000/api/mail-agent/leads

# Generate email
curl -X POST http://localhost:8000/api/mail-agent/generate \
  -H "Content-Type: application/json" \
  -d '{"lead_id": "your-lead-uuid"}'

# Approve & send
curl -X POST http://localhost:8000/api/mail-agent/approve \
  -H "Content-Type: application/json" \
  -d '{"tracker_id": "tracker-uuid"}'
```

### Start the Frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:3000
```

---

## 📡 API Overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/api/auth/google` | Start Gmail OAuth flow |
| `GET` | `/api/auth/status` | Check auth status |
| `GET` | `/api/mail-agent/leads` | List pending leads |
| `POST` | `/api/mail-agent/generate` | Generate email via LLM |
| `POST` | `/api/mail-agent/approve` | Approve & send |
| `POST` | `/api/mail-agent/reject` | Reject email |
| `POST` | `/api/mail-agent/bulk-approve` | Bulk approve |
| `GET` | `/api/mail-agent/dashboard/summary` | Dashboard KPIs |
| `GET` | `/api/mail-agent/templates` | List email templates |
| `GET` | `/api/mail-agent/compliance/summary` | Compliance stats |
| `GET` | `/api/mail-agent/warmup` | Warmup dashboard stats |
| `POST` | `/api/langgraph-agent/run-autonomous-batch` | Run autonomous batch |
| `GET` | `/api/langgraph-agent/visualize/mermaid` | Workflow diagram |

> Full interactive docs at [http://localhost:8000/docs](http://localhost:8000/docs) (Swagger UI)

---

## 🖥️ Dashboard Features

| Tab | Description |
|-----|-------------|
| **Dashboard** | KPIs, send volume chart, revenue projection |
| **Review Queue** | Pending emails with approve/reject + Bulk Edit mode |
| **Sent History** | Sent emails with Thread View toggle |
| **Batches** | Batch processing queue & status |
| **Logs** | System activity log |
| **Performance** | Domain reputation & analytics |
| **Templates** | Save & reuse email templates with variable chips |
| **Compliance** | Unsubscribes, bounces, spam, GDPR tracking |
| **Warmup** | Daily send gauge, reputation, 14-day history chart |
| **Settings** | SMTP & sender configuration |

---

## 🛡️ Concurrency & Safety

The system uses **industrial-grade atomic claim** to prevent double-sends:

- **`FOR UPDATE SKIP LOCKED`** — Postgres row-level locking ensures no two workers process the same lead
- **Atomic RPC** — Lead discovery & queue insertion in a single transaction
- **Unique Constraint** — Database-level `UNIQUE(lead_id)` as a physical safety net
- **Self-Healing** — Stale "zombie" leads from crashes are automatically recovered

---

## 🧪 Testing

```bash
python deep_test_suite.py
```

✅ 18/19 tests pass covering: email generation, Gmail OAuth, approval flow, Supabase integration, error handling, and LangGraph workflow.

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3, FastAPI, Uvicorn, Pydantic v2 |
| **Frontend** | Next.js 14, React 18, TypeScript, Tailwind CSS |
| **Database** | Supabase (PostgreSQL) |
| **LLMs** | OpenAI GPT-4o, Google Gemini 1.5 Flash |
| **Agent** | LangGraph, LangChain |
| **Email** | Gmail API (OAuth 2.0) |

---

## 📄 License

MIT

---

<div align="center">
  <sub>Built with ❤️ for intelligent outreach</sub>
</div>
