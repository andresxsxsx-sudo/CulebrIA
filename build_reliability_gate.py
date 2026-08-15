from pathlib import Path

import pandas as pd


# ============================================================
# CONFIGURACIÓN
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"

METRICS_FILE = (
    DATA_DIR
    / "backtest_market_metrics.csv"
)

CALIBRATION_FILE = (
    DATA_DIR
    / "backtest_calibration.csv"
)

PREDICTIONS_FILE = (
    DATA_DIR
    / "poisson_predictions.csv"
)

OUTPUT_ALL = (
    DATA_DIR
    / "reliability_gate_all.csv"
)

OUTPUT_SIGNALS = (
    DATA_DIR
    / "reliability_gate_signals.csv"
)


# ============================================================
# UMBRALES
# ============================================================

# El modelo tiene que mejorar al baseline
# al menos un 2 % en Brier.
MIN_MARKET_BRIER_SKILL = 0.02

# Error de calibración máximo del mercado.
MAX_MARKET_ECE = 0.06

# Número mínimo de predicciones históricas
# dentro de un rango de probabilidad.
MIN_BIN_SAMPLE = 30

# Diferencia máxima entre probabilidad
# predicha y frecuencia observada.
MAX_BIN_GAP_PCT = 5.0

# Para nuestro grupo de señales
# de menor volatilidad.
MIN_LOW_VOLATILITY_PCT = 70.0


# ============================================================
# MAPA DE MERCADOS
# ============================================================

MARKET_COLUMNS = {
    "HOME_WIN":
        "home_win_pct",

    "DRAW":
        "draw_pct",

    "AWAY_WIN":
        "away_win_pct",

    "1X":
        "home_or_draw_pct",

    "X2":
        "away_or_draw_pct",

    "OVER_1_5":
        "over15_pct",

    "OVER_2_5":
        "over25_pct",

    "UNDER_3_5":
        "under35_pct",

    "BTTS":
        "btts_pct",

    "HOME_SCORES":
        "home_scores_pct",

    "AWAY_SCORES":
        "away_scores_pct",
}


# ============================================================
# LOCALIZAR BIN DE CALIBRACIÓN
# ============================================================

def find_calibration_bin(
    calibration_df,
    market,
    probability_pct
):

    market_bins = calibration_df[
        calibration_df[
            "market"
        ] == market
    ]

    for _, row in market_bins.iterrows():

        start = float(
            row[
                "bin_start_pct"
            ]
        )

        end = float(
            row[
                "bin_end_pct"
            ]
        )

        # Normalmente:
        # 70 <= p < 80
        if (
            probability_pct >= start
            and
            probability_pct < end
        ):
            return row

        # Caso excepcional p = 100
        if (
            probability_pct == 100
            and
            end == 100
        ):
            return row

    return None


# ============================================================
# CLASIFICAR UNA SEÑAL
# ============================================================

def classify_signal(
    probability_pct,
    market_skill,
    market_ece,
    calibration_bin
):

    reasons = []

    # --------------------------------------------------------
    # MERCADO GLOBAL
    # --------------------------------------------------------

    if (
        market_skill
        < MIN_MARKET_BRIER_SKILL
    ):

        reasons.append(
            "BRIER_SKILL_BAJO"
        )

    if (
        market_ece
        > MAX_MARKET_ECE
    ):

        reasons.append(
            "ECE_ALTO"
        )

    # --------------------------------------------------------
    # BIN
    # --------------------------------------------------------

    if calibration_bin is None:

        reasons.append(
            "SIN_BIN_CALIBRACION"
        )

        return {
            "reliable":
                False,

            "low_volatility":
                False,

            "grade":
                "BLOQUEADO",

            "reasons":
                reasons,

            "bin_n":
                0,

            "bin_gap_pct":
                None,

            "bin_actual_pct":
                None,

            "bin_prediction_pct":
                None,
        }

    bin_n = int(
        calibration_bin[
            "n"
        ]
    )

    bin_gap = float(
        calibration_bin[
            "absolute_gap_pct"
        ]
    )

    bin_actual = float(
        calibration_bin[
            "actual_rate_pct"
        ]
    )

    bin_prediction = float(
        calibration_bin[
            "avg_prediction_pct"
        ]
    )

    if (
        bin_n
        < MIN_BIN_SAMPLE
    ):

        reasons.append(
            "MUESTRA_BIN_BAJA"
        )

    if (
        bin_gap
        > MAX_BIN_GAP_PCT
    ):

        reasons.append(
            "BIN_MAL_CALIBRADO"
        )

    # --------------------------------------------------------
    # RESULTADO DE FIABILIDAD
    # --------------------------------------------------------

    reliable = (
        len(reasons) == 0
    )

    low_volatility = (
        reliable
        and
        probability_pct
        >= MIN_LOW_VOLATILITY_PCT
    )

    # --------------------------------------------------------
    # GRADO
    # --------------------------------------------------------

    if (
        low_volatility
        and
        bin_n >= 60
        and
        bin_gap <= 2.5
    ):

        grade = "A"

    elif low_volatility:

        grade = "B"

    elif reliable:

        grade = "C"

    else:

        grade = "BLOQUEADO"

    return {
        "reliable":
            reliable,

        "low_volatility":
            low_volatility,

        "grade":
            grade,

        "reasons":
            reasons,

        "bin_n":
            bin_n,

        "bin_gap_pct":
            bin_gap,

        "bin_actual_pct":
            bin_actual,

        "bin_prediction_pct":
            bin_prediction,
    }


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    print("=" * 80)
    print(
        "CulebrIA - MARKET RELIABILITY GATE"
    )
    print("=" * 80)

    # --------------------------------------------------------
    # CARGAR DATOS
    # --------------------------------------------------------

    metrics_df = pd.read_csv(
        METRICS_FILE
    )

    calibration_df = pd.read_csv(
        CALIBRATION_FILE
    )

    predictions_df = pd.read_csv(
        PREDICTIONS_FILE
    )

    metrics_index = (
        metrics_df
        .set_index(
            "market"
        )
    )

    print()
    print(
        f"Partidos con predicción: "
        f"{len(predictions_df)}"
    )

    print(
        f"Mercados evaluados: "
        f"{len(MARKET_COLUMNS)}"
    )

    # ========================================================
    # RESUMEN GLOBAL DE MERCADOS
    # ========================================================

    print()
    print("=" * 80)
    print(
        "FIABILIDAD GLOBAL DE MERCADOS"
    )
    print("=" * 80)

    print()

    print(
        f"{'MERCADO':<15}"
        f"{'SKILL%':>10}"
        f"{'ECE%':>10}"
        f"{'ESTADO':>15}"
    )

    print(
        "-" * 50
    )

    market_global_status = {}

    for market in MARKET_COLUMNS:

        if (
            market
            not in metrics_index.index
        ):

            market_global_status[
                market
            ] = False

            print(
                f"{market:<15}"
                f"{'?':>10}"
                f"{'?':>10}"
                f"{'SIN DATOS':>15}"
            )

            continue

        metric = metrics_index.loc[
            market
        ]

        skill = float(
            metric[
                "brier_skill"
            ]
        )

        ece = float(
            metric[
                "ece"
            ]
        )

        global_ok = (
            skill
            >= MIN_MARKET_BRIER_SKILL
            and
            ece
            <= MAX_MARKET_ECE
        )

        market_global_status[
            market
        ] = global_ok

        status = (
            "APROBADO"
            if global_ok
            else
            "BLOQUEADO"
        )

        print(
            f"{market:<15}"
            f"{skill * 100:>10.2f}"
            f"{ece * 100:>10.2f}"
            f"{status:>15}"
        )

    # ========================================================
    # EVALUAR PREDICCIONES
    # ========================================================

    rows = []

    for _, prediction in predictions_df.iterrows():

        fixture_id = int(
            prediction[
                "fixture_id"
            ]
        )

        home = str(
            prediction[
                "home"
            ]
        )

        away = str(
            prediction[
                "away"
            ]
        )

        competition = str(
            prediction[
                "competition"
            ]
        )

        for (
            market,
            probability_column
        ) in MARKET_COLUMNS.items():

            if (
                market
                not in metrics_index.index
            ):
                continue

            probability_pct = float(
                prediction[
                    probability_column
                ]
            )

            metric = metrics_index.loc[
                market
            ]

            skill = float(
                metric[
                    "brier_skill"
                ]
            )

            ece = float(
                metric[
                    "ece"
                ]
            )

            calibration_bin = (
                find_calibration_bin(
                    calibration_df=
                        calibration_df,

                    market=
                        market,

                    probability_pct=
                        probability_pct
                )
            )

            result = classify_signal(
                probability_pct=
                    probability_pct,

                market_skill=
                    skill,

                market_ece=
                    ece,

                calibration_bin=
                    calibration_bin
            )

            rows.append(
                {
                    "fixture_id":
                        fixture_id,

                    "competition":
                        competition,

                    "home":
                        home,

                    "away":
                        away,

                    "market":
                        market,

                    "model_probability_pct":
                        round(
                            probability_pct,
                            2
                        ),

                    "market_brier_skill_pct":
                        round(
                            skill * 100,
                            2
                        ),

                    "market_ece_pct":
                        round(
                            ece * 100,
                            2
                        ),

                    "bin_n":
                        result[
                            "bin_n"
                        ],

                    "bin_prediction_pct":
                        result[
                            "bin_prediction_pct"
                        ],

                    "bin_actual_pct":
                        result[
                            "bin_actual_pct"
                        ],

                    "bin_gap_pct":
                        result[
                            "bin_gap_pct"
                        ],

                    "reliable":
                        result[
                            "reliable"
                        ],

                    "low_volatility":
                        result[
                            "low_volatility"
                        ],

                    "grade":
                        result[
                            "grade"
                        ],

                    "block_reasons":
                        " | ".join(
                            result[
                                "reasons"
                            ]
                        ),
                }
            )

    # ========================================================
    # DATAFRAME COMPLETO
    # ========================================================

    all_df = pd.DataFrame(
        rows
    )

    all_df.to_csv(
        OUTPUT_ALL,
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # SEÑALES DE BAJA VOLATILIDAD
    # ========================================================

    signals_df = all_df[
        all_df[
            "low_volatility"
        ] == True
    ].copy()

    grade_order = {
        "A": 1,
        "B": 2,
        "C": 3,
    }

    if not signals_df.empty:

        signals_df[
            "_grade_order"
        ] = signals_df[
            "grade"
        ].map(
            grade_order
        )

        signals_df = (
            signals_df
            .sort_values(
                [
                    "_grade_order",
                    "model_probability_pct"
                ],
                ascending=[
                    True,
                    False
                ]
            )
            .drop(
                columns=[
                    "_grade_order"
                ]
            )
        )

    signals_df.to_csv(
        OUTPUT_SIGNALS,
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # TERMINAL
    # ========================================================

    print()
    print("=" * 80)
    print(
        "SEÑALES QUE SUPERAN EL GATE"
    )
    print("=" * 80)

    print()

    if signals_df.empty:

        print(
            "No hay señales de "
            "baja volatilidad aprobadas."
        )

    else:

        for _, signal in (
            signals_df.iterrows()
        ):

            print(
                f"{signal['home']} "
                f"vs "
                f"{signal['away']}"
            )

            print(
                f"Mercado: "
                f"{signal['market']}"
            )

            print(
                f"Probabilidad modelo: "
                f"{signal['model_probability_pct']:.2f}%"
            )

            print(
                f"Grado: "
                f"{signal['grade']}"
            )

            print(
                f"Backtest bin: "
                f"N={int(signal['bin_n'])}"
            )

            print(
                f"Gap calibración: "
                f"{signal['bin_gap_pct']:.2f}%"
            )

            print(
                "-" * 60
            )

    # ========================================================
    # RESUMEN
    # ========================================================

    print()
    print("=" * 80)
    print(
        "RESULTADO FINAL"
    )
    print("=" * 80)

    print()

    print(
        f"Evaluaciones realizadas: "
        f"{len(all_df)}"
    )

    print(
        f"Señales fiables: "
        f"{int(all_df['reliable'].sum())}"
    )

    print(
        f"Señales baja volatilidad: "
        f"{len(signals_df)}"
    )

    print()

    print(
        "Solicitudes API realizadas: 0"
    )

    print()

    print(
        "Archivos:"
    )

    print(
        OUTPUT_ALL
    )

    print(
        OUTPUT_SIGNALS
    )

    print()

    print(
        "⚠️ Estas son señales estadísticas, "
        "NO recomendaciones de apuesta."
    )

    print(
        "Todavía no tenemos cuotas reales "
        "ni hemos abierto el HOLDOUT."
    )


if __name__ == "__main__":
    main()