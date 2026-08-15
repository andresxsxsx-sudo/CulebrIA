from pathlib import Path

import pandas as pd


# ============================================================
# CONFIGURACIÓN
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"

INPUT_FILE = (
    DATA_DIR
    / "poisson_predictions.csv"
)

OUTPUT_FILE = (
    DATA_DIR
    / "poisson_audit.csv"
)


# ============================================================
# TOLERANCIAS
# ============================================================

PROBABILITY_TOLERANCE = 0.15
IDENTITY_TOLERANCE = 0.20
ODDS_TOLERANCE = 0.01

MIN_LEAGUE_SAMPLE = 50

MIN_LAMBDA = 0.15
MAX_LAMBDA = 4.50


# ============================================================
# UTILIDADES
# ============================================================

def close_enough(
    value,
    expected,
    tolerance
):
    return (
        abs(
            value
            - expected
        )
        <= tolerance
    )


def probability_valid(value):
    return (
        0.0
        <= value
        <= 100.0
    )


def check_fair_odds(
    probability_pct,
    fair_odds
):
    """
    Comprueba:

        cuota justa ≈ 1 / probabilidad

    La probabilidad viene en porcentaje.
    """

    if probability_pct <= 0:
        return True

    probability = (
        probability_pct
        / 100
    )

    expected = (
        1
        / probability
    )

    return (
        abs(
            fair_odds
            - expected
        )
        <= ODDS_TOLERANCE
    )


# ============================================================
# AUDITAR UNA FILA
# ============================================================

def audit_prediction(row):

    errors = []
    warnings = []

    # --------------------------------------------------------
    # PROBABILIDADES
    # --------------------------------------------------------

    probability_columns = [
        "home_win_pct",
        "draw_pct",
        "away_win_pct",
        "home_or_draw_pct",
        "away_or_draw_pct",
        "home_dnb_pct",
        "away_dnb_pct",
        "over15_pct",
        "over25_pct",
        "under35_pct",
        "btts_pct",
        "home_scores_pct",
        "away_scores_pct",
        "most_likely_score_pct",
    ]

    for column in probability_columns:

        value = float(
            row[column]
        )

        if not probability_valid(
            value
        ):
            errors.append(
                f"{column} fuera de 0-100"
            )

    # --------------------------------------------------------
    # 1X2 = 100 %
    # --------------------------------------------------------

    one_x_two = (
        float(
            row["home_win_pct"]
        )
        +
        float(
            row["draw_pct"]
        )
        +
        float(
            row["away_win_pct"]
        )
    )

    if not close_enough(
        one_x_two,
        100.0,
        PROBABILITY_TOLERANCE
    ):
        errors.append(
            f"1X2 suma {one_x_two:.2f}%"
        )

    # --------------------------------------------------------
    # DOBLE OPORTUNIDAD
    # --------------------------------------------------------

    expected_1x = (
        float(
            row["home_win_pct"]
        )
        +
        float(
            row["draw_pct"]
        )
    )

    if not close_enough(
        float(
            row["home_or_draw_pct"]
        ),
        expected_1x,
        IDENTITY_TOLERANCE
    ):
        errors.append(
            "1X inconsistente"
        )

    expected_x2 = (
        float(
            row["away_win_pct"]
        )
        +
        float(
            row["draw_pct"]
        )
    )

    if not close_enough(
        float(
            row["away_or_draw_pct"]
        ),
        expected_x2,
        IDENTITY_TOLERANCE
    ):
        errors.append(
            "X2 inconsistente"
        )

    # --------------------------------------------------------
    # DRAW NO BET
    # --------------------------------------------------------

    dnb_total = (
        float(
            row["home_dnb_pct"]
        )
        +
        float(
            row["away_dnb_pct"]
        )
    )

    if not close_enough(
        dnb_total,
        100.0,
        PROBABILITY_TOLERANCE
    ):
        errors.append(
            f"DNB suma {dnb_total:.2f}%"
        )

    # --------------------------------------------------------
    # OVER 1.5 >= OVER 2.5
    # --------------------------------------------------------

    if (
        float(
            row["over25_pct"]
        )
        >
        float(
            row["over15_pct"]
        )
        +
        PROBABILITY_TOLERANCE
    ):
        errors.append(
            "Over 2.5 mayor que Over 1.5"
        )

    # --------------------------------------------------------
    # LAMBDAS
    # --------------------------------------------------------

    lambda_home = float(
        row["lambda_home"]
    )

    lambda_away = float(
        row["lambda_away"]
    )

    lambda_total = float(
        row["lambda_total"]
    )

    if not (
        MIN_LAMBDA
        <= lambda_home
        <= MAX_LAMBDA
    ):
        errors.append(
            "lambda_home fuera de límites"
        )

    if not (
        MIN_LAMBDA
        <= lambda_away
        <= MAX_LAMBDA
    ):
        errors.append(
            "lambda_away fuera de límites"
        )

    expected_lambda_total = (
        lambda_home
        + lambda_away
    )

    if not close_enough(
        lambda_total,
        expected_lambda_total,
        0.01
    ):
        errors.append(
            "lambda_total inconsistente"
        )

    # --------------------------------------------------------
    # MUESTRA DE LIGA
    # --------------------------------------------------------

    league_sample = int(
        row["league_sample"]
    )

    if (
        league_sample
        < MIN_LEAGUE_SAMPLE
    ):
        warnings.append(
            f"Muestra liga pequeña: "
            f"{league_sample}"
        )

    # --------------------------------------------------------
    # MUESTRAS LOCAL / VISITANTE
    # --------------------------------------------------------

    home_sample = int(
        row["home_venue_sample"]
    )

    away_sample = int(
        row["away_venue_sample"]
    )

    if home_sample < 5:
        warnings.append(
            f"Muestra local baja: "
            f"{home_sample}"
        )

    if away_sample < 5:
        warnings.append(
            f"Muestra visitante baja: "
            f"{away_sample}"
        )

    # --------------------------------------------------------
    # CUOTAS JUSTAS
    # --------------------------------------------------------

    fair_checks = [
        (
            "home_win_pct",
            "fair_home_win"
        ),
        (
            "draw_pct",
            "fair_draw"
        ),
        (
            "away_win_pct",
            "fair_away_win"
        ),
        (
            "over15_pct",
            "fair_over15"
        ),
        (
            "over25_pct",
            "fair_over25"
        ),
        (
            "under35_pct",
            "fair_under35"
        ),
        (
            "btts_pct",
            "fair_btts"
        ),
    ]

    for (
        probability_column,
        odds_column
    ) in fair_checks:

        probability = float(
            row[
                probability_column
            ]
        )

        fair_value = float(
            row[
                odds_column
            ]
        )

        if not check_fair_odds(
            probability,
            fair_value
        ):
            errors.append(
                f"{odds_column} inconsistente"
            )

    # --------------------------------------------------------
    # MARCADOR MÁS PROBABLE
    # --------------------------------------------------------

    score = str(
        row[
            "most_likely_score"
        ]
    )

    parts = score.split("-")

    if len(parts) != 2:

        errors.append(
            "Formato de marcador inválido"
        )

    else:

        try:

            home_goals = int(
                parts[0]
            )

            away_goals = int(
                parts[1]
            )

            if (
                home_goals < 0
                or away_goals < 0
            ):
                errors.append(
                    "Marcador negativo"
                )

        except ValueError:

            errors.append(
                "Marcador no numérico"
            )

    # --------------------------------------------------------
    # ESTADO
    # --------------------------------------------------------

    if errors:

        status = (
            "ERROR"
        )

    elif warnings:

        status = (
            "ADVERTENCIA"
        )

    else:

        status = (
            "OK"
        )

    return {
        "status":
            status,

        "errors":
            errors,

        "warnings":
            warnings,

        "one_x_two_total":
            one_x_two,

        "dnb_total":
            dnb_total,
    }


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    print("=" * 76)
    print(
        "CulebrIA - AUDITORÍA POISSON V1"
    )
    print("=" * 76)

    df = pd.read_csv(
        INPUT_FILE
    )

    print()
    print(
        f"Predicciones encontradas: "
        f"{len(df)}"
    )

    # --------------------------------------------------------
    # DUPLICADOS
    # --------------------------------------------------------

    duplicate_count = int(
        df[
            "fixture_id"
        ].duplicated().sum()
    )

    print(
        f"Fixture ID duplicados: "
        f"{duplicate_count}"
    )

    audit_rows = []

    ok_count = 0
    warning_count = 0
    error_count = 0

    # ========================================================
    # AUDITAR PARTIDO POR PARTIDO
    # ========================================================

    for _, row in df.iterrows():

        result = (
            audit_prediction(
                row
            )
        )

        status = result[
            "status"
        ]

        if status == "OK":

            ok_count += 1

        elif status == "ADVERTENCIA":

            warning_count += 1

        else:

            error_count += 1

        errors_text = (
            " | ".join(
                result[
                    "errors"
                ]
            )
        )

        warnings_text = (
            " | ".join(
                result[
                    "warnings"
                ]
            )
        )

        audit_rows.append(
            {
                "fixture_id":
                    row[
                        "fixture_id"
                    ],

                "competition":
                    row[
                        "competition"
                    ],

                "home":
                    row[
                        "home"
                    ],

                "away":
                    row[
                        "away"
                    ],

                "status":
                    status,

                "errors":
                    errors_text,

                "warnings":
                    warnings_text,

                "lambda_home":
                    row[
                        "lambda_home"
                    ],

                "lambda_away":
                    row[
                        "lambda_away"
                    ],

                "lambda_total":
                    row[
                        "lambda_total"
                    ],

                "one_x_two_total":
                    round(
                        result[
                            "one_x_two_total"
                        ],
                        3
                    ),

                "dnb_total":
                    round(
                        result[
                            "dnb_total"
                        ],
                        3
                    ),

                "home_win_pct":
                    row[
                        "home_win_pct"
                    ],

                "draw_pct":
                    row[
                        "draw_pct"
                    ],

                "away_win_pct":
                    row[
                        "away_win_pct"
                    ],

                "over15_pct":
                    row[
                        "over15_pct"
                    ],

                "over25_pct":
                    row[
                        "over25_pct"
                    ],

                "under35_pct":
                    row[
                        "under35_pct"
                    ],

                "btts_pct":
                    row[
                        "btts_pct"
                    ],
            }
        )

        # ----------------------------------------------------
        # TERMINAL
        # ----------------------------------------------------

        print()
        print("-" * 76)

        print(
            f"{row['home']} "
            f"vs "
            f"{row['away']}"
        )

        print(
            f"Estado: "
            f"{status}"
        )

        print(
            f"λ: "
            f"{row['lambda_home']} "
            f"- "
            f"{row['lambda_away']}"
        )

        print(
            f"1X2 suma: "
            f"{result['one_x_two_total']:.2f}%"
        )

        print(
            f"DNB suma: "
            f"{result['dnb_total']:.2f}%"
        )

        if result[
            "errors"
        ]:

            print(
                "ERRORES:"
            )

            for error in result[
                "errors"
            ]:

                print(
                    f"  ❌ {error}"
                )

        if result[
            "warnings"
        ]:

            print(
                "ADVERTENCIAS:"
            )

            for warning in result[
                "warnings"
            ]:

                print(
                    f"  ⚠️ {warning}"
                )

        if (
            not result["errors"]
            and
            not result["warnings"]
        ):

            print(
                "✅ Sin inconsistencias"
            )

    # ========================================================
    # DUPLICADOS
    # ========================================================

    if duplicate_count > 0:

        error_count += (
            duplicate_count
        )

    # ========================================================
    # GUARDAR
    # ========================================================

    audit_df = pd.DataFrame(
        audit_rows
    )

    audit_df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # RESULTADO FINAL
    # ========================================================

    print()
    print("=" * 76)
    print(
        "RESULTADO FINAL"
    )
    print("=" * 76)

    print()

    print(
        f"OK: "
        f"{ok_count}"
    )

    print(
        f"ADVERTENCIAS: "
        f"{warning_count}"
    )

    print(
        f"ERRORES: "
        f"{error_count}"
    )

    print(
        f"DUPLICADOS: "
        f"{duplicate_count}"
    )

    print()

    print(
        "Solicitudes API realizadas: 0"
    )

    print()

    print(
        "Informe:"
    )

    print(
        OUTPUT_FILE
    )

    print()

    if (
        error_count == 0
        and
        duplicate_count == 0
    ):

        print(
            "✅ Estructura matemática "
            "apta para pasar a backtesting."
        )

    else:

        print(
            "❌ No pasar a backtesting "
            "hasta corregir los errores."
        )


if __name__ == "__main__":
    main()