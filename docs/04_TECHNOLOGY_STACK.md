# NEXUS — Technology Architecture

## Architecture Diagram

```mermaid
graph TB
    subgraph "Frontend — Vercel"
        FE[React 18 + TypeScript]
        VITE[Vite 5]
        TW[Tailwind CSS]
        RR[React Router v6]
        RC[Recharts]
        LU[Lucide Icons]
    end

    subgraph "Backend — Railway"
        API[FastAPI + Uvicorn]
        PY[Python 3.11]
        PD[Pydantic v2]
        SA[SQLAlchemy Async]
        HTTPX[HTTPX Async Client]
    end

    subgraph "AI / LLM Layer"
        direction TB
        LLM[Unified LLM Service]
        OAI["OpenAI<br/>GPT-5.4 · GPT-5.2 · GPT-4o"]
        ANT["Anthropic<br/>Claude Opus 4.6 · Sonnet 4.6 · Haiku 4.5"]
        EMB["OpenAI Embeddings<br/>text-embedding-3-small (1536d)"]
    end

    subgraph "AI Agent Pipeline"
        MON[Monitor Agent] --> VER[Verify Agent]
        VER --> EXE[Execute Agent]
        EXE --> LRN[Learn Agent]
    end

    subgraph "Database — Railway"
        PG["PostgreSQL 15<br/>(Orders · Audit · Workflows · Agents)"]
        PGV["pgvector<br/>(ServiceNow Embeddings · Similarity Search)"]
    end

    subgraph "Enterprise Systems (Simulated)"
        GK[GKPOS]
        SAP[SAP ECC]
        HYB[Hybris]
    end

    subgraph "External Integrations"
        SN[ServiceNow<br/>Incident Management]
    end

    subgraph "DevOps"
        GH[GitHub]
        DK[Docker / Docker Compose]
        RW[Railway Auto-Deploy]
        VC[Vercel Auto-Deploy]
    end

    FE -->|REST API| API
    API -->|asyncpg| PG
    API -->|asyncpg + pgvector| PGV
    API --> LLM
    LLM --> OAI
    LLM --> ANT
    API --> EMB
    EMB -->|1536d vectors| PGV
    API --> MON
    LRN --> PG
    API -->|Simulators| GK
    API -->|Simulators| SAP
    API -->|Simulators| HYB
    API -->|REST Client| SN
    GH --> RW
    GH --> VC

    style FE fill:#61dafb,color:#000
    style API fill:#009688,color:#fff
    style PG fill:#336791,color:#fff
    style PGV fill:#336791,color:#fff
    style OAI fill:#10a37f,color:#fff
    style ANT fill:#d97706,color:#fff
    style EMB fill:#10a37f,color:#fff
    style LLM fill:#7c3aed,color:#fff
    style MON fill:#3b82f6,color:#fff
    style VER fill:#3b82f6,color:#fff
    style EXE fill:#3b82f6,color:#fff
    style LRN fill:#3b82f6,color:#fff
    style SN fill:#81b532,color:#fff
    style GH fill:#24292e,color:#fff
    style RW fill:#000,color:#fff
    style VC fill:#000,color:#fff
```

## Technology Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 18, TypeScript, Vite 5, Tailwind CSS, React Router v6, Recharts |
| **Backend** | Python 3.11, FastAPI, Uvicorn, Pydantic v2, SQLAlchemy Async, HTTPX |
| **Database** | PostgreSQL 15 (asyncpg driver) |
| **Vector DB** | pgvector extension on PostgreSQL (1536-dim embeddings) |
| **LLM — OpenAI** | GPT-5.4, GPT-5.2, GPT-4o, GPT-4o Mini |
| **LLM — Anthropic** | Claude Opus 4.6, Claude Sonnet 4.6, Claude Haiku 4.5 |
| **Embeddings** | OpenAI text-embedding-3-small (1536 dimensions) |
| **AI Agents** | Monitor → Verify → Execute → Learn (direct chain) |
| **Hosting** | Railway (backend + DBs), Vercel (frontend) |
| **CI/CD** | GitHub → Railway/Vercel auto-deploy |
| **Local Dev** | Docker Compose |
| **Integrations** | ServiceNow, GKPOS, SAP ECC, Hybris (simulated) |
