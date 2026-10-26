#!/usr/bin/env python3
"""Dig Dug level whose encounters choose from the Find a Game for Me list.

The only game query is the pre-populate query documented for that page:
the Cube ``RecentTopGames`` read, compiled to SQL against ``recent_top_games``.
Encounter options are comparable values on those rows (review label, quick
recency, and the review total the query already sorts by). Nothing here
adds another filter query.

Run from the repo root:

    pip install -r requirements.txt && python dig_dug.py

Then open http://127.0.0.1:8765/
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "dig_dug_web"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Page rank, best first. Same array findGames uses for "or better".
REVIEW_DESC_ORDER = (
    "Overwhelmingly Positive",
    "Very Positive",
    "Mostly Positive",
    "Positive",
    "Mixed",
    "Negative",
    "Mostly Negative",
    "Very Negative",
    "Overwhelmingly Negative",
)
REVIEW_RANK = {label: index for index, label in enumerate(REVIEW_DESC_ORDER)}

# getRecentTopGames always adds these when adult games are off.
ADULT_TAGS = ("Sexual Content", "Hentai")
# getAppIdsForContentDescriptors substring list, case-insensitive.
DESCRIPTOR_PATTERNS = (
    "sexual assault",
    "non-consensual",
    "bdsm",
    "extreme violence",
    "rape",
)

# Quick ranges from GameFinder.updateQuickDates, tightest first.
# day counts are the page's N×24h offsets. "beginning" is 1900-01-01.
QUICK_RANGES = (
    ("last3days", "Last 3 days", 3),
    ("lastweek", "Last week", 7),
    ("last2weeks", "Last 2 weeks", 14),
    ("lastmonth", "Last month", 30),
    ("last3months", "Last 3 months", 90),
    ("lastyear", "Last year", 365),
    ("last2years", "Last 2 years", 365 * 2),
    ("last3years", "Last 3 years", 365 * 3),
    ("last5years", "Last 5 years", 365 * 5),
    ("beginning", "Beginning of time", None),
)

# Compiled RecentTopGames query (no adult filter in the SQL text; the
# page adds app-id exclusion first, applied below to this same snapshot).
PREPOPULATE_SQL = """
SELECT
  recent_top_games.name,
  recent_top_games.app_id,
  recent_top_games.review_score_desc,
  (recent_top_games.release_date_actual::timestamptz AT TIME ZONE 'UTC'),
  sum(recent_top_games.total_positive),
  sum(recent_top_games.total_negative),
  sum(COALESCE(total_positive, 0) + COALESCE(total_negative, 0))
FROM recent_top_games
GROUP BY 1, 2, 3, 4
ORDER BY 7 DESC
LIMIT 100
"""

HOST = "0.0.0.0"
PORT = 8765
GAMES_ON_CARD = 4


def connection_string() -> str:
    """Same connection the pipeline scripts already use."""
    from dotenv import load_dotenv

    load_dotenv()
    value = os.getenv("SUPABASE_CONNECTION_STRING")
    if value:
        return value
    # The Steam migration script already stores the pipeline connection string.
    script = (ROOT / "create_games_steam_table.py").read_text()
    match = re.search(
        r"""os\.environ\[\s*['"]SUPABASE_CONNECTION_STRING['"]\s*\]\s*=\s*['"]([^'"]+)['"]""",
        script,
    )
    if not match:
        raise SystemExit(
            "SUPABASE_CONNECTION_STRING is not set and "
            "create_games_steam_table.py does not define one."
        )
    return match.group(1)


def _as_int(value) -> int:
    if value is None:
        return 0
    return int(value)


def _as_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def run_find_a_game_query(conn) -> list[dict]:
    """Run the Find a Game for Me pre-populate query and return its rows.

    This is the only game query. Adult-tag and content-descriptor exclusion
    is the first step of getRecentTopGames (includeAdultGames defaults to
    false). Exclusion is applied to this snapshot, which is the table the
    SELECT reads (100 rows).
    """
    import psycopg2

    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = '30s'")
        cur.execute(PREPOPULATE_SQL)
        raw_rows = cur.fetchall()
        app_ids = [row[1] for row in raw_rows]
        excluded = set()
        if app_ids:
            for tag in ADULT_TAGS:
                cur.execute(
                    """
                    SELECT DISTINCT app_id
                    FROM game_tags
                    WHERE tag = %s
                      AND app_id = ANY(%s)
                    """,
                    (tag, app_ids),
                )
                excluded.update(hit[0] for hit in cur.fetchall())
            cur.execute(
                """
                SELECT app_id, content_descriptors
                FROM recent_top_games
                WHERE app_id = ANY(%s)
                """,
                (app_ids,),
            )
            for app_id, descriptors in cur.fetchall():
                text = str(descriptors or "").lower()
                if any(pattern in text for pattern in DESCRIPTOR_PATTERNS):
                    excluded.add(app_id)

    rows = []
    for name, app_id, review, released, positive, negative, total in raw_rows:
        if app_id in excluded:
            continue
        rows.append(
            {
                "app_id": int(app_id),
                "title": (name or "").strip() or "Untitled",
                "review_score": review or "",
                "released": _as_date(released),
                "positive": _as_int(positive),
                "negative": _as_int(negative),
                "total_reviews": _as_int(total),
            }
        )
    rows.sort(
        key=lambda row: (
            -row["total_reviews"],
            REVIEW_RANK.get(row["review_score"], 99),
            row["app_id"],
        )
    )
    return rows


def _card(row: dict) -> dict:
    released = row["released"].isoformat() if row["released"] else "Unknown"
    reviews = (
        f'{row["total_reviews"]:,} '
        f'({row["positive"]:,} positive, {row["negative"]:,} negative)'
    )
    return {
        "app_id": row["app_id"],
        "title": row["title"],
        "fields": [
            {"label": "Review score", "value": row["review_score"] or "Unknown"},
            {"label": "Released", "value": released},
            {"label": "Reviews", "value": reviews},
        ],
    }


def _option(option_id: str, label: str, detail: str, filt: dict, matches: list[dict]) -> dict:
    if len(matches) < 1:
        raise RuntimeError(f"option {label!r} matched no rows")
    return {
        "id": option_id,
        "label": label,
        "detail": detail,
        "filter": filt,
        "match_count": len(matches),
        "games": [_card(row) for row in matches[:GAMES_ON_CARD]],
    }


def _slug(text: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in text)
    return "-".join(part for part in cleaned.split("-") if part)[:60] or "option"


def _review_score_encounter(rows: list[dict]) -> dict | None:
    by_label: dict[str, list[dict]] = {}
    for row in rows:
        if row["review_score"]:
            by_label.setdefault(row["review_score"], []).append(row)
    labels = [label for label in REVIEW_DESC_ORDER if by_label.get(label)]
    # Keep the encounter to one pack of monsters.
    labels = labels[:3]
    if len(labels) < 2:
        return None
    options = []
    for label in labels:
        matches = by_label[label]
        options.append(
            _option(
                _slug(label),
                label,
                f"{len(matches)} games",
                {"reviewScore": label},
                matches,
            )
        )
    return {
        "id": "review-score",
        "dimension": "reviewScore",
        "prompt": "Which review score should we dig up?",
        "options": options,
    }


def _window_start(now: datetime, days: int | None) -> date:
    if days is None:
        return date(1900, 1, 1)
    # GameFinder uses instant subtraction, then the UTC date (toISOString).
    return (now - timedelta(days=days)).date()


def _recency_encounter(rows: list[dict], now: datetime) -> dict | None:
    today = now.date()
    seen: list[frozenset] = []
    options = []
    for key, label, days in QUICK_RANGES:
        start = _window_start(now, days)
        matches = [
            row
            for row in rows
            if row["released"] is not None and start <= row["released"] <= today
        ]
        if not matches:
            continue
        identity = frozenset(row["app_id"] for row in matches)
        if any(identity == previous for previous in seen):
            continue
        seen.append(identity)
        options.append(
            _option(
                key,
                label,
                f"{len(matches)} games",
                {
                    "quickDateRange": key,
                    "minDate": start.isoformat(),
                    "maxDate": today.isoformat(),
                },
                matches,
            )
        )
        if len(options) == 3:
            break
    if len(options) < 2:
        return None
    return {
        "id": "recency",
        "dimension": "quickDateRange",
        "prompt": "How recent should the release be?",
        "options": options,
    }


def _review_total_encounter(rows: list[dict]) -> dict | None:
    """Split the query's review total into minReviews / maxReviews choices.

    Cut points are totals that actually appear on the rows. The measure is
    RecentTopGames.totalReviews (total_positive + total_negative).
    """
    distinct = sorted({row["total_reviews"] for row in rows})
    if len(distinct) < 2:
        return None

    def pack(low_inclusive, high_exclusive, label, filt):
        matches = [
            row
            for row in rows
            if low_inclusive <= row["total_reviews"] < high_exclusive
        ]
        if not matches:
            return None
        return _option(_slug(label), label, f"{len(matches)} games", filt, matches)

    lo = distinct[len(distinct) // 3]
    hi = distinct[(2 * len(distinct)) // 3]
    options = []
    if hi > lo:
        options = [
            item
            for item in (
                pack(hi, 10**12, f"At least {hi:,} reviews", {"minReviews": hi}),
                pack(
                    lo,
                    hi,
                    f"{lo:,}–{hi - 1:,} reviews",
                    {"minReviews": lo, "maxReviews": hi - 1},
                ),
                pack(0, lo, f"Under {lo:,} reviews", {"maxReviews": lo - 1}),
            )
            if item is not None
        ]
    if len(options) < 2:
        median = distinct[len(distinct) // 2]
        if median == distinct[0]:
            median = distinct[1]
        options = [
            item
            for item in (
                pack(median, 10**12, f"At least {median:,} reviews", {"minReviews": median}),
                pack(0, median, f"Under {median:,} reviews", {"maxReviews": median - 1}),
            )
            if item is not None
        ]
    options = options[:3]
    if len(options) < 2:
        return None
    return {
        "id": "review-total",
        "dimension": "totalReviews",
        "prompt": "How many reviews should it have?",
        "options": options,
    }


def build_encounters(rows: list[dict], now: datetime | None = None) -> list[dict]:
    """Turn one pre-populate result into encounter choices. No extra query."""
    if now is None:
        now = datetime.now(timezone.utc)
    encounters = [
        _review_score_encounter(rows),
        _recency_encounter(rows, now),
        _review_total_encounter(rows),
    ]
    built = [enc for enc in encounters if enc is not None]
    known = {row["app_id"] for row in rows}
    for enc in built:
        if len(enc["options"]) < 2:
            raise RuntimeError(f"{enc['id']} needs two or more choices")
        for option in enc["options"]:
            for game in option["games"]:
                if game["app_id"] not in known:
                    raise RuntimeError("choice listed a game outside the query")
    return built


def build_level(rows: list[dict], now: datetime | None = None) -> dict:
    encounters = build_encounters(rows, now)
    if not encounters:
        raise RuntimeError("the pre-populate query did not yield two comparable choices")
    return {
        "row_count": len(rows),
        "source": "recent_top_games",
        "encounters": encounters,
    }


def load_level(conn) -> dict:
    rows = run_find_a_game_query(conn)
    if not rows:
        raise RuntimeError("recent_top_games returned no rows")
    return build_level(rows)


class Handler(BaseHTTPRequestHandler):
    level = None

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/level":
            body = json.dumps(self.level).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/":
            path = "/index.html"
        file_path = (WEB / path.lstrip("/")).resolve()
        if not str(file_path).startswith(str(WEB.resolve())) or not file_path.is_file():
            self.send_error(404)
            return
        kind = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
        }.get(file_path.suffix, "application/octet-stream")
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s\n" % (fmt % args))


def serve(level: dict) -> None:
    Handler.level = level
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Dig Dug is at http://127.0.0.1:{PORT}/")
    print(f"Pre-populate rows: {level['row_count']} from recent_top_games")
    for enc in level["encounters"]:
        labels = ", ".join(opt["label"] for opt in enc["options"])
        print(f"  {enc['dimension']}: {labels}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


def main() -> None:
    import psycopg2

    try:
        conn = psycopg2.connect(connection_string(), connect_timeout=15)
    except Exception as exc:
        text = str(exc)
        if "postgresql://" in text or "password" in text.lower():
            text = exc.__class__.__name__
        raise SystemExit(f"Could not connect to the games database: {text}") from None
    try:
        level = load_level(conn)
    except Exception as exc:
        text = str(exc)
        if "postgresql://" in text:
            text = exc.__class__.__name__
        raise SystemExit(f"Could not run the Find a Game query: {text}") from None
    finally:
        conn.close()
    serve(level)


if __name__ == "__main__":
    main()
