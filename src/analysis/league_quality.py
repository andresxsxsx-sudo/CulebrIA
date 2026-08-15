def _to_bool(value):
    """
    Convierte los diferentes formatos de cobertura
    de API-Football a True/False.
    """

    if isinstance(value, bool):
        return value

    if isinstance(value, dict):
        return any(
            _to_bool(v)
            for v in value.values()
        )

    return bool(value)


def calculate_league_quality(
    league_item,
    target_season=None
):
    """
    Calcula la calidad de cobertura de una liga.

    Si conocemos la temporada exacta del partido,
    utiliza esa temporada.
    """

    seasons = league_item.get(
        "seasons",
        []
    )

    if not seasons:
        return None

    selected_season = None

    # Intentar encontrar exactamente
    # la temporada del partido.
    if target_season is not None:

        for season in seasons:

            if season.get("year") == target_season:
                selected_season = season
                break

    # Si no existe coincidencia exacta,
    # usar la temporada más reciente disponible.
    if selected_season is None:
        selected_season = seasons[-1]

    coverage = selected_season.get(
        "coverage",
        {}
    )

    fixtures = coverage.get(
        "fixtures",
        {}
    )

    has_events = _to_bool(
        fixtures.get("events")
    )

    has_lineups = _to_bool(
        fixtures.get("lineups")
    )

    has_fixture_stats = _to_bool(
        fixtures.get("statistics_fixtures")
    )

    has_player_stats = _to_bool(
        fixtures.get("statistics_players")
    )

    has_standings = _to_bool(
        coverage.get("standings")
    )

    has_players = _to_bool(
        coverage.get("players")
    )

    has_injuries = _to_bool(
        coverage.get("injuries")
    )

    has_predictions = _to_bool(
        coverage.get("predictions")
    )

    has_odds = _to_bool(
        coverage.get("odds")
    )

    # -----------------------------------------
    # PUNTUACIÓN DE COBERTURA
    # -----------------------------------------

    score = 0

    if has_fixture_stats:
        score += 20

    if has_player_stats:
        score += 10

    if has_lineups:
        score += 15

    if has_injuries:
        score += 15

    if has_standings:
        score += 10

    if has_players:
        score += 10

    if has_events:
        score += 5

    if has_predictions:
        score += 5

    if has_odds:
        score += 10

    # -----------------------------------------
    # CLASIFICACIÓN
    # -----------------------------------------

    if score >= 85:
        grade = "A"

    elif score >= 70:
        grade = "B"

    elif score >= 50:
        grade = "C"

    else:
        grade = "D"

    return {
        "score": score,
        "grade": grade,

        "season": selected_season.get(
            "year"
        ),

        "coverage": {
            "fixture_statistics":
                has_fixture_stats,

            "player_statistics":
                has_player_stats,

            "lineups":
                has_lineups,

            "injuries":
                has_injuries,

            "standings":
                has_standings,

            "players":
                has_players,

            "events":
                has_events,

            "predictions":
                has_predictions,

            "odds":
                has_odds,
        }
    }