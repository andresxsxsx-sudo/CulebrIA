import os

import requests
from dotenv import load_dotenv


# ============================================================
# CONFIGURACIÓN
# ============================================================

BASE_URL = "https://api.the-odds-api.com/v4"

load_dotenv()


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    print("=" * 76)
    print("CulebrIA - PRUEBA THE ODDS API")
    print("=" * 76)

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
    # ENDPOINT /SPORTS
    #
    # Este endpoint no consume créditos.
    # --------------------------------------------------------

    url = (
        f"{BASE_URL}/sports"
    )

    params = {
        "apiKey":
            api_key,

        # Queremos ver también deportes/ligas
        # que actualmente puedan estar fuera
        # de temporada.
        "all":
            "true"
    }

    print()
    print(
        "Consultando deportes disponibles..."
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

    print()

    print(
        f"HTTP status: "
        f"{response.status_code}"
    )

    # --------------------------------------------------------
    # CUOTA
    # --------------------------------------------------------

    remaining = response.headers.get(
        "x-requests-remaining",
        "?"
    )

    used = response.headers.get(
        "x-requests-used",
        "?"
    )

    last = response.headers.get(
        "x-requests-last",
        "?"
    )

    print(
        f"Créditos restantes: "
        f"{remaining}"
    )

    print(
        f"Créditos utilizados: "
        f"{used}"
    )

    print(
        f"Coste última petición: "
        f"{last}"
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

    sports = response.json()

    print()
    print(
        f"Deportes/competiciones recibidos: "
        f"{len(sports)}"
    )

    # --------------------------------------------------------
    # SOLO SOCCER
    # --------------------------------------------------------

    soccer = [
        item
        for item in sports

        if str(
            item.get(
                "group",
                ""
            )
        ).lower() == "soccer"
    ]

    print(
        f"Competiciones de fútbol: "
        f"{len(soccer)}"
    )

    # --------------------------------------------------------
    # BUSCAR BRASIL Y PORTUGAL
    # --------------------------------------------------------

    keywords = [
        "brazil",
        "brasil",
        "brasileiro",
        "portugal",
        "primeira",
        "liga portugal"
    ]

    candidates = []

    for item in soccer:

        search_text = (
            f"{item.get('key', '')} "
            f"{item.get('title', '')} "
            f"{item.get('description', '')}"
        ).lower()

        if any(
            keyword in search_text
            for keyword in keywords
        ):

            candidates.append(
                item
            )

    # --------------------------------------------------------
    # MOSTRAR CANDIDATOS
    # --------------------------------------------------------

    print()
    print("=" * 76)
    print(
        "POSIBLES LIGAS PARA CulebrIA"
    )
    print("=" * 76)

    if not candidates:

        print()
        print(
            "⚠️ No se encontraron "
            "coincidencias automáticas."
        )

    else:

        for item in candidates:

            print()

            print(
                f"Key: "
                f"{item.get('key', '?')}"
            )

            print(
                f"Título: "
                f"{item.get('title', '?')}"
            )

            print(
                f"Descripción: "
                f"{item.get('description', '?')}"
            )

            print(
                f"Activo: "
                f"{item.get('active', '?')}"
            )

    print()
    print("=" * 76)

    print(
        "✅ Conexión terminada."
    )

    print()

    print(
        "Este endpoint debe consumir "
        "0 créditos."
    )


if __name__ == "__main__":
    main()