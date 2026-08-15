from collections import Counter


def get_competition_report(fixtures):
    """
    Agrupa los partidos candidatos por país y competición.
    No realiza ninguna petición a Internet.
    """

    competitions = Counter()

    for item in fixtures:
        league = item.get("league", {})

        country = league.get("country", "Desconocido")
        league_name = league.get("name", "Desconocida")
        league_id = league.get("id", "?")

        key = (
            country,
            league_name,
            league_id,
        )

        competitions[key] += 1

    return competitions.most_common()