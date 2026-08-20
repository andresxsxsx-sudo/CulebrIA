from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from datetime import datetime, timezone, date
from pathlib import Path
from statistics import median

import requests
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
MODEL_DIR = DATA / "tennis_model_v1"

DECISION_FILE = DATA / "culebria_tennis_operational_v1.json"
RATINGS_FILE = MODEL_DIR / "wta_ratings_current.json"
OUTPUT_FILE = DATA / "culebria_tennis_bet_confirmation.json"

BASE_URL = "https://api.the-odds-api.com/v4"
REGIONS = "eu"
MARKET = "h2h"
ODDS_FORMAT = "decimal"
DATE_FORMAT = "iso"

MAX_DECISION_AGE_MINUTES = 30
MAX_RATINGS_AGE_DAYS = 2

MIN_REFERENCE_BOOKS = 4
MIN_MODEL_EDGE_VS_CONSENSUS_PP = 1.50
MIN_MODEL_EDGE_VS_TARGET_PP = 1.50
MIN_LEG_ODDS = 1.25
MAX_LEG_ODDS = 1.60
MIN_COMBINED_ODDS = 1.80

APPROVED_BANDS = {
    "70-75%",
    "75-80%",
}

EXCLUDED_BOOKMAKER_TOKENS = {
    "betfair",
    "matchbook",
    "smarkets",
}


def now_utc():
    return datetime.now(timezone.utc)


def normalize(value):
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        ch for ch in text
        if not unicodedata.combining(ch)
    )
    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )
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


def api_get(url, params):
    response = requests.get(
        url,
        params=params,
        timeout=25,
    )

    if response.status_code >= 400:
        # No imprimimos la URL porque contendría la API key.
        raise RuntimeError(
            f"HTTP {response.status_code} consultando The Odds API."
        )

    try:
        payload = response.json()
    except ValueError:
        raise RuntimeError(
            "The Odds API devolvió una respuesta no JSON."
        )

    return {
        "payload": payload,
        "cost": response.headers.get(
            "x-requests-last"
        ),
        "remaining": response.headers.get(
            "x-requests-remaining"
        ),
    }


def implied_probability(odds):
    odds = safe_float(odds)

    if odds is None or odds <= 1:
        return None

    return 1.0 / odds


def bookmaker_allowed(bookmaker):
    text = (
        normalize(
            bookmaker.get("title", "")
        )
        + " "
        + normalize(
            bookmaker.get("key", "")
        )
    )

    return not any(
        token in text
        for token in EXCLUDED_BOOKMAKER_TOKENS
    )


def h2h_pair(bookmaker):
    market = next(
        (
            market
            for market in bookmaker.get(
                "markets",
                []
            )
            if market.get("key") == "h2h"
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
            outcome.get("name", "")
        ).strip()

        odds = safe_float(
            outcome.get("price")
        )

        if (
            not name
            or odds is None
            or odds <= 1
        ):
            continue

        outcomes.append(
            {
                "name": name,
                "odds": odds,
            }
        )

    if len(outcomes) != 2:
        return None

    p1 = implied_probability(
        outcomes[0]["odds"]
    )
    p2 = implied_probability(
        outcomes[1]["odds"]
    )

    if p1 is None or p2 is None:
        return None

    total = p1 + p2

    if total <= 0:
        return None

    outcomes[0]["novig"] = p1 / total
    outcomes[1]["novig"] = p2 / total

    return outcomes


def find_outcome(pair, selection):
    target = normalize(selection)

    for outcome in pair:
        if normalize(
            outcome["name"]
        ) == target:
            return outcome

    return None


def load_decision():
    if not DECISION_FILE.exists():
        raise RuntimeError(
            "No existe culebria_tennis_operational_v1.json. "
            "Ejecuta primero culebria_tennis_operational_v1.py"
        )

    payload = json.loads(
        DECISION_FILE.read_text(
            encoding="utf-8"
        )
    )

    generated = parse_dt(
        payload.get("generated_at_utc")
    )

    if generated is None:
        raise RuntimeError(
            "La decisión no tiene generated_at_utc válido."
        )

    age_minutes = (
        now_utc()
        - generated
    ).total_seconds() / 60.0

    if age_minutes < -2:
        raise RuntimeError(
            "La decisión parece venir del futuro. "
            "Revisa la hora del sistema."
        )

    if age_minutes > MAX_DECISION_AGE_MINUTES:
        raise RuntimeError(
            f"Decisión demasiado antigua: {age_minutes:.1f} min. "
            "Ejecuta de nuevo culebria_tennis_operational_v1.py"
        )

    if payload.get("status") != "PARLAY":
        raise RuntimeError(
            "La decisión actual es NO BET; no hay nada que confirmar."
        )

    parlay = payload.get("best_parlay")

    if not isinstance(parlay, dict):
        raise RuntimeError(
            "Falta best_parlay en la decisión."
        )

    legs = parlay.get("legs")

    if (
        not isinstance(legs, list)
        or len(legs) != 2
    ):
        raise RuntimeError(
            "best_parlay no contiene exactamente 2 piernas."
        )

    if (
        str(legs[0].get("event_id"))
        == str(legs[1].get("event_id"))
    ):
        raise RuntimeError(
            "Las dos piernas pertenecen al mismo evento."
        )

    return (
        payload,
        parlay,
        legs,
        age_minutes,
    )


def check_ratings(decision):
    if not RATINGS_FILE.exists():
        raise RuntimeError(
            "No existe wta_ratings_current.json."
        )

    ratings = json.loads(
        RATINGS_FILE.read_text(
            encoding="utf-8"
        )
    )

    through = (
        ratings.get(
            "live_update",
            {}
        ).get("through")
    )

    if not through:
        raise RuntimeError(
            "Los ratings actuales no tienen fecha through."
        )

    decision_through = str(
        decision.get(
            "ratings_through",
            ""
        )
    )

    if str(through) != decision_through:
        raise RuntimeError(
            "Los ratings cambiaron desde que se generó la decisión. "
            "Ejecuta nuevamente culebria_tennis_operational_v1.py"
        )

    try:
        through_date = date.fromisoformat(
            str(through)
        )
    except ValueError:
        raise RuntimeError(
            "Fecha through inválida en los ratings."
        )

    age_days = (
        now_utc().date()
        - through_date
    ).days

    if age_days > MAX_RATINGS_AGE_DAYS:
        raise RuntimeError(
            f"Ratings demasiado antiguos: {through}."
        )

    return through, age_days


def discover_sport_keys(api_key, legs):
    response = api_get(
        f"{BASE_URL}/sports/",
        {
            "apiKey": api_key,
        },
    )

    active_wta = []

    for item in response["payload"]:
        if item.get("active") is False:
            continue

        if item.get("has_outrights") is True:
            continue

        group = normalize(
            item.get("group", "")
        )

        title = str(
            item.get("title", "")
        )

        key = str(
            item.get("key", "")
        )

        if group != "tennis":
            continue

        if (
            "wta" not in normalize(title)
            and "wta" not in normalize(key)
        ):
            continue

        active_wta.append(
            {
                "key": key,
                "title": title,
            }
        )

    result = {}

    for leg in legs:
        event_id = str(
            leg.get("event_id", "")
        )
        competition = normalize(
            leg.get("competition", "")
        )

        exact = [
            sport
            for sport in active_wta
            if normalize(
                sport["title"]
            ) == competition
        ]

        if len(exact) == 1:
            result[event_id] = exact[0]["key"]
            continue

        # /events no consume créditos. Se usa solo si el título no basta.
        found = None

        for sport in active_wta:
            event_response = api_get(
                (
                    f"{BASE_URL}/sports/"
                    f"{sport['key']}/events"
                ),
                {
                    "apiKey": api_key,
                    "dateFormat": DATE_FORMAT,
                    "eventIds": event_id,
                },
            )

            payload = event_response["payload"]

            if any(
                str(event.get("id", ""))
                == event_id
                for event in payload
            ):
                found = sport["key"]
                break

        if found is None:
            raise RuntimeError(
                f"No pude resolver el torneo del evento {event_id}."
            )

        result[event_id] = found

    return result, response.get("remaining")


def fetch_fresh_event(
    api_key,
    sport_key,
    event_id,
):
    return api_get(
        (
            f"{BASE_URL}/sports/"
            f"{sport_key}/events/"
            f"{event_id}/odds"
        ),
        {
            "apiKey": api_key,
            "regions": REGIONS,
            "markets": MARKET,
            "oddsFormat": ODDS_FORMAT,
            "dateFormat": DATE_FORMAT,
        },
    )


def evaluate_leg(
    leg,
    bookmaker_title,
    event_payload,
):
    event_id = str(
        leg.get("event_id", "")
    )

    if str(
        event_payload.get("id", "")
    ) != event_id:
        return {
            "ok": False,
            "reason": "EVENT_ID_MISMATCH",
        }

    commence = parse_dt(
        event_payload.get("commence_time")
    )

    if (
        commence is None
        or commence <= now_utc()
    ):
        return {
            "ok": False,
            "reason": "EVENT_STARTED_OR_INVALID",
        }

    model_probability = safe_float(
        leg.get("model_probability_pct")
    )

    if model_probability is None:
        return {
            "ok": False,
            "reason": "MODEL_PROBABILITY_MISSING",
        }

    model_probability /= 100.0

    band = str(
        leg.get("reliability_band", "")
    )

    if band not in APPROVED_BANDS:
        return {
            "ok": False,
            "reason": "RELIABILITY_BAND_NOT_APPROVED",
        }

    selection = str(
        leg.get("selection", "")
    )

    books = []

    for bookmaker in event_payload.get(
        "bookmakers",
        []
    ):
        if not bookmaker_allowed(
            bookmaker
        ):
            continue

        pair = h2h_pair(
            bookmaker
        )

        if pair is None:
            continue

        outcome = find_outcome(
            pair,
            selection,
        )

        if outcome is None:
            continue

        books.append(
            {
                "bookmaker": str(
                    bookmaker.get("title", "?")
                ),
                "bookmaker_key": str(
                    bookmaker.get("key", "")
                ),
                "odds": float(
                    outcome["odds"]
                ),
                "novig": float(
                    outcome["novig"]
                ),
            }
        )

    target = next(
        (
            row
            for row in books
            if normalize(
                row["bookmaker"]
            ) == normalize(
                bookmaker_title
            )
        ),
        None,
    )

    if target is None:
        return {
            "ok": False,
            "reason": "BOOKMAKER_OR_SELECTION_UNAVAILABLE",
        }

    refs = [
        row["novig"]
        for row in books
        if row["bookmaker_key"]
        != target["bookmaker_key"]
    ]

    if len(refs) < MIN_REFERENCE_BOOKS:
        return {
            "ok": False,
            "reason": "NOT_ENOUGH_REFERENCE_BOOKS",
            "reference_books": len(refs),
        }

    consensus = median(
        refs
    )

    edge_consensus_pp = (
        model_probability
        - consensus
    ) * 100.0

    edge_target_pp = (
        model_probability
        - target["novig"]
    ) * 100.0

    raw_ev_pct = (
        model_probability
        * target["odds"]
        - 1.0
    ) * 100.0

    reasons = []

    if not (
        MIN_LEG_ODDS
        <= target["odds"]
        <= MAX_LEG_ODDS
    ):
        reasons.append(
            "ODDS_OUTSIDE_RANGE"
        )

    if (
        edge_consensus_pp
        < MIN_MODEL_EDGE_VS_CONSENSUS_PP
    ):
        reasons.append(
            "EDGE_VS_CONSENSUS_TOO_LOW"
        )

    if (
        edge_target_pp
        < MIN_MODEL_EDGE_VS_TARGET_PP
    ):
        reasons.append(
            "EDGE_VS_TARGET_TOO_LOW"
        )

    if raw_ev_pct <= 0:
        reasons.append(
            "EV_NOT_POSITIVE"
        )

    return {
        "ok": not reasons,
        "reason": (
            "OK"
            if not reasons
            else ",".join(reasons)
        ),
        "event_id": event_id,
        "players": str(
            leg.get("players", "")
        ),
        "selection": selection,
        "surface": str(
            leg.get("surface", "")
        ),
        "reliability_band": band,
        "model_probability": model_probability,
        "fresh_odds": target["odds"],
        "fresh_target_novig": target["novig"],
        "fresh_market_consensus_novig": consensus,
        "fresh_edge_vs_consensus_pp": edge_consensus_pp,
        "fresh_edge_vs_target_pp": edge_target_pp,
        "fresh_raw_ev_pct": raw_ev_pct,
        "reference_books": len(refs),
        "commence_time": str(
            event_payload.get("commence_time", "")
        ),
    }


def write_result(payload):
    OUTPUT_FILE.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main():
    print("=" * 94)
    print(
        "🐍 CULEBRIA TENNIS — CONFIRMACIÓN FINAL WTA"
    )
    print("=" * 94)
    print()
    print(
        "Usa la decisión #1 actual y vuelve a consultar "
        "SOLO sus 2 eventos."
    )
    print(
        f"Edad máxima de decisión: "
        f"{MAX_DECISION_AGE_MINUTES} min"
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
            decision,
            parlay,
            legs,
            decision_age,
        ) = load_decision()

        ratings_through, ratings_age = (
            check_ratings(
                decision
            )
        )

    except Exception as exc:
        print(
            f"⛔ NO CONFIRMADO — {exc}"
        )
        return

    bookmaker = str(
        parlay.get("bookmaker", "")
    )

    print(
        f"Decisión generada hace: "
        f"{decision_age:.1f} min"
    )
    print(
        f"Ratings WTA: {ratings_through} "
        f"(edad {ratings_age} días)"
    )
    print(
        f"Casa seleccionada: {bookmaker}"
    )
    print()

    for index, leg in enumerate(
        legs,
        start=1,
    ):
        print(
            f"{index}. {leg.get('players')}"
        )
        print(
            f"   Apostar: {leg.get('selection')} gana"
        )
        print(
            f"   Prob. modelo: "
            f"{safe_float(leg.get('model_probability_pct')):.2f}%"
        )
        print(
            f"   Cuota previa: "
            f"{safe_float(leg.get('odds')):.3f}"
        )

    print()
    print(
        "Consultando cuotas frescas..."
    )

    try:
        sport_keys, remaining = (
            discover_sport_keys(
                api_key,
                legs,
            )
        )
    except Exception as exc:
        print(
            f"⛔ NO CONFIRMADO — {exc}"
        )
        return

    fresh_results = []
    total_cost = 0

    for index, leg in enumerate(
        legs,
        start=1,
    ):
        event_id = str(
            leg["event_id"]
        )
        sport_key = sport_keys[
            event_id
        ]

        try:
            response = fetch_fresh_event(
                api_key,
                sport_key,
                event_id,
            )
        except Exception as exc:
            print(
                f"⛔ Evento {index}: {exc}"
            )
            return

        try:
            total_cost += int(
                response.get("cost")
                or 0
            )
        except (TypeError, ValueError):
            pass

        if response.get(
            "remaining"
        ) is not None:
            remaining = response[
                "remaining"
            ]

        result = evaluate_leg(
            leg,
            bookmaker,
            response[
                "payload"
            ],
        )

        fresh_results.append(
            result
        )

        print()
        print("-" * 94)
        print(
            f"PIERNA {index}"
        )

        if not result["ok"]:
            print(
                f"⛔ RECHAZADA: "
                f"{result['reason']}"
            )
            continue

        print(
            f"✅ {result['players']}"
        )
        print(
            f"   Apostar: "
            f"{result['selection']} gana"
        )
        print(
            f"   Cuota fresca: "
            f"{result['fresh_odds']:.3f}"
        )
        print(
            f"   Prob. modelo: "
            f"{result['model_probability'] * 100:.2f}%"
        )
        print(
            f"   Consenso fresco sin vig: "
            f"{result['fresh_market_consensus_novig'] * 100:.2f}%"
        )
        print(
            f"   Edge vs consenso: "
            f"{result['fresh_edge_vs_consensus_pp']:+.2f} pp"
        )
        print(
            f"   Edge vs casa: "
            f"{result['fresh_edge_vs_target_pp']:+.2f} pp"
        )
        print(
            f"   EV individual: "
            f"{result['fresh_raw_ev_pct']:+.2f}%"
        )
        print(
            f"   Casas referencia: "
            f"{result['reference_books']}"
        )

    all_ok = (
        len(fresh_results) == 2
        and all(
            row.get("ok")
            for row in fresh_results
        )
    )

    confirmation = {
        "generated_at_utc": now_utc().isoformat(),
        "decision_age_minutes": round(
            decision_age,
            2,
        ),
        "bookmaker": bookmaker,
        "ratings_through": ratings_through,
        "status": "REJECTED",
        "legs": fresh_results,
        "api_cost": total_cost,
        "credits_remaining": remaining,
    }

    print()
    print("=" * 94)
    print("RESULTADO FINAL")
    print("=" * 94)

    if not all_ok:
        print()
        print(
            "⛔ NO BET — al menos una pierna "
            "ya no cumple los filtros frescos."
        )
        write_result(
            confirmation
        )

        print()
        print(
            f"Coste API de confirmación: "
            f"{total_cost}"
        )

        if remaining is not None:
            print(
                f"Créditos restantes: "
                f"{remaining}"
            )

        print(
            f"Resultado: {OUTPUT_FILE}"
        )
        return

    combined_odds = (
        fresh_results[0][
            "fresh_odds"
        ]
        * fresh_results[1][
            "fresh_odds"
        ]
    )

    combined_probability = (
        fresh_results[0][
            "model_probability"
        ]
        * fresh_results[1][
            "model_probability"
        ]
    )

    combined_ev_pct = (
        combined_probability
        * combined_odds
        - 1.0
    ) * 100.0

    if combined_odds < MIN_COMBINED_ODDS:
        print()
        print(
            f"⛔ NO BET — cuota combinada fresca "
            f"{combined_odds:.3f} < {MIN_COMBINED_ODDS:.2f}"
        )

        confirmation.update(
            {
                "reason": "COMBINED_ODDS_TOO_LOW",
                "combined_odds": combined_odds,
                "combined_probability_pct":
                    combined_probability * 100,
                "combined_ev_pct":
                    combined_ev_pct,
            }
        )

        write_result(
            confirmation
        )
        return

    if combined_ev_pct <= 0:
        print()
        print(
            "⛔ NO BET — EV combinado fresco "
            "ya no es positivo."
        )

        confirmation.update(
            {
                "reason": "COMBINED_EV_NOT_POSITIVE",
                "combined_odds": combined_odds,
                "combined_probability_pct":
                    combined_probability * 100,
                "combined_ev_pct":
                    combined_ev_pct,
            }
        )

        write_result(
            confirmation
        )
        return

    confirmation.update(
        {
            "status": "CONFIRMED",
            "combined_odds": round(
                combined_odds,
                4,
            ),
            "combined_probability_pct": round(
                combined_probability * 100,
                2,
            ),
            "combined_ev_pct": round(
                combined_ev_pct,
                2,
            ),
        }
    )

    write_result(
        confirmation
    )

    print()
    print("✅ PARLAY CONFIRMADO POR CULEBRIA")
    print()
    print(
        f"Casa: {bookmaker}"
    )

    for index, result in enumerate(
        fresh_results,
        start=1,
    ):
        print(
            f"{index}. {result['selection']} gana "
            f"@ {result['fresh_odds']:.3f}"
        )

    print()
    print(
        f"CUOTA COMBINADA FRESCA: "
        f"{combined_odds:.3f}"
    )
    print(
        f"Prob. combinada estimada: "
        f"{combined_probability * 100:.2f}%"
    )
    print(
        f"EV combinado estimado: "
        f"{combined_ev_pct:+.2f}%"
    )
    print()
    print(
        f"Coste API de confirmación: "
        f"{total_cost}"
    )

    if remaining is not None:
        print(
            f"Créditos restantes: "
            f"{remaining}"
        )

    print(
        f"Resultado: {OUTPUT_FILE}"
    )
    print()
    print(
        "⚠️ CONFIRMED significa que la selección sigue "
        "cumpliendo las reglas del modelo con cuotas frescas; "
        "no garantiza que vaya a ganar."
    )


if __name__ == "__main__":
    main()
