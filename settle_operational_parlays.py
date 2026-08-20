from __future__ import annotations

import math
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

from src.api.fdorg_local_history import (
    load_competition_history,
)


ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"

LEDGER_FILE = (
    DATA_DIR
    / "prospective"
    / "operational_parlay_ledger.csv"
)


def normalize_name(value):
    text = str(value or "").strip().lower()

    text = unicodedata.normalize(
        "NFKD",
        text,
    )

    text = "".join(
        char
        for char in text
        if not unicodedata.combining(
            char
        )
    )

    replacements = {
        "athletico":
            "atletico",
        "ca paranaense":
            "atletico paranaense",
        "club athletico paranaense":
            "atletico paranaense",
        "club atletico paranaense":
            "atletico paranaense",
        "red bull bragantino":
            "rb bragantino",
        "sporting clube de braga":
            "braga",
        "sc braga":
            "braga",
        "sport lisboa e benfica":
            "benfica",
        "academico de viseu":
            "academico viseu",
    }

    for old, new in replacements.items():
        text = text.replace(
            old,
            new,
        )

    for symbol in (
        "-",
        ".",
        "'",
        ",",
        "/",
        "_",
    ):
        text = text.replace(
            symbol,
            " ",
        )

    removable = {
        "fc",
        "cf",
        "football",
        "futebol",
        "club",
        "clube",
    }

    tokens = [
        token
        for token in text.split()
        if token not in removable
    ]

    return " ".join(
        tokens
    )


def similarity(a, b):
    left = normalize_name(a)
    right = normalize_name(b)

    if not left or not right:
        return 0.0

    if left == right:
        return 1.0

    left_tokens = set(
        left.split()
    )
    right_tokens = set(
        right.split()
    )

    containment = 0.0

    if (
        left_tokens
        and right_tokens
        and (
            left_tokens.issubset(
                right_tokens
            )
            or right_tokens.issubset(
                left_tokens
            )
        )
    ):
        containment = 0.96

    union = (
        left_tokens
        | right_tokens
    )

    jaccard = (
        len(
            left_tokens
            & right_tokens
        )
        / len(union)
        if union
        else 0.0
    )

    sequence = SequenceMatcher(
        None,
        left,
        right,
    ).ratio()

    return max(
        containment,
        jaccard,
        sequence,
    )


def parse_datetime(value):
    if (
        value is None
        or str(value).strip() == ""
        or str(value).lower() == "nan"
    ):
        return None

    try:
        dt = datetime.fromisoformat(
            str(value).replace(
                "Z",
                "+00:00",
            )
        )
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=timezone.utc
        )

    return dt.astimezone(
        timezone.utc
    )


def score_from_match(match):
    score = match.get(
        "score",
        {}
    )

    full_time = score.get(
        "fullTime",
        {}
    )

    home = full_time.get(
        "home"
    )
    away = full_time.get(
        "away"
    )

    if home is None or away is None:
        return None

    try:
        return int(home), int(away)
    except (
        TypeError,
        ValueError,
    ):
        return None


def find_finished_match(
    competition,
    target_home,
    target_away,
    target_commence,
):
    try:
        history = (
            load_competition_history(
                competition
            )
        )
    except RuntimeError:
        return None

    matches = history.get(
        "matches",
        [],
    )

    target_dt = parse_datetime(
        target_commence
    )

    best = None
    best_score = 0.0

    for match in matches:
        if str(
            match.get(
                "status",
                ""
            )
        ).upper() != "FINISHED":
            continue

        actual_score = score_from_match(
            match
        )

        if actual_score is None:
            continue

        match_dt = parse_datetime(
            match.get(
                "utcDate"
            )
        )

        if (
            target_dt is not None
            and match_dt is not None
            and abs(
                (
                    match_dt.date()
                    - target_dt.date()
                ).days
            ) > 1
        ):
            continue

        fd_home = (
            match.get(
                "homeTeam",
                {}
            ).get(
                "name",
                "",
            )
        )

        fd_away = (
            match.get(
                "awayTeam",
                {}
            ).get(
                "name",
                "",
            )
        )

        straight = (
            similarity(
                target_home,
                fd_home,
            )
            + similarity(
                target_away,
                fd_away,
            )
        ) / 2

        swapped = (
            similarity(
                target_home,
                fd_away,
            )
            + similarity(
                target_away,
                fd_home,
            )
        ) / 2

        if straight >= swapped:
            candidate_score = straight
            orientation = "NORMAL"
        else:
            candidate_score = swapped
            orientation = "SWAPPED"

        if candidate_score > best_score:
            best_score = candidate_score
            best = {
                "orientation":
                    orientation,
                "score":
                    actual_score,
            }

    if (
        best is None
        or best_score < 0.84
    ):
        return None

    home_goals, away_goals = (
        best["score"]
    )

    if (
        best["orientation"]
        == "SWAPPED"
    ):
        home_goals, away_goals = (
            away_goals,
            home_goals,
        )

    return {
        "home_goals":
            home_goals,
        "away_goals":
            away_goals,
    }


def settle_market(
    market,
    home_goals,
    away_goals,
):
    market = str(
        market
    ).upper()

    if market == "1X":
        return (
            "WIN"
            if home_goals
            >= away_goals
            else "LOSS"
        )

    if market == "X2":
        return (
            "WIN"
            if away_goals
            >= home_goals
            else "LOSS"
        )

    if market == "AWAY_SCORES":
        return (
            "WIN"
            if away_goals
            >= 1
            else "LOSS"
        )

    return "UNSUPPORTED"


def settle_leg(
    row,
    prefix,
):
    result = find_finished_match(
        competition=
            str(
                row[
                    f"{prefix}_competition"
                ]
            ),
        target_home=
            str(
                row[
                    f"{prefix}_home"
                ]
            ),
        target_away=
            str(
                row[
                    f"{prefix}_away"
                ]
            ),
        target_commence=
            row.get(
                f"{prefix}_commence_time",
                "",
            ),
    )

    if result is None:
        return (
            "PENDING",
            "",
        )

    home_goals = result[
        "home_goals"
    ]
    away_goals = result[
        "away_goals"
    ]

    status = settle_market(
        row[
            f"{prefix}_market"
        ],
        home_goals,
        away_goals,
    )

    score = (
        f"{home_goals}-{away_goals}"
    )

    return status, score


def main():
    print("=" * 88)
    print(
        "CulebrIA - SETTLEMENT PARLAYS OPERATIVOS"
    )
    print("=" * 88)
    print()

    if not LEDGER_FILE.exists():
        print(
            "Sin ledger de parlays todavía."
        )
        return

    try:
        df = pd.read_csv(
            LEDGER_FILE,
            dtype=str,
        )
    except (
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
        OSError,
    ):
        print(
            "Ledger vacío o ilegible."
        )
        return

    if df.empty:
        print(
            "Ledger de parlays vacío."
        )
        return

    pending_mask = (
        df[
            "status"
        ].fillna(
            "PENDING"
        ).str.upper()
        == "PENDING"
    )

    pending_indices = list(
        df.index[
            pending_mask
        ]
    )

    print(
        f"Parlays totales: {len(df)}"
    )
    print(
        f"Parlays pendientes: "
        f"{len(pending_indices)}"
    )

    settled_now = 0

    for index in pending_indices:
        row = df.loc[
            index
        ]

        leg1_status, leg1_score = (
            settle_leg(
                row,
                "leg1",
            )
        )

        leg2_status, leg2_score = (
            settle_leg(
                row,
                "leg2",
            )
        )

        df.at[
            index,
            "leg1_status"
        ] = leg1_status

        df.at[
            index,
            "leg1_score"
        ] = leg1_score

        df.at[
            index,
            "leg2_status"
        ] = leg2_status

        df.at[
            index,
            "leg2_score"
        ] = leg2_score

        statuses = {
            leg1_status,
            leg2_status,
        }

        if "LOSS" in statuses:
            final_status = "LOSS"
        elif statuses == {"WIN"}:
            final_status = "WIN"
        elif "UNSUPPORTED" in statuses:
            final_status = "UNSUPPORTED"
        else:
            final_status = "PENDING"

        previous = str(
            row.get(
                "status",
                "PENDING",
            )
        ).upper()

        df.at[
            index,
            "status"
        ] = final_status

        if (
            final_status
            in {
                "WIN",
                "LOSS",
                "UNSUPPORTED",
            }
            and previous == "PENDING"
        ):
            df.at[
                index,
                "settled_at_utc"
            ] = datetime.now(
                timezone.utc
            ).isoformat()

            settled_now += 1

        print()
        print(
            f"{row['record_id']} | "
            f"{row['bookmaker']} | "
            f"{row['combined_odds']}"
        )
        print(
            f"  Pierna 1: "
            f"{leg1_status} "
            f"{leg1_score}"
        )
        print(
            f"  Pierna 2: "
            f"{leg2_status} "
            f"{leg2_score}"
        )
        print(
            f"  Parlay: {final_status}"
        )

    df.to_csv(
        LEDGER_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    wins = int(
        (
            df[
                "status"
            ].fillna(
                ""
            ).str.upper()
            == "WIN"
        ).sum()
    )

    losses = int(
        (
            df[
                "status"
            ].fillna(
                ""
            ).str.upper()
            == "LOSS"
        ).sum()
    )

    pending = int(
        (
            df[
                "status"
            ].fillna(
                ""
            ).str.upper()
            == "PENDING"
        ).sum()
    )

    print()
    print("=" * 88)
    print("RESUMEN PARLAYS")
    print("=" * 88)
    print(
        f"Liquidados ahora: {settled_now}"
    )
    print(
        f"Ganados acumulados: {wins}"
    )
    print(
        f"Perdidos acumulados: {losses}"
    )
    print(
        f"Pendientes: {pending}"
    )
    print()
    print(
        f"Ledger: {LEDGER_FILE}"
    )


if __name__ == "__main__":
    main()
