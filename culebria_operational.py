from __future__ import annotations

import hashlib
import json
import math
import os
import time
import unicodedata
from datetime import datetime, timezone
from itertools import combinations
from statistics import median
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv


# ============================================================
# CULEBRIA - MODO USO BETA
# ============================================================
#
# Objetivo:
# - Usar únicamente señales que ya superaron el Reliability Gate.
# - Mercados operativos: 1X, X2 y AWAY_SCORES.
# - Verificar valor contra probabilidades de mercado SIN VIG.
# - Recomendar como máximo UNA jugada:
#       * Parlay de EXACTAMENTE 2 eventos distintos, misma casa,
#         con cuota combinada >= 1.80.
# - Nunca propone apuestas individuales.
# - Si no cumple todo: NO BET.
#
# IMPORTANTE:
# Este modo NO garantiza ganancias. Es una capa operativa beta.
# ============================================================


ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"

INPUT_FILE = DATA_DIR / "prematch_odds_candidates.csv"
OUTPUT_FILE = DATA_DIR / "culebria_operational_candidates.csv"
FINAL_FILE = DATA_DIR / "culebria_operational_final.json"

PROSPECTIVE_DIR = DATA_DIR / "prospective"
PROSPECTIVE_DIR.mkdir(parents=True, exist_ok=True)

PARLAY_LEDGER_FILE = (
    PROSPECTIVE_DIR
    / "operational_parlay_ledger.csv"
)

CACHE_DIR = DATA_DIR / "operational_odds"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://api.the-odds-api.com/v4"

REGIONS = "eu"
ODDS_FORMAT = "decimal"
DATE_FORMAT = "iso"

MIN_MINUTES_TO_KICKOFF = 10
MIN_COMBINED_ODDS = 1.80
MIN_SINGLE_ODDS = 1.80

# Buffer operativo frente a diferencias minúsculas/model noise.
# No es un umbral científicamente validado: es conservador y editable.
MIN_NOVIG_EDGE_PP = 1.00

# Evita gastar créditos en demasiadas señales en una sola ejecución.
MAX_SIGNALS_TO_PRICE = 12

# Caché inteligente:
# - lejos del inicio conserva las cuotas más tiempo;
# - cerca del inicio reduce automáticamente la vigencia;
# - respuestas sin el mercado pedido también se guardan brevemente.
# Esto reduce consultas repetidas sin congelar cuotas cerca del kickoff.
CACHE_SECONDS_FALLBACK = 600

ALLOWED_MARKETS = {
    "1X",
    "X2",
    "AWAY_SCORES",
}

GRADE_PRIORITY = {
    "A": 0,
    "B": 1,
    "C": 2,
}


# ============================================================
# UTILIDADES
# ============================================================

def utc_now():
    return datetime.now(timezone.utc)


def normalize_text(value):
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )
    for old in ("-", ".", ",", "'", "/", "_"):
        text = text.replace(old, " ")
    return " ".join(text.split())


def name_matches(candidate, target):
    a = normalize_text(candidate)
    b = normalize_text(target)

    if not a or not b:
        return False

    if a == b:
        return True

    a_tokens = set(a.split())
    b_tokens = set(b.split())

    if a_tokens.issubset(b_tokens) or b_tokens.issubset(a_tokens):
        return True

    return False


def parse_datetime(value):
    if value is None or pd.isna(value) or str(value).strip() == "":
        return None

    try:
        dt = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def implied_probability(decimal_odds):
    decimal_odds = float(decimal_odds)
    if decimal_odds <= 1.0:
        return None
    return 1.0 / decimal_odds


def safe_float(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if math.isnan(result):
        return None

    return result


def cache_path(event_id, markets):
    safe_markets = markets.replace(",", "__")
    return CACHE_DIR / f"{event_id}__{safe_markets}.json"


def returned_market_keys(payload):
    keys = set()

    for bookmaker in payload.get(
        "bookmakers",
        [],
    ):
        for market in bookmaker.get(
            "markets",
            [],
        ):
            key = str(
                market.get(
                    "key",
                    "",
                )
            ).strip()

            if key:
                keys.add(key)

    return keys


def requested_market_keys(markets):
    return {
        item.strip()
        for item in str(markets).split(",")
        if item.strip()
    }


def estimated_credit_cost(
    payload,
    markets,
):
    requested = requested_market_keys(
        markets
    )

    returned = returned_market_keys(
        payload
    )

    unique_returned = len(
        requested
        & returned
    )

    region_count = len(
        [
            item
            for item
            in str(REGIONS).split(",")
            if item.strip()
        ]
    )

    return (
        unique_returned
        * max(
            region_count,
            1,
        )
    )


def intelligent_cache_ttl_seconds(
    payload,
    markets,
):
    # TTL operativo según cercanía al kickoff.
    # Si el mercado solicitado no apareció, conservamos esa
    # respuesta durante menos tiempo para permitir que abra más tarde.

    requested = requested_market_keys(
        markets
    )

    returned = returned_market_keys(
        payload
    )

    has_requested_market = bool(
        requested
        & returned
    )

    commence = parse_datetime(
        payload.get(
            "commence_time"
        )
    )

    if commence is None:
        return CACHE_SECONDS_FALLBACK

    minutes_to_start = (
        commence
        - utc_now()
    ).total_seconds() / 60

    if minutes_to_start <= 0:
        return 60

    if not has_requested_market:

        if minutes_to_start > 360:
            return 3600

        if minutes_to_start > 120:
            return 1800

        if minutes_to_start > 45:
            return 900

        return 300

    if minutes_to_start > 720:
        return 3600

    if minutes_to_start > 360:
        return 2700

    if minutes_to_start > 120:
        return 1800

    if minutes_to_start > 45:
        return 900

    if minutes_to_start > 20:
        return 300

    return 120


def load_recent_cache(event_id, markets):
    path = cache_path(
        event_id,
        markets,
    )

    if not path.exists():
        return None

    try:
        payload = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (
        json.JSONDecodeError,
        OSError,
    ):
        return None

    age = (
        time.time()
        - path.stat().st_mtime
    )

    ttl = intelligent_cache_ttl_seconds(
        payload,
        markets,
    )

    if age > ttl:
        return None

    return {
        "payload":
            payload,
        "age_seconds":
            age,
        "ttl_seconds":
            ttl,
        "estimated_saved_credits":
            estimated_credit_cost(
                payload,
                markets,
            ),
    }


def save_cache(event_id, markets, payload):
    path = cache_path(event_id, markets)
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


# ============================================================
# THE ODDS API
# ============================================================

def fetch_event_odds(
    *,
    api_key,
    sport_key,
    event_id,
    markets,
):
    cached = load_recent_cache(
        event_id,
        markets,
    )

    if cached is not None:
        return {
            "payload":
                cached["payload"],
            "source":
                "cache",
            "credits_last":
                0,
            "credits_used":
                None,
            "credits_remaining":
                None,
            "cache_age_seconds":
                cached[
                    "age_seconds"
                ],
            "cache_ttl_seconds":
                cached[
                    "ttl_seconds"
                ],
            "estimated_saved_credits":
                cached[
                    "estimated_saved_credits"
                ],
        }

    url = (
        f"{BASE_URL}/sports/{sport_key}"
        f"/events/{event_id}/odds"
    )

    params = {
        "apiKey": api_key,
        "regions": REGIONS,
        "markets": markets,
        "oddsFormat": ODDS_FORMAT,
        "dateFormat": DATE_FORMAT,
    }

    response = requests.get(
        url,
        params=params,
        timeout=20,
    )

    response.raise_for_status()

    payload = response.json()
    save_cache(
        event_id,
        markets,
        payload,
    )

    return {
        "payload": payload,
        "source": "api",
        "credits_last": response.headers.get("x-requests-last"),
        "credits_used": response.headers.get("x-requests-used"),
        "credits_remaining": response.headers.get("x-requests-remaining"),
    }


# ============================================================
# MERCADO 1X
# ============================================================

def extract_double_chance_1x(market, home_team):
    for outcome in market.get("outcomes", []):
        name = normalize_text(
            outcome.get("name", "")
        )

        price = safe_float(
            outcome.get("price")
        )

        if price is None:
            continue

        # Algunos proveedores lo expresan como 1X.
        if name in {"1x", "home draw", "draw home"}:
            return price

        # Otros incluyen el nombre del equipo + Draw.
        if (
            "draw" in name
            and name_matches(name.replace("draw", ""), home_team)
        ):
            return price

        # Flexibilidad para cadenas tipo "Equipo or Draw".
        if (
            "draw" in name
            and normalize_text(home_team) in name
        ):
            return price

    return None


def extract_h2h_3way(market, home_team, away_team):
    prices = {
        "home": None,
        "draw": None,
        "away": None,
    }

    for outcome in market.get("outcomes", []):
        name = outcome.get("name", "")
        normalized = normalize_text(name)
        price = safe_float(
            outcome.get("price")
        )

        if price is None:
            continue

        if normalized in {"draw", "tie"}:
            prices["draw"] = price
        elif name_matches(name, home_team):
            prices["home"] = price
        elif name_matches(name, away_team):
            prices["away"] = price

    if any(
        prices[key] is None
        for key in ("home", "draw", "away")
    ):
        return None

    return prices


def evaluate_1x_bookmaker(
    bookmaker,
    model_probability,
    home_team,
    away_team,
):
    market_index = {
        market.get("key"): market
        for market in bookmaker.get("markets", [])
    }

    dc_market = market_index.get("double_chance")
    h2h_market = market_index.get("h2h")

    if dc_market is None or h2h_market is None:
        return None

    bet_odds = extract_double_chance_1x(
        dc_market,
        home_team,
    )

    h2h = extract_h2h_3way(
        h2h_market,
        home_team,
        away_team,
    )

    if bet_odds is None or h2h is None:
        return None

    raw = {
        key: implied_probability(value)
        for key, value in h2h.items()
    }

    if any(value is None for value in raw.values()):
        return None

    overround = sum(raw.values())

    if overround <= 0:
        return None

    no_vig_home = raw["home"] / overround
    no_vig_draw = raw["draw"] / overround

    market_novig_probability = (
        no_vig_home
        + no_vig_draw
    )

    raw_ev = (
        model_probability
        * bet_odds
        - 1
    )

    novig_edge = (
        model_probability
        - market_novig_probability
    )

    return {
        "bookmaker": bookmaker.get("title", "?"),
        "bookmaker_key": bookmaker.get("key", ""),
        "odds": bet_odds,
        "market_novig_probability": market_novig_probability,
        "novig_edge": novig_edge,
        "raw_ev": raw_ev,
        "last_update": (
            dc_market.get("last_update")
            or h2h_market.get("last_update")
            or ""
        ),
    }



def evaluate_1x_cross_bookmakers(
    odds_data,
    model_probability,
    home_team,
    away_team,
):
    """
    El mercado double_chance y el h2h no siempre aparecen en la misma casa.
    Construimos una referencia SIN VIG de consenso con todos los h2h disponibles
    y después evaluamos contra cada precio real 1X disponible.
    """

    h2h_fair_probabilities = []
    double_chance_prices = []

    for bookmaker in odds_data.get(
        "bookmakers",
        [],
    ):
        bookmaker_name = bookmaker.get(
            "title",
            "?",
        )
        bookmaker_key = bookmaker.get(
            "key",
            "",
        )

        for market in bookmaker.get(
            "markets",
            [],
        ):
            market_key = market.get(
                "key"
            )

            if market_key == "h2h":
                h2h = extract_h2h_3way(
                    market,
                    home_team,
                    away_team,
                )

                if h2h is None:
                    continue

                raw = {
                    key: implied_probability(
                        value
                    )
                    for key, value
                    in h2h.items()
                }

                if any(
                    value is None
                    for value in raw.values()
                ):
                    continue

                overround = sum(
                    raw.values()
                )

                if overround <= 0:
                    continue

                no_vig_home = (
                    raw["home"]
                    / overround
                )
                no_vig_draw = (
                    raw["draw"]
                    / overround
                )

                h2h_fair_probabilities.append(
                    no_vig_home
                    + no_vig_draw
                )

            elif market_key == "double_chance":
                bet_odds = (
                    extract_double_chance_1x(
                        market,
                        home_team,
                    )
                )

                if bet_odds is None:
                    continue

                double_chance_prices.append(
                    {
                        "bookmaker":
                            bookmaker_name,
                        "bookmaker_key":
                            bookmaker_key,
                        "odds":
                            bet_odds,
                        "last_update":
                            market.get(
                                "last_update",
                                "",
                            ),
                    }
                )

    if (
        not h2h_fair_probabilities
        or not double_chance_prices
    ):
        return {
            "evaluations": [],
            "h2h_books":
                len(
                    h2h_fair_probabilities
                ),
            "double_chance_books":
                len(
                    double_chance_prices
                ),
        }

    # Mediana: evita que una sola casa distorsione la referencia.
    consensus_novig = median(
        h2h_fair_probabilities
    )

    evaluations = []

    for item in double_chance_prices:
        bet_odds = float(
            item["odds"]
        )

        raw_ev = (
            model_probability
            * bet_odds
            - 1
        )

        novig_edge = (
            model_probability
            - consensus_novig
        )

        evaluation = dict(
            item
        )

        evaluation.update(
            {
                "market_novig_probability":
                    consensus_novig,
                "novig_edge":
                    novig_edge,
                "raw_ev":
                    raw_ev,
                "reference_h2h_books":
                    len(
                        h2h_fair_probabilities
                    ),
            }
        )

        evaluations.append(
            evaluation
        )

    return {
        "evaluations":
            evaluations,
        "h2h_books":
            len(
                h2h_fair_probabilities
            ),
        "double_chance_books":
            len(
                double_chance_prices
            ),
    }



# ============================================================
# MERCADO X2
# ============================================================

def extract_double_chance_x2(
    market,
    away_team,
):
    for outcome in market.get(
        "outcomes",
        [],
    ):
        name = normalize_text(
            outcome.get(
                "name",
                "",
            )
        )

        price = safe_float(
            outcome.get(
                "price"
            )
        )

        if price is None:
            continue

        if name in {
            "x2",
            "away draw",
            "draw away",
        }:
            return price

        if (
            "draw" in name
            and name_matches(
                name.replace(
                    "draw",
                    "",
                ),
                away_team,
            )
        ):
            return price

        if (
            "draw" in name
            and normalize_text(
                away_team
            ) in name
        ):
            return price

    return None


def evaluate_x2_cross_bookmakers(
    odds_data,
    model_probability,
    home_team,
    away_team,
):
    h2h_fair_probabilities = []
    double_chance_prices = []

    for bookmaker in odds_data.get(
        "bookmakers",
        [],
    ):
        bookmaker_name = bookmaker.get(
            "title",
            "?",
        )
        bookmaker_key = bookmaker.get(
            "key",
            "",
        )

        for market in bookmaker.get(
            "markets",
            [],
        ):
            market_key = market.get(
                "key"
            )

            if market_key == "h2h":
                h2h = extract_h2h_3way(
                    market,
                    home_team,
                    away_team,
                )

                if h2h is None:
                    continue

                raw = {
                    key: implied_probability(
                        value
                    )
                    for key, value
                    in h2h.items()
                }

                if any(
                    value is None
                    for value in raw.values()
                ):
                    continue

                overround = sum(
                    raw.values()
                )

                if overround <= 0:
                    continue

                no_vig_draw = (
                    raw["draw"]
                    / overround
                )

                no_vig_away = (
                    raw["away"]
                    / overround
                )

                h2h_fair_probabilities.append(
                    no_vig_draw
                    + no_vig_away
                )

            elif (
                market_key
                == "double_chance"
            ):
                bet_odds = (
                    extract_double_chance_x2(
                        market,
                        away_team,
                    )
                )

                if bet_odds is None:
                    continue

                double_chance_prices.append(
                    {
                        "bookmaker":
                            bookmaker_name,
                        "bookmaker_key":
                            bookmaker_key,
                        "odds":
                            bet_odds,
                        "last_update":
                            market.get(
                                "last_update",
                                "",
                            ),
                    }
                )

    if (
        not h2h_fair_probabilities
        or not double_chance_prices
    ):
        return {
            "evaluations": [],
            "h2h_books":
                len(
                    h2h_fair_probabilities
                ),
            "double_chance_books":
                len(
                    double_chance_prices
                ),
        }

    consensus_novig = median(
        h2h_fair_probabilities
    )

    evaluations = []

    for item in double_chance_prices:
        bet_odds = float(
            item["odds"]
        )

        raw_ev = (
            model_probability
            * bet_odds
            - 1
        )

        novig_edge = (
            model_probability
            - consensus_novig
        )

        evaluation = dict(
            item
        )

        evaluation.update(
            {
                "market_novig_probability":
                    consensus_novig,
                "novig_edge":
                    novig_edge,
                "raw_ev":
                    raw_ev,
                "reference_h2h_books":
                    len(
                        h2h_fair_probabilities
                    ),
            }
        )

        evaluations.append(
            evaluation
        )

    return {
        "evaluations":
            evaluations,
        "h2h_books":
            len(
                h2h_fair_probabilities
            ),
        "double_chance_books":
            len(
                double_chance_prices
            ),
    }


# ============================================================
# MERCADO AWAY_SCORES
# ============================================================

def _outcome_side(outcome):
    name = normalize_text(
        outcome.get("name", "")
    )

    if name == "over" or name.startswith("over "):
        return "over"

    if name == "under" or name.startswith("under "):
        return "under"

    return None


def _outcome_matches_team(
    outcome,
    team_name,
):
    description = outcome.get(
        "description",
        ""
    )

    if (
        description
        and name_matches(
            description,
            team_name,
        )
    ):
        return True

    outcome_name = normalize_text(
        outcome.get("name", "")
    )
    team = normalize_text(
        team_name
    )

    return (
        bool(team)
        and team in outcome_name
    )


def evaluate_away_scores_cross_bookmakers(
    odds_data,
    model_probability,
    away_team,
):
    # AWAY_SCORES = visitante marca al menos 1 gol = Over 0.5.
    # Usamos la mediana de probabilidades sin vig entre casas.

    fair_probabilities = []
    over_prices = []

    books_with_market = set()
    books_with_half_line = set()
    books_with_full_pair = set()

    supported_market_keys = {
        "team_totals",
        "alternate_team_totals",
    }

    for bookmaker in odds_data.get(
        "bookmakers",
        [],
    ):
        bookmaker_name = bookmaker.get(
            "title",
            "?",
        )
        bookmaker_key = bookmaker.get(
            "key",
            "",
        )

        best_over = None
        best_under = None
        last_update = ""

        for market in bookmaker.get(
            "markets",
            [],
        ):
            market_key = market.get(
                "key"
            )

            if market_key not in supported_market_keys:
                continue

            books_with_market.add(
                bookmaker_key
                or bookmaker_name
            )

            for outcome in market.get(
                "outcomes",
                [],
            ):
                point = safe_float(
                    outcome.get("point")
                )
                price = safe_float(
                    outcome.get("price")
                )

                if point is None or price is None:
                    continue

                if abs(point - 0.5) > 1e-9:
                    continue

                if not _outcome_matches_team(
                    outcome,
                    away_team,
                ):
                    continue

                side = _outcome_side(
                    outcome
                )

                if side is None:
                    continue

                books_with_half_line.add(
                    bookmaker_key
                    or bookmaker_name
                )

                last_update = (
                    market.get(
                        "last_update",
                        "",
                    )
                    or last_update
                )

                if side == "over":
                    if (
                        best_over is None
                        or price > best_over
                    ):
                        best_over = price

                elif side == "under":
                    if (
                        best_under is None
                        or price > best_under
                    ):
                        best_under = price

        if best_over is not None:
            over_prices.append(
                {
                    "bookmaker":
                        bookmaker_name,
                    "bookmaker_key":
                        bookmaker_key,
                    "odds":
                        best_over,
                    "last_update":
                        last_update,
                }
            )

        if (
            best_over is None
            or best_under is None
        ):
            continue

        implied_over = implied_probability(
            best_over
        )
        implied_under = implied_probability(
            best_under
        )

        if (
            implied_over is None
            or implied_under is None
        ):
            continue

        overround = (
            implied_over
            + implied_under
        )

        if overround <= 0:
            continue

        books_with_full_pair.add(
            bookmaker_key
            or bookmaker_name
        )

        fair_probabilities.append(
            implied_over
            / overround
        )

    if (
        not fair_probabilities
        or not over_prices
    ):
        return {
            "evaluations": [],
            "market_books":
                len(
                    books_with_market
                ),
            "half_line_books":
                len(
                    books_with_half_line
                ),
            "full_pair_books":
                len(
                    books_with_full_pair
                ),
            "over_price_books":
                len(
                    over_prices
                ),
        }

    consensus_novig = median(
        fair_probabilities
    )

    evaluations = []

    for item in over_prices:
        bet_odds = float(
            item["odds"]
        )

        raw_ev = (
            model_probability
            * bet_odds
            - 1
        )

        novig_edge = (
            model_probability
            - consensus_novig
        )

        evaluation = dict(
            item
        )

        evaluation.update(
            {
                "market_novig_probability":
                    consensus_novig,
                "novig_edge":
                    novig_edge,
                "raw_ev":
                    raw_ev,
                "reference_team_total_books":
                    len(
                        fair_probabilities
                    ),
            }
        )

        evaluations.append(
            evaluation
        )

    return {
        "evaluations":
            evaluations,
        "market_books":
            len(
                books_with_market
            ),
        "half_line_books":
            len(
                books_with_half_line
            ),
        "full_pair_books":
            len(
                books_with_full_pair
            ),
        "over_price_books":
            len(
                over_prices
            ),
    }


# ============================================================
# EVALUAR UNA SEÑAL
# ============================================================

def evaluate_signal(
    row,
    api_key,
):
    market = str(
        row["signal_market"]
    ).strip().upper()

    model_probability = (
        float(
            row["model_probability_pct"]
        )
        / 100
    )

    home = str(row["home"])
    away = str(row["away"])
    event_id = str(row["event_id"]).strip()
    sport_key = str(row["sport_key"]).strip()

    if market in {"1X", "X2"}:
        requested_markets = (
            "double_chance,h2h"
        )
    elif market == "AWAY_SCORES":
        # "Marca al menos 1 gol" exige la línea Over 0.5.
        # alternate_team_totals ofrece las líneas alternativas.
        requested_markets = "alternate_team_totals"
    else:
        return [], {
            "source": "blocked",
            "credits_last": 0,
        }

    result = fetch_event_odds(
        api_key=api_key,
        sport_key=sport_key,
        event_id=event_id,
        markets=requested_markets,
    )

    odds_data = result["payload"]

    # IMPORTANTE:
    # Los nombres del fixture en football-data.org pueden ser distintos
    # a los nombres usados por The Odds API (ej. "CA Paranaense" frente
    # a "Atletico Paranaense"). Para interpretar outcomes de cuotas,
    # usamos los nombres CANÓNICOS devueltos por el propio JSON de odds.
    odds_home = str(
        odds_data.get(
            "home_team",
            home,
        )
        or home
    )

    odds_away = str(
        odds_data.get(
            "away_team",
            away,
        )
        or away
    )

    result[
        "diagnostic_odds_home"
    ] = odds_home

    result[
        "diagnostic_odds_away"
    ] = odds_away

    evaluations = []

    if market == "1X":

        consensus = (
            evaluate_1x_cross_bookmakers(
                odds_data,
                model_probability,
                odds_home,
                odds_away,
            )
        )

        evaluations = consensus[
            "evaluations"
        ]

        result[
            "diagnostic_h2h_books"
        ] = consensus[
            "h2h_books"
        ]

        result[
            "diagnostic_double_chance_books"
        ] = consensus[
            "double_chance_books"
        ]

    elif market == "X2":

        consensus = (
            evaluate_x2_cross_bookmakers(
                odds_data,
                model_probability,
                odds_home,
                odds_away,
            )
        )

        evaluations = consensus[
            "evaluations"
        ]

        result[
            "diagnostic_h2h_books"
        ] = consensus[
            "h2h_books"
        ]

        result[
            "diagnostic_double_chance_books"
        ] = consensus[
            "double_chance_books"
        ]

    else:

        consensus = (
            evaluate_away_scores_cross_bookmakers(
                odds_data,
                model_probability,
                odds_away,
            )
        )

        evaluations = consensus[
            "evaluations"
        ]

        result[
            "diagnostic_team_total_books"
        ] = consensus[
            "market_books"
        ]

        result[
            "diagnostic_half_line_books"
        ] = consensus[
            "half_line_books"
        ]

        result[
            "diagnostic_full_pair_books"
        ] = consensus[
            "full_pair_books"
        ]

        result[
            "diagnostic_over_price_books"
        ] = consensus[
            "over_price_books"
        ]

    for evaluation in evaluations:

        evaluation.update(
            {
                "fixture_id":
                    int(row["fixture_id"]),
                "competition":
                    row["competition"],
                "event_id":
                    event_id,
                "sport_key":
                    sport_key,
                "home":
                    home,
                "away":
                    away,
                "market":
                    market,
                "grade":
                    str(row["grade"]),
                "model_probability":
                    model_probability,
                "model_probability_pct":
                    model_probability * 100,
                "commence_time":
                    row["commence_time"],
            }
        )

        evaluation["approved"] = (
            evaluation["raw_ev"] > 0
            and
            evaluation["novig_edge"] * 100
            >= MIN_NOVIG_EDGE_PP
        )

    return evaluations, result


# ============================================================
# ELECCIÓN FINAL
# ============================================================

def best_candidate_per_bookmaker_event(
    approved_df,
):
    if approved_df.empty:
        return approved_df

    ordered = (
        approved_df
        .sort_values(
            [
                "bookmaker_key",
                "event_id",
                "novig_edge",
                "raw_ev",
                "odds",
            ],
            ascending=[
                True,
                True,
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
        .reset_index(drop=True)
    )

    return ordered


def choose_parlay(approved_df):
    best_pair = None

    for bookmaker_key, group in (
        approved_df.groupby(
            "bookmaker_key"
        )
    ):
        rows = [
            row
            for _, row
            in group.iterrows()
        ]

        for first, second in combinations(
            rows,
            2,
        ):
            if (
                first["event_id"]
                == second["event_id"]
            ):
                continue

            combined_odds = (
                float(first["odds"])
                * float(second["odds"])
            )

            if (
                combined_odds
                < MIN_COMBINED_ODDS
            ):
                continue

            combined_model_probability = (
                float(
                    first["model_probability"]
                )
                * float(
                    second["model_probability"]
                )
            )

            combined_ev = (
                combined_model_probability
                * combined_odds
                - 1
            )

            if combined_ev <= 0:
                continue

            min_edge = min(
                float(first["novig_edge"]),
                float(second["novig_edge"]),
            )

            score = (
                combined_ev,
                min_edge,
                combined_odds,
            )

            candidate = {
                "bookmaker_key":
                    bookmaker_key,
                "bookmaker":
                    first["bookmaker"],
                "legs":
                    [first, second],
                "combined_odds":
                    combined_odds,
                "combined_model_probability":
                    combined_model_probability,
                "combined_ev":
                    combined_ev,
                "score":
                    score,
            }

            if (
                best_pair is None
                or candidate["score"]
                > best_pair["score"]
            ):
                best_pair = candidate

    return best_pair


def choose_single(approved_df):
    singles = approved_df[
        approved_df[
            "odds"
        ] >= MIN_SINGLE_ODDS
    ].copy()

    if singles.empty:
        return None

    singles = singles.sort_values(
        [
            "raw_ev",
            "novig_edge",
            "odds",
        ],
        ascending=[
            False,
            False,
            False,
        ],
    )

    return singles.iloc[0]


# ============================================================
# SALIDA
# ============================================================

def market_label(row):
    if row["market"] == "1X":
        return (
            f"1X — {row['home']} "
            "gana o empata"
        )

    if row["market"] == "X2":
        return (
            f"X2 — {row['away']} "
            "gana o empata"
        )

    if row["market"] == "AWAY_SCORES":
        return (
            f"{row['away']} marca "
            "al menos 1 gol"
        )

    return row["market"]


def serializable_leg(row):
    return {
        "fixture_id":
            int(row["fixture_id"]),
        "event_id":
            str(row["event_id"]),
        "competition":
            str(row["competition"]),
        "home":
            str(row["home"]),
        "away":
            str(row["away"]),
        "market":
            str(row["market"]),
        "selection":
            market_label(row),
        "grade":
            str(row["grade"]),
        "bookmaker":
            str(row["bookmaker"]),
        "odds":
            round(float(row["odds"]), 3),
        "model_probability_pct":
            round(
                float(
                    row["model_probability"]
                ) * 100,
                2,
            ),
        "market_novig_probability_pct":
            round(
                float(
                    row[
                        "market_novig_probability"
                    ]
                ) * 100,
                2,
            ),
        "novig_edge_pp":
            round(
                float(row["novig_edge"])
                * 100,
                2,
            ),
        "raw_ev_pct":
            round(
                float(row["raw_ev"])
                * 100,
                2,
            ),
        "commence_time":
            str(
                row.get(
                    "commence_time",
                    "",
                )
            ),
    }


# ============================================================
# LEDGER PROSPECTIVO DE PARLAYS
# ============================================================

PARLAY_LEDGER_COLUMNS = [
    "record_id",
    "created_at_utc",
    "bookmaker",
    "bookmaker_key",
    "combined_odds",
    "combined_model_probability_pct",
    "combined_ev_pct",
    "status",
    "leg1_status",
    "leg1_score",
    "leg1_fixture_id",
    "leg1_event_id",
    "leg1_competition",
    "leg1_home",
    "leg1_away",
    "leg1_market",
    "leg1_selection",
    "leg1_odds",
    "leg1_model_probability_pct",
    "leg1_novig_edge_pp",
    "leg1_commence_time",
    "leg2_status",
    "leg2_score",
    "leg2_fixture_id",
    "leg2_event_id",
    "leg2_competition",
    "leg2_home",
    "leg2_away",
    "leg2_market",
    "leg2_selection",
    "leg2_odds",
    "leg2_model_probability_pct",
    "leg2_novig_edge_pp",
    "leg2_commence_time",
    "settled_at_utc",
]


def parlay_record_id(
    parlay,
):
    legs = sorted(
        [
            (
                str(leg["event_id"]),
                str(leg["market"]),
            )
            for leg in parlay["legs"]
        ]
    )

    # Para evitar duplicados entre ejecuciones usamos
    # el nombre visible de la casa, no bookmaker_key.
    # El mismo parlay debe conservar el mismo record_id
    # aunque una versión antigua no tuviera bookmaker_key.
    bookmaker_identity = normalize_text(
        parlay.get(
            "bookmaker",
            "",
        )
    )

    fingerprint = (
        bookmaker_identity
        + "|"
        + "|".join(
            f"{event_id}:{market}"
            for event_id, market
            in legs
        )
    )

    return hashlib.sha1(
        fingerprint.encode(
            "utf-8"
        )
    ).hexdigest()[:20]


def build_parlay_ledger_row(
    parlay,
):
    legs = parlay["legs"]

    first = serializable_leg(
        legs[0]
    )
    second = serializable_leg(
        legs[1]
    )

    record_id = parlay_record_id(
        parlay
    )

    return {
        "record_id":
            record_id,
        "created_at_utc":
            utc_now().isoformat(),
        "bookmaker":
            str(
                parlay.get(
                    "bookmaker",
                    "",
                )
            ),
        "bookmaker_key":
            str(
                parlay.get(
                    "bookmaker_key",
                    "",
                )
            ),
        "combined_odds":
            round(
                float(
                    parlay[
                        "combined_odds"
                    ]
                ),
                4,
            ),
        "combined_model_probability_pct":
            round(
                float(
                    parlay[
                        "combined_model_probability"
                    ]
                )
                * 100,
                2,
            ),
        "combined_ev_pct":
            round(
                float(
                    parlay[
                        "combined_ev"
                    ]
                )
                * 100,
                2,
            ),
        "status":
            "PENDING",
        "leg1_status":
            "PENDING",
        "leg1_score":
            "",
        "leg1_fixture_id":
            first["fixture_id"],
        "leg1_event_id":
            first["event_id"],
        "leg1_competition":
            first["competition"],
        "leg1_home":
            first["home"],
        "leg1_away":
            first["away"],
        "leg1_market":
            first["market"],
        "leg1_selection":
            first["selection"],
        "leg1_odds":
            first["odds"],
        "leg1_model_probability_pct":
            first[
                "model_probability_pct"
            ],
        "leg1_novig_edge_pp":
            first[
                "novig_edge_pp"
            ],
        "leg1_commence_time":
            first.get(
                "commence_time",
                "",
            ),
        "leg2_status":
            "PENDING",
        "leg2_score":
            "",
        "leg2_fixture_id":
            second["fixture_id"],
        "leg2_event_id":
            second["event_id"],
        "leg2_competition":
            second["competition"],
        "leg2_home":
            second["home"],
        "leg2_away":
            second["away"],
        "leg2_market":
            second["market"],
        "leg2_selection":
            second["selection"],
        "leg2_odds":
            second["odds"],
        "leg2_model_probability_pct":
            second[
                "model_probability_pct"
            ],
        "leg2_novig_edge_pp":
            second[
                "novig_edge_pp"
            ],
        "leg2_commence_time":
            second.get(
                "commence_time",
                "",
            ),
        "settled_at_utc":
            "",
    }


def record_parlay_to_ledger(
    parlay,
):
    row = build_parlay_ledger_row(
        parlay
    )

    record_id = row[
        "record_id"
    ]

    if PARLAY_LEDGER_FILE.exists():

        try:
            existing = pd.read_csv(
                PARLAY_LEDGER_FILE,
                dtype=str,
            )

        except (
            pd.errors.EmptyDataError,
            pd.errors.ParserError,
            OSError,
        ):
            existing = pd.DataFrame(
                columns=
                    PARLAY_LEDGER_COLUMNS
            )

        # No basta con comparar record_id.
        # Versiones anteriores pudieron generar un hash diferente
        # para el mismo parlay. Comparamos también la identidad real:
        # casa + 2 event_id + mercados.

        target_legs = sorted(
            [
                (
                    str(
                        row[
                            "leg1_event_id"
                        ]
                    ).strip(),
                    str(
                        row[
                            "leg1_market"
                        ]
                    ).strip().upper(),
                ),
                (
                    str(
                        row[
                            "leg2_event_id"
                        ]
                    ).strip(),
                    str(
                        row[
                            "leg2_market"
                        ]
                    ).strip().upper(),
                ),
            ]
        )

        target_bookmaker = (
            normalize_text(
                row[
                    "bookmaker"
                ]
            )
        )

        for index, existing_row in (
            existing.iterrows()
        ):
            existing_legs = sorted(
                [
                    (
                        str(
                            existing_row.get(
                                "leg1_event_id",
                                "",
                            )
                        ).strip(),
                        str(
                            existing_row.get(
                                "leg1_market",
                                "",
                            )
                        ).strip().upper(),
                    ),
                    (
                        str(
                            existing_row.get(
                                "leg2_event_id",
                                "",
                            )
                        ).strip(),
                        str(
                            existing_row.get(
                                "leg2_market",
                                "",
                            )
                        ).strip().upper(),
                    ),
                ]
            )

            existing_bookmaker = (
                normalize_text(
                    existing_row.get(
                        "bookmaker",
                        "",
                    )
                )
            )

            if (
                existing_bookmaker
                == target_bookmaker
                and existing_legs
                == target_legs
            ):
                existing_record_id = str(
                    existing_row.get(
                        "record_id",
                        record_id,
                    )
                )

                return (
                    existing_record_id,
                    False,
                )

        if (
            "record_id"
            in existing.columns
            and record_id
            in set(
                existing[
                    "record_id"
                ].astype(str)
            )
        ):
            return record_id, False

    else:
        existing = pd.DataFrame(
            columns=
                PARLAY_LEDGER_COLUMNS
        )

    new_row = pd.DataFrame(
        [row],
        columns=
            PARLAY_LEDGER_COLUMNS,
    )

    combined = pd.concat(
        [
            existing,
            new_row,
        ],
        ignore_index=True,
    )

    combined = combined.reindex(
        columns=
            PARLAY_LEDGER_COLUMNS
    )

    combined.to_csv(
        PARLAY_LEDGER_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    return record_id, True


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 88)
    print("🐍 CULEBRIA — MODO OPERATIVO")
    print("=" * 88)
    print()
    print(
        f"Objetivo: cuota >= "
        f"{MIN_COMBINED_ODDS:.2f}"
    )
    print(
        "Mercados operativos: "
        "1X / X2 / AWAY_SCORES"
    )
    print(
        f"Edge mínimo sin vig: "
        f"{MIN_NOVIG_EDGE_PP:.2f} pp"
    )
    print()

    if not INPUT_FILE.exists():
        print(
            "❌ No existe "
            "prematch_odds_candidates.csv"
        )
        return

    df = pd.read_csv(
        INPUT_FILE
    )

    if df.empty:
        print("⛔ NO BET — no hay señales.")
        return

    required = {
        "fixture_id",
        "competition",
        "sport_key",
        "event_id",
        "home",
        "away",
        "signal_market",
        "model_probability_pct",
        "grade",
        "commence_time",
    }

    missing = required - set(
        df.columns
    )

    if missing:
        print(
            "❌ Faltan columnas: "
            + ", ".join(
                sorted(missing)
            )
        )
        return

    now = utc_now()
    rows = []

    for _, row in df.iterrows():
        market = str(
            row["signal_market"]
        ).strip().upper()

        kickoff = parse_datetime(
            row["commence_time"]
        )

        reasons = []

        if market not in ALLOWED_MARKETS:
            reasons.append(
                "MERCADO_BLOQUEADO"
            )

        if kickoff is None:
            reasons.append(
                "FECHA_INVALIDA"
            )
            minutes_to_start = None
        else:
            minutes_to_start = (
                kickoff - now
            ).total_seconds() / 60

            if minutes_to_start <= 0:
                reasons.append(
                    "PARTIDO_INICIADO"
                )
            elif (
                minutes_to_start
                < MIN_MINUTES_TO_KICKOFF
            ):
                reasons.append(
                    "MUY_CERCA_DEL_INICIO"
                )

        row_copy = row.copy()
        row_copy[
            "_minutes_to_start"
        ] = minutes_to_start
        row_copy[
            "_precheck_reasons"
        ] = " | ".join(reasons)

        rows.append(row_copy)

    prechecked = pd.DataFrame(
        rows
    )

    valid = prechecked[
        prechecked[
            "_precheck_reasons"
        ] == ""
    ].copy()

    if valid.empty:
        print(
            "⛔ NO BET — ninguna señal "
            "sigue siendo PREMATCH y operativa."
        )
        return

    valid[
        "_grade_priority"
    ] = (
        valid["grade"]
        .astype(str)
        .str.upper()
        .map(GRADE_PRIORITY)
        .fillna(99)
    )

    valid[
        "_prob"
    ] = pd.to_numeric(
        valid[
            "model_probability_pct"
        ],
        errors="coerce",
    ).fillna(0)

    valid = (
        valid
        .sort_values(
            [
                "_grade_priority",
                "_prob",
            ],
            ascending=[
                True,
                False,
            ],
        )
        .head(
            MAX_SIGNALS_TO_PRICE
        )
    )

    load_dotenv(
        ROOT_DIR / ".env"
    )

    api_key = os.getenv(
        "THE_ODDS_API_KEY"
    )

    if not api_key:
        print(
            "❌ THE_ODDS_API_KEY "
            "no encontrada en .env"
        )
        return

    all_evaluations = []
    total_api_calls = 0
    total_reported_cost = 0
    cache_hits = 0
    estimated_cache_credits_saved = 0

    for _, row in valid.iterrows():
        market = str(
            row["signal_market"]
        ).upper()

        print("-" * 88)
        print(
            f"{row['home']} vs "
            f"{row['away']}"
        )
        print(
            f"Mercado: {market}"
        )
        print(
            "Modelo: "
            f"{float(row['model_probability_pct']):.2f}%"
        )

        try:
            evaluations, api_result = (
                evaluate_signal(
                    row,
                    api_key,
                )
            )
        except requests.RequestException as error:
            print(
                "❌ Error consultando cuotas:"
            )
            print(error)
            continue

        if api_result.get(
            "source"
        ) == "api":
            total_api_calls += 1

            cost = safe_float(
                api_result.get(
                    "credits_last"
                )
            )

            if cost is not None:
                total_reported_cost += int(
                    cost
                )

            print(
                "Cuotas: 🌐 API"
            )
            print(
                "Créditos restantes: "
                f"{api_result.get('credits_remaining')}"
            )
        else:
            cache_hits += 1

            saved = int(
                api_result.get(
                    "estimated_saved_credits",
                    0,
                )
                or 0
            )

            estimated_cache_credits_saved += (
                saved
            )

            age_minutes = (
                float(
                    api_result.get(
                        "cache_age_seconds",
                        0,
                    )
                )
                / 60
            )

            ttl_minutes = (
                float(
                    api_result.get(
                        "cache_ttl_seconds",
                        0,
                    )
                )
                / 60
            )

            print(
                "Cuotas: 💾 caché inteligente "
                f"(edad {age_minutes:.1f} min / "
                f"TTL {ttl_minutes:.0f} min)"
            )

        if not evaluations:

            if market in {"1X", "X2"}:

                print(
                    "⛔ No se pudo construir "
                    "precio + no-vig comparable."
                )

                print(
                    "   Nombres Odds API: "
                    f"{api_result.get('diagnostic_odds_home', '?')} "
                    "vs "
                    f"{api_result.get('diagnostic_odds_away', '?')}"
                )

                print(
                    "   Casas con h2h utilizable: "
                    f"{api_result.get('diagnostic_h2h_books', 0)}"
                )

                print(
                    f"   Casas con {market} utilizable: "
                    f"{api_result.get('diagnostic_double_chance_books', 0)}"
                )

            else:

                print(
                    "⛔ No se pudo construir "
                    "precio + no-vig comparable."
                )

                print(
                    "   Casas con team totals: "
                    f"{api_result.get('diagnostic_team_total_books', 0)}"
                )

                print(
                    "   Casas con línea visitante 0.5: "
                    f"{api_result.get('diagnostic_half_line_books', 0)}"
                )

                print(
                    "   Casas con Over+Under 0.5: "
                    f"{api_result.get('diagnostic_full_pair_books', 0)}"
                )

                print(
                    "   Casas con precio Over 0.5: "
                    f"{api_result.get('diagnostic_over_price_books', 0)}"
                )

            continue

        approved_here = [
            item
            for item in evaluations
            if item["approved"]
        ]

        if approved_here:
            best_here = max(
                approved_here,
                key=lambda item: (
                    item["raw_ev"],
                    item["novig_edge"],
                    item["odds"],
                ),
            )

            print(
                "✅ Candidato aprobado:"
            )
            print(
                f"   Casa: "
                f"{best_here['bookmaker']}"
            )
            print(
                f"   Cuota: "
                f"{best_here['odds']:.3f}"
            )
            print(
                "   Mercado sin vig: "
                f"{best_here['market_novig_probability'] * 100:.2f}%"
            )
            print(
                "   Edge sin vig: "
                f"{best_here['novig_edge'] * 100:+.2f} pp"
            )
            print(
                "   EV bruto: "
                f"{best_here['raw_ev'] * 100:+.2f}%"
            )
        else:
            print(
                "⛔ No supera precio + no-vig."
            )

        all_evaluations.extend(
            evaluations
        )

    evaluations_df = pd.DataFrame(
        all_evaluations
    )

    if evaluations_df.empty:
        print()
        print(
            "⛔ NO BET — no hubo "
            "mercados comparables."
        )
        return

    evaluations_df[
        "novig_edge_pp"
    ] = (
        evaluations_df[
            "novig_edge"
        ] * 100
    )

    evaluations_df[
        "raw_ev_pct"
    ] = (
        evaluations_df[
            "raw_ev"
        ] * 100
    )

    evaluations_df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    approved_df = (
        evaluations_df[
            evaluations_df[
                "approved"
            ] == True
        ]
        .copy()
    )

    approved_df = (
        best_candidate_per_bookmaker_event(
            approved_df
        )
    )

    parlay = choose_parlay(
        approved_df
    )

    # Política final CulebrIA:
    # SOLO se acepta un parlay de EXACTAMENTE 2 partidos distintos.
    # No existe fallback a apuesta individual.

    print()
    print("=" * 88)
    print("RESULTADO FINAL CULEBRIA")
    print("=" * 88)
    print()

    final_payload = {
        "generated_at_utc":
            utc_now().isoformat(),
        "min_target_odds":
            MIN_COMBINED_ODDS,
        "min_novig_edge_pp":
            MIN_NOVIG_EDGE_PP,
        "api_calls":
            total_api_calls,
        "reported_api_cost":
            total_reported_cost,
    }

    if parlay is not None:
        legs = parlay["legs"]

        print("✅ APUESTA PROPUESTA — PARLAY")
        print()
        print(
            f"Casa: {parlay['bookmaker']}"
        )

        for number, leg in enumerate(
            legs,
            start=1,
        ):
            print()
            print(
                f"{number}. "
                f"{leg['home']} vs "
                f"{leg['away']}"
            )
            print(
                f"   Apostar: "
                f"{market_label(leg)}"
            )
            print(
                f"   Cuota: "
                f"{float(leg['odds']):.3f}"
            )
            print(
                f"   Prob. modelo: "
                f"{float(leg['model_probability']) * 100:.2f}%"
            )
            print(
                f"   Edge sin vig: "
                f"{float(leg['novig_edge']) * 100:+.2f} pp"
            )

        print()
        print(
            "CUOTA COMBINADA: "
            f"{parlay['combined_odds']:.3f}"
        )
        print(
            "EV combinado estimado: "
            f"{parlay['combined_ev'] * 100:+.2f}%"
        )

        final_payload.update(
            {
                "decision":
                    "PARLAY",
                "bookmaker":
                    parlay["bookmaker"],
                "combined_odds":
                    round(
                        parlay[
                            "combined_odds"
                        ],
                        4,
                    ),
                "combined_ev_pct":
                    round(
                        parlay[
                            "combined_ev"
                        ] * 100,
                        2,
                    ),
                "legs": [
                    serializable_leg(
                        leg
                    )
                    for leg in legs
                ],
            }
        )

        record_id, was_created = (
            record_parlay_to_ledger(
                parlay
            )
        )

        final_payload[
            "prospective_record_id"
        ] = record_id

        final_payload[
            "prospective_record_created"
        ] = was_created

        print()

        if was_created:
            print(
                "📝 Parlay guardado en ledger prospectivo: "
                f"{record_id}"
            )
        else:
            print(
                "📝 Parlay ya estaba registrado: "
                f"{record_id}"
            )

    else:
        print("⛔ NO BET")
        print()
        print(
            "No existen exactamente 2 selecciones "
            "aprobadas, de partidos distintos y "
            "disponibles en la misma casa, "
            f"con cuota combinada >= "
            f"{MIN_COMBINED_ODDS:.2f}."
        )

        if not approved_df.empty:
            print()
            print(
                "Hay candidatos estadísticos, "
                "pero no alcanzan la política "
                "de cuota objetivo."
            )

        final_payload.update(
            {
                "decision":
                    "NO_BET",
                "approved_candidates":
                    int(
                        len(
                            approved_df
                        )
                    ),
            }
        )

    FINAL_FILE.write_text(
        json.dumps(
            final_payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("-" * 88)
    print(
        f"Consultas API nuevas: "
        f"{total_api_calls}"
    )
    print(
        "Coste informado por API: "
        f"{total_reported_cost}"
    )
    print(
        f"Usos de caché inteligente: "
        f"{cache_hits}"
    )
    print(
        "Créditos estimados evitados por caché: "
        f"{estimated_cache_credits_saved}"
    )
    print(
        f"Reporte: {OUTPUT_FILE}"
    )
    print(
        f"Decisión: {FINAL_FILE}"
    )
    print()
    print(
        "⚠️ Una señal estadística "
        "no garantiza un resultado ganador."
    )


if __name__ == "__main__":
    main()
