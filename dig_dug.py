#!/usr/bin/env python3
"""Dig Dug level that builds one Find a Game search from avenue choices.

The player knocks away dirt and sand, then pauses at each avenue. Six avenues
offer the top tags. Recency is a calendar window on ``release_date_actual``,
then that window split into three equal stretches, unless the player picks
"doesn't matter". Review score uses the page's "or better" rank. Review count
is ``total_positive + total_negative``. After the last avenue the accumulated
``findGames`` query runs. Clicking the discover tile shows the first three rows.

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

# Page rank, best first. "At least" / "or better" is the prefix through the label.
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

# Increasing strictness among the labels this level offers. Positive is the
# least strict: "at least Positive" is the four-label prefix of the rank above.
SCORE_LADDER = (
    "Positive",
    "Mostly Positive",
    "Very Positive",
    "Overwhelmingly Positive",
)

# findGames adds these when includeAdultGames is false.
ADULT_TAGS = ("Sexual Content", "Hentai")
DESCRIPTOR_PATTERNS = (
    "sexual assault",
    "non-consensual",
    "BDSM",
    "extreme violence",
    "rape",
)

RESULT_LIMIT = 100
SHOWN = 3
TAG_ENCOUNTERS = 6
TAGS_PER_ENCOUNTER = 3

REVIEWS = "(COALESCE(g.total_positive, 0) + COALESCE(g.total_negative, 0))"

BASE_FROM = """
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
"""

HOST = "0.0.0.0"
PORT = 8765

ALWAYS = (
    "type = 'game'",
    "name NOT ILIKE '%playtest%'",
    "release_date.coming_soon IS NULL OR 'false'",
    "exclude tags Sexual Content and Hentai",
    "exclude content descriptors sexual assault, non-consensual, BDSM, extreme violence, rape",
    "ORDER BY total_positive + total_negative DESC",
    f"LIMIT {RESULT_LIMIT}",
)


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


def _today(now: datetime) -> date:
    return now.astimezone(timezone.utc).date()


def load_catalog(conn) -> dict:
    """Top tags by game_tags rows, and the earliest pre-2020 release."""
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = '60s'")
        cur.execute(
            """
            SELECT tag, COUNT(*) AS n
            FROM game_tags
            WHERE tag <> ALL(%s)
            GROUP BY tag
            ORDER BY n DESC, tag ASC
            LIMIT %s
            """,
            (list(ADULT_TAGS), TAG_ENCOUNTERS * TAGS_PER_ENCOUNTER),
        )
        tags = [{"tag": tag, "count": int(count)} for tag, count in cur.fetchall()]
        cur.execute(
            """
            SELECT MIN(release_date_actual)
            FROM games
            WHERE release_date_actual IS NOT NULL
              AND release_date_actual < DATE '2020-01-01'
            """
        )
        earliest = cur.fetchone()[0]
        cur.execute(
            """
            SELECT review_score_desc
            FROM games
            WHERE type = 'game'
              AND review_score_desc = ANY(%s)
            GROUP BY review_score_desc
            """,
            (list(SCORE_LADDER),),
        )
        present = {row[0] for row in cur.fetchall()}
    if len(tags) < TAG_ENCOUNTERS * TAGS_PER_ENCOUNTER:
        raise RuntimeError(f"needed 18 tags after adult exclusion, found {len(tags)}")
    missing = [label for label in SCORE_LADDER if label not in present]
    if missing:
        raise RuntimeError(f"review_score_desc values missing: {', '.join(missing)}")
    if earliest is None:
        raise RuntimeError("no release_date_actual before 2020")
    return {"tags": tags, "earliest": earliest}


def period_windows(now: datetime, earliest: date) -> dict[str, tuple[date, date, str]]:
    today = _today(now)
    year = today.year
    return {
        "this-year": (date(year, 1, 1), today, "This year"),
        "from-2020": (
            date(2020, 1, 1),
            date(year - 1, 12, 31),
            f"2020 through {year - 1}",
        ),
        "before-2020": (earliest, date(2019, 12, 31), "Before 2020"),
    }


def split_window(start: date, end: date) -> list[tuple[date, date]]:
    """Three contiguous inclusive ranges covering start through end.

    Day counts differ by at most one. The earlier ranges take the extra day.
    """
    total = (end - start).days + 1
    if total < 3:
        raise RuntimeError(f"date window {start}..{end} is shorter than 3 days")
    base, remainder = divmod(total, 3)
    ranges = []
    cursor = start
    for index in range(3):
        length = base + (1 if index < remainder else 0)
        range_end = end if index == 2 else cursor + timedelta(days=length - 1)
        ranges.append((cursor, range_end))
        cursor = range_end + timedelta(days=1)
    return ranges


def at_least_labels(label: str) -> list[str]:
    index = REVIEW_DESC_ORDER.index(label)
    return list(REVIEW_DESC_ORDER[: index + 1])


def _quote(value: str) -> str:
    return value.replace("'", "''")


def tag_clause(tag: str) -> str:
    return f"game_tags.tag = '{_quote(tag)}'"


def date_clause(start: date, end: date) -> str:
    return f"release_date_actual BETWEEN {start.isoformat()} AND {end.isoformat()}"


def score_clause(label: str) -> str:
    quoted = ", ".join(f"'{item}'" for item in at_least_labels(label))
    return f"review_score_desc IN ({quoted})"


def count_clause(band: str) -> str:
    if band == "over":
        return "(total_positive + total_negative) > 10000"
    if band == "mid":
        return (
            "(total_positive + total_negative) >= 1000 "
            "AND (total_positive + total_negative) <= 10000"
        )
    if band == "under":
        return "(total_positive + total_negative) < 1000"
    raise ValueError(f"unknown review band {band}")


def _date_option(option_id: str, start: date, end: date, label: str) -> dict:
    return {
        "id": option_id,
        "label": label,
        "detail": date_clause(start, end),
        "filter": {"minDate": start.isoformat(), "maxDate": end.isoformat()},
    }


def _score_option(option_id: str, label: str | None) -> dict:
    if label is None:
        return {
            "id": option_id,
            "label": "Doesn't matter",
            "detail": "no review_score_desc clause",
            "filter": {"reviewScore": "Any"},
        }
    return {
        "id": option_id,
        "label": label,
        "detail": score_clause(label),
        "filter": {"reviewScore": label, "reviewScoreOrBetter": True},
    }


def build_level(catalog: dict, now: datetime | None = None) -> dict:
    if now is None:
        now = datetime.now(timezone.utc)
    groups = [
        catalog["tags"][index * TAGS_PER_ENCOUNTER : (index + 1) * TAGS_PER_ENCOUNTER]
        for index in range(TAG_ENCOUNTERS)
    ]
    encounters = []
    for index, group in enumerate(groups):
        rank = index * TAGS_PER_ENCOUNTER
        encounters.append(
            {
                "id": f"tags-{index + 1}",
                "dimension": "tags",
                "prompt": f"Which tag should it include? ({index + 1} of {TAG_ENCOUNTERS})",
                "options": [
                    {
                        "id": item["tag"],
                        "label": item["tag"],
                        "detail": tag_clause(item["tag"]),
                        "filter": {"tags": [item["tag"]]},
                        "count": item["count"],
                    }
                    for item in group
                ],
                "ranks": [rank + 1, rank + 2, rank + 3],
            }
        )

    windows = period_windows(now, catalog["earliest"])
    coarse_options = [
        _date_option(key, start, end, label) for key, (start, end, label) in windows.items()
    ]
    coarse_options.append(
        {
            "id": "any",
            "label": "Doesn't matter",
            "detail": "no release_date_actual clause",
            "filter": {},
        }
    )
    parts_by_period = {
        key: [
            _date_option(f"part-{part_index}", start, end, f"{start.isoformat()} – {end.isoformat()}")
            for part_index, (start, end) in enumerate(split_window(window[0], window[1]))
        ]
        for key, window in windows.items()
    }
    encounters.append(
        {
            "id": "recency",
            "dimension": "releaseDate",
            "prompt": "How recent should the release be?",
            "options": coarse_options,
        }
    )
    encounters.append(
        {
            "id": "recency-fine",
            "dimension": "releaseDate",
            "prompt": "Which part of that period?",
            "skipWhen": {"recency": "any"},
            "options": parts_by_period["this-year"],
            "optionsByParent": parts_by_period,
        }
    )
    encounters.append(
        {
            "id": "review-score",
            "dimension": "reviewScore",
            "prompt": "Review score is at least?",
            "options": [
                _score_option("positive", "Positive"),
                _score_option("mostly-positive", "Mostly Positive"),
                _score_option("very-positive", "Very Positive"),
                _score_option("overwhelmingly-positive", "Overwhelmingly Positive"),
                _score_option("any", None),
            ],
        }
    )
    encounters.append(
        {
            "id": "review-count",
            "dimension": "totalReviews",
            "prompt": "How many reviews?",
            "options": [
                {
                    "id": "over-10000",
                    "label": "Greater than 10,000",
                    "detail": count_clause("over"),
                    "filter": {"minReviews": 10001},
                },
                {
                    "id": "mid-10000",
                    "label": "1,000–10,000",
                    "detail": count_clause("mid"),
                    "filter": {"minReviews": 1000, "maxReviews": 10000},
                },
                {
                    "id": "under-1000",
                    "label": "Under 1,000",
                    "detail": count_clause("under"),
                    "filter": {"maxReviews": 999},
                },
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


def _option(options: list[dict], option_id: str, encounter_id: str) -> dict:
    for option in options:
        if option["id"] == option_id:
            return option
    raise ValueError(f"unknown option {option_id!r} for {encounter_id}")


def resolve_choices(choices: dict, catalog: dict, now: datetime) -> dict:
    """Turn avenue option ids into the clauses the search will AND together."""
    if not isinstance(choices, dict):
        raise ValueError("choices must be an object")
    known = {f"tags-{index + 1}" for index in range(TAG_ENCOUNTERS)}
    known.update({"recency", "recency-fine", "review-score", "review-count"})
    unknown = set(choices) - known
    if unknown:
        raise ValueError(f"unknown encounter {sorted(unknown)[0]}")

    groups = [
        catalog["tags"][index * TAGS_PER_ENCOUNTER : (index + 1) * TAGS_PER_ENCOUNTER]
        for index in range(TAG_ENCOUNTERS)
    ]
    tags: list[str] = []
    picks = []
    for index, group in enumerate(groups):
        enc_id = f"tags-{index + 1}"
        if enc_id not in choices:
            raise ValueError(f"missing choice for {enc_id}")
        allowed = {item["tag"]: item for item in group}
        tag = choices[enc_id]
        if tag not in allowed:
            raise ValueError(f"unknown tag for {enc_id}")
        tags.append(tag)
        picks.append(
            {
                "encounter": enc_id,
                "dimension": "tags",
                "label": tag,
                "clause": tag_clause(tag),
                "filter": {"tags": [tag]},
            }
        )

    if "recency" not in choices:
        raise ValueError("missing choice for recency")
    recency = choices["recency"]
    windows = period_windows(now, catalog["earliest"])
    dates = None
    if recency == "any":
        if choices.get("recency-fine"):
            raise ValueError("no second recency cut when the period doesn't matter")
        picks.append(
            {
                "encounter": "recency",
                "dimension": "releaseDate",
                "label": "Doesn't matter",
                "clause": "no release_date_actual clause",
                "filter": {},
            }
        )
    elif recency in windows:
        start, end, label = windows[recency]
        if "recency-fine" not in choices:
            raise ValueError("missing choice for recency-fine")
        fine_id = choices["recency-fine"]
        parts = split_window(start, end)
        if fine_id not in {f"part-{index}" for index in range(3)}:
            raise ValueError("unknown second recency cut")
        part_index = int(fine_id.split("-")[1])
        dates = parts[part_index]
        picks.append(
            {
                "encounter": "recency",
                "dimension": "releaseDate",
                "label": label,
                "clause": date_clause(start, end),
                "filter": {"minDate": start.isoformat(), "maxDate": end.isoformat()},
                "replaced": True,
            }
        )
        picks.append(
            {
                "encounter": "recency-fine",
                "dimension": "releaseDate",
                "label": f"{dates[0].isoformat()} – {dates[1].isoformat()}",
                "clause": date_clause(*dates),
                "filter": {
                    "minDate": dates[0].isoformat(),
                    "maxDate": dates[1].isoformat(),
                },
            }
        )
    else:
        raise ValueError("unknown recency choice")

    score_ids = {
        "positive": "Positive",
        "mostly-positive": "Mostly Positive",
        "very-positive": "Very Positive",
        "overwhelmingly-positive": "Overwhelmingly Positive",
        "any": None,
    }
    if "review-score" not in choices:
        raise ValueError("missing choice for review-score")
    score_id = choices["review-score"]
    if score_id not in score_ids:
        raise ValueError("unknown review score")
    score_label = score_ids[score_id]
    labels = at_least_labels(score_label) if score_label else None
    if score_label is None:
        picks.append(
            {
                "encounter": "review-score",
                "dimension": "reviewScore",
                "label": "Doesn't matter",
                "clause": "no review_score_desc clause",
                "filter": {"reviewScore": "Any"},
            }
        )
    else:
        picks.append(
            {
                "encounter": "review-score",
                "dimension": "reviewScore",
                "label": score_label,
                "clause": score_clause(score_label),
                "filter": {"reviewScore": score_label, "reviewScoreOrBetter": True},
            }
        )

    bands = {"over-10000": "over", "mid-10000": "mid", "under-1000": "under"}
    band_labels = {
        "over": "Greater than 10,000",
        "mid": "1,000–10,000",
        "under": "Under 1,000",
    }
    if "review-count" not in choices:
        raise ValueError("missing choice for review-count")
    count_id = choices["review-count"]
    if count_id not in bands:
        raise ValueError("unknown review count")
    band = bands[count_id]
    picks.append(
        {
            "encounter": "review-count",
            "dimension": "totalReviews",
            "label": band_labels[band],
            "clause": count_clause(band),
            "filter": {
                "over": {"minReviews": 10001},
                "mid": {"minReviews": 1000, "maxReviews": 10000},
                "under": {"maxReviews": 999},
            }[band],
        }
    )
    return {"tags": tags, "dates": dates, "labels": labels, "band": band, "picks": picks}


def _where(tags: list[str], dates, labels, band: str | None) -> tuple[str, list]:
    sql = [BASE_FROM]
    params: list = [list(ADULT_TAGS)]
    for tag in tags:
        sql.append(
            "AND EXISTS (SELECT 1 FROM game_tags t WHERE t.app_id = g.app_id AND t.tag = %s)"
        )
        params.append(tag)
    if dates is not None:
        sql.append("AND g.release_date_actual BETWEEN %s AND %s")
        params.extend([dates[0], dates[1]])
    if labels:
        sql.append("AND g.review_score_desc = ANY(%s)")
        params.append(list(labels))
    if band == "over":
        sql.append(f"AND {REVIEWS} > 10000")
    elif band == "mid":
        sql.append(f"AND {REVIEWS} >= 1000 AND {REVIEWS} <= 10000")
    elif band == "under":
        sql.append(f"AND {REVIEWS} < 1000")
    elif band is not None:
        raise ValueError(f"unknown review band {band}")
    return "\n".join(sql), params


def _stages(resolved: dict) -> list[dict]:
    """Cumulative snapshots in play order. The fine date replaces the coarse one."""
    stages = []
    tags: list[str] = []
    dates = None
    labels = None
    band = None
    for pick in resolved["picks"]:
        if pick.get("replaced"):
            dates = (
                date.fromisoformat(pick["filter"]["minDate"]),
                date.fromisoformat(pick["filter"]["maxDate"]),
            )
            stages.append(
                {
                    "pick": pick,
                    "tags": list(tags),
                    "dates": dates,
                    "labels": list(labels) if labels else None,
                    "band": band,
                    "adds_clause": True,
                }
            )
            continue
        elif pick["dimension"] == "tags":
            tags.append(pick["label"])
        elif pick["dimension"] == "releaseDate" and pick["filter"]:
            dates = (
                date.fromisoformat(pick["filter"]["minDate"]),
                date.fromisoformat(pick["filter"]["maxDate"]),
            )
        elif pick["dimension"] == "reviewScore" and pick["filter"].get("reviewScore") not in (
            None,
            "Any",
        ):
            labels = at_least_labels(pick["filter"]["reviewScore"])
        elif pick["dimension"] == "totalReviews":
            if "minReviews" in pick["filter"] and pick["filter"]["minReviews"] >= 10001:
                band = "over"
            elif pick["filter"].get("minReviews") == 1000:
                band = "mid"
            else:
                band = "under"
        if pick["clause"].startswith("no "):
            stages.append(
                {
                    "pick": pick,
                    "tags": list(tags),
                    "dates": dates,
                    "labels": labels,
                    "band": band,
                    "adds_clause": False,
                }
            )
            continue
        stages.append(
            {
                "pick": pick,
                "tags": list(tags),
                "dates": dates,
                "labels": list(labels) if labels else None,
                "band": band,
                "adds_clause": True,
            }
        )
    return stages


def _count(conn, tags, dates, labels, band) -> int:
    where, params = _where(tags, dates, labels, band)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*)\n" + where, params)
        return int(cur.fetchone()[0])


def _shortfall_message(label: str, before: int | None, after: int) -> str:
    if before is None:
        return f"{label} emptied the list, leaving {after} games."
    return f"{label} emptied the list ({before:,} games down to {after:,})."


def diagnose(conn, resolved: dict, final_count: int) -> dict:
    """Name the pick that first took the result under three games."""
    stages = [stage for stage in _stages(resolved) if stage["adds_clause"]]
    if not stages:
        return {
            "encounter": "",
            "label": "The search",
            "before": None,
            "after": final_count,
            "clause": "",
            "message": _shortfall_message("The search", None, final_count),
        }
    after = final_count
    for index in range(len(stages) - 2, -1, -1):
        stage = stages[index]
        before = _count(conn, stage["tags"], stage["dates"], stage["labels"], stage["band"])
        if before >= SHOWN:
            pick = stages[index + 1]["pick"]
            return {
                "encounter": pick["encounter"],
                "label": pick["label"],
                "before": before,
                "after": after,
                "clause": pick["clause"],
                "message": _shortfall_message(pick["label"], before, after),
            }
        after = before
    pick = stages[0]["pick"]
    return {
        "encounter": pick["encounter"],
        "label": pick["label"],
        "before": None,
        "after": after,
        "clause": pick["clause"],
        "message": _shortfall_message(pick["label"], None, after),
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


def run_find_games(conn, choices: dict, catalog: dict, now: datetime | None = None) -> dict:
    if now is None:
        now = datetime.now(timezone.utc)
    resolved = resolve_choices(choices, catalog, now)
    where, params = _where(
        resolved["tags"], resolved["dates"], resolved["labels"], resolved["band"]
    )
    sql = (
        f"""
        SELECT
          g.name,
          g.app_id,
          g.review_score_desc,
          g.release_date_actual,
          COALESCE(g.total_positive, 0),
          COALESCE(g.total_negative, 0),
          {REVIEWS} AS total_reviews
        """
        + where
        + f"""
        ORDER BY total_reviews DESC, g.app_id
        LIMIT {RESULT_LIMIT}
        """
    )
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    cards = [_card(row) for row in rows]
    applied = [
        {
            "encounter": pick["encounter"],
            "dimension": pick["dimension"],
            "label": pick["label"],
            "clause": pick["clause"],
            "filter": pick["filter"],
        }
        for pick in resolved["picks"]
        if not pick.get("replaced") and not pick["clause"].startswith("no ")
    ]
    shortfall = None
    if len(cards) < SHOWN:
        shortfall = diagnose(conn, resolved, len(cards))
    return {
        "source": "games, game_tags",
        "query": "findGames",
        "returned": len(cards),
        "shown": min(SHOWN, len(cards)),
        "always": list(ALWAYS),
        "applied": applied,
        "picks": [
            {
                "encounter": pick["encounter"],
                "label": pick["label"],
                "clause": pick["clause"],
                "replaced": bool(pick.get("replaced")),
            }
            for pick in resolved["picks"]
        ],
        "shortfall": shortfall,
        "games": cards[:SHOWN],
    }


def discover(choices: dict, catalog: dict) -> dict:
    import psycopg2

    conn = psycopg2.connect(connection_string(), connect_timeout=15)
    try:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '40s'")
        return run_find_games(conn, choices, catalog)
    finally:
        conn.close()


class Handler(BaseHTTPRequestHandler):
    catalog = None

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
            self._send_json(build_level(self.catalog))
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
            result = discover(payload["choices"], self.catalog)
        except (ValueError, KeyError, TypeError) as exc:
            self._send_json({"error": _safe_error(exc)}, 400)
            return
        except Exception as exc:
            self._send_json({"error": _safe_error(exc)}, 500)
            return
        self._send_json(result)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s\n" % (fmt % args))


def serve(catalog: dict) -> None:
    Handler.catalog = catalog
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    level = build_level(catalog)
    print(f"Dig Dug is at http://127.0.0.1:{PORT}/")
    print("Query: findGames on games and game_tags")
    print("Top tags:")
    for index, item in enumerate(catalog["tags"], start=1):
        print(f"  {index:2}. {item['tag']} ({item['count']:,})")
    for enc in level["encounters"]:
        labels = ", ".join(opt["label"] for opt in enc["options"])
        print(f"  {enc['id']}: {labels}")
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
        catalog = load_catalog(conn)
    except Exception as exc:
        raise SystemExit(f"Could not read tags and release dates: {_safe_error(exc)}") from None
    finally:
        conn.close()
    serve(catalog)


if __name__ == "__main__":
    main()
