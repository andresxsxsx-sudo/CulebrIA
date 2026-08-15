from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.analysis.prospective_tracker import (
    LEDGER_FILE,
    append_snapshot,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"

VALUE_FILE = (
    DATA_DIR
    / "value_candidates.csv"
)

GATE_FILE = (
    DATA_DIR
    / "reliability_gate_signals.csv"
)


# ============================================================
# POLÍTICA CONGELADA
# ============================================================

ALLOWED_MARKETS = {
    "1X",
    "AWAY_SCORES",
}

FINAL_OR_TRACKABLE_STATUSES = {
    "NO_BET_PRICE",
    "NEEDS_VIG_CHECK",
}


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

    print("=" * 86)
    print(
        "CulebrIA - PROSPECTIVE SNAPSHOT BUILDER"
    )
    print("=" * 86)

    print()
    print(
        "Modelo congelado:"
    )

    print(
        "POISSON_V1_RAW_GATE_V1"
    )

    print()

    # --------------------------------------------------------
    # COMPROBAR ARCHIVOS
    # --------------------------------------------------------

    if not VALUE_FILE.exists():

        print(
            "❌ No existe:"
        )

        print(
            VALUE_FILE
        )

        return

    if not GATE_FILE.exists():

        print(
            "❌ No existe:"
        )

        print(
            GATE_FILE
        )

        return

    # --------------------------------------------------------
    # CARGAR
    # --------------------------------------------------------

    value_df = pd.read_csv(
        VALUE_FILE
    )

    gate_df = pd.read_csv(
        GATE_FILE
    )

    print(
        f"Filas Value Engine: "
        f"{len(value_df)}"
    )

    print(
        f"Filas Reliability Gate: "
        f"{len(gate_df)}"
    )

    # ========================================================
    # PREPARAR GATE
    # ========================================================

    gate_columns = [
        "fixture_id",
        "market",
        "grade",
        "bin_n",
        "bin_prediction_pct",
        "bin_actual_pct",
        "bin_gap_pct",
    ]

    gate_data = gate_df[
        gate_columns
    ].copy()

    gate_data[
        "market"
    ] = (
        gate_data[
            "market"
        ]
        .astype(str)
        .str.upper()
    )

    value_df[
        "market"
    ] = (
        value_df[
            "market"
        ]
        .astype(str)
        .str.upper()
    )

    # --------------------------------------------------------
    # MERGE
    # --------------------------------------------------------

    df = value_df.merge(
        gate_data,
        on=[
            "fixture_id",
            "market",
        ],
        how="left"
    )

    now = datetime.now(
        timezone.utc
    )

    created = 0
    skipped = 0
    duplicates = 0

    print()
    print("=" * 86)
    print(
        "EVALUACIÓN"
    )
    print("=" * 86)

    # ========================================================
    # PROCESAR
    # ========================================================

    for _, row in df.iterrows():

        home = str(
            row[
                "home"
            ]
        )

        away = str(
            row[
                "away"
            ]
        )

        market = str(
            row[
                "market"
            ]
        ).upper()

        status = str(
            row[
                "status"
            ]
        )

        print()
        print("-" * 86)

        print(
            f"{home} vs {away}"
        )

        print(
            f"Mercado: "
            f"{market}"
        )

        print(
            f"Estado Value Engine: "
            f"{status}"
        )

        # ====================================================
        # MERCADO PERMITIDO
        # ====================================================

        if market not in ALLOWED_MARKETS:

            print(
                "⛔ Mercado bloqueado "
                "por política prospectiva."
            )

            skipped += 1
            continue

        # ====================================================
        # ESTADO CON CUOTA EVALUABLE
        # ====================================================

        if (
            status
            not in FINAL_OR_TRACKABLE_STATUSES
        ):

            print(
                "⛔ No existe todavía una "
                "evaluación de precio registrable."
            )

            skipped += 1
            continue

        # ====================================================
        # CAMPOS DE CUOTA
        # ====================================================

        if (
            pd.isna(
                row[
                    "best_odds"
                ]
            )
            or
            pd.isna(
                row[
                    "best_bookmaker"
                ]
            )
        ):

            print(
                "⛔ Falta cuota o bookmaker."
            )

            skipped += 1
            continue

        # ====================================================
        # KICKOFF
        # ====================================================

        kickoff = parse_datetime(
            row[
                "commence_time"
            ]
        )

        if kickoff is None:

            print(
                "⛔ Kickoff inválido."
            )

            skipped += 1
            continue

        if kickoff <= now:

            print(
                "⛔ Evento ya iniciado."
            )

            skipped += 1
            continue

        # ====================================================
        # HORA DE LA CUOTA
        # ====================================================

        odds_snapshot = parse_datetime(
            row[
                "odds_last_update"
            ]
        )

        if odds_snapshot is None:

            print(
                "⛔ No existe timestamp válido "
                "de la cuota."
            )

            skipped += 1
            continue

        if odds_snapshot >= kickoff:

            print(
                "⛔ La cuota no es PREMATCH."
            )

            skipped += 1
            continue

        # ====================================================
        # INFORMACIÓN DEL GATE
        # ====================================================

        if pd.isna(
            row[
                "grade"
            ]
        ):

            print(
                "⛔ No se encontró la información "
                "del Reliability Gate."
            )

            skipped += 1
            continue

        # ====================================================
        # DECISIÓN
        # ====================================================

        if status == "NO_BET_PRICE":

            decision = (
                "NO_BET_PRICE"
            )

            decision_reason = (
                "La mejor cuota disponible "
                "no supera la cuota justa "
                "del modelo."
            )

        elif status == "NEEDS_VIG_CHECK":

            decision = (
                "NEEDS_VIG_CHECK"
            )

            decision_reason = (
                "EV bruto positivo. "
                "Pendiente de validación "
                "contra mercado sin vig."
            )

        else:

            print(
                "⛔ Estado no reconocido."
            )

            skipped += 1
            continue

        # ====================================================
        # REGISTRAR
        # ====================================================

        result = append_snapshot(
            fixture_id=
                row[
                    "fixture_id"
                ],

            event_id=
                row[
                    "event_id"
                ],

            competition=
                row[
                    "competition"
                ],

            kickoff_utc=
                kickoff.isoformat(),

            home=
                home,

            away=
                away,

            market=
                market,

            model_probability_pct=
                row[
                    "model_probability_pct"
                ],

            gate_grade=
                row[
                    "grade"
                ],

            development_bin_n=
                row[
                    "bin_n"
                ],

            development_bin_prediction_pct=
                row[
                    "bin_prediction_pct"
                ],

            development_bin_actual_pct=
                row[
                    "bin_actual_pct"
                ],

            development_bin_gap_pct=
                row[
                    "bin_gap_pct"
                ],

            odds_snapshot_utc=
                odds_snapshot.isoformat(),

            bookmaker=
                row[
                    "best_bookmaker"
                ],

            decimal_odds=
                row[
                    "best_odds"
                ],

            decision=
                decision,

            decision_reason=
                decision_reason,

            model_version=
                "POISSON_V1_RAW_GATE_V1"
        )

        if result[
            "created"
        ]:

            created += 1

            print(
                "✅ Snapshot prospectivo guardado."
            )

            print(
                f"Record ID: "
                f"{result['record_id']}"
            )

            print(
                f"Probabilidad: "
                f"{float(row['model_probability_pct']):.2f}%"
            )

            print(
                f"Cuota: "
                f"{float(row['best_odds']):.3f}"
            )

            print(
                f"EV bruto: "
                f"{result['raw_ev_pct']:+.2f}%"
            )

            print(
                f"Decisión: "
                f"{decision}"
            )

        else:

            duplicates += 1

            print(
                "⚠️ Registro duplicado. "
                "No se volvió a guardar."
            )

    # ========================================================
    # RESUMEN
    # ========================================================

    print()
    print("=" * 86)
    print(
        "RESULTADO FINAL"
    )
    print("=" * 86)

    print()

    print(
        f"Snapshots creados: "
        f"{created}"
    )

    print(
        f"Duplicados ignorados: "
        f"{duplicates}"
    )

    print(
        f"Filas descartadas: "
        f"{skipped}"
    )

    print()

    print(
        "Solicitudes API realizadas: 0"
    )

    print(
        "Créditos utilizados: 0"
    )

    print()

    print(
        "Ledger:"
    )

    print(
        LEDGER_FILE
    )


if __name__ == "__main__":
    main()