from datetime import datetime
from zoneinfo import ZoneInfo


TIMEZONE = "Europe/Madrid"

# Competiciones que inicialmente queremos evitar.
# Más adelante tendremos un sistema de calidad mucho más avanzado.
EXCLUDED_KEYWORDS = [
    "friendly",
    "friendlies",
    "u17",
    "u18",
    "u19",
    "u20",
    "u21",
    "u23",
    "youth",
    "reserve",
]


def is_excluded_competition(league_name):
    """
    Comprueba si la competición pertenece a una categoría
    que inicialmente no queremos utilizar.
    """

    name = league_name.lower()

    return any(
        keyword in name
        for keyword in EXCLUDED_KEYWORDS
    )


def filter_candidate_fixtures(fixtures):
    """
    Primer filtro de CulebrIA.

    Conserva únicamente:
    - Partidos que todavía no han comenzado.
    - Partidos cuya hora de inicio es futura.
    - Partidos con equipos identificados.
    - Competiciones que no estén inicialmente excluidas.
    """

    now = datetime.now(ZoneInfo(TIMEZONE))

    candidates = []

    excluded = {
        "already_started": 0,
        "competition": 0,
        "invalid_team": 0,
        "invalid_date": 0,
    }

    for item in fixtures:

        fixture = item.get("fixture", {})
        league = item.get("league", {})
        teams = item.get("teams", {})

        status = fixture.get(
            "status",
            {}
        ).get(
            "short",
            ""
        )

        # Solo partidos todavía no iniciados
        if status != "NS":
            excluded["already_started"] += 1
            continue

        # --------------------------------------------
        # FECHA Y HORA
        # --------------------------------------------

        fixture_date = fixture.get("date")

        if not fixture_date:
            excluded["invalid_date"] += 1
            continue

        try:
            kickoff = datetime.fromisoformat(
                fixture_date.replace("Z", "+00:00")
            )

            kickoff = kickoff.astimezone(
                ZoneInfo(TIMEZONE)
            )

        except ValueError:
            excluded["invalid_date"] += 1
            continue

        if kickoff <= now:
            excluded["already_started"] += 1
            continue

        # --------------------------------------------
        # EQUIPOS
        # --------------------------------------------

        home = teams.get(
            "home",
            {}
        ).get(
            "name"
        )

        away = teams.get(
            "away",
            {}
        ).get(
            "name"
        )

        if not home or not away:
            excluded["invalid_team"] += 1
            continue

        # --------------------------------------------
        # COMPETICIÓN
        # --------------------------------------------

        league_name = league.get(
            "name",
            ""
        )

        if is_excluded_competition(league_name):
            excluded["competition"] += 1
            continue

        candidates.append(item)

    return {
        "fixtures": candidates,
        "total": len(candidates),
        "excluded": excluded,
    }