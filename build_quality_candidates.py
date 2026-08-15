import csv
from collections import Counter
from pathlib import Path

import pandas as pd

from src.api.football_api import get_today_fixtures
from src.analysis.fixture_filter import filter_candidate_fixtures


ROOT_DIR = Path(__file__).resolve().parent

QUALITY_FILE = (
    ROOT_DIR
    / "data"
    / "league_quality_report.csv"
)

OUTPUT_FILE = (
    ROOT_DIR
    / "data"
    / "quality_candidates.csv"
)


def main():

    print("=" * 70)
    print("CulebrIA - FILTRO POR CALIDAD DE DATOS")
    print("=" * 70)

    # ------------------------------------------------
    # 1. CARGAR PARTIDOS DESDE CACHÉ
    # ------------------------------------------------

    fixture_data = get_today_fixtures()

    filtered = filter_candidate_fixtures(
        fixture_data["fixtures"]
    )

    candidates = filtered["fixtures"]

    print()
    print(
        f"Partidos futuros actuales: "
        f"{len(candidates)}"
    )

    # ------------------------------------------------
    # 2. CARGAR CALIDAD DE LIGAS
    # ------------------------------------------------

    quality_df = pd.read_csv(
        QUALITY_FILE
    )

    quality_index = {}

    for _, row in quality_df.iterrows():

        league_id = int(
            row["League_ID"]
        )

        quality_index[
            league_id
        ] = {
            "score":
                int(row["Puntuacion"]),

            "grade":
                str(row["Nivel"]),

            "country":
                row["Pais"],

            "competition":
                row["Competicion"],
        }

    # ------------------------------------------------
    # 3. CRUZAR PARTIDOS CON CALIDAD
    # ------------------------------------------------

    grade_counter = Counter()

    matched = []

    missing = []

    for fixture_item in candidates:

        league = fixture_item.get(
            "league",
            {}
        )

        teams = fixture_item.get(
            "teams",
            {}
        )

        fixture = fixture_item.get(
            "fixture",
            {}
        )

        league_id = league.get(
            "id"
        )

        quality = quality_index.get(
            league_id
        )

        if quality is None:

            missing.append(
                {
                    "league_id":
                        league_id,

                    "country":
                        league.get(
                            "country",
                            "Desconocido"
                        ),

                    "competition":
                        league.get(
                            "name",
                            "Desconocida"
                        ),

                    "home":
                        teams.get(
                            "home",
                            {}
                        ).get(
                            "name",
                            "Desconocido"
                        ),

                    "away":
                        teams.get(
                            "away",
                            {}
                        ).get(
                            "name",
                            "Desconocido"
                        )
                }
            )

            continue

        grade = quality[
            "grade"
        ]

        grade_counter[
            grade
        ] += 1

        matched.append(
            {
                "fixture_id":
                    fixture.get("id"),

                "league_id":
                    league_id,

                "country":
                    league.get(
                        "country",
                        ""
                    ),

                "competition":
                    league.get(
                        "name",
                        ""
                    ),

                "home":
                    teams.get(
                        "home",
                        {}
                    ).get(
                        "name",
                        ""
                    ),

                "away":
                    teams.get(
                        "away",
                        {}
                    ).get(
                        "name",
                        ""
                    ),

                "date":
                    fixture.get(
                        "date",
                        ""
                    ),

                "quality_score":
                    quality[
                        "score"
                    ],

                "grade":
                    grade
            }
        )

    # ------------------------------------------------
    # 4. RESUMEN
    # ------------------------------------------------

    print()
    print("=" * 70)
    print("PARTIDOS POR NIVEL")
    print("=" * 70)

    print(
        f"Nivel A: "
        f"{grade_counter.get('A', 0)}"
    )

    print(
        f"Nivel B: "
        f"{grade_counter.get('B', 0)}"
    )

    print(
        f"Nivel C: "
        f"{grade_counter.get('C', 0)}"
    )

    print(
        f"Nivel D: "
        f"{grade_counter.get('D', 0)}"
    )

    print()

    print(
        f"Partidos con calidad conocida: "
        f"{len(matched)}"
    )

    print(
        f"Partidos sin calidad asignada: "
        f"{len(missing)}"
    )

    # ------------------------------------------------
    # 5. GUARDAR TODOS LOS PARTIDOS EVALUADOS
    # ------------------------------------------------

    with open(
        OUTPUT_FILE,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=[
                "fixture_id",
                "league_id",
                "country",
                "competition",
                "home",
                "away",
                "date",
                "quality_score",
                "grade"
            ]
        )

        writer.writeheader()

        writer.writerows(
            matched
        )

    # ------------------------------------------------
    # 6. MOSTRAR LAS COMPETICIONES SIN COBERTURA
    # ------------------------------------------------

    if missing:

        print()
        print("=" * 70)
        print("SIN CALIDAD ASIGNADA")
        print("=" * 70)

        shown = set()

        for item in missing:

            key = (
                item["league_id"],
                item["competition"]
            )

            if key in shown:
                continue

            shown.add(key)

            print()

            print(
                f"{item['country']} - "
                f"{item['competition']}"
            )

            print(
                f"League ID: "
                f"{item['league_id']}"
            )

    print()
    print("=" * 70)

    print(
        "✅ Archivo creado:"
    )

    print(
        OUTPUT_FILE
    )


if __name__ == "__main__":
    main()