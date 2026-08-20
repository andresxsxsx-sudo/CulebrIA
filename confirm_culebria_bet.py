from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
import requests
from dotenv import load_dotenv

import culebria_operational as op


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

FINAL_FILE = DATA / "culebria_operational_final.json"
PREMATCH_FILE = DATA / "prematch_odds_candidates.csv"
OUTPUT_FILE = DATA / "culebria_bet_confirmation.json"

MAX_DECISION_AGE_MINUTES = 30


def parse_utc_datetime(value):
    if value is None:
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


def decision_age_minutes(value):
    dt = parse_utc_datetime(value)

    if dt is None:
        return None

    return (
        datetime.now(timezone.utc) - dt
    ).total_seconds() / 60


def fresh_fetch_event_odds(
    *,
    api_key,
    sport_key,
    event_id,
    markets,
):
    """
    Consulta FRESCA a The Odds API.
    No utiliza la caché de culebria_operational.py.
    """
    url = (
        f"{op.BASE_URL}/sports/{sport_key}"
        f"/events/{event_id}/odds"
    )

    response = requests.get(
        url,
        params={
            "apiKey": api_key,
            "regions": op.REGIONS,
            "markets": markets,
            "oddsFormat": op.ODDS_FORMAT,
            "dateFormat": op.DATE_FORMAT,
        },
        timeout=20,
    )

    response.raise_for_status()

    return {
        "payload": response.json(),
        "credits_last": response.headers.get(
            "x-requests-last"
        ),
        "credits_used": response.headers.get(
            "x-requests-used"
        ),
        "credits_remaining": response.headers.get(
            "x-requests-remaining"
        ),
    }


def find_sport_key(
    prematch_df,
    event_id,
):
    matches = prematch_df[
        prematch_df["event_id"]
        .astype(str)
        .str.strip()
        == str(event_id).strip()
    ]

    if matches.empty:
        return None

    value = str(
        matches.iloc[0]["sport_key"]
    ).strip()

    return value or None


def choose_same_bookmaker(
    evaluations,
    bookmaker_name,
):
    target = op.normalize_text(
        bookmaker_name
    )

    matches = [
        item
        for item in evaluations
        if op.normalize_text(
            item.get(
                "bookmaker",
                "",
            )
        )
        == target
    ]

    if not matches:
        return None

    return max(
        matches,
        key=lambda item: (
            float(item.get("odds", 0)),
            float(
                item.get(
                    "novig_edge",
                    -999,
                )
            ),
        ),
    )


def evaluate_leg_fresh(
    *,
    leg,
    bookmaker_name,
    sport_key,
    api_key,
):
    market = str(
        leg["market"]
    ).strip().upper()

    model_probability = (
        float(
            leg[
                "model_probability_pct"
            ]
        )
        / 100
    )

    if market in {
        "1X",
        "X2",
    }:
        requested_markets = (
            "double_chance,h2h"
        )
    elif market == "AWAY_SCORES":
        requested_markets = (
            "alternate_team_totals"
        )
    else:
        return {
            "ok": False,
            "reason":
                f"Mercado no soportado: {market}",
            "api_cost": 0,
        }

    fresh = fresh_fetch_event_odds(
        api_key=api_key,
        sport_key=sport_key,
        event_id=str(
            leg["event_id"]
        ).strip(),
        markets=requested_markets,
    )

    odds_data = fresh[
        "payload"
    ]

    home = str(
        odds_data.get(
            "home_team",
            leg["home"],
        )
        or leg["home"]
    )

    away = str(
        odds_data.get(
            "away_team",
            leg["away"],
        )
        or leg["away"]
    )

    if market == "1X":
        consensus = (
            op.evaluate_1x_cross_bookmakers(
                odds_data,
                model_probability,
                home,
                away,
            )
        )

    elif market == "X2":

        if not hasattr(
            op,
            "evaluate_x2_cross_bookmakers",
        ):
            return {
                "ok": False,
                "reason":
                    "Tu culebria_operational.py "
                    "no tiene instalada la función X2.",
                "api_cost": 0,
            }

        consensus = (
            op.evaluate_x2_cross_bookmakers(
                odds_data,
                model_probability,
                home,
                away,
            )
        )

    else:
        consensus = (
            op.evaluate_away_scores_cross_bookmakers(
                odds_data,
                model_probability,
                away,
            )
        )

    evaluation = (
        choose_same_bookmaker(
            consensus.get(
                "evaluations",
                [],
            ),
            bookmaker_name,
        )
    )

    try:
        api_cost = int(
            fresh.get(
                "credits_last"
            )
            or 0
        )
    except (
        TypeError,
        ValueError,
    ):
        api_cost = 0

    if evaluation is None:
        return {
            "ok": False,
            "reason":
                f"{bookmaker_name} no ofrece ahora "
                f"una cuota comparable para {market}.",
            "api_cost":
                api_cost,
            "credits_remaining":
                fresh.get(
                    "credits_remaining"
                ),
        }

    edge_pp = (
        float(
            evaluation[
                "novig_edge"
            ]
        )
        * 100
    )

    raw_ev = float(
        evaluation[
            "raw_ev"
        ]
    )

    approved = (
        raw_ev > 0
        and edge_pp
        >= op.MIN_NOVIG_EDGE_PP
    )

    return {
        "ok":
            approved,
        "reason":
            ""
            if approved
            else (
                "La cuota fresca ya no supera "
                "precio + no-vig."
            ),
        "market":
            market,
        "home":
            str(leg["home"]),
        "away":
            str(leg["away"]),
        "bookmaker":
            evaluation[
                "bookmaker"
            ],
        "odds":
            float(
                evaluation[
                    "odds"
                ]
            ),
        "model_probability":
            model_probability,
        "market_novig_probability":
            float(
                evaluation[
                    "market_novig_probability"
                ]
            ),
        "novig_edge":
            float(
                evaluation[
                    "novig_edge"
                ]
            ),
        "raw_ev":
            raw_ev,
        "last_update":
            str(
                evaluation.get(
                    "last_update",
                    "",
                )
            ),
        "api_cost":
            api_cost,
        "credits_remaining":
            fresh.get(
                "credits_remaining"
            ),
    }


def market_label(
    item,
):
    market = item[
        "market"
    ]

    if market == "1X":
        return (
            f"1X — {item['home']} "
            "gana o empata"
        )

    if market == "X2":
        return (
            f"X2 — {item['away']} "
            "gana o empata"
        )

    if market == "AWAY_SCORES":
        return (
            f"{item['away']} marca "
            "al menos 1 gol"
        )

    return market


def write_output(
    payload,
):
    OUTPUT_FILE.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main():
    print("=" * 88)
    print(
        "🐍 CULEBRIA — CONFIRMACIÓN FINAL DE APUESTA"
    )
    print("=" * 88)
    print()

    if not FINAL_FILE.exists():
        print(
            "⛔ NO CONFIRMAR — no existe "
            "culebria_operational_final.json."
        )
        return

    if not PREMATCH_FILE.exists():
        print(
            "⛔ NO CONFIRMAR — no existe "
            "prematch_odds_candidates.csv."
        )
        return

    final = json.loads(
        FINAL_FILE.read_text(
            encoding="utf-8"
        )
    )

    if (
        final.get(
            "decision"
        )
        != "PARLAY"
    ):
        print(
            "⛔ NO CONFIRMAR — la última decisión "
            "de CulebrIA no es PARLAY."
        )
        return

    generated_at = final.get(
        "generated_at_utc"
    )

    age_minutes = decision_age_minutes(
        generated_at
    )

    record_id = str(
        final.get(
            "prospective_record_id",
            "",
        )
        or ""
    ).strip()

    print(
        "Decisión operativa generada: "
        f"{generated_at or 'DESCONOCIDA'}"
    )

    if age_minutes is None:
        print(
            "⛔ NO CONFIRMAR — no pude validar "
            "la fecha/hora de la decisión."
        )
        print(
            "Ejecuta primero: python culebria.py"
        )
        return

    print(
        f"Antigüedad de la decisión: "
        f"{age_minutes:.1f} minutos"
    )

    if record_id:
        print(
            f"ID prospectivo del parlay: "
            f"{record_id}"
        )
    else:
        print(
            "ID prospectivo del parlay: NO DISPONIBLE"
        )

    if age_minutes < -2:
        print(
            "⛔ NO CONFIRMAR — la fecha de la decisión "
            "parece estar en el futuro."
        )
        print(
            "Revisa la hora del sistema y ejecuta "
            "de nuevo: python culebria.py"
        )
        return

    if age_minutes > MAX_DECISION_AGE_MINUTES:
        print()
        print("=" * 88)
        print("⛔ DECISIÓN DEMASIADO ANTIGUA")
        print("=" * 88)
        print(
            f"Máximo permitido: "
            f"{MAX_DECISION_AGE_MINUTES} minutos."
        )
        print(
            "No consultaré cuotas ni consumiré créditos."
        )
        print()
        print("Ejecuta primero:")
        print("  python culebria.py")
        print("y después:")
        print("  python confirm_culebria_bet.py")
        return

    legs = final.get(
        "legs",
        [],
    )

    if len(legs) != 2:
        print(
            "⛔ NO CONFIRMAR — la última decisión "
            "no contiene exactamente 2 piernas."
        )
        return

    event_ids = {
        str(
            leg.get(
                "event_id",
                "",
            )
        ).strip()
        for leg in legs
    }

    if len(event_ids) != 2:
        print(
            "⛔ NO CONFIRMAR — las dos piernas "
            "no pertenecen a partidos distintos."
        )
        return

    bookmaker = str(
        final.get(
            "bookmaker",
            "",
        )
    ).strip()

    if not bookmaker:
        print(
            "⛔ NO CONFIRMAR — no se encontró "
            "la casa de apuestas."
        )
        return

    prematch_df = pd.read_csv(
        PREMATCH_FILE
    )

    load_dotenv(
        ROOT / ".env"
    )

    api_key = os.getenv(
        "THE_ODDS_API_KEY"
    )

    if not api_key:
        print(
            "⛔ NO CONFIRMAR — "
            "THE_ODDS_API_KEY no está en .env."
        )
        return

    print()
    print(
        f"Casa que debe mantenerse: {bookmaker}"
    )
    print(
        "Parlay que se va a confirmar:"
    )

    for number, leg in enumerate(
        legs,
        start=1,
    ):
        print(
            f"  {number}. "
            f"{leg['home']} vs {leg['away']} "
            f"| {leg['market']} "
            f"| cuota anterior {leg.get('odds', '?')}"
        )

    print()
    print(
        "Consultando cuotas frescas SOLO "
        "para estos 2 partidos..."
    )
    print()

    confirmed = []
    total_cost = 0
    last_remaining = None

    for number, leg in enumerate(
        legs,
        start=1,
    ):
        event_id = str(
            leg["event_id"]
        ).strip()

        sport_key = find_sport_key(
            prematch_df,
            event_id,
        )

        if sport_key is None:
            print(
                f"⛔ Pierna {number}: "
                "no pude recuperar sport_key."
            )
            return

        try:
            result = evaluate_leg_fresh(
                leg=leg,
                bookmaker_name=
                    bookmaker,
                sport_key=
                    sport_key,
                api_key=
                    api_key,
            )
        except requests.RequestException as exc:
            print(
                f"⛔ Pierna {number}: "
                "error consultando cuotas frescas."
            )
            print(exc)
            return

        total_cost += int(
            result.get(
                "api_cost",
                0,
            )
            or 0
        )

        if result.get(
            "credits_remaining"
        ) is not None:
            last_remaining = (
                result[
                    "credits_remaining"
                ]
            )

        print("-" * 88)
        print(
            f"{number}. "
            f"{leg['home']} vs "
            f"{leg['away']}"
        )
        print(
            f"Mercado: {leg['market']}"
        )

        if not result[
            "ok"
        ]:
            print(
                "⛔ NO CONFIRMADA"
            )
            print(
                f"Motivo: "
                f"{result['reason']}"
            )

            write_output(
                {
                    "decision":
                        "DO_NOT_BET",
                    "reason":
                        result[
                            "reason"
                        ],
                    "failed_leg":
                        number,
                    "bookmaker":
                        bookmaker,
                    "api_cost":
                        total_cost,
                }
            )

            print()
            print("=" * 88)
            print(
                "⛔ NO APOSTAR"
            )
            print("=" * 88)
            print(
                "Al menos una pierna ya no cumple "
                "las condiciones de CulebrIA."
            )
            return

        print(
            "✅ CONFIRMADA"
        )
        print(
            f"Selección: "
            f"{market_label(result)}"
        )
        print(
            f"Cuota fresca: "
            f"{result['odds']:.3f}"
        )
        print(
            "Prob. mercado sin vig: "
            f"{result['market_novig_probability'] * 100:.2f}%"
        )
        print(
            "Edge sin vig: "
            f"{result['novig_edge'] * 100:+.2f} pp"
        )
        print(
            "EV bruto: "
            f"{result['raw_ev'] * 100:+.2f}%"
        )

        confirmed.append(
            result
        )

    combined_odds = (
        confirmed[0]["odds"]
        * confirmed[1]["odds"]
    )

    combined_model_probability = (
        confirmed[0][
            "model_probability"
        ]
        * confirmed[1][
            "model_probability"
        ]
    )

    combined_ev = (
        combined_model_probability
        * combined_odds
        - 1
    )

    print()
    print("=" * 88)

    if (
        combined_odds
        < op.MIN_COMBINED_ODDS
        or combined_ev <= 0
    ):
        print(
            "⛔ NO APOSTAR"
        )
        print("=" * 88)
        print(
            f"Cuota combinada fresca: "
            f"{combined_odds:.3f}"
        )
        print(
            f"Mínimo exigido: "
            f"{op.MIN_COMBINED_ODDS:.2f}"
        )
        print(
            f"EV combinado fresco: "
            f"{combined_ev * 100:+.2f}%"
        )

        write_output(
            {
                "decision":
                    "DO_NOT_BET",
                "bookmaker":
                    bookmaker,
                "combined_odds":
                    round(
                        combined_odds,
                        4,
                    ),
                "combined_ev_pct":
                    round(
                        combined_ev * 100,
                        2,
                    ),
                "api_cost":
                    total_cost,
                "legs":
                    confirmed,
            }
        )

        return

    print(
        "✅ APUESTA CONFIRMADA"
    )
    print("=" * 88)
    print()
    print(
        f"Casa: {bookmaker}"
    )

    for number, item in enumerate(
        confirmed,
        start=1,
    ):
        print(
            f"{number}. "
            f"{item['home']} vs "
            f"{item['away']}"
        )
        print(
            f"   {market_label(item)}"
        )
        print(
            f"   Cuota fresca: "
            f"{item['odds']:.3f}"
        )

    print()
    print(
        f"CUOTA COMBINADA FRESCA: "
        f"{combined_odds:.3f}"
    )
    print(
        f"EV combinado estimado: "
        f"{combined_ev * 100:+.2f}%"
    )
    print()
    print(
        f"Coste API de confirmación: "
        f"{total_cost}"
    )

    if last_remaining is not None:
        print(
            f"Créditos restantes: "
            f"{last_remaining}"
        )

    write_output(
        {
            "decision":
                "BET_CONFIRMED",
            "bookmaker":
                bookmaker,
            "combined_odds":
                round(
                    combined_odds,
                    4,
                ),
            "combined_ev_pct":
                round(
                    combined_ev * 100,
                    2,
                ),
            "api_cost":
                total_cost,
            "legs":
                confirmed,
        }
    )

    print()
    print(
        f"Reporte: {OUTPUT_FILE}"
    )
    print()
    print(
        "⚠️ La confirmación verifica las condiciones "
        "del modelo y las cuotas actuales; no garantiza "
        "que la apuesta resulte ganadora."
    )


if __name__ == "__main__":
    main()
