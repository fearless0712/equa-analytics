# EQUA Analytics

EQUA Analytics turns a sales CSV into validated KPIs, monthly trends, dimension
rankings, data-quality findings, and a decision-support dashboard. It helps
business users review performance without relying on AI for calculations.

The project is at Phase 1, Step 9 and is being prepared for its first public
release. Use only fictional or non-confidential data during development.

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
claimed because cost is not part of the Phase 1 input contract.

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

OpenAI requests use `store=False`, a timeout, limited retries, and a 1,200-token
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

The rate limiter is in-memory and suitable only for the Phase 1 single-worker
deployment. Multiple workers or instances require a shared store such as Redis.

## Report Exports

Reports are generated from deterministic analytics without requiring AI. Both
self-contained HTML and PDF exports are processed in memory and are never
persistently stored. PDF generation uses WeasyPrint and permits one concurrent
render per process, with a separate limit of five requests per ten minutes per
direct client IP. These controls assume a single-worker deployment.

PDF rendering can be CPU- and memory-intensive on Render Free instances. The
current Phase 1 limits report contents and enforces a 5 MB generated PDF cap.

## Tech Stack

Python 3.12, FastAPI, Pydantic Settings, pandas, Plotly, Jinja2, WeasyPrint,
OpenAI Python SDK, pytest, and Uvicorn. Phase 1 has no database, authentication,
or file persistence.

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

Set `EQUA_ANALYTICS_ENV=production`, provide a strong
`EQUA_ANALYTICS_SECRET_KEY`, and keep debug disabled. API docs are disabled in
production. Fake AI is rejected unless `ALLOW_FAKE_AI_IN_PRODUCTION=true` is set
deliberately. Missing OpenAI configuration does not prevent normal dashboard use.
For a Render web service, use one worker and the start command
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

No public deployment URL is configured yet.
