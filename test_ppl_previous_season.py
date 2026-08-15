import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv


# ============================================================
# CONFIGURACIÓN
# ============================================================

BASE_URL = "https://api.football-data.org/v4"

COMPETITION = "PPL"

# 2025 = temporada 2025/26
SEASON = 2025

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"

OUTPUT_FILE = (
    DATA_DIR
    / "fdorg_matches"
    / "PPL_2025_matches.json"
)


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    print("=" * 72)
    print("CulebrIA - PRUEBA HISTÓRICO PPL")
    print("=" * 72)

    print()
    print(
        "Competición: "
        f"{COMPETITION}"
    )

    print(
        "Temporada solicitada: "
        f"{SEASON}/"
        f"{str(SEASON + 1)[-2:]}"
    )

    # --------------------------------------------------------
    # TOKEN
    # --------------------------------------------------------

    api_key = os.getenv(
        "FOOTBALL_DATA_ORG_KEY"
    )

    if not api_key:

        print()
        print(
            "❌ No se encontró "
            "FOOTBALL_DATA_ORG_KEY "
            "en .env"
        )

        return

    # --------------------------------------------------------
    # PETICIÓN
    # --------------------------------------------------------

    url = (
        f"{BASE_URL}"
        f"/competitions/"
        f"{COMPETITION}"
        f"/matches"
    )

    headers = {
        "X-Auth-Token":
            api_key
    }

    params = {
        "season":
            SEASON
    }

    print()
    print(
        "Consultando football-data.org..."
    )

    try:

        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=30
        )

    except requests.RequestException as error:

        print()
        print(
            "❌ Error de conexión:"
        )

        print(error)

        return

    # --------------------------------------------------------
    # STATUS HTTP
    # --------------------------------------------------------

    print()
    print(
        f"HTTP status: "
        f"{response.status_code}"
    )

    # --------------------------------------------------------
    # INTENTAR LEER JSON
    # --------------------------------------------------------

    try:

        data = response.json()

    except ValueError:

        print()
        print(
            "❌ La API no devolvió "
            "un JSON válido."
        )

        print()
        print(
            response.text[:1000]
        )

        return

    # --------------------------------------------------------
    # SI LA API RECHAZA LA PETICIÓN
    # --------------------------------------------------------

    if not response.ok:

        print()
        print(
            "❌ football-data.org "
            "rechazó la petición."
        )

        print()

        message = data.get(
            "message",
            data
        )

        print(message)

        print()
        print(
            "No modificaremos nada "
            "hasta revisar este resultado."
        )

        return

    # --------------------------------------------------------
    # PARTIDOS
    # --------------------------------------------------------

    matches = data.get(
        "matches",
        []
    )

    finished = [
        match
        for match in matches
        if match.get(
            "status"
        ) == "FINISHED"
    ]

    scheduled = [
        match
        for match in matches
        if match.get(
            "status"
        ) in {
            "SCHEDULED",
            "TIMED"
        }
    ]

    # --------------------------------------------------------
    # EQUIPOS
    # --------------------------------------------------------

    teams = set()

    for match in matches:

        home = (
            match
            .get(
                "homeTeam",
                {}
            )
            .get(
                "name"
            )
        )

        away = (
            match
            .get(
                "awayTeam",
                {}
            )
            .get(
                "name"
            )
        )

        if home:
            teams.add(home)

        if away:
            teams.add(away)

    # --------------------------------------------------------
    # GUARDAR
    # --------------------------------------------------------

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    cache = {
        "competition":
            COMPETITION,

        "season":
            SEASON,

        "api_data":
            data
    }

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            cache,
            file,
            ensure_ascii=False,
            indent=2
        )

    # --------------------------------------------------------
    # RESULTADOS
    # --------------------------------------------------------

    print()
    print(
        "✅ Temporada accesible"
    )

    print()
    print(
        f"Partidos recibidos: "
        f"{len(matches)}"
    )

    print(
        f"Finalizados: "
        f"{len(finished)}"
    )

    print(
        f"Pendientes: "
        f"{len(scheduled)}"
    )

    print(
        f"Equipos encontrados: "
        f"{len(teams)}"
    )

    # --------------------------------------------------------
    # COMPROBAR NUESTROS EQUIPOS PPL
    # --------------------------------------------------------

    target_names = [
        "Benfica",
        "Viseu",
        "Gil Vicente",
        "Rio Ave",
        "Moreirense",
        "Braga"
    ]

    print()
    print("=" * 72)
    print("BÚSQUEDA DE EQUIPOS")
    print("=" * 72)

    for target in target_names:

        found = [
            team
            for team in teams
            if target.lower()
            in team.lower()
        ]

        print()

        if found:

            print(
                f"✅ {target}: "
                f"{', '.join(found)}"
            )

        else:

            print(
                f"⚠️ {target}: "
                "no encontrado"
            )

    print()
    print("=" * 72)

    print(
        "Archivo guardado:"
    )

    print(
        OUTPUT_FILE
    )


if __name__ == "__main__":
    main()