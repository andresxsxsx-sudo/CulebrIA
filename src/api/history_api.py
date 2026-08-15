import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv


BASE_URL = "https://v3.football.api-sports.io"
TIMEZONE = "Europe/Madrid"

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[2]

HISTORY_DIR = (
    ROOT_DIR
    / "data"
    / "history"
)

HISTORY_DIR.mkdir(
    parents=True,
    exist_ok=True
)


def _history_file(
    league_id,
    season
):
    return (
        HISTORY_DIR
        / f"league_{league_id}_{season}.json"
    )


def get_league_history(
    league_id,
    season,
    force_refresh=False
):
    """
    Descarga todos los fixtures disponibles
    de una liga y temporada.

    Si ya existe el archivo local,
    reutiliza el caché y no consume API.
    """

    cache_file = _history_file(
        league_id,
        season
    )

    # -----------------------------------------
    # USAR CACHÉ
    # -----------------------------------------

    if (
        cache_file.exists()
        and not force_refresh
    ):

        with open(
            cache_file,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        return {
            "source": "cache",
            "fixtures": data.get(
                "response",
                []
            ),
            "results": data.get(
                "results",
                0
            ),
            "remaining": None,
            "file": str(
                cache_file
            )
        }

    # -----------------------------------------
    # CONSULTAR API
    # -----------------------------------------

    api_key = os.getenv(
        "API_FOOTBALL_KEY"
    )

    if not api_key:
        raise RuntimeError(
            "No se encontró "
            "API_FOOTBALL_KEY en .env"
        )

    url = (
        f"{BASE_URL}/fixtures"
    )

    headers = {
        "x-apisports-key":
            api_key
    }

    params = {
        "league":
            int(league_id),

        "season":
            int(season),

        "timezone":
            TIMEZONE
    }

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=30
    )

    remaining = response.headers.get(
        "x-ratelimit-requests-remaining"
    )

    response.raise_for_status()

    data = response.json()

    if data.get("errors"):

        raise RuntimeError(
            f"API-Football: "
            f"{data['errors']}"
        )

    # -----------------------------------------
    # GUARDAR
    # -----------------------------------------

    with open(
        cache_file,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )

    return {
        "source": "api",
        "fixtures": data.get(
            "response",
            []
        ),
        "results": data.get(
            "results",
            0
        ),
        "remaining":
            remaining,
        "file":
            str(cache_file)
    }