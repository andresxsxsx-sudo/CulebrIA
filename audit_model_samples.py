from pathlib import Path

import pandas as pd

from src.analysis.team_stats import (
    collect_team_matches,
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

OUTPUT_FILE = (
    DATA_DIR
    / "model_sample_audit.csv"
)


# ============================================================
# FORMATO DE FECHA
# ============================================================

def format_date(value):

    if value is None:
        return "?"

    return value.strftime(
        "%Y-%m-%d"
    )


# ============================================================
# AUDITAR UN EQUIPO
# ============================================================

def audit_team(
    matches,
    team_name,
    kickoff,
    venue
):

    overall = collect_team_matches(
        matches=matches,
        team_name=team_name,
        before_date=kickoff
    )

    venue_matches = collect_team_matches(
        matches=matches,
        team_name=team_name,
        before_date=kickoff,
        venue=venue
    )

    last5 = overall[:5]
    last10 = overall[:10]

    venue5 = venue_matches[:5]
    venue10 = venue_matches[:10]

    # --------------------------------------------------------
    # COMPROBAR DATA LEAKAGE
    # --------------------------------------------------------

    future_leak = any(
        item["date"] >= kickoff
        for item in overall
    )

    if last5:

        newest_date = (
            last5[0]["date"]
        )

        oldest_date = (
            last5[-1]["date"]
        )

    else:

        newest_date = None
        oldest_date = None

    return {
        "overall_total":
            len(overall),

        "last5":
            len(last5),

        "last10":
            len(last10),

        "venue_total":
            len(venue_matches),

        "venue5":
            len(venue5),

        "venue10":
            len(venue10),

        "newest_date":
            newest_date,

        "oldest_date":
            oldest_date,

        "future_leak":
            future_leak,
    }


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    print("=" * 74)
    print(
        "CulebrIA - AUDITORÍA HISTÓRICA"
    )
    print("=" * 74)

    validation_df = pd.read_csv(
        VALIDATION_FILE
    )

    verified_df = validation_df[
        validation_df[
            "validation"
        ] == "VERIFICADO"
    ].copy()

    print()
    print(
        f"Partidos verificados: "
        f"{len(verified_df)}"
    )

    # --------------------------------------------------------
    # CARGAR UNA VEZ CADA COMPETICIÓN
    # --------------------------------------------------------

    competitions = {}

    codes = (
        verified_df[
            "fdorg_code"
        ]
        .astype(str)
        .str.upper()
        .unique()
    )

    print()
    print("=" * 74)
    print("HISTÓRICOS LOCALES")
    print("=" * 74)

    for code in codes:

        history = (
            load_competition_history(
                code
            )
        )

        competitions[
            code
        ] = history["matches"]

        print()
        print(
            f"{code}"
        )

        print(
            f"Archivos utilizados: "
            f"{history['file_count']}"
        )

        for filename in (
            history["files"]
        ):

            print(
                f"  - {filename}"
            )

        print(
            f"Partidos combinados: "
            f"{history['match_count']}"
        )

    matches_ready = 0
    matches_warning = 0
    leakage_errors = 0

    rows = []

    # ========================================================
    # AUDITAR PARTIDOS
    # ========================================================

    for _, match in verified_df.iterrows():

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

            matches_warning += 1
            continue

        competition_matches = (
            competitions[
                code
            ]
        )

        # ----------------------------------------------------
        # LOCAL
        # ----------------------------------------------------

        home_audit = audit_team(
            matches=
                competition_matches,

            team_name=
                home,

            kickoff=
                kickoff,

            venue=
                "HOME"
        )

        # ----------------------------------------------------
        # VISITANTE
        # ----------------------------------------------------

        away_audit = audit_team(
            matches=
                competition_matches,

            team_name=
                away,

            kickoff=
                kickoff,

            venue=
                "AWAY"
        )

        # ----------------------------------------------------
        # LEAKAGE
        # ----------------------------------------------------

        has_leakage = (
            home_audit[
                "future_leak"
            ]
            or
            away_audit[
                "future_leak"
            ]
        )

        if has_leakage:
            leakage_errors += 1

        # ----------------------------------------------------
        # MUESTRA GENERAL
        # ----------------------------------------------------

        basic_sample_ok = (
            home_audit[
                "last5"
            ] >= 5

            and

            away_audit[
                "last5"
            ] >= 5
        )

        # ----------------------------------------------------
        # MUESTRA LOCAL / VISITANTE
        # ----------------------------------------------------

        venue_sample_ok = (
            home_audit[
                "venue5"
            ] >= 3

            and

            away_audit[
                "venue5"
            ] >= 3
        )

        # ----------------------------------------------------
        # ESTADO
        # ----------------------------------------------------

        if (
            basic_sample_ok
            and
            venue_sample_ok
            and
            not has_leakage
        ):

            model_status = (
                "LISTO"
            )

            matches_ready += 1

        else:

            model_status = (
                "MUESTRA_INSUFICIENTE"
            )

            matches_warning += 1

        # ----------------------------------------------------
        # TERMINAL
        # ----------------------------------------------------

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
            f"Equipo: {home}"
        )

        print(
            f"Histórico disponible: "
            f"{home_audit['overall_total']}"
        )

        print(
            f"Últimos 5: "
            f"{home_audit['last5']}/5"
        )

        print(
            f"Últimos 10: "
            f"{home_audit['last10']}/10"
        )

        print(
            f"Como LOCAL: "
            f"{home_audit['venue_total']}"
        )

        print(
            f"Últimos 5 como LOCAL: "
            f"{home_audit['venue5']}/5"
        )

        print(
            f"Rango últimos 5: "
            f"{format_date(home_audit['oldest_date'])}"
            f" → "
            f"{format_date(home_audit['newest_date'])}"
        )

        print()

        print("VISITANTE")

        print(
            f"Equipo: {away}"
        )

        print(
            f"Histórico disponible: "
            f"{away_audit['overall_total']}"
        )

        print(
            f"Últimos 5: "
            f"{away_audit['last5']}/5"
        )

        print(
            f"Últimos 10: "
            f"{away_audit['last10']}/10"
        )

        print(
            f"Como VISITANTE: "
            f"{away_audit['venue_total']}"
        )

        print(
            f"Últimos 5 como VISITANTE: "
            f"{away_audit['venue5']}/5"
        )

        print(
            f"Rango últimos 5: "
            f"{format_date(away_audit['oldest_date'])}"
            f" → "
            f"{format_date(away_audit['newest_date'])}"
        )

        print()

        print(
            "Muestra general: "
            f"{'✅' if basic_sample_ok else '⚠️'}"
        )

        print(
            "Muestra local/visitante ≥3: "
            f"{'✅' if venue_sample_ok else '⚠️'}"
        )

        print(
            "Data leakage: "
            f"{'❌ DETECTADO' if has_leakage else '✅ NO'}"
        )

        print(
            f"Estado para modelo: "
            f"{model_status}"
        )

        # ----------------------------------------------------
        # CSV
        # ----------------------------------------------------

        rows.append(
            {
                "fixture_id":
                    match[
                        "fixture_id"
                    ],

                "competition":
                    code,

                "home":
                    home,

                "away":
                    away,

                "home_history":
                    home_audit[
                        "overall_total"
                    ],

                "home_last5":
                    home_audit[
                        "last5"
                    ],

                "home_last10":
                    home_audit[
                        "last10"
                    ],

                "home_venue":
                    home_audit[
                        "venue_total"
                    ],

                "away_history":
                    away_audit[
                        "overall_total"
                    ],

                "away_last5":
                    away_audit[
                        "last5"
                    ],

                "away_last10":
                    away_audit[
                        "last10"
                    ],

                "away_venue":
                    away_audit[
                        "venue_total"
                    ],

                "basic_sample_ok":
                    basic_sample_ok,

                "venue_sample_ok":
                    venue_sample_ok,

                "data_leakage":
                    has_leakage,

                "model_status":
                    model_status,
            }
        )

    # ========================================================
    # GUARDAR
    # ========================================================

    pd.DataFrame(
        rows
    ).to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # RESUMEN
    # ========================================================

    print()
    print("=" * 74)
    print("RESULTADO FINAL")
    print("=" * 74)

    print()

    print(
        f"Partidos auditados: "
        f"{len(rows)}"
    )

    print(
        f"LISTOS para modelo: "
        f"{matches_ready}"
    )

    print(
        f"Con advertencias: "
        f"{matches_warning}"
    )

    print(
        f"Data leakage detectado: "
        f"{leakage_errors}"
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