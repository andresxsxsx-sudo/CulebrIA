import json
import unicodedata
from pathlib import Path

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parent

MARKET_FILE = (
    ROOT_DIR
    / "data"
    / "market_pool.csv"
)

FDORG_FILE = (
    ROOT_DIR
    / "data"
    / "football_data_org_competitions.json"
)

OUTPUT_FILE = (
    ROOT_DIR
    / "data"
    / "fdorg_core_matches.csv"
)


# Relación entre nombres usados por API-Football
# y códigos de football-data.org.
ALIASES = {
    ("portugal", "primeira liga"): "PPL",
    ("brazil", "serie a"): "BSA",

    ("england", "premier league"): "PL",
    ("england", "championship"): "ELC",

    ("spain", "la liga"): "PD",

    ("italy", "serie a"): "SA",

    ("germany", "bundesliga"): "BL1",

    ("france", "ligue 1"): "FL1",

    ("netherlands", "eredivisie"): "DED",

    ("world", "uefa champions league"): "CL",
    ("world", "world cup"): "WC",
    ("world", "european championship"): "EC",
}


def normalize(text):
    """
    Normaliza textos para facilitar comparaciones.
    """

    text = str(text).strip().lower()

    text = unicodedata.normalize(
        "NFKD",
        text
    )

    text = "".join(
        character
        for character in text
        if not unicodedata.combining(
            character
        )
    )

    return text


def main():

    print("=" * 70)
    print("CulebrIA - CRUCE CORE + FOOTBALL-DATA.ORG")
    print("=" * 70)

    # ------------------------------------------------
    # 1. CARGAR LOS 25 CORE
    # ------------------------------------------------

    market_df = pd.read_csv(
        MARKET_FILE
    )

    core_df = market_df[
        market_df[
            "market_status"
        ] == "CORE"
    ].copy()

    print()
    print(
        f"Partidos CORE actuales: "
        f"{len(core_df)}"
    )

    # ------------------------------------------------
    # 2. CARGAR LAS COMPETICIONES DE FOOTBALL-DATA
    # ------------------------------------------------

    with open(
        FDORG_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        cached = json.load(
            file
        )

    api_data = cached.get(
        "api_data",
        {}
    )

    competitions = api_data.get(
        "competitions",
        []
    )

    print(
        f"Competiciones disponibles "
        f"football-data.org: "
        f"{len(competitions)}"
    )

    # ------------------------------------------------
    # 3. CREAR ÍNDICE POR CÓDIGO
    # ------------------------------------------------

    fdorg_by_code = {}

    for item in competitions:

        code = item.get(
            "code"
        )

        if not code:
            continue

        fdorg_by_code[
            code
        ] = {
            "id":
                item.get("id"),

            "code":
                code,

            "name":
                item.get(
                    "name",
                    ""
                ),

            "area":
                item.get(
                    "area",
                    {}
                ).get(
                    "name",
                    ""
                )
        }

    # ------------------------------------------------
    # 4. MOSTRAR LAS COMPETICIONES DISPONIBLES
    # ------------------------------------------------

    print()
    print("=" * 70)
    print("COBERTURA DE TU CUENTA")
    print("=" * 70)

    for code, item in sorted(
        fdorg_by_code.items()
    ):

        print(
            f"{code:5} | "
            f"{item['area']} | "
            f"{item['name']}"
        )

    # ------------------------------------------------
    # 5. CRUZAR LOS PARTIDOS CORE
    # ------------------------------------------------

    supported = []
    unsupported = []

    for _, match in core_df.iterrows():

        country = normalize(
            match["country"]
        )

        competition = normalize(
            match["competition"]
        )

        alias_key = (
            country,
            competition
        )

        fdorg_code = ALIASES.get(
            alias_key
        )

        # El alias solo sirve si realmente
        # está disponible para nuestra cuenta.
        if (
            fdorg_code
            and fdorg_code
            in fdorg_by_code
        ):

            fdorg_competition = (
                fdorg_by_code[
                    fdorg_code
                ]
            )

            supported.append(
                {
                    "fixture_id":
                        match[
                            "fixture_id"
                        ],

                    "home":
                        match[
                            "home"
                        ],

                    "away":
                        match[
                            "away"
                        ],

                    "country":
                        match[
                            "country"
                        ],

                    "competition":
                        match[
                            "competition"
                        ],

                    "api_football_league_id":
                        match[
                            "league_id"
                        ],

                    "quality_score":
                        match[
                            "quality_score"
                        ],

                    "fdorg_code":
                        fdorg_code,

                    "fdorg_id":
                        fdorg_competition[
                            "id"
                        ],

                    "fdorg_name":
                        fdorg_competition[
                            "name"
                        ],
                }
            )

        else:

            unsupported.append(
                {
                    "home":
                        match[
                            "home"
                        ],

                    "away":
                        match[
                            "away"
                        ],

                    "country":
                        match[
                            "country"
                        ],

                    "competition":
                        match[
                            "competition"
                        ],
                }
            )

    # ------------------------------------------------
    # 6. GUARDAR LOS SOPORTADOS
    # ------------------------------------------------

    supported_df = pd.DataFrame(
        supported
    )

    supported_df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    # ------------------------------------------------
    # 7. RESUMEN
    # ------------------------------------------------

    print()
    print("=" * 70)
    print("RESULTADO DEL CRUCE")
    print("=" * 70)

    print()
    print(
        f"CORE totales: "
        f"{len(core_df)}"
    )

    print(
        f"CORE cubiertos: "
        f"{len(supported)}"
    )

    print(
        f"CORE todavía sin segunda fuente: "
        f"{len(unsupported)}"
    )

    # ------------------------------------------------
    # 8. MOSTRAR LOS CUBIERTOS
    # ------------------------------------------------

    print()
    print("=" * 70)
    print("CORE CUBIERTOS")
    print("=" * 70)

    for index, match in enumerate(
        supported,
        start=1
    ):

        print()

        print(
            f"{index}. "
            f"{match['home']} "
            f"vs "
            f"{match['away']}"
        )

        print(
            f"   "
            f"{match['country']} - "
            f"{match['competition']}"
        )

        print(
            f"   football-data.org: "
            f"{match['fdorg_code']} - "
            f"{match['fdorg_name']}"
        )

    # ------------------------------------------------
    # 9. COMPETICIONES NO CUBIERTAS
    # ------------------------------------------------

    missing_competitions = sorted(
        {
            (
                item["country"],
                item["competition"]
            )
            for item in unsupported
        }
    )

    print()
    print("=" * 70)
    print("COMPETICIONES CORE SIN SEGUNDA FUENTE")
    print("=" * 70)

    for country, competition in (
        missing_competitions
    ):

        print(
            f"- {country} - "
            f"{competition}"
        )

    print()
    print("=" * 70)

    print(
        "✅ Resultado guardado:"
    )

    print(
        OUTPUT_FILE
    )


if __name__ == "__main__":
    main()