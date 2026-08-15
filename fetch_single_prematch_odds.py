import json
import os

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from dotenv import load_dotenv


# ============================================================
# CONFIGURACIÓN
# ============================================================

BASE_URL = "https://api.the-odds-api.com/v4"

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"

INPUT_FILE = (
    DATA_DIR
    / "prematch_odds_candidates.csv"
)

OUTPUT_DIR = (
    DATA_DIR
    / "odds_raw"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)

load_dotenv()


# ============================================================
# MAPEO CulebrIA -> THE ODDS API
# ============================================================

MARKET_MAP = {
    "1X":
        "double_chance",

    "X2":
        "double_chance",

    "AWAY_SCORES":
        "team_totals",
}


# ============================================================
# FECHAS
# ============================================================

def parse_datetime(value):

    if (
        value is None
        or pd.isna(value)
        or str(value).strip() == ""
    ):
        return None

    try:

        return datetime.fromisoformat(
            str(value).replace(
                "Z",
                "+00:00"
            )
        )

    except ValueError:

        return None


# ============================================================
# MOSTRAR OUTCOMES
# ============================================================

def print_market_data(
    data,
    requested_market
):

    bookmakers = data.get(
        "bookmakers",
        []
    )

    print()
    print(
        f"Bookmakers recibidos: "
        f"{len(bookmakers)}"
    )

    market_count = 0
    outcome_count = 0

    for bookmaker in bookmakers:

        bookmaker_title = bookmaker.get(
            "title",
            "?"
        )

        markets = bookmaker.get(
            "markets",
            []
        )

        relevant_markets = [
            market
            for market in markets
            if market.get("key")
            == requested_market
        ]

        if not relevant_markets:
            continue

        print()
        print("=" * 72)

        print(
            f"BOOKMAKER: "
            f"{bookmaker_title}"
        )

        for market in relevant_markets:

            market_count += 1

            print(
                f"Mercado: "
                f"{market.get('key', '?')}"
            )

            print(
                f"Última actualización: "
                f"{market.get('last_update', '?')}"
            )

            outcomes = market.get(
                "outcomes",
                []
            )

            for outcome in outcomes:

                outcome_count += 1

                name = outcome.get(
                    "name",
                    "?"
                )

                price = outcome.get(
                    "price",
                    "?"
                )

                description = outcome.get(
                    "description"
                )

                point = outcome.get(
                    "point"
                )

                print()

                print(
                    f"  Nombre: "
                    f"{name}"
                )

                if description is not None:

                    print(
                        f"  Descripción: "
                        f"{description}"
                    )

                if point is not None:

                    print(
                        f"  Línea: "
                        f"{point}"
                    )

                print(
                    f"  Cuota decimal: "
                    f"{price}"
                )

    return (
        market_count,
        outcome_count
    )


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    print("=" * 80)
    print(
        "CulebrIA - PRIMERA CUOTA PREMATCH"
    )
    print("=" * 80)

    api_key = os.getenv(
        "THE_ODDS_API_KEY"
    )

    if not api_key:

        print()
        print(
            "❌ No se encontró "
            "THE_ODDS_API_KEY en .env"
        )

        return

    # --------------------------------------------------------
    # CARGAR CANDIDATOS
    # --------------------------------------------------------

    df = pd.read_csv(
        INPUT_FILE
    )

    prematch = df[
        df[
            "timing_status"
        ] == "PREMATCH"
    ].copy()

    print()
    print(
        f"Señales PREMATCH guardadas: "
        f"{len(prematch)}"
    )

    if prematch.empty:

        print()
        print(
            "No existe ninguna señal "
            "PREMATCH disponible."
        )

        print(
            "Créditos consumidos: 0"
        )

        return

    # --------------------------------------------------------
    # SOLO UNA SEÑAL EN ESTA PRUEBA
    # --------------------------------------------------------

    row = prematch.iloc[0]

    home = str(
        row["home"]
    )

    away = str(
        row["away"]
    )

    signal_market = str(
        row["signal_market"]
    ).strip().upper()

    probability = float(
        row[
            "model_probability_pct"
        ]
    )

    sport_key = str(
        row["sport_key"]
    )

    event_id = str(
        row["event_id"]
    )

    commence_time = parse_datetime(
        row["commence_time"]
    )

    # --------------------------------------------------------
    # COMPROBAR EL MERCADO
    # --------------------------------------------------------

    api_market = MARKET_MAP.get(
        signal_market
    )

    print()
    print("=" * 80)
    print("SEÑAL")
    print("=" * 80)

    print()
    print(
        f"Partido: "
        f"{home} vs {away}"
    )

    print(
        f"Señal CulebrIA: "
        f"{signal_market}"
    )

    print(
        f"Probabilidad modelo: "
        f"{probability:.2f}%"
    )

    print(
        f"Sport key: "
        f"{sport_key}"
    )

    print(
        f"Event ID: "
        f"{event_id}"
    )

    print(
        f"Inicio: "
        f"{row['commence_time']}"
    )

    if api_market is None:

        print()
        print(
            "❌ No existe un mercado "
            "API configurado para esta señal."
        )

        print(
            "Créditos consumidos: 0"
        )

        return

    print(
        f"Mercado The Odds API: "
        f"{api_market}"
    )

    # ========================================================
    # COMPROBACIÓN DE HORA JUSTO ANTES DE PAGAR
    # ========================================================

    now = datetime.now(
        timezone.utc
    )

    if commence_time is None:

        print()
        print(
            "❌ Fecha del evento inválida."
        )

        print(
            "Créditos consumidos: 0"
        )

        return

    minutes_remaining = (
        commence_time
        - now
    ).total_seconds() / 60

    print()

    print(
        f"Faltan: "
        f"{minutes_remaining:.1f} minutos"
    )

    if minutes_remaining <= 0:

        print()
        print(
            "⛔ El partido ya comenzó."
        )

        print(
            "No se solicitarán cuotas LIVE."
        )

        print(
            "Créditos consumidos: 0"
        )

        return

    # ========================================================
    # CONSULTAR UN SOLO MERCADO
    # ========================================================

    url = (
        f"{BASE_URL}"
        f"/sports/"
        f"{sport_key}"
        f"/events/"
        f"{event_id}"
        f"/odds"
    )

    params = {
        "apiKey":
            api_key,

        "regions":
            "eu",

        "markets":
            api_market,

        "oddsFormat":
            "decimal",

        "dateFormat":
            "iso",
    }

    print()
    print("=" * 80)
    print(
        "CONSULTANDO CUOTA PREMATCH"
    )
    print("=" * 80)

    print()
    print(
        "Región: eu"
    )

    print(
        f"Mercado solicitado: "
        f"{api_market}"
    )

    try:

        response = requests.get(
            url,
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
    # CONTROL DE CRÉDITOS
    # --------------------------------------------------------

    remaining = response.headers.get(
        "x-requests-remaining",
        "?"
    )

    used = response.headers.get(
        "x-requests-used",
        "?"
    )

    last_cost = response.headers.get(
        "x-requests-last",
        "?"
    )

    print()
    print(
        f"HTTP status: "
        f"{response.status_code}"
    )

    print(
        f"Coste última petición: "
        f"{last_cost}"
    )

    print(
        f"Créditos utilizados: "
        f"{used}"
    )

    print(
        f"Créditos restantes: "
        f"{remaining}"
    )

    # --------------------------------------------------------
    # ERROR HTTP
    # --------------------------------------------------------

    if not response.ok:

        print()
        print(
            "❌ The Odds API rechazó "
            "la petición."
        )

        try:

            print(
                response.json()
            )

        except ValueError:

            print(
                response.text[:1000]
            )

        return

    # --------------------------------------------------------
    # RESPUESTA
    # --------------------------------------------------------

    data = response.json()

    # --------------------------------------------------------
    # GUARDAR JSON ORIGINAL
    # --------------------------------------------------------

    output_file = (
        OUTPUT_DIR
        / (
            f"{event_id}_"
            f"{api_market}.json"
        )
    )

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )

    # --------------------------------------------------------
    # MOSTRAR MERCADOS EXACTAMENTE COMO LLEGAN
    # --------------------------------------------------------

    market_count, outcome_count = (
        print_market_data(
            data=
                data,

            requested_market=
                api_market
        )
    )

    # ========================================================
    # RESULTADO
    # ========================================================

    print()
    print("=" * 80)
    print(
        "RESULTADO FINAL"
    )
    print("=" * 80)

    print()

    print(
        f"Mercados encontrados: "
        f"{market_count}"
    )

    print(
        f"Outcomes encontrados: "
        f"{outcome_count}"
    )

    print()

    if market_count == 0:

        print(
            "⚠️ El mercado solicitado "
            "no fue devuelto para este evento."
        )

        print(
            "No vamos a inventar una cuota."
        )

    else:

        print(
            "✅ Cuotas reales recibidas."
        )

    print()

    print(
        "JSON guardado en:"
    )

    print(
        output_file
    )

    print()

    print(
        "⚠️ Todavía NO estamos "
        "calculando EV."
    )

    print(
        "Primero verificaremos la estructura "
        "exacta del mercado recibido."
    )


if __name__ == "__main__":
    main()