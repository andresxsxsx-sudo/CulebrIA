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
    """
    Obtiene los partidos de hoy.

    Si existe un caché de menos de 4 horas,
    utiliza los datos locales y NO consume API.
    """

    now = datetime.now(ZoneInfo(TIMEZONE))
    today = now.strftime("%Y-%m-%d")

    cache_file = _cache_file_for_date(today)

    # -------------------------------------------------
    # 1. INTENTAR USAR DATOS GUARDADOS
    # -------------------------------------------------

    if not force_refresh:
        cached = _load_cache(cache_file)

        if cached:
            api_data = cached["api_data"]

            return {
                "date": today,
                "fixtures": api_data.get("response", []),
                "results": api_data.get("results", 0),
                "paging": api_data.get("paging", {}),
                "daily_limit": None,
                "daily_remaining": None,
                "source": "cache",
                "fetched_at": cached["fetched_at"],
            }

    # -------------------------------------------------
    # 2. SI NO HAY CACHÉ, CONSULTAR API
    # -------------------------------------------------

    api_key = os.getenv("API_FOOTBALL_KEY")

    if not api_key:
        raise RuntimeError(
            "No se encontró API_FOOTBALL_KEY en el archivo .env"
        )

    url = f"{BASE_URL}/fixtures"

    headers = {
        "x-apisports-key": api_key
    }

    params = {
        "date": today,
        "timezone": TIMEZONE
    }

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=20
    )

    daily_limit = response.headers.get(
        "x-ratelimit-requests-limit"
    )

    daily_remaining = response.headers.get(
        "x-ratelimit-requests-remaining"
    )

    response.raise_for_status()

    api_data = response.json()

    if api_data.get("errors"):
        raise RuntimeError(
            f"API-Football devolvió un error: {api_data['errors']}"
        )

    # Guardamos los datos localmente
    _save_cache(cache_file, api_data)

    return {
        "date": today,
        "fixtures": api_data.get("response", []),
        "results": api_data.get("results", 0),
        "paging": api_data.get("paging", {}),
        "daily_limit": daily_limit,
        "daily_remaining": daily_remaining,
        "source": "api",
        "fetched_at": now.isoformat(),
    }