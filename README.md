# NaguAuto CRM — runnable local prototype

This is a working local workflow prototype using Python, SQLite, vanilla browser JavaScript and ReportLab. It is not the proposed React/.NET/PostgreSQL production implementation. It uses synthetic customer records and does not import the Access database.

## Open the running application

http://127.0.0.1:8765

- Email: `demo@naguauto.local`
- Default local password: `NaguDemo2026!`

## Start on this Mac

Run `./run.command` from this folder on macOS/Linux. Keep its terminal running. Stop it with Control-C. If another copy is running, use the existing browser address rather than starting another copy.

The launcher creates a Python virtual environment and installs `requirements.txt` from PyPI. Python 3.9+ is required; Python 3.12 was used for verification. You can also run:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

Set `NAGU_PASSWORD` to override the demo password; `PORT` overrides 8765. The server listens only on 127.0.0.1. It is not intended to be exposed on a network.

## Try the workflow

1. Sign in and open Customers. Three fictional customers are included.
2. Open Alex Morgan or create a customer. Edit contact details and internal notes.
3. Create an invoice. Enter service descriptions, quantities, prices, vehicle details and customer-facing notes.
4. Save the draft, revisit it, then choose Review & finalize. Finalization allocates an invoice number and stores an actual PDF.
5. Open PDF / Print. Use the browser PDF controls to download or print.
6. Create an email preview. Enter a recipient and open Email outbox to download an `.eml` message containing the invoice PDF. No email is transmitted.
7. Update customer or business details. Previously finalized invoice PDFs stay unchanged.

## Included

- Local authenticated session, sign-out and CSRF protection for changes.
- Customer creation, editing, internal notes and search across name, company, phone, email, customer ID and finalized invoice number.
- Customer invoice history and dashboard.
- Editable drafts with stale-update protection.
- Server-side decimal calculations; line amounts rounded to cents, then invoice-level percentage tax rounded half-up.
- Transactional invoice numbering; repeated finalization does not allocate another number.
- Immutable finalized invoice workflow and stored PDF bytes.
- PDF attachments in downloadable local email previews.
- Business settings and a database audit log.
- Persistent SQLite storage in `data/nagu.sqlite3`.

## Deliberate prototype limits

- One demo administrator, no staff administration, MFA, external identity or production session key management.
- No real email delivery, delivery webhooks, background queue or SMTP configuration. Email previews are explicitly marked not sent.
- No credits, voids, payments, balances, vehicle directory or legacy migration.
- A 13% illustrative default tax is configurable; it has not been validated against NaguAuto's Access calculations or business rules.
- All invoices are marked local prototype/test. Do not issue them as production invoices.
- PDF generation is synchronous inside finalization for this small demo; production should use the durable jobs described in the architecture.
- Customer and invoice lists are loaded into the browser; no production-scale pagination/performance claims.
- No configured backups or production monitoring. Before experiments, stop the server and copy the data directory if you want a backup. Do not rewind a production invoice sequence by restoring this demo database.
- Sessions expire after eight hours or a server restart. Local HTTP is intentional; production requires HTTPS.

## Verification

Run `python test_app.py` in an environment with ReportLab installed. Tests use a separate temporary database and cover authentication/CSRF, customer updates/conflicts, draft creation, decimal calculations, finalization idempotence, finalized-edit rejection, snapshot isolation, PDF output and matching email attachments. JavaScript syntax was checked with Node. These tests do not replace browser end-to-end tests, concurrent load tests or a security review.

Automated visual browser verification could not run because the browser's admin-policy check was unavailable. No rendering verification is claimed.

Do not commit `data/`, customer exports, Access files or secrets. The supplied GitHub repository is public. Only synthetic demonstration records are included in this repository.
