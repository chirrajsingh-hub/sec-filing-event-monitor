# SEC Filing Event Monitor

An event-driven research workflow that watches a tracked universe of public companies for
material [SEC Form 8-K](https://www.sec.gov/files/form8-k.pdf) disclosures and turns them into a
weekly, analyst-style memo — what happened, which companies were involved, why it matters, a
materiality/urgency score, and a link back to the original EDGAR filing.

This is not a dashboard. The deliverable is a repeatable pipeline that goes from raw regulatory
filings to a written research artifact, the same shape of workflow used in equity research, credit
risk, and event-driven investing desks:

```
EDGAR filings  →  classify  →  score materiality  →  write analysis  →  weekly memo
```

See [`examples/sample_weekly_memo.md`](examples/sample_weekly_memo.md) for what the output looks
like (generated from mocked data — see the disclaimer at the top of that file).

## How it works

1. **Universe** — [`config/companies.yaml`](config/companies.yaml) tracks 32 US-listed
   semiconductor & semiconductor-equipment companies (NVDA, AMD, INTC, TXN, AVGO, ASML, and peers).
   Swap in any sector by editing tickers/sector name.
2. **Fetch** (`secmonitor.edgar`) — resolves tickers to CIKs and pulls recent 8-K filings straight
   from SEC EDGAR's free, public, no-key-required endpoints (`company_tickers.json` and
   `data.sec.gov/submissions/CIK##########.json`), then fetches each filing's primary document.
3. **Classify** (`secmonitor.events`) — maps each 8-K's disclosed item code(s) (5.02, 2.02, 4.02,
   1.05, ...) to a normalized event category (leadership change, earnings, restatement, cyber
   incident, debt financing, litigation, M&A, ...) per the [Form 8-K item
   taxonomy](https://www.sec.gov/files/form8-k.pdf). Generic catch-all items (8.01/7.01) are
   further refined by scanning the filing text for category keywords, since the item code alone
   doesn't distinguish a routine press release from litigation or M&A news.
4. **Score** (`secmonitor.scoring`) — an explainable materiality/urgency heuristic (1-5,
   Informational → Critical): starts from the highest-weight item on the filing, bumps for
   multiple stacked material items in one filing, and bumps again for high-severity language
   (`material weakness`, `going concern`, `bankruptcy`, `class action`, ...) in the filing text.
   Every score carries a plain-English rationale.
5. **Write** (`secmonitor.summarizer`) — produces the "what happened / why it matters /
   valuation-risk-thesis impact" narrative. Runs in template mode by default (deterministic,
   category-aware, no API key needed); set `ANTHROPIC_API_KEY` to have Claude ground the same
   three fields in the actual filing excerpt for more analyst-like prose. Falls back to the
   template automatically if the API call fails, so the pipeline never breaks on a flaky request.
6. **Persist** (`secmonitor.storage`) — a local SQLite cache keyed by accession number, so re-running
   `fetch` is idempotent and `memo` can render any date range from what's already been collected.
7. **Memo** (`secmonitor.memo`) — renders the week's events into a markdown memo grouped by
   materiality tier, each with the filing's items, score + rationale, narrative, and a direct link
   back to the EDGAR filing index page.

## Setup

```bash
pip install -e .
# or: pip install -r requirements.txt
```

SEC requires every automated client to send a descriptive `User-Agent` (name + contact email) on
every request — see the [EDGAR developer
FAQ](https://www.sec.gov/os/webmaster-faq#developers). Set:

```bash
export SEC_EDGAR_USER_AGENT="Your Name your.email@example.com"

# optional: enables LLM-grounded narratives instead of the template fallback
export ANTHROPIC_API_KEY="sk-ant-..."
```

## Usage

```bash
# Pull and score new 8-Ks for the tracked universe over the trailing 7 days
secmonitor fetch

# Render this week's memo from whatever's cached, writing to a file
secmonitor memo --output memo-$(date +%F).md

# Fetch fresh data and render in one step, for an explicit date range
secmonitor memo --refresh --since 2026-08-01 --until 2026-08-08 --output memo.md

# See the tracked universe
secmonitor list-companies
```

Run it on a weekly cron/CI schedule and commit the generated memo, or pipe it into whatever
publishing step you want — the pipeline's only output is a plain markdown string.

## Data source

[SEC EDGAR](https://www.sec.gov/edgar) is the source of truth: filings are fetched directly from
`sec.gov`/`data.sec.gov`, free and without an API key. This project also anticipates plugging in a
richer 8-K feed (event labels, materiality scores, ticker pages, already summarized) as a drop-in
replacement for `secmonitor.edgar.EdgarClient` if/when one becomes available — the pipeline stages
after fetch (classify/score/write/memo) are decoupled from *how* filings are fetched.

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

Tests run entirely offline against fixtures/mocked EDGAR responses (`tests/fixtures/`) — no network
access to `sec.gov` is required to run the suite.

### Project layout

```
secmonitor/
  models.py       dataclasses: Company, Filing, EventTag, MaterialityScore, FilingEvent
  edgar.py         EDGAR HTTP client: ticker->CIK resolution, 8-K listing, document text fetch
  events.py         8-K item -> event category taxonomy + catch-all keyword refinement
  scoring.py        materiality/urgency heuristic
  summarizer.py     narrative generation (template + optional Claude-backed)
  pipeline.py        orchestrates fetch -> classify -> score -> summarize -> persist
  storage.py         SQLite cache/dedupe
  memo.py            weekly markdown memo renderer
  cli.py             `secmonitor fetch|memo|list-companies`
config/companies.yaml  tracked company universe (sector + tickers)
examples/               sample rendered memo
scripts/                 helper script that (re)generates the example memo from mocked data
tests/                   offline unit tests + fixtures
```

## Limitations / next steps

- Only `filings.recent` is scanned per company (comfortably covers weeks/months of history); a
  historical backfill would need to paginate EDGAR's `filings.files`.
- Materiality scoring is a transparent heuristic, not a trained model — it's designed to be easy to
  audit and adjust (`secmonitor/scoring.py`), not to be state-of-the-art.
- The keyword-based catch-all refinement (`refine_catchall_category`) is intentionally simple; an
  LLM-based classifier could replace it for the ambiguous Item 8.01/7.01 cases.
