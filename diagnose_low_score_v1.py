import math
from pathlib import Path

import pandas as pd


# ============================================================
# CONFIGURACIÓN
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"

INPUT_FILE = (
    DATA_DIR
    / "backtest_poisson_predictions.csv"
)

OUTPUT_FILE = (
    DATA_DIR
    / "v1_low_score_diagnostic.csv"
)


# ============================================================
# POISSON
# ============================================================

def poisson_probability(
    goals,
    lambda_value
):

    return (
        math.exp(
            -lambda_value
        )
        *
        (
            lambda_value ** goals
        )
        /
        math.factorial(
            goals
        )
    )


# ============================================================
# PREPARAR PROBABILIDADES DE MARCADORES
# ============================================================

def add_score_probabilities(
    df
):

    df = df.copy()

    p00_values = []
    p01_values = []
    p10_values = []
    p11_values = []

    draw_high_values = []

    total_le2_values = []

    home_zero_values = []
    away_zero_values = []

    for _, row in df.iterrows():

        lambda_home = float(
            row[
                "lambda_home"
            ]
        )

        lambda_away = float(
            row[
                "lambda_away"
            ]
        )

        # ----------------------------------------------------
        # DISTRIBUCIONES INDIVIDUALES
        # ----------------------------------------------------

        home_probs = [
            poisson_probability(
                goals,
                lambda_home
            )
            for goals in range(
                11
            )
        ]

        away_probs = [
            poisson_probability(
                goals,
                lambda_away
            )
            for goals in range(
                11
            )
        ]

        # ----------------------------------------------------
        # CELDAS DIXON-COLES
        # ----------------------------------------------------

        p00 = (
            home_probs[0]
            * away_probs[0]
        )

        p01 = (
            home_probs[0]
            * away_probs[1]
        )

        p10 = (
            home_probs[1]
            * away_probs[0]
        )

        p11 = (
            home_probs[1]
            * away_probs[1]
        )

        # ----------------------------------------------------
        # EMPATES 2-2 O SUPERIORES
        # ----------------------------------------------------

        draw_high = 0.0

        for goals in range(
            2,
            11
        ):

            draw_high += (
                home_probs[goals]
                * away_probs[goals]
            )

        # ----------------------------------------------------
        # TOTAL DE GOLES <= 2
        # ----------------------------------------------------

        total_le2 = 0.0

        for home_goals in range(
            11
        ):

            for away_goals in range(
                11
            ):

                if (
                    home_goals
                    + away_goals
                    <= 2
                ):

                    total_le2 += (
                        home_probs[
                            home_goals
                        ]
                        *
                        away_probs[
                            away_goals
                        ]
                    )

        p00_values.append(
            p00
        )

        p01_values.append(
            p01
        )

        p10_values.append(
            p10
        )

        p11_values.append(
            p11
        )

        draw_high_values.append(
            draw_high
        )

        total_le2_values.append(
            total_le2
        )

        home_zero_values.append(
            home_probs[0]
        )

        away_zero_values.append(
            away_probs[0]
        )

    df[
        "pred_p00"
    ] = p00_values

    df[
        "pred_p01"
    ] = p01_values

    df[
        "pred_p10"
    ] = p10_values

    df[
        "pred_p11"
    ] = p11_values

    df[
        "pred_draw_2plus"
    ] = draw_high_values

    df[
        "pred_total_le2"
    ] = total_le2_values

    df[
        "pred_home_zero"
    ] = home_zero_values

    df[
        "pred_away_zero"
    ] = away_zero_values

    return df


# ============================================================
# RESUMEN
# ============================================================

def summarize(
    df,
    competition,
    period
):

    if df.empty:

        return None

    home_goals = (
        df[
            "home_goals"
        ].astype(int)
    )

    away_goals = (
        df[
            "away_goals"
        ].astype(int)
    )

    actual_00 = (
        (
            home_goals == 0
        )
        &
        (
            away_goals == 0
        )
    ).mean()

    actual_01 = (
        (
            home_goals == 0
        )
        &
        (
            away_goals == 1
        )
    ).mean()

    actual_10 = (
        (
            home_goals == 1
        )
        &
        (
            away_goals == 0
        )
    ).mean()

    actual_11 = (
        (
            home_goals == 1
        )
        &
        (
            away_goals == 1
        )
    ).mean()

    actual_draw_2plus = (
        (
            home_goals
            == away_goals
        )
        &
        (
            home_goals
            >= 2
        )
    ).mean()

    actual_dc_cells = (
        (
            (
                home_goals == 0
            )
            &
            (
                away_goals == 0
            )
        )
        |
        (
            (
                home_goals == 0
            )
            &
            (
                away_goals == 1
            )
        )
        |
        (
            (
                home_goals == 1
            )
            &
            (
                away_goals == 0
            )
        )
        |
        (
            (
                home_goals == 1
            )
            &
            (
                away_goals == 1
            )
        )
    ).mean()

    actual_total_le2 = (
        (
            home_goals
            + away_goals
        )
        <= 2
    ).mean()

    actual_home_zero = (
        home_goals
        == 0
    ).mean()

    actual_away_zero = (
        away_goals
        == 0
    ).mean()

    predicted_dc_cells = (
        df[
            "pred_p00"
        ].mean()
        +
        df[
            "pred_p01"
        ].mean()
        +
        df[
            "pred_p10"
        ].mean()
        +
        df[
            "pred_p11"
        ].mean()
    )

    return {
        "competition":
            competition,

        "period":
            period,

        "n":
            len(df),

        # ----------------------------------------------------
        # EMPATES
        # ----------------------------------------------------

        "pred_draw_pct":
            df[
                "p_draw"
            ].mean()
            * 100,

        "real_draw_pct":
            df[
                "y_draw"
            ].mean()
            * 100,

        # ----------------------------------------------------
        # MARCADORES EXACTOS
        # ----------------------------------------------------

        "pred_00_pct":
            df[
                "pred_p00"
            ].mean()
            * 100,

        "real_00_pct":
            actual_00
            * 100,

        "pred_11_pct":
            df[
                "pred_p11"
            ].mean()
            * 100,

        "real_11_pct":
            actual_11
            * 100,

        "pred_draw_2plus_pct":
            df[
                "pred_draw_2plus"
            ].mean()
            * 100,

        "real_draw_2plus_pct":
            actual_draw_2plus
            * 100,

        # ----------------------------------------------------
        # CUATRO CELDAS DIXON-COLES
        # ----------------------------------------------------

        "pred_dc_cells_pct":
            predicted_dc_cells
            * 100,

        "real_dc_cells_pct":
            actual_dc_cells
            * 100,

        # ----------------------------------------------------
        # PARTIDOS DE POCOS GOLES
        # ----------------------------------------------------

        "pred_total_le2_pct":
            df[
                "pred_total_le2"
            ].mean()
            * 100,

        "real_total_le2_pct":
            actual_total_le2
            * 100,

        # ----------------------------------------------------
        # CERO GOLES
        # ----------------------------------------------------

        "pred_home_zero_pct":
            df[
                "pred_home_zero"
            ].mean()
            * 100,

        "real_home_zero_pct":
            actual_home_zero
            * 100,

        "pred_away_zero_pct":
            df[
                "pred_away_zero"
            ].mean()
            * 100,

        "real_away_zero_pct":
            actual_away_zero
            * 100,
    }


# ============================================================
# MOSTRAR
# ============================================================

def print_summary(
    row
):

    if row is None:
        return

    print()
    print("=" * 88)

    print(
        f"{row['competition']} "
        f"- "
        f"{row['period']}"
    )

    print("=" * 88)

    print()

    print(
        f"N: "
        f"{row['n']}"
    )

    print()

    print(
        f"{'EVENTO':<25}"
        f"{'MODELO':>12}"
        f"{'REAL':>12}"
        f"{'ERROR':>12}"
    )

    print(
        "-" * 61
    )

    metrics = [
        (
            "DRAW",
            "pred_draw_pct",
            "real_draw_pct"
        ),
        (
            "0-0",
            "pred_00_pct",
            "real_00_pct"
        ),
        (
            "1-1",
            "pred_11_pct",
            "real_11_pct"
        ),
        (
            "DRAW 2-2+",
            "pred_draw_2plus_pct",
            "real_draw_2plus_pct"
        ),
        (
            "DC CELLS",
            "pred_dc_cells_pct",
            "real_dc_cells_pct"
        ),
        (
            "TOTAL <= 2",
            "pred_total_le2_pct",
            "real_total_le2_pct"
        ),
        (
            "HOME = 0",
            "pred_home_zero_pct",
            "real_home_zero_pct"
        ),
        (
            "AWAY = 0",
            "pred_away_zero_pct",
            "real_away_zero_pct"
        ),
    ]

    for (
        name,
        pred_column,
        real_column
    ) in metrics:

        predicted = float(
            row[
                pred_column
            ]
        )

        real = float(
            row[
                real_column
            ]
        )

        error = (
            predicted
            - real
        )

        print(
            f"{name:<25}"
            f"{predicted:>11.2f}%"
            f"{real:>11.2f}%"
            f"{error:>+11.2f}"
        )


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    print("=" * 88)
    print(
        "CulebrIA - DIAGNOSTICO "
        "DE BAJOS MARCADORES V1"
    )
    print("=" * 88)

    df = pd.read_csv(
        INPUT_FILE
    )

    df[
        "kickoff"
    ] = pd.to_datetime(
        df[
            "kickoff"
        ],
        errors="coerce",
        utc=True
    )

    df = (
        df
        .sort_values(
            "kickoff"
        )
        .reset_index(
            drop=True
        )
    )

    df = add_score_probabilities(
        df
    )

    summaries = []

    # ========================================================
    # GLOBAL
    # ========================================================

    for period in [
        "DEVELOPMENT",
        "HOLDOUT"
    ]:

        period_df = df[
            df[
                "split"
            ] == period
        ]

        row = summarize(
            df=
                period_df,

            competition=
                "ALL",

            period=
                period
        )

        summaries.append(
            row
        )

        print_summary(
            row
        )

    # ========================================================
    # POR COMPETICIÓN
    # ========================================================

    competitions = sorted(
        df[
            "competition"
        ]
        .dropna()
        .astype(str)
        .unique()
    )

    for competition in competitions:

        competition_df = df[
            df[
                "competition"
            ].astype(str)
            == competition
        ].copy()

        development = competition_df[
            competition_df[
                "split"
            ]
            == "DEVELOPMENT"
        ].copy()

        holdout = competition_df[
            competition_df[
                "split"
            ]
            == "HOLDOUT"
        ].copy()

        # ----------------------------------------------------
        # DEVELOPMENT COMPLETO
        # ----------------------------------------------------

        row = summarize(
            df=
                development,

            competition=
                competition,

            period=
                "DEVELOPMENT"
        )

        summaries.append(
            row
        )

        print_summary(
            row
        )

        # ----------------------------------------------------
        # DEVELOPMENT RECIENTE
        # DEL MISMO TAMAÑO QUE HOLDOUT
        # ----------------------------------------------------

        holdout_n = len(
            holdout
        )

        if (
            holdout_n > 0
            and
            not development.empty
        ):

            recent_development = (
                development
                .sort_values(
                    "kickoff"
                )
                .tail(
                    min(
                        holdout_n,
                        len(
                            development
                        )
                    )
                )
            )

            row = summarize(
                df=
                    recent_development,

                competition=
                    competition,

                period=
                    "RECENT_DEVELOPMENT"
            )

            summaries.append(
                row
            )

            print_summary(
                row
            )

        # ----------------------------------------------------
        # HOLDOUT
        # ----------------------------------------------------

        row = summarize(
            df=
                holdout,

            competition=
                competition,

            period=
                "HOLDOUT"
        )

        summaries.append(
            row
        )

        print_summary(
            row
        )

    # ========================================================
    # GUARDAR
    # ========================================================

    output_df = pd.DataFrame(
        [
            row
            for row in summaries
            if row is not None
        ]
    )

    output_df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    print()
    print("=" * 88)
    print(
        "IMPORTANTE"
    )
    print("=" * 88)

    print()

    print(
        "Este diagnóstico NO modifica V1."
    )

    print(
        "No se ha ajustado ningún parámetro "
        "utilizando el HOLDOUT."
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