import math
from datetime import timedelta


# ============================================================
# CONFIGURACIÓN DEL MODELO
# ============================================================

MAX_GOALS = 10

# Usaremos aproximadamente una temporada de información.
MAX_HISTORY_DAYS = 450

# Máximo de partidos específicos local/visitante.
VENUE_MATCH_LIMIT = 10

# Máximo de partidos recientes generales.
RECENT_MATCH_LIMIT = 5

# Fuerza del prior para evitar sobreajuste.
VENUE_PRIOR_MATCHES = 5
RECENT_PRIOR_MATCHES = 10

# Peso del rendimiento estructural local/visitante
# frente a la forma reciente.
VENUE_WEIGHT = 0.85
RECENT_WEIGHT = 0.15

# Límites prudentes para λ.
MIN_LAMBDA = 0.15
MAX_LAMBDA = 4.50


# ============================================================
# UTILIDADES
# ============================================================

def get_full_time_score(match):

    score = match.get(
        "score",
        {}
    )

    full_time = score.get(
        "fullTime",
        {}
    )

    home = full_time.get(
        "home"
    )

    away = full_time.get(
        "away"
    )

    if (
        home is None
        or away is None
    ):
        return None

    return (
        int(home),
        int(away)
    )


def parse_api_date(value):

    if not value:
        return None

    from datetime import datetime

    try:

        return datetime.fromisoformat(
            str(value).replace(
                "Z",
                "+00:00"
            )
        )

    except ValueError:
        return None


def mean(values):

    if not values:
        return 0.0

    return sum(values) / len(values)


# ============================================================
# FILTRAR HISTÓRICO
# ============================================================

def finished_before(
    matches,
    kickoff
):
    """
    Devuelve exclusivamente partidos terminados
    antes del kickoff que estamos intentando predecir.

    También limita la antigüedad para evitar utilizar
    temporadas demasiado antiguas.
    """

    minimum_date = (
        kickoff
        - timedelta(
            days=MAX_HISTORY_DAYS
        )
    )

    result = []

    for match in matches:

        if (
            match.get("status")
            != "FINISHED"
        ):
            continue

        date = parse_api_date(
            match.get(
                "utcDate"
            )
        )

        if date is None:
            continue

        if date >= kickoff:
            continue

        if date < minimum_date:
            continue

        score = get_full_time_score(
            match
        )

        if score is None:
            continue

        result.append(
            match
        )

    result.sort(
        key=lambda item:
            item.get(
                "utcDate",
                ""
            )
    )

    return result


# ============================================================
# PROMEDIOS DE LIGA
# ============================================================

def calculate_league_baseline(
    matches,
    kickoff
):
    """
    Calcula el promedio de goles local y visitante
    de la competición antes del partido objetivo.
    """

    historical = finished_before(
        matches,
        kickoff
    )

    home_goals = []
    away_goals = []

    for match in historical:

        score = get_full_time_score(
            match
        )

        if score is None:
            continue

        home, away = score

        home_goals.append(
            home
        )

        away_goals.append(
            away
        )

    if not home_goals:

        raise RuntimeError(
            "No existen partidos suficientes "
            "para calcular el promedio de liga."
        )

    avg_home = mean(
        home_goals
    )

    avg_away = mean(
        away_goals
    )

    return {
        "matches":
            len(home_goals),

        "home_goals_avg":
            avg_home,

        "away_goals_avg":
            avg_away,

        "goals_per_team_avg":
            (
                avg_home
                + avg_away
            ) / 2,

        "total_goals_avg":
            (
                avg_home
                + avg_away
            ),
    }


# ============================================================
# PARTIDOS DE UN EQUIPO
# ============================================================

def collect_team_records(
    matches,
    team_name,
    kickoff,
    venue=None
):
    """
    venue:
        None
        HOME
        AWAY
    """

    historical = finished_before(
        matches,
        kickoff
    )

    records = []

    for match in historical:

        home_name = (
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

        away_name = (
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

        is_home = (
            home_name
            == team_name
        )

        is_away = (
            away_name
            == team_name
        )

        if not (
            is_home
            or is_away
        ):
            continue

        if (
            venue == "HOME"
            and not is_home
        ):
            continue

        if (
            venue == "AWAY"
            and not is_away
        ):
            continue

        score = get_full_time_score(
            match
        )

        if score is None:
            continue

        home_goals, away_goals = (
            score
        )

        if is_home:

            goals_for = (
                home_goals
            )

            goals_against = (
                away_goals
            )

        else:

            goals_for = (
                away_goals
            )

            goals_against = (
                home_goals
            )

        records.append(
            {
                "date":
                    parse_api_date(
                        match.get(
                            "utcDate"
                        )
                    ),

                "goals_for":
                    goals_for,

                "goals_against":
                    goals_against,
            }
        )

    records.sort(
        key=lambda item:
            item["date"],
        reverse=True
    )

    return records


# ============================================================
# REGULARIZACIÓN
# ============================================================

def regularized_ratio(
    observed_average,
    league_average,
    sample_size,
    prior_matches
):
    """
    Calcula una fuerza relativa y la acerca a 1
    cuando la muestra todavía es pequeña.

    1.00 = promedio de liga
    >1   = superior al promedio
    <1   = inferior al promedio
    """

    if league_average <= 0:
        return 1.0

    if sample_size <= 0:
        return 1.0

    raw_ratio = (
        observed_average
        / league_average
    )

    sample_weight = (
        sample_size
        /
        (
            sample_size
            + prior_matches
        )
    )

    shrunk_ratio = (
        sample_weight
        * raw_ratio
        +
        (
            1
            - sample_weight
        )
        * 1.0
    )

    return shrunk_ratio


# ============================================================
# FUERZAS DEL EQUIPO
# ============================================================

def calculate_team_strengths(
    matches,
    team_name,
    kickoff,
    venue,
    league_baseline
):

    venue_records = (
        collect_team_records(
            matches,
            team_name,
            kickoff,
            venue=venue
        )[
            :VENUE_MATCH_LIMIT
        ]
    )

    recent_records = (
        collect_team_records(
            matches,
            team_name,
            kickoff,
            venue=None
        )[
            :RECENT_MATCH_LIMIT
        ]
    )

    # --------------------------------------------------------
    # PROMEDIOS VENUE
    # --------------------------------------------------------

    venue_gf = mean(
        [
            item["goals_for"]
            for item
            in venue_records
        ]
    )

    venue_ga = mean(
        [
            item["goals_against"]
            for item
            in venue_records
        ]
    )

    # --------------------------------------------------------
    # PROMEDIOS RECIENTES
    # --------------------------------------------------------

    recent_gf = mean(
        [
            item["goals_for"]
            for item
            in recent_records
        ]
    )

    recent_ga = mean(
        [
            item["goals_against"]
            for item
            in recent_records
        ]
    )

    # --------------------------------------------------------
    # BASELINES DEPENDIENDO DEL VENUE
    # --------------------------------------------------------

    if venue == "HOME":

        attack_baseline = (
            league_baseline[
                "home_goals_avg"
            ]
        )

        defense_baseline = (
            league_baseline[
                "away_goals_avg"
            ]
        )

    else:

        attack_baseline = (
            league_baseline[
                "away_goals_avg"
            ]
        )

        defense_baseline = (
            league_baseline[
                "home_goals_avg"
            ]
        )

    # --------------------------------------------------------
    # FUERZA LOCAL/VISITANTE
    # --------------------------------------------------------

    venue_attack = (
        regularized_ratio(
            observed_average=
                venue_gf,

            league_average=
                attack_baseline,

            sample_size=
                len(
                    venue_records
                ),

            prior_matches=
                VENUE_PRIOR_MATCHES
        )
    )

    venue_defense = (
        regularized_ratio(
            observed_average=
                venue_ga,

            league_average=
                defense_baseline,

            sample_size=
                len(
                    venue_records
                ),

            prior_matches=
                VENUE_PRIOR_MATCHES
        )
    )

    # --------------------------------------------------------
    # FORMA RECIENTE
    # --------------------------------------------------------

    recent_baseline = (
        league_baseline[
            "goals_per_team_avg"
        ]
    )

    recent_attack = (
        regularized_ratio(
            observed_average=
                recent_gf,

            league_average=
                recent_baseline,

            sample_size=
                len(
                    recent_records
                ),

            prior_matches=
                RECENT_PRIOR_MATCHES
        )
    )

    recent_defense = (
        regularized_ratio(
            observed_average=
                recent_ga,

            league_average=
                recent_baseline,

            sample_size=
                len(
                    recent_records
                ),

            prior_matches=
                RECENT_PRIOR_MATCHES
        )
    )

    # --------------------------------------------------------
    # BLEND
    # --------------------------------------------------------

    attack_strength = (
        VENUE_WEIGHT
        * venue_attack
        +
        RECENT_WEIGHT
        * recent_attack
    )

    defense_strength = (
        VENUE_WEIGHT
        * venue_defense
        +
        RECENT_WEIGHT
        * recent_defense
    )

    return {
        "venue_matches":
            len(
                venue_records
            ),

        "recent_matches":
            len(
                recent_records
            ),

        "venue_gf":
            venue_gf,

        "venue_ga":
            venue_ga,

        "recent_gf":
            recent_gf,

        "recent_ga":
            recent_ga,

        "attack_strength":
            attack_strength,

        # IMPORTANTE:
        # > 1 significa que concede más
        # que la media, por tanto defensa peor.
        "defense_factor":
            defense_strength,
    }


# ============================================================
# LAMBDAS
# ============================================================

def calculate_expected_goals(
    matches,
    home_team,
    away_team,
    kickoff
):

    league = (
        calculate_league_baseline(
            matches,
            kickoff
        )
    )

    home_strength = (
        calculate_team_strengths(
            matches=
                matches,

            team_name=
                home_team,

            kickoff=
                kickoff,

            venue=
                "HOME",

            league_baseline=
                league
        )
    )

    away_strength = (
        calculate_team_strengths(
            matches=
                matches,

            team_name=
                away_team,

            kickoff=
                kickoff,

            venue=
                "AWAY",

            league_baseline=
                league
        )
    )

    # --------------------------------------------------------
    # EXPECTED GOALS LOCAL
    # --------------------------------------------------------

    lambda_home = (
        league[
            "home_goals_avg"
        ]
        *
        home_strength[
            "attack_strength"
        ]
        *
        away_strength[
            "defense_factor"
        ]
    )

    # --------------------------------------------------------
    # EXPECTED GOALS VISITANTE
    # --------------------------------------------------------

    lambda_away = (
        league[
            "away_goals_avg"
        ]
        *
        away_strength[
            "attack_strength"
        ]
        *
        home_strength[
            "defense_factor"
        ]
    )

    # Evitar valores extremos
    lambda_home = max(
        MIN_LAMBDA,
        min(
            lambda_home,
            MAX_LAMBDA
        )
    )

    lambda_away = max(
        MIN_LAMBDA,
        min(
            lambda_away,
            MAX_LAMBDA
        )
    )

    return {
        "league":
            league,

        "home_strength":
            home_strength,

        "away_strength":
            away_strength,

        "lambda_home":
            lambda_home,

        "lambda_away":
            lambda_away,
    }


# ============================================================
# POISSON
# ============================================================

def poisson_probability(
    goals,
    expected_goals
):

    return (
        math.exp(
            -expected_goals
        )
        *
        (
            expected_goals
            ** goals
        )
        /
        math.factorial(
            goals
        )
    )


# ============================================================
# MATRIZ DE MARCADORES
# ============================================================

def build_score_matrix(
    lambda_home,
    lambda_away
):

    matrix = {}

    total_probability = 0.0

    for home_goals in range(
        MAX_GOALS + 1
    ):

        home_probability = (
            poisson_probability(
                home_goals,
                lambda_home
            )
        )

        for away_goals in range(
            MAX_GOALS + 1
        ):

            away_probability = (
                poisson_probability(
                    away_goals,
                    lambda_away
                )
            )

            probability = (
                home_probability
                * away_probability
            )

            matrix[
                (
                    home_goals,
                    away_goals
                )
            ] = probability

            total_probability += (
                probability
            )

    # Normalización para absorber la pequeñísima
    # cola que queda por encima de 10 goles.
    if total_probability > 0:

        for key in matrix:

            matrix[key] = (
                matrix[key]
                / total_probability
            )

    return matrix


# ============================================================
# MERCADOS
# ============================================================

def calculate_market_probabilities(
    lambda_home,
    lambda_away
):

    matrix = build_score_matrix(
        lambda_home,
        lambda_away
    )

    home_win = 0.0
    draw = 0.0
    away_win = 0.0

    over_15 = 0.0
    over_25 = 0.0
    under_35 = 0.0

    btts = 0.0

    best_score = None
    best_score_probability = 0.0

    for (
        home_goals,
        away_goals
    ), probability in matrix.items():

        total_goals = (
            home_goals
            + away_goals
        )

        # 1X2
        if (
            home_goals
            > away_goals
        ):

            home_win += (
                probability
            )

        elif (
            home_goals
            == away_goals
        ):

            draw += (
                probability
            )

        else:

            away_win += (
                probability
            )

        # Totales
        if total_goals >= 2:

            over_15 += (
                probability
            )

        if total_goals >= 3:

            over_25 += (
                probability
            )

        if total_goals <= 3:

            under_35 += (
                probability
            )

        # Ambos marcan
        if (
            home_goals >= 1
            and away_goals >= 1
        ):

            btts += (
                probability
            )

        # Marcador modal
        if (
            probability
            > best_score_probability
        ):

            best_score_probability = (
                probability
            )

            best_score = (
                home_goals,
                away_goals
            )

    # --------------------------------------------------------
    # MERCADOS DERIVADOS
    # --------------------------------------------------------

    home_scores = (
        1
        - math.exp(
            -lambda_home
        )
    )

    away_scores = (
        1
        - math.exp(
            -lambda_away
        )
    )

    home_or_draw = (
        home_win
        + draw
    )

    away_or_draw = (
        away_win
        + draw
    )

    no_draw = (
        home_win
        + away_win
    )

    if no_draw > 0:

        home_dnb = (
            home_win
            / no_draw
        )

        away_dnb = (
            away_win
            / no_draw
        )

    else:

        home_dnb = 0.5
        away_dnb = 0.5

    return {
        "home_win":
            home_win,

        "draw":
            draw,

        "away_win":
            away_win,

        "home_or_draw":
            home_or_draw,

        "away_or_draw":
            away_or_draw,

        "home_dnb":
            home_dnb,

        "away_dnb":
            away_dnb,

        "over_15":
            over_15,

        "over_25":
            over_25,

        "under_35":
            under_35,

        "btts":
            btts,

        "home_scores":
            home_scores,

        "away_scores":
            away_scores,

        "best_score":
            best_score,

        "best_score_probability":
            best_score_probability,
    }


# ============================================================
# CUOTA JUSTA
# ============================================================

def fair_odds(probability):

    if probability <= 0:
        return None

    return (
        1
        / probability
    )