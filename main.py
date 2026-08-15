from datetime import datetime

import requests

from src.api.football_api import get_today_fixtures
from src.analysis.fixture_filter import filter_candidate_fixtures


def main():

    print("=" * 60)
    print("CulebrIA")
    print("Motor de análisis deportivo")
    print("=" * 60)

    print(
        "Inicio:",
        datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    )

    print()
    print("Cargando datos de fútbol...")
    print()

    try:

        data = get_today_fixtures()

        print("✅ Datos obtenidos correctamente")
        print()

        print(
            f"Partidos totales encontrados: "
            f"{data['results']}"
        )

        # --------------------------------------------
        # ORIGEN DE LOS DATOS
        # --------------------------------------------

        if data["source"] == "api":

            print(
                "Fuente de datos: 🌐 API-Football"
            )

            print(
                f"Solicitudes API restantes: "
                f"{data['daily_remaining']} / "
                f"{data['daily_limit']}"
            )

        else:

            print(
                "Fuente de datos: 💾 Caché local"
            )

            print(
                "Solicitudes API consumidas "
                "en esta ejecución: 0"
            )

        # --------------------------------------------
        # FILTRAR EVENTOS
        # --------------------------------------------

        filter_result = filter_candidate_fixtures(
            data["fixtures"]
        )

        candidates = filter_result["fixtures"]
        excluded = filter_result["excluded"]

        print()
        print("=" * 60)
        print("PRIMER FILTRO CULEBRIA")
        print("=" * 60)

        print(
            f"Partidos originales: "
            f"{data['results']}"
        )

        print(
            f"Candidatos restantes: "
            f"{filter_result['total']}"
        )

        print()
        print("Descartados:")

        print(
            f"  Ya iniciados/finalizados: "
            f"{excluded['already_started']}"
        )

        print(
            f"  Competiciones excluidas: "
            f"{excluded['competition']}"
        )

        print(
            f"  Equipos inválidos: "
            f"{excluded['invalid_team']}"
        )

        print(
            f"  Fecha inválida: "
            f"{excluded['invalid_date']}"
        )

        # --------------------------------------------
        # MOSTRAR PRIMEROS CANDIDATOS
        # --------------------------------------------

        print()
        print("=" * 60)
        print("PRIMEROS CANDIDATOS")
        print("=" * 60)

        for index, item in enumerate(
            candidates[:30],
            start=1
        ):

            fixture = item["fixture"]
            league = item["league"]
            teams = item["teams"]

            home = teams["home"]["name"]
            away = teams["away"]["name"]

            competition = league.get(
                "name",
                "Desconocida"
            )

            country = league.get(
                "country",
                ""
            )

            match_date = fixture["date"]

            hour = match_date[11:16]

            print()
            print(
                f"{index}. "
                f"{home} vs {away}"
            )

            print(
                f"   {competition} "
                f"({country})"
            )

            print(
                f"   Hora: {hour}"
            )

        if len(candidates) > 30:

            print()

            print(
                f"... y "
                f"{len(candidates) - 30} "
                f"candidatos adicionales."
            )

        print()
        print("=" * 60)

    except requests.exceptions.RequestException as error:

        print()
        print(
            "❌ Error de conexión con API-Football:"
        )
        print(error)

    except Exception as error:

        print()
        print("❌ Error:")
        print(error)


if __name__ == "__main__":
    main()