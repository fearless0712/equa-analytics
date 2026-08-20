# EQUA Analytics

EQUA Analytics turns a sales CSV into validated KPIs, monthly trends, dimension
rankings, data-quality findings, and a decision-support dashboard. It helps
business users review performance without relying on AI for calculations.

Version 1.0 is the first public portfolio and MVP release. Use only fictional
or non-confidential data unless your deployment and provider policies have been
reviewed for the intended data.

## Key Features

- Strict CSV validation and normalization before analysis
- Exact Decimal-based sales calculations and pandas aggregation
- Monthly, product, category, and regional performance analysis
- Five interactive Plotly charts with supporting accessible tables
- Deterministic change, concentration, quality, and potential-outlier detection
- Optional, button-triggered AI interpretation with a deterministic Fake mode
- Self-contained HTML and PDF business report exports with five static SVG charts

## Processing Flow

`CSV bytes -> syntax and header validation -> value normalization -> pandas ->
KPI and dimension analysis -> deterministic insights -> dashboard`

AI is a separate optional path. Pressing **Generate AI Insights** re-sends the
same CSV and repeats the server-side pipeline before building a bounded summary.
No database or client-supplied analysis snapshot is trusted.

## CSV Input

- Required: `date`, `product`, `category`, `region`, `quantity`, `unit_price`
- Optional: `discount`, `customer_type`
- Formula: `sales = quantity x unit_price x (1 - discount)`
- Encoding: UTF-8 or UTF-8 with BOM
- Limits: 5 MB and 10,000 data rows
- Date: strict `YYYY-MM-DD`; quantity: non-negative integer
- Unit price: non-negative Decimal up to 1,000,000,000
- Discount: Decimal from 0 to 1; blank defaults to 0
- Text fields: maximum 200 characters

Uploads are processed in memory and are not persistently stored. NUL bytes,
unknown or duplicate normalized headers, malformed rows, exponent notation,
NaN, and Infinity are rejected. Duplicate data rows are reported but retained.

## Deterministic Analytics

The application calculates total sales, quantity, transaction count, average
order value, average unit price, and unique product/category/region counts.
Monthly analysis fills missing calendar months with explicit imputed zero points.
Rankings use deterministic tie-breaking. No cost or gross-profit metric is
claimed because cost is not part of the v1.0 input contract.

Potential outliers use an IQR rule with a minimum sample size. They are review
candidates, not declarations of fraud or bad data, and no row is removed.

## AI Insights

AI is optional and does not calculate KPIs, detect anomalies, or receive raw CSV
rows. It receives only bounded calculated metadata, KPIs, six recent months,
top-five dimensions, and limited deterministic insights. The context is capped
at 12,000 serialized characters.

- `AI_MODE=disabled`: dashboard works without AI
- `AI_MODE=fake`: deterministic local/test output without external communication
- `AI_MODE=openai`: official OpenAI SDK and Responses API Structured Outputs

OpenAI requests use `store=False`, a timeout, limited retries, and a 1,800-token
output limit. Provider errors never replace the calculated dashboard. AI output
is decision support and requires human review. Provider retention policies may
still apply independently of `store=False`.

## Security and Privacy

- Expiring signed CSRF tokens protect every POST route
- AI requests are limited to 3 per 10 minutes per direct client IP
- CSP keeps `script-src 'self'`; Plotly requires only inline style permission
- HSTS and Secure cookies are enabled in production
- All responses use `Cache-Control: no-store` and restrictive security headers
- API keys and the production secret are environment variables and are not logged
- CSV content, filenames, AI context, prompts, and AI output are not logged

The rate limiter is in-memory and suitable only for the v1.0 single-worker
deployment. Multiple workers or instances require a shared store such as Redis.

## Report Exports

Reports are generated from deterministic analytics without requiring AI. Both
self-contained HTML and PDF exports are processed in memory and are never
persistently stored. PDF generation uses WeasyPrint and permits one concurrent
render per process, with a separate limit of five requests per ten minutes per
direct client IP. These controls assume a single-worker deployment.

PDF rendering can be CPU- and memory-intensive on Render Free instances. The
v1.0 limits report contents and enforces a 5 MB generated PDF cap.

## Tech Stack

Python 3.12, FastAPI, Pydantic Settings, pandas, Plotly, Jinja2, WeasyPrint,
OpenAI Python SDK, pytest, and Uvicorn. Version 1.0 has no database, authentication,
or file persistence.

## v1.0.0 Release Notes

Released 2026-08-20.

- Validated CSV-to-dashboard deterministic analytics with accessible charts and tables
- Unified Business Report export for deterministic and AI-assisted HTML/PDF output
- Bounded optional AI interpretation with evidence-backed recommendations and fallback behavior
- Self-contained report HTML, static SVG charts, and WeasyPrint PDF rendering
- Signed CSRF protection, bounded uploads and outputs, rate limits, and PDF concurrency control
- Reproducible Render Docker runtime with Python 3.12, native PDF dependencies, and health checks

## Testing

The suite covers CSV boundaries, normalization, Decimal calculations, monthly
and dimension analysis, insights, charts, XSS handling, CSRF, rate limiting, AI
context limits, Fake AI, and mocked OpenAI responses. Automated tests never call
the real OpenAI API.

```bash
pytest --cov=app --cov-report=term-missing
```

## Local Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000` and upload `sample_data/valid_sales.csv`.

## Production Notes

Production uses the repository `Dockerfile`, based on Python 3.12.13 and Debian
Bookworm slim. The image installs the Pango, HarfBuzz, Fontconfig, and DejaVu
runtime packages required for WeasyPrint PDF rendering, then runs as a non-root
user. Python is patch-pinned in Docker and `.python-version`; dependency ranges
remain declared in `pyproject.toml`.

The container starts one worker with:

```bash
uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers 1
```

One worker is required for the v1.0 process-local PDF semaphore and in-memory
rate limits. Render supplies `PORT`; the image defaults to `10000` outside
Render. `PYTHON_VERSION` is not required for the Docker runtime because the
Python version is fixed by the base image.

Required production environment variables:

- `EQUA_ANALYTICS_ENV=production`
- `EQUA_ANALYTICS_SECRET_KEY`: strong secret, configured only in Render
- `AI_MODE`: `disabled`, `fake`, or `openai`; the Blueprint defaults to `disabled`
- `OPENAI_API_KEY`: required only when `AI_MODE=openai`
- `OPENAI_MODEL`: required only when `AI_MODE=openai`
- `PORT`: managed by Render

API docs are disabled in production. Fake AI is rejected unless
`ALLOW_FAKE_AI_IN_PRODUCTION=true` is deliberately configured. Missing OpenAI
configuration does not prevent deterministic dashboard and report use.

`render.yaml` defines a Docker web service, keeps deployment deliberate with
automatic deployment disabled, and uses the lightweight `GET /health` endpoint. The
health check does not access AI, generate a PDF, or require persistent storage.
The production service runs this Docker configuration; the legacy Python service
is retained separately as a rollback option. Enter secret values in the Render
dashboard when creating another environment from the Blueprint.

To reproduce or validate the production runtime, build and run the offline smoke check:

```bash
docker build -t equa-analytics:v1 .
docker run --rm \
  -e EQUA_ANALYTICS_ENV=production \
  -e EQUA_ANALYTICS_SECRET_KEY=replace-with-a-local-smoke-secret \
  --entrypoint python equa-analytics:v1 scripts/production_smoke.py
```

The smoke check verifies Python 3.12, WeasyPrint/Pango capability, application
import, and deterministic sample PDF generation without calling an AI provider.
For a running container, verify `GET /health` returns HTTP 200; Docker also runs
this check through its built-in `HEALTHCHECK`.

Production: https://equa-analytics.onrender.com
