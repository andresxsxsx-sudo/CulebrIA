from pathlib import Path

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parent

INPUT_FILE = (
    ROOT_DIR
    / "data"
    / "fdorg_core_matches.csv"
)


def main():

    print("=" * 70)
    print("CulebrIA - CORE CON DATOS ACTUALES")
    print("=" * 70)

    df = pd.read_csv(
        INPUT_FILE
    )

    print()
    print(
        f"Partidos CORE cubiertos: "
        f"{len(df)}"
    )

    # -----------------------------------------
    # COMPETICIONES ÚNICAS
    # -----------------------------------------

    competitions = (
        df[
            [
                "fdorg_code",
                "fdorg_id",
                "fdorg_name"
            ]
        ]
        .drop_duplicates()
        .sort_values(
            "fdorg_code"
        )
        .reset_index(
            drop=True
        )
    )

    print(
        f"Competiciones únicas: "
        f"{len(competitions)}"
    )

    # -----------------------------------------
    # MOSTRAR COMPETICIONES
    # -----------------------------------------

    print()
    print("=" * 70)
    print("COMPETICIONES")
    print("=" * 70)

    for index, row in competitions.iterrows():

        code = row[
            "fdorg_code"
        ]

        matches = df[
            df["fdorg_code"] == code
        ]

        print()

        print(
            f"{index + 1}. "
            f"{row['fdorg_name']}"
        )

        print(
            f"   Código: "
            f"{code}"
        )

        print(
            f"   ID: "
            f"{row['fdorg_id']}"
        )

        print(
            f"   Partidos CORE hoy: "
            f"{len(matches)}"
        )

    # -----------------------------------------
    # MOSTRAR PARTIDOS
    # -----------------------------------------

    print()
    print("=" * 70)
    print("PARTIDOS CORE CUBIERTOS")
    print("=" * 70)

    for index, row in df.iterrows():

        print()

        print(
            f"{index + 1}. "
            f"{row['home']} "
            f"vs "
            f"{row['away']}"
        )

        print(
            f"   "
            f"{row['country']} - "
            f"{row['competition']}"
        )

        print(
            f"   Fuente: "
            f"{row['fdorg_code']}"
        )

        print(
            f"   Calidad API-Football: "
            f"{row['quality_score']}/100"
        )

    print()
    print("=" * 70)

    print(
        "Consultas API realizadas: 0"
    )


if __name__ == "__main__":
    main()