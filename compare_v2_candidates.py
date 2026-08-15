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
    / "v2_candidate_predictions.csv"
)

OUTPUT_METRICS = (
    DATA_DIR
    / "v2_candidate_metrics.csv"
)


# Solo DEVELOPMENT.
# El HOLDOUT de V1 queda retirado.
MIN_PRIOR_MATCHES = 40
ROLLING_WINDOW = 60

# Regularización de la corrección dinámica.
SHRINK_MATCHES = 20

# Evitamos correcciones extremas.
MIN_SCALE = 0.75
MAX_SCALE = 1.25

MAX_GOALS = 10
EPSILON = 1e-12


# ============================================================
# POISSON BÁSICO
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
        lambda_value ** goals
        /
        math.factorial(
            goals
        )
    )


def independent_matrix(
    lambda_home,
    lambda_away
):

    home_probs = [
        poisson_probability(
            goals,
            lambda_home
        )
        for goals in range(
            MAX_GOALS + 1
        )
    ]

    away_probs = [
        poisson_probability(
            goals,
            lambda_away
        )
        for goals in range(
            MAX_GOALS + 1
        )
    ]

    matrix = []

    for home_goals in range(
        MAX_GOALS + 1
    ):

        row = []

        for away_goals in range(
            MAX_GOALS + 1
        ):

            row.append(
                home_probs[
                    home_goals
                ]
                *
                away_probs[
                    away_goals
                ]
            )

        matrix.append(
            row
        )

    return normalize_matrix(
        matrix
    )


# ============================================================
# NORMALIZAR MATRIZ
# ============================================================

def normalize_matrix(
    matrix
):

    total = sum(
        sum(row)
        for row in matrix
    )

    if total <= 0:

        return matrix

    return [
        [
            value / total
            for value in row
        ]
        for row in matrix
    ]


# ============================================================
# DIXON-COLES
# ============================================================

def dixon_coles_tau(
    home_goals,
    away_goals,
    lambda_home,
    lambda_away,
    rho
):

    if (
        home_goals == 0
        and
        away_goals == 0
    ):

        return (
            1
            -
            lambda_home
            * lambda_away
            * rho
        )

    if (
        home_goals == 0
        and
        away_goals == 1
    ):

        return (
            1
            +
            lambda_home
            * rho
        )

    if (
        home_goals == 1
        and
        away_goals == 0
    ):

        return (
            1
            +
            lambda_away
            * rho
        )

    if (
        home_goals == 1
        and
        away_goals == 1
    ):

        return (
            1
            -
            rho
        )

    return 1.0


def dixon_coles_matrix(
    lambda_home,
    lambda_away,
    rho
):

    matrix = (
        independent_matrix(
            lambda_home,
            lambda_away
        )
    )

    adjusted = []

    for home_goals in range(
        MAX_GOALS + 1
    ):

        row = []

        for away_goals in range(
            MAX_GOALS + 1
        ):

            tau = dixon_coles_tau(
                home_goals=
                    home_goals,

                away_goals=
                    away_goals,

                lambda_home=
                    lambda_home,

                lambda_away=
                    lambda_away,

                rho=
                    rho
            )

            value = (
                matrix[
                    home_goals
                ][
                    away_goals
                ]
                *
                tau
            )

            # Evitamos probabilidades negativas
            # para combinaciones extremas de rho.
            value = max(
                value,
                EPSILON
            )

            row.append(
                value
            )

        adjusted.append(
            row
        )

    return normalize_matrix(
        adjusted
    )


# ============================================================
# POISSON BIVARIADO
# ============================================================

def bivariate_probability(
    home_goals,
    away_goals,
    lambda_home,
    lambda_away,
    shared_fraction
):

    # --------------------------------------------------------
    # COMPONENTE COMPARTIDO
    #
    # shared = c * min(lambda_home, lambda_away)
    #
    # Así garantizamos:
    #
    # alpha >= 0
    # beta  >= 0
    #
    # y conservamos aproximadamente las medias marginales.
    # --------------------------------------------------------

    shared = (
        shared_fraction
        * min(
            lambda_home,
            lambda_away
        )
    )

    alpha = (
        lambda_home
        - shared
    )

    beta = (
        lambda_away
        - shared
    )

    if (
        alpha < 0
        or
        beta < 0
        or
        shared < 0
    ):

        return EPSILON

    probability = 0.0

    maximum_k = min(
        home_goals,
        away_goals
    )

    exponential = math.exp(
        -(
            alpha
            +
            beta
            +
            shared
        )
    )

    for k in range(
        maximum_k + 1
    ):

        term = (
            (
                alpha
                ** (
                    home_goals
                    - k
                )
            )
            *
            (
                beta
                ** (
                    away_goals
                    - k
                )
            )
            *
            (
                shared
                ** k
            )
            /
            (
                math.factorial(
                    home_goals
                    - k
                )
                *
                math.factorial(
                    away_goals
                    - k
                )
                *
                math.factorial(
                    k
                )
            )
        )

        probability += term

    return (
        exponential
        * probability
    )


def bivariate_matrix(
    lambda_home,
    lambda_away,
    shared_fraction
):

    matrix = []

    for home_goals in range(
        MAX_GOALS + 1
    ):

        row = []

        for away_goals in range(
            MAX_GOALS + 1
        ):

            value = (
                bivariate_probability(
                    home_goals=
                        home_goals,

                    away_goals=
                        away_goals,

                    lambda_home=
                        lambda_home,

                    lambda_away=
                        lambda_away,

                    shared_fraction=
                        shared_fraction
                )
            )

            row.append(
                value
            )

        matrix.append(
            row
        )

    return normalize_matrix(
        matrix
    )


# ============================================================
# MERCADOS DESDE MATRIZ
# ============================================================

def matrix_markets(
    matrix
):

    home_win = 0.0
    draw = 0.0
    away_win = 0.0

    away_zero = 0.0

    for home_goals in range(
        len(matrix)
    ):

        for away_goals in range(
            len(
                matrix[
                    home_goals
                ]
            )
        ):

            probability = (
                matrix[
                    home_goals
                ][
                    away_goals
                ]
            )

            if (
                home_goals
                >
                away_goals
            ):

                home_win += (
                    probability
                )

            elif (
                home_goals
                ==
                away_goals
            ):

                draw += (
                    probability
                )

            else:

                away_win += (
                    probability
                )

            if away_goals == 0:

                away_zero += (
                    probability
                )

    return {
        "p_home_win":
            home_win,

        "p_draw":
            draw,

        "p_away_win":
            away_win,

        "p_1x":
            home_win
            +
            draw,

        "p_x2":
            draw
            +
            away_win,

        "p_away_scores":
            1
            -
            away_zero,
    }


# ============================================================
# CORRECCIÓN DINÁMICA DE LAMBDA
# ============================================================

def dynamic_scales(
    prior_df
):

    n = len(
        prior_df
    )

    predicted_home = (
        prior_df[
            "lambda_home"
        ].sum()
    )

    predicted_away = (
        prior_df[
            "lambda_away"
        ].sum()
    )

    actual_home = (
        prior_df[
            "home_goals"
        ].sum()
    )

    actual_away = (
        prior_df[
            "away_goals"
        ].sum()
    )

    if predicted_home > 0:

        raw_home_scale = (
            actual_home
            /
            predicted_home
        )

    else:

        raw_home_scale = 1.0

    if predicted_away > 0:

        raw_away_scale = (
            actual_away
            /
            predicted_away
        )

    else:

        raw_away_scale = 1.0

    # --------------------------------------------------------
    # SHRINKAGE HACIA 1.0
    # --------------------------------------------------------

    weight = (
        n
        /
        (
            n
            +
            SHRINK_MATCHES
        )
    )

    home_scale = (
        1.0
        +
        weight
        * (
            raw_home_scale
            -
            1.0
        )
    )

    away_scale = (
        1.0
        +
        weight
        * (
            raw_away_scale
            -
            1.0
        )
    )

    home_scale = max(
        MIN_SCALE,
        min(
            MAX_SCALE,
            home_scale
        )
    )

    away_scale = max(
        MIN_SCALE,
        min(
            MAX_SCALE,
            away_scale
        )
    )

    return (
        home_scale,
        away_scale
    )


# ============================================================
# LOG-LIKELIHOOD DIXON-COLES
# ============================================================

def dc_log_likelihood(
    prior_df,
    home_scale,
    away_scale,
    rho
):

    total = 0.0

    for _, row in (
        prior_df.iterrows()
    ):

        lambda_home = (
            float(
                row[
                    "lambda_home"
                ]
            )
            *
            home_scale
        )

        lambda_away = (
            float(
                row[
                    "lambda_away"
                ]
            )
            *
            away_scale
        )

        matrix = (
            dixon_coles_matrix(
                lambda_home=
                    lambda_home,

                lambda_away=
                    lambda_away,

                rho=
                    rho
            )
        )

        home_goals = int(
            row[
                "home_goals"
            ]
        )

        away_goals = int(
            row[
                "away_goals"
            ]
        )

        if (
            home_goals
            <= MAX_GOALS
            and
            away_goals
            <= MAX_GOALS
        ):

            probability = (
                matrix[
                    home_goals
                ][
                    away_goals
                ]
            )

        else:

            probability = (
                EPSILON
            )

        total += math.log(
            max(
                probability,
                EPSILON
            )
        )

    return total


def estimate_rho(
    prior_df,
    home_scale,
    away_scale
):

    best_rho = 0.0
    best_score = float(
        "-inf"
    )

    # -0.20 ... +0.20
    for step in range(
        -20,
        21
    ):

        rho = (
            step
            / 100
        )

        score = (
            dc_log_likelihood(
                prior_df=
                    prior_df,

                home_scale=
                    home_scale,

                away_scale=
                    away_scale,

                rho=
                    rho
            )
        )

        if score > best_score:

            best_score = score
            best_rho = rho

    return best_rho


# ============================================================
# LOG-LIKELIHOOD BIVARIADO
# ============================================================

def bp_log_likelihood(
    prior_df,
    home_scale,
    away_scale,
    shared_fraction
):

    total = 0.0

    for _, row in (
        prior_df.iterrows()
    ):

        lambda_home = (
            float(
                row[
                    "lambda_home"
                ]
            )
            *
            home_scale
        )

        lambda_away = (
            float(
                row[
                    "lambda_away"
                ]
            )
            *
            away_scale
        )

        home_goals = int(
            row[
                "home_goals"
            ]
        )

        away_goals = int(
            row[
                "away_goals"
            ]
        )

        probability = (
            bivariate_probability(
                home_goals=
                    home_goals,

                away_goals=
                    away_goals,

                lambda_home=
                    lambda_home,

                lambda_away=
                    lambda_away,

                shared_fraction=
                    shared_fraction
            )
        )

        total += math.log(
            max(
                probability,
                EPSILON
            )
        )

    return total


def estimate_shared_fraction(
    prior_df,
    home_scale,
    away_scale
):

    best_fraction = 0.0
    best_score = float(
        "-inf"
    )

    # 0.00 ... 0.50
    # pasos de 0.025
    for step in range(
        0,
        21
    ):

        fraction = (
            step
            * 0.025
        )

        score = (
            bp_log_likelihood(
                prior_df=
                    prior_df,

                home_scale=
                    home_scale,

                away_scale=
                    away_scale,

                shared_fraction=
                    fraction
            )
        )

        if score > best_score:

            best_score = score
            best_fraction = fraction

    return best_fraction


# ============================================================
# MÉTRICAS
# ============================================================

def multiclass_brier(
    df
):

    total = (
        (
            df[
                "p_home_win"
            ]
            -
            df[
                "y_home_win"
            ]
        ) ** 2
        +
        (
            df[
                "p_draw"
            ]
            -
            df[
                "y_draw"
            ]
        ) ** 2
        +
        (
            df[
                "p_away_win"
            ]
            -
            df[
                "y_away_win"
            ]
        ) ** 2
    )

    return total.mean()


def multiclass_log_loss(
    df
):

    probabilities = []

    for _, row in (
        df.iterrows()
    ):

        if int(
            row[
                "y_home_win"
            ]
        ) == 1:

            probability = (
                row[
                    "p_home_win"
                ]
            )

        elif int(
            row[
                "y_draw"
            ]
        ) == 1:

            probability = (
                row[
                    "p_draw"
                ]
            )

        else:

            probability = (
                row[
                    "p_away_win"
                ]
            )

        probabilities.append(
            max(
                float(
                    probability
                ),
                EPSILON
            )
        )

    return (
        -sum(
            math.log(
                probability
            )
            for probability
            in probabilities
        )
        /
        len(
            probabilities
        )
    )


def binary_brier(
    predicted,
    actual
):

    return (
        (
            predicted
            -
            actual
        ) ** 2
    ).mean()


def calculate_metrics(
    df,
    model_name,
    competition
):

    if df.empty:

        return None

    predicted_class = (
        df[
            [
                "p_home_win",
                "p_draw",
                "p_away_win"
            ]
        ]
        .idxmax(
            axis=1
        )
    )

    actual_class = (
        df[
            [
                "y_home_win",
                "y_draw",
                "y_away_win"
            ]
        ]
        .idxmax(
            axis=1
        )
    )

    accuracy = (
        predicted_class
        ==
        actual_class
    ).mean()

    return {
        "competition":
            competition,

        "model":
            model_name,

        "n":
            len(
                df
            ),

        "accuracy_pct":
            accuracy
            * 100,

        "brier_1x2":
            multiclass_brier(
                df
            ),

        "log_loss_1x2":
            multiclass_log_loss(
                df
            ),

        "draw_prediction_pct":
            df[
                "p_draw"
            ].mean()
            * 100,

        "draw_actual_pct":
            df[
                "y_draw"
            ].mean()
            * 100,

        "draw_brier":
            binary_brier(
                df[
                    "p_draw"
                ],

                df[
                    "y_draw"
                ]
            ),

        "one_x_prediction_pct":
            df[
                "p_1x"
            ].mean()
            * 100,

        "one_x_actual_pct":
            df[
                "y_home_or_draw"
            ].mean()
            * 100,

        "one_x_brier":
            binary_brier(
                df[
                    "p_1x"
                ],

                df[
                    "y_home_or_draw"
                ]
            ),

        "away_scores_prediction_pct":
            df[
                "p_away_scores"
            ].mean()
            * 100,

        "away_scores_actual_pct":
            df[
                "y_away_scores"
            ].mean()
            * 100,

        "away_scores_brier":
            binary_brier(
                df[
                    "p_away_scores"
                ],

                df[
                    "y_away_scores"
                ]
            ),
    }


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    print("=" * 92)
    print(
        "CulebrIA - COMPARACION "
        "DE CANDIDATOS V2"
    )
    print("=" * 92)

    print()
    print(
        "IMPORTANTE:"
    )

    print(
        "Solo se utilizará DEVELOPMENT."
    )

    print(
        "El HOLDOUT de V1 permanece "
        "fuera de esta comparación."
    )

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
        f"DEVELOPMENT total: "
        f"{len(development)}"
    )

    output_rows = []

    # ========================================================
    # WALK-FORWARD POR COMPETICIÓN
    # ========================================================

    for competition in sorted(
        development[
            "competition"
        ]
        .dropna()
        .astype(str)
        .unique()
    ):

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
        print("=" * 92)
        print(
            f"{competition}"
        )
        print("=" * 92)

        print(
            f"Partidos DEVELOPMENT: "
            f"{len(competition_df)}"
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
                competition_df
                .iloc[
                    position
                ]
            )

            # =================================================
            # PARÁMETROS DINÁMICOS
            # =================================================

            (
                home_scale,
                away_scale
            ) = dynamic_scales(
                prior_df
            )

            lambda_home = (
                float(
                    current[
                        "lambda_home"
                    ]
                )
                *
                home_scale
            )

            lambda_away = (
                float(
                    current[
                        "lambda_away"
                    ]
                )
                *
                away_scale
            )

            rho = estimate_rho(
                prior_df=
                    prior_df,

                home_scale=
                    home_scale,

                away_scale=
                    away_scale
            )

            shared_fraction = (
                estimate_shared_fraction(
                    prior_df=
                        prior_df,

                    home_scale=
                        home_scale,

                    away_scale=
                        away_scale
                )
            )

            # =================================================
            # MODELO 0 - V1 ORIGINAL
            # =================================================

            original = {
                "p_home_win":
                    float(
                        current[
                            "p_home_win"
                        ]
                    ),

                "p_draw":
                    float(
                        current[
                            "p_draw"
                        ]
                    ),

                "p_away_win":
                    float(
                        current[
                            "p_away_win"
                        ]
                    ),

                "p_1x":
                    float(
                        current[
                            "p_home_or_draw"
                        ]
                    ),

                "p_x2":
                    float(
                        current[
                            "p_away_or_draw"
                        ]
                    ),

                "p_away_scores":
                    float(
                        current[
                            "p_away_scores"
                        ]
                    ),
            }

            # =================================================
            # MODELO A - DINÁMICO
            # =================================================

            dynamic_matrix = (
                independent_matrix(
                    lambda_home=
                        lambda_home,

                    lambda_away=
                        lambda_away
                )
            )

            dynamic = (
                matrix_markets(
                    dynamic_matrix
                )
            )

            # =================================================
            # MODELO B - DINÁMICO + DIXON-COLES
            # =================================================

            dc_matrix = (
                dixon_coles_matrix(
                    lambda_home=
                        lambda_home,

                    lambda_away=
                        lambda_away,

                    rho=
                        rho
                )
            )

            dynamic_dc = (
                matrix_markets(
                    dc_matrix
                )
            )

            # =================================================
            # MODELO C - DINÁMICO + BIVARIADO
            # =================================================

            bp_matrix = (
                bivariate_matrix(
                    lambda_home=
                        lambda_home,

                    lambda_away=
                        lambda_away,

                    shared_fraction=
                        shared_fraction
                )
            )

            dynamic_bp = (
                matrix_markets(
                    bp_matrix
                )
            )

            models = {
                "V1_RAW":
                    original,

                "V2_DYNAMIC":
                    dynamic,

                "V2_DYNAMIC_DC":
                    dynamic_dc,

                "V2_DYNAMIC_BP":
                    dynamic_bp,
            }

            # =================================================
            # GUARDAR PREDICCIONES
            # =================================================

            for (
                model_name,
                prediction
            ) in models.items():

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

                        "model":
                            model_name,

                        "home_scale":
                            home_scale,

                        "away_scale":
                            away_scale,

                        "rho":
                            (
                                rho
                                if
                                model_name
                                ==
                                "V2_DYNAMIC_DC"
                                else None
                            ),

                        "shared_fraction":
                            (
                                shared_fraction
                                if
                                model_name
                                ==
                                "V2_DYNAMIC_BP"
                                else None
                            ),

                        "lambda_home":
                            (
                                float(
                                    current[
                                        "lambda_home"
                                    ]
                                )
                                if
                                model_name
                                ==
                                "V1_RAW"
                                else
                                lambda_home
                            ),

                        "lambda_away":
                            (
                                float(
                                    current[
                                        "lambda_away"
                                    ]
                                )
                                if
                                model_name
                                ==
                                "V1_RAW"
                                else
                                lambda_away
                            ),

                        "p_home_win":
                            prediction[
                                "p_home_win"
                            ],

                        "p_draw":
                            prediction[
                                "p_draw"
                            ],

                        "p_away_win":
                            prediction[
                                "p_away_win"
                            ],

                        "p_1x":
                            prediction[
                                "p_1x"
                            ],

                        "p_x2":
                            prediction[
                                "p_x2"
                            ],

                        "p_away_scores":
                            prediction[
                                "p_away_scores"
                            ],

                        "home_goals":
                            current[
                                "home_goals"
                            ],

                        "away_goals":
                            current[
                                "away_goals"
                            ],

                        "y_home_win":
                            current[
                                "y_home_win"
                            ],

                        "y_draw":
                            current[
                                "y_draw"
                            ],

                        "y_away_win":
                            current[
                                "y_away_win"
                            ],

                        "y_home_or_draw":
                            current[
                                "y_home_or_draw"
                            ],

                        "y_away_or_draw":
                            current[
                                "y_away_or_draw"
                            ],

                        "y_away_scores":
                            current[
                                "y_away_scores"
                            ],
                    }
                )

            evaluated += 1

        print(
            f"Partidos evaluados walk-forward: "
            f"{evaluated}"
        )

    # ========================================================
    # DATAFRAME
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

    model_names = [
        "V1_RAW",
        "V2_DYNAMIC",
        "V2_DYNAMIC_DC",
        "V2_DYNAMIC_BP",
    ]

    # --------------------------------------------------------
    # GLOBAL
    # --------------------------------------------------------

    for model_name in model_names:

        model_df = predictions_df[
            predictions_df[
                "model"
            ] == model_name
        ].copy()

        row = calculate_metrics(
            df=
                model_df,

            model_name=
                model_name,

            competition=
                "ALL"
        )

        if row is not None:

            metric_rows.append(
                row
            )

    # --------------------------------------------------------
    # POR COMPETICIÓN
    # --------------------------------------------------------

    for competition in sorted(
        predictions_df[
            "competition"
        ]
        .dropna()
        .astype(str)
        .unique()
    ):

        for model_name in (
            model_names
        ):

            model_df = predictions_df[
                (
                    predictions_df[
                        "competition"
                    ].astype(str)
                    == competition
                )
                &
                (
                    predictions_df[
                        "model"
                    ]
                    == model_name
                )
            ].copy()

            row = calculate_metrics(
                df=
                    model_df,

                model_name=
                    model_name,

                competition=
                    competition
            )

            if row is not None:

                metric_rows.append(
                    row
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
    # MOSTRAR
    # ========================================================

    print()
    print("=" * 92)
    print(
        "COMPARACION FINAL - DEVELOPMENT WALK-FORWARD"
    )
    print("=" * 92)

    for competition in [
        "ALL",
        *sorted(
            predictions_df[
                "competition"
            ]
            .dropna()
            .astype(str)
            .unique()
        )
    ]:

        block = metrics_df[
            metrics_df[
                "competition"
            ]
            == competition
        ]

        print()
        print(
            f"--- {competition} ---"
        )

        print()

        print(
            f"{'MODELO':<18}"
            f"{'N':>5}"
            f"{'BRIER':>10}"
            f"{'LOGLOSS':>10}"
            f"{'DRAW_BR':>10}"
            f"{'1X_BR':>10}"
            f"{'AWSC_BR':>10}"
        )

        print(
            "-" * 73
        )

        for _, row in (
            block.iterrows()
        ):

            print(
                f"{row['model']:<18}"
                f"{int(row['n']):>5}"
                f"{row['brier_1x2']:>10.4f}"
                f"{row['log_loss_1x2']:>10.4f}"
                f"{row['draw_brier']:>10.4f}"
                f"{row['one_x_brier']:>10.4f}"
                f"{row['away_scores_brier']:>10.4f}"
            )

        print()
        print(
            "CALIBRACIÓN MEDIA"
        )

        print()

        print(
            f"{'MODELO':<18}"
            f"{'DRAW P/R':>18}"
            f"{'1X P/R':>18}"
            f"{'AWSC P/R':>18}"
        )

        print(
            "-" * 72
        )

        for _, row in (
            block.iterrows()
        ):

            draw_pair = (
                f"{row['draw_prediction_pct']:.1f}"
                f"/"
                f"{row['draw_actual_pct']:.1f}"
            )

            one_x_pair = (
                f"{row['one_x_prediction_pct']:.1f}"
                f"/"
                f"{row['one_x_actual_pct']:.1f}"
            )

            away_pair = (
                f"{row['away_scores_prediction_pct']:.1f}"
                f"/"
                f"{row['away_scores_actual_pct']:.1f}"
            )

            print(
                f"{row['model']:<18}"
                f"{draw_pair:>18}"
                f"{one_x_pair:>18}"
                f"{away_pair:>18}"
            )

    # ========================================================
    # PARÁMETROS APRENDIDOS
    # ========================================================

    print()
    print("=" * 92)
    print(
        "PARAMETROS ROLLING"
    )
    print("=" * 92)

    for competition in sorted(
        predictions_df[
            "competition"
        ]
        .dropna()
        .astype(str)
        .unique()
    ):

        comp = predictions_df[
            (
                predictions_df[
                    "competition"
                ].astype(str)
                == competition
            )
            &
            (
                predictions_df[
                    "model"
                ]
                ==
                "V2_DYNAMIC_BP"
            )
        ]

        dc_comp = predictions_df[
            (
                predictions_df[
                    "competition"
                ].astype(str)
                == competition
            )
            &
            (
                predictions_df[
                    "model"
                ]
                ==
                "V2_DYNAMIC_DC"
            )
        ]

        print()
        print(
            competition
        )

        print(
            f"Home scale medio: "
            f"{comp['home_scale'].mean():.3f}"
        )

        print(
            f"Away scale medio: "
            f"{comp['away_scale'].mean():.3f}"
        )

        print(
            f"Rho DC medio: "
            f"{dc_comp['rho'].mean():.3f}"
        )

        print(
            f"Shared fraction BP media: "
            f"{comp['shared_fraction'].mean():.3f}"
        )

    # ========================================================
    # FIN
    # ========================================================

    print()
    print("=" * 92)
    print(
        "IMPORTANTE"
    )
    print("=" * 92)

    print()

    print(
        "No se utilizó HOLDOUT "
        "para ajustar ni comparar V2."
    )

    print(
        "Esta prueba sirve para escoger "
        "la arquitectura candidata."
    )

    print()

    print(
        "Solicitudes API realizadas: 0"
    )

    print(
        "Créditos The Odds API utilizados: 0"
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