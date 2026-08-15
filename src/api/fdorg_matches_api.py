import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv


BASE_URL = "https://api.football-data.org/v4"

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[2]

CACHE_DIR = (
    ROOT_DIR
    / "data"
    / "fdorg_matches"
)

CACHE_DIR.mkdir(
    parents=True,
    exist_ok=True
)

# Durante el desarrollo reutilizaremos la descarga
# durante 6 horas.
CACHE_HOURS = 6


def _cache_file(
    competition_code
):
    return (
        CACHE_DIR
        / f"{competition_code}_matches.json"
    )


def _load_cache(
    competition_code
):
    file_path = _cache_file(
        competition_code
    )

    if not file_path.exists():
        return None

    try:

        with open(
            file_path,
            "r",
            encoding="utf-8"
        ) as file:

            cached = json.load(file)

        fetched_at = datetime.fromisoformat(
            cached["fetched_at"]
        )

        age = (
            datetime.now()
            - fetched_at
        )

        if age <= timedelta(
            hours=CACHE_HOURS
        ):
            return cached

    except (
        json.JSONDecodeError,
        KeyError,
        ValueError
    ):
        return None

    return None


def _save_cache(
    competition_code,
    api_data
):
    file_path = _cache_file(
        competition_code
    )

    content = {
        "fetched_at":
            datetime.now().isoformat(),

        "api_data":
            api_data
    }

    with open(
        file_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            content,
            file,
            ensure_ascii=False,
            indent=2
        )


def get_competition_matches(
    competition_code,
    force_refresh=False
):
    """
    Obtiene todos los partidos de la temporada
    actual de una competición.

    Si existe caché reciente, no consulta Internet.
    """

    competition_code = (
        str(
            competition_code
        )
        .strip()
        .upper()
    )

    # -----------------------------------------
    # 1. CACHÉ
    # -----------------------------------------

    if not force_refresh:

        cached = _load_cache(
            competition_code
        )

        if cached:

            api_data = cached[
                "api_data"
            ]

            return {
                "source":
                    "cache",

                "competition_code":
                    competition_code,

                "matches":
                    api_data.get(
                        "matches",
                        []
                    ),

                "result_set":
                    api_data.get(
                        "resultSet",
                        {}
                    ),

                "competition":
                    api_data.get(
                        "competition",
                        {}
                    ),

                "filters":
                    api_data.get(
                        "filters",
                        {}
                    ),
            }

    # -----------------------------------------
    # 2. TOKEN
    # -----------------------------------------

    api_key = os.getenv(
        "FOOTBALL_DATA_ORG_KEY"
    )

    if not api_key:

        raise RuntimeError(
            "No se encontró "
            "FOOTBALL_DATA_ORG_KEY "
            "en .env"
        )

    # -----------------------------------------
    # 3. PETICIÓN
    # -----------------------------------------

    url = (
        f"{BASE_URL}"
        f"/competitions/"
        f"{competition_code}"
        f"/matches"
    )

    headers = {
        "X-Auth-Token":
            api_key
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    api_data = response.json()

    # -----------------------------------------
    # 4. GUARDAR
    # -----------------------------------------

    _save_cache(
        competition_code,
        api_data
    )

    return {
        "source":
            "api",

        "competition_code":
            competition_code,

        "matches":
            api_data.get(
                "matches",
                []
            ),

        "result_set":
            api_data.get(
                "resultSet",
                {}
            ),

        "competition":
            api_data.get(
                "competition",
                {}
            ),

        "filters":
            api_data.get(
                "filters",
                {}
            ),
    }