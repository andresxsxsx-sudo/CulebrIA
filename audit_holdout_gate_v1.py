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
    / "holdout_v1_gate_signals_corrected.csv"
)

OUTPUT_FILE = (
    DATA_DIR
    / "holdout_v1_gate_audit.csv"
)


# ============================================================
# UTILIDADES
# ============================================================

EPSILON = 1e-15


def brier_score(
    probabilities,
    actuals
):

    return (
        (
            probabilities
            - actuals
        ) ** 2
    ).mean()


def log_loss(
    probabilities,
    actuals
):

    probabilities = (
        probabilities
        .clip(
            EPSILON,
            1 - EPSILON
        )
    )

    losses = -(
        actuals
        * probabilities.apply(
            math.log
        )
        +
        (
            1 - actuals
        )
        * (
            1 - probabilities
        ).apply(
            math.log
        )
    )

    return losses.mean()


def wilson_interval(
    successes,
    n,
    z=1.96
):

    if n == 0:

        return (
            None,
            None
        )

    p = (
        successes
        / n
    )

    denominator = (
        1
        +
        z ** 2
        / n
    )

    center = (
        p
        +
        z ** 2
        / (
            2 * n
        )
    ) / denominator

    margin = (
        z
        * math.sqrt(
            p
            * (
                1 - p
            )
            / n
            +
            z ** 2
            / (
                4
                * n ** 2
            )
        )
        / denominator
    )

    return (
        center - margin,
        center + margin
    )


# ============================================================
# RESUMIR GRUPO
# ============================================================

def summarize_group(
    group_name,
    df
):

    n = len(
        df
    )

    unique_matches = (
        df[
            "match_id"
        ].nunique()
    )

    successes = int(
        df[
            "actual"
        ].sum()
    )

    prediction_mean = (
        df[
            "model_probability"
        ].mean()
    )

    actual_rate = (
        df[
            "actual"
        ].mean()
    )

    calibration_gap = abs(
        prediction_mean
        - actual_rate
    )

    model_brier = (
        brier_score(
            probabilities=
                df[
                    "model_probability"
                ],

            actuals=
                df[
                    "actual"
                ]
        )
    )

    model_log_loss = (
        log_loss(
            probabilities=
                df[
                    "model_probability"
                ],

            actuals=
                df[
                    "actual"
                ]
        )
    )

    # --------------------------------------------------------
    # PROBABILIDAD EMPÍRICA DEL BIN
    # APRENDIDA ÚNICAMENTE EN DEVELOPMENT
    # --------------------------------------------------------

    bin_probability = (
        df[
            "development_bin_actual_pct"
        ]
        / 100
    )

    bin_brier = (
        brier_score(
            probabilities=
                bin_probability,

            actuals=
                df[
                    "actual"
                ]
        )
    )

    bin_log_loss = (
        log_loss(
            probabilities=
                bin_probability,

            actuals=
                df[
                    "actual"
                ]
        )
    )

    ci_low, ci_high = (
        wilson_interval(
            successes=
                successes,

            n=
                n
        )
    )

    return {
        "group":
            group_name,

        "n_signals":
            n,

        "unique_matches":
            unique_matches,

        "hits":
            successes,

        "misses":
            n - successes,

        "prediction_pct":
            prediction_mean * 100,

        "actual_pct":
            actual_rate * 100,

        "gap_pp":
            calibration_gap * 100,

        "actual_ci95_low_pct":
            ci_low * 100,

        "actual_ci95_high_pct":
            ci_high * 100,

        "model_brier":
            model_brier,

        "development_bin_brier":
            bin_brier,

        "model_log_loss":
            model_log_loss,

        "development_bin_log_loss":
            bin_log_loss,
    }


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    print("=" * 86)
    print(
        "CulebrIA - AUDITORIA FINAL "
        "DEL RELIABILITY GATE V1"
    )
    print("=" * 86)

    df = pd.read_csv(
        INPUT_FILE
    )

    if df.empty:

        print()
        print(
            "❌ El archivo de señales está vacío."
        )

        return

    # ========================================================
    # INFORMACIÓN GENERAL
    # ========================================================

    total_signals = len(
        df
    )

    unique_matches = (
        df[
            "match_id"
        ].nunique()
    )

    duplicate_signals = (
        total_signals
        - unique_matches
    )

    print()
    print(
        f"Señales: "
        f"{total_signals}"
    )

    print(
        f"Partidos únicos: "
        f"{unique_matches}"
    )

    print(
        f"Señales adicionales "
        f"sobre partidos repetidos: "
        f"{duplicate_signals}"
    )

    # ========================================================
    # PARTIDOS CON MÁS DE UNA SEÑAL
    # ========================================================

    match_counts = (
        df.groupby(
            "match_id"
        )
        .size()
        .sort_values(
            ascending=False
        )
    )

    repeated_matches = (
        match_counts[
            match_counts > 1
        ]
    )

    print()
    print("=" * 86)
    print(
        "PARTIDOS CON MULTIPLES SEÑALES"
    )
    print("=" * 86)

    print()

    if repeated_matches.empty:

        print(
            "Ningún partido tiene "
            "más de una señal."
        )

    else:

        print(
            f"Partidos con más de una señal: "
            f"{len(repeated_matches)}"
        )

        print()

        for match_id, count in (
            repeated_matches.items()
        ):

            match_rows = df[
                df[
                    "match_id"
                ] == match_id
            ]

            first = (
                match_rows.iloc[0]
            )

            markets = ", ".join(
                match_rows[
                    "market"
                ].astype(str)
            )

            print(
                f"{first['home']} "
                f"vs "
                f"{first['away']}"
            )

            print(
                f"Señales: "
                f"{count}"
            )

            print(
                f"Mercados: "
                f"{markets}"
            )

            print(
                "-" * 60
            )

    # ========================================================
    # RESUMEN
    # ========================================================

    summaries = []

    summaries.append(
        summarize_group(
            group_name=
                "ALL",

            df=
                df
        )
    )

    for market in sorted(
        df[
            "market"
        ].unique()
    ):

        market_df = df[
            df[
                "market"
            ] == market
        ].copy()

        summaries.append(
            summarize_group(
                group_name=
                    market,

                df=
                    market_df
            )
        )

    summary_df = pd.DataFrame(
        summaries
    )

    summary_df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # TERMINAL
    # ========================================================

    print()
    print("=" * 86)
    print(
        "METRICAS SELECTIVAS"
    )
    print("=" * 86)

    print()

    print(
        f"{'GRUPO':<15}"
        f"{'N':>5}"
        f"{'UNIQ':>6}"
        f"{'PRED%':>9}"
        f"{'REAL%':>9}"
        f"{'GAP':>8}"
        f"{'BRIER':>10}"
        f"{'BIN_BR':>10}"
    )

    print(
        "-" * 72
    )

    for _, row in (
        summary_df.iterrows()
    ):

        print(
            f"{row['group']:<15}"
            f"{int(row['n_signals']):>5}"
            f"{int(row['unique_matches']):>6}"
            f"{row['prediction_pct']:>9.2f}"
            f"{row['actual_pct']:>9.2f}"
            f"{row['gap_pp']:>8.2f}"
            f"{row['model_brier']:>10.4f}"
            f"{row['development_bin_brier']:>10.4f}"
        )

    # ========================================================
    # INTERVALOS DE CONFIANZA
    # ========================================================

    print()
    print("=" * 86)
    print(
        "INTERVALOS 95% - FRECUENCIA REAL"
    )
    print("=" * 86)

    print()

    for _, row in (
        summary_df.iterrows()
    ):

        print(
            f"{row['group']:<15}"
            f"N={int(row['n_signals']):<4} "
            f"Real={row['actual_pct']:.2f}% "
            f"| IC95% "
            f"{row['actual_ci95_low_pct']:.2f}%"
            f" – "
            f"{row['actual_ci95_high_pct']:.2f}%"
        )

    # ========================================================
    # COMPARACIÓN RAW VS CALIBRACIÓN DEVELOPMENT
    # ========================================================

    print()
    print("=" * 86)
    print(
        "RAW MODEL VS BIN DE DEVELOPMENT"
    )
    print("=" * 86)

    print()

    for _, row in (
        summary_df.iterrows()
    ):

        if (
            row[
                "model_brier"
            ]
            <
            row[
                "development_bin_brier"
            ]
        ):

            brier_winner = (
                "MODELO RAW"
            )

        elif (
            row[
                "model_brier"
            ]
            >
            row[
                "development_bin_brier"
            ]
        ):

            brier_winner = (
                "BIN DEVELOPMENT"
            )

        else:

            brier_winner = (
                "EMPATE"
            )

        print(
            f"{row['group']}:"
        )

        print(
            f"  Brier modelo: "
            f"{row['model_brier']:.4f}"
        )

        print(
            f"  Brier bin: "
            f"{row['development_bin_brier']:.4f}"
        )

        print(
            f"  Mejor: "
            f"{brier_winner}"
        )

        print(
            f"  Log Loss modelo: "
            f"{row['model_log_loss']:.4f}"
        )

        print(
            f"  Log Loss bin: "
            f"{row['development_bin_log_loss']:.4f}"
        )

        print()

    # ========================================================
    # POLÍTICA PROVISIONAL
    # ========================================================

    print("=" * 86)
    print(
        "POLITICA PROVISIONAL V1"
    )
    print("=" * 86)

    print()

    for _, row in (
        summary_df[
            summary_df[
                "group"
            ] != "ALL"
        ].iterrows()
    ):

        market = str(
            row[
                "group"
            ]
        )

        n = int(
            row[
                "n_signals"
            ]
        )

        actual_pct = float(
            row[
                "actual_pct"
            ]
        )

        gap = float(
            row[
                "gap_pp"
            ]
        )

        if (
            n >= 20
            and
            actual_pct >= 70
            and
            gap <= 5
        ):

            status = (
                "MANTENER"
            )

        elif n < 20:

            status = (
                "BLOQUEAR_MUESTRA"
            )

        else:

            status = (
                "BLOQUEAR"
            )

        print(
            f"{market:<15}"
            f"{status}"
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