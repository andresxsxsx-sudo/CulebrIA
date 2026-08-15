from src.api.football_data_org_api import (
    get_available_competitions
)


def main():

    print("=" * 70)
    print("CulebrIA - FOOTBALL-DATA.ORG")
    print("=" * 70)

    print()
    print(
        "Consultando competiciones "
        "disponibles..."
    )

    try:

        data = get_available_competitions()

        print()

        if data["source"] == "api":

            print(
                "Fuente: 🌐 football-data.org"
            )

        else:

            print(
                "Fuente: 💾 Caché local"
            )

            print(
                "Solicitudes consumidas: 0"
            )

        competitions = data[
            "competitions"
        ]

        print()
        print(
            f"Competiciones disponibles: "
            f"{len(competitions)}"
        )

        print()
        print("=" * 70)
        print("LISTA DE COMPETICIONES")
        print("=" * 70)

        for index, item in enumerate(
            competitions,
            start=1
        ):

            area = item.get(
                "area",
                {}
            )

            current_season = item.get(
                "currentSeason",
                {}
            ) or {}

            print()

            print(
                f"{index}. "
                f"{item.get('name', 'Desconocida')}"
            )

            print(
                f"   Código: "
                f"{item.get('code', '?')}"
            )

            print(
                f"   ID: "
                f"{item.get('id', '?')}"
            )

            print(
                f"   País/Área: "
                f"{area.get('name', '?')}"
            )

            print(
                f"   Inicio temporada: "
                f"{current_season.get('startDate', '?')}"
            )

            print(
                f"   Fin temporada: "
                f"{current_season.get('endDate', '?')}"
            )

        print()
        print("=" * 70)

    except Exception as error:

        print()
        print("❌ Error:")
        print(error)


if __name__ == "__main__":
    main()