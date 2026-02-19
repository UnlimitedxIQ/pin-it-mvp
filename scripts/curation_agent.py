#!/usr/bin/env python3
"""
Stage 2: slow curation agent for Reddit queue items.

For each queued item, classify into:
- problem
- solution
- not_related

Behavior:
- problems are persisted for issue clustering.
- solution and not_related items are removed from the active stream and logged.
- optionally runs continuously in small batches with pauses.
- rebuilds live issue data for frontend after each batch.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "agent"
QUEUE_FILE = DATA_DIR / "queue.jsonl"
PROBLEM_FILE = DATA_DIR / "problems.jsonl"
DELETED_FILE = DATA_DIR / "deleted.jsonl"
AUDIT_FILE = DATA_DIR / "audit.jsonl"

# Frontend output consumed by app.js
CURATED_JSON = ROOT / "data" / "reddit-problems.json"
CURATED_JS = ROOT / "reddit-problems.js"
CURATED_CANDIDATE_JSON = ROOT / "data" / "reddit-problems-candidates.json"

COMPLAINT_PATTERNS = [
    re.compile(r"\bproblem(s)?\b", re.IGNORECASE),
    re.compile(r"\bissue(s)?\b", re.IGNORECASE),
    re.compile(r"\bstruggl(e|ing|ed)\b", re.IGNORECASE),
    re.compile(r"\bfrustrat(ed|ing|ion)\b", re.IGNORECASE),
    re.compile(r"\b(can't|cannot|unable|won't|doesn't)\b", re.IGNORECASE),
    re.compile(r"\b(delay|late|backlog|slow)\b", re.IGNORECASE),
    re.compile(r"\b(expensive|costly|too much)\b", re.IGNORECASE),
    re.compile(r"\bnot working\b", re.IGNORECASE),
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
    re.compile(r"\bwe use\b", re.IGNORECASE),
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

STOPWORDS = {
    "the", "and", "that", "this", "with", "from", "have", "been", "they", "them", "into", "their", "there",
    "what", "when", "where", "which", "about", "were", "your", "you", "our", "for", "while", "over", "across",
    "business", "problem", "problems", "issue", "issues", "startup", "startups", "customer", "customers",
    "client", "clients", "comment", "comments", "reddit", "post", "posts",
}

JUNK_PATTERNS = [
    re.compile(r"this is a friendly reminder that r\/", re.IGNORECASE),
    re.compile(r"i am a bot[, ]", re.IGNORECASE),
    re.compile(r"automoderator", re.IGNORECASE),
    re.compile(r"removed automatically", re.IGNORECASE),
    re.compile(r"be respectful and follow the rules", re.IGNORECASE),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI curation agent for raw Reddit queue.")
    parser.add_argument("--batch-size", type=int, default=25, help="Items to process per cycle.")
    parser.add_argument("--item-delay", type=float, default=0.25, help="Sleep between item classifications.")
    parser.add_argument("--cycle-delay", type=float, default=10.0, help="Sleep between cycles in continuous mode.")
    parser.add_argument("--continuous", action="store_true", help="Keep running until interrupted.")
    parser.add_argument("--min-complaints", type=int, default=5, help="Min complaints needed for a visible issue card.")
    parser.add_argument("--openai-model", default="gpt-4.1-mini", help="Model used if OPENAI_API_KEY is set.")
    return parser.parse_args()


def read_jsonl(path: Path) -> List[dict]:
    if not path.exists():
        return []
    items: List[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return items


def write_jsonl(path: Path, items: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def append_jsonl(path: Path, items: List[dict]) -> None:
    if not items:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:90] or "issue"


def count_hits(text: str, patterns: List[re.Pattern]) -> int:
    return sum(1 for p in patterns if p.search(text))


def derive_issue_title(text: str) -> str:
    tokens = re.findall(r"[a-zA-Z]{3,}", text.lower())
    filtered = [token for token in tokens if token not in STOPWORDS]
    if not filtered:
        return "Operational Friction"
    common = Counter(filtered).most_common(4)
    words = [w for w, _ in common[:3]]
    if not words:
        return "Operational Friction"
    if len(words) == 1:
        return words[0].title() + " Workflow Issues"
    return " ".join(words[:3]).title()


def detect_roles(text: str, sector_hint: str) -> List[str]:
    body = text.lower()
    roles: List[str] = []
    for role, keywords in ROLE_KEYWORDS.items():
        if any(keyword in body for keyword in keywords):
            roles.append(role)
    if len(roles) >= 3:
        return roles[:3]

    defaults = {
        "FinTech": ["Backend Engineer", "Finance/Compliance", "Product Manager"],
        "SaaS": ["Full-Stack Engineer", "Product Manager", "Designer"],
        "Commerce": ["Growth Marketer", "Sales Lead", "Operations Lead"],
        "Business": ["Product Manager", "Operations Lead", "Sales Lead"],
        "Mobility": ["Operations Lead", "Backend Engineer", "Product Manager"],
        "PropTech": ["Full-Stack Engineer", "Operations Lead", "Sales Lead"],
        "HealthTech": ["Backend Engineer", "Data/AI Engineer", "Finance/Compliance"],
        "Creator Economy": ["Designer", "Growth Marketer", "Full-Stack Engineer"],
    }
    for role in defaults.get(sector_hint, ["Full-Stack Engineer", "Product Manager", "Growth Marketer"]):
        if role not in roles:
            roles.append(role)
        if len(roles) >= 3:
            break
    return roles


def classify_heuristic(text: str, sector_hint: str) -> dict:
    lower_text = text.lower()
    if any(pattern.search(lower_text) for pattern in JUNK_PATTERNS):
        return {
            "label": "not_related",
            "confidence": 0.95,
            "reason": "Detected moderation/bot boilerplate.",
            "issue_title": derive_issue_title(text),
            "roles": [],
        }

    business = count_hits(text, BUSINESS_PATTERNS)
    complaint = count_hits(text, COMPLAINT_PATTERNS)
    solution = count_hits(text, SOLUTION_PATTERNS)

    if solution >= complaint + 1 and solution > 0:
        return {
            "label": "solution",
            "confidence": min(0.95, 0.55 + solution * 0.08),
            "reason": "Contains explicit solution/proposal language.",
            "issue_title": derive_issue_title(text),
            "roles": detect_roles(text, sector_hint),
        }

    if complaint > 0:
        return {
            "label": "problem",
            "confidence": min(0.95, 0.5 + complaint * 0.1),
            "reason": "Contains recurring pain/complaint signals.",
            "issue_title": derive_issue_title(text),
            "roles": [],
        }

    if solution > 0:
        return {
            "label": "solution",
            "confidence": 0.6,
            "reason": "Contains solution language with business context.",
            "issue_title": derive_issue_title(text),
            "roles": detect_roles(text, sector_hint),
        }

    if business > 1 and len(text.split()) > 14:
        return {
            "label": "problem",
            "confidence": 0.52,
            "reason": "Likely friction discussion with weak explicit markers.",
            "issue_title": derive_issue_title(text),
            "roles": [],
        }

    return {
        "label": "not_related",
        "confidence": 0.62,
        "reason": "No clear problem/solution pattern detected.",
        "issue_title": derive_issue_title(text),
        "roles": [],
    }


def classify_openai(text: str, sector_hint: str, model: str) -> Optional[dict]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Classify the Reddit comment as exactly one label: problem, solution, or not_related. "
                    "Return compact JSON with keys: label, confidence, reason, issue_title, roles. "
                    "roles must be an array of role strings (empty if not needed). "
                    "issue_title should be a short underlying issue title."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({"sector_hint": sector_hint, "comment": text}),
            },
        ],
        "response_format": {"type": "json_object"},
    }

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=40) as response:
            body = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    try:
        content = body["choices"][0]["message"]["content"]
        parsed = json.loads(content)
    except Exception:
        return None

    label = str(parsed.get("label", "")).strip().lower()
    if label not in {"problem", "solution", "not_related"}:
        return None

    issue_title = str(parsed.get("issue_title") or derive_issue_title(text)).strip() or derive_issue_title(text)
    roles = parsed.get("roles") if isinstance(parsed.get("roles"), list) else []

    return {
        "label": label,
        "confidence": float(parsed.get("confidence") or 0.7),
        "reason": str(parsed.get("reason") or "LLM classification."),
        "issue_title": issue_title,
        "roles": [str(r).strip() for r in roles if str(r).strip()][:6],
    }


def classify_item(text: str, sector_hint: str, model: str) -> dict:
    llm = classify_openai(text, sector_hint, model=model)
    if llm:
        if llm["label"] == "solution" and not llm["roles"]:
            llm["roles"] = detect_roles(text, sector_hint)
        return llm
    return classify_heuristic(text, sector_hint)


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


def _cluster_title(texts: List[str]) -> str:
    if not texts:
        return "Operational Friction"

    try:
        vec = TfidfVectorizer(stop_words="english", ngram_range=(2, 4), min_df=1, max_features=2500)
        mat = vec.fit_transform(texts)
        scores = mat.sum(axis=0).A1
        terms = vec.get_feature_names_out()
        ranked = sorted(
            ((t, float(s)) for t, s in zip(terms, scores) if t),
            key=lambda x: x[1],
            reverse=True,
        )
        if ranked:
            phrase = ranked[0][0].strip()
            words = phrase.split()
            if len(words) > 6:
                phrase = " ".join(words[:6])
            return phrase.title()
    except Exception:
        pass

    return derive_issue_title(" ".join(texts[:5]))


def _cluster_summary(texts: List[str], complaint_count: int, subreddit_count: int) -> str:
    try:
        vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1, max_features=4000)
        mat = vec.fit_transform(texts)
        scores = mat.sum(axis=0).A1
        terms = vec.get_feature_names_out()
        ranked = sorted(zip(terms, scores), key=lambda x: x[1], reverse=True)
        top_terms = [term for term, _ in ranked[:5]]
        if top_terms:
            return (
                f"Recurring complaints mention {', '.join(top_terms[:3])}. "
                f"Evidence: {complaint_count} comments across {subreddit_count} subreddits."
            )
    except Exception:
        pass
    return f"Recurring complaints detected from {complaint_count} Reddit comments across {subreddit_count} subreddits."


def _cluster_problem_records(problem_items: List[dict], threshold: float = 0.24) -> Tuple[List[List[int]], TfidfVectorizer, object]:
    texts = [str(x.get("text") or "") for x in problem_items]
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=2, max_df=0.93, max_features=10000)
    mat = vec.fit_transform(texts)

    n = len(problem_items)
    if n <= 1:
        return ([list(range(n))] if n else []), vec, mat

    sim = cosine_similarity(mat)
    uf = UnionFind(n)
    for i in range(n):
        row = sim[i]
        for j in range(i + 1, n):
            if row[j] >= threshold:
                uf.union(i, j)

    grouped: Dict[int, List[int]] = defaultdict(list)
    for i in range(n):
        grouped[uf.find(i)].append(i)
    return list(grouped.values()), vec, mat


def rebuild_curated_issues(min_complaints: int) -> None:
    problems = read_jsonl(PROBLEM_FILE)
    problems = [p for p in problems if str(p.get("author") or "").lower() not in {"automoderator", "moderator"}]

    if not problems:
        CURATED_JSON.parent.mkdir(parents=True, exist_ok=True)
        CURATED_JSON.write_text("[]", encoding="utf-8")
        CURATED_JS.write_text("window.redditProblems = [];\n", encoding="utf-8")
        CURATED_CANDIDATE_JSON.write_text("[]", encoding="utf-8")
        return

    # Semantic clustering for underlying issues.
    try:
        cluster_indices, _, _ = _cluster_problem_records(problems, threshold=0.24)
    except Exception:
        cluster_indices = [[i] for i in range(len(problems))]

    candidate_min_complaints = 3
    published_clusters = [idxs for idxs in cluster_indices if len(idxs) >= min_complaints]
    candidate_clusters = [idxs for idxs in cluster_indices if candidate_min_complaints <= len(idxs) < min_complaints]

    def build_issue_payload(idxs: List[int], status: str) -> dict:
        items = [problems[i] for i in idxs]
        items.sort(key=lambda x: (int(x.get("score") or 0), float(x.get("createdUtc") or 0)), reverse=True)

        texts = [str(x.get("text") or "") for x in items]
        title = _cluster_title(texts)
        key = slugify(title)
        sector = Counter([str(x.get("sectorHint") or "General") for x in items]).most_common(1)[0][0]
        subreddits = sorted({str(x.get("subreddit") or "") for x in items if x.get("subreddit")})
        complaint_count = len(items)
        total_score = sum(max(0, int(x.get("score") or 0)) for x in items)
        interested = max(10, int(complaint_count * 8 + total_score * 0.12))
        demand = "high" if complaint_count >= 30 else ("medium" if complaint_count >= 12 else "low")

        complaint_payload = [
            {
                "text": x.get("text"),
                "subreddit": x.get("subreddit"),
                "author": x.get("author"),
                "score": int(x.get("score") or 0),
                "createdUtc": x.get("createdUtc"),
                "postTitle": x.get("postTitle"),
                "sourceUrl": x.get("sourceUrl"),
            }
            for x in items[:220]
        ]

        return {
            "id": f"reddit-issue-{key}",
            "title": title,
            "sector": sector,
            "summary": _cluster_summary(texts, complaint_count, len(subreddits)),
            "interested": interested,
            "teams": 0,
            "demand": demand,
            "fresh": True,
            "investor": complaint_count >= 10,
            "complaintCount": complaint_count,
            "sourcePlatform": "Reddit",
            "sourceSubreddits": subreddits,
            "complaints": complaint_payload,
            "solutions": [],
            "status": status,
        }

    published_issues = sorted(
        [build_issue_payload(idxs, "published") for idxs in published_clusters],
        key=lambda x: (x["complaintCount"], x["interested"]),
        reverse=True,
    )
    candidate_issues = sorted(
        [build_issue_payload(idxs, "candidate") for idxs in candidate_clusters],
        key=lambda x: (x["complaintCount"], x["interested"]),
        reverse=True,
    )

    CURATED_JSON.parent.mkdir(parents=True, exist_ok=True)
    CURATED_JSON.write_text(json.dumps(published_issues, indent=2), encoding="utf-8")
    CURATED_JS.write_text("window.redditProblems = " + json.dumps(published_issues, indent=2) + ";\n", encoding="utf-8")
    CURATED_CANDIDATE_JSON.write_text(json.dumps(candidate_issues, indent=2), encoding="utf-8")


def process_batch(batch: List[dict], model: str) -> Tuple[List[dict], List[dict], List[dict], int]:
    problems_out: List[dict] = []
    deleted_out: List[dict] = []
    audit_out: List[dict] = []
    solution_count = 0

    now_iso = datetime.now(timezone.utc).isoformat()

    for item in batch:
        text = str(item.get("text") or "").strip()
        sector_hint = str(item.get("sectorHint") or "Business")
        result = classify_item(text=text, sector_hint=sector_hint, model=model)

        issue_title = str(result.get("issue_title") or derive_issue_title(text)).strip() or "Operational Friction"
        issue_key = slugify(issue_title)

        enriched = dict(item)
        enriched["classifiedAt"] = now_iso
        enriched["classification"] = result["label"]
        enriched["confidence"] = float(result.get("confidence") or 0.6)
        enriched["reason"] = str(result.get("reason") or "")
        enriched["issueTitle"] = issue_title
        enriched["issueKey"] = issue_key
        enriched["roles"] = result.get("roles") if isinstance(result.get("roles"), list) else []

        audit_out.append(
            {
                "id": enriched.get("id"),
                "classification": enriched["classification"],
                "issueKey": issue_key,
                "issueTitle": issue_title,
                "confidence": enriched["confidence"],
                "at": now_iso,
            }
        )

        if result["label"] == "problem":
            problems_out.append(enriched)
        elif result["label"] == "solution":
            # We classify solution-like text for audit visibility but do not surface Reddit solutions on the site.
            solution_count += 1
            deleted_out.append(enriched)
        else:
            deleted_out.append(enriched)

    return problems_out, deleted_out, audit_out, solution_count


def run_once(args: argparse.Namespace) -> None:
    queue = read_jsonl(QUEUE_FILE)
    if not queue:
        rebuild_curated_issues(min_complaints=args.min_complaints)
        print("[ok] queue is empty | curated output refreshed")
        return

    batch = queue[: args.batch_size]
    remaining = queue[args.batch_size :]

    problems_out, deleted_out, audit_out, solution_count = process_batch(batch, model=args.openai_model)

    write_jsonl(QUEUE_FILE, remaining)
    append_jsonl(PROBLEM_FILE, problems_out)
    append_jsonl(DELETED_FILE, deleted_out)
    append_jsonl(AUDIT_FILE, audit_out)

    rebuild_curated_issues(min_complaints=args.min_complaints)

    print(
        f"[ok] processed {len(batch)} | problems={len(problems_out)} | "
        f"solutions_filtered={solution_count} | deleted={len(deleted_out)} | remaining={len(remaining)}"
    )


def main() -> None:
    args = parse_args()

    if not args.continuous:
        run_once(args)
        return

    while True:
        run_once(args)
        time.sleep(args.cycle_delay)


if __name__ == "__main__":
    main()
