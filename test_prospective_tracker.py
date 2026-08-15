from datetime import datetime, timezone

from src.analysis.prospective_tracker import (
    LEDGER_FILE,
    append_snapshot,
)


def main():

    print("=" * 80)
    print(
        "CulebrIA - TEST PROSPECTIVE TRACKER"
    )
    print("=" * 80)

    # ========================================================
    # REGISTRO FICTICIO
    #
    # No representa una apuesta.
    # Solo verifica que el ledger funciona.
    # ========================================================

    snapshot_time = (
        datetime.now(
            timezone.utc
        )
        .replace(
            microsecond=0
        )
        .isoformat()
    )

    result = append_snapshot(
        fixture_id=
            "TEST_001",

        event_id=
            "TEST_EVENT_001",

        competition=
            "TEST",

        kickoff_utc=
            "2099-01-01T20:00:00+00:00",

        home=
            "Equipo Local Test",

        away=
            "Equipo Visitante Test",

        market=
            "AWAY_SCORES",

        model_probability_pct=
            78.50,

        gate_grade=
            "A",

        development_bin_n=
            93,

        development_bin_prediction_pct=
            74.78,

        development_bin_actual_pct=
            75.27,

        development_bin_gap_pct=
            0.49,

        odds_snapshot_utc=
            snapshot_time,

        bookmaker=
            "TEST_BOOKMAKER",

        decimal_odds=
            1.40,

        decision=
            "TEST_ONLY",

        decision_reason=
            (
                "Registro ficticio para "
                "comprobar el ledger."
            ),
    )

    print()

    print(
        f"Creado: "
        f"{result['created']}"
    )

    print(
        f"Record ID: "
        f"{result['record_id']}"
    )

    if result[
        "created"
    ]:

        print()

        print(
            f"Cuota justa: "
            f"{result['model_fair_odds']:.3f}"
        )

        print(
            f"Break-even: "
            f"{result['break_even_pct']:.2f}%"
        )

        print(
            f"Edge: "
            f"{result['raw_edge_pp']:+.2f} pp"
        )

        print(
            f"EV: "
            f"{result['raw_ev_pct']:+.2f}%"
        )

    print()

    print(
        "Ledger:"
    )

    print(
        LEDGER_FILE
    )

    print()

    print(
        "Solicitudes API: 0"
    )

    print(
        "Créditos utilizados: 0"
    )


if __name__ == "__main__":
    main()