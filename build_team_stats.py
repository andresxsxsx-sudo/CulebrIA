from pathlib import Path

import pandas as pd

from src.analysis.team_stats import (
    calculate_team_profile,
    parse_datetime
)

from src.api.fdorg_local_history import (
    load_competition_history
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"

VALIDATION_FILE = (
    DATA_DIR
    / "cross_source_validation.csv"
)

AUDIT_FILE = (
    DATA_DIR
    / "model_sample_audit.csv"
)

OUTPUT_FILE = (
    DATA_DIR
    / "team_stats_report.csv"
)


# ============================================================
# UTILIDADES
# ============================================================

def pct(value):
    return round(
        value * 100,
        1
    )


def add_stats(
    output,
    prefix,
    stats
):
    """
    Añade un bloque estadístico al registro
    que posteriormente guardaremos en CSV.
    """

    output[
        f"{prefix}_matches"
    ] = stats["matches"]

    output[
        f"{prefix}_win_pct"
    ] = pct(
        stats.get(
            "win_rate",
            0
        )
    )

    output[
        f"{prefix}_draw_pct"
    ] = pct(
        stats.get(
            "draw_rate",
            0
        )
    )

    output[
        f"{prefix}_loss_pct"
    ] = pct(
        stats.get(
            "loss_rate",
            0
        )
    )

    output[
        f"{prefix}_gf_avg"
    ] = round(
        stats[
            "avg_goals_for"
        ],
        3
    )

    output[
        f"{prefix}_ga_avg"
    ] = round(
        stats[
            "avg_goals_against"
        ],
        3
    )

    output[
        f"{prefix}_scored_pct"
    ] = pct(
        stats[
            "scored_rate"
        ]
    )

    output[
        f"{prefix}_clean_sheet_pct"
    ] = pct(
        stats[
            "clean_sheet_rate"
        ]
    )

    output[
        f"{prefix}_btts_pct"
    ] = pct(
        stats[
            "btts_rate"
        ]
    )

    output[
        f"{prefix}_over05_pct"
    ] = pct(
        stats[
            "over_05_rate"
        ]
    )

    output[
        f"{prefix}_over15_pct"
    ] = pct(
        stats[
            "over_15_rate"
        ]
    )

    output[
        f"{prefix}_over25_pct"
    ] = pct(
        stats[
            "over_25_rate"
        ]
    )

    output[
        f"{prefix}_under35_pct"
    ] = pct(
        stats[
            "under_35_rate"
        ]
    )


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    print("=" * 74)
    print(
        "CulebrIA - MOTOR ESTADÍSTICO HISTÓRICO"
    )
    print("=" * 74)

    # --------------------------------------------------------
    # VALIDACIÓN ENTRE FUENTES
    # --------------------------------------------------------

    validation_df = pd.read_csv(
        VALIDATION_FILE
    )

    verified_df = validation_df[
        validation_df[
            "validation"
        ] == "VERIFICADO"
    ].copy()

    # --------------------------------------------------------
    # AUDITORÍA DE SUFICIENCIA
    # --------------------------------------------------------

    audit_df = pd.read_csv(
        AUDIT_FILE
    )

    ready_ids = set(
        audit_df[
            audit_df[
                "model_status"
            ] == "LISTO"
        ][
            "fixture_id"
        ].astype(int)
    )

    verified_df[
        "fixture_id"
    ] = verified_df[
        "fixture_id"
    ].astype(int)

    ready_df = verified_df[
        verified_df[
            "fixture_id"
        ].isin(
            ready_ids
        )
    ].copy()

    rejected_df = verified_df[
        ~verified_df[
            "fixture_id"
        ].isin(
            ready_ids
        )
    ].copy()

    print()
    print(
        f"Partidos verificados: "
        f"{len(verified_df)}"
    )

    print(
        f"LISTOS para estadísticas: "
        f"{len(ready_df)}"
    )

    print(
        f"Excluidos por muestra: "
        f"{len(rejected_df)}"
    )

    # --------------------------------------------------------
    # MOSTRAR EXCLUIDOS
    # --------------------------------------------------------

    if not rejected_df.empty:

        print()
        print("=" * 74)
        print(
            "EXCLUIDOS POR MUESTRA INSUFICIENTE"
        )
        print("=" * 74)

        for _, match in rejected_df.iterrows():

            print()

            print(
                f"⚠️ "
                f"{match['fdorg_home']} "
                f"vs "
                f"{match['fdorg_away']}"
            )

            print(
                "   No se utilizará "
                "en el modelo actual."
            )

    # --------------------------------------------------------
    # CARGAR HISTÓRICOS UNA SOLA VEZ
    # --------------------------------------------------------

    histories = {}

    codes = (
        ready_df[
            "fdorg_code"
        ]
        .astype(str)
        .str.upper()
        .unique()
    )

    print()
    print("=" * 74)
    print(
        "HISTÓRICOS UTILIZADOS"
    )
    print("=" * 74)

    for code in codes:

        history = (
            load_competition_history(
                code
            )
        )

        histories[
            code
        ] = history[
            "matches"
        ]

        print()
        print(
            f"{code}"
        )

        print(
            f"Archivos: "
            f"{history['file_count']}"
        )

        for filename in history[
            "files"
        ]:

            print(
                f"  - {filename}"
            )

        print(
            f"Partidos combinados: "
            f"{history['match_count']}"
        )

    # --------------------------------------------------------
    # GENERAR ESTADÍSTICAS
    # --------------------------------------------------------

    output_rows = []

    for _, match in ready_df.iterrows():

        code = str(
            match[
                "fdorg_code"
            ]
        ).strip().upper()

        home = str(
            match[
                "fdorg_home"
            ]
        )

        away = str(
            match[
                "fdorg_away"
            ]
        )

        kickoff = parse_datetime(
            match[
                "fdorg_date"
            ]
        )

        if kickoff is None:

            print()
            print(
                f"❌ Fecha inválida: "
                f"{home} vs {away}"
            )

            continue

        competition_matches = (
            histories[
                code
            ]
        )

        # ====================================================
        # EQUIPO LOCAL
        # ====================================================

        home_profile = (
            calculate_team_profile(
                matches=
                    competition_matches,

                team_name=
                    home,

                before_date=
                    kickoff,

                venue=
                    "HOME"
            )
        )

        # ====================================================
        # EQUIPO VISITANTE
        # ====================================================

        away_profile = (
            calculate_team_profile(
                matches=
                    competition_matches,

                team_name=
                    away,

                before_date=
                    kickoff,

                venue=
                    "AWAY"
            )
        )

        # ====================================================
        # REGISTRO
        # ====================================================

        row = {
            "fixture_id":
                match[
                    "fixture_id"
                ],

            "competition":
                match[
                    "competition"
                ],

            "fdorg_code":
                code,

            "kickoff":
                match[
                    "fdorg_date"
                ],

            "home":
                home,

            "away":
                away,
        }

        # ----------------------------------------------------
        # LOCAL GENERAL
        # ----------------------------------------------------

        add_stats(
            row,
            "home_last5",
            home_profile[
                "last_5"
            ]
        )

        add_stats(
            row,
            "home_last10",
            home_profile[
                "last_10"
            ]
        )

        # ----------------------------------------------------
        # LOCAL EN CASA
        # ----------------------------------------------------

        add_stats(
            row,
            "home_home5",
            home_profile[
                "venue_last_5"
            ]
        )

        add_stats(
            row,
            "home_home10",
            home_profile[
                "venue_last_10"
            ]
        )

        # ----------------------------------------------------
        # VISITANTE GENERAL
        # ----------------------------------------------------

        add_stats(
            row,
            "away_last5",
            away_profile[
                "last_5"
            ]
        )

        add_stats(
            row,
            "away_last10",
            away_profile[
                "last_10"
            ]
        )

        # ----------------------------------------------------
        # VISITANTE FUERA
        # ----------------------------------------------------

        add_stats(
            row,
            "away_away5",
            away_profile[
                "venue_last_5"
            ]
        )

        add_stats(
            row,
            "away_away10",
            away_profile[
                "venue_last_10"
            ]
        )

        output_rows.append(
            row
        )

        # ====================================================
        # RESUMEN EN TERMINAL
        # ====================================================

        home5 = home_profile[
            "last_5"
        ]

        home10 = home_profile[
            "last_10"
        ]

        homevenue = home_profile[
            "venue_last_5"
        ]

        away5 = away_profile[
            "last_5"
        ]

        away10 = away_profile[
            "last_10"
        ]

        awayvenue = away_profile[
            "venue_last_5"
        ]

        print()
        print("-" * 74)

        print(
            f"{home} vs {away}"
        )

        print(
            f"Competición: {code}"
        )

        print()

        print("LOCAL")

        print(
            f"Últimos 5: "
            f"{home5['matches']}"
        )

        print(
            f"Últimos 10: "
            f"{home10['matches']}"
        )

        print(
            f"GF últimos 5: "
            f"{home5['avg_goals_for']:.2f}"
        )

        print(
            f"GC últimos 5: "
            f"{home5['avg_goals_against']:.2f}"
        )

        print(
            f"Marca ≥1: "
            f"{pct(home5['scored_rate'])}%"
        )

        print(
            f"Over 1.5: "
            f"{pct(home5['over_15_rate'])}%"
        )

        print(
            f"BTTS: "
            f"{pct(home5['btts_rate'])}%"
        )

        print(
            f"Últimos como LOCAL: "
            f"{homevenue['matches']}"
        )

        print()

        print("VISITANTE")

        print(
            f"Últimos 5: "
            f"{away5['matches']}"
        )

        print(
            f"Últimos 10: "
            f"{away10['matches']}"
        )

        print(
            f"GF últimos 5: "
            f"{away5['avg_goals_for']:.2f}"
        )

        print(
            f"GC últimos 5: "
            f"{away5['avg_goals_against']:.2f}"
        )

        print(
            f"Marca ≥1: "
            f"{pct(away5['scored_rate'])}%"
        )

        print(
            f"Over 1.5: "
            f"{pct(away5['over_15_rate'])}%"
        )

        print(
            f"BTTS: "
            f"{pct(away5['btts_rate'])}%"
        )

        print(
            f"Últimos como VISITANTE: "
            f"{awayvenue['matches']}"
        )

    # ========================================================
    # GUARDAR CSV
    # ========================================================

    output_df = pd.DataFrame(
        output_rows
    )

    output_df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # RESULTADO FINAL
    # ========================================================

    print()
    print("=" * 74)
    print(
        "MOTOR ESTADÍSTICO FINALIZADO"
    )
    print("=" * 74)

    print()

    print(
        f"Partidos procesados: "
        f"{len(output_rows)}"
    )

    print(
        f"Partidos excluidos: "
        f"{len(rejected_df)}"
    )

    print()

    print(
        "Solicitudes API realizadas: 0"
    )

    print()

    print(
        "Informe:"
    )

    print(
        OUTPUT_FILE
    )


if __name__ == "__main__":
    main()