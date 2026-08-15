from pathlib import Path

import pandas as pd


# ============================================================
# CONFIGURACIÓN
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"

INPUT_FILE = (
    DATA_DIR
    / "selective_v2_predictions.csv"
)

OUTPUT_FILE = (
    DATA_DIR
    / "selective_v2_fixed_cohort_metrics.csv"
)

RAW_THRESHOLD = 0.70


# ============================================================
# MÉTRICAS
# ============================================================

def brier_score(probabilities, actuals):

    return (
        (
            probabilities
            - actuals
        ) ** 2
    ).mean()


def binary_log_loss(
    probabilities,
    actuals
):

    probabilities = probabilities.clip(
        1e-6,
        1 - 1e-6
    )

    losses = -(
        actuals
        * probabilities.apply(
            lambda p: __import__("math").log(p)
        )
        +
        (1 - actuals)
        * (1 - probabilities).apply(
            lambda p: __import__("math").log(p)
        )
    )

    return losses.mean()


# ============================================================
# RESUMEN
# ============================================================

def summarize(
    df,
    scope,
    market,
    model
):

    probabilities = (
        df[
            "probability"
        ].astype(float)
    )

    actuals = (
        df[
            "actual"
        ].astype(int)
    )

    prediction_mean = (
        probabilities.mean()
    )

    actual_rate = (
        actuals.mean()
    )

    return {
        "scope":
            scope,

        "market":
            market,

        "model":
            model,

        "n":
            len(df),

        "prediction_pct":
            prediction_mean * 100,

        "actual_pct":
            actual_rate * 100,

        "gap_pp":
            abs(
                prediction_mean
                - actual_rate
            ) * 100,

        "brier":
            brier_score(
                probabilities,
                actuals
            ),

        "log_loss":
            binary_log_loss(
                probabilities,
                actuals
            ),
    }


# ============================================================
# PROGRAMA
# ============================================================

def main():

    print("=" * 88)
    print(
        "CulebrIA - FIXED SELECTIVE COHORT TEST"
    )
    print("=" * 88)

    print()
    print(
        "El conjunto de partidos se define "
        "exclusivamente con RAW >= 70%."
    )

    print(
        "Después comparamos todos los métodos "
        "sobre exactamente los mismos partidos."
    )

    df = pd.read_csv(
        INPUT_FILE
    )

    required_models = {
        "RAW",
        "ROLLING_BIAS",
        "LOGIT_OFFSET",
    }

    models_found = set(
        df[
            "model"
        ].astype(str)
    )

    missing = (
        required_models
        - models_found
    )

    if missing:

        print()
        print(
            f"❌ Faltan modelos: "
            f"{sorted(missing)}"
        )

        return

    scopes = [
        "ALL",
        *sorted(
            df[
                "competition"
            ]
            .dropna()
            .astype(str)
            .unique()
        )
    ]

    markets = sorted(
        df[
            "market"
        ]
        .dropna()
        .astype(str)
        .unique()
    )

    output_rows = []

    # ========================================================
    # CADA MERCADO
    # ========================================================

    for market in markets:

        market_df = df[
            df[
                "market"
            ] == market
        ].copy()

        # ----------------------------------------------------
        # COHORTE FIJADA POR RAW
        # ----------------------------------------------------

        raw_df = market_df[
            market_df[
                "model"
            ] == "RAW"
        ].copy()

        raw_cohort = raw_df[
            raw_df[
                "probability"
            ]
            >= RAW_THRESHOLD
        ][
            [
                "competition",
                "match_id",
                "market",
            ]
        ].copy()

        raw_cohort = (
            raw_cohort
            .drop_duplicates()
        )

        print()
        print("=" * 88)
        print(
            f"MERCADO: {market}"
        )
        print("=" * 88)

        print()
        print(
            f"Cohorte RAW >=70%: "
            f"{len(raw_cohort)} partidos"
        )

        # ====================================================
        # SCOPES
        # ====================================================

        for scope in scopes:

            if scope == "ALL":

                cohort_scope = (
                    raw_cohort.copy()
                )

                source_scope = (
                    market_df.copy()
                )

            else:

                cohort_scope = raw_cohort[
                    raw_cohort[
                        "competition"
                    ].astype(str)
                    == scope
                ].copy()

                source_scope = market_df[
                    market_df[
                        "competition"
                    ].astype(str)
                    == scope
                ].copy()

            if cohort_scope.empty:
                continue

            print()
            print(
                f"--- {scope} ---"
            )

            print()

            print(
                f"{'MODELO':<16}"
                f"{'N':>6}"
                f"{'PRED%':>10}"
                f"{'REAL%':>10}"
                f"{'GAP':>9}"
                f"{'BRIER':>10}"
                f"{'LOGLOSS':>11}"
            )

            print(
                "-" * 72
            )

            # =================================================
            # CADA MODELO SOBRE LA MISMA COHORTE
            # =================================================

            for model in [
                "RAW",
                "ROLLING_BIAS",
                "LOGIT_OFFSET",
            ]:

                model_df = source_scope[
                    source_scope[
                        "model"
                    ] == model
                ].copy()

                fixed_df = model_df.merge(
                    cohort_scope,
                    on=[
                        "competition",
                        "match_id",
                        "market",
                    ],
                    how="inner"
                )

                if fixed_df.empty:
                    continue

                result = summarize(
                    df=
                        fixed_df,

                    scope=
                        scope,

                    market=
                        market,

                    model=
                        model
                )

                output_rows.append(
                    result
                )

                print(
                    f"{model:<16}"
                    f"{result['n']:>6}"
                    f"{result['prediction_pct']:>9.2f}%"
                    f"{result['actual_pct']:>9.2f}%"
                    f"{result['gap_pp']:>8.2f}"
                    f"{result['brier']:>10.4f}"
                    f"{result['log_loss']:>11.4f}"
                )

    # ========================================================
    # GUARDAR
    # ========================================================

    output_df = pd.DataFrame(
        output_rows
    )

    output_df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    print()
    print("=" * 88)
    print(
        "FIN"
    )
    print("=" * 88)

    print()
    print(
        "Antiguo HOLDOUT utilizado: NO"
    )

    print(
        "Solicitudes API: 0"
    )

    print(
        "Créditos The Odds API: 0"
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