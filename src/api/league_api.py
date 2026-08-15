import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv


BASE_URL = "https://v3.football.api-sports.io"
TIMEZONE = "Europe/Madrid"

CACHE_DAYS = 7

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

CACHE_FILE = DATA_DIR / "leagues_coverage.json"


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

        now = datetime.now(
            ZoneInfo(TIMEZONE)
        )

        if now - fetched_at <= timedelta(
            days=CACHE_DAYS
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

    now = datetime.now(
        ZoneInfo(TIMEZONE)
    )

    content = {
        "fetched_at": now.isoformat(),
        "api_data": api_data
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


def get_leagues_coverage(
    force_refresh=False
):

    if not force_refresh:

        cached = _load_cache()

        if cached:

            return {
                "leagues": cached[
                    "api_data"
                ].get(
                    "response",
                    []
                ),
                "source": "cache",
                "remaining": None
            }

    api_key = os.getenv(
        "API_FOOTBALL_KEY"
    )

    if not api_key:

        raise RuntimeError(
            "No se encontró "
            "API_FOOTBALL_KEY"
        )

    url = f"{BASE_URL}/leagues"

    headers = {
        "x-apisports-key":
        api_key
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=30
    )

    remaining = response.headers.get(
        "x-ratelimit-requests-remaining"
    )

    response.raise_for_status()

    api_data = response.json()

    if api_data.get("errors"):

        raise RuntimeError(
            f"Error API-Football: "
            f"{api_data['errors']}"
        )

    _save_cache(
        api_data
    )

    return {
        "leagues":
        api_data.get(
            "response",
            []
        ),
        "source":
        "api",
        "remaining":
        remaining
    }