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
    / "v1_distribution_shift.csv"
)


# ============================================================
# RESUMEN DE UN BLOQUE
# ============================================================

def summarize(
    df,
    scope,
    period
):

    if df.empty:
        return None

    actual_total_goals = (
        df["home_goals"]
        +
        df["away_goals"]
    )

    predicted_total_goals = (
        df["lambda_home"]
        +
        df["lambda_away"]
    )

    return {
        "scope":
            scope,

        "period":
            period,

        "n":
            len(df),

        # ----------------------------------------------------
        # 1X2 - MODELO
        # ----------------------------------------------------

        "pred_home_win_pct":
            df[
                "p_home_win"
            ].mean() * 100,

        "pred_draw_pct":
            df[
                "p_draw"
            ].mean() * 100,

        "pred_away_win_pct":
            df[
                "p_away_win"
            ].mean() * 100,

        # ----------------------------------------------------
        # 1X2 - REAL
        # ----------------------------------------------------

        "real_home_win_pct":
            df[
                "y_home_win"
            ].mean() * 100,

        "real_draw_pct":
            df[
                "y_draw"
            ].mean() * 100,

        "real_away_win_pct":
            df[
                "y_away_win"
            ].mean() * 100,

        # ----------------------------------------------------
        # ERRORES DE CALIBRACIÓN
        # positivo = modelo sobreestima
        # negativo = modelo subestima
        # ----------------------------------------------------

        "home_win_error_pp":
            (
                df[
                    "p_home_win"
                ].mean()
                -
                df[
                    "y_home_win"
                ].mean()
            ) * 100,

        "draw_error_pp":
            (
                df[
                    "p_draw"
                ].mean()
                -
                df[
                    "y_draw"
                ].mean()
            ) * 100,

        "away_win_error_pp":
            (
                df[
                    "p_away_win"
                ].mean()
                -
                df[
                    "y_away_win"
                ].mean()
            ) * 100,

        # ----------------------------------------------------
        # MERCADOS QUE SOBREVIVIERON
        # ----------------------------------------------------

        "pred_1x_pct":
            df[
                "p_home_or_draw"
            ].mean() * 100,

        "real_1x_pct":
            df[
                "y_home_or_draw"
            ].mean() * 100,

        "pred_away_scores_pct":
            df[
                "p_away_scores"
            ].mean() * 100,

        "real_away_scores_pct":
            df[
                "y_away_scores"
            ].mean() * 100,

        # ----------------------------------------------------
        # GOLES
        # ----------------------------------------------------

        "lambda_home":
            df[
                "lambda_home"
            ].mean(),

        "actual_home_goals":
            df[
                "home_goals"
            ].mean(),

        "lambda_away":
            df[
                "lambda_away"
            ].mean(),

        "actual_away_goals":
            df[
                "away_goals"
            ].mean(),

        "pred_total_goals":
            predicted_total_goals.mean(),

        "actual_total_goals":
            actual_total_goals.mean(),
    }


# ============================================================
# IMPRIMIR BLOQUE
# ============================================================

def print_block(
    title,
    row
):

    if row is None:

        print()
        print(
            f"{title}: SIN DATOS"
        )

        return

    print()
    print("=" * 86)
    print(title)
    print("=" * 86)

    print()

    print(
        f"N: "
        f"{row['n']}"
    )

    print()

    print(
        "1X2"
    )

    print(
        f"{'':<16}"
        f"{'MODELO':>12}"
        f"{'REAL':>12}"
        f"{'ERROR':>12}"
    )

    print(
        "-" * 52
    )

    print(
        f"{'HOME WIN':<16}"
        f"{row['pred_home_win_pct']:>11.2f}%"
        f"{row['real_home_win_pct']:>11.2f}%"
        f"{row['home_win_error_pp']:>+11.2f}"
    )

    print(
        f"{'DRAW':<16}"
        f"{row['pred_draw_pct']:>11.2f}%"
        f"{row['real_draw_pct']:>11.2f}%"
        f"{row['draw_error_pp']:>+11.2f}"
    )

    print(
        f"{'AWAY WIN':<16}"
        f"{row['pred_away_win_pct']:>11.2f}%"
        f"{row['real_away_win_pct']:>11.2f}%"
        f"{row['away_win_error_pp']:>+11.2f}"
    )

    print()

    print(
        "MERCADOS CONSERVADOS"
    )

    print(
        f"1X: "
        f"modelo "
        f"{row['pred_1x_pct']:.2f}% "
        f"| real "
        f"{row['real_1x_pct']:.2f}%"
    )

    print(
        f"AWAY_SCORES: "
        f"modelo "
        f"{row['pred_away_scores_pct']:.2f}% "
        f"| real "
        f"{row['real_away_scores_pct']:.2f}%"
    )

    print()

    print(
        "GOLES"
    )

    print(
        f"Home λ: "
        f"{row['lambda_home']:.3f} "
        f"| goles reales: "
        f"{row['actual_home_goals']:.3f}"
    )

    print(
        f"Away λ: "
        f"{row['lambda_away']:.3f} "
        f"| goles reales: "
        f"{row['actual_away_goals']:.3f}"
    )

    print(
        f"Total λ: "
        f"{row['pred_total_goals']:.3f} "
        f"| total real: "
        f"{row['actual_total_goals']:.3f}"
    )


# ============================================================
# COMPARAR DEVELOPMENT VS HOLDOUT
# ============================================================

def print_shift(
    development,
    holdout
):

    print()
    print("=" * 86)
    print(
        "CAMBIO DEVELOPMENT -> HOLDOUT"
    )
    print("=" * 86)

    print()

    metrics = [
        (
            "HOME WIN real",
            "real_home_win_pct",
            "pp"
        ),
        (
            "DRAW real",
            "real_draw_pct",
            "pp"
        ),
        (
            "AWAY WIN real",
            "real_away_win_pct",
            "pp"
        ),
        (
            "1X real",
            "real_1x_pct",
            "pp"
        ),
        (
            "AWAY_SCORES real",
            "real_away_scores_pct",
            "pp"
        ),
        (
            "Goles home",
            "actual_home_goals",
            ""
        ),
        (
            "Goles away",
            "actual_away_goals",
            ""
        ),
        (
            "Goles totales",
            "actual_total_goals",
            ""
        ),
    ]

    for (
        label,
        column,
        suffix
    ) in metrics:

        change = (
            holdout[column]
            -
            development[column]
        )

        if suffix == "pp":

            print(
                f"{label:<22}"
                f"{change:>+8.2f} pp"
            )

        else:

            print(
                f"{label:<22}"
                f"{change:>+8.3f}"
            )


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    print("=" * 86)
    print(
        "CulebrIA - DIAGNOSTICO "
        "DE DISTRIBUTION SHIFT V1"
    )
    print("=" * 86)

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

    # ========================================================
    # ESCALA
    # ========================================================

    probability_columns = [
        "p_home_win",
        "p_draw",
        "p_away_win",
        "p_home_or_draw",
        "p_away_scores",
    ]

    minimum = (
        df[
            probability_columns
        ]
        .min()
        .min()
    )

    maximum = (
        df[
            probability_columns
        ]
        .max()
        .max()
    )

    print()
    print(
        f"Probabilidad mínima: "
        f"{minimum:.6f}"
    )

    print(
        f"Probabilidad máxima: "
        f"{maximum:.6f}"
    )

    if not (
        minimum >= 0
        and
        maximum <= 1
    ):

        print()
        print(
            "❌ Escala inesperada."
        )

        return

    # ========================================================
    # SPLITS GLOBALES
    # ========================================================

    development_df = df[
        df[
            "split"
        ] == "DEVELOPMENT"
    ].copy()

    holdout_df = df[
        df[
            "split"
        ] == "HOLDOUT"
    ].copy()

    development_summary = summarize(
        development_df,
        scope="ALL",
        period="DEVELOPMENT"
    )

    holdout_summary = summarize(
        holdout_df,
        scope="ALL",
        period="HOLDOUT"
    )

    print_block(
        "TODAS LAS COMPETICIONES - DEVELOPMENT",
        development_summary
    )

    print_block(
        "TODAS LAS COMPETICIONES - HOLDOUT",
        holdout_summary
    )

    print_shift(
        development_summary,
        holdout_summary
    )

    # ========================================================
    # FILAS PARA CSV
    # ========================================================

    output_rows = [
        development_summary,
        holdout_summary,
    ]

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

        comp_dev = competition_df[
            competition_df[
                "split"
            ]
            == "DEVELOPMENT"
        ].copy()

        comp_holdout = competition_df[
            competition_df[
                "split"
            ]
            == "HOLDOUT"
        ].copy()

        dev_summary = summarize(
            comp_dev,
            scope=competition,
            period="DEVELOPMENT"
        )

        holdout_summary_comp = summarize(
            comp_holdout,
            scope=competition,
            period="HOLDOUT"
        )

        print_block(
            f"{competition} - DEVELOPMENT",
            dev_summary
        )

        print_block(
            f"{competition} - HOLDOUT",
            holdout_summary_comp
        )

        if (
            dev_summary is not None
            and
            holdout_summary_comp is not None
        ):

            print_shift(
                dev_summary,
                holdout_summary_comp
            )

        if dev_summary is not None:

            output_rows.append(
                dev_summary
            )

        if holdout_summary_comp is not None:

            output_rows.append(
                holdout_summary_comp
            )

        # ====================================================
        # VENTANA DEVELOPMENT DEL MISMO TAMAÑO
        # QUE EL HOLDOUT
        #
        # Esto ayuda a comprobar si el cambio
        # ya estaba apareciendo ANTES del HOLDOUT.
        # ====================================================

        holdout_n = len(
            comp_holdout
        )

        if (
            holdout_n > 0
            and
            len(comp_dev) > 0
        ):

            recent_dev = (
                comp_dev
                .sort_values(
                    "kickoff"
                )
                .tail(
                    min(
                        holdout_n,
                        len(comp_dev)
                    )
                )
                .copy()
            )

            recent_summary = summarize(
                recent_dev,
                scope=competition,
                period="RECENT_DEVELOPMENT"
            )

            print_block(
                (
                    f"{competition} - "
                    f"DEVELOPMENT RECIENTE "
                    f"(N comparable al HOLDOUT)"
                ),
                recent_summary
            )

            output_rows.append(
                recent_summary
            )

    # ========================================================
    # GUARDAR
    # ========================================================

    output_df = pd.DataFrame(
        [
            row
            for row in output_rows
            if row is not None
        ]
    )

    output_df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # RECORDATORIO
    # ========================================================

    print()
    print("=" * 86)
    print(
        "IMPORTANTE"
    )
    print("=" * 86)

    print()

    print(
        "Este diagnóstico NO modifica "
        "ningún parámetro."
    )

    print(
        "Los 82 partidos HOLDOUT ya están "
        "consumidos y NO serán utilizados "
        "como nueva validación de V2."
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