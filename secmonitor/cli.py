from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

from secmonitor.config import Settings, load_companies
from secmonitor.memo import render_weekly_memo
from secmonitor.pipeline import run_pipeline
from secmonitor.storage import EventStore


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def cmd_fetch(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    until = args.until or date.today()
    since = args.since or (until - timedelta(days=settings.lookback_days))

    events = run_pipeline(settings, since=since, until=until, skip_seen=not args.force)
    print(f"Fetched {len(events)} new 8-K event(s) between {since} and {until}.")
    for event in events:
        print(f"  {event.filing.filing_date} {event.filing.company.ticker:>6}  "
              f"[{event.materiality.level:>13}]  {event.primary_category}")
    return 0


def cmd_memo(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    until = args.until or date.today()
    since = args.since or (until - timedelta(days=settings.lookback_days))

    store = EventStore(settings.data_dir / "secmonitor.db")

    if args.refresh:
        run_pipeline(settings, since=since, until=until, store=store, skip_seen=True)

    events = store.load_range(since, until)
    companies = load_companies()
    sector = companies[0].sector if companies else ""
    memo_text = render_weekly_memo(events, since, until, sector=sector)

    if args.output:
        Path(args.output).write_text(memo_text)
        print(f"Wrote memo ({len(events)} events) to {args.output}")
    else:
        print(memo_text)
    return 0


def cmd_list_companies(args: argparse.Namespace) -> int:
    companies = load_companies()
    print(f"Tracked universe: {len(companies)} companies ({companies[0].sector if companies else 'n/a'})")
    for c in companies:
        print(f"  {c.ticker:>6}  {c.name}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="secmonitor", description="SEC 8-K event monitor")
    sub = parser.add_subparsers(dest="command", required=True)

    p_fetch = sub.add_parser("fetch", help="Pull and score new 8-K filings for the tracked universe")
    p_fetch.add_argument("--since", type=_parse_date, default=None)
    p_fetch.add_argument("--until", type=_parse_date, default=None)
    p_fetch.add_argument("--force", action="store_true", help="Re-process filings already seen")
    p_fetch.set_defaults(func=cmd_fetch)

    p_memo = sub.add_parser("memo", help="Render a weekly memo from cached (or freshly fetched) events")
    p_memo.add_argument("--since", type=_parse_date, default=None)
    p_memo.add_argument("--until", type=_parse_date, default=None)
    p_memo.add_argument("--refresh", action="store_true", help="Fetch new filings before rendering")
    p_memo.add_argument("--output", type=str, default=None, help="Write memo to this path instead of stdout")
    p_memo.set_defaults(func=cmd_memo)

    p_list = sub.add_parser("list-companies", help="Print the tracked company universe")
    p_list.set_defaults(func=cmd_list_companies)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
