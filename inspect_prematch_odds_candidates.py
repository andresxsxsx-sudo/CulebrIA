from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


# ============================================================
# CONFIGURACIÓN
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"

INPUT_FILE = (
    DATA_DIR
    / "odds_event_matches.csv"
)

OUTPUT_FILE = (
    DATA_DIR
    / "prematch_odds_candidates.csv"
)


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
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    print("=" * 80)
    print(
        "CulebrIA - FILTRO PREMATCH"
    )
    print("=" * 80)

    df = pd.read_csv(
        INPUT_FILE
    )

    # --------------------------------------------------------
    # SOLO MATCHED
    # --------------------------------------------------------

    df = df[
        df[
            "match_status"
        ] == "MATCHED"
    ].copy()

    print()
    print(
        f"Señales MATCHED: "
        f"{len(df)}"
    )

    print(
        f"Eventos únicos: "
        f"{df['event_id'].nunique()}"
    )

    now_utc = datetime.now(
        timezone.utc
    )

    print()
    print(
        f"Hora actual UTC: "
        f"{now_utc.isoformat()}"
    )

    rows = []

    # ========================================================
    # EVALUAR CADA SEÑAL
    # ========================================================

    for _, row in df.iterrows():

        commence_time = parse_datetime(
            row[
                "odds_commence_time"
            ]
        )

        if commence_time is None:

            timing_status = (
                "FECHA_INVALIDA"
            )

            minutes_to_start = None

        else:

            seconds = (
                commence_time
                - now_utc
            ).total_seconds()

            minutes_to_start = (
                seconds
                / 60
            )

            if minutes_to_start > 0:

                timing_status = (
                    "PREMATCH"
                )

            else:

                timing_status = (
                    "YA_INICIADO"
                )

        rows.append(
            {
                "fixture_id":
                    row[
                        "fixture_id"
                    ],

                "competition":
                    row[
                        "competition"
                    ],

                "sport_key":
                    row[
                        "sport_key"
                    ],

                "event_id":
                    row[
                        "event_id"
                    ],

                "home":
                    row[
                        "home"
                    ],

                "away":
                    row[
                        "away"
                    ],

                "signal_market":
                    row[
                        "signal_market"
                    ],

                "model_probability_pct":
                    row[
                        "model_probability_pct"
                    ],

                "grade":
                    row[
                        "grade"
                    ],

                "commence_time":
                    row[
                        "odds_commence_time"
                    ],

                "minutes_to_start":
                    (
                        round(
                            minutes_to_start,
                            1
                        )
                        if minutes_to_start
                        is not None
                        else None
                    ),

                "timing_status":
                    timing_status,
            }
        )

    result_df = pd.DataFrame(
        rows
    )

    # ========================================================
    # GUARDAR
    # ========================================================

    result_df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # TERMINAL
    # ========================================================

    print()
    print("=" * 80)
    print(
        "ESTADO DE LAS SEÑALES"
    )
    print("=" * 80)

    for _, row in (
        result_df.iterrows()
    ):

        print()
        print(
            f"{row['home']} "
            f"vs "
            f"{row['away']}"
        )

        print(
            f"Mercado: "
            f"{row['signal_market']}"
        )

        print(
            f"Probabilidad: "
            f"{row['model_probability_pct']}%"
        )

        print(
            f"Estado: "
            f"{row['timing_status']}"
        )

        if pd.notna(
            row[
                "minutes_to_start"
            ]
        ):

            if (
                row[
                    "minutes_to_start"
                ]
                > 0
            ):

                print(
                    f"Faltan aproximadamente: "
                    f"{row['minutes_to_start']:.1f} "
                    f"minutos"
                )

            else:

                print(
                    f"Comenzó hace aproximadamente: "
                    f"{abs(row['minutes_to_start']):.1f} "
                    f"minutos"
                )

        print(
            "-" * 60
        )

    # ========================================================
    # RESUMEN
    # ========================================================

    prematch_df = result_df[
        result_df[
            "timing_status"
        ] == "PREMATCH"
    ]

    started_df = result_df[
        result_df[
            "timing_status"
        ] == "YA_INICIADO"
    ]

    unique_prematch = (
        prematch_df[
            "event_id"
        ].nunique()
    )

    print()
    print("=" * 80)
    print(
        "RESULTADO FINAL"
    )
    print("=" * 80)

    print()

    print(
        f"Señales PREMATCH: "
        f"{len(prematch_df)}"
    )

    print(
        f"Señales ya iniciadas: "
        f"{len(started_df)}"
    )

    print(
        f"Eventos PREMATCH únicos: "
        f"{unique_prematch}"
    )

    print()

    print(
        "Créditos utilizados: 0"
    )

    print()

    print(
        "Archivo:"
    )

    print(
        OUTPUT_FILE
    )


if __name__ == "__main__":
    main()