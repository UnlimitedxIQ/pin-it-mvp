#!/usr/bin/env python3
"""
Stage 1: scrape Reddit comments into a raw processing queue.

Output:
- data/agent/queue.jsonl (pending items for the curation agent)
"""

from __future__ import annotations

import argparse
import json
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "agent"
QUEUE_FILE = DATA_DIR / "queue.jsonl"
PROBLEM_FILE = DATA_DIR / "problems.jsonl"
SOLUTION_FILE = DATA_DIR / "solutions.jsonl"
DELETED_FILE = DATA_DIR / "deleted.jsonl"

USER_AGENT = "ProblemPinRawScraper/1.0 (research use)"

SUBREDDITS = [
    "entrepreneur",
    "startups",
    "smallbusiness",
    "SaaS",
    "sales",
    "marketing",
    "personalfinance",
    "freelance",
    "healthIT",
    "realestateinvesting",
    "logistics",
    "ecommerce",
    "shopify",
    "webdev",
    "programming",
    "devops",
    "sysadmin",
    "productmanagement",
    "consulting",
    "supplychain",
    "restaurantowners",
    "retail",
    "realestate",
    "insurance",
    "cybersecurity",
    "analytics",
    "datascience",
    "customer_success",
    "SEO",
    "PPC",
    "EntrepreneurRideAlong",
    "indiehackers",
]

GENERAL_SUBREDDITS = [
    "AskReddit",
    "NoStupidQuestions",
    "mildlyinfuriating",
    "offmychest",
    "TrueOffMyChest",
    "rant",
    "vent",
    "relationships",
    "Advice",
    "lifehacks",
    "technology",
    "gadgets",
    "privacy",
    "sysadmin",
    "programming",
    "travel",
    "homeowners",
    "cars",
    "jobs",
    "antiwork",
    "college",
    "teachers",
    "healthcare",
]

SUBREDDIT_TO_SECTOR: Dict[str, str] = {
    "entrepreneur": "Business",
    "startups": "Business",
    "smallbusiness": "Commerce",
    "SaaS": "SaaS",
    "sales": "Commerce",
    "marketing": "Commerce",
    "personalfinance": "FinTech",
    "freelance": "Creator Economy",
    "healthIT": "HealthTech",
    "realestateinvesting": "PropTech",
    "logistics": "Mobility",
    "ecommerce": "Commerce",
    "shopify": "Commerce",
    "webdev": "SaaS",
    "programming": "SaaS",
    "devops": "SaaS",
    "sysadmin": "SaaS",
    "productmanagement": "Business",
    "consulting": "Business",
    "supplychain": "Mobility",
    "restaurantowners": "Commerce",
    "retail": "Commerce",
    "realestate": "PropTech",
    "insurance": "FinTech",
    "cybersecurity": "SaaS",
    "analytics": "SaaS",
    "datascience": "SaaS",
    "customer_success": "Business",
    "SEO": "Commerce",
    "PPC": "Commerce",
    "EntrepreneurRideAlong": "Business",
    "indiehackers": "Business",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape Reddit comments into raw queue.")
    parser.add_argument("--posts-per-subreddit", type=int, default=20, help="Posts to fetch per subreddit per sort.")
    parser.add_argument("--comments-per-post", type=int, default=70, help="Comments to request per post.")
    parser.add_argument("--sleep", type=float, default=1.0, help="Sleep between network calls.")
    parser.add_argument("--max-retries", type=int, default=3, help="Retry attempts for temporary failures.")
    parser.add_argument("--min-length", type=int, default=45, help="Minimum comment length to enqueue.")
    parser.add_argument(
        "--subreddits",
        default="",
        help="Optional comma-separated subreddit override (e.g., startups,entrepreneur,SaaS).",
    )
    parser.add_argument(
        "--max-subreddits",
        type=int,
        default=0,
        help="Optional cap on number of subreddits processed (0 = all).",
    )
    parser.add_argument(
        "--include-general",
        action="store_true",
        help="Include broader non-business subreddits to capture complaints about anything.",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=0,
        help="Randomly sample N subreddits from the selected set each run (0 = no sampling).",
    )
    return parser.parse_args()


def clean_text(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_jsonl_ids(path: Path) -> Set[str]:
    ids: Set[str] = set()
    if not path.exists():
        return ids
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            item_id = str(item.get("id") or item.get("commentId") or "").strip()
            if item_id:
                ids.add(item_id)
    return ids


def append_jsonl(path: Path, items: List[dict]) -> None:
    if not items:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def request_json(url: str, max_retries: int, sleep: float) -> Optional[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=35) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < max_retries:
                time.sleep(sleep * (2 ** attempt))
                continue
            raise
        except Exception:
            if attempt < max_retries:
                time.sleep(sleep * (2 ** attempt))
                continue
            raise
    return None


def fetch_posts(subreddit: str, sort: str, limit: int, max_retries: int, sleep: float) -> List[dict]:
    params = {"limit": str(limit)}
    if sort == "top":
        params["t"] = "month"
    query = urllib.parse.urlencode(params)
    url = f"https://www.reddit.com/r/{subreddit}/{sort}.json?{query}"
    payload = request_json(url, max_retries=max_retries, sleep=sleep)
    if not payload:
        return []
    return payload.get("data", {}).get("children", [])


def flatten_comments(children: Iterable[dict], out: List[dict]) -> None:
    for child in children:
        if child.get("kind") != "t1":
            continue
        data = child.get("data", {})
        if data:
            out.append(data)
        replies = data.get("replies")
        if isinstance(replies, dict):
            flatten_comments(replies.get("data", {}).get("children", []), out)


def fetch_comments(subreddit: str, post_id: str, limit: int, max_retries: int, sleep: float) -> List[dict]:
    query = urllib.parse.urlencode({"limit": str(limit), "depth": "5", "sort": "top"})
    url = f"https://www.reddit.com/r/{subreddit}/comments/{post_id}.json?{query}"
    payload = request_json(url, max_retries=max_retries, sleep=sleep)
    if not isinstance(payload, list) or len(payload) < 2:
        return []
    root = payload[1].get("data", {}).get("children", [])
    out: List[dict] = []
    flatten_comments(root, out)
    return out


def main() -> None:
    args = parse_args()
    now_iso = datetime.now(timezone.utc).isoformat()

    known_ids = set()
    for path in (QUEUE_FILE, PROBLEM_FILE, SOLUTION_FILE, DELETED_FILE):
        known_ids.update(load_jsonl_ids(path))

    new_items: List[dict] = []

    selected_subreddits = [s.strip() for s in args.subreddits.split(",") if s.strip()] if args.subreddits else list(SUBREDDITS)
    if args.include_general:
        selected_subreddits.extend(GENERAL_SUBREDDITS)
    # Deduplicate while preserving order.
    selected_subreddits = list(dict.fromkeys(selected_subreddits))
    if args.sample_size > 0 and args.sample_size < len(selected_subreddits):
        selected_subreddits = random.sample(selected_subreddits, args.sample_size)
    if args.max_subreddits > 0:
        selected_subreddits = selected_subreddits[: args.max_subreddits]

    for subreddit in selected_subreddits:
        sector = SUBREDDIT_TO_SECTOR.get(subreddit, "Business")
        posts: Dict[str, dict] = {}

        for sort in ("hot", "new", "top"):
            try:
                listing = fetch_posts(
                    subreddit=subreddit,
                    sort=sort,
                    limit=args.posts_per_subreddit,
                    max_retries=args.max_retries,
                    sleep=args.sleep,
                )
            except urllib.error.HTTPError as exc:
                print(f"[warn] /r/{subreddit} {sort}: HTTP {exc.code}")
                time.sleep(args.sleep)
                continue
            except Exception as exc:
                print(f"[warn] /r/{subreddit} {sort}: {exc}")
                time.sleep(args.sleep)
                continue

            for item in listing:
                data = item.get("data", {})
                post_id = data.get("id")
                if not post_id:
                    continue
                if data.get("stickied"):
                    continue
                posts[post_id] = data

            time.sleep(args.sleep)

        for post_id, post in posts.items():
            try:
                comments = fetch_comments(
                    subreddit=subreddit,
                    post_id=post_id,
                    limit=args.comments_per_post,
                    max_retries=args.max_retries,
                    sleep=args.sleep,
                )
            except urllib.error.HTTPError as exc:
                print(f"[warn] /r/{subreddit} post {post_id}: HTTP {exc.code}")
                time.sleep(args.sleep)
                continue
            except Exception as exc:
                print(f"[warn] /r/{subreddit} post {post_id}: {exc}")
                time.sleep(args.sleep)
                continue

            post_title = clean_text(post.get("title") or "")

            for comment in comments:
                comment_id = str(comment.get("id") or "").strip()
                if not comment_id or comment_id in known_ids:
                    continue

                body = clean_text(comment.get("body") or "")
                if not body or body in ("[deleted]", "[removed]"):
                    continue
                if len(body) < args.min_length:
                    continue

                permalink = comment.get("permalink") or ""
                created_utc = float(comment.get("created_utc") or datetime.now(timezone.utc).timestamp())

                record = {
                    "id": comment_id,
                    "platform": "reddit",
                    "subreddit": subreddit,
                    "sectorHint": sector,
                    "postId": post_id,
                    "postTitle": post_title,
                    "author": comment.get("author") or "unknown",
                    "score": int(comment.get("score") or 0),
                    "createdUtc": created_utc,
                    "sourceUrl": f"https://www.reddit.com{permalink}" if permalink else "",
                    "text": body,
                    "ingestedAt": now_iso,
                    "status": "pending",
                }
                new_items.append(record)
                known_ids.add(comment_id)

            time.sleep(args.sleep)

    append_jsonl(QUEUE_FILE, new_items)
    print(f"[ok] added to queue: {len(new_items)}")
    print(f"[ok] queue file: {QUEUE_FILE}")


if __name__ == "__main__":
    main()
