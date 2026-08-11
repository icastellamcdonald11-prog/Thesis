---
name: cover-letter-material
description: Pulls relevant material — proof points, anecdotes, opening hooks, phrasing, and biographical facts — from the user's personal database of previously written cover letters (stored in Google Drive) so it can be manually repurposed into a new cover letter. Use whenever the user is applying for a job, internship, or fellowship and asks for help drafting or adapting a cover letter, finding material/examples to reuse, or mentions a specific employer or role they're applying to.
---

# Cover letter material finder

## What this skill is for

The user has a growing archive of cover letters written for real applications
(journalism, finance, multilateral development banks, think tanks, Chinese
corporates, government, etc.), stored as Google Docs in a Google Drive
folder, one subfolder per application. Good material — biographical facts,
proof points, anecdotes, phrasing that has worked before — is scattered
across dozens of these letters.

**This skill retrieves and organizes that material. It does not write a new
cover letter.** The deliverable is a curated, attributed briefing the user
edits and assembles by hand. Do not produce a ready-to-send draft unless the
user explicitly asks for one *after* reviewing the material — and even then,
prefer assembling it visibly from the sourced material rather than inventing
new prose or claims.

## Data source

Root folder (all past applications, one subfolder per employer/role):

```
https://drive.google.com/drive/folders/1-jryNKHdVJeUS9Nx8qYydJElkITsKTd5
```

Folder ID: `1-jryNKHdVJeUS9Nx8qYydJElkITsKTd5`

Structure: each subfolder is named after the employer/role (e.g. `SCMP`,
`Goldman Sachs`, `AIIB - Investment Analyst (Energy)`) and usually contains
one Google Doc — sometimes titled `<Name> - <Employer> Cover Letter`,
sometimes just `Untitled document` — plus occasionally a CV or job posting.
Treat the doc titled or shaped like a cover letter (opens "Dear ...", closes
"Yours sincerely") as the source; skip CVs/job postings unless the user
wants biographical facts cross-checked against the CV.

**Do not assume the folder list below is complete or current** — new
applications get added over time. Always re-list the root folder live
(`search_files` with `parentId = '1-jryNKHdVJeUS9Nx8qYydJElkITsKTd5'`)
rather than relying on a cached list, including this one, which is only a
snapshot to help route relevance:

- Journalism: `FT`, `SCMP` (subfolder has 2 letters), `Argus media`,
  `Guangzhou Wanyi - Senior Media Journalist`
- Multilateral / development finance: `AIIB - *` (five separate AIIB
  subfolders for different roles — check which one matches), `EBRD`, `ADB
  YPP`, `UNDP`, `GCF`, `GGGI Intern`
- Climate / energy policy & research: `CREA`, `CCFLA - Intern`, `CPI -
  Internship`, `Finance for Development Lab`, `Rystad`, `GSCC`
- Think tank / policy research: `IIPP`, `TBI`
- Finance / private markets: `Goldman Sachs`, `StepStone Private Equity`,
  `Empyrean Partners`
- Chinese corporates: `Xiangyu Corporation`, `Zhaoli`, `Musasa
  International Global Trade`, `Huayuan - Overseas Investment Analyst`,
  `Shanghai Zheran International Trade`, `Dezan Shira & Associates`
- UK government: `Civil Service`
- Unclassified — check contents before assuming: `Hillhaus`, `ChatCut`,
  `ARN Group`, `Counterpoint`

## Workflow

**1. Clarify the target.** If not already given, ask what role/employer the
user is applying to, and — if they have it — paste the job posting or the
angle they want to take. This determines which past letters are most
relevant (same sector > same *type* of pitch (advertised role vs.
speculative) > most recent > most polished).

**2. Find candidate letters.** Use `mcp__Google_Drive__search_files` against
the root folder to list subfolders (`parentId = '<root id>'`), or
`fullText contains '<keyword>'` / `title contains '<keyword>'` to search
directly (e.g. sector name, a recurring proof point like "solar" or
"sanctions"). Pick 3–6 letters most relevant to the target — favor the same
sector/audience type first, since framing of the same facts shifts a lot
between a journalism letter, a multilateral-bank letter, and a finance
letter.

**3. Read the selected letters in full** with
`mcp__Google_Drive__read_file_content`.

**4. Extract and organize material into a briefing**, always attributing
each item to its source letter (by employer/title), grouped as:

- **Core biographical facts** — the stable, reusable spine (education,
  languages, credentials) that recurs near-verbatim across letters.
- **Signature proof points / anecdotes** — specific accomplishments,
  scoops, projects (each with a one-line note on what it demonstrates, so
  the user can pick the one that fits the target role's emphasis).
- **Opening hooks** — how past letters opened, grouped by letter type
  (responding to an advertised role / speculative approach to a named
  contact / internship application), since the right opening move differs
  by type.
- **Sector-specific framing** — note, where visible, how the *same*
  underlying facts get reframed differently for e.g. a journalism audience
  vs. a policy/multilateral audience vs. a finance audience. This is often
  the most useful thing to surface, since the target letter needs the same
  treatment.
- **Closing lines / sign-offs.**

**5. Present the briefing as structured markdown, not prose.** Use short
attributed bullets ("Bloomberg ECM letter: ...") so the user can scan and
copy-paste what's useful. Do not merge everything into flowing paragraphs —
that pre-empts the user's own drafting.

**6. Explicitly flag gaps.** If nothing in the archive fits a requirement of
the new role well, say so rather than stretching an unrelated anecdote to
fit.

## Guardrails

- Never fabricate an anecdote, credential, or figure not present in an
  actual past letter — this is a retrieval tool, not a generator, and the
  material stands in for the user's own words.
- Don't write a complete, submittable cover letter as the default output.
  If the user asks for a full draft after seeing the material, build it
  visibly from the sourced material and say which parts came from where.
- The archive contains personal contact details (address, phone, email).
  Keep output local to the conversation; don't publish it (e.g. as a public
  Artifact) without the user's explicit OK.
- Keep the corpus in Google Drive, not copied into this repo — application
  letters change over time and the repo is unrelated to job search, so a
  static copy here would just go stale and mix concerns.
