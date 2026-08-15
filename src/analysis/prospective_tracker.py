import csv
import hashlib
from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# CONFIGURACIÓN
# ============================================================

ROOT_DIR = (
    Path(__file__)
    .resolve()
    .parents[2]
)

DATA_DIR = (
    ROOT_DIR
    / "data"
)

PROSPECTIVE_DIR = (
    DATA_DIR
    / "prospective"
)

PROSPECTIVE_DIR.mkdir(
    parents=True,
    exist_ok=True
)

LEDGER_FILE = (
    PROSPECTIVE_DIR
    / "prospective_ledger.csv"
)


# ============================================================
# COLUMNAS DEL LEDGER
# ============================================================

FIELDNAMES = [
    "record_id",

    # --------------------------------------------------------
    # IDENTIFICACIÓN
    # --------------------------------------------------------

    "created_at_utc",
    "fixture_id",
    "event_id",
    "competition",
    "kickoff_utc",
    "home",
    "away",

    # --------------------------------------------------------
    # MODELO
    # --------------------------------------------------------

    "model_version",
    "market",
    "model_probability_pct",
    "model_fair_odds",

    # --------------------------------------------------------
    # RELIABILITY GATE
    # --------------------------------------------------------

    "gate_grade",
    "development_bin_n",
    "development_bin_prediction_pct",
    "development_bin_actual_pct",
    "development_bin_gap_pct",

    # --------------------------------------------------------
    # MERCADO / CUOTA
    # --------------------------------------------------------

    "odds_snapshot_utc",
    "bookmaker",
    "decimal_odds",
    "break_even_pct",
    "raw_edge_pp",
    "raw_ev_pct",

    # --------------------------------------------------------
    # DECISIÓN
    # --------------------------------------------------------

    "decision",
    "decision_reason",

    # --------------------------------------------------------
    # RESULTADO
    # Se completa DESPUÉS del partido.
    # --------------------------------------------------------

    "settled",
    "home_goals",
    "away_goals",
    "market_result",
    "profit_units",

    # --------------------------------------------------------
    # AUDITORÍA
    # --------------------------------------------------------

    "settled_at_utc",
]


# ============================================================
# UTILIDADES
# ============================================================

def utc_now_iso():

    return (
        datetime.now(
            timezone.utc
        )
        .replace(
            microsecond=0
        )
        .isoformat()
    )


def safe_string(value):

    if value is None:
        return ""

    return str(
        value
    ).strip()


def safe_float(value):

    if (
        value is None
        or
        safe_string(value)
        == ""
    ):
        return None

    return float(
        value
    )


# ============================================================
# ID ÚNICO
# ============================================================

def build_record_id(
    event_id,
    fixture_id,
    market,
    odds_snapshot_utc
):

    raw = (
        f"{safe_string(event_id)}|"
        f"{safe_string(fixture_id)}|"
        f"{safe_string(market).upper()}|"
        f"{safe_string(odds_snapshot_utc)}"
    )

    digest = hashlib.sha256(
        raw.encode(
            "utf-8"
        )
    ).hexdigest()

    return digest[:20]


# ============================================================
# CREAR LEDGER
# ============================================================

def ensure_ledger():

    if LEDGER_FILE.exists():
        return

    with open(
        LEDGER_FILE,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=FIELDNAMES
        )

        writer.writeheader()


# ============================================================
# LEER IDS EXISTENTES
# ============================================================

def existing_record_ids():

    ensure_ledger()

    ids = set()

    with open(
        LEDGER_FILE,
        "r",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        reader = csv.DictReader(
            file
        )

        for row in reader:

            record_id = safe_string(
                row.get(
                    "record_id"
                )
            )

            if record_id:
                ids.add(
                    record_id
                )

    return ids


# ============================================================
# GUARDAR SNAPSHOT
# ============================================================

def append_snapshot(
    *,
    fixture_id,
    event_id,
    competition,
    kickoff_utc,
    home,
    away,
    market,
    model_probability_pct,
    gate_grade,
    development_bin_n,
    development_bin_prediction_pct,
    development_bin_actual_pct,
    development_bin_gap_pct,
    odds_snapshot_utc,
    bookmaker,
    decimal_odds,
    decision,
    decision_reason,
    model_version="POISSON_V1_RAW_GATE_V1"
):

    ensure_ledger()

    model_probability = (
        float(
            model_probability_pct
        )
        / 100
    )

    decimal_odds = float(
        decimal_odds
    )

    model_fair_odds = (
        1
        / model_probability
    )

    break_even = (
        1
        / decimal_odds
    )

    raw_edge = (
        model_probability
        - break_even
    )

    raw_ev = (
        model_probability
        * decimal_odds
        - 1
    )

    record_id = build_record_id(
        event_id=
            event_id,

        fixture_id=
            fixture_id,

        market=
            market,

        odds_snapshot_utc=
            odds_snapshot_utc
    )

    current_ids = (
        existing_record_ids()
    )

    if record_id in current_ids:

        return {
            "created":
                False,

            "record_id":
                record_id,

            "reason":
                "DUPLICATE_RECORD",
        }

    row = {
        "record_id":
            record_id,

        "created_at_utc":
            utc_now_iso(),

        "fixture_id":
            safe_string(
                fixture_id
            ),

        "event_id":
            safe_string(
                event_id
            ),

        "competition":
            safe_string(
                competition
            ),

        "kickoff_utc":
            safe_string(
                kickoff_utc
            ),

        "home":
            safe_string(
                home
            ),

        "away":
            safe_string(
                away
            ),

        "model_version":
            safe_string(
                model_version
            ),

        "market":
            safe_string(
                market
            ).upper(),

        "model_probability_pct":
            round(
                float(
                    model_probability_pct
                ),
                4
            ),

        "model_fair_odds":
            round(
                model_fair_odds,
                4
            ),

        "gate_grade":
            safe_string(
                gate_grade
            ),

        "development_bin_n":
            safe_string(
                development_bin_n
            ),

        "development_bin_prediction_pct":
            safe_string(
                development_bin_prediction_pct
            ),

        "development_bin_actual_pct":
            safe_string(
                development_bin_actual_pct
            ),

        "development_bin_gap_pct":
            safe_string(
                development_bin_gap_pct
            ),

        "odds_snapshot_utc":
            safe_string(
                odds_snapshot_utc
            ),

        "bookmaker":
            safe_string(
                bookmaker
            ),

        "decimal_odds":
            round(
                decimal_odds,
                4
            ),

        "break_even_pct":
            round(
                break_even
                * 100,
                4
            ),

        "raw_edge_pp":
            round(
                raw_edge
                * 100,
                4
            ),

        "raw_ev_pct":
            round(
                raw_ev
                * 100,
                4
            ),

        "decision":
            safe_string(
                decision
            ),

        "decision_reason":
            safe_string(
                decision_reason
            ),

        "settled":
            "NO",

        "home_goals":
            "",

        "away_goals":
            "",

        "market_result":
            "",

        "profit_units":
            "",

        "settled_at_utc":
            "",
    }

    with open(
        LEDGER_FILE,
        "a",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=FIELDNAMES
        )

        writer.writerow(
            row
        )

    return {
        "created":
            True,

        "record_id":
            record_id,

        "reason":
            "OK",

        "model_fair_odds":
            model_fair_odds,

        "break_even_pct":
            break_even
            * 100,

        "raw_edge_pp":
            raw_edge
            * 100,

        "raw_ev_pct":
            raw_ev
            * 100,
    }