import time
from pathlib import Path

import pandas as pd

from src.api.fdorg_matches_api import (
    get_competition_matches
)


ROOT_DIR = Path(__file__).resolve().parent

INPUT_FILE = (
    ROOT_DIR
    / "data"
    / "fdorg_core_matches.csv"
)

WAIT_SECONDS = 7


def main():

    print("=" * 70)
    print("CulebrIA - DATOS ACTUALES CORE")
    print("=" * 70)

    # -----------------------------------------
    # 1. CARGAR CORE CUBIERTO
    # -----------------------------------------

    core_df = pd.read_csv(
        INPUT_FILE
    )

    competitions = (
        core_df[
            [
                "fdorg_code",
                "fdorg_id",
                "fdorg_name"
            ]
        ]
        .drop_duplicates()
        .reset_index(
            drop=True
        )
    )

    print()
    print(
        f"Partidos CORE cubiertos: "
        f"{len(core_df)}"
    )

    print(
        f"Competiciones a descargar: "
        f"{len(competitions)}"
    )

    print()

    api_requests = 0
    cache_hits = 0
    errors = 0

    # -----------------------------------------
    # 2. DESCARGAR
    # -----------------------------------------

    for index, row in competitions.iterrows():

        code = str(
            row["fdorg_code"]
        )

        name = row[
            "fdorg_name"
        ]

        print("=" * 70)

        print(
            f"[{index + 1}/"
            f"{len(competitions)}]"
        )

        print(
            f"{name} ({code})"
        )

        try:

            result = (
                get_competition_matches(
                    code
                )
            )

            matches = result[
                "matches"
            ]

            result_set = result[
                "result_set"
            ]

            finished = [
                match
                for match in matches
                if match.get(
                    "status"
                ) == "FINISHED"
            ]

            future = [
                match
                for match in matches
                if match.get(
                    "status"
                ) in {
                    "SCHEDULED",
                    "TIMED"
                }
            ]

            print(
                f"Partidos recibidos: "
                f"{len(matches)}"
            )

            print(
                f"Finalizados: "
                f"{len(finished)}"
            )

            print(
                f"Pendientes: "
                f"{len(future)}"
            )

            print(
                f"Temporada aplicada: "
                f"{result['filters'].get('season', '?')}"
            )

            # ---------------------------------
            # ORIGEN
            # ---------------------------------

            if result[
                "source"
            ] == "api":

                api_requests += 1

                print(
                    "Fuente: "
                    "🌐 football-data.org"
                )

            else:

                cache_hits += 1

                print(
                    "Fuente: "
                    "💾 Caché local"
                )

                print(
                    "Solicitudes consumidas: 0"
                )

            # ---------------------------------
            # ESPERA SOLO SI HUBO API
            # ---------------------------------

            if (
                result["source"] == "api"
                and index
                < len(competitions) - 1
            ):

                print(
                    f"Esperando "
                    f"{WAIT_SECONDS}s..."
                )

                time.sleep(
                    WAIT_SECONDS
                )

        except Exception as error:

            errors += 1

            print()
            print("❌ Error:")
            print(error)

        print()

    # -----------------------------------------
    # 3. RESUMEN
    # -----------------------------------------

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
        "Datos guardados en:"
    )

    print(
        ROOT_DIR
        / "data"
        / "fdorg_matches"
    )


if __name__ == "__main__":
    main()