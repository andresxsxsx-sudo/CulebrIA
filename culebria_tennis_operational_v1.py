from __future__ import annotations

import json
import math
import os
import re
import time
import unicodedata
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path
from statistics import median

import pandas as pd
import requests
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
MODEL_DIR = DATA / "tennis_model_v1"
CACHE_DIR = DATA / "tennis_operational_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://api.the-odds-api.com/v4"
REGIONS = "eu"
MARKET = "h2h"
ODDS_FORMAT = "decimal"
DATE_FORMAT = "iso"

# Política operativa.
MIN_MINUTES_TO_START = 10
HORIZON_HOURS = 48
MAX_RATINGS_AGE_DAYS = 2

# Reliability Gate WTA aprobado por HOLDOUT 2025 + monitor 2026.
APPROVED_WTA_BANDS = [
    (0.70, 0.75),
    (0.75, 0.80),
]

# Criterios de precio/valor.
MIN_REFERENCE_BOOKS = 4
MIN_MODEL_EDGE_VS_CONSENSUS_PP = 1.50
MIN_MODEL_EDGE_VS_TARGET_PP = 1.50
MIN_RAW_EV_PCT = 0.01

# Perfil buscado por el usuario: dos selecciones conservadoras.
MIN_LEG_ODDS = 1.25
MAX_LEG_ODDS = 1.60
MIN_COMBINED_ODDS = 1.80

# Solo casas tradicionales. Exchanges quedan fuera de target y consenso.
EXCLUDED_BOOKMAKER_TOKENS = {
    "betfair",
    "matchbook",
    "smarkets",
}

# Fallback oficial únicamente cuando no podemos resolver la superficie
# desde el CSV local. Cincinnati 2026 = Hard.
KNOWN_SURFACES_BY_SPORT_KEY = {
    "tennis_wta_cincinnati_open": "Hard",
}

RATINGS_FILE = MODEL_DIR / "wta_ratings_current.json"
RANKINGS_FILE = MODEL_DIR / "wta_current_rankings.json"

CANDIDATES_FILE = DATA / "culebria_tennis_candidates_operational_v1.csv"
PARLAYS_FILE = DATA / "culebria_tennis_parlays_operational_v1.csv"
FINAL_FILE = DATA / "culebria_tennis_operational_v1.json"


def now_utc():
    return datetime.now(timezone.utc)


def normalize(value):
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def safe_float(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if math.isnan(result):
        return None

    return result


def parse_dt(value):
    try:
        dt = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
    except (TypeError, ValueError):
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def implied_probability(odds):
    odds = safe_float(odds)

    if odds is None or odds <= 1:
        return None

    return 1.0 / odds


def elo_probability(diff):
    return 1.0 / (
        1.0
        + 10.0 ** (
            -diff / 400.0
        )
    )


def rank_probability(rank_a, rank_b):
    if (
        rank_a is None
        or rank_b is None
        or rank_a <= 0
        or rank_b <= 0
    ):
        return None

    score = math.log(
        (rank_b + 1.0)
        / (rank_a + 1.0)
    )

    return 1.0 / (
        1.0
        + math.exp(
            -1.15 * score
        )
    )


def approved_band(probability):
    for low, high in APPROVED_WTA_BANDS:
        if low <= probability < high:
            return f"{low * 100:.0f}-{high * 100:.0f}%"

    return None


def bookmaker_allowed(bookmaker):
    title = normalize(
        bookmaker.get("title", "")
    )
    key = normalize(
        bookmaker.get("key", "")
    )

    combined = f"{title} {key}"

    return not any(
        token in combined
        for token in EXCLUDED_BOOKMAKER_TOKENS
    )


def event_is_prematch(event):
    start = parse_dt(
        event.get("commence_time")
    )

    if start is None:
        return False

    now = now_utc()

    return (
        start
        > now
        + timedelta(
            minutes=MIN_MINUTES_TO_START
        )
        and start
        <= now
        + timedelta(
            hours=HORIZON_HOURS
        )
    )


def cache_path(sport_key):
    safe = re.sub(
        r"[^a-zA-Z0-9_.-]+",
        "_",
        sport_key,
    )
    return (
        CACHE_DIR
        / f"{safe}__h2h.json"
    )


def cache_ttl(events):
    starts = [
        parse_dt(
            event.get(
                "commence_time"
            )
        )
        for event in events
    ]

    starts = [
        dt
        for dt in starts
        if dt is not None
    ]

    if not starts:
        return 900

    nearest = min(
        starts
    )

    minutes = (
        nearest
        - now_utc()
    ).total_seconds() / 60

    if minutes <= 30:
        return 120

    if minutes <= 120:
        return 300

    if minutes <= 360:
        return 900

    return 1800


def read_cache(sport_key):
    path = cache_path(
        sport_key
    )

    if not path.exists():
        return None

    try:
        payload = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (json.JSONDecodeError, OSError):
        return None

    events = payload.get(
        "events",
        []
    )

    ttl = cache_ttl(
        events
    )

    age = (
        time.time()
        - path.stat().st_mtime
    )

    if age > ttl:
        return None

    return {
        "events": events,
        "age": age,
        "ttl": ttl,
    }


def write_cache(sport_key, events):
    cache_path(
        sport_key
    ).write_text(
        json.dumps(
            {
                "saved_at_utc":
                    now_utc().isoformat(),
                "events":
                    events,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def api_get(url, params):
    response = requests.get(
        url,
        params=params,
        timeout=25,
    )
    response.raise_for_status()

    return {
        "payload":
            response.json(),
        "last":
            response.headers.get(
                "x-requests-last"
            ),
        "remaining":
            response.headers.get(
                "x-requests-remaining"
            ),
    }


def active_wta_sports(api_key):
    response = api_get(
        f"{BASE_URL}/sports/",
        {
            "apiKey":
                api_key,
        },
    )

    sports = []

    for item in response[
        "payload"
    ]:
        if item.get("active") is False:
            continue

        if item.get(
            "has_outrights"
        ) is True:
            continue

        key = str(
            item.get(
                "key",
                "",
            )
        )

        title = str(
            item.get(
                "title",
                key,
            )
        )

        group = normalize(
            item.get(
                "group",
                "",
            )
        )

        if group != "tennis":
            continue

        key_n = normalize(
            key
        )
        title_n = normalize(
            title
        )

        if (
            "wta" not in key_n
            and "wta" not in title_n
        ):
            continue

        sports.append(
            {
                "key":
                    key,
                "title":
                    title,
            }
        )

    sports.sort(
        key=lambda row:
            row["title"]
    )

    return (
        sports,
        response,
    )


def fetch_wta_odds(
    api_key,
    sport_key,
):
    cached = read_cache(
        sport_key
    )

    if cached is not None:
        return {
            "events":
                cached[
                    "events"
                ],
            "source":
                "cache",
            "age":
                cached[
                    "age"
                ],
            "ttl":
                cached[
                    "ttl"
                ],
            "cost":
                0,
            "remaining":
                None,
        }

    response = api_get(
        (
            f"{BASE_URL}/sports/"
            f"{sport_key}/odds/"
        ),
        {
            "apiKey":
                api_key,
            "regions":
                REGIONS,
            "markets":
                MARKET,
            "oddsFormat":
                ODDS_FORMAT,
            "dateFormat":
                DATE_FORMAT,
        },
    )

    write_cache(
        sport_key,
        response[
            "payload"
        ],
    )

    try:
        cost = int(
            response[
                "last"
            ]
            or 0
        )
    except (TypeError, ValueError):
        cost = 0

    return {
        "events":
            response[
                "payload"
            ],
        "source":
            "api",
        "age":
            0,
        "ttl":
            cache_ttl(
                response[
                    "payload"
                ]
            ),
        "cost":
            cost,
        "remaining":
            response[
                "remaining"
            ],
    }


def locate_wta_season_file():
    filename = (
        "2026-wta-season.csv"
    )

    candidates = [
        ROOT / filename,
        DATA / filename,
        MODEL_DIR / filename,
        Path.home()
        / "Downloads"
        / filename,
        Path.home()
        / "Descargas"
        / filename,
        Path.home()
        / "Desktop"
        / filename,
        Path.home()
        / "Escritorio"
        / filename,
    ]

    for path in candidates:
        if (
            path.exists()
            and path.is_file()
            and path.stat().st_size
            > 100
        ):
            return path

    return None


def parse_date_series(series):
    raw = series.copy()

    result = pd.Series(
        pd.NaT,
        index=series.index,
        dtype="datetime64[ns]",
    )

    numeric = pd.to_numeric(
        raw,
        errors="coerce",
    )

    yyyymmdd = (
        numeric.notna()
        & numeric.between(
            19000101,
            21001231,
        )
    )

    if yyyymmdd.any():
        result.loc[
            yyyymmdd
        ] = pd.to_datetime(
            numeric.loc[
                yyyymmdd
            ]
            .round()
            .astype("Int64")
            .astype(str),
            format="%Y%m%d",
            errors="coerce",
        )

    epoch = (
        numeric.notna()
        & ~yyyymmdd
    )

    if epoch.any():
        values = numeric.loc[
            epoch
        ].abs()

        units = {
            "s":
                values < 1e11,
            "ms":
                (
                    values >= 1e11
                )
                & (
                    values < 1e14
                ),
            "us":
                (
                    values >= 1e14
                )
                & (
                    values < 1e17
                ),
            "ns":
                values >= 1e17,
        }

        for unit, mask in (
            units.items()
        ):
            if not mask.any():
                continue

            idx = values.index[
                mask
            ]

            parsed = pd.to_datetime(
                numeric.loc[
                    idx
                ],
                unit=unit,
                origin="unix",
                errors="coerce",
                utc=True,
            ).dt.tz_convert(
                None
            )

            result.loc[
                idx
            ] = parsed

    remaining = (
        result.isna()
        & raw.astype(str)
        .str.strip()
        .ne("")
    )

    if remaining.any():
        try:
            parsed = pd.to_datetime(
                raw.loc[
                    remaining
                ].astype(str),
                format="mixed",
                errors="coerce",
                utc=True,
            ).dt.tz_convert(
                None
            )
        except (TypeError, ValueError):
            parsed = pd.to_datetime(
                raw.loc[
                    remaining
                ].astype(str),
                errors="coerce",
                utc=True,
            ).dt.tz_convert(
                None
            )

        result.loc[
            remaining
        ] = parsed

    return result


def normalize_surface(value):
    text = normalize(
        value
    )

    if "hard" in text:
        return "Hard"

    if "clay" in text:
        return "Clay"

    if "grass" in text:
        return "Grass"

    if "carpet" in text:
        return "Carpet"

    if "indoor" in text:
        return "Indoor"

    return "Unknown"


def canonical_tournament(value):
    text = normalize(value)

    generic = {
        "wta",
        "atp",
        "open",
        "singles",
        "women",
        "womens",
        "ladies",
        "tournament",
        "championship",
        "championships",
        "masters",
    }

    tokens = [
        token
        for token in text.split()
        if token not in generic
    ]

    return " ".join(tokens)


def build_surface_lookup():
    path = locate_wta_season_file()

    if path is None:
        return (
            {},
            {},
            None,
        )

    df = pd.read_csv(
        path,
        low_memory=False,
    )

    required = {
        "date_timestamp",
        "home_name",
        "away_name",
        "surface",
        "tournament",
    }

    if not required.issubset(
        set(
            df.columns
        )
    ):
        return (
            {},
            {},
            path,
        )

    work = df.copy()

    work[
        "_date"
    ] = parse_date_series(
        work[
            "date_timestamp"
        ]
    )

    work = work[
        work[
            "_date"
        ].notna()
    ].copy()

    pair_lookup = {}
    tournament_samples = {}

    for _, row in work.iterrows():
        home = normalize(
            row[
                "home_name"
            ]
        )

        away = normalize(
            row[
                "away_name"
            ]
        )

        surface = normalize_surface(
            row[
                "surface"
            ]
        )

        if surface == "Unknown":
            continue

        match_date = row[
            "_date"
        ]

        # 1) Lookup exacto por pareja de jugadoras.
        if (
            home
            and away
            and home != away
        ):
            pair_key = tuple(
                sorted(
                    [
                        home,
                        away,
                    ]
                )
            )

            pair_lookup.setdefault(
                pair_key,
                []
            ).append(
                {
                    "date":
                        match_date,
                    "surface":
                        surface,
                }
            )

        # 2) Lookup por torneo para partidos futuros que todavía
        # no aparecen como emparejamiento exacto en el CSV.
        tournament = canonical_tournament(
            row[
                "tournament"
            ]
        )

        if tournament:
            tournament_samples.setdefault(
                tournament,
                []
            ).append(
                surface
            )

    tournament_lookup = {}

    for tournament, samples in (
        tournament_samples.items()
    ):
        counts = {}

        for surface in samples:
            counts[
                surface
            ] = (
                counts.get(
                    surface,
                    0,
                )
                + 1
            )

        ranked = sorted(
            counts.items(),
            key=lambda item:
                item[1],
            reverse=True,
        )

        if not ranked:
            continue

        best_surface, best_count = ranked[0]
        total = sum(
            counts.values()
        )

        # Solo aceptamos un torneo si la superficie es prácticamente
        # unánime dentro del CSV.
        if (
            total > 0
            and best_count / total
            >= 0.95
        ):
            tournament_lookup[
                tournament
            ] = {
                "surface":
                    best_surface,
                "n":
                    total,
            }

    return (
        pair_lookup,
        tournament_lookup,
        path,
    )


def event_surface(
    event,
    pair_lookup,
    tournament_lookup,
    sport_title,
    sport_key,
):
    home = normalize(
        event.get(
            "home_team",
            "",
        )
    )

    away = normalize(
        event.get(
            "away_team",
            "",
        )
    )

    key = tuple(
        sorted(
            [
                home,
                away,
            ]
        )
    )

    rows = pair_lookup.get(
        key,
        [],
    )

    start = parse_dt(
        event.get(
            "commence_time"
        )
    )

    if start is None:
        return (
            None,
            "missing_start",
        )

    event_date = pd.Timestamp(
        start.date()
    )

    best = None
    best_delta = None

    for row in rows:
        match_date = pd.Timestamp(
            row[
                "date"
            ]
        ).normalize()

        delta = abs(
            (
                match_date
                - event_date
            ).days
        )

        if delta > 3:
            continue

        if (
            best is None
            or delta
            < best_delta
        ):
            best = row[
                "surface"
            ]
            best_delta = delta

    if best is not None:
        return (
            best,
            "exact_pair",
        )

    # Fallback 1: superficie consistente del torneo en TennisData.
    target = canonical_tournament(
        sport_title
    )

    if target:
        exact = tournament_lookup.get(
            target
        )

        if exact is not None:
            return (
                exact[
                    "surface"
                ],
                "tournament_csv_exact",
            )

        candidates = []

        for tournament, payload in (
            tournament_lookup.items()
        ):
            ratio = SequenceMatcher(
                None,
                target,
                tournament,
            ).ratio()

            target_tokens = set(
                target.split()
            )
            tournament_tokens = set(
                tournament.split()
            )

            overlap = (
                len(
                    target_tokens
                    & tournament_tokens
                )
                / max(
                    1,
                    len(
                        target_tokens
                        | tournament_tokens
                    ),
                )
            )

            score = max(
                ratio,
                overlap,
            )

            if score >= 0.72:
                candidates.append(
                    (
                        score,
                        tournament,
                        payload,
                    )
                )

        candidates.sort(
            key=lambda item:
                item[
                    0
                ],
            reverse=True,
        )

        if candidates:
            if (
                len(candidates) == 1
                or candidates[
                    0
                ][
                    0
                ]
                - candidates[
                    1
                ][
                    0
                ]
                >= 0.08
            ):
                return (
                    candidates[
                        0
                    ][
                        2
                    ][
                        "surface"
                    ],
                    (
                        "tournament_csv_fuzzy:"
                        + candidates[
                            0
                        ][
                            1
                        ]
                    ),
                )

    # Fallback 2: mapa oficial explícito para torneos verificados.
    known = KNOWN_SURFACES_BY_SPORT_KEY.get(
        str(
            sport_key
        )
    )

    if known is not None:
        return (
            known,
            "official_fallback",
        )

    return (
        None,
        "unmatched",
    )


def load_model():
    if not RATINGS_FILE.exists():
        raise FileNotFoundError(
            RATINGS_FILE
        )

    if not RANKINGS_FILE.exists():
        raise FileNotFoundError(
            RANKINGS_FILE
        )

    ratings = json.loads(
        RATINGS_FILE.read_text(
            encoding="utf-8"
        )
    )

    rankings = json.loads(
        RANKINGS_FILE.read_text(
            encoding="utf-8"
        )
    )

    live_update = ratings.get(
        "live_update",
        {}
    )

    through_text = live_update.get(
        "through"
    )

    through = None

    if through_text:
        try:
            through = datetime.fromisoformat(
                str(
                    through_text
                )
            ).date()
        except ValueError:
            through = None

    if through is None:
        raise RuntimeError(
            "wta_ratings_current.json no contiene "
            "una fecha 'through' válida."
        )

    today = now_utc().date()

    age_days = (
        today
        - through
    ).days

    if (
        age_days
        > MAX_RATINGS_AGE_DAYS
    ):
        raise RuntimeError(
            "Ratings WTA demasiado antiguos: "
            f"{through} ({age_days} días). "
            "Ejecuta primero "
            "update_culebria_tennis_current_ratings.py"
        )

    return (
        ratings,
        rankings,
        through,
        age_days,
    )


def build_player_index(
    ratings,
):
    index = {}

    for key, payload in (
        ratings.get(
            "players",
            {}
        ).items()
    ):
        name = normalize(
            payload.get(
                "name",
                "",
            )
        )

        if not name:
            continue

        matches = int(
            payload.get(
                "matches",
                0,
            )
            or 0
        )

        current = index.get(
            name
        )

        if (
            current is None
            or matches
            > current[
                "matches"
            ]
        ):
            index[
                name
            ] = {
                "key":
                    key,
                "payload":
                    payload,
                "matches":
                    matches,
            }

    return index


def resolve_player(
    raw_name,
    index,
):
    target = normalize(
        raw_name
    )

    exact = index.get(
        target
    )

    if exact is not None:
        return (
            exact,
            "exact",
        )

    # Fuzzy estricto: solo para diferencias pequeñas de formato.
    candidates = []

    for name, payload in (
        index.items()
    ):
        ratio = SequenceMatcher(
            None,
            target,
            name,
        ).ratio()

        if ratio >= 0.93:
            candidates.append(
                (
                    ratio,
                    name,
                    payload,
                )
            )

    candidates.sort(
        key=lambda item:
            item[0],
        reverse=True,
    )

    if not candidates:
        return (
            None,
            None,
        )

    if (
        len(candidates) > 1
        and candidates[
            0
        ][0]
        - candidates[
            1
        ][0]
        < 0.03
    ):
        return (
            None,
            "ambiguous",
        )

    return (
        candidates[
            0
        ][2],
        (
            f"fuzzy:"
            f"{candidates[0][1]}"
        ),
    )


def current_rank(
    raw_name,
    rankings,
):
    players = rankings.get(
        "players",
        {}
    )

    target = normalize(
        raw_name
    )

    payload = players.get(
        target
    )

    if payload is not None:
        rank = safe_float(
            payload.get(
                "rank"
            )
        )

        return rank

    best = None
    best_ratio = 0.0

    for name, row in (
        players.items()
    ):
        ratio = SequenceMatcher(
            None,
            target,
            name,
        ).ratio()

        if ratio > best_ratio:
            best_ratio = ratio
            best = row

    if (
        best is not None
        and best_ratio >= 0.95
    ):
        return safe_float(
            best.get(
                "rank"
            )
        )

    return None


def player_surface_rating(
    payload,
    surface,
):
    surfaces = payload.get(
        "surfaces",
        {}
    )

    value = safe_float(
        surfaces.get(
            surface
        )
    )

    if value is not None:
        return value

    return safe_float(
        payload.get(
            "general"
        )
    )


def model_probability(
    player_a,
    player_b,
    surface,
    rank_a,
    rank_b,
    params,
):
    a_general = safe_float(
        player_a.get(
            "general"
        )
    )

    b_general = safe_float(
        player_b.get(
            "general"
        )
    )

    a_surface = player_surface_rating(
        player_a,
        surface,
    )

    b_surface = player_surface_rating(
        player_b,
        surface,
    )

    if (
        a_general is None
        or b_general is None
        or a_surface is None
        or b_surface is None
    ):
        return None

    surface_weight = float(
        params[
            "surface_weight"
        ]
    )

    rank_weight = float(
        params[
            "rank_weight"
        ]
    )

    diff = (
        (
            1.0
            - surface_weight
        )
        * (
            a_general
            - b_general
        )
        + surface_weight
        * (
            a_surface
            - b_surface
        )
    )

    p_elo = elo_probability(
        diff
    )

    p_rank = rank_probability(
        rank_a,
        rank_b,
    )

    if p_rank is None:
        return None

    return (
        (
            1.0
            - rank_weight
        )
        * p_elo
        + rank_weight
        * p_rank
    )


def book_pair(bookmaker):
    market = next(
        (
            market
            for market in bookmaker.get(
                "markets",
                []
            )
            if market.get(
                "key"
            ) == "h2h"
        ),
        None,
    )

    if market is None:
        return None

    outcomes = []

    for outcome in market.get(
        "outcomes",
        []
    ):
        name = str(
            outcome.get(
                "name",
                "",
            )
        ).strip()

        odds = safe_float(
            outcome.get(
                "price"
            )
        )

        if (
            not name
            or odds is None
            or odds <= 1
        ):
            continue

        outcomes.append(
            {
                "name":
                    name,
                "odds":
                    odds,
            }
        )

    if len(outcomes) != 2:
        return None

    p1 = implied_probability(
        outcomes[
            0
        ][
            "odds"
        ]
    )
    p2 = implied_probability(
        outcomes[
            1
        ][
            "odds"
        ]
    )

    if (
        p1 is None
        or p2 is None
    ):
        return None

    total = p1 + p2

    if total <= 0:
        return None

    outcomes[
        0
    ][
        "novig"
    ] = p1 / total

    outcomes[
        1
    ][
        "novig"
    ] = p2 / total

    return outcomes


def outcome_for_name(
    pair,
    player_name,
):
    target = normalize(
        player_name
    )

    for outcome in pair:
        if normalize(
            outcome[
                "name"
            ]
        ) == target:
            return outcome

    return None


def candidate_rows_for_event(
    event,
    sport_title,
    surface,
    model_favorite,
    model_probability_value,
    band,
):
    eligible_books = []

    for bookmaker in event.get(
        "bookmakers",
        []
    ):
        if not bookmaker_allowed(
            bookmaker
        ):
            continue

        pair = book_pair(
            bookmaker
        )

        if pair is None:
            continue

        favorite_outcome = (
            outcome_for_name(
                pair,
                model_favorite,
            )
        )

        if favorite_outcome is None:
            continue

        eligible_books.append(
            {
                "bookmaker":
                    str(
                        bookmaker.get(
                            "title",
                            "?",
                        )
                    ),
                "bookmaker_key":
                    str(
                        bookmaker.get(
                            "key",
                            "",
                        )
                    ),
                "odds":
                    float(
                        favorite_outcome[
                            "odds"
                        ]
                    ),
                "target_novig":
                    float(
                        favorite_outcome[
                            "novig"
                        ]
                    ),
            }
        )

    if (
        len(
            eligible_books
        )
        < MIN_REFERENCE_BOOKS
        + 1
    ):
        return []

    candidates = []

    for target in eligible_books:
        refs = [
            row[
                "target_novig"
            ]
            for row in eligible_books
            if row[
                "bookmaker_key"
            ]
            != target[
                "bookmaker_key"
            ]
        ]

        if len(refs) < MIN_REFERENCE_BOOKS:
            continue

        consensus = median(
            refs
        )

        model_edge_consensus_pp = (
            model_probability_value
            - consensus
        ) * 100.0

        model_edge_target_pp = (
            model_probability_value
            - target[
                "target_novig"
            ]
        ) * 100.0

        raw_ev_pct = (
            model_probability_value
            * target[
                "odds"
            ]
            - 1.0
        ) * 100.0

        if not (
            MIN_LEG_ODDS
            <= target[
                "odds"
            ]
            <= MAX_LEG_ODDS
        ):
            continue

        if (
            model_edge_consensus_pp
            < MIN_MODEL_EDGE_VS_CONSENSUS_PP
        ):
            continue

        if (
            model_edge_target_pp
            < MIN_MODEL_EDGE_VS_TARGET_PP
        ):
            continue

        if raw_ev_pct <= MIN_RAW_EV_PCT:
            continue

        candidates.append(
            {
                "sport":
                    "WTA",
                "competition":
                    sport_title,
                "event_id":
                    str(
                        event.get(
                            "id",
                            "",
                        )
                    ),
                "commence_time":
                    str(
                        event.get(
                            "commence_time",
                            "",
                        )
                    ),
                "player1":
                    str(
                        event.get(
                            "home_team",
                            "",
                        )
                    ),
                "player2":
                    str(
                        event.get(
                            "away_team",
                            "",
                        )
                    ),
                "surface":
                    surface,
                "selection":
                    model_favorite,
                "market":
                    "MATCH_WINNER",
                "reliability_band":
                    band,
                "model_probability":
                    model_probability_value,
                "market_consensus_novig":
                    consensus,
                "target_novig_probability":
                    target[
                        "target_novig"
                    ],
                "model_edge_consensus_pp":
                    model_edge_consensus_pp,
                "model_edge_target_pp":
                    model_edge_target_pp,
                "raw_ev_pct":
                    raw_ev_pct,
                "reference_books":
                    len(
                        refs
                    ),
                "bookmaker":
                    target[
                        "bookmaker"
                    ],
                "bookmaker_key":
                    target[
                        "bookmaker_key"
                    ],
                "odds":
                    target[
                        "odds"
                    ],
            }
        )

    return candidates


def best_per_book_event(df):
    if df.empty:
        return df

    return (
        df.sort_values(
            [
                "bookmaker_key",
                "event_id",
                "model_probability",
                "model_edge_consensus_pp",
                "raw_ev_pct",
                "odds",
            ],
            ascending=[
                True,
                True,
                False,
                False,
                False,
                False,
            ],
        )
        .drop_duplicates(
            subset=[
                "bookmaker_key",
                "event_id",
            ],
            keep="first",
        )
        .reset_index(
            drop=True
        )
    )


def build_parlays(df):
    if (
        df.empty
        or len(df) < 2
    ):
        return []

    parlays = []

    for (
        bookmaker_key,
        group,
    ) in df.groupby(
        "bookmaker_key"
    ):
        rows = [
            row
            for _, row in (
                group.iterrows()
            )
        ]

        for first, second in combinations(
            rows,
            2,
        ):
            if str(
                first[
                    "event_id"
                ]
            ) == str(
                second[
                    "event_id"
                ]
            ):
                continue

            combined_odds = (
                float(
                    first[
                        "odds"
                    ]
                )
                * float(
                    second[
                        "odds"
                    ]
                )
            )

            if (
                combined_odds
                < MIN_COMBINED_ODDS
            ):
                continue

            combined_probability = (
                float(
                    first[
                        "model_probability"
                    ]
                )
                * float(
                    second[
                        "model_probability"
                    ]
                )
            )

            combined_ev_pct = (
                combined_probability
                * combined_odds
                - 1.0
            ) * 100.0

            if combined_ev_pct <= 0:
                continue

            parlays.append(
                {
                    "bookmaker":
                        str(
                            first[
                                "bookmaker"
                            ]
                        ),
                    "bookmaker_key":
                        bookmaker_key,
                    "combined_odds":
                        combined_odds,
                    "combined_probability":
                        combined_probability,
                    "combined_ev_pct":
                        combined_ev_pct,
                    "min_leg_probability":
                        min(
                            float(
                                first[
                                    "model_probability"
                                ]
                            ),
                            float(
                                second[
                                    "model_probability"
                                ]
                            ),
                        ),
                    "min_edge_consensus_pp":
                        min(
                            float(
                                first[
                                    "model_edge_consensus_pp"
                                ]
                            ),
                            float(
                                second[
                                    "model_edge_consensus_pp"
                                ]
                            ),
                        ),
                    "leg1":
                        first,
                    "leg2":
                        second,
                }
            )

    # Mismo par de eventos puede aparecer en varias casas:
    # conservamos la mejor combinación.
    best = {}

    for parlay in parlays:
        identity = tuple(
            sorted(
                [
                    str(
                        parlay[
                            "leg1"
                        ][
                            "event_id"
                        ]
                    ),
                    str(
                        parlay[
                            "leg2"
                        ][
                            "event_id"
                        ]
                    ),
                ]
            )
        )

        # Para un perfil conservador, primero priorizamos
        # la probabilidad estimada de acertar las dos selecciones.
        # El EV sirve después para escoger el mejor precio entre
        # combinaciones de riesgo similar.
        score = (
            parlay[
                "combined_probability"
            ],
            parlay[
                "min_leg_probability"
            ],
            parlay[
                "combined_ev_pct"
            ],
            parlay[
                "min_edge_consensus_pp"
            ],
            parlay[
                "combined_odds"
            ],
        )

        current = best.get(
            identity
        )

        if (
            current is None
            or score
            > current[
                "_score"
            ]
        ):
            parlay[
                "_score"
            ] = score
            best[
                identity
            ] = parlay

    result = list(
        best.values()
    )

    for parlay in result:
        parlay.pop(
            "_score",
            None,
        )

    result.sort(
        key=lambda row: (
            row[
                "combined_probability"
            ],
            row[
                "min_leg_probability"
            ],
            row[
                "combined_ev_pct"
            ],
            row[
                "min_edge_consensus_pp"
            ],
            row[
                "combined_odds"
            ],
        ),
        reverse=True,
    )

    return result


def serialize_leg(row):
    return {
        "event_id":
            str(
                row[
                    "event_id"
                ]
            ),
        "competition":
            str(
                row[
                    "competition"
                ]
            ),
        "players":
            (
                f"{row['player1']} "
                f"vs "
                f"{row['player2']}"
            ),
        "surface":
            str(
                row[
                    "surface"
                ]
            ),
        "market":
            str(
                row[
                    "market"
                ]
            ),
        "selection":
            str(
                row[
                    "selection"
                ]
            ),
        "reliability_band":
            str(
                row[
                    "reliability_band"
                ]
            ),
        "model_probability_pct":
            round(
                float(
                    row[
                        "model_probability"
                    ]
                )
                * 100,
                2,
            ),
        "market_consensus_novig_pct":
            round(
                float(
                    row[
                        "market_consensus_novig"
                    ]
                )
                * 100,
                2,
            ),
        "edge_vs_consensus_pp":
            round(
                float(
                    row[
                        "model_edge_consensus_pp"
                    ]
                ),
                2,
            ),
        "edge_vs_target_pp":
            round(
                float(
                    row[
                        "model_edge_target_pp"
                    ]
                ),
                2,
            ),
        "raw_ev_pct":
            round(
                float(
                    row[
                        "raw_ev_pct"
                    ]
                ),
                2,
            ),
        "odds":
            round(
                float(
                    row[
                        "odds"
                    ]
                ),
                3,
            ),
        "commence_time":
            str(
                row[
                    "commence_time"
                ]
            ),
    }


def parlays_dataframe(parlays):
    rows = []

    for rank, parlay in enumerate(
        parlays,
        start=1,
    ):
        row = {
            "rank":
                rank,
            "bookmaker":
                parlay[
                    "bookmaker"
                ],
            "combined_odds":
                round(
                    parlay[
                        "combined_odds"
                    ],
                    4,
                ),
            "combined_probability_pct":
                round(
                    parlay[
                        "combined_probability"
                    ]
                    * 100,
                    2,
                ),
            "combined_ev_pct":
                round(
                    parlay[
                        "combined_ev_pct"
                    ],
                    2,
                ),
        }

        for number, key in (
            (
                1,
                "leg1",
            ),
            (
                2,
                "leg2",
            ),
        ):
            leg = serialize_leg(
                parlay[
                    key
                ]
            )

            for field, value in (
                leg.items()
            ):
                row[
                    f"leg{number}_{field}"
                ] = value

        rows.append(
            row
        )

    return pd.DataFrame(
        rows
    )


def main():
    print("=" * 94)
    print(
        "🐍 CULEBRIA TENNIS OPERATIONAL V1 — WTA"
    )
    print("=" * 94)
    print()
    print(
        "Fútbol NO se modifica."
    )
    print(
        "ATP permanece MONITOR ONLY."
    )
    print(
        "WTA operativa solo en bandas Reliability "
        "70-75% y 75-80%."
    )
    print(
        "Mercado: ganador del partido (h2h)."
    )
    print(
        "Exactamente 2 eventos distintos, misma casa, "
        "cuota combinada >= 1.80."
    )
    print(
        f"Cuota por selección: "
        f"{MIN_LEG_ODDS:.2f}–{MAX_LEG_ODDS:.2f}"
    )
    print(
        f"Edge modelo vs consenso mínimo: "
        f"{MIN_MODEL_EDGE_VS_CONSENSUS_PP:.2f} pp"
    )
    print(
        f"Casas referencia mínimas: "
        f"{MIN_REFERENCE_BOOKS}"
    )
    print(
        "Betting exchanges excluidos."
    )
    print(
        "Ranking conservador: primero mayor probabilidad combinada; "
        "después EV/edge."
    )
    print()

    load_dotenv(
        ROOT / ".env"
    )

    api_key = os.getenv(
        "THE_ODDS_API_KEY"
    )

    if not api_key:
        print(
            "❌ THE_ODDS_API_KEY no encontrada en .env"
        )
        return

    try:
        (
            ratings,
            rankings,
            ratings_through,
            ratings_age_days,
        ) = load_model()
    except Exception as exc:
        print(
            f"❌ Ratings WTA no utilizables: {exc}"
        )
        return

    print(
        f"Ratings WTA hasta: "
        f"{ratings_through} "
        f"(edad {ratings_age_days} días)"
    )

    (
        pair_surface_lookup,
        tournament_surface_lookup,
        season_file,
    ) = build_surface_lookup()

    if season_file is None:
        print(
            "❌ No encontré 2026-wta-season.csv. "
            "Se necesita para identificar la superficie."
        )
        return

    print(
        f"Fuente de superficies: {season_file}"
    )

    player_index = build_player_index(
        ratings
    )

    params = ratings[
        "params"
    ]

    try:
        (
            sports,
            sports_response,
        ) = active_wta_sports(
            api_key
        )
    except requests.RequestException as exc:
        print(
            f"❌ Error consultando /sports: {exc}"
        )
        return

    print()
    print(
        f"Competiciones WTA activas: {len(sports)}"
    )

    if not sports:
        print(
            "⛔ NO BET — no hay competiciones WTA activas."
        )
        return

    usage = {
        # /sports es una llamada de red, pero oficialmente cuesta 0 créditos.
        "api_calls":
            1,
        "api_cost":
            0,
        "cache_hits":
            0,
        "remaining":
            sports_response.get(
                "remaining"
            ),
    }

    diagnostics = {
        "events_seen":
            0,
        "events_prematch":
            0,
        "surface_unmatched":
            0,
        "surface_exact_pair":
            0,
        "surface_tournament_csv":
            0,
        "surface_official_fallback":
            0,
        "player_unmatched":
            0,
        "rank_missing":
            0,
        "low_experience":
            0,
        "outside_reliability":
            0,
        "events_modeled":
            0,
    }

    candidates = []

    for index, sport in enumerate(
        sports,
        start=1,
    ):
        try:
            result = fetch_wta_odds(
                api_key,
                sport[
                    "key"
                ],
            )
        except requests.RequestException as exc:
            response = getattr(
                exc,
                "response",
                None,
            )

            if (
                response is not None
                and response.status_code == 422
            ):
                print(
                    f"[{index}/{len(sports)}] "
                    f"{sport['title']} — ⚠️ no compatible"
                )
                continue

            raise

        if result[
            "source"
        ] == "cache":
            usage[
                "cache_hits"
            ] += 1

            source_text = (
                f"💾 caché "
                f"{result['age'] / 60:.1f} min"
            )
        else:
            usage[
                "api_calls"
            ] += 1

            usage[
                "api_cost"
            ] += int(
                result[
                    "cost"
                ]
                or 0
            )

            if result[
                "remaining"
            ] is not None:
                usage[
                    "remaining"
                ] = result[
                    "remaining"
                ]

            source_text = "🌐 API"

        print(
            f"[{index}/{len(sports)}] "
            f"{sport['title']} — "
            f"{source_text}"
        )

        for event in result[
            "events"
        ]:
            diagnostics[
                "events_seen"
            ] += 1

            if not event_is_prematch(
                event
            ):
                continue

            diagnostics[
                "events_prematch"
            ] += 1

            (
                surface,
                surface_source,
            ) = event_surface(
                event,
                pair_surface_lookup,
                tournament_surface_lookup,
                sport[
                    "title"
                ],
                sport[
                    "key"
                ],
            )

            if surface is None:
                diagnostics[
                    "surface_unmatched"
                ] += 1
                continue

            if (
                surface_source
                == "exact_pair"
            ):
                diagnostics[
                    "surface_exact_pair"
                ] += 1
            elif surface_source.startswith(
                "tournament_csv"
            ):
                diagnostics[
                    "surface_tournament_csv"
                ] += 1
            elif (
                surface_source
                == "official_fallback"
            ):
                diagnostics[
                    "surface_official_fallback"
                ] += 1

            player1_name = str(
                event.get(
                    "home_team",
                    "",
                )
            )

            player2_name = str(
                event.get(
                    "away_team",
                    "",
                )
            )

            (
                player1_entry,
                _,
            ) = resolve_player(
                player1_name,
                player_index,
            )

            (
                player2_entry,
                _,
            ) = resolve_player(
                player2_name,
                player_index,
            )

            if (
                player1_entry is None
                or player2_entry is None
            ):
                diagnostics[
                    "player_unmatched"
                ] += 1
                continue

            player1 = player1_entry[
                "payload"
            ]

            player2 = player2_entry[
                "payload"
            ]

            if (
                int(
                    player1.get(
                        "matches",
                        0,
                    )
                    or 0
                )
                < 30
                or int(
                    player2.get(
                        "matches",
                        0,
                    )
                    or 0
                )
                < 30
            ):
                diagnostics[
                    "low_experience"
                ] += 1
                continue

            rank1 = current_rank(
                player1_name,
                rankings,
            )

            rank2 = current_rank(
                player2_name,
                rankings,
            )

            if (
                rank1 is None
                or rank2 is None
            ):
                diagnostics[
                    "rank_missing"
                ] += 1
                continue

            p1 = model_probability(
                player1,
                player2,
                surface,
                rank1,
                rank2,
                params,
            )

            if p1 is None:
                continue

            if p1 >= 0.5:
                favorite = player1_name
                favorite_probability = p1
            else:
                favorite = player2_name
                favorite_probability = (
                    1.0
                    - p1
                )

            band = approved_band(
                favorite_probability
            )

            if band is None:
                diagnostics[
                    "outside_reliability"
                ] += 1
                continue

            diagnostics[
                "events_modeled"
            ] += 1

            candidates.extend(
                candidate_rows_for_event(
                    event,
                    sport[
                        "title"
                    ],
                    surface,
                    favorite,
                    favorite_probability,
                    band,
                )
            )

    candidate_df = best_per_book_event(
        pd.DataFrame(
            candidates
        )
    )

    parlays = build_parlays(
        candidate_df
    )

    if not candidate_df.empty:
        candidate_df.to_csv(
            CANDIDATES_FILE,
            index=False,
            encoding="utf-8-sig",
        )

    if parlays:
        parlays_dataframe(
            parlays
        ).to_csv(
            PARLAYS_FILE,
            index=False,
            encoding="utf-8-sig",
        )

    print()
    print("=" * 94)
    print("RESULTADO WTA")
    print("=" * 94)

    if not parlays:
        print()
        print("⛔ NO BET")
        print(
            "No existen 2 eventos distintos que cumplan "
            "Reliability + precio + edge + EV + misma casa."
        )
    else:
        print(
            f"Parlays válidos: {len(parlays)}"
        )

        for rank, parlay in enumerate(
            parlays[
                :5
            ],
            start=1,
        ):
            print()
            print("-" * 94)
            print(
                f"PARLAY #{rank} — "
                f"{parlay['bookmaker']}"
            )

            for number, leg_key in (
                (
                    1,
                    "leg1",
                ),
                (
                    2,
                    "leg2",
                ),
            ):
                leg = parlay[
                    leg_key
                ]

                print()
                print(
                    f"{number}. "
                    f"{leg['player1']} "
                    f"vs "
                    f"{leg['player2']}"
                )
                print(
                    f"   Apostar: "
                    f"{leg['selection']} gana"
                )
                print(
                    f"   Superficie: "
                    f"{leg['surface']}"
                )
                print(
                    f"   Reliability: "
                    f"{leg['reliability_band']}"
                )
                print(
                    f"   Prob. modelo: "
                    f"{leg['model_probability'] * 100:.2f}%"
                )
                print(
                    f"   Consenso mercado sin vig: "
                    f"{leg['market_consensus_novig'] * 100:.2f}%"
                )
                print(
                    f"   Edge vs consenso: "
                    f"{leg['model_edge_consensus_pp']:+.2f} pp"
                )
                print(
                    f"   Cuota: "
                    f"{leg['odds']:.3f}"
                )
                print(
                    f"   EV individual: "
                    f"{leg['raw_ev_pct']:+.2f}%"
                )

            print()
            print(
                f"CUOTA COMBINADA: "
                f"{parlay['combined_odds']:.3f}"
            )
            print(
                f"Prob. combinada estimada: "
                f"{parlay['combined_probability'] * 100:.2f}%"
            )
            print(
                f"EV combinado estimado: "
                f"{parlay['combined_ev_pct']:+.2f}%"
            )

    final = {
        "generated_at_utc":
            now_utc().isoformat(),
        "model":
            "CulebrIA Tennis Operational V1",
        "status":
            (
                "PARLAY"
                if parlays
                else "NO_BET"
            ),
        "ratings_through":
            str(
                ratings_through
            ),
        "policy": {
            "tour":
                "WTA",
            "market":
                "MATCH_WINNER",
            "approved_reliability_bands":
                [
                    "70-75%",
                    "75-80%",
                ],
            "events_per_parlay":
                2,
            "same_bookmaker":
                True,
            "min_leg_odds":
                MIN_LEG_ODDS,
            "max_leg_odds":
                MAX_LEG_ODDS,
            "min_combined_odds":
                MIN_COMBINED_ODDS,
            "min_reference_books":
                MIN_REFERENCE_BOOKS,
            "min_model_edge_vs_consensus_pp":
                MIN_MODEL_EDGE_VS_CONSENSUS_PP,
            "min_model_edge_vs_target_pp":
                MIN_MODEL_EDGE_VS_TARGET_PP,
            "exchanges_excluded":
                sorted(
                    EXCLUDED_BOOKMAKER_TOKENS
                ),
        },
        "diagnostics":
            diagnostics,
        "candidates":
            len(
                candidate_df
            ),
        "valid_parlays":
            len(
                parlays
            ),
        "best_parlay":
            (
                {
                    "bookmaker":
                        parlays[
                            0
                        ][
                            "bookmaker"
                        ],
                    "combined_odds":
                        round(
                            parlays[
                                0
                            ][
                                "combined_odds"
                            ],
                            4,
                        ),
                    "combined_probability_pct":
                        round(
                            parlays[
                                0
                            ][
                                "combined_probability"
                            ]
                            * 100,
                            2,
                        ),
                    "combined_ev_pct":
                        round(
                            parlays[
                                0
                            ][
                                "combined_ev_pct"
                            ],
                            2,
                        ),
                    "legs": [
                        serialize_leg(
                            parlays[
                                0
                            ][
                                "leg1"
                            ]
                        ),
                        serialize_leg(
                            parlays[
                                0
                            ][
                                "leg2"
                            ]
                        ),
                    ],
                }
                if parlays
                else None
            ),
        "usage": usage,
    }

    FINAL_FILE.write_text(
        json.dumps(
            final,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 94)
    print("RESUMEN")
    print("=" * 94)
    print(
        f"Eventos vistos: "
        f"{diagnostics['events_seen']}"
    )
    print(
        f"Eventos prematch <=48h: "
        f"{diagnostics['events_prematch']}"
    )
    print(
        f"Sin superficie emparejada: "
        f"{diagnostics['surface_unmatched']}"
    )
    print(
        f"Superficie por pareja exacta: "
        f"{diagnostics['surface_exact_pair']}"
    )
    print(
        f"Superficie por torneo CSV: "
        f"{diagnostics['surface_tournament_csv']}"
    )
    print(
        f"Superficie por fallback oficial: "
        f"{diagnostics['surface_official_fallback']}"
    )
    print(
        f"Jugador no emparejado: "
        f"{diagnostics['player_unmatched']}"
    )
    print(
        f"Ranking faltante: "
        f"{diagnostics['rank_missing']}"
    )
    print(
        f"Experiencia insuficiente: "
        f"{diagnostics['low_experience']}"
    )
    print(
        f"Fuera de bandas 70-80%: "
        f"{diagnostics['outside_reliability']}"
    )
    print(
        f"Eventos dentro de Reliability: "
        f"{diagnostics['events_modeled']}"
    )
    print(
        f"Candidatos por casa: "
        f"{len(candidate_df)}"
    )
    print(
        f"Parlays válidos: "
        f"{len(parlays)}"
    )
    print(
        f"Consultas API nuevas: "
        f"{usage['api_calls']}"
    )
    print(
        f"Coste API informado: "
        f"{usage['api_cost']}"
    )
    print(
        f"Usos de caché: "
        f"{usage['cache_hits']}"
    )

    if usage[
        "remaining"
    ] is not None:
        print(
            f"Créditos restantes: "
            f"{usage['remaining']}"
        )

    print()
    print(
        f"Decisión: {FINAL_FILE}"
    )
    print()
    print(
        "⚠️ El modelo ha pasado calibración histórica, "
        "pero eso no garantiza resultados futuros. "
        "NO BET sigue siendo una decisión válida."
    )


if __name__ == "__main__":
    main()
