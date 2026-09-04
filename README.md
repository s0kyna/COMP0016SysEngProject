# COMP0016 Systems Engineering Project
## Agentic Order-to-Cash Operations Platform

This project implements an agentic Order-to-Cash system with three specialist workflows:

- Invoice QA / three-way matching
- Cash Application
- Dunning / Collections
- Human-in-the-loop review
- Agent activity and audit trails
- Case reconstruction

The backend uses Python, FastAPI, SQLAlchemy and SQLite.  
The frontend uses Vue 3 and Vite.

---

# Running the Application

## 1. Backend setup

From the project root:

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Create/reset the demonstration database:

```powershell
python seed_data.py
```

Start the backend:

```powershell
uvicorn api:app --reload
```

The backend runs at:

```text
http://127.0.0.1:8000
```

API documentation:

```text
http://127.0.0.1:8000/docs
```

---

## 2. Frontend setup

Open another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Then open:

```text
http://localhost:5173
```

---

# Demo Data

The seeded database contains both automated decisions and human-review cases.

Useful examples:

| Case | Demonstrates |
| --- | --- |
| `INV-1001` | Invoice QA exception requiring human review |
| `INV-1002` | Automated Invoice QA |
| `PAY-2001` | Ambiguous Cash Application case |
| `PAY-2004` | Automatic multi-invoice payment split |
| `INV-3001` | Dunning case requiring human review |
| `INV-3002` | Automated Dunning decision |

Run:

```powershell
python seed_data.py
```

at any time to restore the original demonstration state.

---

# Live Agent Examples

The seed also contains unprocessed records for live execution:

| Record | Workflow |
| --- | --- |
| `INV-LIVE-001` | Invoice QA |
| `PAY-LIVE-001` | Cash Application |
| `INV-LIVE-002` | Dunning |

### Cash Application

```powershell
python -m agents.cash_application PAY-LIVE-001
```

`PAY-LIVE-001` demonstrates deterministic payment matching and does not require Azure OpenAI.

### Invoice QA

```powershell
python -m agents.invoice_qa INV-LIVE-001
```

### Dunning

```powershell
python -m agents.dunning INV-LIVE-002
```

Cases requiring AI interpretation require Azure OpenAI credentials.

After running an agent, refresh the web application to view the resulting Agent Activity, Human Review and Case Overview records.

---

# Azure OpenAI

For live AI cases, create a `.env` file in the project root:

```env
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_API_VERSION=
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4.1-mini
```

Do not commit `.env` or API keys.

---

# Reset Demo

To restore all seeded examples:

```powershell
python seed_data.py
```
