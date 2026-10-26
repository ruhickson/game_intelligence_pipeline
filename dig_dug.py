#!/usr/bin/env python3
"""Dig Dug level that builds one Find a Game search across seven avenues.

Each avenue adds one filter from the Find a Game for Me player search
(``findGames`` in gamediscoverytool). After the last avenue, that accumulated
query runs against ``games`` and ``game_tags``. Clicking the discover tile
shows the first three rows.

The always-on predicates are the ones the Games cube adds on every search:
type ``game``, name not a playtest, ``coming_soon`` null or false, and adult
exclusion (tags Sexual Content and Hentai, plus the content-descriptor
substrings). Page defaults that would omit a clause (review Any, min reviews
0, max reviews 10000000, hours off, AI any, no tags) are not added here. The
avenue choice is what adds that clause. Recency is a single date window, the
one the player picked, because the page has only one release-date range.

Run from the repo root:

    pip install -r requirements.txt && python dig_dug.py

Then open http://127.0.0.1:8765/
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "dig_dug_web"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Page rank, best first. "Or better" sends this prefix through the chosen label.
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

# getRecentTopGames / findGames add these when includeAdultGames is false.
ADULT_TAGS = ("Sexual Content", "Hentai")
DESCRIPTOR_PATTERNS = (
    "sexual assault",
    "non-consensual",
    "BDSM",
    "extreme violence",
    "rape",
)

# GameFinder.updateQuickDates. N is a multiple of 24h, then the UTC date.
RECENCY_DAYS = {
    "lastyear": 365,
    "last3years": 365 * 3,
    "last5years": 365 * 5,
}

# Page default order and cap. The tile shows the first three of this list.
RESULT_LIMIT = 100
SHOWN = 3

# Worst combination of the options below. Startup refuses to serve if this
# returns fewer than three games, so every other combination (looser nested
# recency and review label, and the other tag / review-count / AI / exclude
# options) still has a tile to open.
WORST_CHOICES = {
    "recency": "lastyear",
    "review-score": "overwhelmingly-positive",
    "tag": "indie",
    "min-reviews": "min-500",
    "max-reviews": "max-20000",
    "ai": "declared",
    "exclude-tag": "exclude-early-access",
}

ALWAYS = (
    "type = 'game'",
    "name NOT ILIKE '%playtest%'",
    "release_date.coming_soon IS NULL OR 'false'",
    "exclude tags Sexual Content and Hentai",
    "exclude content descriptors sexual assault, non-consensual, BDSM, extreme violence, rape",
    "ORDER BY total_positive + total_negative DESC",
    f"LIMIT {RESULT_LIMIT}",
)

# Avenue order is the order the player reaches them, bottom to top.
ENCOUNTERS = (
    {
        "id": "recency",
        "dimension": "quickDateRange",
        "prompt": "How recent should the release be?",
        "options": (
            {
                "id": "lastyear",
                "label": "Last year",
                "filter": {"quickDateRange": "lastyear"},
            },
            {
                "id": "last3years",
                "label": "Last 3 years",
                "filter": {"quickDateRange": "last3years"},
            },
            {
                "id": "last5years",
                "label": "Last 5 years",
                "filter": {"quickDateRange": "last5years"},
            },
        ),
    },
    {
        "id": "review-score",
        "dimension": "reviewScore",
        "prompt": "Which review score, or better?",
        "options": (
            {
                "id": "overwhelmingly-positive",
                "label": "Overwhelmingly Positive",
                "filter": {
                    "reviewScore": "Overwhelmingly Positive",
                    "reviewScoreOrBetter": True,
                },
            },
            {
                "id": "very-positive",
                "label": "Very Positive or better",
                "filter": {
                    "reviewScore": "Very Positive",
                    "reviewScoreOrBetter": True,
                },
            },
            {
                "id": "mostly-positive",
                "label": "Mostly Positive or better",
                "filter": {
                    "reviewScore": "Mostly Positive",
                    "reviewScoreOrBetter": True,
                },
            },
        ),
    },
    {
        "id": "tag",
        "dimension": "tags",
        "prompt": "Which tag should it include?",
        "options": (
            {
                "id": "singleplayer",
                "label": "Singleplayer",
                "filter": {"tags": ["Singleplayer"]},
            },
            {
                "id": "indie",
                "label": "Indie",
                "filter": {"tags": ["Indie"]},
            },
            {
                "id": "casual",
                "label": "Casual",
                "filter": {"tags": ["Casual"]},
            },
        ),
    },
    {
        "id": "min-reviews",
        "dimension": "minReviews",
        "prompt": "How many reviews, at least?",
        "options": (
            {
                "id": "min-100",
                "label": "At least 100 reviews",
                "filter": {"minReviews": 100},
            },
            {
                "id": "min-500",
                "label": "At least 500 reviews",
                "filter": {"minReviews": 500},
            },
        ),
    },
    {
        "id": "max-reviews",
        "dimension": "maxReviews",
        "prompt": "How many reviews, at most?",
        "options": (
            {
                "id": "max-20000",
                "label": "At most 20,000 reviews",
                "filter": {"maxReviews": 20000},
            },
            {
                "id": "max-50000",
                "label": "At most 50,000 reviews",
                "filter": {"maxReviews": 50000},
            },
        ),
    },
    {
        "id": "ai",
        "dimension": "aiDeclaration",
        "prompt": "Declared as made with AI?",
        "options": (
            {
                "id": "not-declared",
                "label": "No",
                "filter": {"aiDeclaration": "not_declared"},
            },
            {
                "id": "declared",
                "label": "Yes",
                "filter": {"aiDeclaration": "declared"},
            },
        ),
    },
    {
        "id": "exclude-tag",
        "dimension": "excludeTags",
        "prompt": "Which tag should be left out?",
        "options": (
            {
                "id": "exclude-early-access",
                "label": "Exclude Early Access",
                "filter": {"excludeTags": ["Early Access"]},
            },
            {
                "id": "exclude-free-to-play",
                "label": "Exclude Free to Play",
                "filter": {"excludeTags": ["Free to Play"]},
            },
        ),
    },
)

HOST = "0.0.0.0"
PORT = 8765

AI_SQL = {
    "declared": "g.made_with_ai IS TRUE",
    "not_declared": "g.made_with_ai IS FALSE",
}


def connection_string() -> str:
    """Same connection the pipeline scripts already use."""
    from dotenv import load_dotenv

    load_dotenv()
    value = os.getenv("SUPABASE_CONNECTION_STRING")
    if value:
        return value
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


def _safe_error(exc: Exception) -> str:
    text = str(exc)
    if "postgresql://" in text or "password" in text.lower():
        return exc.__class__.__name__
    return text


def _option(encounter: dict, option_id: str) -> dict:
    for option in encounter["options"]:
        if option["id"] == option_id:
            return option
    raise ValueError(f"unknown option {option_id!r} for {encounter['id']}")


def _selected(choices: dict) -> list[tuple[dict, dict]]:
    if not isinstance(choices, dict):
        raise ValueError("choices must be an object")
    unknown = set(choices) - {enc["id"] for enc in ENCOUNTERS}
    if unknown:
        raise ValueError(f"unknown encounter {sorted(unknown)[0]}")
    selected = []
    for encounter in ENCOUNTERS:
        if encounter["id"] not in choices:
            raise ValueError(f"missing choice for {encounter['id']}")
        selected.append((encounter, _option(encounter, choices[encounter["id"]])))
    return selected


def _labels_or_better(label: str) -> tuple[str, ...]:
    index = REVIEW_DESC_ORDER.index(label)
    return REVIEW_DESC_ORDER[: index + 1]


def _date_window(now: datetime, days: int) -> tuple:
    moment = now.astimezone(timezone.utc)
    today = moment.date()
    start = (moment - timedelta(days=days)).date()
    return start, today


def clause_text(encounter: dict, option: dict, now: datetime) -> str:
    """The SQL predicate this avenue option adds. Built only from our options."""
    filt = option["filter"]
    if encounter["dimension"] == "quickDateRange":
        start, today = _date_window(now, RECENCY_DAYS[option["id"]])
        return f"release_date_actual BETWEEN {start.isoformat()} AND {today.isoformat()}"
    if encounter["dimension"] == "reviewScore":
        labels = _labels_or_better(filt["reviewScore"])
        quoted = ", ".join(f"'{label}'" for label in labels)
        return f"review_score_desc IN ({quoted})"
    if encounter["dimension"] == "tags":
        return f"game_tags.tag = '{filt['tags'][0]}'"
    if encounter["dimension"] == "minReviews":
        return f"(total_positive + total_negative) >= {int(filt['minReviews'])}"
    if encounter["dimension"] == "maxReviews":
        return f"(total_positive + total_negative) <= {int(filt['maxReviews'])}"
    if encounter["dimension"] == "aiDeclaration":
        word = "TRUE" if filt["aiDeclaration"] == "declared" else "FALSE"
        return f"made_with_ai IS {word}"
    if encounter["dimension"] == "excludeTags":
        tag = filt["excludeTags"][0]
        return f"app_id NOT IN (SELECT app_id FROM game_tags WHERE tag = '{tag}')"
    raise ValueError(f"unknown dimension {encounter['dimension']}")


def build_level(now: datetime | None = None) -> dict:
    if now is None:
        now = datetime.now(timezone.utc)
    encounters = []
    for encounter in ENCOUNTERS:
        encounters.append(
            {
                "id": encounter["id"],
                "dimension": encounter["dimension"],
                "prompt": encounter["prompt"],
                "options": [
                    {
                        "id": option["id"],
                        "label": option["label"],
                        "detail": clause_text(encounter, option, now),
                        "filter": option["filter"],
                    }
                    for option in encounter["options"]
                ],
            }
        )
    return {
        "source": "games, game_tags",
        "query": "findGames",
        "shown": SHOWN,
        "limit": RESULT_LIMIT,
        "encounters": encounters,
    }


def _card(row) -> dict:
    name, app_id, review, released, positive, negative, total = row
    if hasattr(released, "isoformat"):
        released_text = released.isoformat()
    elif released is None:
        released_text = ""
    else:
        released_text = str(released)[:10]
    return {
        "app_id": int(app_id),
        "title": (name or "").strip() or "Untitled",
        "review_score": review or "",
        "released": released_text,
        "positive": int(positive or 0),
        "negative": int(negative or 0),
        "total_reviews": int(total or 0),
    }


def run_find_games(conn, choices: dict, now: datetime | None = None) -> dict:
    """Run the accumulated findGames search and keep the first three rows."""
    if now is None:
        now = datetime.now(timezone.utc)
    selected = _selected(choices)
    by_id = {enc["id"]: opt for enc, opt in selected}

    start, today = _date_window(now, RECENCY_DAYS[by_id["recency"]["id"]])
    review = by_id["review-score"]["filter"]
    labels = list(_labels_or_better(review["reviewScore"]))
    min_reviews = int(by_id["min-reviews"]["filter"]["minReviews"])
    max_reviews = int(by_id["max-reviews"]["filter"]["maxReviews"])
    if min_reviews <= 0 or max_reviews >= 1000000 or max_reviews < min_reviews:
        raise ValueError("review bounds are outside the finder rules")
    include_tag = by_id["tag"]["filter"]["tags"][0]
    exclude_tag = by_id["exclude-tag"]["filter"]["excludeTags"][0]
    ai_key = by_id["ai"]["filter"]["aiDeclaration"]
    if ai_key not in AI_SQL:
        raise ValueError("unknown AI declaration")

    # CASE evaluates the jsonb cast only when release_date looks like JSON,
    # so a plain-text date cannot abort the statement. The kept values match
    # the cube wrapper: coming_soon null or the string false.
    sql = (
        """
        SELECT
          g.name,
          g.app_id,
          g.review_score_desc,
          g.release_date_actual,
          COALESCE(g.total_positive, 0),
          COALESCE(g.total_negative, 0),
          (COALESCE(g.total_positive, 0) + COALESCE(g.total_negative, 0)) AS total_reviews
        FROM games g
        WHERE g.type = 'game'
          AND g.name NOT ILIKE '%%playtest%%'
          AND CASE
                WHEN g.release_date IS NULL OR g.release_date !~ '^[\\[{]' THEN TRUE
                ELSE COALESCE(g.release_date::jsonb->>'coming_soon', 'false') = 'false'
              END
          AND NOT EXISTS (
            SELECT 1 FROM game_tags t
            WHERE t.app_id = g.app_id AND t.tag = ANY(%s)
          )
          AND NOT (
            COALESCE(g.content_descriptors, '') ILIKE '%%sexual assault%%'
            OR COALESCE(g.content_descriptors, '') ILIKE '%%non-consensual%%'
            OR COALESCE(g.content_descriptors, '') ILIKE '%%BDSM%%'
            OR COALESCE(g.content_descriptors, '') ILIKE '%%extreme violence%%'
            OR COALESCE(g.content_descriptors, '') ILIKE '%%rape%%'
          )
          AND g.release_date_actual BETWEEN %s AND %s
          AND g.review_score_desc = ANY(%s)
          AND (COALESCE(g.total_positive, 0) + COALESCE(g.total_negative, 0)) >= %s
          AND (COALESCE(g.total_positive, 0) + COALESCE(g.total_negative, 0)) <= %s
          AND """
        + AI_SQL[ai_key]
        + """
          AND EXISTS (
            SELECT 1 FROM game_tags t
            WHERE t.app_id = g.app_id AND t.tag = %s
          )
          AND NOT EXISTS (
            SELECT 1 FROM game_tags t
            WHERE t.app_id = g.app_id AND t.tag = %s
          )
        ORDER BY total_reviews DESC, g.app_id
        LIMIT """
        + str(RESULT_LIMIT)
    )
    params = (
        list(ADULT_TAGS),
        start,
        today,
        labels,
        min_reviews,
        max_reviews,
        include_tag,
        exclude_tag,
    )
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    cards = [_card(row) for row in rows]
    applied = [
        {
            "encounter": enc["id"],
            "dimension": enc["dimension"],
            "label": opt["label"],
            "filter": opt["filter"],
            "clause": clause_text(enc, opt, now),
        }
        for enc, opt in selected
    ]
    return {
        "source": "games, game_tags",
        "query": "findGames",
        "returned": len(cards),
        "shown": min(SHOWN, len(cards)),
        "always": list(ALWAYS),
        "applied": applied,
        "games": cards[:SHOWN],
    }


def assert_playable(conn) -> int:
    result = run_find_games(conn, WORST_CHOICES)
    if len(result["games"]) < SHOWN:
        raise RuntimeError(
            f"tightest avenue combination returned {len(result['games'])} games"
        )
    return result["returned"]


def discover(choices: dict) -> dict:
    import psycopg2

    conn = psycopg2.connect(connection_string(), connect_timeout=15)
    try:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '25s'")
        return run_find_games(conn, choices)
    finally:
        conn.close()


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/level":
            self._send_json(build_level())
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

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/api/discover":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > 20000:
            self._send_json({"error": "expected a small JSON body"}, 400)
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            choices = payload["choices"]
            result = discover(choices)
        except (ValueError, KeyError, TypeError) as exc:
            self._send_json({"error": _safe_error(exc)}, 400)
            return
        except Exception as exc:
            self._send_json({"error": _safe_error(exc)}, 500)
            return
        self._send_json(result)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s\n" % (fmt % args))


def serve() -> None:
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    level = build_level()
    print(f"Dig Dug is at http://127.0.0.1:{PORT}/")
    print("Query: findGames on games and game_tags")
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
        raise SystemExit(f"Could not connect to the games database: {_safe_error(exc)}") from None
    try:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '25s'")
        found = assert_playable(conn)
    except Exception as exc:
        raise SystemExit(f"Could not run the Find a Game query: {_safe_error(exc)}") from None
    finally:
        conn.close()
    print(f"Tightest combination returned {found} games")
    serve()


if __name__ == "__main__":
    main()
