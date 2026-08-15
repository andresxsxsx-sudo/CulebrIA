from pathlib import Path

import pandas as pd


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


def main():

    print("=" * 70)
    print("CulebrIA - INSPECCIÓN DEL CORE")
    print("=" * 70)

    market_df = pd.read_csv(
        MARKET_FILE
    )

    quality_df = pd.read_csv(
        QUALITY_FILE
    )

    # Solo partidos CORE
    core_df = market_df[
        market_df["market_status"] == "CORE"
    ].copy()

    # Nos quedamos con la temporada
    seasons = quality_df[
        [
            "League_ID",
            "Temporada_partido"
        ]
    ].copy()

    seasons = seasons.rename(
        columns={
            "League_ID": "league_id",
            "Temporada_partido": "season"
        }
    )

    core_df = core_df.merge(
        seasons,
        on="league_id",
        how="left"
    )

    print()
    print(
        f"Partidos CORE: "
        f"{len(core_df)}"
    )

    unique_leagues = (
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
    )

    print(
        f"Ligas/temporadas únicas: "
        f"{len(unique_leagues)}"
    )

    print()
    print("=" * 70)
    print("LIGAS CORE")
    print("=" * 70)

    for index, row in enumerate(
        unique_leagues.itertuples(
            index=False
        ),
        start=1
    ):

        matches = core_df[
            core_df["league_id"]
            == row.league_id
        ]

        print()
        print(
            f"{index}. "
            f"{row.country} - "
            f"{row.competition}"
        )

        print(
            f"   League ID: "
            f"{row.league_id}"
        )

        print(
            f"   Temporada: "
            f"{row.season}"
        )

        print(
            f"   Partidos CORE hoy: "
            f"{len(matches)}"
        )

    print()
    print("=" * 70)

    print()
    print(
        "Solicitudes estimadas para "
        "descargar el histórico:"
    )

    print(
        len(unique_leagues)
    )


if __name__ == "__main__":
    main()