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

OUTPUT_PREDICTIONS = (
    DATA_DIR
    / "selective_v2_predictions.csv"
)

OUTPUT_METRICS = (
    DATA_DIR
    / "selective_v2_metrics.csv"
)


# ============================================================
# WALK-FORWARD
# ============================================================

MIN_PRIOR_MATCHES = 40
ROLLING_WINDOW = 60

# Regularización.
SHRINK_MATCHES = 20

# Señal de menor volatilidad.
HIGH_PROBABILITY_THRESHOLD = 0.70

EPSILON = 1e-6


# ============================================================
# MERCADOS QUE SOBREVIVIERON V1
# ============================================================

MARKETS = {
    "1X": {
        "probability":
            "p_home_or_draw",

        "actual":
            "y_home_or_draw",
    },

    "AWAY_SCORES": {
        "probability":
            "p_away_scores",

        "actual":
            "y_away_scores",
    },
}


# ============================================================
# UTILIDADES
# ============================================================

def clip_probability(value):

    return max(
        EPSILON,
        min(
            1 - EPSILON,
            float(value)
        )
    )


def logit(probability):

    probability = clip_probability(
        probability
    )

    return math.log(
        probability
        /
        (
            1 - probability
        )
    )


def sigmoid(value):

    if value >= 0:

        exponential = math.exp(
            -value
        )

        return (
            1
            /
            (
                1
                +
                exponential
            )
        )

    exponential = math.exp(
        value
    )

    return (
        exponential
        /
        (
            1
            +
            exponential
        )
    )


# ============================================================
# MÉTODO 1 - CORRECCIÓN DE SESGO EN PROBABILIDAD
# ============================================================

def rolling_bias_probability(
    raw_probability,
    prior_probabilities,
    prior_actuals
):

    n = len(
        prior_probabilities
    )

    residual_bias = (
        prior_actuals.mean()
        -
        prior_probabilities.mean()
    )

    shrink_weight = (
        n
        /
        (
            n
            +
            SHRINK_MATCHES
        )
    )

    correction = (
        shrink_weight
        *
        residual_bias
    )

    adjusted = (
        raw_probability
        +
        correction
    )

    return clip_probability(
        adjusted
    )


# ============================================================
# MÉTODO 2 - LOGISTIC INTERCEPT RECALIBRATION
# ============================================================

def estimate_logit_offset(
    prior_probabilities,
    prior_actuals
):

    target_rate = float(
        prior_actuals.mean()
    )

    # --------------------------------------------------------
    # Casos extremos.
    # --------------------------------------------------------

    if target_rate <= 0:

        return -5.0

    if target_rate >= 1:

        return 5.0

    logits = [
        logit(
            probability
        )
        for probability
        in prior_probabilities
    ]

    # --------------------------------------------------------
    # Buscamos delta tal que:
    #
    # promedio(sigmoid(logit(p) + delta))
    # ≈ tasa observada.
    #
    # Bisección evita depender de scipy.
    # --------------------------------------------------------

    low = -5.0
    high = 5.0

    for _ in range(
        80
    ):

        middle = (
            low
            +
            high
        ) / 2

        adjusted_mean = (
            sum(
                sigmoid(
                    value
                    +
                    middle
                )
                for value
                in logits
            )
            /
            len(
                logits
            )
        )

        if adjusted_mean < target_rate:

            low = middle

        else:

            high = middle

    delta = (
        low
        +
        high
    ) / 2

    # --------------------------------------------------------
    # SHRINKAGE HACIA 0
    # --------------------------------------------------------

    n = len(
        prior_probabilities
    )

    shrink_weight = (
        n
        /
        (
            n
            +
            SHRINK_MATCHES
        )
    )

    return (
        delta
        *
        shrink_weight
    )


def logit_offset_probability(
    raw_probability,
    delta
):

    adjusted = sigmoid(
        logit(
            raw_probability
        )
        +
        delta
    )

    return clip_probability(
        adjusted
    )


# ============================================================
# MÉTRICAS
# ============================================================

def brier_score(
    probabilities,
    actuals
):

    return (
        (
            probabilities
            -
            actuals
        ) ** 2
    ).mean()


def log_loss(
    probabilities,
    actuals
):

    total = 0.0

    for probability, actual in zip(
        probabilities,
        actuals
    ):

        probability = (
            clip_probability(
                probability
            )
        )

        if int(
            actual
        ) == 1:

            total -= math.log(
                probability
            )

        else:

            total -= math.log(
                1 - probability
            )

    return (
        total
        /
        len(
            probabilities
        )
    )


# ============================================================
# RESUMEN
# ============================================================

def summarize(
    df,
    competition,
    market,
    model
):

    if df.empty:

        return None

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

    mean_probability = (
        probabilities.mean()
    )

    actual_rate = (
        actuals.mean()
    )

    gap = abs(
        mean_probability
        -
        actual_rate
    )

    # --------------------------------------------------------
    # SUBCONJUNTO >= 70 %
    # --------------------------------------------------------

    high_df = df[
        df[
            "probability"
        ]
        >= HIGH_PROBABILITY_THRESHOLD
    ].copy()

    if high_df.empty:

        high_n = 0

        high_prediction = None
        high_actual = None
        high_gap = None
        high_brier = None

    else:

        high_n = len(
            high_df
        )

        high_prediction = (
            high_df[
                "probability"
            ].mean()
        )

        high_actual = (
            high_df[
                "actual"
            ].mean()
        )

        high_gap = abs(
            high_prediction
            -
            high_actual
        )

        high_brier = (
            brier_score(
                probabilities=
                    high_df[
                        "probability"
                    ],

                actuals=
                    high_df[
                        "actual"
                    ]
            )
        )

    return {
        "competition":
            competition,

        "market":
            market,

        "model":
            model,

        "n":
            len(
                df
            ),

        "prediction_pct":
            mean_probability
            * 100,

        "actual_pct":
            actual_rate
            * 100,

        "gap_pp":
            gap
            * 100,

        "brier":
            brier_score(
                probabilities=
                    probabilities,

                actuals=
                    actuals
            ),

        "log_loss":
            log_loss(
                probabilities=
                    probabilities,

                actuals=
                    actuals
            ),

        "high70_n":
            high_n,

        "high70_prediction_pct":
            (
                high_prediction
                * 100
                if high_prediction
                is not None
                else None
            ),

        "high70_actual_pct":
            (
                high_actual
                * 100
                if high_actual
                is not None
                else None
            ),

        "high70_gap_pp":
            (
                high_gap
                * 100
                if high_gap
                is not None
                else None
            ),

        "high70_brier":
            high_brier,
    }


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    print("=" * 94)
    print(
        "CulebrIA - SELECTIVE V2 "
        "CALIBRATION TEST"
    )
    print("=" * 94)

    print()
    print(
        "Solo DEVELOPMENT."
    )

    print(
        "El antiguo HOLDOUT NO será utilizado."
    )

    # ========================================================
    # CARGAR DATOS
    # ========================================================

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

    development = df[
        df[
            "split"
        ] == "DEVELOPMENT"
    ].copy()

    development = (
        development
        .sort_values(
            [
                "competition",
                "kickoff"
            ]
        )
        .reset_index(
            drop=True
        )
    )

    print()
    print(
        f"DEVELOPMENT: "
        f"{len(development)}"
    )

    output_rows = []

    # ========================================================
    # WALK-FORWARD
    # ========================================================

    competitions = sorted(
        development[
            "competition"
        ]
        .dropna()
        .astype(str)
        .unique()
    )

    for competition in competitions:

        competition_df = (
            development[
                development[
                    "competition"
                ].astype(str)
                == competition
            ]
            .sort_values(
                "kickoff"
            )
            .reset_index(
                drop=True
            )
        )

        print()
        print(
            f"{competition}: "
            f"{len(competition_df)} partidos"
        )

        evaluated = 0

        for position in range(
            len(
                competition_df
            )
        ):

            if (
                position
                <
                MIN_PRIOR_MATCHES
            ):

                continue

            start_position = max(
                0,
                position
                -
                ROLLING_WINDOW
            )

            prior_df = (
                competition_df
                .iloc[
                    start_position:
                    position
                ]
                .copy()
            )

            current = (
                competition_df.iloc[
                    position
                ]
            )

            # =================================================
            # CADA MERCADO
            # =================================================

            for (
                market,
                columns
            ) in MARKETS.items():

                probability_column = (
                    columns[
                        "probability"
                    ]
                )

                actual_column = (
                    columns[
                        "actual"
                    ]
                )

                raw_probability = float(
                    current[
                        probability_column
                    ]
                )

                actual = int(
                    current[
                        actual_column
                    ]
                )

                prior_probabilities = (
                    prior_df[
                        probability_column
                    ].astype(float)
                )

                prior_actuals = (
                    prior_df[
                        actual_column
                    ].astype(int)
                )

                # =============================================
                # RAW
                # =============================================

                output_rows.append(
                    {
                        "competition":
                            competition,

                        "match_id":
                            current[
                                "match_id"
                            ],

                        "kickoff":
                            current[
                                "kickoff"
                            ],

                        "home":
                            current[
                                "home"
                            ],

                        "away":
                            current[
                                "away"
                            ],

                        "market":
                            market,

                        "model":
                            "RAW",

                        "probability":
                            raw_probability,

                        "actual":
                            actual,

                        "rolling_n":
                            len(
                                prior_df
                            ),

                        "rolling_actual_rate":
                            prior_actuals.mean(),

                        "rolling_prediction_rate":
                            prior_probabilities.mean(),

                        "calibration_parameter":
                            0.0,
                    }
                )

                # =============================================
                # ROLLING BIAS
                # =============================================

                bias_probability = (
                    rolling_bias_probability(
                        raw_probability=
                            raw_probability,

                        prior_probabilities=
                            prior_probabilities,

                        prior_actuals=
                            prior_actuals
                    )
                )

                bias_parameter = (
                    bias_probability
                    -
                    raw_probability
                )

                output_rows.append(
                    {
                        "competition":
                            competition,

                        "match_id":
                            current[
                                "match_id"
                            ],

                        "kickoff":
                            current[
                                "kickoff"
                            ],

                        "home":
                            current[
                                "home"
                            ],

                        "away":
                            current[
                                "away"
                            ],

                        "market":
                            market,

                        "model":
                            "ROLLING_BIAS",

                        "probability":
                            bias_probability,

                        "actual":
                            actual,

                        "rolling_n":
                            len(
                                prior_df
                            ),

                        "rolling_actual_rate":
                            prior_actuals.mean(),

                        "rolling_prediction_rate":
                            prior_probabilities.mean(),

                        "calibration_parameter":
                            bias_parameter,
                    }
                )

                # =============================================
                # LOGIT OFFSET
                # =============================================

                delta = (
                    estimate_logit_offset(
                        prior_probabilities=
                            prior_probabilities,

                        prior_actuals=
                            prior_actuals
                    )
                )

                offset_probability = (
                    logit_offset_probability(
                        raw_probability=
                            raw_probability,

                        delta=
                            delta
                    )
                )

                output_rows.append(
                    {
                        "competition":
                            competition,

                        "match_id":
                            current[
                                "match_id"
                            ],

                        "kickoff":
                            current[
                                "kickoff"
                            ],

                        "home":
                            current[
                                "home"
                            ],

                        "away":
                            current[
                                "away"
                            ],

                        "market":
                            market,

                        "model":
                            "LOGIT_OFFSET",

                        "probability":
                            offset_probability,

                        "actual":
                            actual,

                        "rolling_n":
                            len(
                                prior_df
                            ),

                        "rolling_actual_rate":
                            prior_actuals.mean(),

                        "rolling_prediction_rate":
                            prior_probabilities.mean(),

                        "calibration_parameter":
                            delta,
                    }
                )

            evaluated += 1

        print(
            f"Walk-forward evaluados: "
            f"{evaluated}"
        )

    # ========================================================
    # GUARDAR PREDICCIONES
    # ========================================================

    predictions_df = pd.DataFrame(
        output_rows
    )

    predictions_df.to_csv(
        OUTPUT_PREDICTIONS,
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # MÉTRICAS
    # ========================================================

    metric_rows = []

    models = [
        "RAW",
        "ROLLING_BIAS",
        "LOGIT_OFFSET",
    ]

    scopes = [
        "ALL",
        *competitions,
    ]

    for scope in scopes:

        if scope == "ALL":

            scope_df = (
                predictions_df.copy()
            )

        else:

            scope_df = predictions_df[
                predictions_df[
                    "competition"
                ].astype(str)
                == scope
            ].copy()

        for market in MARKETS:

            for model in models:

                block = scope_df[
                    (
                        scope_df[
                            "market"
                        ]
                        == market
                    )
                    &
                    (
                        scope_df[
                            "model"
                        ]
                        == model
                    )
                ].copy()

                result = summarize(
                    df=
                        block,

                    competition=
                        scope,

                    market=
                        market,

                    model=
                        model
                )

                if result is not None:

                    metric_rows.append(
                        result
                    )

    metrics_df = pd.DataFrame(
        metric_rows
    )

    metrics_df.to_csv(
        OUTPUT_METRICS,
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # MOSTRAR RESULTADOS
    # ========================================================

    for scope in scopes:

        print()
        print("=" * 94)
        print(
            f"{scope}"
        )
        print("=" * 94)

        for market in MARKETS:

            print()
            print(
                f"--- {market} ---"
            )

            block = metrics_df[
                (
                    metrics_df[
                        "competition"
                    ]
                    == scope
                )
                &
                (
                    metrics_df[
                        "market"
                    ]
                    == market
                )
            ]

            print()

            print(
                f"{'MODELO':<16}"
                f"{'N':>5}"
                f"{'BRIER':>10}"
                f"{'LOGLOSS':>10}"
                f"{'PRED/REAL':>16}"
                f"{'GAP':>9}"
            )

            print(
                "-" * 66
            )

            for _, row in (
                block.iterrows()
            ):

                pair = (
                    f"{row['prediction_pct']:.1f}"
                    f"/"
                    f"{row['actual_pct']:.1f}"
                )

                print(
                    f"{row['model']:<16}"
                    f"{int(row['n']):>5}"
                    f"{row['brier']:>10.4f}"
                    f"{row['log_loss']:>10.4f}"
                    f"{pair:>16}"
                    f"{row['gap_pp']:>8.2f}"
                )

            print()
            print(
                "SEÑALES >= 70 %"
            )

            print()

            print(
                f"{'MODELO':<16}"
                f"{'N70':>6}"
                f"{'PRED70':>11}"
                f"{'REAL70':>11}"
                f"{'GAP70':>10}"
                f"{'BRIER70':>11}"
            )

            print(
                "-" * 65
            )

            for _, row in (
                block.iterrows()
            ):

                n70 = int(
                    row[
                        "high70_n"
                    ]
                )

                if n70 == 0:

                    print(
                        f"{row['model']:<16}"
                        f"{0:>6}"
                        f"{'-':>11}"
                        f"{'-':>11}"
                        f"{'-':>10}"
                        f"{'-':>11}"
                    )

                    continue

                print(
                    f"{row['model']:<16}"
                    f"{n70:>6}"
                    f"{row['high70_prediction_pct']:>10.2f}%"
                    f"{row['high70_actual_pct']:>10.2f}%"
                    f"{row['high70_gap_pp']:>9.2f}"
                    f"{row['high70_brier']:>11.4f}"
                )

    # ========================================================
    # FIN
    # ========================================================

    print()
    print("=" * 94)
    print(
        "IMPORTANTE"
    )
    print("=" * 94)

    print()

    print(
        "El antiguo HOLDOUT no fue utilizado."
    )

    print(
        "No se han consultado cuotas."
    )

    print(
        "No se ha realizado ninguna llamada API."
    )

    print()

    print(
        "Archivos:"
    )

    print(
        OUTPUT_PREDICTIONS
    )

    print(
        OUTPUT_METRICS
    )


if __name__ == "__main__":
    main()