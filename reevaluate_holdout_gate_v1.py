from pathlib import Path

import pandas as pd

from build_reliability_gate import (
    find_calibration_bin,
    classify_signal
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"

PREDICTIONS_FILE = (
    DATA_DIR
    / "backtest_poisson_predictions.csv"
)

DEVELOPMENT_METRICS_FILE = (
    DATA_DIR
    / "backtest_market_metrics.csv"
)

DEVELOPMENT_CALIBRATION_FILE = (
    DATA_DIR
    / "backtest_calibration.csv"
)

OUTPUT_SIGNALS = (
    DATA_DIR
    / "holdout_v1_gate_signals_corrected.csv"
)

OUTPUT_SUMMARY = (
    DATA_DIR
    / "holdout_v1_gate_summary_corrected.csv"
)


# ============================================================
# COLUMNAS CORRECTAS DEL BACKTEST
# ============================================================

PROBABILITY_COLUMNS = {
    "HOME_WIN":
        "p_home_win",

    "DRAW":
        "p_draw",

    "AWAY_WIN":
        "p_away_win",

    "1X":
        "p_home_or_draw",

    "X2":
        "p_away_or_draw",

    "OVER_1_5":
        "p_over15",

    "OVER_2_5":
        "p_over25",

    "UNDER_3_5":
        "p_under35",

    "BTTS":
        "p_btts",

    "HOME_SCORES":
        "p_home_scores",

    "AWAY_SCORES":
        "p_away_scores",
}


ACTUAL_COLUMNS = {
    "HOME_WIN":
        "y_home_win",

    "DRAW":
        "y_draw",

    "AWAY_WIN":
        "y_away_win",

    "1X":
        "y_home_or_draw",

    "X2":
        "y_away_or_draw",

    "OVER_1_5":
        "y_over15",

    "OVER_2_5":
        "y_over25",

    "UNDER_3_5":
        "y_under35",

    "BTTS":
        "y_btts",

    "HOME_SCORES":
        "y_home_scores",

    "AWAY_SCORES":
        "y_away_scores",
}


# ============================================================
# CRITERIOS DEFINIDOS ANTES DE ABRIR EL HOLDOUT
# ============================================================

MIN_GATE_HOLDOUT_N = 20
MIN_GATE_ACTUAL_RATE = 0.70
MAX_GATE_CALIBRATION_GAP = 0.05


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    print("=" * 84)
    print(
        "CulebrIA - REEVALUACION CORREGIDA "
        "DEL RELIABILITY GATE V1"
    )
    print("=" * 84)

    # --------------------------------------------------------
    # CARGAR DATOS
    # --------------------------------------------------------

    predictions = pd.read_csv(
        PREDICTIONS_FILE
    )

    metrics = pd.read_csv(
        DEVELOPMENT_METRICS_FILE
    )

    calibration = pd.read_csv(
        DEVELOPMENT_CALIBRATION_FILE
    )

    holdout = predictions[
        predictions[
            "split"
        ] == "HOLDOUT"
    ].copy()

    metrics_index = (
        metrics
        .set_index(
            "market"
        )
    )

    print()
    print(
        f"Partidos HOLDOUT: "
        f"{len(holdout)}"
    )

    # ========================================================
    # VERIFICAR ESCALA
    # ========================================================

    probability_columns = list(
        PROBABILITY_COLUMNS.values()
    )

    minimum_probability = (
        holdout[
            probability_columns
        ]
        .min()
        .min()
    )

    maximum_probability = (
        holdout[
            probability_columns
        ]
        .max()
        .max()
    )

    print()
    print(
        "Rango de probabilidades "
        "en el backtest:"
    )

    print(
        f"Mínimo: "
        f"{minimum_probability:.6f}"
    )

    print(
        f"Máximo: "
        f"{maximum_probability:.6f}"
    )

    if (
        minimum_probability >= 0
        and
        maximum_probability <= 1
    ):

        print(
            "✅ Escala confirmada: 0–1."
        )

    else:

        print(
            "❌ Escala inesperada."
        )

        print(
            "No se continuará."
        )

        return

    # ========================================================
    # APLICAR EL GATE
    # ========================================================

    rows = []

    for _, prediction in (
        holdout.iterrows()
    ):

        for (
            market,
            probability_column
        ) in PROBABILITY_COLUMNS.items():

            actual_column = (
                ACTUAL_COLUMNS[
                    market
                ]
            )

            if (
                market
                not in metrics_index.index
            ):
                continue

            # ------------------------------------------------
            # BACKTEST GUARDA 0–1
            # ------------------------------------------------

            probability = float(
                prediction[
                    probability_column
                ]
            )

            probability_pct = (
                probability
                * 100
            )

            actual = int(
                prediction[
                    actual_column
                ]
            )

            # ------------------------------------------------
            # MÉTRICAS DE DEVELOPMENT
            # ------------------------------------------------

            metric = metrics_index.loc[
                market
            ]

            market_skill = float(
                metric[
                    "brier_skill"
                ]
            )

            market_ece = float(
                metric[
                    "ece"
                ]
            )

            # ------------------------------------------------
            # BIN APRENDIDO EN DEVELOPMENT
            # ------------------------------------------------

            calibration_bin = (
                find_calibration_bin(
                    calibration_df=
                        calibration,

                    market=
                        market,

                    probability_pct=
                        probability_pct
                )
            )

            # ------------------------------------------------
            # MISMO GATE QUE YA HABÍAMOS DEFINIDO
            # ------------------------------------------------

            result = classify_signal(
                probability_pct=
                    probability_pct,

                market_skill=
                    market_skill,

                market_ece=
                    market_ece,

                calibration_bin=
                    calibration_bin
            )

            if not result[
                "low_volatility"
            ]:
                continue

            rows.append(
                {
                    "competition":
                        prediction[
                            "competition"
                        ],

                    "match_id":
                        prediction[
                            "match_id"
                        ],

                    "kickoff":
                        prediction[
                            "kickoff"
                        ],

                    "home":
                        prediction[
                            "home"
                        ],

                    "away":
                        prediction[
                            "away"
                        ],

                    "market":
                        market,

                    "grade":
                        result[
                            "grade"
                        ],

                    "model_probability":
                        probability,

                    "model_probability_pct":
                        probability_pct,

                    "actual":
                        actual,

                    "development_bin_n":
                        result[
                            "bin_n"
                        ],

                    "development_bin_prediction_pct":
                        result[
                            "bin_prediction_pct"
                        ],

                    "development_bin_actual_pct":
                        result[
                            "bin_actual_pct"
                        ],

                    "development_bin_gap_pct":
                        result[
                            "bin_gap_pct"
                        ],
                }
            )

    gate_df = pd.DataFrame(
        rows
    )

    gate_df.to_csv(
        OUTPUT_SIGNALS,
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # SI NO HAY SEÑALES
    # ========================================================

    if gate_df.empty:

        print()
        print(
            "No se generaron señales."
        )

        print()
        print(
            "ESTADO: INCONCLUSO"
        )

        return

    # ========================================================
    # RESUMEN TOTAL
    # ========================================================

    average_prediction = (
        gate_df[
            "model_probability"
        ].mean()
    )

    actual_rate = (
        gate_df[
            "actual"
        ].mean()
    )

    calibration_gap = abs(
        average_prediction
        - actual_rate
    )

    print()
    print("=" * 84)
    print(
        "RELIABILITY GATE - HOLDOUT CORREGIDO"
    )
    print("=" * 84)

    print()

    print(
        f"Señales: "
        f"{len(gate_df)}"
    )

    print(
        f"Probabilidad media modelo: "
        f"{average_prediction * 100:.2f}%"
    )

    print(
        f"Frecuencia real: "
        f"{actual_rate * 100:.2f}%"
    )

    print(
        f"Gap calibración: "
        f"{calibration_gap * 100:.2f} pp"
    )

    # ========================================================
    # RESUMEN POR MERCADO
    # ========================================================

    summary_rows = []

    print()
    print("=" * 84)
    print(
        "RESULTADO POR MERCADO"
    )
    print("=" * 84)

    print()

    for market in sorted(
        gate_df[
            "market"
        ].unique()
    ):

        market_df = gate_df[
            gate_df[
                "market"
            ] == market
        ]

        n = len(
            market_df
        )

        predicted = (
            market_df[
                "model_probability"
            ].mean()
        )

        real = (
            market_df[
                "actual"
            ].mean()
        )

        gap = abs(
            predicted
            - real
        )

        summary_rows.append(
            {
                "market":
                    market,

                "n":
                    n,

                "average_prediction_pct":
                    predicted * 100,

                "actual_rate_pct":
                    real * 100,

                "calibration_gap_pct":
                    gap * 100,
            }
        )

        print(
            f"{market:<15}"
            f"N={n:<4}"
            f"Pred={predicted * 100:>7.2f}%   "
            f"Real={real * 100:>7.2f}%   "
            f"Gap={gap * 100:>6.2f} pp"
        )

    summary_df = pd.DataFrame(
        summary_rows
    )

    summary_df.to_csv(
        OUTPUT_SUMMARY,
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # CRITERIO ORIGINAL
    # ========================================================

    if (
        len(gate_df)
        < MIN_GATE_HOLDOUT_N
    ):

        status = (
            "INCONCLUSO_MUESTRA_BAJA"
        )

    elif (
        actual_rate
        >= MIN_GATE_ACTUAL_RATE
        and
        calibration_gap
        <= MAX_GATE_CALIBRATION_GAP
    ):

        status = (
            "APROBADO"
        )

    else:

        status = (
            "NO_APROBADO"
        )

    # ========================================================
    # RESULTADO
    # ========================================================

    print()
    print("=" * 84)
    print(
        "VEREDICTO DEL GATE"
    )
    print("=" * 84)

    print()

    print(
        f"N mínimo requerido: "
        f"{MIN_GATE_HOLDOUT_N}"
    )

    print(
        f"Frecuencia real mínima: "
        f"{MIN_GATE_ACTUAL_RATE * 100:.2f}%"
    )

    print(
        f"Gap máximo permitido: "
        f"{MAX_GATE_CALIBRATION_GAP * 100:.2f} pp"
    )

    print()

    print(
        f"ESTADO RELIABILITY GATE: "
        f"{status}"
    )

    print()
    print(
        "IMPORTANTE:"
    )

    print(
        "Este resultado corrige únicamente "
        "el Reliability Gate."
    )

    print(
        "El resultado global 1X2 del HOLDOUT "
        "permanece sin cambios."
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
        "Archivos:"
    )

    print(
        OUTPUT_SIGNALS
    )

    print(
        OUTPUT_SUMMARY
    )


if __name__ == "__main__":
    main()