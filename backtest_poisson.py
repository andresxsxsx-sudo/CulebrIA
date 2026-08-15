import math
from pathlib import Path

import pandas as pd

from src.analysis.poisson_model import (
    calculate_expected_goals,
    calculate_market_probabilities,
    collect_team_records,
    finished_before,
    get_full_time_score,
    parse_api_date
)

from src.api.fdorg_local_history import (
    load_competition_history
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"

OUTPUT_PREDICTIONS = (
    DATA_DIR
    / "backtest_poisson_predictions.csv"
)

OUTPUT_METRICS = (
    DATA_DIR
    / "backtest_market_metrics.csv"
)

OUTPUT_CALIBRATION = (
    DATA_DIR
    / "backtest_calibration.csv"
)

OUTPUT_SKIPPED = (
    DATA_DIR
    / "backtest_skipped.csv"
)


# Competiciones que actualmente tenemos
# disponibles localmente.
COMPETITIONS = [
    "BSA",
    "PPL",
]


# ============================================================
# REQUISITOS MÍNIMOS
# ============================================================

# Partidos anteriores de la competición.
MIN_LEAGUE_HISTORY = 40

# Partidos anteriores generales de cada equipo.
MIN_TEAM_HISTORY = 5

# Partidos anteriores en la condición
# local / visitante.
MIN_VENUE_HISTORY = 3


# ============================================================
# DEVELOPMENT / HOLDOUT
# ============================================================

# Primer 80 % cronológico:
# podremos usarlo para estudiar y modificar el modelo.
#
# Último 20 %:
# queda reservado como HOLDOUT.
DEVELOPMENT_RATIO = 0.80

# MUY IMPORTANTE:
# todavía NO mostraremos métricas del holdout.
REPORT_HOLDOUT = False


# ============================================================
# LOG LOSS
# ============================================================

EPSILON = 1e-15


# ============================================================
# MERCADOS A EVALUAR
# ============================================================

MARKETS = {
    "HOME_WIN": (
        "p_home_win",
        "y_home_win"
    ),

    "DRAW": (
        "p_draw",
        "y_draw"
    ),

    "AWAY_WIN": (
        "p_away_win",
        "y_away_win"
    ),

    "1X": (
        "p_home_or_draw",
        "y_home_or_draw"
    ),

    "X2": (
        "p_away_or_draw",
        "y_away_or_draw"
    ),

    "OVER_1_5": (
        "p_over15",
        "y_over15"
    ),

    "OVER_2_5": (
        "p_over25",
        "y_over25"
    ),

    "UNDER_3_5": (
        "p_under35",
        "y_under35"
    ),

    "BTTS": (
        "p_btts",
        "y_btts"
    ),

    "HOME_SCORES": (
        "p_home_scores",
        "y_home_scores"
    ),

    "AWAY_SCORES": (
        "p_away_scores",
        "y_away_scores"
    ),
}


# ============================================================
# UTILIDADES MATEMÁTICAS
# ============================================================

def clamp_probability(value):

    return max(
        EPSILON,
        min(
            1.0 - EPSILON,
            float(value)
        )
    )


def binary_brier(
    probability,
    actual
):

    return (
        probability
        - actual
    ) ** 2


def binary_log_loss(
    probability,
    actual
):

    probability = (
        clamp_probability(
            probability
        )
    )

    return -(
        actual
        * math.log(
            probability
        )
        +
        (
            1 - actual
        )
        * math.log(
            1 - probability
        )
    )


# ============================================================
# RESULTADO REAL
# ============================================================

def get_actual_result(match):

    score = get_full_time_score(
        match
    )

    if score is None:
        return None

    home_goals, away_goals = score

    total_goals = (
        home_goals
        + away_goals
    )

    if home_goals > away_goals:

        outcome = "H"

    elif home_goals == away_goals:

        outcome = "D"

    else:

        outcome = "A"

    return {
        "home_goals":
            home_goals,

        "away_goals":
            away_goals,

        "outcome":
            outcome,

        "y_home_win":
            int(
                outcome == "H"
            ),

        "y_draw":
            int(
                outcome == "D"
            ),

        "y_away_win":
            int(
                outcome == "A"
            ),

        "y_home_or_draw":
            int(
                outcome in {
                    "H",
                    "D"
                }
            ),

        "y_away_or_draw":
            int(
                outcome in {
                    "A",
                    "D"
                }
            ),

        "y_over15":
            int(
                total_goals >= 2
            ),

        "y_over25":
            int(
                total_goals >= 3
            ),

        "y_under35":
            int(
                total_goals <= 3
            ),

        "y_btts":
            int(
                home_goals >= 1
                and
                away_goals >= 1
            ),

        "y_home_scores":
            int(
                home_goals >= 1
            ),

        "y_away_scores":
            int(
                away_goals >= 1
            ),
    }


# ============================================================
# COMPROBAR MUESTRA ANTERIOR
# ============================================================

def check_history_requirements(
    matches,
    home_team,
    away_team,
    kickoff
):

    league_history = finished_before(
        matches,
        kickoff
    )

    if (
        len(league_history)
        < MIN_LEAGUE_HISTORY
    ):

        return (
            False,
            "LIGA_INSUFICIENTE",
            {
                "league":
                    len(
                        league_history
                    )
            }
        )

    # --------------------------------------------------------
    # HISTÓRICO GENERAL
    # --------------------------------------------------------

    home_overall = (
        collect_team_records(
            matches=
                matches,

            team_name=
                home_team,

            kickoff=
                kickoff,

            venue=
                None
        )
    )

    away_overall = (
        collect_team_records(
            matches=
                matches,

            team_name=
                away_team,

            kickoff=
                kickoff,

            venue=
                None
        )
    )

    # --------------------------------------------------------
    # LOCAL / VISITANTE
    # --------------------------------------------------------

    home_venue = (
        collect_team_records(
            matches=
                matches,

            team_name=
                home_team,

            kickoff=
                kickoff,

            venue=
                "HOME"
        )
    )

    away_venue = (
        collect_team_records(
            matches=
                matches,

            team_name=
                away_team,

            kickoff=
                kickoff,

            venue=
                "AWAY"
        )
    )

    counts = {
        "league":
            len(
                league_history
            ),

        "home_overall":
            len(
                home_overall
            ),

        "away_overall":
            len(
                away_overall
            ),

        "home_venue":
            len(
                home_venue
            ),

        "away_venue":
            len(
                away_venue
            ),
    }

    if (
        len(home_overall)
        < MIN_TEAM_HISTORY
    ):

        return (
            False,
            "LOCAL_HISTORICO_INSUFICIENTE",
            counts
        )

    if (
        len(away_overall)
        < MIN_TEAM_HISTORY
    ):

        return (
            False,
            "VISITANTE_HISTORICO_INSUFICIENTE",
            counts
        )

    if (
        len(home_venue)
        < MIN_VENUE_HISTORY
    ):

        return (
            False,
            "LOCAL_VENUE_INSUFICIENTE",
            counts
        )

    if (
        len(away_venue)
        < MIN_VENUE_HISTORY
    ):

        return (
            False,
            "VISITANTE_VENUE_INSUFICIENTE",
            counts
        )

    return (
        True,
        "OK",
        counts
    )


# ============================================================
# CONSTRUIR UNA PREDICCIÓN HISTÓRICA
# ============================================================

def build_backtest_prediction(
    competition,
    match,
    matches
):

    if (
        match.get("status")
        != "FINISHED"
    ):
        return None, None

    kickoff = parse_api_date(
        match.get(
            "utcDate"
        )
    )

    if kickoff is None:

        return None, {
            "competition":
                competition,

            "match_id":
                match.get(
                    "id"
                ),

            "reason":
                "FECHA_INVALIDA"
        }

    home_team = (
        match
        .get(
            "homeTeam",
            {}
        )
        .get(
            "name",
            ""
        )
    )

    away_team = (
        match
        .get(
            "awayTeam",
            {}
        )
        .get(
            "name",
            ""
        )
    )

    if (
        not home_team
        or not away_team
    ):

        return None, {
            "competition":
                competition,

            "match_id":
                match.get(
                    "id"
                ),

            "reason":
                "EQUIPO_INVALIDO"
        }

    # --------------------------------------------------------
    # RESULTADO REAL
    # --------------------------------------------------------

    actual = get_actual_result(
        match
    )

    if actual is None:

        return None, {
            "competition":
                competition,

            "match_id":
                match.get(
                    "id"
                ),

            "reason":
                "MARCADOR_INVALIDO"
        }

    # --------------------------------------------------------
    # MUESTRA
    # --------------------------------------------------------

    (
        eligible,
        reason,
        counts
    ) = check_history_requirements(
        matches=
            matches,

        home_team=
            home_team,

        away_team=
            away_team,

        kickoff=
            kickoff
    )

    if not eligible:

        skipped = {
            "competition":
                competition,

            "match_id":
                match.get(
                    "id"
                ),

            "kickoff":
                kickoff.isoformat(),

            "home":
                home_team,

            "away":
                away_team,

            "reason":
                reason,

            "league_history":
                counts.get(
                    "league",
                    0
                ),

            "home_history":
                counts.get(
                    "home_overall",
                    0
                ),

            "away_history":
                counts.get(
                    "away_overall",
                    0
                ),

            "home_venue":
                counts.get(
                    "home_venue",
                    0
                ),

            "away_venue":
                counts.get(
                    "away_venue",
                    0
                ),
        }

        return None, skipped

    # --------------------------------------------------------
    # MODELO
    # --------------------------------------------------------

    try:

        model = (
            calculate_expected_goals(
                matches=
                    matches,

                home_team=
                    home_team,

                away_team=
                    away_team,

                kickoff=
                    kickoff
            )
        )

        probabilities = (
            calculate_market_probabilities(
                model[
                    "lambda_home"
                ],
                model[
                    "lambda_away"
                ]
            )
        )

    except Exception as error:

        skipped = {
            "competition":
                competition,

            "match_id":
                match.get(
                    "id"
                ),

            "kickoff":
                kickoff.isoformat(),

            "home":
                home_team,

            "away":
                away_team,

            "reason":
                "ERROR_MODELO",

            "error":
                str(error)
        }

        return None, skipped

    # --------------------------------------------------------
    # RESULTADO
    # --------------------------------------------------------

    best_score = (
        probabilities[
            "best_score"
        ]
    )

    row = {
        "competition":
            competition,

        "match_id":
            match.get(
                "id"
            ),

        "kickoff":
            kickoff.isoformat(),

        "home":
            home_team,

        "away":
            away_team,

        # ----------------------------------------------------
        # MUESTRA DISPONIBLE EN ESE MOMENTO
        # ----------------------------------------------------

        "league_history":
            counts[
                "league"
            ],

        "home_history":
            counts[
                "home_overall"
            ],

        "away_history":
            counts[
                "away_overall"
            ],

        "home_venue_history":
            counts[
                "home_venue"
            ],

        "away_venue_history":
            counts[
                "away_venue"
            ],

        # ----------------------------------------------------
        # LAMBDAS
        # ----------------------------------------------------

        "lambda_home":
            model[
                "lambda_home"
            ],

        "lambda_away":
            model[
                "lambda_away"
            ],

        # ----------------------------------------------------
        # PROBABILIDADES 1X2
        # ----------------------------------------------------

        "p_home_win":
            probabilities[
                "home_win"
            ],

        "p_draw":
            probabilities[
                "draw"
            ],

        "p_away_win":
            probabilities[
                "away_win"
            ],

        # ----------------------------------------------------
        # DOBLE OPORTUNIDAD
        # ----------------------------------------------------

        "p_home_or_draw":
            probabilities[
                "home_or_draw"
            ],

        "p_away_or_draw":
            probabilities[
                "away_or_draw"
            ],

        # ----------------------------------------------------
        # MERCADOS DE GOLES
        # ----------------------------------------------------

        "p_over15":
            probabilities[
                "over_15"
            ],

        "p_over25":
            probabilities[
                "over_25"
            ],

        "p_under35":
            probabilities[
                "under_35"
            ],

        "p_btts":
            probabilities[
                "btts"
            ],

        "p_home_scores":
            probabilities[
                "home_scores"
            ],

        "p_away_scores":
            probabilities[
                "away_scores"
            ],

        # ----------------------------------------------------
        # MARCADOR MODAL
        # ----------------------------------------------------

        "predicted_score":
            (
                f"{best_score[0]}"
                f"-"
                f"{best_score[1]}"
            ),

        # ----------------------------------------------------
        # RESULTADO REAL
        # ----------------------------------------------------

        "home_goals":
            actual[
                "home_goals"
            ],

        "away_goals":
            actual[
                "away_goals"
            ],

        "actual_outcome":
            actual[
                "outcome"
            ],
    }

    # Añadir todos los labels binarios.
    for key, value in actual.items():

        if key.startswith(
            "y_"
        ):

            row[key] = value

    return row, None


# ============================================================
# ASIGNAR DEVELOPMENT / HOLDOUT
# ============================================================

def assign_temporal_split(df):

    df = df.copy()

    df[
        "split"
    ] = ""

    for competition in (
        df[
            "competition"
        ].unique()
    ):

        mask = (
            df[
                "competition"
            ]
            == competition
        )

        group = (
            df[
                mask
            ]
            .sort_values(
                "kickoff"
            )
        )

        total = len(
            group
        )

        if total == 0:
            continue

        development_count = int(
            total
            * DEVELOPMENT_RATIO
        )

        # Garantizar que exista al menos
        # una observación holdout.
        if (
            total >= 2
            and
            development_count >= total
        ):

            development_count = (
                total - 1
            )

        development_indices = (
            group
            .iloc[
                :development_count
            ]
            .index
        )

        holdout_indices = (
            group
            .iloc[
                development_count:
            ]
            .index
        )

        df.loc[
            development_indices,
            "split"
        ] = "DEVELOPMENT"

        df.loc[
            holdout_indices,
            "split"
        ] = "HOLDOUT"

    return df


# ============================================================
# MULTICLASS 1X2
# ============================================================

def calculate_1x2_metrics(df):

    if df.empty:
        return {}

    brier_values = []
    log_losses = []

    correct = 0

    actual_counts = {
        "H": 0,
        "D": 0,
        "A": 0,
    }

    for _, row in df.iterrows():

        probabilities = {
            "H":
                float(
                    row[
                        "p_home_win"
                    ]
                ),

            "D":
                float(
                    row[
                        "p_draw"
                    ]
                ),

            "A":
                float(
                    row[
                        "p_away_win"
                    ]
                ),
        }

        actual = row[
            "actual_outcome"
        ]

        actual_counts[
            actual
        ] += 1

        # ----------------------------------------------------
        # BRIER MULTICLASE
        # ----------------------------------------------------

        brier = 0.0

        for outcome in [
            "H",
            "D",
            "A"
        ]:

            target = int(
                actual == outcome
            )

            brier += (
                probabilities[
                    outcome
                ]
                - target
            ) ** 2

        brier_values.append(
            brier
        )

        # ----------------------------------------------------
        # LOG LOSS
        # ----------------------------------------------------

        actual_probability = (
            clamp_probability(
                probabilities[
                    actual
                ]
            )
        )

        log_losses.append(
            -math.log(
                actual_probability
            )
        )

        # ----------------------------------------------------
        # ACCURACY
        # ----------------------------------------------------

        prediction = max(
            probabilities,
            key=
                probabilities.get
        )

        if prediction == actual:
            correct += 1

    total = len(
        df
    )

    model_brier = (
        sum(
            brier_values
        )
        / total
    )

    model_log_loss = (
        sum(
            log_losses
        )
        / total
    )

    accuracy = (
        correct
        / total
    )

    # --------------------------------------------------------
    # BASELINE EMPÍRICO
    # --------------------------------------------------------

    baseline_probabilities = {
        outcome:
            actual_counts[
                outcome
            ]
            / total

        for outcome
        in [
            "H",
            "D",
            "A"
        ]
    }

    baseline_briers = []
    baseline_log_losses = []

    for _, row in df.iterrows():

        actual = row[
            "actual_outcome"
        ]

        brier = 0.0

        for outcome in [
            "H",
            "D",
            "A"
        ]:

            target = int(
                actual == outcome
            )

            brier += (
                baseline_probabilities[
                    outcome
                ]
                - target
            ) ** 2

        baseline_briers.append(
            brier
        )

        baseline_log_losses.append(
            -math.log(
                clamp_probability(
                    baseline_probabilities[
                        actual
                    ]
                )
            )
        )

    baseline_brier = (
        sum(
            baseline_briers
        )
        / total
    )

    baseline_log_loss = (
        sum(
            baseline_log_losses
        )
        / total
    )

    if baseline_brier > 0:

        brier_skill = (
            1
            - (
                model_brier
                / baseline_brier
            )
        )

    else:

        brier_skill = 0.0

    return {
        "n":
            total,

        "accuracy":
            accuracy,

        "brier":
            model_brier,

        "log_loss":
            model_log_loss,

        "baseline_brier":
            baseline_brier,

        "baseline_log_loss":
            baseline_log_loss,

        "brier_skill":
            brier_skill,

        "home_rate":
            baseline_probabilities[
                "H"
            ],

        "draw_rate":
            baseline_probabilities[
                "D"
            ],

        "away_rate":
            baseline_probabilities[
                "A"
            ],
    }


# ============================================================
# CALIBRACIÓN DE UN MERCADO
# ============================================================

def calculate_calibration(
    df,
    market_name,
    probability_column,
    actual_column
):

    bins = {
        number: []
        for number in range(
            10
        )
    }

    for _, row in df.iterrows():

        probability = float(
            row[
                probability_column
            ]
        )

        actual = int(
            row[
                actual_column
            ]
        )

        bin_number = min(
            int(
                probability
                * 10
            ),
            9
        )

        bins[
            bin_number
        ].append(
            (
                probability,
                actual
            )
        )

    rows = []

    total = len(
        df
    )

    ece = 0.0

    for bin_number in range(
        10
    ):

        observations = bins[
            bin_number
        ]

        if not observations:
            continue

        probabilities = [
            item[0]
            for item
            in observations
        ]

        actuals = [
            item[1]
            for item
            in observations
        ]

        count = len(
            observations
        )

        average_probability = (
            sum(
                probabilities
            )
            / count
        )

        actual_rate = (
            sum(
                actuals
            )
            / count
        )

        gap = abs(
            average_probability
            - actual_rate
        )

        weight = (
            count
            / total
        )

        ece += (
            weight
            * gap
        )

        rows.append(
            {
                "market":
                    market_name,

                "bin_start_pct":
                    bin_number
                    * 10,

                "bin_end_pct":
                    (
                        bin_number
                        + 1
                    )
                    * 10,

                "n":
                    count,

                "avg_prediction_pct":
                    average_probability
                    * 100,

                "actual_rate_pct":
                    actual_rate
                    * 100,

                "absolute_gap_pct":
                    gap
                    * 100,
            }
        )

    return rows, ece


# ============================================================
# MÉTRICAS BINARIAS
# ============================================================

def calculate_market_metrics(
    df
):

    metric_rows = []
    calibration_rows = []

    for (
        market_name,
        (
            probability_column,
            actual_column
        )
    ) in MARKETS.items():

        probabilities = (
            df[
                probability_column
            ].astype(float)
        )

        actuals = (
            df[
                actual_column
            ].astype(int)
        )

        count = len(
            df
        )

        if count == 0:
            continue

        # ----------------------------------------------------
        # BRIER
        # ----------------------------------------------------

        brier_values = [
            binary_brier(
                probability,
                actual
            )

            for probability, actual
            in zip(
                probabilities,
                actuals
            )
        ]

        brier = (
            sum(
                brier_values
            )
            / count
        )

        # ----------------------------------------------------
        # LOG LOSS
        # ----------------------------------------------------

        log_losses = [
            binary_log_loss(
                probability,
                actual
            )

            for probability, actual
            in zip(
                probabilities,
                actuals
            )
        ]

        log_loss = (
            sum(
                log_losses
            )
            / count
        )

        # ----------------------------------------------------
        # FRECUENCIA REAL
        # ----------------------------------------------------

        prevalence = (
            actuals.mean()
        )

        mean_prediction = (
            probabilities.mean()
        )

        # ----------------------------------------------------
        # BASELINE CONSTANTE
        # ----------------------------------------------------

        baseline_brier = (
            prevalence
            * (
                1
                - prevalence
            )
        )

        if baseline_brier > 0:

            brier_skill = (
                1
                - (
                    brier
                    / baseline_brier
                )
            )

        else:

            brier_skill = 0.0

        # ----------------------------------------------------
        # CALIBRACIÓN
        # ----------------------------------------------------

        (
            market_calibration,
            ece
        ) = calculate_calibration(
            df=
                df,

            market_name=
                market_name,

            probability_column=
                probability_column,

            actual_column=
                actual_column
        )

        calibration_rows.extend(
            market_calibration
        )

        # ----------------------------------------------------
        # GUARDAR
        # ----------------------------------------------------

        metric_rows.append(
            {
                "market":
                    market_name,

                "n":
                    count,

                "mean_prediction_pct":
                    mean_prediction
                    * 100,

                "actual_rate_pct":
                    prevalence
                    * 100,

                "brier":
                    brier,

                "baseline_brier":
                    baseline_brier,

                "brier_skill":
                    brier_skill,

                "log_loss":
                    log_loss,

                "ece":
                    ece,
            }
        )

    return (
        pd.DataFrame(
            metric_rows
        ),
        pd.DataFrame(
            calibration_rows
        )
    )


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    print("=" * 78)
    print(
        "CulebrIA - BACKTEST POISSON V1"
    )
    print("=" * 78)

    all_predictions = []
    skipped_rows = []

    # ========================================================
    # RECORRER COMPETICIONES
    # ========================================================

    for competition in COMPETITIONS:

        print()
        print("=" * 78)

        print(
            f"COMPETICIÓN: "
            f"{competition}"
        )

        history = (
            load_competition_history(
                competition
            )
        )

        matches = history[
            "matches"
        ]

        print(
            f"Archivos locales: "
            f"{history['file_count']}"
        )

        for file_name in (
            history[
                "files"
            ]
        ):

            print(
                f"  - {file_name}"
            )

        finished_matches = [
            match
            for match in matches

            if (
                match.get(
                    "status"
                )
                == "FINISHED"
            )
        ]

        finished_matches.sort(
            key=lambda item:
                item.get(
                    "utcDate",
                    ""
                )
        )

        print(
            f"Partidos finalizados: "
            f"{len(finished_matches)}"
        )

        generated = 0
        skipped = 0

        # ====================================================
        # WALK-FORWARD
        # ====================================================

        for index, match in enumerate(
            finished_matches,
            start=1
        ):

            (
                prediction,
                skip
            ) = build_backtest_prediction(
                competition=
                    competition,

                match=
                    match,

                matches=
                    matches
            )

            if prediction is not None:

                all_predictions.append(
                    prediction
                )

                generated += 1

            elif skip is not None:

                skipped_rows.append(
                    skip
                )

                skipped += 1

            # Indicador de progreso
            if (
                index % 50
                == 0
            ):

                print(
                    f"Procesados "
                    f"{index}/"
                    f"{len(finished_matches)}"
                )

        print()

        print(
            f"Predicciones válidas: "
            f"{generated}"
        )

        print(
            f"Omitidos por muestra: "
            f"{skipped}"
        )

    # ========================================================
    # DATAFRAME
    # ========================================================

    predictions_df = pd.DataFrame(
        all_predictions
    )

    if predictions_df.empty:

        print()
        print(
            "❌ No se generaron "
            "predicciones históricas."
        )

        return

    predictions_df = (
        predictions_df
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

    # ========================================================
    # SPLIT TEMPORAL
    # ========================================================

    predictions_df = (
        assign_temporal_split(
            predictions_df
        )
    )

    development_df = (
        predictions_df[
            predictions_df[
                "split"
            ]
            == "DEVELOPMENT"
        ].copy()
    )

    holdout_df = (
        predictions_df[
            predictions_df[
                "split"
            ]
            == "HOLDOUT"
        ].copy()
    )

    # ========================================================
    # GUARDAR PREDICCIONES
    # ========================================================

    predictions_df.to_csv(
        OUTPUT_PREDICTIONS,
        index=False,
        encoding="utf-8-sig"
    )

    pd.DataFrame(
        skipped_rows
    ).to_csv(
        OUTPUT_SKIPPED,
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # MÉTRICAS DEVELOPMENT
    # ========================================================

    one_x_two = (
        calculate_1x2_metrics(
            development_df
        )
    )

    (
        metrics_df,
        calibration_df
    ) = calculate_market_metrics(
        development_df
    )

    metrics_df.to_csv(
        OUTPUT_METRICS,
        index=False,
        encoding="utf-8-sig"
    )

    calibration_df.to_csv(
        OUTPUT_CALIBRATION,
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # RESUMEN DE MUESTRA
    # ========================================================

    print()
    print("=" * 78)
    print(
        "MUESTRA DEL BACKTEST"
    )
    print("=" * 78)

    print()

    print(
        f"Predicciones totales: "
        f"{len(predictions_df)}"
    )

    print(
        f"DEVELOPMENT: "
        f"{len(development_df)}"
    )

    print(
        f"HOLDOUT bloqueado: "
        f"{len(holdout_df)}"
    )

    print(
        f"Partidos omitidos: "
        f"{len(skipped_rows)}"
    )

    print()

    for competition in COMPETITIONS:

        comp_df = (
            predictions_df[
                predictions_df[
                    "competition"
                ]
                == competition
            ]
        )

        comp_dev = (
            comp_df[
                comp_df[
                    "split"
                ]
                == "DEVELOPMENT"
            ]
        )

        comp_holdout = (
            comp_df[
                comp_df[
                    "split"
                ]
                == "HOLDOUT"
            ]
        )

        print(
            f"{competition}: "
            f"{len(comp_df)} total | "
            f"{len(comp_dev)} development | "
            f"{len(comp_holdout)} holdout"
        )

    # ========================================================
    # 1X2 DEVELOPMENT
    # ========================================================

    print()
    print("=" * 78)
    print(
        "1X2 - DEVELOPMENT"
    )
    print("=" * 78)

    print()

    print(
        f"N: "
        f"{one_x_two['n']}"
    )

    print(
        f"Accuracy: "
        f"{one_x_two['accuracy'] * 100:.2f}%"
    )

    print(
        f"Brier multiclass: "
        f"{one_x_two['brier']:.4f}"
    )

    print(
        f"Brier baseline: "
        f"{one_x_two['baseline_brier']:.4f}"
    )

    print(
        f"Brier Skill Score: "
        f"{one_x_two['brier_skill'] * 100:.2f}%"
    )

    print(
        f"Log Loss: "
        f"{one_x_two['log_loss']:.4f}"
    )

    print(
        f"Log Loss baseline: "
        f"{one_x_two['baseline_log_loss']:.4f}"
    )

    print()

    print(
        "Frecuencias reales:"
    )

    print(
        f"Local: "
        f"{one_x_two['home_rate'] * 100:.2f}%"
    )

    print(
        f"Empate: "
        f"{one_x_two['draw_rate'] * 100:.2f}%"
    )

    print(
        f"Visitante: "
        f"{one_x_two['away_rate'] * 100:.2f}%"
    )

    # ========================================================
    # MERCADOS DEVELOPMENT
    # ========================================================

    print()
    print("=" * 78)
    print(
        "MERCADOS - DEVELOPMENT"
    )
    print("=" * 78)

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
        metrics_df.iterrows()
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
    # HOLDOUT
    # ========================================================

    print()
    print("=" * 78)
    print(
        "HOLDOUT"
    )
    print("=" * 78)

    print()

    if REPORT_HOLDOUT:

        print(
            "⚠️ REPORT_HOLDOUT está activado."
        )

        holdout_1x2 = (
            calculate_1x2_metrics(
                holdout_df
            )
        )

        print()

        print(
            f"N: "
            f"{holdout_1x2['n']}"
        )

        print(
            f"Accuracy: "
            f"{holdout_1x2['accuracy'] * 100:.2f}%"
        )

        print(
            f"Brier: "
            f"{holdout_1x2['brier']:.4f}"
        )

        print(
            f"Log Loss: "
            f"{holdout_1x2['log_loss']:.4f}"
        )

    else:

        print(
            "🔒 HOLDOUT BLOQUEADO"
        )

        print()

        print(
            "No se muestran sus métricas "
            "para evitar ajustar el modelo "
            "contra los datos reservados."
        )

        print()

        print(
            f"Partidos reservados: "
            f"{len(holdout_df)}"
        )

    # ========================================================
    # ARCHIVOS
    # ========================================================

    print()
    print("=" * 78)
    print(
        "BACKTEST FINALIZADO"
    )
    print("=" * 78)

    print()

    print(
        "Solicitudes API realizadas: 0"
    )

    print()

    print(
        "Archivos creados:"
    )

    print(
        f"1. {OUTPUT_PREDICTIONS}"
    )

    print(
        f"2. {OUTPUT_METRICS}"
    )

    print(
        f"3. {OUTPUT_CALIBRATION}"
    )

    print(
        f"4. {OUTPUT_SKIPPED}"
    )

    print()

    print(
        "⚠️ No modificar todavía "
        "los parámetros del modelo."
    )


if __name__ == "__main__":
    main()