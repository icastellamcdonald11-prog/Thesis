# FT China Pitch-Discovery Pipeline

Monitors Chinese-language media and social trending data, triages stories against
FT-China pitch criteria, and produces a daily digest of 5–10 pitch candidates plus
recurring-theme clusters. See `CLAUDE.md` for the full product brief and rationale.

## Live-run findings (first GitHub Actions dry run, 2026-07-05)

- **tophub scraper works** — 3,023 items fetched on the first try. A `max_items: 500`
  cap was added to protect the triage budget.
- **rsshub.app blocks datacenter IPs** (instant 403 on every route from the Actions
  runner). Fallback mirrors are now configured in `config/settings.yaml` and tried
  in order; the durable fix is self-hosting RSSHub and putting its URL first.
- **weibo_hot** was switched from RSSHub to a direct scraper of Weibo's public
  hot-search JSON endpoint.
- **36kr** was switched to its native RSS feed (`https://36kr.com/feed`), removing
  the RSSHub dependency.
- **china_energy_news** re-enabled with the human-verified listing URL
  (`/jsxw`) and a broad link-pattern selector; tighten the selector once the
  page DOM can be inspected.
- **tophub** now filters to a platform allowlist (news/finance/tech platforms
  only — see `platforms:` in `sources.yaml`) so entertainment hot lists don't
  consume the triage budget.

## Status: scaffolded, partially field-verified

This codebase was built in a sandboxed environment with **no general internet
egress** (only anthropic.com, pypi, npm, and a few infra domains were reachable —
everything else, including rsshub.app, tophub.today, ft.com, and the Chinese
outlets, returned `403` at the network gateway) and **no `ANTHROPIC_API_KEY`**
available. That means every stage was built, unit-tested against fixtures, and
smoke-tested end-to-end (`scripts/run_all.py --dry-run`), but the following from
the brief's "Build order" still needs to happen with real network access and a
real API key, ideally by you:

1. **Verify each source** (`python -m pipeline.acquisition.run --source <id>`)
   actually returns items. The `rsshub` routes in `sources.yaml` are best-effort
   guesses based on RSSHub's route conventions — RSSHub routes drift, so check
   https://docs.rsshub.app and fix the `route:` values that are wrong. The
   `tophub` and `china_energy_news` scraper selectors (`pipeline/acquisition/scraping/`)
   are similarly best-effort against remembered page structure and will likely
   need their CSS selectors adjusted against the live DOM.
2. **Run Stage 2 on a real day's haul** and eyeball the survivors together before
   trusting the threshold defaults.
3. **Run Stage 3 on a small sample** (`--limit 5`) to check cost and search
   quality before raising the daily cap.

## Stage 3 redesign (2026-07-12): analysis out, search + translation in

Stage 3 was originally a Sonnet "differentiation check" that produced verdicts
(`ft_covered` yes/no, per-outlet coverage judgments, a pitch angle, a confidence
rating). In practice the analysis was the least useful part — often wrong, and
the most expensive line item. It has been replaced with a **coverage scan**
(`pipeline/coverage/`) that only does what the API is reliably good at:

- **Translate** the Chinese headline faithfully (plus a 1–2 sentence summary).
- **Search** for existing English coverage (site:ft.com first, then
  Reuters/Bloomberg/WSJ/NYT/Economist, then SCMP/Caixin), capped at
  `coverage.max_searches` per item.
- **Grab headlines**: report each relevant article found as raw
  `{outlet, headline, url}` — no verdicts, no pitch angles, no confidence.

Whether FT already covered a story is now decided *mechanically in code* (any
hit whose URL is on ft.com — see `CoverageReport.ft_url`), not by model
judgment. Cost: Haiku instead of Sonnet (~3x cheaper per token; search results
are billed as input tokens, so this matters) and 3 searches instead of 6
(hosted web_search bills ~$0.01/search). Worst case at the default 15-item cap:
~$0.45 of searches + a few cents of tokens per day.

The old `diffcheck` table is retained read-only in existing databases; items it
already processed are excluded from the new scan so nothing is re-billed.

Actual search usage is now counted (one `server_tool_use` block = one billed
search) and stored per item in `coverage.searches_used`; every Stage 3 run logs
the day's running total and approximate search fees.

## Ministry & think-tank monitor (added 2026-07-12)

`sources.yaml` now includes ~11 scraped sources with `category: ministry`
(State Council, NDRC, MOF, PBOC, MOFCOM, NBS, MIIT, NEA) or
`category: thinktank` (DRC, CASS, CF40). They cost nothing to monitor (Stage 1
scraping, no API calls) and are handled two ways:

- Everything they published in the last 24h appears in a dedicated
  **"New from ministries & think tanks"** digest section, regardless of triage
  score — a what's-new feed, not a filter.
- They also flow through normal triage, so a major policy release can still
  become a pitch candidate with a coverage scan.

**The selectors are unverified** (added from a sandbox with no internet
egress). On the first live run, check the Stage 1 log: any source whose
selector matched nothing dumps a sample of the anchors actually on the page —
fix `list_selector` in `sources.yaml` from that, no code changes needed. Some
gov.cn properties may 403 GitHub's datacenter IPs (as rsshub.app does); disable
those with a comment rather than fighting them.
4. Only then turn on the GitHub Actions cron for real.

Everything downstream of "does the JSON parse and does the SQL do the right
thing" — dedupe logic, batching, threshold math, cluster detection, digest
rendering, cost caps — is implemented and covered by tests that don't require
network or API access (`pytest`, 22 tests, all passing).

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt   # includes pytest; use requirements.txt for prod-only
cp .env.example .env                  # fill in ANTHROPIC_API_KEY, SMTP_*, EMAIL_TO
```

## Running a stage manually

Each stage is a standalone CLI plus an orchestrator:

```bash
python -m pipeline.acquisition.run [--dry-run] [--source SOURCE_ID]
python -m pipeline.triage.run [--limit N] [--dry-run]
python -m pipeline.coverage.run [--limit N] [--dry-run]
python -m pipeline.digest.run [--no-email]

python scripts/run_all.py [--dry-run]   # runs all four in order
```

`--dry-run` on Stage 1 fetches but doesn't write to SQLite. On Stage 2/3 it
skips the paid API call entirely and just reports the pending count — useful
for checking the backlog before spending money. `scripts/run_all.py --dry-run`
chains all of that into one zero-cost smoke test.

State lives in `data/pitch_discovery.db` (SQLite) and `digests/YYYY-MM-DD.md`.
Mark candidates once you've decided on them:

```bash
python scripts/mark_feedback.py <item_id> pitched "why it worked"
python scripts/mark_feedback.py <item_id> ignored
```

## Configuration

- `sources.yaml` — source list. Add an `rsshub`/`rss` source with no code
  changes. `scrape` sources need a module registered in
  `pipeline/acquisition/scraping/registry.py` (or use `type: scrape, route: generic`
  with a `scrape_config:` block of CSS selectors for a simple listing page).
- `config/settings.yaml` — thresholds, batch sizes, daily caps, SMTP host/port,
  db path. Non-secret only.
- Secrets come from the environment (`.env` locally, GitHub Actions secrets in
  CI): `ANTHROPIC_API_KEY`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_TO`,
  `EMAIL_ENABLED`.

## Architecture

```
pipeline/
  acquisition/   Stage 1 — rsshub / rss / scrape adapters, dedupe, rate limiting
  triage/        Stage 2 — Haiku batch scoring against the pitch-criteria prompt
  cluster/       cross-story theme detection (runs as part of Stage 2)
  coverage/      Stage 3 — Haiku + hosted web_search: translate headline, find existing coverage
  digest/        Stage 4 — markdown render, email send, feedback.csv logging
  db.py          SQLite schema + all queries
  models.py      RawItem / TriageScore / CoverageReport dataclasses
  config.py      sources.yaml + config/settings.yaml + env loader
scripts/
  run_all.py         orchestrates all four stages
  mark_feedback.py   CLI to mark a digest candidate pitched/ignored
.github/workflows/daily.yml   cron (06:00 Asia/Shanghai) + manual dispatch
```

A broken source in Stage 1 is logged and skipped, never fatal to the run — this
was tested for real: with all outbound network blocked, `run_all.py --dry-run`
correctly logged all seven sources as failed and still produced a valid (empty)
digest, exercising the full pipeline wiring end to end.

## Tests

```bash
pytest
```

32 tests, no network or API key required: adapters run against fixture RSS/HTML
in `tests/fixtures/`, Haiku response parsing (triage and coverage scan) is
tested against a fake Anthropic client, and dedupe/cluster/digest logic run
against real (temp-file) SQLite databases.

## GitHub Actions

`.github/workflows/daily.yml` runs `scripts/run_all.py` daily at 06:00 Asia/Shanghai
(22:00 UTC) and on manual `workflow_dispatch` (with a `dry_run` input). It commits
`data/pitch_discovery.db`, `digests/`, and `feedback.csv` back to the branch after
each real run, so dedupe state and history persist across ephemeral runners.
Requires repo secrets: `ANTHROPIC_API_KEY`, `SMTP_USERNAME`, `SMTP_PASSWORD`,
`EMAIL_TO`.

## Known gaps / deliberately deferred

- Playwright/JS-rendered scraping isn't implemented — none of the seven starting
  sources should need it, but if a future source does, add a dedicated adapter
  module rather than extending `GenericSelectorScraper`.
- Cluster detection is wired in but, per the brief, only becomes meaningful once
  a week of real data has accumulated.
- robots.txt compliance is a manual check for now — before you enable a new
  scrape source, check its `robots.txt` yourself and set `enabled: false` with a
  comment if it disallows automated access, per the brief's constraint.
