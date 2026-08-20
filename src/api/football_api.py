import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv


BASE_URL = "https://v3.football.api-sports.io"
TIMEZONE = "Europe/Madrid"

# Durante el desarrollo reutilizaremos los datos durante 4 horas.
CACHE_HOURS = 4

load_dotenv()

# Ruta principal del proyecto CulebrIA
ROOT_DIR = Path(__file__).resolve().parents[2]

# Carpeta donde guardaremos temporalmente los datos
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


def _cache_file_for_date(date_string):
    return DATA_DIR / f"fixtures_{date_string}.json"


def _load_cache(cache_file):
    """
    Devuelve los datos guardados si el caché todavía es válido.
    """

    if not cache_file.exists():
        return None

    try:
        with open(cache_file, "r", encoding="utf-8") as file:
            cached = json.load(file)

        fetched_at = datetime.fromisoformat(cached["fetched_at"])
        now = datetime.now(ZoneInfo(TIMEZONE))

        age = now - fetched_at

        if age <= timedelta(hours=CACHE_HOURS):
            return cached

    except (json.JSONDecodeError, KeyError, ValueError):
        return None

    return None


def _save_cache(cache_file, api_data):
    """
    Guarda la respuesta de API-Football para reutilizarla.
    """

    now = datetime.now(ZoneInfo(TIMEZONE))

    cache_data = {
        "fetched_at": now.isoformat(),
        "api_data": api_data,
    }

    with open(cache_file, "w", encoding="utf-8") as file:
        json.dump(
            cache_data,
            file,
            ensure_ascii=False,
            indent=2
        )


def get_today_fixtures(force_refresh=False):
    # CulebrIA ahora analiza HOY + MAÑANA.
    # Conservamos el nombre para no romper imports existentes.

    now = datetime.now(ZoneInfo(TIMEZONE))
    api_key = os.getenv("API_FOOTBALL_KEY")
    url = f"{BASE_URL}/fixtures"

    headers = None
    combined_fixtures = []
    seen_fixture_ids = set()

    sources = []
    fetched_at_values = []

    daily_limit = None
    daily_remaining = None
    date_strings = []

    for offset in range(2):

        target_date = (
            now
            + timedelta(days=offset)
        )

        date_string = target_date.strftime(
            "%Y-%m-%d"
        )

        date_strings.append(
            date_string
        )

        cache_file = _cache_file_for_date(
            date_string
        )

        api_data = None

        if not force_refresh:

            cached = _load_cache(
                cache_file
            )

            if cached:

                api_data = cached[
                    "api_data"
                ]

                sources.append(
                    "cache"
                )

                fetched_at_values.append(
                    cached.get(
                        "fetched_at"
                    )
                )

        if api_data is None:

            if not api_key:
                raise RuntimeError(
                    "No se encontró API_FOOTBALL_KEY en el archivo .env"
                )

            if headers is None:
                headers = {
                    "x-apisports-key":
                        api_key
                }

            params = {
                "date":
                    date_string,
                "timezone":
                    TIMEZONE,
            }

            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=20,
            )

            daily_limit = (
                response.headers.get(
                    "x-ratelimit-requests-limit"
                )
            )

            daily_remaining = (
                response.headers.get(
                    "x-ratelimit-requests-remaining"
                )
            )

            response.raise_for_status()

            api_data = response.json()

            if api_data.get(
                "errors"
            ):
                raise RuntimeError(
                    "API-Football devolvió un error: "
                    f"{api_data['errors']}"
                )

            _save_cache(
                cache_file,
                api_data,
            )

            sources.append(
                "api"
            )

            fetched_at_values.append(
                datetime.now(
                    ZoneInfo(TIMEZONE)
                ).isoformat()
            )

        for item in api_data.get(
            "response",
            [],
        ):

            fixture_id = (
                item.get(
                    "fixture",
                    {}
                ).get(
                    "id"
                )
            )

            if fixture_id is None:
                continue

            if fixture_id in seen_fixture_ids:
                continue

            seen_fixture_ids.add(
                fixture_id
            )

            combined_fixtures.append(
                item
            )

    source = (
        "api"
        if "api" in sources
        else "cache"
    )

    return {
        "date":
            " -> ".join(
                date_strings
            ),
        "fixtures":
            combined_fixtures,
        "results":
            len(
                combined_fixtures
            ),
        "paging":
            {},
        "daily_limit":
            daily_limit,
        "daily_remaining":
            daily_remaining,
        "source":
            source,
        "fetched_at":
            fetched_at_values[-1]
            if fetched_at_values
            else now.isoformat(),
    }
