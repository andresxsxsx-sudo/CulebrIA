import json
import os
import unicodedata

from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd
import requests

from dotenv import load_dotenv


# ============================================================
# CONFIGURACIÓN
# ============================================================

BASE_URL = "https://api.the-odds-api.com/v4"

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"

SIGNALS_FILE = (
    DATA_DIR
    / "reliability_gate_signals.csv"
)

PREDICTIONS_FILE = (
    DATA_DIR
    / "poisson_predictions.csv"
)

OUTPUT_FILE = (
    DATA_DIR
    / "odds_event_matches.csv"
)

EVENT_CACHE_DIR = (
    DATA_DIR
    / "odds_events"
)

EVENT_CACHE_DIR.mkdir(
    parents=True,
    exist_ok=True
)

load_dotenv()


# ============================================================
# MAPEO DE COMPETICIONES
# ============================================================

SPORT_KEYS = {
    "BSA":
        "soccer_brazil_campeonato",

    "PPL":
        "soccer_portugal_primeira_liga",
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
        character
        for character in text
        if not unicodedata.combining(
            character
        )
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

    removable_words = {
        "fc",
        "cf",
        "futebol",
        "football",
        "clube",
        "club",
    }

    tokens = [
        token
        for token in text.split()
        if token not in removable_words
    ]

    text = " ".join(
        tokens
    )

    if text in TEAM_ALIASES:

        return TEAM_ALIASES[
            text
        ]

    return text


# ============================================================
# SIMILITUD
# ============================================================

def team_similarity(
    name_a,
    name_b
):

    a = normalize_name(
        name_a
    )

    b = normalize_name(
        name_b
    )

    if a == b:

        return 1.0

    sequence_score = (
        SequenceMatcher(
            None,
            a,
            b
        ).ratio()
    )

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
        sequence_score,
        jaccard,
        containment
    )


# ============================================================
# FECHAS
# ============================================================

def parse_datetime(value):

    if not value:

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


def time_difference_hours(
    date_a,
    date_b
):

    if (
        date_a is None
        or date_b is None
    ):

        return None

    difference = abs(
        date_a
        - date_b
    )

    return (
        difference.total_seconds()
        / 3600
    )


# ============================================================
# CONSULTAR EVENTOS
# ============================================================

def get_events(
    sport_key
):

    api_key = os.getenv(
        "THE_ODDS_API_KEY"
    )

    if not api_key:

        raise RuntimeError(
            "No se encontró "
            "THE_ODDS_API_KEY "
            "en .env"
        )

    url = (
        f"{BASE_URL}"
        f"/sports/"
        f"{sport_key}"
        f"/events"
    )

    params = {
        "apiKey":
            api_key,

        "dateFormat":
            "iso"
    }

    response = requests.get(
        url,
        params=params,
        timeout=30
    )

    remaining = response.headers.get(
        "x-requests-remaining",
        "?"
    )

    used = response.headers.get(
        "x-requests-used",
        "?"
    )

    last_cost = response.headers.get(
        "x-requests-last",
        "?"
    )

    if not response.ok:

        try:

            error = (
                response.json()
            )

        except ValueError:

            error = (
                response.text
            )

        raise RuntimeError(
            f"The Odds API "
            f"HTTP {response.status_code}: "
            f"{error}"
        )

    events = response.json()

    return {
        "events":
            events,

        "remaining":
            remaining,

        "used":
            used,

        "last_cost":
            last_cost,
    }


# ============================================================
# GUARDAR EVENTOS
# ============================================================

def save_events(
    competition,
    sport_key,
    events
):

    file_path = (
        EVENT_CACHE_DIR
        / f"{competition}_events.json"
    )

    content = {
        "fetched_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "competition":
            competition,

        "sport_key":
            sport_key,

        "events":
            events,
    }

    with open(
        file_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            content,
            file,
            ensure_ascii=False,
            indent=2
        )

    return file_path


# ============================================================
# BUSCAR EVENTO
# ============================================================

def find_best_event(
    events,
    home,
    away,
    kickoff
):

    best_event = None
    best_score = 0.0
    best_orientation = ""
    best_time_difference = None

    for event in events:

        event_home = str(
            event.get(
                "home_team",
                ""
            )
        )

        event_away = str(
            event.get(
                "away_team",
                ""
            )
        )

        event_date = parse_datetime(
            event.get(
                "commence_time"
            )
        )

        time_difference = (
            time_difference_hours(
                kickoff,
                event_date
            )
        )

        # Si conocemos ambas horas,
        # no consideramos partidos separados
        # por más de 12 horas.
        if (
            time_difference
            is not None
            and
            time_difference > 12
        ):

            continue

        # ----------------------------------------------------
        # ORIENTACIÓN NORMAL
        # ----------------------------------------------------

        normal_score = (
            team_similarity(
                home,
                event_home
            )
            +
            team_similarity(
                away,
                event_away
            )
        ) / 2

        # ----------------------------------------------------
        # ORIENTACIÓN INVERTIDA
        # ----------------------------------------------------

        inverted_score = (
            team_similarity(
                home,
                event_away
            )
            +
            team_similarity(
                away,
                event_home
            )
        ) / 2

        if (
            normal_score
            >= inverted_score
        ):

            score = (
                normal_score
            )

            orientation = (
                "NORMAL"
            )

        else:

            score = (
                inverted_score
            )

            orientation = (
                "INVERTIDO"
            )

        if score > best_score:

            best_score = score

            best_event = event

            best_orientation = (
                orientation
            )

            best_time_difference = (
                time_difference
            )

    return {
        "event":
            best_event,

        "similarity":
            best_score,

        "orientation":
            best_orientation,

        "time_difference_hours":
            best_time_difference,
    }


# ============================================================
# CLASIFICAR MATCH
# ============================================================

def classify_event_match(
    similarity,
    orientation,
    time_difference
):

    if (
        similarity >= 0.82
        and
        orientation == "NORMAL"
        and
        (
            time_difference is None
            or
            time_difference <= 3
        )
    ):

        return "MATCHED"

    if (
        similarity >= 0.70
        and
        (
            time_difference is None
            or
            time_difference <= 12
        )
    ):

        return "REVIEW"

    return "NO_MATCH"


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    print("=" * 80)
    print(
        "CulebrIA - MATCH THE ODDS API EVENTS"
    )
    print("=" * 80)

    # --------------------------------------------------------
    # SEÑALES
    # --------------------------------------------------------

    signals = pd.read_csv(
        SIGNALS_FILE
    )

    predictions = pd.read_csv(
        PREDICTIONS_FILE
    )

    predictions[
        "fixture_id"
    ] = predictions[
        "fixture_id"
    ].astype(int)

    signals[
        "fixture_id"
    ] = signals[
        "fixture_id"
    ].astype(int)

    # Necesitamos el kickoff,
    # que está guardado en poisson_predictions.
    kickoff_index = (
        predictions[
            [
                "fixture_id",
                "kickoff"
            ]
        ]
        .drop_duplicates(
            subset=[
                "fixture_id"
            ]
        )
    )

    signals = signals.merge(
        kickoff_index,
        on="fixture_id",
        how="left"
    )

    print()
    print(
        f"Señales recibidas: "
        f"{len(signals)}"
    )

    unique_fixtures = (
        signals[
            "fixture_id"
        ].nunique()
    )

    print(
        f"Partidos únicos: "
        f"{unique_fixtures}"
    )

    # ========================================================
    # CONSULTAR LAS DOS COMPETICIONES
    # ========================================================

    events_by_competition = {}

    total_reported_cost = 0

    competitions = (
        signals[
            "competition"
        ]
        .astype(str)
        .str.upper()
        .unique()
    )

    print()
    print("=" * 80)
    print(
        "DESCARGA GRATUITA DE EVENTOS"
    )
    print("=" * 80)

    for competition in competitions:

        sport_key = SPORT_KEYS.get(
            competition
        )

        print()
        print(
            f"{competition}"
        )

        if sport_key is None:

            print(
                "❌ No existe sport_key "
                "configurado."
            )

            events_by_competition[
                competition
            ] = []

            continue

        try:

            result = get_events(
                sport_key
            )

        except Exception as error:

            print(
                f"❌ {error}"
            )

            events_by_competition[
                competition
            ] = []

            continue

        events = result[
            "events"
        ]

        events_by_competition[
            competition
        ] = events

        cache_file = save_events(
            competition=
                competition,

            sport_key=
                sport_key,

            events=
                events
        )

        print(
            f"Sport key: "
            f"{sport_key}"
        )

        print(
            f"Eventos recibidos: "
            f"{len(events)}"
        )

        print(
            f"Coste última petición: "
            f"{result['last_cost']}"
        )

        print(
            f"Créditos usados: "
            f"{result['used']}"
        )

        print(
            f"Créditos restantes: "
            f"{result['remaining']}"
        )

        print(
            f"Caché local: "
            f"{cache_file.name}"
        )

        try:

            total_reported_cost += int(
                result[
                    "last_cost"
                ]
            )

        except (
            TypeError,
            ValueError
        ):

            pass

    # ========================================================
    # CRUZAR SEÑALES CON EVENTOS
    # ========================================================

    output_rows = []

    print()
    print("=" * 80)
    print(
        "CRUCE DE PARTIDOS"
    )
    print("=" * 80)

    for _, signal in signals.iterrows():

        fixture_id = int(
            signal[
                "fixture_id"
            ]
        )

        competition = str(
            signal[
                "competition"
            ]
        ).upper()

        home = str(
            signal[
                "home"
            ]
        )

        away = str(
            signal[
                "away"
            ]
        )

        market = str(
            signal[
                "market"
            ]
        )

        kickoff = parse_datetime(
            signal.get(
                "kickoff"
            )
        )

        events = (
            events_by_competition.get(
                competition,
                []
            )
        )

        result = find_best_event(
            events=
                events,

            home=
                home,

            away=
                away,

            kickoff=
                kickoff
        )

        event = result[
            "event"
        ]

        similarity = result[
            "similarity"
        ]

        orientation = result[
            "orientation"
        ]

        time_difference = result[
            "time_difference_hours"
        ]

        if event is None:

            status = (
                "NO_MATCH"
            )

            event_id = ""
            odds_home = ""
            odds_away = ""
            commence_time = ""

        else:

            status = classify_event_match(
                similarity=
                    similarity,

                orientation=
                    orientation,

                time_difference=
                    time_difference
            )

            event_id = event.get(
                "id",
                ""
            )

            odds_home = event.get(
                "home_team",
                ""
            )

            odds_away = event.get(
                "away_team",
                ""
            )

            commence_time = event.get(
                "commence_time",
                ""
            )

        output_rows.append(
            {
                "fixture_id":
                    fixture_id,

                "competition":
                    competition,

                "sport_key":
                    SPORT_KEYS.get(
                        competition,
                        ""
                    ),

                "home":
                    home,

                "away":
                    away,

                "signal_market":
                    market,

                "model_probability_pct":
                    signal[
                        "model_probability_pct"
                    ],

                "grade":
                    signal[
                        "grade"
                    ],

                "kickoff":
                    signal.get(
                        "kickoff",
                        ""
                    ),

                "event_id":
                    event_id,

                "odds_home":
                    odds_home,

                "odds_away":
                    odds_away,

                "odds_commence_time":
                    commence_time,

                "similarity":
                    round(
                        similarity,
                        3
                    ),

                "orientation":
                    orientation,

                "time_difference_hours":
                    (
                        round(
                            time_difference,
                            3
                        )
                        if time_difference
                        is not None
                        else None
                    ),

                "match_status":
                    status,
            }
        )

        print()
        print(
            f"{home} vs {away}"
        )

        print(
            f"Señal: "
            f"{market}"
        )

        print(
            f"Estado: "
            f"{status}"
        )

        if event is not None:

            print(
                f"The Odds API: "
                f"{odds_home} "
                f"vs "
                f"{odds_away}"
            )

            print(
                f"Event ID: "
                f"{event_id}"
            )

            print(
                f"Similitud: "
                f"{similarity:.1%}"
            )

            if (
                time_difference
                is not None
            ):

                print(
                    f"Diferencia horaria: "
                    f"{time_difference:.2f} h"
                )

        print(
            "-" * 60
        )

    # ========================================================
    # GUARDAR
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
    # RESUMEN
    # ========================================================

    matched = int(
        (
            output_df[
                "match_status"
            ]
            == "MATCHED"
        ).sum()
    )

    review = int(
        (
            output_df[
                "match_status"
            ]
            == "REVIEW"
        ).sum()
    )

    no_match = int(
        (
            output_df[
                "match_status"
            ]
            == "NO_MATCH"
        ).sum()
    )

    unique_matched_events = (
        output_df[
            output_df[
                "match_status"
            ]
            == "MATCHED"
        ][
            "event_id"
        ]
        .replace(
            "",
            pd.NA
        )
        .dropna()
        .nunique()
    )

    print()
    print("=" * 80)
    print(
        "RESULTADO FINAL"
    )
    print("=" * 80)

    print()

    print(
        f"Señales procesadas: "
        f"{len(output_df)}"
    )

    print(
        f"MATCHED: "
        f"{matched}"
    )

    print(
        f"REVIEW: "
        f"{review}"
    )

    print(
        f"NO MATCH: "
        f"{no_match}"
    )

    print()

    print(
        f"Eventos únicos confirmados: "
        f"{unique_matched_events}"
    )

    print()

    print(
        f"Coste total informado: "
        f"{total_reported_cost} créditos"
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