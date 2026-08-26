"""Command-line entry point: `python -m secmonitor.cli [options]`.

Runs the pipeline and writes both the rendered memo (Markdown) and the
underlying structured events (CSV) to an output directory, then prints a
short summary to stdout.
"""

from __future__ import annotations

import argparse
import os
from datetime import date
from pathlib import Path

from secmonitor.pipeline import MODE_LIVE, MODE_OFFLINE, run_pipeline
from secmonitor.universe import DEFAULT_SECTOR

ALPHA_VANTAGE_ENV_VAR = "ALPHAVANTAGE_API_KEY"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=[MODE_OFFLINE, MODE_LIVE], default=MODE_OFFLINE,
        help="offline (default): synthetic fixture data, no network needed. "
             "live: real EDGAR data, requires network access and --contact-email.",
    )
    parser.add_argument(
        "--weeks-back", type=int, default=1,
        help="How many weeks of filings to pull, ending today (default: 1).",
    )
    parser.add_argument(
        "--contact-email", default=None,
        help="Required for --mode live: identifies this tool in the SEC "
             "User-Agent header per SEC's fair-access policy.",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("examples/output"),
        help="Directory to write the memo and events CSV into (default: examples/output).",
    )
    parser.add_argument(
        "--alpha-vantage-key", default=os.environ.get(ALPHA_VANTAGE_ENV_VAR),
        help="Optional: adds a real 'This week in sector news' section from Alpha "
             "Vantage's NEWS_SENTIMENT feed, independent of EDGAR/--mode. Get a free "
             f"key at https://www.alphavantage.co/support/#api-key. Defaults to the "
             f"{ALPHA_VANTAGE_ENV_VAR} environment variable if set.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    result = run_pipeline(
        sector=DEFAULT_SECTOR,
        mode=args.mode,
        weeks_back=args.weeks_back,
        contact_email=args.contact_email,
        alpha_vantage_key=args.alpha_vantage_key,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()
    memo_path = args.output_dir / f"secmonitor_memo_{stamp}_{args.mode}.md"
    csv_path = args.output_dir / f"secmonitor_events_{stamp}_{args.mode}.csv"

    memo_path.write_text(result.render_memo())
    result.to_dataframe().to_csv(csv_path, index=False)

    print(f"Mode: {result.mode}")
    print(f"Coverage: {result.week_start} to {result.week_end}")
    print(f"Universe: {len(result.sector.tickers)} companies")
    print(f"Filings captured: {len(result.events)}")
    if result.warnings:
        print(f"Warnings: {len(result.warnings)} (see stderr above)")
    if args.alpha_vantage_key:
        print(f"News items: {len(result.news)}")
        if result.news_warnings:
            print(f"News warnings: {len(result.news_warnings)} (see stderr above)")
    else:
        print("News: skipped (no --alpha-vantage-key / ALPHAVANTAGE_API_KEY set)")
    print(f"Memo written to: {memo_path}")
    print(f"Events CSV written to: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
