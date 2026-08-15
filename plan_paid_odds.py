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
    / "prematch_odds_candidates.csv"
)

OUTPUT_FILE = (
    DATA_DIR
    / "paid_odds_plan.csv"
)


# ============================================================
# POLÍTICA PROSPECTIVA CONGELADA
# ============================================================

ALLOWED_MARKETS = {
    "1X",
    "AWAY_SCORES",
}


MARKET_MAP = {
    "1X":
        "double_chance",

    "AWAY_SCORES":
        "team_totals",
}


# Protección operativa.
# No queremos pedir una cuota cuando el evento
# está a segundos de comenzar.
MIN_MINUTES_TO_KICKOFF = 10


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
# MAIN
# ============================================================

def main():

    print("=" * 88)
    print(
        "CulebrIA - PAID ODDS PLANNER"
    )
    print("=" * 88)

    print()
    print(
        "Este script NO consulta "
        "The Odds API."
    )

    print(
        "Solo decide qué consultas "
        "estarían autorizadas."
    )

    # --------------------------------------------------------
    # ARCHIVO
    # --------------------------------------------------------

    if not INPUT_FILE.exists():

        print()
        print(
            "❌ No existe:"
        )

        print(
            INPUT_FILE
        )

        return

    df = pd.read_csv(
        INPUT_FILE
    )

    print()
    print(
        f"Señales recibidas: "
        f"{len(df)}"
    )

    now = datetime.now(
        timezone.utc
    )

    rows = []

    # ========================================================
    # REEVALUAR TODAS LAS SEÑALES
    # ========================================================

    for _, row in df.iterrows():

        market = str(
            row[
                "signal_market"
            ]
        ).strip().upper()

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

        event_id = str(
            row[
                "event_id"
            ]
        ).strip()

        sport_key = str(
            row[
                "sport_key"
            ]
        ).strip()

        commence_time = parse_datetime(
            row[
                "commence_time"
            ]
        )

        reasons = []

        # ----------------------------------------------------
        # MERCADO
        # ----------------------------------------------------

        if market not in ALLOWED_MARKETS:

            reasons.append(
                "MARKET_BLOCKED"
            )

        api_market = MARKET_MAP.get(
            market
        )

        if api_market is None:

            reasons.append(
                "NO_API_MARKET"
            )

        # ----------------------------------------------------
        # EVENTO
        # ----------------------------------------------------

        if (
            event_id == ""
            or
            event_id.lower()
            == "nan"
        ):

            reasons.append(
                "NO_EVENT_ID"
            )

        if (
            sport_key == ""
            or
            sport_key.lower()
            == "nan"
        ):

            reasons.append(
                "NO_SPORT_KEY"
            )

        # ----------------------------------------------------
        # HORA
        # ----------------------------------------------------

        if commence_time is None:

            minutes_to_start = None

            reasons.append(
                "INVALID_KICKOFF"
            )

        else:

            minutes_to_start = (
                commence_time
                - now
            ).total_seconds() / 60

            if minutes_to_start <= 0:

                reasons.append(
                    "STARTED"
                )

            elif (
                minutes_to_start
                <
                MIN_MINUTES_TO_KICKOFF
            ):

                reasons.append(
                    "TOO_CLOSE_TO_KICKOFF"
                )

        # ----------------------------------------------------
        # DECISIÓN
        # ----------------------------------------------------

        authorized = (
            len(reasons) == 0
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
                    sport_key,

                "event_id":
                    event_id,

                "home":
                    home,

                "away":
                    away,

                "market":
                    market,

                "api_market":
                    api_market,

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
                        "commence_time"
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

                "authorized":
                    authorized,

                "block_reasons":
                    " | ".join(
                        reasons
                    ),
            }
        )

    result_df = pd.DataFrame(
        rows
    )

    result_df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # AUTORIZADAS
    # ========================================================

    authorized_df = result_df[
        result_df[
            "authorized"
        ] == True
    ].copy()

    # Una misma consulta puede servir para varias señales
    # si pertenecen al mismo evento y mismo mercado API.
    if authorized_df.empty:

        unique_requests = 0

    else:

        unique_requests = (
            authorized_df[
                [
                    "event_id",
                    "api_market"
                ]
            ]
            .drop_duplicates()
            .shape[0]
        )

    # ========================================================
    # TERMINAL
    # ========================================================

    print()
    print("=" * 88)
    print(
        "SEÑALES AUTORIZADAS"
    )
    print("=" * 88)

    if authorized_df.empty:

        print()
        print(
            "No existe ninguna consulta "
            "de cuotas autorizada."
        )

    else:

        for _, candidate in (
            authorized_df.iterrows()
        ):

            print()
            print(
                f"{candidate['home']} "
                f"vs "
                f"{candidate['away']}"
            )

            print(
                f"Mercado CulebrIA: "
                f"{candidate['market']}"
            )

            print(
                f"Mercado API: "
                f"{candidate['api_market']}"
            )

            print(
                f"Probabilidad: "
                f"{float(candidate['model_probability_pct']):.2f}%"
            )

            print(
                f"Grade: "
                f"{candidate['grade']}"
            )

            print(
                f"Minutos al inicio: "
                f"{candidate['minutes_to_start']:.1f}"
            )

            print(
                f"Event ID: "
                f"{candidate['event_id']}"
            )

            print(
                "-" * 60
            )

    # ========================================================
    # BLOQUEADAS
    # ========================================================

    blocked_df = result_df[
        result_df[
            "authorized"
        ] == False
    ]

    print()
    print("=" * 88)
    print(
        "RESUMEN"
    )
    print("=" * 88)

    print()

    print(
        f"Señales analizadas: "
        f"{len(result_df)}"
    )

    print(
        f"Señales autorizadas: "
        f"{len(authorized_df)}"
    )

    print(
        f"Señales bloqueadas: "
        f"{len(blocked_df)}"
    )

    print(
        f"Consultas únicas necesarias: "
        f"{unique_requests}"
    )

    # --------------------------------------------------------
    # MOTIVOS
    # --------------------------------------------------------

    if not blocked_df.empty:

        print()
        print(
            "Motivos de bloqueo:"
        )

        reason_counts = {}

        for value in blocked_df[
            "block_reasons"
        ].fillna(
            ""
        ):

            for reason in str(
                value
            ).split(
                " | "
            ):

                reason = (
                    reason.strip()
                )

                if not reason:
                    continue

                reason_counts[
                    reason
                ] = (
                    reason_counts.get(
                        reason,
                        0
                    )
                    + 1
                )

        for (
            reason,
            count
        ) in sorted(
            reason_counts.items()
        ):

            print(
                f"  {reason}: "
                f"{count}"
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
        "Plan guardado en:"
    )

    print(
        OUTPUT_FILE
    )

    print()
    print(
        "IMPORTANTE:"
    )

    print(
        "Consultas únicas necesarias "
        "NO significa créditos gastados."
    )

    print(
        "El gasto real solo se conocerá "
        "cuando The Odds API responda "
        "y leamos sus headers."
    )


if __name__ == "__main__":
    main()