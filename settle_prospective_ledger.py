import json
import os
import unicodedata

from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

from src.analysis.prospective_tracker import (
    FIELDNAMES,
    LEDGER_FILE,
    ensure_ledger,
)

from src.api.fdorg_local_history import (
    load_competition_history,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"

FDORG_DIR = (
    DATA_DIR
    / "fdorg_matches"
)

REPORT_FILE = (
    DATA_DIR
    / "prospective"
    / "settlement_report.csv"
)

TEMP_LEDGER_FILE = (
    DATA_DIR
    / "prospective"
    / "prospective_ledger_temp.csv"
)


# ============================================================
# DECISIONES QUE REPRESENTAN UNA APUESTA EJECUTADA
#
# Actualmente CulebrIA todavía NO utiliza ninguna de estas.
# Por tanto, NO_BET_PRICE y NEEDS_VIG_CHECK tendrán profit = 0.
# ============================================================

EXECUTED_BET_DECISIONS = {
    "BET_PLACED",
    "BET_APPROVED",
}


# ============================================================
# ALIAS DE EQUIPOS
# ============================================================

TEAM_ALIASES = {
    "se palmeiras":
        "palmeiras",

    "sociedade esportiva palmeiras":
        "palmeiras",

    "sc internacional":
        "internacional",

    "sport club internacional":
        "internacional",

    "ec bahia":
        "bahia",

    "esporte clube bahia":
        "bahia",

    "cr vasco da gama":
        "vasco da gama",

    "club de regatas vasco da gama":
        "vasco da gama",

    "rb bragantino":
        "bragantino",

    "red bull bragantino":
        "bragantino",

    "sc corinthians paulista":
        "corinthians",

    "sport club corinthians paulista":
        "corinthians",

    "gil vicente fc":
        "gil vicente",

    "rio ave fc":
        "rio ave",

    "moreirense fc":
        "moreirense",

    "sporting clube de braga":
        "braga",

    "sc braga":
        "braga",

    "sport lisboa e benfica":
        "benfica",

    "academico de viseu fc":
        "academico viseu",

    "academico de viseu":
        "academico viseu",

    "santos fc":
        "santos",

    "ca paranaense":
        "atletico paranaense",

    "athletico paranaense":
        "atletico paranaense",
}


# ============================================================
# NORMALIZACIÓN
# ============================================================

def normalize_name(value):

    text = str(
        value
    ).strip().lower()

    text = unicodedata.normalize(
        "NFKD",
        text
    )

    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )

    text = (
        text
        .replace("-", " ")
        .replace(".", " ")
        .replace(",", " ")
        .replace("'", "")
    )

    text = " ".join(
        text.split()
    )

    if text in TEAM_ALIASES:

        return TEAM_ALIASES[
            text
        ]

    removable = {
        "fc",
        "cf",
        "club",
        "clube",
        "football",
        "futebol",
    }

    tokens = [
        token
        for token in text.split()
        if token not in removable
    ]

    text = " ".join(
        tokens
    )

    if text in TEAM_ALIASES:

        return TEAM_ALIASES[
            text
        ]

    return text


def similarity(
    first,
    second
):

    a = normalize_name(
        first
    )

    b = normalize_name(
        second
    )

    if a == b:

        return 1.0

    sequence = SequenceMatcher(
        None,
        a,
        b
    ).ratio()

    tokens_a = set(
        a.split()
    )

    tokens_b = set(
        b.split()
    )

    jaccard = 0.0
    containment = 0.0

    if (
        tokens_a
        and tokens_b
    ):

        intersection = (
            tokens_a
            & tokens_b
        )

        union = (
            tokens_a
            | tokens_b
        )

        jaccard = (
            len(intersection)
            / len(union)
        )

        if (
            tokens_a.issubset(
                tokens_b
            )
            or
            tokens_b.issubset(
                tokens_a
            )
        ):

            containment = 0.96

    return max(
        sequence,
        jaccard,
        containment
    )


# ============================================================
# FECHAS
# ============================================================

def parse_datetime(value):

    if (
        value is None
        or
        pd.isna(value)
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
# CARGAR FOOTBALL-DATA.ORG
# ============================================================

def load_competition_matches(
    competition
):
    # Usa el loader centralizado para respetar api_data -> matches
    # y combinar temporada actual + históricos disponibles.

    try:

        history = (
            load_competition_history(
                competition
            )
        )

    except RuntimeError:

        return []

    return history[
        "matches"
    ]


# ============================================================
# DATOS DE EQUIPOS FD.ORG
# ============================================================

def fdorg_team_name(
    match,
    side
):

    team = match.get(
        side,
        {}
    )

    if not isinstance(
        team,
        dict
    ):

        return ""

    return (
        team.get(
            "name"
        )
        or
        team.get(
            "shortName"
        )
        or
        team.get(
            "tla"
        )
        or
        ""
    )


# ============================================================
# BUSCAR PARTIDO FINALIZADO
# ============================================================

def find_finished_match(
    matches,
    home,
    away,
    kickoff
):

    best_match = None
    best_similarity = 0.0
    best_time_difference = None

    for match in matches:

        if str(
            match.get(
                "status",
                ""
            )
        ).upper() != "FINISHED":

            continue

        fd_home = fdorg_team_name(
            match,
            "homeTeam"
        )

        fd_away = fdorg_team_name(
            match,
            "awayTeam"
        )

        home_score = similarity(
            home,
            fd_home
        )

        away_score = similarity(
            away,
            fd_away
        )

        combined_similarity = (
            home_score
            +
            away_score
        ) / 2

        match_date = parse_datetime(
            match.get(
                "utcDate"
            )
        )

        if (
            kickoff is not None
            and match_date is not None
        ):

            difference_hours = abs(
                (
                    kickoff
                    - match_date
                ).total_seconds()
            ) / 3600

        else:

            difference_hours = None

        # No cruzamos partidos muy alejados.
        if (
            difference_hours is not None
            and difference_hours > 24
        ):

            continue

        if combined_similarity > best_similarity:

            best_similarity = (
                combined_similarity
            )

            best_match = (
                match
            )

            best_time_difference = (
                difference_hours
            )

    if best_match is None:

        return None

    if best_similarity < 0.82:

        return None

    return {
        "match":
            best_match,

        "similarity":
            best_similarity,

        "time_difference_hours":
            best_time_difference,
    }


# ============================================================
# RESULTADO FINAL
# ============================================================

def get_full_time_score(
    match
):

    score = match.get(
        "score",
        {}
    )

    full_time = score.get(
        "fullTime",
        {}
    )

    home_goals = full_time.get(
        "home"
    )

    away_goals = full_time.get(
        "away"
    )

    if (
        home_goals is None
        or
        away_goals is None
    ):

        return None

    try:

        return (
            int(
                home_goals
            ),
            int(
                away_goals
            )
        )

    except (
        TypeError,
        ValueError
    ):

        return None


# ============================================================
# SETTLEMENT DE MERCADOS
# ============================================================

def settle_market(
    market,
    home_goals,
    away_goals
):

    market = str(
        market
    ).strip().upper()

    # --------------------------------------------------------
    # 1X
    # --------------------------------------------------------

    if market == "1X":

        return (
            1
            if home_goals >= away_goals
            else 0
        )

    # --------------------------------------------------------
    # AWAY SCORES
    # --------------------------------------------------------

    if market == "AWAY_SCORES":

        return (
            1
            if away_goals >= 1
            else 0
        )

    # --------------------------------------------------------
    # X2
    # Aunque está bloqueado actualmente,
    # dejamos soporte técnico.
    # --------------------------------------------------------

    if market == "X2":

        return (
            1
            if away_goals >= home_goals
            else 0
        )

    return None


# ============================================================
# PROFIT
# ============================================================

def calculate_profit(
    decision,
    market_result,
    decimal_odds
):

    decision = str(
        decision
    ).strip().upper()

    # --------------------------------------------------------
    # NO hubo apuesta real.
    # --------------------------------------------------------

    if (
        decision
        not in EXECUTED_BET_DECISIONS
    ):

        return 0.0

    # --------------------------------------------------------
    # Apuesta de 1 unidad.
    # --------------------------------------------------------

    if market_result == 1:

        return (
            float(
                decimal_odds
            )
            - 1
        )

    return -1.0


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    print("=" * 88)
    print(
        "CulebrIA - PROSPECTIVE SETTLEMENT"
    )
    print("=" * 88)

    ensure_ledger()

    ledger = pd.read_csv(
        LEDGER_FILE,
        dtype=str
    )

    print()

    print(
        f"Registros totales: "
        f"{len(ledger)}"
    )

    if ledger.empty:

        print()
        print(
            "No existen snapshots "
            "prospectivos todavía."
        )

        print()
        print(
            "Pendientes: 0"
        )

        print(
            "Liquidados: 0"
        )

        print()
        print(
            "Solicitudes API: 0"
        )

        print(
            "Créditos utilizados: 0"
        )

        return

    # --------------------------------------------------------
    # NORMALIZAR SETTLED
    # --------------------------------------------------------

    ledger[
        "settled"
    ] = (
        ledger[
            "settled"
        ]
        .fillna(
            "NO"
        )
        .astype(str)
        .str.upper()
    )

    pending_indexes = ledger[
        ledger[
            "settled"
        ] != "YES"
    ].index.tolist()

    print(
        f"Registros pendientes: "
        f"{len(pending_indexes)}"
    )

    if not pending_indexes:

        print()
        print(
            "✅ No hay registros "
            "pendientes de liquidar."
        )

        return

    # ========================================================
    # CACHE LOCAL POR COMPETICIÓN
    # ========================================================

    competition_cache = {}

    settled_count = 0
    unavailable_count = 0
    unsupported_count = 0

    report_rows = []

    # ========================================================
    # PROCESAR PENDIENTES
    # ========================================================

    for index in pending_indexes:

        row = ledger.loc[
            index
        ]

        competition = str(
            row.get(
                "competition",
                ""
            )
        ).upper()

        home = str(
            row.get(
                "home",
                ""
            )
        )

        away = str(
            row.get(
                "away",
                ""
            )
        )

        market = str(
            row.get(
                "market",
                ""
            )
        ).upper()

        kickoff = parse_datetime(
            row.get(
                "kickoff_utc"
            )
        )

        print()
        print("-" * 88)

        print(
            f"{home} vs {away}"
        )

        print(
            f"Mercado: "
            f"{market}"
        )

        # ----------------------------------------------------
        # CARGAR COMPETICIÓN UNA SOLA VEZ
        # ----------------------------------------------------

        if competition not in competition_cache:

            competition_cache[
                competition
            ] = load_competition_matches(
                competition
            )

        matches = competition_cache[
            competition
        ]

        if not matches:

            print(
                "⏳ No hay datos locales "
                "de resultados para esta competición."
            )

            unavailable_count += 1

            report_rows.append(
                {
                    "record_id":
                        row.get(
                            "record_id",
                            ""
                        ),

                    "competition":
                        competition,

                    "home":
                        home,

                    "away":
                        away,

                    "market":
                        market,

                    "status":
                        "NO_LOCAL_DATA",
                }
            )

            continue

        # ----------------------------------------------------
        # BUSCAR PARTIDO
        # ----------------------------------------------------

        match_result = find_finished_match(
            matches=
                matches,

            home=
                home,

            away=
                away,

            kickoff=
                kickoff
        )

        if match_result is None:

            print(
                "⏳ Partido finalizado "
                "todavía no encontrado "
                "en los datos locales."
            )

            unavailable_count += 1

            report_rows.append(
                {
                    "record_id":
                        row.get(
                            "record_id",
                            ""
                        ),

                    "competition":
                        competition,

                    "home":
                        home,

                    "away":
                        away,

                    "market":
                        market,

                    "status":
                        "WAITING_RESULT",
                }
            )

            continue

        match = match_result[
            "match"
        ]

        score = get_full_time_score(
            match
        )

        if score is None:

            print(
                "⏳ El partido aparece finalizado "
                "pero no tiene marcador válido."
            )

            unavailable_count += 1
            continue

        home_goals, away_goals = (
            score
        )

        # ----------------------------------------------------
        # SETTLEMENT
        # ----------------------------------------------------

        market_result = settle_market(
            market=
                market,

            home_goals=
                home_goals,

            away_goals=
                away_goals
        )

        if market_result is None:

            print(
                "⛔ Mercado no soportado "
                "por settlement."
            )

            unsupported_count += 1
            continue

        try:

            decimal_odds = float(
                row.get(
                    "decimal_odds",
                    0
                )
            )

        except (
            TypeError,
            ValueError
        ):

            decimal_odds = 0.0

        profit_units = calculate_profit(
            decision=
                row.get(
                    "decision",
                    ""
                ),

            market_result=
                market_result,

            decimal_odds=
                decimal_odds
        )

        # ----------------------------------------------------
        # ACTUALIZAR ÚNICAMENTE CAMPOS DE RESULTADO
        # ----------------------------------------------------

        ledger.at[
            index,
            "settled"
        ] = "YES"

        ledger.at[
            index,
            "home_goals"
        ] = str(
            home_goals
        )

        ledger.at[
            index,
            "away_goals"
        ] = str(
            away_goals
        )

        ledger.at[
            index,
            "market_result"
        ] = str(
            market_result
        )

        ledger.at[
            index,
            "profit_units"
        ] = str(
            round(
                profit_units,
                4
            )
        )

        ledger.at[
            index,
            "settled_at_utc"
        ] = (
            datetime.now()
            .astimezone()
            .astimezone(
                tz=None
            )
            .isoformat(
                timespec="seconds"
            )
        )

        settled_count += 1

        result_text = (
            "HIT"
            if market_result == 1
            else "MISS"
        )

        print(
            f"Resultado: "
            f"{home_goals}-{away_goals}"
        )

        print(
            f"Mercado: "
            f"{result_text}"
        )

        print(
            f"Similitud del cruce: "
            f"{match_result['similarity']:.1%}"
        )

        print(
            f"Profit registrado: "
            f"{profit_units:+.2f} u"
        )

        if (
            str(
                row.get(
                    "decision",
                    ""
                )
            ).upper()
            not in EXECUTED_BET_DECISIONS
        ):

            print(
                "Nota: profit = 0 porque "
                "no hubo apuesta aprobada."
            )

        report_rows.append(
            {
                "record_id":
                    row.get(
                        "record_id",
                        ""
                    ),

                "competition":
                    competition,

                "home":
                    home,

                "away":
                    away,

                "market":
                    market,

                "status":
                    "SETTLED",

                "home_goals":
                    home_goals,

                "away_goals":
                    away_goals,

                "market_result":
                    market_result,

                "profit_units":
                    profit_units,

                "match_similarity":
                    match_result[
                        "similarity"
                    ],
            }
        )

    # ========================================================
    # GUARDAR LEDGER DE FORMA SEGURA
    # ========================================================

    ledger.to_csv(
        TEMP_LEDGER_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    os.replace(
        TEMP_LEDGER_FILE,
        LEDGER_FILE
    )

    # ========================================================
    # REPORTE
    # ========================================================

    pd.DataFrame(
        report_rows
    ).to_csv(
        REPORT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # RESUMEN
    # ========================================================

    remaining = int(
        (
            ledger[
                "settled"
            ]
            != "YES"
        ).sum()
    )

    print()
    print("=" * 88)
    print(
        "RESULTADO FINAL"
    )
    print("=" * 88)

    print()

    print(
        f"Liquidados ahora: "
        f"{settled_count}"
    )

    print(
        f"Pendientes de resultado: "
        f"{remaining}"
    )

    print(
        f"Sin resultado local disponible: "
        f"{unavailable_count}"
    )

    print(
        f"Mercados no soportados: "
        f"{unsupported_count}"
    )

    print()

    print(
        "Solicitudes API realizadas: 0"
    )

    print(
        "Créditos The Odds API: 0"
    )

    print()

    print(
        "Ledger actualizado:"
    )

    print(
        LEDGER_FILE
    )

    print()

    print(
        "Reporte:"
    )

    print(
        REPORT_FILE
    )


if __name__ == "__main__":
    main()