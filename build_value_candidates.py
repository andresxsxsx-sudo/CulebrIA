import json

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.analysis.value_engine import (
    evaluate_value_candidate,
    get_api_market
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"

INPUT_FILE = (
    DATA_DIR
    / "prematch_odds_candidates.csv"
)

ODDS_RAW_DIR = (
    DATA_DIR
    / "odds_raw"
)

OUTPUT_FILE = (
    DATA_DIR
    / "value_candidates.csv"
)


# ============================================================
# FECHAS
# ============================================================

def parse_datetime(value):

    if (
        value is None
        or pd.isna(value)
        or str(value).strip() == ""
    ):
        return None

    try:

        return datetime.fromisoformat(
            str(value).replace(
                "Z",
                "+00:00"
            )
        )

    except ValueError:

        return None


# ============================================================
# LOCALIZAR JSON DE CUOTAS
# ============================================================

def find_odds_file(
    event_id,
    api_market
):

    return (
        ODDS_RAW_DIR
        / (
            f"{event_id}_"
            f"{api_market}.json"
        )
    )


# ============================================================
# LEER JSON
# ============================================================

def load_odds_file(
    file_path
):

    with open(
        file_path,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(
            file
        )


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    print("=" * 82)
    print(
        "CulebrIA - VALUE ENGINE"
    )
    print("=" * 82)

    df = pd.read_csv(
        INPUT_FILE
    )

    print()
    print(
        f"Señales guardadas: "
        f"{len(df)}"
    )

    now = datetime.now(
        timezone.utc
    )

    rows = []

    # ========================================================
    # PROCESAR SEÑALES
    # ========================================================

    for _, candidate in df.iterrows():

        fixture_id = int(
            candidate[
                "fixture_id"
            ]
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

        signal_market = str(
            candidate[
                "signal_market"
            ]
        ).strip().upper()

        model_probability_pct = float(
            candidate[
                "model_probability_pct"
            ]
        )

        event_id = str(
            candidate[
                "event_id"
            ]
        )

        commence_time = parse_datetime(
            candidate[
                "commence_time"
            ]
        )

        api_market = get_api_market(
            signal_market
        )

        # ----------------------------------------------------
        # COMPROBAR TIEMPO ACTUAL
        # ----------------------------------------------------

        if commence_time is None:

            status = (
                "INVALID_DATE"
            )

            reason = (
                "Fecha de inicio inválida."
            )

            minutes_to_start = None

            result = None

        else:

            minutes_to_start = (
                commence_time
                - now
            ).total_seconds() / 60

            if minutes_to_start <= 0:

                status = (
                    "STARTED"
                )

                reason = (
                    "El evento ya comenzó. "
                    "No se usarán cuotas live."
                )

                result = None

            elif api_market is None:

                status = (
                    "BLOCKED_MARKET"
                )

                reason = (
                    "No existe mapeo para "
                    "este mercado."
                )

                result = None

            else:

                odds_file = find_odds_file(
                    event_id=
                        event_id,

                    api_market=
                        api_market
                )

                # --------------------------------------------
                # TODAVÍA NO TENEMOS JSON
                # --------------------------------------------

                if not odds_file.exists():

                    if (
                        signal_market
                        == "AWAY_SCORES"
                    ):

                        status = (
                            "NEEDS_MARKET_STRUCTURE"
                        )

                        reason = (
                            "Falta obtener e inspeccionar "
                            "team_totals."
                        )

                    else:

                        status = (
                            "NO_ODDS_FILE"
                        )

                        reason = (
                            "Todavía no existe un JSON "
                            "de cuotas guardado."
                        )

                    result = None

                # --------------------------------------------
                # EVALUAR
                # --------------------------------------------

                else:

                    odds_data = (
                        load_odds_file(
                            odds_file
                        )
                    )

                    result = (
                        evaluate_value_candidate(
                            signal_market=
                                signal_market,

                            model_probability_pct=
                                model_probability_pct,

                            odds_data=
                                odds_data
                        )
                    )

                    status = result[
                        "status"
                    ]

                    reason = result[
                        "reason"
                    ]

        # ====================================================
        # CONSTRUIR FILA
        # ====================================================

        output_row = {
            "fixture_id":
                fixture_id,

            "competition":
                candidate[
                    "competition"
                ],

            "event_id":
                event_id,

            "home":
                home,

            "away":
                away,

            "market":
                signal_market,

            "grade":
                candidate[
                    "grade"
                ],

            "model_probability_pct":
                round(
                    model_probability_pct,
                    2
                ),

            "api_market":
                api_market,

            "commence_time":
                candidate[
                    "commence_time"
                ],

            "minutes_to_start":
                (
                    round(
                        minutes_to_start,
                        1
                    )
                    if minutes_to_start
                    is not None
                    else None
                ),

            "status":
                status,

            "reason":
                reason,

            "best_bookmaker":
                None,

            "best_odds":
                None,

            "model_fair_odds":
                None,

            "break_even_pct":
                None,

            "raw_edge_pp":
                None,

            "raw_ev_pct":
                None,

            "odds_last_update":
                None,
        }

        # ----------------------------------------------------
        # SI HUBO EVALUACIÓN COMPLETA
        # ----------------------------------------------------

        if (
            result is not None
        ):

            model_fair_odds = result.get(
                "model_fair_odds"
            )

            output_row[
                "model_fair_odds"
            ] = (
                round(
                    model_fair_odds,
                    3
                )
                if model_fair_odds
                is not None
                else None
            )

            if result.get(
                "best_odds"
            ) is not None:

                output_row[
                    "best_bookmaker"
                ] = result.get(
                    "best_bookmaker"
                )

                output_row[
                    "best_odds"
                ] = round(
                    result[
                        "best_odds"
                    ],
                    3
                )

                output_row[
                    "break_even_pct"
                ] = round(
                    result[
                        "break_even_probability"
                    ]
                    * 100,
                    2
                )

                output_row[
                    "raw_edge_pp"
                ] = round(
                    result[
                        "raw_edge"
                    ]
                    * 100,
                    2
                )

                output_row[
                    "raw_ev_pct"
                ] = round(
                    result[
                        "raw_ev"
                    ]
                    * 100,
                    2
                )

                output_row[
                    "odds_last_update"
                ] = result.get(
                    "last_update"
                )

        rows.append(
            output_row
        )

        # ====================================================
        # TERMINAL
        # ====================================================

        print()
        print("-" * 82)

        print(
            f"{home} vs {away}"
        )

        print(
            f"Mercado: "
            f"{signal_market}"
        )

        print(
            f"Probabilidad CulebrIA: "
            f"{model_probability_pct:.2f}%"
        )

        print(
            f"Estado: "
            f"{status}"
        )

        if (
            output_row[
                "best_odds"
            ]
            is not None
        ):

            print(
                f"Mejor bookmaker: "
                f"{output_row['best_bookmaker']}"
            )

            print(
                f"Mejor cuota: "
                f"{output_row['best_odds']}"
            )

            print(
                f"Cuota justa modelo: "
                f"{output_row['model_fair_odds']}"
            )

            print(
                f"Break-even: "
                f"{output_row['break_even_pct']}%"
            )

            print(
                f"Edge bruto: "
                f"{output_row['raw_edge_pp']:+.2f} pp"
            )

            print(
                f"EV bruto: "
                f"{output_row['raw_ev_pct']:+.2f}%"
            )

        print(
            f"Motivo: "
            f"{reason}"
        )

    # ========================================================
    # GUARDAR
    # ========================================================

    output_df = pd.DataFrame(
        rows
    )

    output_df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # CONTADORES
    # ========================================================

    no_bet = int(
        (
            output_df[
                "status"
            ]
            == "NO_BET_PRICE"
        ).sum()
    )

    needs_vig = int(
        (
            output_df[
                "status"
            ]
            == "NEEDS_VIG_CHECK"
        ).sum()
    )

    started = int(
        (
            output_df[
                "status"
            ]
            == "STARTED"
        ).sum()
    )

    needs_structure = int(
        (
            output_df[
                "status"
            ]
            == "NEEDS_MARKET_STRUCTURE"
        ).sum()
    )

    no_odds = int(
        (
            output_df[
                "status"
            ]
            == "NO_ODDS_FILE"
        ).sum()
    )

    # ========================================================
    # RESUMEN
    # ========================================================

    print()
    print("=" * 82)
    print(
        "RESULTADO FINAL"
    )
    print("=" * 82)

    print()

    print(
        f"Señales procesadas: "
        f"{len(output_df)}"
    )

    print(
        f"NO BET por precio: "
        f"{no_bet}"
    )

    print(
        f"EV positivo pendiente de vig: "
        f"{needs_vig}"
    )

    print(
        f"Ya iniciadas: "
        f"{started}"
    )

    print(
        f"Mercado pendiente de estructura: "
        f"{needs_structure}"
    )

    print(
        f"Sin archivo de cuotas: "
        f"{no_odds}"
    )

    print()

    print(
        "Solicitudes API realizadas: 0"
    )

    print(
        "Créditos utilizados: 0"
    )

    print()

    print(
        "Informe:"
    )

    print(
        OUTPUT_FILE
    )


if __name__ == "__main__":
    main()