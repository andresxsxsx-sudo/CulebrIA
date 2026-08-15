import time
from pathlib import Path

import pandas as pd

from src.api.history_api import (
    get_league_history
)


ROOT_DIR = Path(__file__).resolve().parent

MARKET_FILE = (
    ROOT_DIR
    / "data"
    / "market_pool.csv"
)

QUALITY_FILE = (
    ROOT_DIR
    / "data"
    / "league_quality_report.csv"
)


# Esperaremos 7 segundos entre
# peticiones reales para respetar
# el límite por minuto.
WAIT_SECONDS = 7


def main():

    print("=" * 70)
    print("CulebrIA - DESCARGA DE HISTÓRICOS CORE")
    print("=" * 70)

    # -----------------------------------------
    # CARGAR DATOS
    # -----------------------------------------

    market_df = pd.read_csv(
        MARKET_FILE
    )

    quality_df = pd.read_csv(
        QUALITY_FILE
    )

    # Solo CORE
    core_df = market_df[
        market_df[
            "market_status"
        ] == "CORE"
    ].copy()

    # Obtener temporadas
    seasons = quality_df[
        [
            "League_ID",
            "Temporada_partido"
        ]
    ].copy()

    seasons = seasons.rename(
        columns={
            "League_ID":
                "league_id",

            "Temporada_partido":
                "season"
        }
    )

    core_df = core_df.merge(
        seasons,
        on="league_id",
        how="left"
    )

    # -----------------------------------------
    # LIGAS ÚNICAS
    # -----------------------------------------

    leagues = (
        core_df[
            [
                "league_id",
                "country",
                "competition",
                "season"
            ]
        ]
        .drop_duplicates()
        .sort_values(
            [
                "country",
                "competition"
            ]
        )
        .reset_index(
            drop=True
        )
    )

    print()
    print(
        f"Partidos CORE: "
        f"{len(core_df)}"
    )

    print(
        f"Ligas/temporadas: "
        f"{len(leagues)}"
    )

    print()

    api_requests = 0
    cache_hits = 0
    errors = 0

    # -----------------------------------------
    # DESCARGAR UNA A UNA
    # -----------------------------------------

    for index, row in leagues.iterrows():

        league_id = int(
            row["league_id"]
        )

        season = int(
            row["season"]
        )

        country = row[
            "country"
        ]

        competition = row[
            "competition"
        ]

        print("=" * 70)

        print(
            f"[{index + 1}/"
            f"{len(leagues)}]"
        )

        print(
            f"{country} - "
            f"{competition}"
        )

        print(
            f"League ID: "
            f"{league_id}"
        )

        print(
            f"Temporada: "
            f"{season}"
        )

        try:

            result = get_league_history(
                league_id,
                season
            )

            print(
                f"Fixtures disponibles: "
                f"{result['results']}"
            )

            # -----------------------------
            # API
            # -----------------------------

            if result[
                "source"
            ] == "api":

                api_requests += 1

                print(
                    "Fuente: "
                    "🌐 API-Football"
                )

                print(
                    "Solicitudes restantes: "
                    f"{result['remaining']}"
                )

                print(
                    "💾 Histórico guardado."
                )

                # Esperar antes de otra
                # petición real.
                if (
                    index
                    < len(leagues) - 1
                ):

                    print(
                        f"Esperando "
                        f"{WAIT_SECONDS}s..."
                    )

                    time.sleep(
                        WAIT_SECONDS
                    )

            # -----------------------------
            # CACHÉ
            # -----------------------------

            else:

                cache_hits += 1

                print(
                    "Fuente: "
                    "💾 Caché local"
                )

                print(
                    "Solicitudes "
                    "consumidas: 0"
                )

        except Exception as error:

            errors += 1

            print(
                "❌ Error:"
            )

            print(
                error
            )

            # Continuar con la siguiente
            # liga en vez de detener todo.
            continue

        print()

    # -----------------------------------------
    # RESUMEN
    # -----------------------------------------

    print()
    print("=" * 70)
    print("DESCARGA FINALIZADA")
    print("=" * 70)

    print(
        f"Peticiones realizadas: "
        f"{api_requests}"
    )

    print(
        f"Archivos reutilizados: "
        f"{cache_hits}"
    )

    print(
        f"Errores: "
        f"{errors}"
    )

    print()

    print(
        "Los históricos están en:"
    )

    print(
        ROOT_DIR
        / "data"
        / "history"
    )


if __name__ == "__main__":
    main()