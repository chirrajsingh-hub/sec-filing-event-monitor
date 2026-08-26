"""Example runner for the SEC 8-K event monitor, mirroring run_pipeline.py's
offline-by-default / --live-when-available convention.

    python examples/run_secmonitor.py
    python examples/run_secmonitor.py --mode live --contact-email you@example.com
    python examples/run_secmonitor.py --mode live --contact-email you@example.com \
        --alpha-vantage-key your_key_here  # adds a real news section

Outputs land in examples/output/: a weekly analyst memo (Markdown) and the
underlying scored events (CSV).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from secmonitor.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
