# FT China Pitch-Discovery Pipeline

Monitors Chinese-language media, translates each publication's daily headline
into English, and produces a daily digest + email. See `CLAUDE.md` for the
full product brief, rationale, and the 2026-07-20 pivot note at the top of
that file.

## 2026-07-20 — pivot: translate-and-link, not triage-and-pitch

The original design (Haiku triage/scoring → Sonnet + web-search
differentiation-check against FT/competitor coverage → curated 5-10
pitch-candidate digest) is **replaced** with a simpler, cheaper flow, per
direct product feedback that the differentiation-check stage was too
expensive and unreliable:

- **Stage 1 (acquisition)** now keeps only the single top/lead item per
  source per fetch (`max_items: 1` in `sources.yaml`) — i.e. each
  publication's current headline, not a firehose of items to triage.
- **Stage 2 (`pipeline/translate/`)** replaces both the old Haiku triage and
  the Sonnet differentiation-check: one cheap batched Haiku call translates
  the day's headlines into English. No scoring, no web search, no
  FT/competitor coverage check.
- **Stage 3 (`pipeline/digest/`)** renders one card per publication (English
  translation + Chinese headline + link) instead of a curated candidate list
  with clusters.

The old `pipeline/triage/` and `pipeline/diffcheck/` code, their SQLite
tables, and cluster detection (`pipeline/cluster/`, which read triage tags)
are **untouched but dormant** — not part of the default `scripts/run_all.py`
run. `config/settings.yaml` has `triage.enabled: false` /
`diffcheck.enabled: false`; flip either to `true` to have `run_all.py` call
that stage again (you'd also need to update `pipeline/digest/render.py`,
which currently only reads translation output, if you want its results back
in the digest).

`sources.yaml` was rewritten around a ~30-publication list (see the file's
header comment for what's a known-working adapter vs. an unverified
best-effort scrape config).

## Live-run findings (first GitHub Actions dry run, 2026-07-05, original 7-source list)

- **tophub scraper works** — 3,023 items fetched on the first try. (tophub is
  no longer in `sources.yaml` — dropped in the 2026-07-20 source-list rewrite,
  which isn't triage-volume-constrained the way tophub's firehose was suited
  for.)
- **rsshub.app blocks datacenter IPs** (instant 403 on every route from the
  Actions runner). Fallback mirrors are configured in `config/settings.yaml`
  and tried in order; the durable fix is self-hosting RSSHub and putting its
  URL first.
- **weibo_hot** was switched from RSSHub to a direct scraper of Weibo's public
  hot-search JSON endpoint. (Also dropped in the 2026-07-20 rewrite — not in
  the new source list.)
- **36kr** was switched to its native RSS feed (`https://36kr.com/feed`),
  removing the RSSHub dependency. Still in the source list, still enabled.
- **china_energy_news** stayed disabled: the article list is JS-rendered,
  needs Playwright or the underlying XHR/JSON endpoint.

## Status: scaffolded, mostly unverified against live sites

Both the original build and the 2026-07-20 rewrite happened in sandboxed
environments with **no general internet egress** — confirmed again on
2026-07-20 (jiemian.com/yicai.com connections timed out, people.com.cn
returned 403, all from here). GitHub Actions runners have historically had
real internet access (see "Live-run findings" above, and two weeks of real
scheduled runs since), so sources that fail from this sandbox may still work
fine in CI — but most of the ~30 sources added on 2026-07-20 have never been
checked against their live DOM at all. Before trusting the pipeline:

1. **Verify each new source** (`python -m pipeline.acquisition.run --source
   <id>`) actually returns an item. Most `scrape_config.list_selector` values
   are the best-effort generic guess `a[href*='.html']` — when it matches
   nothing, `GenericSelectorScraper` logs a sample of the anchors actually on
   the page, which is usually enough to fix the selector without needing
   browser access. `sources.yaml`'s header comment has the full list of
   what's known-good vs. guessed.
2. **Run Stage 2 (translate) on a real day's haul** and check translation
   quality before trusting it unattended.
3. Only then rely on the GitHub Actions cron for real.

Everything downstream of "does the JSON parse and does the SQL do the right
thing" — dedupe logic, batching, digest rendering — is implemented and
covered by tests that don't require network or API access (`pytest`, all
passing).

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
python -m pipeline.translate.run [--limit N] [--dry-run]
python -m pipeline.digest.run [--no-email]

python scripts/run_all.py [--dry-run]   # runs all three in order

# Dormant (see the 2026-07-20 pivot note above) — still runnable directly if
# you re-enable them in config/settings.yaml:
python -m pipeline.triage.run [--limit N] [--dry-run]
python -m pipeline.diffcheck.run [--limit N] [--dry-run]
```

`--dry-run` on Stage 1 fetches but doesn't write to SQLite. On Stage 2 it
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
  Every current source has `max_items: 1` — Stage 1 keeps only the top item
  per source per fetch (that source's current headline).
- `config/settings.yaml` — batch sizes, SMTP host/port, db path,
  `triage.enabled` / `diffcheck.enabled` toggles for the dormant stages,
  `detail_summary` (fetches each kept item's own article page for a lead
  paragraph when the listing page had no description — most `scrape` sources).
  Non-secret only.
- Secrets come from the environment (`.env` locally, GitHub Actions secrets in
  CI): `ANTHROPIC_API_KEY`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_TO`,
  `EMAIL_ENABLED`.

## Architecture

```
pipeline/
  acquisition/   Stage 1 — rsshub / rss / scrape adapters, dedupe, rate limiting
  translate/     Stage 2 — Haiku batch translation of each source's daily headline
  digest/        Stage 3 — markdown render, email send, feedback.csv logging
  db.py          SQLite schema + all queries
  models.py      RawItem / Translation / (dormant) TriageScore / DiffVerdict dataclasses
  config.py      sources.yaml + config/settings.yaml + env loader
  triage/        dormant — Haiku scoring against the original pitch-criteria prompt
  diffcheck/     dormant — Sonnet + hosted web_search differentiation check
  cluster/       dormant — cross-story theme detection (read triage tags)
scripts/
  run_all.py         orchestrates acquisition -> translate -> digest (+ dormant stages if re-enabled)
  mark_feedback.py   CLI to mark a digest candidate pitched/ignored
.github/workflows/daily.yml   cron (06:00 Asia/Shanghai) + manual dispatch
```

A broken source in Stage 1 is logged and skipped, never fatal to the run.

## Tests

```bash
pytest
```

All tests pass without network or API access: adapters run against fixture
RSS/HTML in `tests/fixtures/`, Haiku/Sonnet response parsing is tested
against a fake Anthropic client (including the current `translate` stage and
the dormant `triage`/`diffcheck` stages), and dedupe/digest logic run against
real (temp-file) SQLite databases.

## GitHub Actions

`.github/workflows/daily.yml` runs `scripts/run_all.py` daily at 06:00 Asia/Shanghai
(22:00 UTC) and on manual `workflow_dispatch` (with a `dry_run` input). It commits
`data/pitch_discovery.db`, `digests/`, and `feedback.csv` back to the branch after
each real run, so dedupe state and history persist across ephemeral runners.
Requires repo secrets: `ANTHROPIC_API_KEY`, `SMTP_USERNAME`, `SMTP_PASSWORD`,
`EMAIL_TO`.

## Known gaps / deliberately deferred

- Playwright/JS-rendered scraping isn't implemented. `china_energy_news` is
  disabled for this reason; a couple of the 2026-07-20 sources may turn out
  to need it too once checked live.
- robots.txt compliance is a manual check for now — before you enable a new
  scrape source, check its `robots.txt` yourself and set `enabled: false` with a
  comment if it disallows automated access, per the brief's constraint.
- Most of the ~30 sources added 2026-07-20 have unverified `scrape_config`
  selectors — see "Status" above.
