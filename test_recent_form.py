import os
import requests
from dotenv import load_dotenv

from src.api.football_api import get_today_fixtures
from src.analysis.fixture_filter import filter_candidate_fixtures


BASE_URL = "https://v3.football.api-sports.io"

load_dotenv()


def main():
    print("=" * 70)
    print("CulebrIA - PRUEBA DE FORMA RECIENTE")
    print("=" * 70)

    # Usamos los partidos que ya están guardados en caché
    data = get_today_fixtures()

    filtered = filter_candidate_fixtures(
        data["fixtures"]
    )

    fixtures = filtered["fixtures"]

    if not fixtures:
        print("No hay partidos futuros disponibles.")
        return

    # Elegimos automáticamente el primer equipo local disponible
    match = fixtures[0]

    home_team = match["teams"]["home"]

    team_id = home_team["id"]
    team_name = home_team["name"]

    print()
    print(f"Equipo de prueba: {team_name}")
    print(f"Team ID: {team_id}")

    api_key = os.getenv("API_FOOTBALL_KEY")

    if not api_key:
        print("❌ No se encontró API_FOOTBALL_KEY en .env")
        return

    url = f"{BASE_URL}/fixtures"

    headers = {
        "x-apisports-key": api_key
    }

    params = {
        "team": team_id,
        "last": 10,
        "timezone": "Europe/Madrid"
    }

    print()
    print("Consultando últimos 10 partidos...")
    print()

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=30
    )

    remaining = response.headers.get(
        "x-ratelimit-requests-remaining",
        "?"
    )

    print(
        f"HTTP status: {response.status_code}"
    )

    data = response.json()

    if data.get("errors"):
        print("❌ API-Football respondió:")
        print(data["errors"])

        print()
        print(
            f"Solicitudes restantes: {remaining}"
        )

        return

    fixtures = data.get(
        "response",
        []
    )

    print("✅ Petición aceptada")
    print(
        f"Partidos recibidos: {len(fixtures)}"
    )

    print(
        f"Solicitudes restantes: {remaining}"
    )

    print()
    print("=" * 70)
    print("ÚLTIMOS PARTIDOS")
    print("=" * 70)

    for index, item in enumerate(
        fixtures,
        start=1
    ):
        fixture = item["fixture"]
        teams = item["teams"]
        goals = item["goals"]

        home = teams["home"]["name"]
        away = teams["away"]["name"]

        home_goals = goals["home"]
        away_goals = goals["away"]

        date = fixture["date"][:10]

        print()
        print(
            f"{index}. {date}"
        )

        print(
            f"   {home} "
            f"{home_goals} - "
            f"{away_goals} "
            f"{away}"
        )


if __name__ == "__main__":
    main()