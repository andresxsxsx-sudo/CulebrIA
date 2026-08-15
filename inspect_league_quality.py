import csv
from collections import Counter
from pathlib import Path

from src.api.football_api import get_today_fixtures
from src.api.league_api import get_leagues_coverage

from src.analysis.fixture_filter import (
    filter_candidate_fixtures
)

from src.analysis.league_quality import (
    calculate_league_quality
)


ROOT_DIR = Path(__file__).resolve().parent

OUTPUT_FILE = (
    ROOT_DIR
    / "data"
    / "league_quality_report.csv"
)


def yes_no(value):

    if value:
        return "SI"

    return "NO"


def main():

    print("=" * 70)
    print("CulebrIA - CALIDAD DE COMPETICIONES")
    print("=" * 70)

    # -----------------------------------------
    # 1. PARTIDOS ACTUALES
    # -----------------------------------------

    fixture_data = get_today_fixtures()

    filtered = filter_candidate_fixtures(
        fixture_data["fixtures"]
    )

    candidates = filtered["fixtures"]

    print()
    print(
        f"Partidos candidatos actuales: "
        f"{len(candidates)}"
    )

    # -----------------------------------------
    # 2. COBERTURA DE LIGAS
    # -----------------------------------------

    print()
    print(
        "Cargando cobertura de "
        "competiciones..."
    )

    league_data = get_leagues_coverage()

    print()

    if league_data["source"] == "api":

        print(
            "Fuente cobertura: "
            "🌐 API-Football"
        )

        print(
            "Solicitudes API restantes: "
            f"{league_data['remaining']}"
        )

    else:

        print(
            "Fuente cobertura: "
            "💾 Caché local"
        )

        print(
            "Solicitudes consumidas: 0"
        )

    # -----------------------------------------
    # 3. ÍNDICE POR LEAGUE ID
    # -----------------------------------------

    league_index = {}

    for item in league_data["leagues"]:

        league = item.get(
            "league",
            {}
        )

        league_id = league.get(
            "id"
        )

        if league_id is not None:

            league_index[
                league_id
            ] = item

    # -----------------------------------------
    # 4. COMPETICIONES DE LOS CANDIDATOS
    # -----------------------------------------

    candidate_competitions = {}

    for fixture in candidates:

        league = fixture.get(
            "league",
            {}
        )

        league_id = league.get(
            "id"
        )

        if league_id is None:
            continue

        if league_id not in candidate_competitions:

            candidate_competitions[
                league_id
            ] = {
                "country":
                    league.get(
                        "country",
                        "Desconocido"
                    ),

                "name":
                    league.get(
                        "name",
                        "Desconocida"
                    ),

                "season":
                    league.get(
                        "season"
                    ),

                "matches": 0
            }

        candidate_competitions[
            league_id
        ]["matches"] += 1

    # -----------------------------------------
    # 5. CALCULAR CALIDAD
    # -----------------------------------------

    results = []

    missing = []

    for (
        league_id,
        competition
    ) in candidate_competitions.items():

        api_league = league_index.get(
            league_id
        )

        if api_league is None:

            missing.append(
                {
                    "id": league_id,
                    "country":
                        competition[
                            "country"
                        ],
                    "name":
                        competition[
                            "name"
                        ]
                }
            )

            continue

        quality = calculate_league_quality(
            api_league,
            target_season=competition[
                "season"
            ]
        )

        if quality is None:
            continue

        results.append(
            {
                "league_id":
                    league_id,

                "country":
                    competition[
                        "country"
                    ],

                "name":
                    competition[
                        "name"
                    ],

                "fixture_season":
                    competition[
                        "season"
                    ],

                "coverage_season":
                    quality[
                        "season"
                    ],

                "matches":
                    competition[
                        "matches"
                    ],

                "score":
                    quality[
                        "score"
                    ],

                "grade":
                    quality[
                        "grade"
                    ],

                "coverage":
                    quality[
                        "coverage"
                    ]
            }
        )

    # Mejor calidad primero
    results.sort(
        key=lambda item: (
            item["score"],
            item["matches"]
        ),
        reverse=True
    )

    # -----------------------------------------
    # 6. RESUMEN A/B/C/D
    # -----------------------------------------

    grade_counter = Counter(
        item["grade"]
        for item in results
    )

    print()
    print("=" * 70)
    print("RESUMEN")
    print("=" * 70)

    print(
        f"Competiciones candidatas: "
        f"{len(candidate_competitions)}"
    )

    print(
        f"Competiciones evaluadas: "
        f"{len(results)}"
    )

    print(
        f"Sin información: "
        f"{len(missing)}"
    )

    print()

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

    # -----------------------------------------
    # 7. GUARDAR CSV
    # -----------------------------------------

    with open(
        OUTPUT_FILE,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.writer(
            file
        )

        writer.writerow(
            [
                "Pais",
                "Competicion",
                "League_ID",
                "Temporada_partido",
                "Temporada_cobertura",
                "Partidos_futuros",
                "Puntuacion",
                "Nivel",
                "Estadisticas_partido",
                "Estadisticas_jugador",
                "Alineaciones",
                "Lesiones",
                "Clasificacion",
                "Jugadores",
                "Eventos",
                "Predicciones",
                "Odds"
            ]
        )

        for item in results:

            coverage = item[
                "coverage"
            ]

            writer.writerow(
                [
                    item["country"],
                    item["name"],
                    item["league_id"],
                    item["fixture_season"],
                    item["coverage_season"],
                    item["matches"],
                    item["score"],
                    item["grade"],

                    yes_no(
                        coverage[
                            "fixture_statistics"
                        ]
                    ),

                    yes_no(
                        coverage[
                            "player_statistics"
                        ]
                    ),

                    yes_no(
                        coverage[
                            "lineups"
                        ]
                    ),

                    yes_no(
                        coverage[
                            "injuries"
                        ]
                    ),

                    yes_no(
                        coverage[
                            "standings"
                        ]
                    ),

                    yes_no(
                        coverage[
                            "players"
                        ]
                    ),

                    yes_no(
                        coverage[
                            "events"
                        ]
                    ),

                    yes_no(
                        coverage[
                            "predictions"
                        ]
                    ),

                    yes_no(
                        coverage[
                            "odds"
                        ]
                    ),
                ]
            )

    # -----------------------------------------
    # 8. MOSTRAR RESULTADOS
    # -----------------------------------------

    print()
    print("=" * 70)
    print("RANKING DE CALIDAD")
    print("=" * 70)

    for index, item in enumerate(
        results,
        start=1
    ):

        print()

        print(
            f"{index}. "
            f"{item['country']} - "
            f"{item['name']}"
        )

        print(
            f"   League ID: "
            f"{item['league_id']}"
        )

        print(
            f"   Partidos futuros: "
            f"{item['matches']}"
        )

        print(
            f"   Calidad: "
            f"{item['score']}/100"
        )

        print(
            f"   Nivel: "
            f"{item['grade']}"
        )

    print()
    print("=" * 70)

    print(
        "✅ Informe guardado en:"
    )

    print(
        OUTPUT_FILE
    )


if __name__ == "__main__":
    main()