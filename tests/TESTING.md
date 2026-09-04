# Testing Summary

The current automated test suite covers the original O2C prototype flow, controller routing, deterministic agent logic, persistence, human-review API behaviour, case reconstruction, seeded live cases, and Azure configuration safeguards.

## Running the tests

From the project root, with the Python environment activated:

```powershell
pytest -q
```

Current result on the supplied project snapshot:

```text
43 passed
```

## Main areas covered

- End-to-end mocked O2C success and failure flows
- Human-controller success, failure and dunning paths
- Agent controller routing for Invoice QA, Cash Application and Dunning
- Invoice QA deterministic three-way-match checks
- Invoice QA AI-output validation and human-handover policy
- Verification that clean Invoice QA cases bypass the AI path
- Cash Application exact-reference matching
- Cash Application ambiguity handling
- Cash Application unique multi-invoice split matching
- Cash Application database persistence and duplicate-safe escalation
- Verification that `PAY-LIVE-001` runs through the deterministic path without an AI call
- Dunning deterministic handling for disputed and not-due invoices
- Dunning AI-response validation and high-risk escalation
- Azure configuration error handling
- Review-list and 404 API behaviour
- Invoice QA human approval persistence and resolution timestamps
- Cash allocation total validation and over-allocation protection
- Manual payment application persistence
- Dunning human-resolution history persistence
- Agent Activity endpoint
- Recent Cases resolution timestamps
- Case Overview confirmed payment relationships
- Verification that unprocessed payments do not pull speculative candidate invoices into Case Overview
- Seed verification for `INV-LIVE-001`, `PAY-LIVE-001`, and `INV-LIVE-002`

## Test isolation

Database tests use an isolated in-memory SQLite database. They do not modify the normal `erp_database.db` demonstration database.

AI calls are mocked for automated tests, so the test suite does not consume Azure OpenAI credits or depend on network availability.

## Minor issue identified during testing

`INV-LIVE-001` was initially seeded with `InvoiceQAStatus.MISMATCH`, even though it is intended to represent an unprocessed live Invoice QA case. This has been corrected to `InvoiceQAStatus.PENDING` in the tested version.

## Remaining manual testing

The automated suite primarily validates backend, persistence and agent-control behaviour. Before submission, the Vue interface should still receive a short manual smoke test in a browser: navigation, review selection, review resolution, payment allocation input, Case Overview search and refresh after a live-agent run.

## Warnings

The suite currently reports deprecation warnings around `datetime.utcnow()` and one SQLAlchemy legacy `Query.get()` call in a test. These do not cause functional test failures, but they can be modernised later if desired.
