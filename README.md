# SWE Job Radar

SWE Job Radar is an async Python service that monitors only verified official company
careers systems, establishes a no-email historical baseline, and emails once when a newly
observed role appears eligible for a 2027 SWE internship or 2027 new-grad profile.

It does not apply to jobs, generate application content, or use job aggregators. Unsupported
companies are disabled until their official source has been investigated and fixture-tested.

## Current phase

Phase 1 (core) and the six-company Phase 2 proof are implemented. The brief contains 99 actual
named companies: numbered item 90 is a note about priority, not a company. All 99 are in
`config/companies.yaml`; six verified sources are enabled and the other 93 have intentionally
null URLs rather than speculative endpoints.

| Company | Priority | Official Careers URL | Mechanism | Scraper Status | Last Verified |
|---|---|---|---|---|---|
| OpenAI | Critical | https://openai.com/careers/search/ | Ashby public posting feed used by the official experience | Supported | 2026-08-31 |
| Google | Critical | https://www.google.com/about/careers/applications/jobs/results/ | Structured `AF_initDataCallback` data in official server HTML | Supported | 2026-08-31 |
| Stripe | Critical | https://stripe.com/careers/search | Complete official Next.js role index; stable Greenhouse IDs | Supported | 2026-08-31 |
| Ramp | Critical | https://ramp.com/careers | Ashby public posting feed used by the official experience | Supported | 2026-08-31 |
| GitHub | High | https://www.github.careers/careers-home/jobs | Official Jibe `/api/jobs` JSON | Supported | 2026-08-31 |
| Jane Street | Quant | https://www.janestreet.com/join-jane-street/open-roles/ | Official page's `/jobs/main.json` feed | Supported | 2026-08-31 |

The authoritative status of every remaining company is in `config/companies.yaml` as
`unsupported / Awaiting official-source investigation`.

## Architecture

Each enabled company has a company-specific class implementing `CompanyScraper.fetch_jobs()`.
Shared adapters normalize official Ashby data and common parsing. The rest of the pipeline is
source-agnostic:

```text
official careers source -> typed Job -> SQLite identity/baseline -> rules classifier
                        -> pending notification -> SMTP email -> sent timestamp
```

Polling is concurrent and bounded globally and per domain. Each company has an independent
loop and randomized jitter. HTTP uses connection pooling, timeouts, transient retry with
exponential backoff, and in-process ETag/Last-Modified revalidation. A suspicious zero result is
recorded as a scraper failure and never deactivates every known posting.

SQLite tracks active jobs, first/last seen timestamps, classification, notification state,
baselines, scraper health, and notification attempts. Fingerprints prefer the source's stable
job ID; URL-based fallback identity strips tracking parameters.

### Google scope

Google has thousands of postings. Its scraper polls the first, date-sorted U.S. result page for
three broad terms (`engineer`, `developer`, `intern`) and deduplicates them by Google job ID.
This is designed for low-latency detection of newly posted target roles without downloading
hundreds of pages every two minutes. This source-specific constraint is fixture-tested and is
called out here so it is not mistaken for complete historical enumeration.

## Classification

Only newly observed jobs are classified. Deterministic rules run first and produce:

- `INTERN_2027`
- `NEW_GRAD_2027`
- `RELEVANT_BUT_AMBIGUOUS`
- `IRRELEVANT`

Rules recognize broad SWE, backend, infrastructure, platform, systems, cloud, SRE, security,
ML/AI engineering, and quantitative-development language. They parse graduation windows,
0–1-year requirements, target seasons, U.S. locations, seniority, and explicit 3+ year
requirements. Strong SWE roles with unclear timing are emailed for review to favor recall.
Quant-priority companies additionally reject researcher, trader, analyst, pure-research, and
data-science titles unless the title is explicitly software-oriented.

The classifier interface is deliberately independent from monitoring. A provider-neutral
`StructuredJsonLLMFallback` accepts an injected authenticated JSON request function and is called
only for ambiguous newly discovered jobs. It validates the classification/confidence/reason
schema and cannot override deterministic seniority exclusions because excluded jobs never reach
the fallback. No LLM is required or configured by default.

## Local setup

Python 3.12 or newer is required.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Set SMTP values in `.env` or export them into the process environment. The application does not
itself load `.env`; Docker Compose does. Credentials are never stored in YAML or SQLite.

```text
EMAIL_PROVIDER=smtp
EMAIL_FROM=alerts@example.com
EMAIL_TO=you@example.com
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...
SMTP_STARTTLS=true
```

## CLI

Run the live validation first. It neither opens SQLite nor sends email:

```bash
python -m swe_job_radar validate stripe
python -m swe_job_radar validate --all
```

Create an explicit baseline before continuous operation:

```bash
python -m swe_job_radar baseline
python -m swe_job_radar run
```

Other operations:

```bash
python -m swe_job_radar check-once
python -m swe_job_radar status
```

Normal monitoring is also safe on a fresh database: the first successful non-empty fetch for
each company automatically becomes that company's baseline and cannot notify. Re-running the
explicit `baseline` command intentionally absorbs the then-current jobs without email, so do not
use it as a routine polling command.

When SMTP is absent or temporarily fails, eligible rows remain pending. Retries use exponential
backoff. `notification_sent_at` is written only after SMTP reports success, and a deterministic
Message-ID reduces duplicates across ambiguous crash boundaries.

## Docker deployment

```bash
cp .env.example .env
# edit .env
docker compose build
docker compose run --rm radar baseline
docker compose up -d
docker compose logs -f radar
```

The named `radar-data` volume persists SQLite at `/app/data`. Compose restarts the monitor unless
it is explicitly stopped. Kubernetes is not required.

## Testing

Tests use saved official-response structures and do not depend on live sites:

```bash
pytest
ruff check .
```

Coverage includes normalization, canonical URLs, fingerprints, baseline safety, deduplication,
reposts, notification retry/idempotency, classification, graduation windows, quant/seniority
filters, email formatting, suspicious zero results, and all six scraper response schemas.

Live validation is separate because official pages change and can rate-limit or block automated
access. One failed validation never prevents another company from being tested.

## Adding a company

1. Confirm the official careers URL.
2. Inspect the official page's current network/data behavior.
3. Prefer its structured public request, then embedded structured data, then server HTML.
4. Add one company-specific module under `src/swe_job_radar/scrapers/`; reuse a shared adapter.
5. Add a representative fixture and parser test.
6. Live-run `validate <slug>`.
7. Only after success, add the verified URL/mechanism/date and set `enabled: true` and
   `status: supported` in `config/companies.yaml`.

Never guess endpoints or selectors, use generic ATS discovery as source truth, bypass a CAPTCHA,
or introduce stealth/evasion behavior. If public automation is refused, keep the company
unsupported and document the observed reason.

## Troubleshooting

- `email_not_configured`: eligible jobs are retained as pending; set the SMTP environment.
- `suspicious zero-job response`: the source likely changed or failed; known active jobs are
  preserved. Run `validate <slug>` and compare the fixture to the live response.
- HTTP 401/403/CAPTCHA: do not bypass it. Disable the source and update its notes.
- Repeated errors: `status` shows last success, failure count, and last normal count; JSON logs
  include company, scraper, duration, counts, and exceptions without secrets.
- Prolonged failures send one distinct `RADAR HEALTH` email after approximately 2 hours for
  critical, 6 hours for high, or 12 hours for quant sources. A successful poll resets the outage.
- SQLite locking: run one monitor instance per database volume. WAL mode handles normal reads.
