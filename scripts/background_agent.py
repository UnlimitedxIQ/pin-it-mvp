#!/usr/bin/env python3
"""
Continuous orchestrator:
1) Scrape Reddit raw comments into queue
2) Run curation agent batch (problem / solution / not_related)
3) Repeat forever (or until interrupted)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
LOG_DIR = ROOT / "data" / "agent"
LOOP_LOG = LOG_DIR / "background-loop.log"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run scrape + curation continuously.")
    parser.add_argument("--cycle-delay", type=float, default=90.0, help="Seconds between cycles.")
    parser.add_argument("--posts-per-subreddit", type=int, default=4, help="Scraper posts per subreddit.")
    parser.add_argument("--comments-per-post", type=int, default=25, help="Scraper comments per post.")
    parser.add_argument("--sample-size", type=int, default=8, help="Random subreddit sample size per cycle.")
    parser.add_argument("--batch-size", type=int, default=35, help="Curation items processed per cycle.")
    parser.add_argument("--min-complaints", type=int, default=5, help="Min complaints for visible issue cards.")
    parser.add_argument("--openai-model", default="gpt-4.1-mini", help="LLM model for optional LLM classification.")
    return parser.parse_args()


def log(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat()
    line = f"[{stamp}] {message}"
    print(line, flush=True)
    with LOOP_LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def run_step(command: list[str]) -> int:
    proc = subprocess.run(command, cwd=str(ROOT))
    return proc.returncode


def main() -> None:
    args = parse_args()

    scraper = SCRIPTS_DIR / "scrape_reddit_raw.py"
    curator = SCRIPTS_DIR / "curation_agent.py"

    if not scraper.exists() or not curator.exists():
        print("Required scripts are missing.", file=sys.stderr)
        sys.exit(1)

    log("Background agent started")
    while True:
        scrape_cmd = [
            sys.executable,
            str(scraper),
            "--posts-per-subreddit",
            str(args.posts_per_subreddit),
            "--comments-per-post",
            str(args.comments_per_post),
            "--sleep",
            "0.5",
            "--max-retries",
            "2",
            "--include-general",
            "--sample-size",
            str(args.sample_size),
        ]
        log("Running scraper cycle")
        scrape_rc = run_step(scrape_cmd)
        log(f"Scraper exit code: {scrape_rc}")

        curate_cmd = [
            sys.executable,
            str(curator),
            "--batch-size",
            str(args.batch_size),
            "--min-complaints",
            str(args.min_complaints),
            "--openai-model",
            args.openai_model,
        ]
        log("Running curation cycle")
        curate_rc = run_step(curate_cmd)
        log(f"Curation exit code: {curate_rc}")

        log(f"Sleeping {args.cycle_delay:.1f}s before next cycle")
        time.sleep(args.cycle_delay)


if __name__ == "__main__":
    main()
