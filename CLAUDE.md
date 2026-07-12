# FT China Pitch-Discovery Pipeline — Claude Code Kickoff Brief

Paste everything below this line into Claude Code as your opening prompt. It doubles as the project's CLAUDE.md — save it to the repo root once the project is scaffolded.

## Who I am and what this is

I'm a journalist starting an internship at the Financial Times, covering China. I want a pipeline that monitors Chinese-language media and social trending data, triages stories against my pitch criteria, and emails me a daily digest of 5–10 pitch candidates. I will assess candidates manually; the tool's job is discovery and differentiation-checking, not writing.

## Pitch criteria (in strict priority order)

A good pitch is:

1. Not yet reported by the FT (hard requirement — check site:ft.com)
2. New (story or development from the last ~72 hours, or a newly visible trend)
3. In the FT's China niche — markets, corporates, macro/policy, energy transition, tech and tech regulation, trade, property, labour/demographics with an economic angle
4. Interesting — surprising, consequential, or revealing about where China is heading; not routine earnings/personnel/procedural news
5. Not yet reported by Western English-language competitors (Reuters, Bloomberg, WSJ, NYT, Economist) — coverage here weakens but doesn't kill a pitch
6. Not yet reported in English by SCMP or Caixin Global — weakest penalty; Chinese-language-only coverage is fine and often a positive signal

Also flag clusters: the same theme appearing across ≥3 sources in a rolling 7-day window, even if no single story qualifies. Trend-connection pitches are often stronger than single-story pitches.

## Architecture

Three stages, run as a scheduled job (GitHub Actions cron, daily at 06:00 Asia/Shanghai; design so it can also be run manually):

### Stage 1 — Acquisition (no LLM)

Config-driven source list in `sources.yaml` (schema below). Adding a source must never require code changes for RSS-type sources.

Fetch via three adapter types:
- `rsshub`: routes served from a self-hosted or public RSSHub instance (make the base URL configurable; public instances rate-limit)
- `rss`: native RSS where it exists
- `scrape`: per-site scraper module (requests + BeautifulSoup first; fall back to Playwright only if the page is JS-rendered)

Store items in SQLite: id, source, url, title_zh, summary_zh, published_at, fetched_at, content_hash. Dedupe on URL and on fuzzy title similarity (same story syndicated across outlets).

Be polite: per-domain rate limiting, realistic User-Agent, exponential backoff, and a `--dry-run` mode. If a source fails, log and continue — never let one broken scraper kill the run.

### Stage 2 — Cheap triage (Claude Haiku via Anthropic API)

Batch new items (title + summary, Chinese is fine — do not pre-translate) in groups of ~25.

For each item score: `in_niche` (0–2), `newsworthy` (0–2), `interesting` (0–2), plus a one-line English gist.

Discard anything scoring below a configurable threshold (default: total ≥ 4 and in_niche ≥ 1). Expect this to kill ~90% of volume.

Also run cluster detection here: embed or keyword-tag surviving items, compare against the last 7 days, flag recurring themes.

### Stage 3 — Coverage scan (Claude Haiku via Anthropic API, web search tool enabled)

Redesigned 2026-07-12: the original Sonnet "differentiation check" produced analysis (verdicts, pitch angles, confidence ratings) that was expensive and often wrong. Stage 3 is now search + headline-grabbing + translation only — the journalist does the judging.

For each survivor (cap at ~15/day, ~3 searches/item to control cost):

1. Translate the Chinese headline faithfully into English, plus a 1–2 sentence summary.
2. Generate 2–3 English search phrases (entity names in both pinyin and English where known) and search in this order: `site:ft.com` → Reuters/Bloomberg/WSJ → SCMP/Caixin Global.
3. Report raw findings only: a list of `{outlet, headline, url}` for every relevant article found. No verdicts, no pitch angle, no confidence rating.

Whether FT already covered a story is decided mechanically in code (any reported URL on ft.com), not by model judgment. Those items are dropped from the digest but logged.

## Output

Daily digest as email (SMTP, config-driven) and a markdown file in `digests/YYYY-MM-DD.md`.

Each candidate: translated English headline + summary, Chinese headline + link, source, what English coverage exists (raw headlines and links), why it survived triage. Clusters get their own section.

The digest also carries a "New from ministries & think tanks" section: everything published in the last 24h by the monitored official sources (`category: ministry | thinktank` in sources.yaml — State Council, NDRC, MOF, PBOC, MOFCOM, NBS, MIIT, NEA, DRC, CASS, CF40), listed regardless of triage score. These are scraped in Stage 1, so monitoring them costs no API spend.

Keep a `feedback.csv` where I can mark candidates pitched/ignored — future tuning data, no ML needed yet.

## sources.yaml schema

```yaml
sources:
  - id: jiemian
    name: 界面新闻
    type: rsshub          # rsshub | rss | scrape
    route: /jiemian/list/4  # rsshub route, rss url, or scraper module name
    category: business
    enabled: true
    weight: 1.0            # multiplier on triage score, for tuning source quality
```

## Starting sources (verify each route/selector works before moving on)

| Source | Suggested adapter | Notes |
|---|---|---|
| Weibo hot search | rsshub `/weibo/search/hot` | Trending signal, not stories — triage differently (flag topics, not articles) |
| tophub.today | scrape | Aggregates hot lists across ~30 platforms; one page, high value |
| 界面新闻 Jiemian | rsshub | Business/finance |
| 第一财经 Yicai | rsshub or scrape | Finance/markets |
| 36氪 36Kr | rsshub | Tech/startups |
| 澎湃新闻 The Paper | rsshub | General news, strong original reporting |
| 中国能源报 China Energy News | scrape | Plain HTML, likely trivial |

RSSHub routes change; check https://docs.rsshub.app for current routes rather than trusting the ones above. If a route is dead, fall back to a scraper.

## Triage prompt (Stage 2 — use as the system prompt, refine iteratively)

```
You are a story scout for a Financial Times journalist covering China.
You will receive a batch of Chinese-language headlines and summaries.
For each item, return JSON only:
{"id": ..., "in_niche": 0-2, "newsworthy": 0-2, "interesting": 0-2,
 "gist_en": "one line in English", "tags": ["...", "..."]}

Scoring guide:
- in_niche 2: squarely FT territory — markets, major corporates, macro policy,
  energy transition, tech regulation, trade, property, demographics-as-economics.
  1: adjacent (society/culture stories with a clear economic dimension).
  0: politics-only, entertainment, sport, crime, local human interest.
- newsworthy 2: a new development or data point from the last 72 hours.
  1: ongoing story with a fresh angle. 0: evergreen, commemorative, or routine
  (scheduled earnings, personnel moves, procedural announcements).
- interesting 2: would make an FT editor lean forward — surprising, contrarian,
  or an early signal of something structural. 1: solid but expected.
  0: dull even if accurate.
- tags: 2-4 lowercase English theme tags for cluster detection
  (e.g. "ev-price-war", "local-government-debt", "youth-unemployment").

Be ruthless. Most items should score low. State media 成就宣传 (achievement
propaganda) scores interesting=0 unless the underlying data point is itself news.
```

## Build order

1. Scaffold: repo, sources.yaml, SQLite schema, config loading, logging.
2. Stage 1 for the seven sources above; verify each returns real items. Handle failures gracefully.
3. Stage 2 triage with the prompt above; run on a real day's haul and eyeball the survivors with me before proceeding.
4. Stage 3 differentiation check on a small sample (5 items) to validate cost and search quality.
5. Digest generation + email + GitHub Actions cron.
6. Cluster detection last — it needs a week of data to be testable anyway.

Ask me before making product decisions (thresholds, digest format, cost trade-offs). Don't ask before making ordinary engineering decisions.

## Constraints

- Python 3.11+, keep dependencies minimal (requests, beautifulsoup4, feedparser, pyyaml, anthropic; playwright only if genuinely needed).
- Anthropic API key via environment variable / GitHub Actions secret — never in the repo.
- Daily LLM spend target: under $1/day at steady state (Haiku everywhere; Stage 3 capped at 15 items and 3 web searches each — web_search bills ~$0.01/search on top of tokens).
- Respect robots.txt for scrapers; if a site blocks automated access, mark the source `enabled: false` with a comment and tell me — I'll handle those manually.
- All code comments and digest output in English; never pre-translate source text before triage (Claude reads Chinese natively; translation loses signal).

## Current implementation status

See `README.md` for what's built, how to run each stage, and — importantly — a note on what could **not** be verified live from the environment this codebase was scaffolded in (no general internet egress, no Anthropic API key present), and what you need to check yourself before trusting the pipeline end-to-end.
