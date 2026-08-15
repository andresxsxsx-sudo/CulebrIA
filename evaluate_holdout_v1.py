from pathlib import Path

import pandas as pd

from backtest_poisson import (
    calculate_1x2_metrics,
    calculate_market_metrics
)

from build_reliability_gate import (
    MARKET_COLUMNS,
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

OUTPUT_MARKETS = (
    DATA_DIR
    / "holdout_v1_market_metrics.csv"
)

OUTPUT_SIGNALS = (
    DATA_DIR
    / "holdout_v1_gate_signals.csv"
)

OUTPUT_GATE_SUMMARY = (
    DATA_DIR
    / "holdout_v1_gate_summary.csv"
)


# ============================================================
# RESULTADOS REALES DE CADA MERCADO
# ============================================================

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
# CRITERIOS DEFINIDOS ANTES DE VER EL HOLDOUT
# ============================================================

MIN_GATE_HOLDOUT_N = 20

MIN_GATE_ACTUAL_RATE = 0.70

MAX_GATE_CALIBRATION_GAP = 0.05


# ============================================================
# FORMATO
# ============================================================

def percentage(value):

    return (
        float(value)
        * 100
    )


# ============================================================
# EVALUAR RELIABILITY GATE EN HOLDOUT
# ============================================================

def evaluate_gate(
    holdout_df,
    development_metrics,
    development_calibration
):

    metrics_index = (
        development_metrics
        .set_index(
            "market"
        )
    )

    rows = []

    for _, prediction in holdout_df.iterrows():

        for (
            market,
            probability_column
        ) in MARKET_COLUMNS.items():

            if (
                market
                not in metrics_index.index
            ):
                continue

            actual_column = (
                ACTUAL_COLUMNS.get(
                    market
                )
            )

            if actual_column is None:
                continue

            if (
                probability_column
                not in prediction.index
            ):
                continue

            if (
                actual_column
                not in prediction.index
            ):
                continue

            # ------------------------------------------------
            # PROBABILIDAD
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

            # ------------------------------------------------
            # MÉTRICAS DEVELOPMENT
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
            # BIN DEVELOPMENT
            # ------------------------------------------------

            calibration_bin = (
                find_calibration_bin(
                    calibration_df=
                        development_calibration,

                    market=
                        market,

                    probability_pct=
                        probability_pct
                )
            )

            # ------------------------------------------------
            # APLICAR EXACTAMENTE EL MISMO GATE
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

            actual = int(
                prediction[
                    actual_column
                ]
            )

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

    return pd.DataFrame(
        rows
    )


# ============================================================
# RESUMEN DEL GATE
# ============================================================

def build_gate_summary(
    gate_df
):

    rows = []

    if gate_df.empty:

        return pd.DataFrame(
            rows
        )

    # --------------------------------------------------------
    # TOTAL
    # --------------------------------------------------------

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

    rows.append(
        {
            "group":
                "ALL",

            "n":
                len(
                    gate_df
                ),

            "average_prediction_pct":
                average_prediction
                * 100,

            "actual_rate_pct":
                actual_rate
                * 100,

            "calibration_gap_pct":
                calibration_gap
                * 100,
        }
    )

    # --------------------------------------------------------
    # POR MERCADO
    # --------------------------------------------------------

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

        average_prediction = (
            market_df[
                "model_probability"
            ].mean()
        )

        actual_rate = (
            market_df[
                "actual"
            ].mean()
        )

        calibration_gap = abs(
            average_prediction
            - actual_rate
        )

        rows.append(
            {
                "group":
                    market,

                "n":
                    len(
                        market_df
                    ),

                "average_prediction_pct":
                    average_prediction
                    * 100,

                "actual_rate_pct":
                    actual_rate
                    * 100,

                "calibration_gap_pct":
                    calibration_gap
                    * 100,
            }
        )

    return pd.DataFrame(
        rows
    )


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    print("=" * 82)
    print(
        "CulebrIA - EXAMEN FINAL HOLDOUT V1"
    )
    print("=" * 82)

    print()
    print(
        "⚠️ ESTE SCRIPT ABRE EL HOLDOUT."
    )

    print(
        "Después de esta ejecución, "
        "estos datos no deben utilizarse "
        "para ajustar Poisson V1."
    )

    # ========================================================
    # CARGAR BACKTEST
    # ========================================================

    predictions = pd.read_csv(
        PREDICTIONS_FILE
    )

    development = predictions[
        predictions[
            "split"
        ] == "DEVELOPMENT"
    ].copy()

    holdout = predictions[
        predictions[
            "split"
        ] == "HOLDOUT"
    ].copy()

    if holdout.empty:

        print()
        print(
            "❌ No existen registros HOLDOUT."
        )

        return

    print()
    print(
        f"DEVELOPMENT: "
        f"{len(development)}"
    )

    print(
        f"HOLDOUT: "
        f"{len(holdout)}"
    )

    # ========================================================
    # 1X2
    # ========================================================

    development_1x2 = (
        calculate_1x2_metrics(
            development
        )
    )

    holdout_1x2 = (
        calculate_1x2_metrics(
            holdout
        )
    )

    print()
    print("=" * 82)
    print(
        "1X2 - DEVELOPMENT VS HOLDOUT"
    )
    print("=" * 82)

    print()

    print(
        f"{'MÉTRICA':<25}"
        f"{'DEVELOPMENT':>15}"
        f"{'HOLDOUT':>15}"
    )

    print(
        "-" * 55
    )

    print(
        f"{'N':<25}"
        f"{development_1x2['n']:>15}"
        f"{holdout_1x2['n']:>15}"
    )

    print(
        f"{'Accuracy %':<25}"
        f"{percentage(development_1x2['accuracy']):>15.2f}"
        f"{percentage(holdout_1x2['accuracy']):>15.2f}"
    )

    print(
        f"{'Brier':<25}"
        f"{development_1x2['brier']:>15.4f}"
        f"{holdout_1x2['brier']:>15.4f}"
    )

    print(
        f"{'Brier baseline':<25}"
        f"{development_1x2['baseline_brier']:>15.4f}"
        f"{holdout_1x2['baseline_brier']:>15.4f}"
    )

    print(
        f"{'Brier Skill %':<25}"
        f"{percentage(development_1x2['brier_skill']):>15.2f}"
        f"{percentage(holdout_1x2['brier_skill']):>15.2f}"
    )

    print(
        f"{'Log Loss':<25}"
        f"{development_1x2['log_loss']:>15.4f}"
        f"{holdout_1x2['log_loss']:>15.4f}"
    )

    print(
        f"{'Log Loss baseline':<25}"
        f"{development_1x2['baseline_log_loss']:>15.4f}"
        f"{holdout_1x2['baseline_log_loss']:>15.4f}"
    )

    # ========================================================
    # ¿GENERALIZA EL MODELO?
    # ========================================================

    model_generalizes = (
        holdout_1x2[
            "brier_skill"
        ] > 0

        and

        holdout_1x2[
            "log_loss"
        ]
        <
        holdout_1x2[
            "baseline_log_loss"
        ]
    )

    print()
    print(
        "Resultado 1X2:"
    )

    if model_generalizes:

        print(
            "✅ Poisson V1 supera al baseline "
            "también en HOLDOUT."
        )

    else:

        print(
            "❌ Poisson V1 NO supera "
            "consistentemente al baseline "
            "en HOLDOUT."
        )

    # ========================================================
    # MERCADOS HOLDOUT
    # ========================================================

    (
        holdout_metrics,
        _
    ) = calculate_market_metrics(
        holdout
    )

    holdout_metrics.to_csv(
        OUTPUT_MARKETS,
        index=False,
        encoding="utf-8-sig"
    )

    print()
    print("=" * 82)
    print(
        "MERCADOS - HOLDOUT"
    )
    print("=" * 82)

    print()

    print(
        f"{'MERCADO':<15}"
        f"{'N':>6}"
        f"{'PRED%':>10}"
        f"{'REAL%':>10}"
        f"{'BRIER':>10}"
        f"{'SKILL%':>10}"
        f"{'ECE%':>10}"
    )

    print(
        "-" * 71
    )

    for _, row in (
        holdout_metrics.iterrows()
    ):

        print(
            f"{row['market']:<15}"
            f"{int(row['n']):>6}"
            f"{row['mean_prediction_pct']:>10.2f}"
            f"{row['actual_rate_pct']:>10.2f}"
            f"{row['brier']:>10.4f}"
            f"{row['brier_skill'] * 100:>10.2f}"
            f"{row['ece'] * 100:>10.2f}"
        )

    # ========================================================
    # APLICAR GATE DE DEVELOPMENT AL HOLDOUT
    # ========================================================

    development_metrics = pd.read_csv(
        DEVELOPMENT_METRICS_FILE
    )

    development_calibration = pd.read_csv(
        DEVELOPMENT_CALIBRATION_FILE
    )

    gate_df = evaluate_gate(
        holdout_df=
            holdout,

        development_metrics=
            development_metrics,

        development_calibration=
            development_calibration
    )

    gate_df.to_csv(
        OUTPUT_SIGNALS,
        index=False,
        encoding="utf-8-sig"
    )

    gate_summary = (
        build_gate_summary(
            gate_df
        )
    )

    gate_summary.to_csv(
        OUTPUT_GATE_SUMMARY,
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # RESULTADOS DEL GATE
    # ========================================================

    print()
    print("=" * 82)
    print(
        "RELIABILITY GATE - HOLDOUT"
    )
    print("=" * 82)

    print()

    if gate_df.empty:

        print(
            "No se generaron señales "
            "de baja volatilidad."
        )

        gate_status = (
            "INCONCLUSO"
        )

    else:

        total_n = len(
            gate_df
        )

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

        print(
            f"Señales HOLDOUT: "
            f"{total_n}"
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

        print()
        print(
            "POR MERCADO"
        )

        print()

        for _, row in (
            gate_summary[
                gate_summary[
                    "group"
                ] != "ALL"
            ].iterrows()
        ):

            print(
                f"{row['group']}: "
                f"N={int(row['n'])} | "
                f"Pred={row['average_prediction_pct']:.2f}% | "
                f"Real={row['actual_rate_pct']:.2f}% | "
                f"Gap={row['calibration_gap_pct']:.2f} pp"
            )

        # ----------------------------------------------------
        # CRITERIO PREDEFINIDO
        # ----------------------------------------------------

        if (
            total_n
            < MIN_GATE_HOLDOUT_N
        ):

            gate_status = (
                "INCONCLUSO_MUESTRA_BAJA"
            )

        elif (
            actual_rate
            >= MIN_GATE_ACTUAL_RATE
            and
            calibration_gap
            <= MAX_GATE_CALIBRATION_GAP
        ):

            gate_status = (
                "APROBADO"
            )

        else:

            gate_status = (
                "NO_APROBADO"
            )

    print()
    print(
        f"Estado Reliability Gate: "
        f"{gate_status}"
    )

    # ========================================================
    # RESULTADO FINAL
    # ========================================================

    print()
    print("=" * 82)
    print(
        "VEREDICTO V1"
    )
    print("=" * 82)

    print()

    if (
        model_generalizes
        and
        gate_status
        == "APROBADO"
    ):

        final_status = (
            "V1_VALIDADO"
        )

        print(
            "✅ POISSON V1 + RELIABILITY GATE "
            "superaron el HOLDOUT."
        )

    elif (
        model_generalizes
        and
        gate_status.startswith(
            "INCONCLUSO"
        )
    ):

        final_status = (
            "MODELO_VALIDO_GATE_INCONCLUSO"
        )

        print(
            "🟡 Poisson V1 generaliza, "
            "pero el Gate necesita "
            "más observaciones."
        )

    else:

        final_status = (
            "V1_NO_VALIDADO"
        )

        print(
            "❌ V1 no cumple todos "
            "los criterios definidos."
        )

    print()
    print(
        f"ESTADO FINAL: "
        f"{final_status}"
    )

    print()

    print(
        "Solicitudes API realizadas: 0"
    )

    print(
        "Créditos The Odds API: 0"
    )

    print()

    print(
        "Archivos creados:"
    )

    print(
        OUTPUT_MARKETS
    )

    print(
        OUTPUT_SIGNALS
    )

    print(
        OUTPUT_GATE_SUMMARY
    )

    print()
    print(
        "⚠️ El HOLDOUT queda oficialmente "
        "ABIERTO después de esta prueba."
    )


if __name__ == "__main__":
    main()