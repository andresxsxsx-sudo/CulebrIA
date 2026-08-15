import json
import math
import unicodedata
from pathlib import Path

import pandas as pd


# ============================================================
# CONFIGURACIÓN
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"

CANDIDATES_FILE = (
    DATA_DIR
    / "prematch_odds_candidates.csv"
)

ODDS_RAW_DIR = (
    DATA_DIR
    / "odds_raw"
)

OUTPUT_FILE = (
    DATA_DIR
    / "single_value_evaluation.csv"
)


# ============================================================
# UTILIDADES
# ============================================================

def normalize_text(value):

    text = str(
        value
    ).strip().lower()

    text = unicodedata.normalize(
        "NFKD",
        text
    )

    text = "".join(
        char
        for char in text
        if not unicodedata.combining(
            char
        )
    )

    return " ".join(
        text.split()
    )


def fair_odds(probability):

    if probability <= 0:
        return None

    return 1 / probability


def implied_probability(decimal_odds):

    if decimal_odds <= 0:
        return None

    return 1 / decimal_odds


def expected_value(
    model_probability,
    decimal_odds
):

    return (
        model_probability
        * decimal_odds
        - 1
    )


# ============================================================
# IDENTIFICAR OUTCOME
# ============================================================

def is_target_outcome(
    outcome_name,
    signal_market,
    event_home,
    event_away
):

    outcome = normalize_text(
        outcome_name
    )

    home = normalize_text(
        event_home
    )

    away = normalize_text(
        event_away
    )

    signal_market = str(
        signal_market
    ).strip().upper()

    # --------------------------------------------------------
    # 1X
    # --------------------------------------------------------

    if signal_market == "1X":

        return (
            home in outcome
            and
            "draw" in outcome
        )

    # --------------------------------------------------------
    # X2
    # --------------------------------------------------------

    if signal_market == "X2":

        return (
            away in outcome
            and
            "draw" in outcome
        )

    return False


# ============================================================
# CARGAR JSON DE CUOTAS
# ============================================================

def load_odds_json(
    event_id,
    api_market
):

    file_path = (
        ODDS_RAW_DIR
        / f"{event_id}_{api_market}.json"
    )

    if not file_path.exists():

        raise RuntimeError(
            f"No existe el archivo: "
            f"{file_path}"
        )

    with open(
        file_path,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(
            file
        )


# ============================================================
# EXTRAER PRECIOS
# ============================================================

def extract_prices(
    data,
    signal_market,
    api_market
):

    event_home = data.get(
        "home_team",
        ""
    )

    event_away = data.get(
        "away_team",
        ""
    )

    prices = []

    bookmakers = data.get(
        "bookmakers",
        []
    )

    for bookmaker in bookmakers:

        bookmaker_name = (
            bookmaker.get(
                "title",
                "?"
            )
        )

        bookmaker_key = (
            bookmaker.get(
                "key",
                ""
            )
        )

        for market in bookmaker.get(
            "markets",
            []
        ):

            if (
                market.get("key")
                != api_market
            ):
                continue

            for outcome in market.get(
                "outcomes",
                []
            ):

                outcome_name = (
                    outcome.get(
                        "name",
                        ""
                    )
                )

                if not is_target_outcome(
                    outcome_name=
                        outcome_name,

                    signal_market=
                        signal_market,

                    event_home=
                        event_home,

                    event_away=
                        event_away
                ):
                    continue

                try:

                    price = float(
                        outcome[
                            "price"
                        ]
                    )

                except (
                    KeyError,
                    TypeError,
                    ValueError
                ):

                    continue

                prices.append(
                    {
                        "bookmaker":
                            bookmaker_name,

                        "bookmaker_key":
                            bookmaker_key,

                        "outcome":
                            outcome_name,

                        "price":
                            price,

                        "last_update":
                            market.get(
                                "last_update",
                                ""
                            ),
                    }
                )

    return prices


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    print("=" * 80)
    print(
        "CulebrIA - PRIMER VALUE CHECK"
    )
    print("=" * 80)

    candidates = pd.read_csv(
        CANDIDATES_FILE
    )

    prematch = candidates[
        candidates[
            "timing_status"
        ] == "PREMATCH"
    ].copy()

    if prematch.empty:

        print()
        print(
            "No hay candidatos PREMATCH."
        )

        return

    # --------------------------------------------------------
    # ESTA PRUEBA TRABAJA CON EL PRIMER CANDIDATO
    # --------------------------------------------------------

    candidate = (
        prematch.iloc[0]
    )

    home = str(
        candidate[
            "home"
        ]
    )

    away = str(
        candidate[
            "away"
        ]
    )

    event_id = str(
        candidate[
            "event_id"
        ]
    )

    signal_market = str(
        candidate[
            "signal_market"
        ]
    ).strip().upper()

    probability_pct = float(
        candidate[
            "model_probability_pct"
        ]
    )

    model_probability = (
        probability_pct
        / 100
    )

    # --------------------------------------------------------
    # MAPEO DE MERCADO
    # --------------------------------------------------------

    if signal_market in {
        "1X",
        "X2"
    }:

        api_market = (
            "double_chance"
        )

    elif signal_market == "AWAY_SCORES":

        api_market = (
            "team_totals"
        )

    else:

        print()
        print(
            f"❌ Mercado todavía "
            f"no soportado: "
            f"{signal_market}"
        )

        return

    # --------------------------------------------------------
    # AWAY_SCORES SE IMPLEMENTARÁ CUANDO
    # TENGAMOS UN JSON REAL DE TEAM_TOTALS.
    # --------------------------------------------------------

    if signal_market == "AWAY_SCORES":

        print()
        print(
            "⚠️ AWAY_SCORES todavía "
            "no se evaluará automáticamente."
        )

        print(
            "Primero necesitamos inspeccionar "
            "un JSON real de team_totals."
        )

        return

    # --------------------------------------------------------
    # LEER CUOTAS
    # --------------------------------------------------------

    data = load_odds_json(
        event_id=
            event_id,

        api_market=
            api_market
    )

    prices = extract_prices(
        data=
            data,

        signal_market=
            signal_market,

        api_market=
            api_market
    )

    print()
    print(
        f"Partido: "
        f"{home} vs {away}"
    )

    print(
        f"Mercado: "
        f"{signal_market}"
    )

    print(
        f"Probabilidad CulebrIA: "
        f"{probability_pct:.2f}%"
    )

    model_fair_odds = (
        fair_odds(
            model_probability
        )
    )

    print(
        f"Cuota justa CulebrIA: "
        f"{model_fair_odds:.3f}"
    )

    if not prices:

        print()
        print(
            "❌ No se encontró "
            "ninguna cuota correspondiente."
        )

        return

    # ========================================================
    # EVALUAR CADA BOOKMAKER
    # ========================================================

    evaluations = []

    print()
    print("=" * 80)
    print(
        "BOOKMAKERS"
    )
    print("=" * 80)

    for item in prices:

        price = item[
            "price"
        ]

        implied = (
            implied_probability(
                price
            )
        )

        ev = expected_value(
            model_probability=
                model_probability,

            decimal_odds=
                price
        )

        edge = (
            model_probability
            - implied
        )

        evaluations.append(
            {
                **item,

                "implied_probability":
                    implied,

                "edge":
                    edge,

                "ev":
                    ev,
            }
        )

        print()

        print(
            f"{item['bookmaker']}"
        )

        print(
            f"Cuota: "
            f"{price:.3f}"
        )

        print(
            f"Break-even: "
            f"{implied * 100:.2f}%"
        )

        print(
            f"Edge bruto: "
            f"{edge * 100:+.2f} pp"
        )

        print(
            f"EV: "
            f"{ev * 100:+.2f}%"
        )

    # ========================================================
    # MEJOR PRECIO
    # ========================================================

    best = max(
        evaluations,
        key=lambda item:
            item[
                "price"
            ]
    )

    best_price = (
        best[
            "price"
        ]
    )

    best_ev = (
        best[
            "ev"
        ]
    )

    best_edge = (
        best[
            "edge"
        ]
    )

    best_implied = (
        best[
            "implied_probability"
        ]
    )

    # ========================================================
    # CLASIFICACIÓN
    # ========================================================

    if best_ev <= 0:

        status = (
            "NO_BET_PRICE"
        )

        explanation = (
            "La mejor cuota disponible "
            "no supera la cuota justa "
            "del modelo."
        )

    else:

        status = (
            "POSITIVE_EV_UNFILTERED"
        )

        explanation = (
            "Existe EV bruto positivo, "
            "pero todavía requiere "
            "validación contra el mercado "
            "sin vig antes de considerarse "
            "candidato final."
        )

    # ========================================================
    # TERMINAL
    # ========================================================

    print()
    print("=" * 80)
    print(
        "MEJOR PRECIO"
    )
    print("=" * 80)

    print()

    print(
        f"Bookmaker: "
        f"{best['bookmaker']}"
    )

    print(
        f"Cuota: "
        f"{best_price:.3f}"
    )

    print(
        f"Probabilidad CulebrIA: "
        f"{model_probability * 100:.2f}%"
    )

    print(
        f"Break-even mercado: "
        f"{best_implied * 100:.2f}%"
    )

    print(
        f"Cuota justa CulebrIA: "
        f"{model_fair_odds:.3f}"
    )

    print(
        f"Edge bruto: "
        f"{best_edge * 100:+.2f} pp"
    )

    print(
        f"EV: "
        f"{best_ev * 100:+.2f}%"
    )

    print()

    print(
        f"ESTADO: "
        f"{status}"
    )

    print(
        explanation
    )

    # ========================================================
    # GUARDAR
    # ========================================================

    output = pd.DataFrame(
        [
            {
                "fixture_id":
                    candidate[
                        "fixture_id"
                    ],

                "event_id":
                    event_id,

                "home":
                    home,

                "away":
                    away,

                "market":
                    signal_market,

                "model_probability_pct":
                    probability_pct,

                "model_fair_odds":
                    model_fair_odds,

                "best_bookmaker":
                    best[
                        "bookmaker"
                    ],

                "best_odds":
                    best_price,

                "break_even_pct":
                    best_implied
                    * 100,

                "raw_edge_pp":
                    best_edge
                    * 100,

                "ev_pct":
                    best_ev
                    * 100,

                "status":
                    status,
            }
        ]
    )

    output.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    print()
    print(
        "Informe:"
    )

    print(
        OUTPUT_FILE
    )

    print()

    print(
        "Solicitudes API realizadas: 0"
    )


if __name__ == "__main__":
    main()