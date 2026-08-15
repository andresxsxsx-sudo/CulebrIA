from collections import Counter
from pathlib import Path

import pandas as pd

from src.analysis.market_eligibility import (
    classify_market_eligibility
)


ROOT_DIR = Path(__file__).resolve().parent

QUALITY_FILE = (
    ROOT_DIR
    / "data"
    / "league_quality_report.csv"
)

CANDIDATES_FILE = (
    ROOT_DIR
    / "data"
    / "quality_candidates.csv"
)

OUTPUT_FILE = (
    ROOT_DIR
    / "data"
    / "market_pool.csv"
)


def main():

    print("=" * 70)
    print("CulebrIA - MARKET POOL")
    print("=" * 70)

    # -----------------------------------------
    # 1. CARGAR ARCHIVOS LOCALES
    # -----------------------------------------

    quality_df = pd.read_csv(
        QUALITY_FILE
    )

    candidates_df = pd.read_csv(
        CANDIDATES_FILE
    )

    # -----------------------------------------
    # 2. CREAR ÍNDICE DE CALIDAD
    # -----------------------------------------

    quality_index = {}

    for _, row in quality_df.iterrows():

        league_id = int(
            row["League_ID"]
        )

        quality_index[
            league_id
        ] = row.to_dict()

    # -----------------------------------------
    # 3. CLASIFICAR CADA PARTIDO
    # -----------------------------------------

    output_rows = []

    status_counter = Counter()

    missing = 0

    for _, match in candidates_df.iterrows():

        league_id = int(
            match["league_id"]
        )

        quality_row = quality_index.get(
            league_id
        )

        if quality_row is None:

            missing += 1
            continue

        eligibility = (
            classify_market_eligibility(
                quality_row
            )
        )

        status = eligibility[
            "status"
        ]

        status_counter[
            status
        ] += 1

        output_rows.append(
            {
                "fixture_id":
                    match["fixture_id"],

                "league_id":
                    league_id,

                "country":
                    match["country"],

                "competition":
                    match["competition"],

                "home":
                    match["home"],

                "away":
                    match["away"],

                "date":
                    match["date"],

                "quality_score":
                    match["quality_score"],

                "grade":
                    match["grade"],

                "market_status":
                    status,

                "fixture_stats":
                    eligibility[
                        "fixture_stats"
                    ],

                "standings":
                    eligibility[
                        "standings"
                    ],

                "lineups":
                    eligibility[
                        "lineups"
                    ],

                "injuries":
                    eligibility[
                        "injuries"
                    ],

                "odds_signal":
                    eligibility[
                        "odds_signal"
                    ],
            }
        )

    # -----------------------------------------
    # 4. GUARDAR RESULTADO
    # -----------------------------------------

    output_df = pd.DataFrame(
        output_rows
    )

    output_df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    # -----------------------------------------
    # 5. RESUMEN
    # -----------------------------------------

    print()
    print("RESULTADO")
    print("-" * 70)

    print(
        f"CORE: "
        f"{status_counter.get('CORE', 0)}"
    )

    print(
        f"CONTEXTUAL: "
        f"{status_counter.get('CONTEXTUAL', 0)}"
    )

    print(
        f"DESCARTADOS: "
        f"{status_counter.get('DESCARTADO', 0)}"
    )

    print(
        f"SIN CLASIFICAR: "
        f"{missing}"
    )

    print()

    print(
        f"Total procesado: "
        f"{len(output_rows)}"
    )

    print()
    print("✅ Archivo creado:")
    print(OUTPUT_FILE)


if __name__ == "__main__":
    main()