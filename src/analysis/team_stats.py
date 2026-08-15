from datetime import datetime


def parse_datetime(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
    except ValueError:
        return None


def get_score(match):
    """
    Obtiene el marcador final de un partido
    de football-data.org.
    """

    score = match.get("score", {})
    full_time = score.get("fullTime", {})

    home_goals = full_time.get("home")
    away_goals = full_time.get("away")

    if home_goals is None or away_goals is None:
        return None

    return int(home_goals), int(away_goals)


def collect_team_matches(
    matches,
    team_name,
    before_date=None,
    venue=None
):
    """
    Obtiene partidos FINALIZADOS de un equipo.

    venue:
        None   -> todos
        "HOME" -> solo jugando de local
        "AWAY" -> solo jugando de visitante

    before_date evita utilizar partidos posteriores
    al encuentro que queremos predecir.
    """

    collected = []

    for match in matches:

        if match.get("status") != "FINISHED":
            continue

        match_date = parse_datetime(
            match.get("utcDate")
        )

        if match_date is None:
            continue

        if (
            before_date is not None
            and match_date >= before_date
        ):
            continue

        home_team = (
            match.get("homeTeam", {})
            .get("name", "")
        )

        away_team = (
            match.get("awayTeam", {})
            .get("name", "")
        )

        is_home = home_team == team_name
        is_away = away_team == team_name

        if not is_home and not is_away:
            continue

        if venue == "HOME" and not is_home:
            continue

        if venue == "AWAY" and not is_away:
            continue

        score = get_score(match)

        if score is None:
            continue

        home_goals, away_goals = score

        if is_home:
            goals_for = home_goals
            goals_against = away_goals
        else:
            goals_for = away_goals
            goals_against = home_goals

        if goals_for > goals_against:
            result = "W"

        elif goals_for == goals_against:
            result = "D"

        else:
            result = "L"

        collected.append(
            {
                "date": match_date,
                "goals_for": goals_for,
                "goals_against": goals_against,
                "total_goals": (
                    home_goals
                    + away_goals
                ),
                "result": result,
                "is_home": is_home,
                "is_away": is_away,
            }
        )

    collected.sort(
        key=lambda item: item["date"],
        reverse=True
    )

    return collected


def safe_rate(value, total):
    if total == 0:
        return 0.0

    return value / total


def calculate_sample_stats(matches):
    """
    Calcula métricas estadísticas sobre
    una lista previamente seleccionada.
    """

    total = len(matches)

    if total == 0:
        return {
            "matches": 0,
            "wins": 0,
            "draws": 0,
            "losses": 0,
            "avg_goals_for": 0.0,
            "avg_goals_against": 0.0,
            "scored_rate": 0.0,
            "clean_sheet_rate": 0.0,
            "btts_rate": 0.0,
            "over_05_rate": 0.0,
            "over_15_rate": 0.0,
            "over_25_rate": 0.0,
            "under_35_rate": 0.0,
        }

    wins = sum(
        1 for match in matches
        if match["result"] == "W"
    )

    draws = sum(
        1 for match in matches
        if match["result"] == "D"
    )

    losses = sum(
        1 for match in matches
        if match["result"] == "L"
    )

    goals_for = sum(
        match["goals_for"]
        for match in matches
    )

    goals_against = sum(
        match["goals_against"]
        for match in matches
    )

    scored = sum(
        1 for match in matches
        if match["goals_for"] >= 1
    )

    clean_sheets = sum(
        1 for match in matches
        if match["goals_against"] == 0
    )

    btts = sum(
        1 for match in matches
        if (
            match["goals_for"] >= 1
            and match["goals_against"] >= 1
        )
    )

    over_05 = sum(
        1 for match in matches
        if match["total_goals"] >= 1
    )

    over_15 = sum(
        1 for match in matches
        if match["total_goals"] >= 2
    )

    over_25 = sum(
        1 for match in matches
        if match["total_goals"] >= 3
    )

    under_35 = sum(
        1 for match in matches
        if match["total_goals"] <= 3
    )

    return {
        "matches": total,

        "wins": wins,
        "draws": draws,
        "losses": losses,

        "win_rate":
            safe_rate(wins, total),

        "draw_rate":
            safe_rate(draws, total),

        "loss_rate":
            safe_rate(losses, total),

        "avg_goals_for":
            goals_for / total,

        "avg_goals_against":
            goals_against / total,

        "scored_rate":
            safe_rate(scored, total),

        "clean_sheet_rate":
            safe_rate(
                clean_sheets,
                total
            ),

        "btts_rate":
            safe_rate(btts, total),

        "over_05_rate":
            safe_rate(over_05, total),

        "over_15_rate":
            safe_rate(over_15, total),

        "over_25_rate":
            safe_rate(over_25, total),

        "under_35_rate":
            safe_rate(under_35, total),
    }


def calculate_team_profile(
    matches,
    team_name,
    before_date,
    venue
):
    """
    Genera las principales muestras que
    utilizaremos posteriormente en el modelo.
    """

    overall = collect_team_matches(
        matches=matches,
        team_name=team_name,
        before_date=before_date
    )

    venue_matches = collect_team_matches(
        matches=matches,
        team_name=team_name,
        before_date=before_date,
        venue=venue
    )

    return {
        "last_5":
            calculate_sample_stats(
                overall[:5]
            ),

        "last_10":
            calculate_sample_stats(
                overall[:10]
            ),

        "venue_last_5":
            calculate_sample_stats(
                venue_matches[:5]
            ),

        "venue_last_10":
            calculate_sample_stats(
                venue_matches[:10]
            ),

        "season_overall":
            calculate_sample_stats(
                overall
            ),
    }