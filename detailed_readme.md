# MedSysAI — Detailed Technical Reference

> **Branding:** the product is written **MedSysAI** (no space, no version
> suffix). The old "MedSys 2.0" / "MedSys AI 2.0" wording was removed from the
> logos (`NavShell`, `Landing`, `HeaderNav`), the FastAPI title/root message
> in `app/main.py`, and backend docstrings/banners. The Mongo database names
> (`medsys_doctor`, `medsys_patient`) and container tags are unchanged on
> purpose — renaming them would point the app at empty databases.

This file exists so an AI agent (or a new engineer) can make changes to this
codebase **without reading every source file first**. It documents every
module, function, data model, external integration, and non-obvious design
decision. If you're about to touch a file, find it in this doc first — it
tells you what already exists, why it's shaped the way it is, and what will
break if you change it carelessly.

Keep this file in sync: whenever you add/remove/rename a function, route,
model field, or env var, update the matching section here in the same
change.

**This is a full rewrite of an earlier version of this doc**, produced from
a fresh repo-wide audit. The app has grown from a single-user, no-auth
personal health tracker into a Clerk-authenticated, multi-tenant clinical
platform with separate doctor and patient portals, plus three fine-tuned
medical LLM adapters trained outside this repo (in Colab) and served to it
over a remote HTTP endpoint. If you have an older copy of this file cached
in memory/context, discard it — the data model (two Mongo databases instead
of one, `embeddings.py` deleted, Pinecone replacing brute-force Mongo vector
search), the auth model (Clerk + demo mode instead of none), and the route
surface (14 routers instead of 7) have all changed underneath it.

**Section 11 lists confirmed bugs and dead code found during this audit** —
read it before assuming an endpoint works as its name/docstring suggests.

---

## Table of contents

1. [What this project is](#1-what-this-project-is)
2. [Tech stack](#2-tech-stack)
3. [Environment variables](#3-environment-variables)
4. [MongoDB — two databases, no ODM](#4-mongodb--two-databases-no-odm-via-appdbpy)
5. [Backend — file by file](#5-backend--file-by-file)
6. [Frontend — file by file](#6-frontend--file-by-file)
7. [Which LLM does what](#7-which-llm-does-what)
8. [Design decisions & gotchas](#8-design-decisions--gotchas-read-before-fixing-these)
9. [Adding a new feature](#9-adding-a-new-feature--where-things-go)
10. [Fine-tuning notebooks](#10-fine-tuning-notebooks--the-medgemma-specialty-adapters)
11. [Known bugs & dead code](#11-known-bugs--dead-code-confirmed-by-this-audit)

---

## 1. What this project is

MedSys AI is a **Clerk-authenticated, multi-tenant clinical platform** with
two distinct portals behind one React app and one FastAPI backend:

- **Doctor portal** — a command center (KPIs, priority alerts, today's
  appointments), a patient directory, a 3-step new-patient wizard, a
  tabbed 360° patient workspace (overview/labs/timeline/AI copilot), a
  5-step guided consultation workflow with AI decision support and
  medication-safety checking, an analytics dashboard, and an appointment
  queue.
- **Patient portal** — a dashboard of doctor-published advice/prescriptions,
  a medication tracker with dose logging, a diet manager with meal logging,
  a lab-report vault (OCR'd on upload), an appointment booking flow, a
  document vault ("My Data"), a Find Care map, and a legacy Home page with a
  live symptom knowledge graph.
- **Shared** — a chat interface (branded "Clinical Copilot" for doctors,
  "Ask MedSys" for patients) grounded on selected documents, with **explicit
  medical-specialty routing** to one of several fine-tuned adapters (see §7
  and §10) via `@tag` syntax, a UI dropdown, or automatic keyword
  classification.

Auth is real (Clerk-issued JWTs verified server-side) but the app also ships
a **demo mode** (`MEDSYS_DEMO_MODE=true` by default) that auto-provisions an
isolated per-browser doctor/patient identity for unauthenticated requests
instead of rejecting them — see §5's `clerk_auth.py` and §8.9.

## 2. Tech stack

- **Frontend**: Vite + React 19 + TypeScript, Tailwind CSS v4 (`@theme` in
  `index.css`, no `tailwind.config.js`), Framer Motion, React Router,
  `@clerk/clerk-react` for auth, `react-markdown` + `remark-gfm`,
  `@tomtom-org/maps-sdk` + `maplibre-gl` v6.
- **Backend**: FastAPI (Python 3.12+), MongoDB (**two isolated databases**,
  see §4) via `pymongo` (sync driver used directly in async handlers —
  fine at this scale), Pinecone for RAG vector storage/embedding
  (`sentence-transformers`/local embeddings are **gone**, see §11),
  `pymupdf` for PDF text extraction, `reportlab` for PDF generation
  (consultation/prescription summaries), `ddgs` for web search.
- **LLMs**: **Gemini** and **Groq Cloud** are the two clouds actually in
  the fallback chains; **Ollama** is checked first for the main chat-reply
  path only (empty by default). A **remote MedGemma multi-adapter service**
  (three separately fine-tuned LoRA adapters on `google/medgemma-4b-it`,
  hosted from a Colab notebook via ngrok) is tried *before* any of those
  for specialty-routed chat. See §7 and §10 for the exact fallback order —
  it is **not** the same order for every feature.
- **External services**: Clerk (auth), Pinecone (vector RAG store),
  Supermemory (medication memory + chat/document logging — **not** the
  primary symptom store, see §5), Firecrawl (web page scraping), TomTom
  (maps + facility search), OpenWeather (weather/AQI), Google Gemini.

Run frontend: `cd frontend && npm run dev` (port 5173).
Run backend (Windows): first-time setup is
`cd backend && python -m venv .venv && .\.venv\Scripts\python.exe -m pip install -r requirements.txt`,
then `backend/run.ps1` (uses `.venv` explicitly so a global `jwt` package
can't shadow PyJWT; serves on port 8000, API docs at `/docs`). `.venv/` is
local and not committed. Elsewhere:
`cd backend && python -m uvicorn app.main:app --reload --port 8000`.
If startup fails with a `pymongo` "DNS query name does not exist" error for
the `mongodb+srv://` host, that is a transient DNS failure resolving the
Atlas SRV record — retry before suspecting the cluster or `.env`.

---

## 3. Environment variables

### Backend (`backend/.env`, see `backend/.env.example` — **the example file
is itself stale**: it's missing `PINECONE_API_KEY`/`PINECONE_INDEX`,
`TOMTOM_API_KEY`, `GEMINI_API_KEY`/`GEMINI_MODEL`, `MEDGEMMA_ADAPTER_URL`,
and `MEDSYS_DEMO_MODE`, all of which exist in `config.py` and are set in the
live `.env`. Update `.env.example` to match `Settings` the next time you
touch either file.)

| Variable | Default | Used by |
|---|---|---|
| `MONGODB_URI` | `mongodb://localhost:27017` | `db.py` — one connection string, two databases |
| `MONGODB_DOCTOR_DB` | `medsys_doctor` | `db.py` — **only** `doctors` and `doctor_profiles` collections live here |
| `MONGODB_PATIENT_DB` | `medsys_patient` | `db.py` — everything else: patients, consultations, prescriptions, appointments, alerts, chat/RAG, documents, symptoms, `doctor_patient` links, audit logs. A consultation/appointment still carries a `doctor_id` reference *field*, but the doctor's own account row never lives here |
| `OLLAMA_HOST` | `http://localhost:11434` | `model_router.py`, checked first in the `_complete()` chain only |
| `OLLAMA_MODEL` | `""` (a MedGemma GGUF quant in the live `.env`) | `model_router.py` |
| `OLLAMA_VISION_MODEL` | `""` | `model_router.py` (vision path is defined but confirm live usage — see §11's OCR note) |
| `GROQ_API_KEY` | `""` | model routing, Whisper transcription, tool-calling web-search decision |
| `GROQ_MODEL` | `openai/gpt-oss-20b` | chat/report/classification model |
| `GROQ_WHISPER_MODEL` | `whisper-large-v3-turbo` | speech-to-text |
| `GROQ_VISION_MODEL` | `qwen/qwen3.6-27b` | vision OCR path (see §11 — currently unused by the live upload flow) |
| `MEDGEMMA_ADAPTER_URL` | `""` | `domain_adapter.py` — optional ngrok/remote URL for the 3-adapter MedGemma service (§10). **Set in the live `.env`.** Unreachable/unset → silent fallback, never an error to the user |
| `FIRECRAWL_API_KEY` | `""` | `web_search.py` — without it, falls back to DuckDuckGo snippets |
| `OPENWEATHER_API_KEY` | `""` | `weather.py` |
| `LOCATION_NAME` / `LOCATION_LAT` / `LOCATION_LNG` | Bengaluru coords | `weather.py` |
| `SUPERMEMORY_API_KEY` | `""` | medication memory + chat/web/document logging (**not** symptoms — see §5's `supermemory_client.py`) |
| `SUPERMEMORY_CONTAINER_TAG` | `medsys-symptoms` | container tag (legacy name; symptom data itself is Mongo-backed now) |
| `SUPERMEMORY_CHAT_CONTAINER_TAG` | `medsys-chat` | chat/web/document memory logging |
| `PINECONE_API_KEY` | `""` | RAG vector store — index auto-created on first use, bound to Pinecone's hosted `llama-text-embed-v2` embedding model, **one namespace per signed-in user** |
| `PINECONE_INDEX` | `Default` | which Pinecone index to use |
| `CLERK_SECRET_KEY` | `""` | server-side JWT verification |
| `CLERK_PUBLISHABLE_KEY` | `""` | **must match the frontend's key** — JWT issuer/JWKS host is derived from it (base64-decoded), not a separate env var |
| `TOMTOM_API_KEY` | `""` | `facilities_service.py` live POI search |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | `""` / `gemini-2.5-flash` | **the primary model for most non-chat-reply LLM calls** — triage, quick-options, graph enrichment, title generation, general tip (via `complete_gemini`) |
| `MEDSYS_DEMO_MODE` | `true` | when true, unauthenticated requests get an auto-provisioned, isolated per-browser demo identity (keyed by `X-Demo-Session-Id`) instead of a 401 |
| `CORS_ORIGINS` | `http://localhost:5173` | `main.py` |

### Frontend (`frontend/.env.local`, see `.env.example`)

| Variable | Effect |
|---|---|
| `VITE_API_BASE_URL` | If unset, the *original* pages (Home, legacy Chat pieces, Find Care, My Data, Profile, Symptoms) run on mock data (`services/mocks.ts`). **The newer doctor/patient-portal pages have no real mock fixtures** — see §6's services note; most will render empty/placeholder states without a real backend. |
| `VITE_CLERK_PUBLISHABLE_KEY` | Gates the app behind Clerk sign-in. Must match the backend's `CLERK_PUBLISHABLE_KEY`. |
| `VITE_TOMTOM_API_KEY` | If unset, Find Care shows a CSS-drawn placeholder map. |

---

## 4. MongoDB — two databases, no ODM (via `app/db.py`)

The single biggest structural change since the original build. **`get_db()`
no longer exists** — it was replaced by `get_doctor_db()` and
`get_patient_db()`, both backed by one cached `MongoClient`.

- **`medsys_doctor`** (`MONGODB_DOCTOR_DB`) — exactly two collections:
  `doctors`, `doctor_profiles`. Nothing patient-related is ever written
  here.
- **`medsys_patient`** (`MONGODB_PATIENT_DB`) — everything else: `patients`,
  `doctor_patient` (assignment links), `consultations`, `prescriptions`,
  `vitals`, `lab_metrics`, `lab_reports`, `raw_lab_documents`, `alerts`,
  `appointments`, `patient_conditions`, `allergies`, `patient_diet`,
  `diet_plans`, `meal_logs`, `medication_logs`, `lab_orders`, `audit_logs`,
  `patient_invitations`, `patient_symptom_history`, `symptoms`,
  `graph_cache`, plus the legacy chat/RAG collections below. A consultation
  or appointment document still carries a `doctor_id` reference *field*,
  but the doctor's own account row is never stored alongside it.

`init_collections()` (called unconditionally at every app startup, in
`main.py`) creates indexes in both databases and — **only when `doctors` is
empty** — seeds one sample doctor, 3 sample patients, assignments, vitals,
labs, alerts, and appointments. A bad Mongo URI therefore fails app
**startup**, not first request.

Legacy chat/RAG collections, still in `medsys_patient`, unchanged in shape
from the original single-DB design:

- **`chat_sessions`** — `{id, title, createdAt, updatedAt, sourceIds: [str]}`.
- **`chat_messages`** — `{id, sessionId, role, content, createdAt}`.
- **`sources`** — one doc per grounding source: `{id, title, kind,
  uploadedAt, excerpt, content, url?}`. Still written to directly by
  `rag.py` as a content/metadata mirror — **but the vector data itself now
  lives in Pinecone, not in a Mongo `chunks` collection**. `embeddings.py`
  and the old brute-force-cosine-similarity `chunks` collection design
  described in earlier versions of this doc are **gone**, fully replaced.
  See §11.

---

## 5. Backend — file by file

### Core: `app/db.py`, `app/models.py`, `app/models_v2.py`, `app/config.py`, `app/main.py`

- **`app/db.py`** — `get_doctor_db()` / `get_patient_db()` (see §4).
  `init_collections()` creates indexes + one-time seed data.
- **`app/models.py`** — legacy Pydantic models for the pre-multi-tenant
  surface: `HomeSnapshot`/`EnvironmentSnapshot`/`KnowledgeGraph` (Home),
  `ChatMessage`/`ChatSession`/`ChatSessionIn`/`ChatMessageIn` (chat — now
  carries `specialty`/`adapter`/`adapter_used` fields for the MedGemma
  adapter feature), `ModelStatus`, `Facility`, `ProfileRecord`/`ProfileIn`,
  `DoctorProfileRecord`.
- **`app/models_v2.py`** — the V2 clinical schema set: audit logs,
  vitals/prescriptions/`AISuggestions`, doctor registration & 3-step
  patient onboarding wizard, appointments, patient portal
  (medication/meal logs, diet plans), command-center/workspace
  (`AlertRecord`, `DoctorPatientAssignment`, `WhatsNewChanges`,
  `EvidenceTrace`, analytics, multi-patient compare, lab trends,
  pre-consultation brief), consultations
  (`ConsultationCreateIn/FinalizeIn/Session`), `CopilotChatIn`. **Two
  confirmed bugs live in this model — see §11.1 and §11.2.**
- **`app/config.py`** — env-driven `Settings` singleton (full field table
  in §3). `clerk_issuer` is derived at import time from
  `CLERK_PUBLISHABLE_KEY`'s base64 payload — not a separate env var.
- **`app/main.py`** — registers `health`, `facilities`, `auth` with no auth
  dependency; `doctor`, `patient`, `appointments`, `documents` with auth
  enforced *inside* each route (`require_role`/`get_current_user`, not a
  router-level dependency); `home`, `chat`, `profile`, `symptoms`, `mydata`
  behind a router-level `Depends(require_clerk_auth)`. Calls
  `init_collections()` at import time. Serves `/uploads` as static files.

### Routers

#### `app/routers/health.py`
`GET /health` → `ModelStatus`, no auth. Returns
`model_router.active_provider()` + `check_reachable()` (probes
Ollama/Groq/Gemini in that order).

#### `app/routers/auth.py`
Clerk-account linking and registration, no blanket auth dependency (mixed
public/authenticated routes internally):
- `GET /api/auth/me` — tells the frontend if the signed-in Clerk account
  has a linked profile; demo sessions always report `hasProfile=true`.
- `POST /api/auth/register-patient` — links Clerk id to a new or
  **unclaimed** existing `patients` doc (matched by email, no `clerk_id`
  yet — i.e. a doctor-wizard-created record). Auto-generates
  `PAT-{count+127:06d}` code. Mirrors into legacy `profiles` (keyed by
  patient `id`) so Home/Chat/Profile legacy pages work. **Assigns the new
  patient to every doctor currently in the system** (`for doc in doctors:
  insert doctor_patient`) — intentional per an in-code comment, so
  self-registrations show up on every doctor's panel immediately, but
  means doctor panels aren't selective for organic sign-ups.
- `POST /api/auth/register-doctor` — links Clerk id to a new `doctors` doc;
  blocks cross-registration and duplicate email.
- `POST /api/auth/add-patient-wizard` — doctor-only. Creates a patient
  **fully active immediately** (no invitation step — this intentionally
  supersedes the older invitation flow below). Lazily creates a `doctors`
  row for the caller if one doesn't exist yet. Creates the assignment,
  conditions, allergies, and an optional draft consultation.
- `GET /api/auth/invitation/{token}` / `POST /api/auth/activate-patient` —
  legacy invitation-token activation, kept only for any unconsumed
  invitations predating the wizard.

#### `app/routers/facilities.py`
`GET /facilities`, no auth — delegates to `facilities_service.search_nearby_facilities`.

#### `app/routers/home.py`
`GET /home/snapshot`, behind `require_clerk_auth`. `asyncio.gather`s
weather, Supermemory-derived graph build, and a general wellness tip
(`return_exceptions=True`); falls back to `mock_data.HOME_SNAPSHOT` on total
failure (broad `except Exception: pass`). Fires
`ai_graph_builder.enrich_graph_with_clinical_knowledge` as a **fire-and-
forget background task** after already returning the cached/partial graph —
the next request picks up the enrichment.

#### `app/routers/profile.py`
Behind `require_clerk_auth`.
- `GET /profile` — `patient_db.profiles` → falls back to `patient_db.patients`
  (computing BMI on the fly) → falls back to `mock_data.DEFAULT_PROFILE`.
  Merges in conditions/medications extracted from `patient_db.sources`
  (backfilling missing extraction fields once per document via
  `model_router.extract_medical_history`) plus Supermemory-derived
  medications from chat.
- `PUT /profile` — upserts `profiles`, syncs demographics into `patients`.
- `GET/PUT /profile/doctor` — separate `doctor_db.doctor_profiles`, keyed
  by `clerkUserId`.

#### `app/routers/symptoms.py`
Behind `require_clerk_auth`. `GET/POST /symptoms` (normalizes via
`ai_graph_builder.normalize_symptom_name`, stores via
`supermemory_client.log_symptom`, fires background KG enrichment),
`DELETE /symptoms/{name}`.

#### `app/routers/mydata.py`
Behind `require_clerk_auth`. `POST /mydata/upload` resolves the current
user's patient record, then delegates entirely to
`hybrid_db_service.ingest_unified_medical_document`.

#### `app/routers/chat.py` — the core clinical chat pipeline

The most complex router. Session CRUD (`GET/POST/DELETE /chat/sessions*`,
`GET .../messages`, `PUT .../sources`) scoped by `$or: [{clerkUserId},
{doctor_id}]` and optionally `patient_id`.

`POST /chat/sessions/{id}/messages` — the core turn, in order:
1. `domain_adapter.resolve_adapter` (explicit `@tag` > UI `specialty`/
   `adapter` param > implicit keyword classification).
2. Stores the user message; mirrors into Pinecone (`rag`) + Supermemory.
3. `triage.eval_triage` (LLM-based semantic red-flag check) — if flagged,
   **short-circuits**: returns a canned emergency-warning message, skips
   all generation, still updates the session.
4. Optional deep web search (manual toggle or `model_router.decide_web_search`,
   Groq-only tool-calling).
5. Assembles context: patient EHR block (if session is patient-scoped) or
   the caller's own profile; longitudinal symptom memory
   (`symptom_tracker.format_medical_memory_block`); live weather/AQI; RAG
   excerpts (`rag.retrieve`, filtered to selected sources + session's own
   history + new web sources).
6. **Generation with fallback** — see §7 for the confirmed full chain:
   remote MedGemma adapter first; if it returns nothing, falls back to
   `model_router.generate_reply` (which itself tries Ollama → Groq →
   Gemini), run in parallel with entity extraction.
7. Generates quick-reply chips, logs extracted symptoms/medications back
   into Supermemory + `symptom_tracker`, stores the assistant message,
   refines the session title in the background on the first turn.

`GET/DELETE /chat/sources*`, `GET /chat/sources/{id}/content` —
`patient_db.sources`, falling back to `mock_data.CHAT_SOURCES` if empty.
Delete also purges from Pinecone and every session's `sourceIds`.
`POST /chat/transcribe` — Groq Whisper; 503s cleanly with no `GROQ_API_KEY`.

**Gotcha**: `_aggregate_patient_ehr_context` reads a `systolic` key before
falling back to `systolic_bp` for vitals, but every writer in the codebase
stores `systolic_bp`/`diastolic_bp` — harmless (falls through correctly)
but a sign the field-naming convention drifted at some point.

#### `app/routers/doctor.py` — largest router (1339 lines)

Everything gated by `require_role("doctor")` and, per-patient, by
`verify_patient_access`.

- `GET /api/doctor/command-center` — aggregates assigned-patient count,
  consultation count, pending-lab count, **dynamically computed** triage
  alerts (stored alerts + on-the-fly rules scanning every assigned
  patient's latest vitals/labs — hardcoded thresholds: BP >135/88
  systolic/diastolic, HR outside 55–100), today's appointments. Logs an
  audit event on **every read**, not just writes.
- `GET /patients`, `/patients/search`, `POST /patients/link` — panel
  management; `link_existing_patient` (by email or `PAT-XXXXXX` code) is
  the counterpart to the wizard for already-self-registered patients.
- `GET /patient/{id}/whats-new`, `/evidence`, `/overview`,
  `/timeline-analysis`, `/timeline`, `/pre-brief`, `/lab-trends`,
  `/safety-check`, `/custom-summary` — read-only clinical views, delegating
  math to `patient_context_service`; all gated by `verify_patient_access`.
- `POST /voice-parse` — **hardcoded stub**, see §11.6.
- `GET /analytics`, `/compare` — scoped strictly to the calling doctor's
  own patients.
- `POST /copilot/chat`, `/generate-diet-plan`, `/custom-summary` — LLM-
  backed, each with a hardcoded canned-string fallback on LLM failure (so
  these never error to the client, just silently degrade to templated
  text).
- `POST /consultations`, `.../ai-assist`, `.../finalize`,
  `GET .../pdf` — full consultation lifecycle: draft → AI decision support
  (`doctor_ai_service.generate_doctor_ai_support`) → doctor sign-off
  (writes `prescriptions`, `patient_diet`, auto-schedules a follow-up
  appointment unless `follow_up_date` is one of `["none","prn","n/a",""]`)
  → PDF export (`pdf_service.generate_consultation_pdf`).
- `POST /lab-orders` — writes a `lab_orders` doc; **nothing else in the
  codebase ever reads this collection back** — write-only today, see §11.7.

#### `app/routers/patient.py`

All `require_role("patient")`.
- `GET /api/patient/dashboard`, `/medications`, `POST .../log`,
  `GET/POST /diet*` — `_ensure_sample_patient_data` lazily seeds two sample
  prescriptions + one finalized consultation the **first time** a given
  `patient_id` has zero prescriptions (a per-patient seed distinct from
  `db.py`'s one-time global seed).
- `POST /api/patient/chat` — **broken, 500s on every call**, see §11.1.
  Otherwise the intended logic: `emergency_triage.evaluate_emergency_triage`
  (keyword-based) short-circuits red flags; else grounds a
  `generate_completion` call in the latest finalized consultation + active
  prescriptions, with a canned fallback on LLM failure.
- `GET .../pdf` — scoped by `patient_id` in the query itself, can't fetch
  another patient's session.

#### `app/routers/appointments.py`

- `GET /availability` — **buggy slot-matching**, see §11.3.
- `POST /request`, `GET /doctor-queue`, `GET /patient-queue` — both list
  endpoints lazily seed a fake appointment the first time a given
  doctor/patient has zero appointments — a **third**, independent ad-hoc
  seeding mechanism alongside `db.py`'s global seed and `patient.py`'s
  `_ensure_sample_patient_data`.
- `POST /{id}/action` — doctor confirms/declines/cancels/completes; writes
  a notification `alerts` doc for the patient.
- `GET /patient-latest-update` — polling endpoint for status changes.
- Uses `get_current_user` (not `require_role`) on most routes, with a
  fallback: if `user.role != "patient"`, uses `"pat_01"` as the patient id
  — meant for a demo-mode doctor accidentally hitting a patient-shaped
  endpoint, but silently misattributes real actions to `pat_01` if
  mis-called in production.

#### `app/routers/documents.py`

- `GET /api/documents/lab-reports` — lists `lab_reports` + joined
  `lab_metrics`; target patient forced to the caller's own id unless the
  caller is a doctor (who may pass `patient_id`).
- `POST /api/documents/upload` — delegates to
  `hybrid_db_service.ingest_unified_medical_document`.
- Uses `get_current_user`, not `require_role` — see §11.9 for a minor
  authorization note (safe by omission, not by an explicit check).

### Services

#### `app/services/clerk_auth.py` — the identity/RBAC layer

`get_current_user` is the real resolver (`require_clerk_auth` is a thin
legacy wrapper returning just a `user_id` string). Full flow, role
resolution, and demo mode are described in §8.9 — read that before touching
auth. `require_role(role)` 403s on mismatch (`"admin"` always passes,
though nothing in the codebase creates an admin account).
`verify_patient_access(patient_id, user)` is the actual per-resource
authorization check used throughout `doctor.py`. **Gotcha**:
`_decode_bearer_token` treats the literal string `"mock-dev-token"` as "no
token" (falls through to demo mode) — a dev-convenience leftover, easy to
trip over if a frontend `.env` still has that placeholder.

#### `app/services/hybrid_db_service.py` — unified document ingestion

`ingest_unified_medical_document(...)`: save file → OCR
(`ocr.extract_text_from_file`) → **in parallel** generate a Markdown
report, classify document type, extract lab metrics, extract medical
history (all `model_router`) → `rag.ingest_report` (Pinecone + `sources`)
→ `process_and_store_lab_report` → `supermemory_client.log_document`
(best-effort). **`process_and_store_lab_report` has a hardcoded reference-
range bug** — see §11.4. Also defines `store_ai_chat_message`,
`save_ai_insight`, `finalize_doctor_clinical_decision` — **all three are
orphaned, zero call sites elsewhere**, see §11.8.

#### `app/services/domain_adapter.py`

`parse_explicit_adapter_tag`, `classify_implicit_adapter`,
`resolve_adapter`, `call_remote_medgemma_adapter`,
`get_adapter_display_name`, `build_specialty_prompt_preamble` — see §10 for
the CANONICAL_ADAPTERS list and §11.5 for the confirmed gap (4 of the 8
declared specialties have no real trained adapter behind the remote
service). `call_remote_medgemma_adapter` treats a 400 (unrecognized
adapter name) the same as any other non-200 — falls back silently, but the
warning log doesn't distinguish "wrong adapter name" from "whole service
down." Called only by `chat.py`.

#### `app/services/model_router.py` — every LLM call in the codebase

Two independent fallback chains coexist (see §7):
- `_complete(...)` — **Ollama → Groq → Gemini**, used for chat replies,
  report generation, classification, history/lab-metric extraction. Swaps
  to vision models automatically when images are passed.
- `complete_gemini(...)` — **Gemini → Groq** (multi-model fallback list:
  `[groq_model, "qwen/qwen3.6-27b", "openai/gpt-oss-120b"]`, 2 retries with
  1.5s backoff on 429), **no Ollama at all**. Used by triage,
  quick_options, ai_graph_builder, chat-title generation, general tip.
- `generate_completion(messages, system_prompt)` — tries `complete_gemini`
  then falls back to `_complete`. Used by doctor/patient copilot-style
  endpoints.
- `decide_web_search` — Groq-only (tool-calling); returns `None`
  immediately if the active provider isn't Groq, by design.
- `extract_lab_metrics` — regex fallback (9 hardcoded patterns: glucose,
  HbA1c, cholesterol, triglycerides, creatinine, hemoglobin, WBC, platelets,
  TSH) only triggers on an outright `Exception` from the LLM call, **not**
  when the LLM succeeds but returns an empty `metrics: []`.
- Strips `<think>...</think>` blocks and `<|special|>` tokens defensively
  from every raw model output (recurring need for open/local models without
  clean stop tokens).

#### `app/services/pinecone_client.py`

Thin wrapper using Pinecone's **server-side integrated embeddings**
(`llama-text-embed-v2`, index auto-created lazily) — no local embedding
model or vector math anywhere in this codebase. `get_index()`,
`upsert_records`, `delete_by_source`, `search` — every call wrapped in a
swallow-all `try/except: pass`/`return []`, so a Pinecone outage degrades
RAG to "no context" silently. Namespace = the calling user's Clerk id (or
demo-provisioned id) — full per-user isolation. Called only by `rag.py`.

#### `app/services/rag.py`

Chunking + retrieval, **fully Pinecone-backed** (see §11 — this fully
replaces the old brute-force Mongo vector search; `embeddings.py` is
deleted, not supplemented). `ingest_report`, `store_web_content`,
`store_chat_message`, `retrieve` — chunks text (800 chars, 150 overlap),
upserts into Pinecone under the owner's namespace, mirrors full
content/excerpt into `patient_db.sources` (for the reader UI and Profile's
extraction cache). `retrieve` supports `allowed_source_ids` filtering.
Called by `chat.py`, `hybrid_db_service.py`, `web_search.py`.

#### `app/services/ocr.py` — two paths, only one is live

- `extract_text_from_file(raw, filename)` — **sync, no LLM**: plain-text
  passthrough for `.txt/.md/.csv/.json/.log`, `pymupdf` text-layer
  extraction for PDFs, and a **placeholder string** for images (images are
  never actually OCR'd through this path). This is the one actually used,
  by `hybrid_db_service.ingest_unified_medical_document`.
- `images_from_upload`, `extract_text(images_b64)` — the vision-LLM OCR
  path (rasterizes PDF pages, batches through Ollama/Groq vision models).
  **Confirmed zero callers anywhere in the codebase** — see §11.10.

#### Triage — three independent layers, no shared code

- `emergency_triage.py` — synchronous, keyword-substring matching
  (`RED_FLAG_KEYWORDS`), no LLM, no negation handling. Used by `patient.py`
  and `doctor_ai_service.py`.
- `triage.py` — async, LLM-based (`complete_gemini`), explicit
  negation/third-party handling ("no chest pain," "my father had a
  stroke" are correctly *not* flagged), with a fast deterministic
  pre-check for unambiguous cases before calling the LLM. Used only by
  `chat.py`.
- `med_safety.py` — **not a triage system**; a single function
  (`apply_safety_guardrails`) that prepends an empathetic-persona system
  prompt string. **Confirmed unused anywhere**, see §11.11.

Confirm this three-way split is intentional (perf/reliability tradeoff per
surface) before assuming it's accidental duplication.

#### `app/services/quick_options.py`
Generates 2–4 quick-reply chip strings via `complete_gemini`. Used only by
`chat.py`. Swallow-all → empty list on failure, never blocks the reply.

#### `app/services/supermemory_client.py`

**Symptoms are Mongo-backed, not Supermemory-backed** — `log_symptom`,
`delete_symptom`, `list_all_symptoms` read/write `patient_db.symptoms`
directly (regex case-insensitive match, upsert with an `occurrences` array
+ running frequency count); Supermemory sync for symptoms is fire-and-
forget via `asyncio.create_task`. Only *medications* (`list_all_medications`)
and chat/web/document logging genuinely round-trip through the Supermemory
API. `log_medication`, `log_web_content`, `log_document`, `log_chat_message`
hit `/v4/memories`; the last three are wrapped in try/except (best-effort),
**`log_medication` is not** — an inconsistency, since every other write
here treats Supermemory as best-effort. `list_all_medications` is capped at
`limit: 100` (a documented hard Supermemory-side cap). `describe_status`
(LLM-judged stable/moderate/serious severity) falls back to a deterministic
keyword classifier on LLM failure. `build_graph` builds a complete graph
(every symptom connected to every other, edges labeled by day-gap) — used
by `home.py`.

#### `app/services/symptom_tracker.py`

Longitudinal symptom lifecycle state machine (`active`/`resolved`/
`historical`) in `patient_db.patient_symptom_history`, separate from
`supermemory_client`'s flat log. `format_medical_memory_block` builds the
`[PATIENT SYMPTOM LIFECYCLE MEMORY]` prompt block injected into `chat.py`'s
context, explicitly instructing the LLM not to treat resolved/historical
symptoms as active. Called only by `chat.py`.

#### `app/services/weather.py`

10-minute in-memory TTL cache — **module-level global, shared across all
users/requests, not per-user**. `get_environment_snapshot()` returns the
stale cache on any error rather than `None` if a cache exists — a
persistent OpenWeather outage silently serves increasingly stale data
until process restart, never goes empty. `_overall_aqi` implements real EPA
PM2.5/PM10 breakpoint tables (hand-rolled, not an API passthrough).
`tip_for` is rule-based, respiratory-symptom-aware. Called by `home.py`,
`chat.py`.

#### `app/services/web_search.py`

DuckDuckGo (`ddgs`) + optional Firecrawl scrape (falls back to the DDG
snippet body without a key). `deep_search` caps at 5 search hits, scrapes
only the first 3. Results piped into `rag.store_web_content` +
`supermemory_client.log_web_content`. Called only by `chat.py`.

#### `app/services/ai_graph_builder.py`

`normalize_symptom_name` — layperson phrase → clinical term (Gemini), used
by `symptoms.py` and `chat.py` before logging. `build_llm_knowledge_graph`
— LLM-authored graph with real medical relationship edges, date-gap-based
fallback on LLM failure — **confirmed unused by any router**, see §11.12
(`home.py` uses `supermemory_client.build_graph` instead).
`apply_cached_knowledge` (sync, instant cache lookup) vs.
`enrich_graph_with_clinical_knowledge` (async, Gemini for uncached
nodes/edges, writes back to `graph_cache` permanently) — `home.py` applies
the cache synchronously, then fires enrichment as a background task for the
*next* request. `compute_and_store_symptom_knowledge` pre-warms the cache
on every new symptom log.

#### `app/services/audit_service.py`

`log_audit_event(...)` writes into **`patient_db.audit_logs`** (not a
separate audit database). Write failures only `print()`, never raised or
alerted. Called extensively from `auth.py` and `doctor.py` (including every
command-center *read*), and from `appointments.py`/`patient.py`. **Not
called** from `chat.py`, `profile.py`, `symptoms.py`, `mydata.py` —
coverage is concentrated on the newer V2 clinical surface.

#### `app/services/doctor_ai_service.py`

`generate_doctor_ai_support(...)` — despite being framed as AI clinical
decision support, the structured `differential_diagnoses`/
`suggested_prescriptions` fields are **entirely rule-based keyword
matching** (e.g. `"chest pain" in symptoms` → hardcoded `["Acute Coronary
Syndrome", "GERD", "Costochondritis"]`), not LLM-derived — the LLM
(`generate_completion`) is only used for the free-text `clinical_summary`
field. Also calls `emergency_triage.evaluate_emergency_triage` for a
warning banner. Contains the `suggested_diet=` kwarg bug — see §11.2.
Called only by `doctor.py`'s `/consultations/{id}/ai-assist`.

#### `app/services/facilities_service.py`

Combines a hardcoded Bengaluru seed list (`mock_data.FACILITIES`) with live
TomTom POI results (3 category queries in parallel, **hard 1-second
`asyncio.wait_for` timeout** — aggressive; a slow TomTom response is
dropped entirely, not partially used). Dedupes by lowercased name, live
results win on collision. `haversine_km` is real great-circle math. Called
only by `facilities.py`.

#### `app/services/patient_context_service.py`

Pure aggregation, no LLM calls. `build_patient_context` — one-stop
profile/conditions/allergies/consultations/prescriptions/vitals/
lab_metrics/alerts pull. `compute_adherence_rate` deliberately returns
`None` (not `0%`) when there are zero medication logs, distinguishing "no
data" from "0% adherence" — `doctor.py` correctly renders `"No data"` in
that case. `get_whats_new_changes`/`get_evidence_trace` build entirely from
real Mongo records (no fabricated placeholder data, matching the module's
own "honest empty states" design philosophy). Called only by `doctor.py`.

#### `app/services/pdf_service.py`

`generate_consultation_pdf(...)` — pure ReportLab formatting function, no
DB/LLM access of its own. Builds an A4 doc: header banner, doctor/patient
info table, vitals row, diagnosis/notes, Rx table, diet/follow-up section,
signature footer. Called from `doctor.py`'s and `patient.py`'s PDF
endpoints — **each independently fetches/assembles the same shape of data
first**, ~30 near-duplicate lines in each router with no shared helper.
This is what pulled `reportlab>=4.0.0` into `requirements.txt`.

#### `app/services/mock_data.py`

Seed/fallback fixtures only — `HOME_SNAPSHOT`, `CHAT_SOURCES`, `FACILITIES`
(6 hardcoded Bengaluru locations), `DEFAULT_PROFILE`,
`DEFAULT_DOCTOR_PROFILE`. Consumed only as a fallback when the
corresponding Mongo query is empty — never overrides live data.

### `backend/scripts/*.py` — one-liner each

| Script | Purpose |
|---|---|
| `export_data.py` | JSON backup of all Mongo collections. **Broken** — imports removed `get_db()`. |
| `import_data.py` | Restores a JSON backup. **Broken** — same. |
| `seed_symptoms.py` | One-off demo seeder (chest pain + night sweats) via `supermemory_client.log_symptom`. |
| `test_all_phases.py` | Manual end-to-end test (triage/tracking/quick-options/formatting). **Broken** — `get_db()`. |
| `test_namespace_isolation.py` | Verifies Pinecone/Supermemory per-user isolation. **Broken** — `get_db()`. |
| `test_pdf_export.py` | `TestClient` smoke test for both PDF endpoints, demo-mode headers. Not broken (uses the split DB functions). |
| `test_pipeline.py` | Manual test: symptom normalize → log → graph enrich → chat entity extraction. **Broken** — `get_db()`. |
| `test_triage.py` | Manual cases for `triage.eval_triage`. Not broken. |
| `verify_chat_adapters.py` | Manual test of `domain_adapter` tag parsing/classification against `chat.py` internals. |
| `verify_fixes.py` | Manual IDOR/patient-isolation regression check. |
| `verify_full_system.py` | Broad `TestClient` smoke test across the API, demo-mode headers. |
| `verify_phase2_fixes.py` | Manual regression check for lab-metric extraction and appointment-action fixes. |
| `verify_profiles.py` | Manual regression check for profile save/read and `_aggregate_patient_ehr_context`. |

---

## 6. Frontend — file by file

### Entry / routing

`main.tsx` — mounts `<App>` in `<BrowserRouter>`, wrapped in
`<ClerkProvider afterSignOutUrl="/">` **only if**
`VITE_CLERK_PUBLISHABLE_KEY` is set (Clerk is required in practice —
`useAuth`/`useUser` elsewhere assume the provider exists). Wrapped again in
`<ErrorBoundary>`.

`App.tsx` — full route table:
- **Public**: `/` (`Landing`), `/select-role` (`SelectRolePage`),
  `/doctor/register` (`DoctorRegistrationPage`), `/activate-account`
  (`PatientActivationPage`), `/sign-in`, `/sign-in/:role`, `/sign-up`,
  `/sign-up/:role` (all → `RoleLoginPage`).
- **Protected** (wrapped in `<ProtectedLayout>`):
  - Doctor: `/doctor/dashboard` (`DoctorCommandCenter`), `/doctor/patients`
    (`MyPatients`), `/doctor/add-patient` (`AddPatientWizard`),
    `/doctor/patient/:id` (`PatientWorkspace`),
    `/doctor/patient/:id/consult` (`ActiveConsultationSuite`),
    `/doctor/copilot` (`ClinicalCopilot`), `/doctor/analytics`
    (`DoctorAnalyticsPage`), `/doctor/appointments`
    (`DoctorAppointmentsPage`).
  - Patient: `/patient/dashboard` (`PatientDashboard`),
    `/patient/medications` (`MedicationTracker`), `/patient/diet`
    (`DietManager`), `/patient/chat` (`PatientChat`),
    `/patient/lab-reports` (`LabReports`), `/patient/appointments` and
    `/appointments` (both → `Appointments`).
  - Shared/legacy: `/find-care` (`FindCare`), `/profile` (`Profile`),
    `/chat` (`PatientChat` — always patient-mode despite the grouping),
    `/home` (`Home`), `/mydata` (`MyData`).
- `/dashboard` redirects to `/doctor/dashboard`. `<AuthTokenBridge>` mounts
  once, outside `<Routes>`.

**Dead code — not routed, don't assume it's live**: `pages/SignInPage.tsx`,
`pages/SignUpPage.tsx` (orphaned wrappers), `pages/doctor/DoctorDashboard.tsx`
(older single-page doctor workspace, superseded by `DoctorCommandCenter` +
`MyPatients` + `PatientWorkspace` + `ActiveConsultationSuite`),
`pages/doctor/ConsultationSessionModal.tsx` (used only by that orphaned
page), `pages/doctor/MultiPatientCompare.tsx` (calls a real, working
service function but is never mounted), `components/layout/HeaderNav.tsx`
(legacy top-bar nav, superseded by `NavShell`). If asked to "wire up
patient comparison" or "restore the old doctor dashboard," start here —
these files aren't broken, just unmounted.

### Auth & role-routing (read before touching login/auth flow)

A fresh, unauthenticated visitor lands on `/` (`Landing`), offering "Doctor
Portal Login" (`/sign-in/doctor`) and "Patient Portal Login"
(`/sign-in/patient`), plus a generic `/select-role`. Picking a role calls
`setActiveRoleOverride(role)` and writes `localStorage["medsys_role"]`
**before any real authentication** — just an intent marker. `RoleLoginPage`
then shows Clerk's `<SignIn>`/`<SignUp>` widget, or a "Demo Credentials"
form whose submit just calls `setDemoAuthenticated(true)` and navigates in
with **zero backend calls** — this frontend demo mode is distinct from the
backend's `MEDSYS_DEMO_MODE` auto-provisioning (see §8.9 — they connect via
the `X-Demo-Session-Id` header but neither requires the other).

Every app-shell route is nested in `<ProtectedLayout>`, which on each mount:
1. Requires a real Clerk session or `isDemoAuthenticated()`; else redirect
   to `/select-role`.
2. If real, calls `GET /api/auth/me` to ask which role this Clerk identity
   is linked to (doctor checked first, then patient — never both) and
   whether a profile exists.
3. Three outcomes: **(a)** no profile → render `ProfileSetup` inline; **(b)**
   backend's real role disagrees with the picked login role → blocking
   "account already in use" screen; **(c)** resolved and matches → proceed.
   Demo sessions skip the `/api/auth/me` round-trip.
4. Renders `<NavShell key={userId}>` with role-appropriate nav items.
5. Defense-in-depth: hard-redirects a resolved doctor away from any
   patient-only path to `/doctor/dashboard`, and a resolved patient away
   from any `/doctor/*` path to `/home` — **matters** because several
   "shared" routes (`Home`, `PatientChat` at `/chat`, `MyData`) have no
   role guard of their own.

### Pages — route, data, purpose

| File | Route | Fetches | Purpose |
|---|---|---|---|
| `pages/Landing.tsx` | `/` | none | Public hero with separate doctor/patient login entry points. |
| `pages/auth/SelectRolePage.tsx` | `/select-role` | none | Role picker → sets local override → navigates to `/sign-in/:role`. |
| `pages/auth/RoleLoginPage.tsx` | `/sign-in(/:role)`, `/sign-up(/:role)` | none | Clerk `<SignIn>`/`<SignUp>` widget OR a no-backend "Demo Credentials" shortcut. |
| `pages/auth/DoctorRegistration.tsx` | `/doctor/register` | `POST /api/auth/register-doctor` | Two-step doctor signup: details → Clerk `<SignUp>` → link. |
| `pages/auth/PatientActivationPage.tsx` | `/activate-account?token=` | `GET .../invitation/:token`, `POST .../activate-patient` | Verifies invite, then Clerk signup + activation link. |
| `pages/auth/ProfileSetup.tsx` | inline, no route | `POST .../register-doctor` or `register-patient` | Shown when a signed-in Clerk account has no linked row yet. |
| `pages/doctor/DoctorCommandCenter.tsx` | `/doctor/dashboard` | `fetchCommandCenter()` | 4 uniform KPI cards (real counts only, no hardcoded fallbacks), severity-sorted vertical priority-alert list (critical first, highlighted, scrollable), today's appointments in a side column on `xl`. |
| `pages/doctor/MyPatients.tsx` | `/doctor/patients` | `fetchAssignedPatients`, `searchPatients`, `linkExistingPatient` | Patient directory + search + link-existing modal. |
| `pages/doctor/AddPatientWizard.tsx` | `/doctor/add-patient` | `POST .../add-patient-wizard` | 3-step new-patient registration. |
| `pages/doctor/PatientWorkspace.tsx` | `/doctor/patient/:id` | overview/timeline/analysis/brief/lab-trends/whats-new/evidence/copilot/summary/pdf functions | Tabbed 360° patient record + "What's New" banner + evidence/summary modals. |
| `pages/doctor/ActiveConsultationSuite.tsx` | `/doctor/patient/:id/consult` | overview, lab-trends, create/AI-assist/finalize consultation, med-safety check, voice-parse, copilot, lab upload, diet-plan gen, lab order, pdf | 5-step guided consultation: intake/vitals → AI assist + lab OCR → Rx/diet/lab-order builder → sign-off → finalized summary. |
| `pages/doctor/ClinicalCopilot.tsx` | `/doctor/copilot` | — | Thin wrapper: `<Chat title="Clinical Copilot" doctorMode/>`. |
| `pages/doctor/DoctorAnalytics.tsx` | `/doctor/analytics` | `fetchDoctorAnalytics()` | Hand-rolled SVG donut + bar charts, condition/adherence breakdowns. Hardcoded demo numbers only while still loading, not once real data returns empty. |
| `pages/doctor/DoctorAppointments.tsx` | `/doctor/appointments` | `fetchDoctorAppointments`, `processAppointmentAction` | Appointment queue with accept/decline(+reason)/complete. |
| `pages/doctor/DoctorDashboard.tsx` | *unrouted* | `fetchAssignedPatients`, `fetchPatientTimeline` | Older single-page doctor workspace — dead code. |
| `pages/doctor/ConsultationSessionModal.tsx` | *unrouted component* | consultation create/AI-assist/finalize | Modal consultation flow, superseded by `ActiveConsultationSuite`. |
| `pages/doctor/MultiPatientCompare.tsx` | *unrouted* | `fetchMultiPatientCompare()` | Side-by-side comparison cards + AI summary — dead code. |
| `pages/patient/PatientDashboard.tsx` | `/patient/dashboard` | `fetchPatientDashboard`, `logMedicationDose`, `getProfile`, `downloadPatientConsultationPdf` | Doctor-published advice/prescriptions, diet guidelines, medication reminders. |
| `pages/patient/MedicationTracker.tsx` | `/patient/medications` | `fetchPatientMedications`, `logMedicationDose` | Active prescriptions + dose-compliance history. |
| `pages/patient/DietManager.tsx` | `/patient/diet` | `fetchPatientDiet`, `logPatientMeal` | Doctor diet guidelines + meal-logging form/history. |
| `pages/patient/PatientChat.tsx` | `/patient/chat`, `/chat` | — | `<Chat title="Ask MedSys" doctorMode={false}/>`. |
| `pages/patient/LabReports.tsx` | `/patient/lab-reports` | `fetchLabReports("pat_01")` (hardcoded id), `uploadLabReport` | OCR'd lab-report upload/list. |
| `pages/patient/Appointments.tsx` | `/patient/appointments`, `/appointments` | `fetchDoctorAvailability`, `requestPatientAppointment`, `fetchPatientAppointments` (polls every 8s) | Book against a fixed doctor's slot grid; "my requests" list. |
| `pages/Home.tsx` | `/home` | `getHomeSnapshot()` | Legacy patient home: status banner, environment/AQI, tips, symptom knowledge graph. Retries silently on 401/403 (treated as Clerk clock-skew). |
| `pages/FindCare.tsx` | `/find-care` | `getFacilities({lat,lng,radiusKm})` | Nearby-facilities map + list, geolocation, filters, manual pin mode. |
| `pages/MyData.tsx` | `/mydata` | `listMyData`, `uploadMyData`, `deleteMyDataSource` | Document vault grid with category filter, optimistic upload, delete. |
| `pages/Profile.tsx` | `/profile` | role-branched: `getProfile`/`saveProfile` or `getDoctorProfile`/`saveDoctorProfile` + `fetchCommandCenter` | Patient health-passport view/edit, or `DoctorProfileView`. |
| `pages/Chat.tsx` | wrapped by `PatientChat`/`ClinicalCopilot` | `listMyData`, `getModelStatus`, session CRUD/messages, `setSessionSources`; doctor mode adds `fetchAssignedPatients` | The shared chat UI: sessions, messages, composer (image/voice/deep-search/adapter tags), grounded-sources panel, model indicator. Doctor mode adds a patient-context selector. |

### `services/` — two incompatible mock-mode strategies coexist

**Read this before assuming any doctor/patient-portal page works without a
backend.** The original services (`chat.ts`, `facilities.ts`, `home.ts`,
`mydata.ts`, `profile.ts`, `symptoms.ts`) explicitly check `isMockMode` and
serve rich fixtures from `services/mocks.ts`. **`services/clinicalService.ts`**
— all doctor-portal, patient-dashboard/medications/diet, appointments, and
documents/lab-report code — has **no `isMockMode` branching of its own**;
every function is a bare `apiFetch`/`apiUpload`/`downloadPdfBlob` call. Its
only mock behavior comes from `client.ts`'s `getFallbackData<T>(path)`,
which recognizes exactly 5 URL substrings (`/command-center`, `/patients`,
`/overview`, `/pre-brief`, `/lab-trends`) and returns `{}` for everything
else — every consultation, medication, diet, appointment, analytics, and
lab-report endpoint included. In mock mode, most doctor/patient-portal
pages silently receive `{}` and render their fallback strings, not a
populated demo UI.

- **`client.ts`** — `apiFetch<T>`, `apiUpload<T>`, `isMockMode`, `mockDelay`
  (unchanged), plus **new**: `downloadPdfBlob(path, filename)` (GET → blob
  → browser download; **no mock-mode branch, always hits the network**),
  `authHeaders()` (Clerk-token `Authorization` + `X-User-Role` +
  `X-Demo-Session-Id`), `setAuthTokenGetter`/`setActiveRoleOverride`/
  `getActiveRoleOverride`/`setDemoAuthenticated`/`isDemoAuthenticated`,
  `getFallbackData<T>` (the partial stub above).
- **`clinicalService.ts`** (~30 functions, one per doctor/patient-portal
  endpoint) — doctor: `fetchCommandCenter`, `fetchWhatsNew`,
  `fetchEvidenceTrace`, `parseVoiceNotes`, `checkMedicationSafety`,
  `generateAIDietPlan`, `orderLabTest`, `fetchCustomHistorySummary`,
  `fetchDoctorAnalytics`, `fetchMultiPatientCompare`,
  `fetchAssignedPatients`, `searchPatients`, `linkExistingPatient`,
  `fetchPatientOverview/Timeline/TimelineAnalysis/PreConsultationBrief/LabTrends`,
  `sendDoctorCopilotQuery`, `createConsultation`, `triggerAIDecisionSupport`,
  `finalizeConsultation`. Patient: `fetchPatientDashboard`,
  `fetchPatientMedications`, `logMedicationDose`, `fetchPatientDiet`,
  `logPatientMeal`, `sendPatientClarificationChat`. Appointments/documents:
  `fetchDoctorAvailability`, `requestPatientAppointment`,
  `fetchDoctorAppointments`, `fetchPatientAppointments`,
  `processAppointmentAction`, `fetchLabReports`, `uploadLabReport`,
  `downloadDoctorConsultationPdf`/`downloadPatientConsultationPdf`.
- **`chat.ts`** — `getModelStatus`, `getChatSources`, `getSourceContent`,
  `listChatSessions`, `createChatSession`, `setSessionSources`,
  `getSessionMessages`, `deleteChatSession`/`deleteChatSource`,
  `sendSessionMessage`, `transcribeAudio` — each mock-branches to a fixture
  in `mocks.ts`.
- **`facilities.ts`**, **`home.ts`** — one function each, mock-branched.
- **`mydata.ts`** — `listMyData`/`getMyDataContent`/`deleteMyDataSource` are
  direct re-exports of the `chat.ts` equivalents; `uploadMyData` is the
  only new logic.
- **`profile.ts`** — `getProfile`/`saveProfile` (patient, localStorage-
  backed mock persistence under `medsys_patient_profile`),
  `getDoctorProfile`/`saveDoctorProfile` (doctor, `medsys_doctor_profile`).
- **`symptoms.ts`** — `logSymptom`, `listSymptoms`, `deleteSymptom`.

### `types/index.ts`

Mirrors backend Pydantic models field-for-field — **update this in the same
commit as any Pydantic model change**. Grouped by domain: identity/roles
(`UserRole`, `UserRecord`, `DoctorPatientAssignment`), clinical
(`Vitals`, `PrescriptionItem`, `AISuggestions`, `ConsultationSession`),
medication/diet (`MedicationSchedule`, `MedicationLogRecord`,
`MealLogRecord`, `DietPlan`), labs (`LabMetric`, `LabReportRecord`,
`MetricHistoryPoint`, `LabMetricTrend`), doctor workflow
(`PreConsultationBrief`, `PatientClarificationMessage`, `CommandCenterData`,
`WhatsNewChanges`, `EvidenceTrace`, `StructuredVoiceNoteOut`,
`DoctorAnalytics`, `PatientComparisonCard`, `MultiPatientCompareResult`),
appointments/alerts/audit (`AppointmentRecord`, `AlertRecord`,
`AuditLogRecord`), chat/RAG (`ChatSourceKind` — 7 values now, including
`consult_prescription`/`prescription` — `ChatSourceDetail`, `ChatSource`,
`ChatMessage` with `adapter_used?`, `ChatSession`), Find Care
(`FacilityType`, `Facility`), Home (`HomeSnapshot`, `EnvironmentSnapshot`,
`KnowledgeGraph`, `SystemStatus`, `ModelStatus`), `ProfileRecord`,
scheduling (`TimeSlot`, `DoctorAvailabilityData` — **also independently
redeclared, identically, inside `clinicalService.ts`**; minor duplication,
not a bug, but fix both if the shape ever changes).

### Components, by subdirectory

- **`components/` (top-level)**: `CommandPalette` (Ctrl/Cmd+K jump modal,
  hardcoded demo patients+shortcuts), `ErrorBoundary`, `FormattedText`
  (hand-rolled lightweight markdown for AI copilot bubbles in
  `PatientWorkspace`/`ActiveConsultationSuite` — distinct from
  `chat/Markdown.tsx`'s real `react-markdown`), `LoadError`, `PageHeader`
  (wraps cleanly on mobile; the `action` slot is `shrink-0`), `SourceModal`, `Thread` (signature animated SVG connector, used in
  `Landing` and `Home`).
- **`components/auth/`**: `AuthTokenBridge` (bridges Clerk's
  `useAuth().getToken` into the non-React `client.ts` module),
  `ProtectedLayout` (the auth/role gate described above).
- **`components/chat/`** (8 files, shared by both portals via
  `pages/Chat.tsx`): `Composer` (adapter-specialty quick-tags, source
  picker, deep-search toggle, image attach, voice + transcribe),
  `Markdown` (`react-markdown`+`remark-gfm` with styled overrides),
  `MessageBubble` (red-flag emergency styling with 911/find-care buttons,
  adapter-used badge, quick-option chips, sparkle avatar on assistant
  replies, asymmetric navy user bubble), `ModelIndicator` (specialty-
  model switcher with a simulated 60s "loading weights" progress modal,
  state in `localStorage`), `SessionList` (General Copilot vs. Patient
  Isolated sections), `SourcePicker`, `SourcesPanel`, `TypingIndicator` (pill-shaped, teal dots).
- **`components/findcare/`** (5 files): `MapView` (real TomTom/MapLibre
  `TomTomMapView` when `VITE_TOMTOM_API_KEY` is set, else a CSS
  `PlaceholderMap` — see §8.5's load-bearing worker-setup caveats, still
  applicable), `FacilityCard`, `LocationControl`, `SpecialtyChips`,
  `TypeFilter`.
- **`components/home/`** (4 files): `EnvironmentCard`, `KnowledgeGraphCard`
  (interactive SVG radial graph — hover/select nodes+edges, zoom, search,
  time-window filter, category colors — plus the symptom log/delete form),
  `StatusBanner`, `TipsCard`.
- **`components/mydata/`**: `CategoryFilter`, `DataCard`.
- **`components/profile/`**: `DoctorProfileView` (full doctor profile
  display + its own edit modal; also exports `DoctorProfileData`/
  `DEFAULT_DOCTOR_PROFILE`/`DoctorProfileStats`), `Field`, `ProfileForm`.
- **`components/layout/`**: `NavShell` (role-aware — `DOCTOR_NAV_ITEMS` vs
  `PATIENT_NAV_ITEMS`, desktop sidebar + mobile tabs, Clerk `UserButton`,
  mounts `CommandPalette`; page content is wrapped in a `max-w-[1480px]`
  container; the role badge is hidden below `xl` where the sidebar is the
  80px icon rail), `HeaderNav` (dead code, see above).

### Visual design system (`index.css`)

All visual tokens live in the `@theme` block — there is still no
`tailwind.config.js`. Notes for anyone restyling:

- **Shadows are overridden globally.** `--shadow-2xs` … `--shadow-lg` are
  redefined as warm, navy-tinted values, so every existing `shadow-xs/sm/md/
  lg` class across the app picks them up. Change them there, not per-component.
- **Base layer** sets body size/line-height, display-font headings
  (`h1–h3`), a shared 150ms transition on interactive elements, a press
  effect on `button:active`, and a teal focus ring on inputs/selects/
  textareas. **Fields with the `bg-transparent` class are exempt** from the
  ring (e.g. the chat composer's textarea, which sits inside a pill that
  draws its own `focus-within` ring) — keep that class on borderless inputs.
- **Utilities** `.surface` (card background, hairline border, `rounded-2xl`
  radius, `shadow-xs`) and `.surface-hover` (lift + teal border on hover) are the
  shared card recipe; `DataCard` uses them. Prefer them for new cards.
- Palette is unchanged: `bg-mist` background, `ink` navy, `teal-deep`
  accent, `clay-alert`, `indigo-thread`, `hairline`, `surface-card`. The chat
  uses `bg-bg-mist` (it previously used a slightly different `#f4f2eb`).
- Pages not yet restyled individually (Home, Find Care, Profile, both
  appointments pages, patients directory, registration wizard, copilot/
  consultation screens) inherit the global shadow/focus/scrollbar changes
  but still use their original card markup.

### `hooks/` and `lib/`

`hooks/useReducedMotion.ts` — unchanged. `lib/geo.ts` — `haversineKm`.
`lib/motion.ts` — `staggerContainer`, `riseIn`/`riseInReduced`,
`fadeUpMessage`, unchanged. `lib/sourceKinds.ts` — `KIND_ICON`/`KIND_LABEL`
maps, now covering 7 `ChatSourceKind` values.

### Dependencies added since the original build

`@clerk/clerk-react` (auth), `@tomtom-org/maps-sdk` + `maplibre-gl` (maps),
`react-markdown` + `remark-gfm` (chat rendering). `vite.config.ts`'s
`optimizeDeps.exclude: ['maplibre-gl', '@tomtom-org/maps-sdk']` is
confirmed still present — see §8.5.

---

## 7. Which LLM does what

| Task | Function | Fallback chain | Notes |
|---|---|---|---|
| Specialty-routed chat replies | `chat.py`'s `post_session_message` | **Remote MedGemma adapter → Ollama → Groq → Gemini** | The only call site with the remote adapter in its chain. See §10; 4 of 8 declared specialties have no real adapter behind the remote service (§11.5). |
| Triage, quick-options, title generation, graph enrichment, general tip | `complete_gemini` callers | **Gemini → Groq** (2 retries, 1.5s backoff on 429) | **No Ollama, no MedGemma adapter** — this chain is chat-reply-specific, not codebase-wide. |
| Doctor/patient copilot-style completions | `generate_completion` | **Gemini → (Ollama → Groq → Gemini)** i.e. tries `complete_gemini` first, then `_complete` | Used by `doctor.py`/`patient.py` non-chat AI features. |
| Lab-report / document OCR | `ocr.extract_text_from_file` | pymupdf text-layer only; **no vision-LLM call in the live path** | The vision-LLM OCR path (`ocr.extract_text`, Groq/Ollama vision) exists but has zero callers — see §11.10. Images are never actually OCR'd today. |
| Speech-to-text | `/chat/transcribe` | `whisper-large-v3-turbo` (Groq) | Direct multipart proxy; 503s cleanly with no `GROQ_API_KEY`. |
| Consultation PDF generation | `pdf_service.py` | n/a (ReportLab, not an LLM) | Requires the `reportlab` package. |
| Web search decision | `decide_web_search` | Groq tool-calling only | Returns `None` immediately on any other active provider. |

---

## 8. Design decisions & gotchas (read before "fixing" these)

### 8.1 Chunk overlap and `sources.content`

`_chunk_text` uses 150-char overlap so retrieval doesn't miss content
straddling a boundary. The full original document text is stored directly
on the `sources` doc (not reconstructed by joining chunks — joining
duplicated overlapping text and visibly broke Markdown tables early on).
This still holds even though the vector storage backend changed from Mongo
to Pinecone (§11) — `sources.content` remains the source of truth for the
document-reader UI.

### 8.2 Session-scoped RAG grounding

`rag.retrieve` takes an explicit `allowed_source_ids` list; `chat.py`
always passes one (session's own chat history + user-selected My Data
cards + any fresh deep-search results). An unselected document stays
invisible to a session's answers no matter how relevant. If you add a new
caller of `retrieve`, decide its `allowed_source_ids` deliberately.

### 8.3 Reasoning-model `max_tokens` truncation

Open reasoning models (e.g. `openai/gpt-oss-20b` on Groq) emit an internal
chain-of-thought that consumes `max_tokens` budget before any answer
tokens — a low budget can produce `finish_reason: "length"` with an
**empty** `content` field. Budget at least ~300–400 tokens for any new
short-output Groq call on this model family, or add explicit empty-content
handling.

### 8.4 Home never shows a hardcoded fallback alert

`mock_data.HOME_SNAPSHOT["alert"]` is `None` and `["status"]` is
`"stable"` by design — `home.py` always computes the real status/alert
from live symptom data (never gates that computation behind a key-presence
check), so nothing on Home ever looks like a real detection when it isn't
one. `environment`/`tip` are the only fields that legitimately fall back to
static mock content (weather-based, clearly placeholder-shaped).

### 8.5 The MapLibre/TomTom worker setup is load-bearing

`components/findcare/MapView.tsx`'s `setWorkerUrl()` call at module scope
(before any map is constructed) and `vite.config.ts`'s
`optimizeDeps.exclude: ['maplibre-gl', '@tomtom-org/maps-sdk']` are both
required — without them, MapLibre v6 silently never paints under Vite's
bundler (a documented MapLibre v6 + bundler issue). Confirmed both are
still present in the current codebase. The old CDN-script-tag approach to
loading TomTom's SDK is dead (TomTom retired that endpoint); the app uses
the real npm packages now — don't reintroduce a CDN script tag.

### 8.6 `qwen/qwen3.6-27b` image limit

3 images per Groq vision request is a hard vendor limit for this specific
model (confirmed against a live 400 response), not a conservative choice.
Moot for the current live upload flow since that path doesn't call the
vision-LLM OCR function at all (§11.10) — but relevant if you re-wire it.

### 8.7 Chat has no direct file upload

Uploads happen exclusively through My Data / Documents (richer pipeline:
OCR, LLM report, classification, Pinecone ingestion). Chat's paperclip
opens a source picker over existing documents instead. Explicit
architectural choice, not a missing feature.

### 8.8 Two Mongo databases, never mix them

See §4. Doctor account/credential data lives in `medsys_doctor`; literally
everything else lives in `medsys_patient`. `hybrid_db_service.py` only
touches `medsys_patient` — even documents uploaded by a doctor on a
patient's behalf land there, never in the doctor database. Decide the
target database explicitly for any new write; don't default by habit.

### 8.9 Auth resolution and demo mode, in full

`clerk_auth.get_current_user` decodes the Bearer JWT via Clerk's JWKS
(cached `PyJWKClient`, RS256, issuer pinned to `settings.clerk_issuer`). If
a valid token exists, **role is decided purely by which collection has a
`clerk_id`-linked record** — `doctor_db.doctors` checked first, then
`patient_db.patients`; if neither, the identity resolves to the raw Clerk
id with role forced to `"patient"` (so legacy Mongo-keyed routes keep
working for an account that hasn't finished registration, but always as a
patient). **The client-sent `X-User-Role` header is never consulted for a
real Clerk session** — only in the demo-mode branch, where there's no real
identity to protect. If no bearer token is present at all: demo mode
(`MEDSYS_DEMO_MODE`, default true) auto-provisions an isolated
`doc_demo{hash}`/`pat_demo{hash}` record keyed by the client-supplied
`X-Demo-Session-Id` header (role chosen by `X-User-Role` in this branch
only) — two different demo browsers never collide. If demo mode is off,
absence of a token is a hard 401. Frontend "Demo Credentials" login
(`setDemoAuthenticated`) and backend `MEDSYS_DEMO_MODE` are independent
mechanisms that happen to connect via this header — see §6's auth section.

### 8.10 Two frontend mock-mode strategies, only one is populated

See §6's services section — `getFallbackData()` in `client.ts` is a
**partial** stub (5 URL substrings), unlike the rich `mocks.ts` fixtures
the original pages use. Setting `VITE_API_BASE_URL=` (empty) does not make
the whole app demoable; it only fully mocks the pre-existing patient-side
pages, not the doctor portal or newer patient-portal screens.

### 8.11 `MEDGEMMA_ADAPTER_URL` points at a Colab notebook, not a stable service

The remote MedGemma multi-adapter endpoint (§10) is an ngrok tunnel into a
live Google Colab runtime. It only exists while someone has that notebook
open and running; ngrok free-tier URLs rotate on tunnel recreation, and
Colab runtimes disconnect after inactivity or ~12 hours.
`call_remote_medgemma_adapter` already degrades silently to
Ollama/Groq/Gemini on any failure — correct and intentional, not a bug to
fix with retries — but if specialty answers seem to have quietly stopped
reflecting the fine-tuned adapters, check whether the notebook is still
running and whether `MEDGEMMA_ADAPTER_URL` matches its current ngrok URL
before debugging anything else.

---

## 9. Adding a new feature — where things go

- **New page**: add to `App.tsx` routes + the correct role's `NAV_ITEMS`
  array in `NavShell.tsx`, create the component, add types to
  `types/index.ts`, add a `services/*.ts` function. Decide up front
  whether it needs a real mock-mode fallback (`chat.ts`-style `isMockMode`
  branch) or is fine falling through to `clinicalService.ts`'s bare-fetch
  pattern (only fine if a backend is assumed).
- **New backend data that should ground chat**: route it through
  `rag.ingest_report`/`store_web_content` (Pinecone + `sources` mirror) so
  it's retrievable, and add a matching `supermemory_client.log_*` call for
  long-term memory.
- **New LLM-backed feature**: add to `model_router.py`. Pick
  `_complete`/`generate_reply` (Ollama-first) vs. `complete_gemini`
  (Gemini-first, no Ollama) deliberately based on whether local-model
  support matters for that feature — don't assume one chain everywhere
  (§7). If it's meant to be specialty-aware, route through
  `domain_adapter.resolve_adapter` first with the same silent-fallback
  pattern as chat.
- **New env var**: add to `Settings` in `config.py` **and** to
  `.env.example` — and while you're there, backfill the currently-missing
  ones listed in §3.
- **New database write**: decide explicitly which of `medsys_doctor` /
  `medsys_patient` it belongs to (§4, §8.8) before writing any code.
- **New audit-worthy action**: call `audit_service.log_audit_event`
  directly — coverage is currently uneven (concentrated on `doctor.py`/
  `auth.py`), so don't assume a new route gets audited automatically.

---

## 10. Fine-tuning notebooks — the MedGemma specialty adapters

Outside this repo, four Google Colab notebooks were used to fine-tune and
serve three LoRA adapters on top of `google/medgemma-4b-it` (Google's 4B
multimodal medical instruction-tuned model), and to stand up the multi-
adapter HTTP service that `backend/app/services/domain_adapter.py` calls
via `MEDGEMMA_ADAPTER_URL`. These notebooks are not part of the repo's
version control — this section is the only record of what they do. If
asked to retrain, extend, or debug an adapter, this is the starting point;
the notebooks themselves must be re-fetched from their Google Drive links
to make changes.

### 10.1 Ophthalmology adapter — training (30 cells)

The one **full training** notebook among the four (radiology and
dermatology were presumably trained in an equivalent notebook not included
in this batch — only their *testing* notebooks were available for this
audit; treat their hyperparameters as "presumed identical to
ophthalmology's" unless their own training notebook surfaces).

- **Base model**: `google/medgemma-4b-it` via `AutoModelForCausalLM`,
  4-bit NF4 quantization (`bnb_4bit_compute_dtype=torch.float16,
  bnb_4bit_use_double_quant=True`).
- **Dataset**: `BaekSeungJu/Ophthalmology-EQA-v3` (Hugging Face), reformatted
  into `"Instruction: Answer the following ophthalmology question.\n\n
  Question: {q}\n\nAnswer: {a}"`.
- **Tokenization**: `MAX_LENGTH = 256`, truncation + max-length padding.
- **LoRA config**: `r=16, lora_alpha=32, lora_dropout=0.05, bias="none"`,
  `task_type="CAUSAL_LM"`, targeting **only the language-model attention
  projections** across all 34 layers —
  `language_model.layers.{0..33}.self_attn.{q,k,v,o}_proj` — explicitly
  excluding the vision tower (verified post-training by asserting zero
  `vision_tower` params carry `lora_` weights).
- **Training run actually used**: only **5,000** examples (a commented-out
  10,000-example variant is left in but unused), 1 epoch, batch size 1 with
  gradient accumulation 4, `learning_rate=2e-4`,
  `optim="paged_adamw_8bit"`, `fp16=False, bf16=False` (compute happens
  through the 4-bit quantized path), via plain `transformers.Trainer` (not
  TRL's `SFTTrainer`, despite `trl` being installed).
- **Output**: adapter saved, zipped, downloaded — this zip is the artifact
  later uploaded into the multi-adapter serving notebook (§10.4).
- **In-notebook eval**: qualitative base-vs-adapter comparison on 5 fixed
  ophthalmology questions — no quantitative metric computed here (contrast
  with §10.2's held-out F1 eval).

### 10.2 Radiology adapter — testing only (15 cells)

Explicitly **"No training happens in this notebook"** — the adapter was
trained elsewhere. Documents the adapter's shape: 272 tensors, 136 wrapped
modules (34 layers × q/k/v/o, same target-module pattern as §10.1),
8,912,896 parameters (all FP32), 0 vision keys, reported train/val loss
0.4524/0.1962.

- **Task**: given a free-text chest X-ray report, extract findings as a
  comma-separated list of standardized names (structured extraction, not
  open-ended Q&A). The exact instruction string is load-bearing — the
  notebook's own troubleshooting table warns that drift from the trained
  string degrades output toward base-model prose instead of clean labels.
- **Loading quirk**: base model loaded with `dtype=torch.float32` for
  non-quantized weights (embeddings, norms) even though it runs 4-bit —
  documented as mandatory (Gemma-3-family models overflow to NaN logits in
  pure fp16, causing greedy decoding to emit `<pad>` forever). An explicit
  NaN guard cell asserts this didn't happen.
- **Verification cells**: inspects the adapter's safetensors header
  directly (no model load needed) to assert module/parameter counts and
  absence of vision keys; after loading, cross-checks every `lora_A`/
  `lora_B` tensor exists in the live state dict and that no `lora_B` is
  all-zero (would mean that module never received gradient — a structural
  no-op despite being "attached").
- **Quantitative held-out eval**: reproduces the exact held-out split from
  the (unseen) training notebook — `dnamodel/xraydar-reports` dataset,
  `MAX_LENGTH=320` filter, `SEED=42` shuffle, first 250 post-filter
  examples as held-out, actually scores 30 of them — reports exact-match,
  Jaccard, precision, recall, F1 for adapter vs. base. Notebook's own note:
  a near-zero base-model score is expected (it was never taught this label
  vocabulary), judge the adapter row and the size of the gap instead.

### 10.3 Dermatology adapter — testing only (12 cells)

Same structural pattern as §10.2, but for an **open-ended Q&A task**
(acne causes/symptoms, atopic vs. contact dermatitis, ABCDE mole criteria,
first-line psoriasis treatment) with no rigid output format — no
quantitative scoring cell, only qualitative side-by-side generation. Uses
`AutoModelForImageTextToText` + `AutoProcessor` rather than radiology
testing's `AutoModelForCausalLM`/`AutoTokenizer`, even though neither
notebook passes an actual image — worth normalizing if these notebooks are
ever consolidated, not a functional bug as-is.

### 10.4 Multi-adapter deployment (26 cells) — produces the live `MEDGEMMA_ADAPTER_URL`

Loads one 4-bit-quantized base model, then attaches all three trained
adapters as *named* PEFT adapters on that single base
(`PeftModel.from_pretrained(..., adapter_name="radiology")`, then
`.load_adapter(..., adapter_name="dermatology")` and `"ophthalmology"` on
the same model object) — only one copy of the base weights is ever
resident in VRAM; switching specialty is `model.set_adapter(name)`, O(1),
not a reload.

- **Serving layer**: a small FastAPI app (`"MedGemma Multi-Adapter API"`)
  with `GET /health`, `GET /adapters`, and `POST /chat` (`{adapter,
  question}` → 400 with `"Unknown adapter. Available: [...]"` if `adapter`
  isn't one of the three loaded names, else switches and generates with
  `max_new_tokens=512`, greedy decoding).
- **This is the exact contract `domain_adapter.call_remote_medgemma_adapter`
  speaks.** **Confirmed gap** (see §11.5): `domain_adapter.py`'s
  `CANONICAL_ADAPTERS` declares 8 specialties, but this service only
  recognizes 3. A message classifying into `pathology`/`chest_xray`/
  `cardiology`/`clinical_reasoning` gets a 400 here, which
  `call_remote_medgemma_adapter` treats the same as any other failure
  (falls back to local models) — never a crash, but 5 of 8 declared
  specialties (including `"general"`) never reach a fine-tuned adapter.
- **Serving mechanics**: `uvicorn.run` in a background `threading.Thread`
  inside the Colab runtime (so the cell returns immediately), smoke-tested
  locally, then exposed via `pyngrok` (`ngrok.connect(8000)`). The
  resulting public URL is what gets pasted into `backend/.env` as
  `MEDGEMMA_ADAPTER_URL` — see §8.11 for why this URL is fragile/ephemeral.
- **Prompt format used by this service**: a plain `"Answer the following
  medical question accurately and clearly.\n\nQuestion: {q}\n\nAnswer:"`
  template — notably simpler than `domain_adapter.build_specialty_prompt_preamble`'s
  richer per-domain instructions (scope, structured Findings/
  Interpretation/Next-Steps format, explicit 512-token budget). Verify in
  `chat.py` whether that preamble is actually prepended to the question
  before this call, or whether it's currently dead prompt-engineering that
  never reaches the remote model.

### 10.5 Practical implications

- Adding a 4th specialty adapter: (1) fine-tune with the same LoRA
  target-module pattern so it stays compatible with the multi-adapter
  loading code, (2) add its zip to the deployment notebook's
  `adapter_files` dict and re-run the load cells, (3) add a matching entry
  to `CANONICAL_ADAPTERS` in `domain_adapter.py` with real keywords, (4)
  re-deploy the ngrok tunnel and update `MEDGEMMA_ADAPTER_URL`.
- The three live adapters are narrow specialists: radiology's was trained
  to extract structured findings from report *text* only (nothing in any
  of these notebooks fine-tunes on the vision tower — despite this being a
  multimodal model), and all three trained on ≤5,000 examples for 1 epoch.
  Don't expect adapter answers to generalize far outside their trained
  task shape.

---

## 11. Known bugs & dead code (confirmed by this audit)

Everything below was directly confirmed by reading the code — grep for
call sites where noted. Fix or route around these deliberately; don't
assume the docstring/name of a function describes what it actually does.

### 11.1 `POST /api/patient/chat` returns 500 on every call

`app/routers/patient.py`'s `patient_clarification_chat` constructs
`PatientClarificationMessage` with `role=`, `content=`, `is_red_flag=`,
`emergency_guidance=` kwargs, but the Pydantic model in `models_v2.py`
requires `session_id`, `sender`, `message` (no defaults, none of which
match). This raises a `ValidationError` on construction — the endpoint
cannot currently succeed. The frontend's `sendPatientClarificationChat` in
`clinicalService.ts` will always receive an error.

### 11.2 `suggested_diet=` kwarg is silently dropped

`doctor_ai_service.generate_doctor_ai_support` constructs `AISuggestions`
with `suggested_diet=diet`, but the real field name is
`suggested_lifestyle_advice`. Pydantic v2's default `extra="ignore"`
silently drops the unrecognized kwarg — the diet recommendations are
computed and then discarded; `suggested_lifestyle_advice` always comes
back `[]` from the AI-assist path.

### 11.3 Appointment availability slot-matching is broken for most slots

`appointments.py`'s `GET /availability` builds `booked_times` by checking
`slot in appt_date_str` — a string like `"09:00 AM"` is never literally
contained in an ISO timestamp like `"2026-09-05T10:00:00Z"`. It's
backstopped by a hardcoded special case for only the `09:00`/`10:00` slots.
Every other slot (`11:30 AM`, `02:00 PM`, `03:30 PM`, `04:30 PM`) can never
be marked busy through this logic even if genuinely booked. Reads as an
unfinished partial implementation, not a subtle edge case.

### 11.4 Every parsed lab metric gets glucose's reference range

`hybrid_db_service.process_and_store_lab_report` hardcodes
`reference_min=70.0, reference_max=99.0` (glucose's normal range) for
**every** metric it stores, regardless of what it actually is — HbA1c,
cholesterol, etc. all get glucose's numbers. This discards the real
per-metric `reference_range` string that `model_router.extract_lab_metrics`
already returns. Any "is this value abnormal" UI logic downstream of
stored `lab_metrics` is currently wrong for non-glucose metrics.

### 11.5 4 of 8 "canonical adapters" have no real trained model behind them

See §10.4. `domain_adapter.CANONICAL_ADAPTERS` declares `pathology`,
`chest_xray`, `cardiology`, `clinical_reasoning`, and `general` as
selectable specialties, but the remote MedGemma service only actually
serves `radiology`, `dermatology`, `ophthalmology`. The other 5 fall back
to the local LLM chain silently — functionally fine, but don't assume
routing a message to one of them produces a fine-tuned-specialist answer.

### 11.6 `POST /doctor/voice-parse` is a hardcoded stub

Returns a canned `StructuredVoiceNoteOut` regardless of input, only
echoing `raw_speech_text` into `doctor_notes`. Not wired to any speech-to-
text or LLM structuring despite being documented as an "AI Structurer."

### 11.7 `POST /doctor/lab-orders` is write-only

Creates a `lab_orders` document; no endpoint anywhere in the codebase
reads this collection back (no "pending lab orders" list view exists).

### 11.8 Three orphaned functions in `hybrid_db_service.py`

`store_ai_chat_message`, `save_ai_insight`, `finalize_doctor_clinical_decision`
are fully implemented (writing to `ai_chat_sessions`/`ai_chat_messages`/
`ai_generated_insights`/`consultations`/`prescriptions`) but have **zero
call sites** anywhere in `app/routers` or `app/services` — confirmed by
grep. `doctor.py`'s actual consultation-finalize path writes directly to
Mongo instead of calling `finalize_doctor_clinical_decision`. These read as
a superseded or parallel implementation.

### 11.9 Documents router: safe by omission, not by explicit check

`documents.py`'s `list_lab_reports`/`upload_lab_report` compute
`target_id = patient_id if user.role == "doctor" else user.user_id` — a
patient's own `?patient_id=` query param is simply ignored/overridden
rather than explicitly validated and rejected. The net effect is safe
today, but there's no explicit "you may not request another patient's
data" check; if the branching logic is ever refactored, this could regress
silently into an IDOR.

### 11.10 Uploaded images are never actually OCR'd

The live document-ingestion path (`ocr.extract_text_from_file`, called by
`hybrid_db_service.ingest_unified_medical_document`) returns a placeholder
string for image uploads ("Image Document ... uploaded. Visual content
processed.") — it never runs OCR on images, only on PDFs with a text layer
and plain-text files. The actual vision-LLM OCR implementation
(`ocr.images_from_upload` / `ocr.extract_text`, which does the real
Groq/Ollama vision-model work) exists in the same file but has **zero
callers anywhere in the codebase** (confirmed by grep). If a user uploads a
photo of a lab report or prescription, its text is not extracted today.

### 11.11 `med_safety.apply_safety_guardrails` is unused

`chat.py` imports the `med_safety` module, but the one function it defines
has zero call sites. It's a prompt-string formatter (prepends an
empathetic-persona system prompt), not a safety-check function despite the
name — and isn't invoked regardless.

### 11.12 `ai_graph_builder.build_llm_knowledge_graph` is unused

Fully implemented (LLM-authored graph with real medical relationship
edges, date-gap fallback) but **no router calls it** — `home.py` uses
`supermemory_client.build_graph` (always-fully-connected, day-gap-labeled
edges) instead, a different and simpler graph shape. Reads as a superseded
alternate implementation, similar to §11.8.

### 11.13 5 of 12 backend scripts are broken

`export_data.py`, `import_data.py`, `test_all_phases.py`,
`test_namespace_isolation.py`, `test_pipeline.py` all import
`app.db.get_db`, a function removed when the single-database design was
split into `get_doctor_db()`/`get_patient_db()` (§4). They fail at import
time until updated to target one or both new databases explicitly.

### 11.14 `.env.example` is stale

Missing `PINECONE_API_KEY`/`PINECONE_INDEX`, `TOMTOM_API_KEY`,
`GEMINI_API_KEY`/`GEMINI_MODEL`, `MEDGEMMA_ADAPTER_URL`, and
`MEDSYS_DEMO_MODE` — all of which exist in `config.py`'s `Settings` and
are set in the live `.env`. A fresh clone following `.env.example` alone
will be missing several working features.

### 11.15 Frontend dead code inventory

`pages/SignInPage.tsx`, `pages/SignUpPage.tsx`, `pages/doctor/DoctorDashboard.tsx`,
`pages/doctor/ConsultationSessionModal.tsx`,
`pages/doctor/MultiPatientCompare.tsx`, `components/layout/HeaderNav.tsx` —
none are imported from `App.tsx`'s route table or from any live component.
See §6 for what each was superseded by.
