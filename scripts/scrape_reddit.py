#!/usr/bin/env python3
"""
Build underlying issue cards from Reddit complaints and attach real Reddit solution ideas.

- Issues are discovered by semantic clustering of complaint comments.
- Only clusters with >= min-complaints are exported.
- Solutions are extracted from Reddit comments and assigned to the nearest issue cluster.
- Output contains no placeholder/filler records.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_JS = ROOT / "reddit-problems.js"
OUTPUT_JSON = ROOT / "data" / "reddit-problems.json"

USER_AGENT = "ProblemPinIssueCrawler/4.0 (research use)"

# Expanded coverage for broader signal collection.
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

COMPLAINT_PATTERNS = [
    re.compile(r"\bproblem(s)?\b", re.IGNORECASE),
    re.compile(r"\bissue(s)?\b", re.IGNORECASE),
    re.compile(r"\bstruggl(e|ing|ed)\b", re.IGNORECASE),
    re.compile(r"\bfrustrat(ed|ing|ion)\b", re.IGNORECASE),
    re.compile(r"\b(difficult|hard|painful|pain point)\b", re.IGNORECASE),
    re.compile(r"\b(can't|cannot|unable|won't|doesn't)\b", re.IGNORECASE),
    re.compile(r"\b(delay|late|backlog|slow)\b", re.IGNORECASE),
    re.compile(r"\b(expensive|costly|too much)\b", re.IGNORECASE),
    re.compile(r"\b(scope creep)\b", re.IGNORECASE),
    re.compile(r"\b(not working|broken|fails?)\b", re.IGNORECASE),
]

SOLUTION_PATTERNS = [
    re.compile(r"\bsolution\b", re.IGNORECASE),
    re.compile(r"\bfix\b", re.IGNORECASE),
    re.compile(r"\bwe solved\b", re.IGNORECASE),
    re.compile(r"\bwhat worked\b", re.IGNORECASE),
    re.compile(r"\btry\b", re.IGNORECASE),
    re.compile(r"\byou should\b", re.IGNORECASE),
    re.compile(r"\bbuild\b", re.IGNORECASE),
    re.compile(r"\bautomate\b", re.IGNORECASE),
    re.compile(r"\bapproach\b", re.IGNORECASE),
    re.compile(r"\bidea\b", re.IGNORECASE),
    re.compile(r"\bhere'?s what I did\b", re.IGNORECASE),
    re.compile(r"\bwe use\b", re.IGNORECASE),
    re.compile(r"\bworkflow\b", re.IGNORECASE),
]

BUSINESS_PATTERNS = [
    re.compile(r"\bcustomer(s)?\b", re.IGNORECASE),
    re.compile(r"\bclient(s)?\b", re.IGNORECASE),
    re.compile(r"\bstartup\b", re.IGNORECASE),
    re.compile(r"\bsmall business\b", re.IGNORECASE),
    re.compile(r"\bmarketing\b", re.IGNORECASE),
    re.compile(r"\blead(s)?\b", re.IGNORECASE),
    re.compile(r"\bsales?\b", re.IGNORECASE),
    re.compile(r"\binvoice\b", re.IGNORECASE),
    re.compile(r"\bpayment(s)?\b", re.IGNORECASE),
    re.compile(r"\bworkflow\b", re.IGNORECASE),
    re.compile(r"\bprocess(es)?\b", re.IGNORECASE),
    re.compile(r"\bfreelanc(e|er)\b", re.IGNORECASE),
    re.compile(r"\binventory\b", re.IGNORECASE),
    re.compile(r"\blogistics\b", re.IGNORECASE),
    re.compile(r"\bshipping\b", re.IGNORECASE),
    re.compile(r"\bsaas\b", re.IGNORECASE),
    re.compile(r"\bsoftware\b", re.IGNORECASE),
    re.compile(r"\boperations?\b", re.IGNORECASE),
    re.compile(r"\bmargins?\b", re.IGNORECASE),
    re.compile(r"\bpricing\b", re.IGNORECASE),
]

EXCLUDED_PATTERNS = [
    re.compile(r"\bhomework\b", re.IGNORECASE),
    re.compile(r"\bteacher\b", re.IGNORECASE),
    re.compile(r"\bclassmate\b", re.IGNORECASE),
    re.compile(r"\bdating\b", re.IGNORECASE),
    re.compile(r"\broommate\b", re.IGNORECASE),
]

GENERIC_TITLE_WORDS = {
    "problem",
    "problems",
    "issue",
    "issues",
    "struggling",
    "struggle",
    "startup",
    "startups",
    "business",
    "small",
    "company",
    "companies",
    "customer",
    "customers",
    "client",
    "clients",
    "reddit",
    "post",
    "comment",
}

ROLE_KEYWORDS = {
    "Full-Stack Engineer": ["build", "app", "website", "platform", "software", "automation", "tool"],
    "Backend Engineer": ["api", "backend", "server", "database", "integration"],
    "Data/AI Engineer": ["data", "analytics", "model", "ai", "ml", "prediction"],
    "Product Manager": ["roadmap", "feature", "workflow", "prioritize", "product"],
    "Designer": ["ux", "ui", "design", "interface", "onboarding"],
    "Growth Marketer": ["marketing", "ads", "seo", "campaign", "funnel"],
    "Sales Lead": ["sales", "outbound", "pipeline", "prospect", "closing"],
    "Operations Lead": ["operations", "process", "manual", "sop", "fulfillment", "logistics"],
    "Finance/Compliance": ["compliance", "legal", "invoice", "payment", "accounting", "tax"],
}


class UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cluster Reddit complaints into underlying issues and extract real solution ideas.")
    parser.add_argument("--posts-per-subreddit", type=int, default=20, help="Posts per subreddit per sort.")
    parser.add_argument("--comments-per-post", type=int, default=80, help="Comments requested per post.")
    parser.add_argument("--max-problems", type=int, default=120, help="Max issue cards to export.")
    parser.add_argument("--min-complaints", type=int, default=5, help="Minimum complaint comments per issue.")
    parser.add_argument("--issue-similarity-threshold", type=float, default=0.28, help="Complaint similarity threshold for clustering.")
    parser.add_argument("--solution-assignment-threshold", type=float, default=0.15, help="Minimum similarity to assign a solution to an issue.")
    parser.add_argument("--sleep", type=float, default=1.0, help="Pause between HTTP calls.")
    parser.add_argument("--max-retries", type=int, default=3, help="Retries on 429/temporary failures.")
    return parser.parse_args()


def clean_text(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text or "")
    text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def request_json(url: str, max_retries: int, sleep: float) -> Optional[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=35) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < max_retries:
                wait = sleep * (2 ** attempt)
                time.sleep(wait)
                continue
            raise
        except Exception:
            if attempt < max_retries:
                wait = sleep * (2 ** attempt)
                time.sleep(wait)
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
            reply_children = replies.get("data", {}).get("children", [])
            flatten_comments(reply_children, out)


def fetch_comments(subreddit: str, post_id: str, limit: int, max_retries: int, sleep: float) -> List[dict]:
    query = urllib.parse.urlencode({"limit": str(limit), "depth": "5", "sort": "top"})
    url = f"https://www.reddit.com/r/{subreddit}/comments/{post_id}.json?{query}"
    payload = request_json(url, max_retries=max_retries, sleep=sleep)
    if not isinstance(payload, list) or len(payload) < 2:
        return []
    comments_root = payload[1].get("data", {}).get("children", [])
    out: List[dict] = []
    flatten_comments(comments_root, out)
    return out


def count_pattern_hits(text: str, patterns: List[re.Pattern]) -> int:
    return sum(1 for pattern in patterns if pattern.search(text))


def is_business_relevant(text: str) -> bool:
    if len(text) < 45:
        return False
    if any(pattern.search(text) for pattern in EXCLUDED_PATTERNS):
        return False
    return count_pattern_hits(text, BUSINESS_PATTERNS) >= 1


def is_complaint_comment(text: str) -> bool:
    return is_business_relevant(text) and count_pattern_hits(text, COMPLAINT_PATTERNS) >= 1


def is_solution_comment(text: str) -> bool:
    # A solution must be business-relevant and contain clear proposal/action language.
    return is_business_relevant(text) and count_pattern_hits(text, SOLUTION_PATTERNS) >= 1


def safe_excerpt(text: str, max_len: int = 260) -> str:
    cleaned = clean_text(text)
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3].rstrip() + "..."


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:100] or "issue"


def detect_roles(solution_text: str, sector: str) -> List[str]:
    text = solution_text.lower()
    roles = []
    for role, keywords in ROLE_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            roles.append(role)

    if len(roles) >= 3:
        return roles[:3]

    sector_defaults = {
        "FinTech": ["Backend Engineer", "Finance/Compliance", "Product Manager"],
        "SaaS": ["Full-Stack Engineer", "Product Manager", "Designer"],
        "Commerce": ["Growth Marketer", "Sales Lead", "Operations Lead"],
        "Business": ["Product Manager", "Operations Lead", "Sales Lead"],
        "Mobility": ["Operations Lead", "Backend Engineer", "Product Manager"],
        "PropTech": ["Full-Stack Engineer", "Operations Lead", "Sales Lead"],
        "HealthTech": ["Backend Engineer", "Data/AI Engineer", "Finance/Compliance"],
        "Creator Economy": ["Designer", "Growth Marketer", "Full-Stack Engineer"],
    }
    for role in sector_defaults.get(sector, ["Full-Stack Engineer", "Product Manager", "Growth Marketer"]):
        if role not in roles:
            roles.append(role)
        if len(roles) >= 3:
            break
    return roles


def extract_comments(args: argparse.Namespace) -> Tuple[List[dict], List[dict]]:
    complaints: List[dict] = []
    solutions: List[dict] = []
    seen_comment_ids = set()

    for subreddit in SUBREDDITS:
        sector_hint = SUBREDDIT_TO_SECTOR.get(subreddit, "Business")
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
                comment_id = comment.get("id")
                if not comment_id or comment_id in seen_comment_ids:
                    continue
                seen_comment_ids.add(comment_id)

                body = clean_text(comment.get("body") or "")
                if not body or body in ("[deleted]", "[removed]"):
                    continue

                score = int(comment.get("score") or 0)
                permalink = comment.get("permalink") or ""
                created_utc = float(comment.get("created_utc") or datetime.now(timezone.utc).timestamp())

                base = {
                    "commentId": comment_id,
                    "text": safe_excerpt(body),
                    "rawText": body,
                    "subreddit": subreddit,
                    "sector": sector_hint,
                    "author": comment.get("author") or "unknown",
                    "score": score,
                    "createdUtc": created_utc,
                    "postTitle": post_title,
                    "sourceUrl": f"https://www.reddit.com{permalink}" if permalink else "",
                }

                if is_complaint_comment(body):
                    complaints.append(base)

                if is_solution_comment(body):
                    solutions.append(base)

            time.sleep(args.sleep)

    return complaints, solutions


def pick_title(cluster_texts: List[str]) -> str:
    if not cluster_texts:
        return "Operational Friction"

    phrase_vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(2, 4), min_df=1, max_features=2500)
    phrase_matrix = phrase_vectorizer.fit_transform(cluster_texts)
    phrase_scores = phrase_matrix.sum(axis=0).A1
    phrase_terms = phrase_vectorizer.get_feature_names_out()

    ranked = [
        (term, float(score))
        for term, score in zip(phrase_terms, phrase_scores)
        if term and not any(word in GENERIC_TITLE_WORDS for word in term.split())
    ]
    ranked.sort(key=lambda x: x[1], reverse=True)

    if ranked:
        phrase = ranked[0][0].strip()
        # Keep title focused and readable.
        words = phrase.split()
        if len(words) > 6:
            phrase = " ".join(words[:6])
        return phrase.title()

    word_vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 1), min_df=1, max_features=2500)
    word_matrix = word_vectorizer.fit_transform(cluster_texts)
    scores = word_matrix.sum(axis=0).A1
    words = word_vectorizer.get_feature_names_out()

    ranked_words = [
        (w, float(s))
        for w, s in zip(words, scores)
        if w and w not in GENERIC_TITLE_WORDS and len(w) > 2
    ]
    ranked_words.sort(key=lambda x: x[1], reverse=True)

    if ranked_words:
        best = " ".join(w for w, _ in ranked_words[:2])
        return best.title() + " Workflow Issues"

    return "Operational Friction"


def pick_summary(cluster_texts: List[str], complaint_count: int, subreddit_count: int) -> str:
    if not cluster_texts:
        return f"Evidence from {complaint_count} complaints across {subreddit_count} subreddits."

    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1, max_features=4000)
    matrix = vectorizer.fit_transform(cluster_texts)
    scores = matrix.sum(axis=0).A1
    terms = vectorizer.get_feature_names_out()

    ranked = sorted(zip(terms, scores), key=lambda x: x[1], reverse=True)
    keywords = [term for term, _ in ranked if term not in GENERIC_TITLE_WORDS][:4]
    keyword_str = ", ".join(keywords[:3]) if keywords else "recurring workflow pain points"

    return (
        f"Complaints repeatedly mention {keyword_str}. "
        f"Evidence: {complaint_count} comments across {subreddit_count} subreddits."
    )


def cluster_complaints(complaints: List[dict], similarity_threshold: float) -> Tuple[List[List[int]], TfidfVectorizer, object]:
    if not complaints:
        raise ValueError("No complaints to cluster")

    texts = [c["rawText"] for c in complaints]
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=2, max_df=0.92, max_features=12000)
    matrix = vectorizer.fit_transform(texts)

    n = matrix.shape[0]
    if n == 1:
        return [[0]], vectorizer, matrix

    sim = cosine_similarity(matrix)
    uf = UnionFind(n)

    for i in range(n):
        row = sim[i]
        for j in range(i + 1, n):
            if row[j] >= similarity_threshold:
                uf.union(i, j)

    grouped: Dict[int, List[int]] = defaultdict(list)
    for i in range(n):
        grouped[uf.find(i)].append(i)

    return list(grouped.values()), vectorizer, matrix


def demand_from_count(count: int) -> str:
    if count >= 30:
        return "high"
    if count >= 12:
        return "medium"
    return "low"


def investor_signal(sector: str, complaint_count: int, subreddit_count: int) -> bool:
    investable = {"FinTech", "HealthTech", "EdTech", "PropTech", "SaaS", "Business", "Commerce"}
    return sector in investable and complaint_count >= 8 and subreddit_count >= 2


def assign_solutions_to_issues(
    issues: List[dict],
    issue_indices: List[List[int]],
    complaint_matrix,
    solution_candidates: List[dict],
    complaint_vectorizer: TfidfVectorizer,
    assignment_threshold: float,
) -> None:
    if not issues or not solution_candidates:
        for issue in issues:
            issue["solutions"] = []
            issue["teams"] = 0
        return

    # Build centroids for retained issue clusters.
    centroid_rows = []
    for cluster_idx_list in issue_indices:
        centroid = complaint_matrix[cluster_idx_list].mean(axis=0)
        centroid_rows.append(centroid)

    # centroids as dense matrix for cosine similarity with sparse transform output.
    centroid_matrix = None
    for idx, row in enumerate(centroid_rows):
        arr = row.A if hasattr(row, "A") else row
        if centroid_matrix is None:
            centroid_matrix = arr
        else:
            centroid_matrix = __import__("numpy").vstack([centroid_matrix, arr])

    solution_texts = [item["rawText"] for item in solution_candidates]
    solution_matrix = complaint_vectorizer.transform(solution_texts)
    sims = cosine_similarity(solution_matrix, centroid_matrix)

    grouped: Dict[int, List[dict]] = defaultdict(list)

    for i, candidate in enumerate(solution_candidates):
        row = sims[i]
        best_issue_idx = int(row.argmax())
        best_score = float(row[best_issue_idx])
        if best_score < assignment_threshold:
            continue
        grouped[best_issue_idx].append(candidate)

    for issue_idx, issue in enumerate(issues):
        candidates = grouped.get(issue_idx, [])
        candidates.sort(key=lambda x: (x["score"], x["createdUtc"]), reverse=True)

        dedup = []
        seen = set()
        for c in candidates:
            key = (c["author"], c["text"].lower())
            if key in seen:
                continue
            seen.add(key)
            roles = detect_roles(c["rawText"], issue["sector"])
            dedup.append(
                {
                    "title": "Reddit Proposed Approach",
                    "summary": c["text"],
                    "roles": roles,
                    "author": c["author"],
                    "subreddit": c["subreddit"],
                    "score": c["score"],
                    "sourceUrl": c["sourceUrl"],
                    "createdUtc": c["createdUtc"],
                }
            )
            if len(dedup) >= 80:
                break

        issue["solutions"] = dedup

        unique_solution_authors = {s["author"] for s in dedup if s.get("author")}
        issue["teams"] = max(0, len(unique_solution_authors))


def aggregate_issues(
    complaints: List[dict],
    solutions: List[dict],
    min_complaints: int,
    max_problems: int,
    issue_similarity_threshold: float,
    solution_assignment_threshold: float,
) -> List[dict]:
    if not complaints:
        return []

    clusters, complaint_vectorizer, complaint_matrix = cluster_complaints(complaints, issue_similarity_threshold)
    now_ts = datetime.now(timezone.utc).timestamp()

    issues: List[dict] = []
    retained_cluster_indices: List[List[int]] = []
    seen_issue_ids = set()

    for cluster_ids in clusters:
        items = [complaints[i] for i in cluster_ids]
        complaint_count = len(items)

        if complaint_count < min_complaints:
            continue

        items.sort(key=lambda x: (x["score"], x["createdUtc"]), reverse=True)
        cluster_texts = [x["rawText"] for x in items]

        title = pick_title(cluster_texts)
        issue_id = f"reddit-issue-{slugify(title)}"
        if issue_id in seen_issue_ids:
            issue_id = f"{issue_id}-{len(seen_issue_ids) + 1}"
        seen_issue_ids.add(issue_id)

        dominant_sector = Counter([x["sector"] for x in items]).most_common(1)[0][0]
        subreddits = sorted({x["subreddit"] for x in items})
        subreddit_count = len(subreddits)

        total_score = sum(max(0, x["score"]) for x in items)
        recent_count = sum(1 for x in items if now_ts - x["createdUtc"] <= 7 * 24 * 60 * 60)

        interested = max(15, min(1200, int(complaint_count * 9 + total_score * 0.15)))
        demand = demand_from_count(complaint_count)
        fresh = recent_count >= max(2, int(complaint_count * 0.2))

        issue = {
            "id": issue_id,
            "title": title,
            "sector": dominant_sector,
            "summary": pick_summary(cluster_texts, complaint_count, subreddit_count),
            "interested": interested,
            "teams": 0,
            "demand": demand,
            "fresh": bool(fresh),
            "investor": investor_signal(dominant_sector, complaint_count, subreddit_count),
            "complaintCount": complaint_count,
            "sourcePlatform": "Reddit",
            "sourceSubreddits": subreddits,
            "complaints": [
                {
                    "text": x["text"],
                    "subreddit": x["subreddit"],
                    "author": x["author"],
                    "score": x["score"],
                    "createdUtc": x["createdUtc"],
                    "postTitle": x["postTitle"],
                    "sourceUrl": x["sourceUrl"],
                }
                for x in items[:200]
            ],
            "solutions": [],
        }

        issues.append(issue)
        retained_cluster_indices.append(cluster_ids)

    issues.sort(
        key=lambda x: (x["complaintCount"], x["interested"], len(x.get("sourceSubreddits", []))),
        reverse=True,
    )

    # Keep top issues before assigning solutions to avoid wasted mapping work.
    issues = issues[:max_problems]
    retained_cluster_indices = retained_cluster_indices[: len(issues)]

    assign_solutions_to_issues(
        issues=issues,
        issue_indices=retained_cluster_indices,
        complaint_matrix=complaint_matrix,
        solution_candidates=solutions,
        complaint_vectorizer=complaint_vectorizer,
        assignment_threshold=solution_assignment_threshold,
    )

    return issues


def write_outputs(issues: List[dict]) -> None:
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(issues, indent=2), encoding="utf-8")
    OUTPUT_JS.write_text("window.redditProblems = " + json.dumps(issues, indent=2) + ";\n", encoding="utf-8")


def main() -> None:
    args = parse_args()

    complaints, solutions = extract_comments(args)
    issues = aggregate_issues(
        complaints=complaints,
        solutions=solutions,
        min_complaints=args.min_complaints,
        max_problems=args.max_problems,
        issue_similarity_threshold=args.issue_similarity_threshold,
        solution_assignment_threshold=args.solution_assignment_threshold,
    )

    write_outputs(issues)

    print(f"[ok] complaints parsed: {len(complaints)}")
    print(f"[ok] solution candidates parsed: {len(solutions)}")
    print(f"[ok] underlying issues: {len(issues)} (min {args.min_complaints} complaints each)")
    print(f"[ok] JS:   {OUTPUT_JS}")
    print(f"[ok] JSON: {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
