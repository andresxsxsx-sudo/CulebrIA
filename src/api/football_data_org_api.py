import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv


BASE_URL = "https://api.football-data.org/v4"

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[2]

DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

CACHE_FILE = (
    DATA_DIR
    / "football_data_org_competitions.json"
)

CACHE_HOURS = 24


def _load_cache():

    if not CACHE_FILE.exists():
        return None

    try:

        with open(
            CACHE_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            cached = json.load(file)

        fetched_at = datetime.fromisoformat(
            cached["fetched_at"]
        )

        if (
            datetime.now() - fetched_at
            <= timedelta(hours=CACHE_HOURS)
        ):
            return cached

    except (
        json.JSONDecodeError,
        KeyError,
        ValueError
    ):
        return None

    return None


def _save_cache(api_data):

    content = {
        "fetched_at":
            datetime.now().isoformat(),

        "api_data":
            api_data
    }

    with open(
        CACHE_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            content,
            file,
            ensure_ascii=False,
            indent=2
        )


def get_available_competitions(
    force_refresh=False
):

    # -----------------------------------------
    # USAR CACHÉ
    # -----------------------------------------

    if not force_refresh:

        cached = _load_cache()

        if cached:

            return {
                "source":
                    "cache",

                "competitions":
                    cached[
                        "api_data"
                    ].get(
                        "competitions",
                        []
                    ),

                "count":
                    cached[
                        "api_data"
                    ].get(
                        "count",
                        0
                    )
            }

    # -----------------------------------------
    # API TOKEN
    # -----------------------------------------

    api_key = os.getenv(
        "FOOTBALL_DATA_ORG_KEY"
    )

    if not api_key:

        raise RuntimeError(
            "No se encontró "
            "FOOTBALL_DATA_ORG_KEY "
            "en el archivo .env"
        )

    # -----------------------------------------
    # PETICIÓN
    # -----------------------------------------

    url = (
        f"{BASE_URL}/competitions"
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

    data = response.json()

    _save_cache(
        data
    )

    return {
        "source":
            "api",

        "competitions":
            data.get(
                "competitions",
                []
            ),

        "count":
            data.get(
                "count",
                0
            )
    }