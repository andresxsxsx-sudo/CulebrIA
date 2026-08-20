from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from difflib import SequenceMatcher

import pandas as pd


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
MODEL_DIR = DATA / "tennis_model_v1"

BASE_RATINGS = MODEL_DIR / "wta_ratings.json"
CURRENT_RATINGS = MODEL_DIR / "wta_ratings_current.json"
CURRENT_RANKINGS = MODEL_DIR / "wta_current_rankings.json"

MAPPING_REPORT = MODEL_DIR / "wta_name_mapping_rebuild.csv"
SUMMARY_REPORT = MODEL_DIR / "wta_name_mapping_rebuild.json"

SAFE_START_DATE = pd.Timestamp("2026-06-09")
BASE_RATING = 1500.0
ELO_SCALE = 400.0


def normalize(value):
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        ch for ch in text
        if not unicodedata.combining(ch)
    )
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def safe_float(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if math.isnan(result):
        return None

    return result


def parse_winner_code(value):
    text = normalize(value)

    if text in {
        "1",
        "home",
        "home player",
        "player 1",
        "player1",
        "p1",
    }:
        return 1

    if text in {
        "2",
        "away",
        "away player",
        "player 2",
        "player2",
        "p2",
    }:
        return 2

    number = safe_float(value)

    if number == 1:
        return 1

    if number == 2:
        return 2

    return None


def parse_date_series(series):
    raw = series.copy()
    text = raw.astype(str).str.strip()

    result = pd.Series(
        pd.NaT,
        index=series.index,
        dtype="datetime64[ns]",
    )

    numeric = pd.to_numeric(
        raw,
        errors="coerce",
    )

    yyyymmdd = (
        numeric.notna()
        & numeric.between(
            19000101,
            21001231,
        )
    )

    if yyyymmdd.any():
        result.loc[
            yyyymmdd
        ] = pd.to_datetime(
            numeric.loc[
                yyyymmdd
            ]
            .round()
            .astype("Int64")
            .astype(str),
            format="%Y%m%d",
            errors="coerce",
        )

    epoch = (
        numeric.notna()
        & ~yyyymmdd
    )

    if epoch.any():
        values = numeric.loc[
            epoch
        ].abs()

        unit_masks = {
            "s":
                values < 1e11,
            "ms":
                (values >= 1e11)
                & (values < 1e14),
            "us":
                (values >= 1e14)
                & (values < 1e17),
            "ns":
                values >= 1e17,
        }

        for unit, mask in unit_masks.items():
            if not mask.any():
                continue

            idx = values.index[
                mask
            ]

            parsed = pd.to_datetime(
                numeric.loc[idx],
                unit=unit,
                origin="unix",
                errors="coerce",
                utc=True,
            ).dt.tz_convert(None)

            result.loc[
                idx
            ] = parsed

    remaining = (
        result.isna()
        & text.ne("")
        & text.ne("nan")
        & text.ne("None")
    )

    if remaining.any():
        try:
            parsed = pd.to_datetime(
                text.loc[
                    remaining
                ],
                format="mixed",
                errors="coerce",
                utc=True,
            ).dt.tz_convert(None)
        except (TypeError, ValueError):
            parsed = pd.to_datetime(
                text.loc[
                    remaining
                ],
                errors="coerce",
                utc=True,
            ).dt.tz_convert(None)

        result.loc[
            remaining
        ] = parsed

    return result


def normalize_surface(value):
    text = normalize(value)

    if "hard" in text:
        return "Hard"

    if "clay" in text:
        return "Clay"

    if "grass" in text:
        return "Grass"

    if "carpet" in text:
        return "Carpet"

    if "indoor" in text:
        return "Indoor"

    return "Unknown"


def main_tour_match(value):
    text = normalize(value)

    if not text:
        return False

    if (
        "chall" in text
        or "itf" in text
        or "qualification" in text
        or "qualif" in text
    ):
        return False

    return "wta" in text


def locate_season():
    filename = "2026-wta-season.csv"

    for path in [
        ROOT / filename,
        DATA / filename,
        MODEL_DIR / filename,
        Path.home() / "Downloads" / filename,
        Path.home() / "Descargas" / filename,
        Path.home() / "Desktop" / filename,
        Path.home() / "Escritorio" / filename,
    ]:
        if (
            path.exists()
            and path.is_file()
            and path.stat().st_size > 100
        ):
            return path

    return None


def elo_probability(diff):
    return 1.0 / (
        1.0
        + 10.0 ** (
            -diff / ELO_SCALE
        )
    )


def surface_rating(player, surface):
    surfaces = player.setdefault(
        "surfaces",
        {}
    )

    value = safe_float(
        surfaces.get(surface)
    )

    if value is not None:
        return value

    general = safe_float(
        player.get("general")
    )

    if general is None:
        general = BASE_RATING

    return general


def update_match(
    winner,
    loser,
    surface,
    params,
):
    k_general = float(
        params["k_general"]
    )
    k_surface = float(
        params["k_surface"]
    )

    w_general = safe_float(
        winner.get("general")
    )
    l_general = safe_float(
        loser.get("general")
    )

    if w_general is None:
        w_general = BASE_RATING

    if l_general is None:
        l_general = BASE_RATING

    w_matches = int(
        winner.get("matches", 0)
        or 0
    )
    l_matches = int(
        loser.get("matches", 0)
        or 0
    )

    w_mult = (
        1.20
        if w_matches < 30
        else 1.0
    )
    l_mult = (
        1.20
        if l_matches < 30
        else 1.0
    )

    expected_w = elo_probability(
        w_general - l_general
    )

    winner["general"] = (
        w_general
        + k_general
        * w_mult
        * (1.0 - expected_w)
    )

    loser["general"] = (
        l_general
        - k_general
        * l_mult
        * (1.0 - expected_w)
    )

    if surface != "Unknown":
        w_surface = surface_rating(
            winner,
            surface,
        )
        l_surface = surface_rating(
            loser,
            surface,
        )

        expected_surface_w = (
            elo_probability(
                w_surface - l_surface
            )
        )

        winner.setdefault(
            "surfaces",
            {},
        )[surface] = (
            w_surface
            + k_surface
            * w_mult
            * (
                1.0
                - expected_surface_w
            )
        )

        loser.setdefault(
            "surfaces",
            {},
        )[surface] = (
            l_surface
            - k_surface
            * l_mult
            * (
                1.0
                - expected_surface_w
            )
        )

    winner["matches"] = (
        w_matches + 1
    )
    loser["matches"] = (
        l_matches + 1
    )


def build_base_index(players):
    by_exact = {}
    candidates = []

    for key, payload in players.items():
        full_name = str(
            payload.get(
                "name",
                "",
            )
        ).strip()

        norm = normalize(full_name)

        if not norm:
            continue

        matches = int(
            payload.get(
                "matches",
                0,
            )
            or 0
        )

        existing = by_exact.get(norm)

        if (
            existing is None
            or matches
            > existing["matches"]
        ):
            by_exact[norm] = {
                "key": key,
                "name": full_name,
                "matches": matches,
            }

    for norm, payload in by_exact.items():
        tokens = norm.split()

        candidates.append(
            {
                "norm": norm,
                "tokens": tokens,
                "key": payload["key"],
                "name": payload["name"],
                "matches": payload["matches"],
            }
        )

    return by_exact, candidates


def abbreviation_matches(
    source_norm,
    candidate_tokens,
):
    source_tokens = source_norm.split()

    if len(source_tokens) < 2:
        return False

    long_tokens = [
        token
        for token in source_tokens
        if len(token) >= 2
    ]

    initials = [
        token
        for token in source_tokens
        if len(token) == 1
    ]

    if not long_tokens:
        return False

    # TennisData suele usar "apellido inicial".
    # Exigimos que todos los tokens largos aparezcan completos
    # en el nombre base.
    if not all(
        token in candidate_tokens
        for token in long_tokens
    ):
        return False

    # Y que cada inicial pueda corresponder a algún token adicional.
    for initial in initials:
        if not any(
            token.startswith(initial)
            for token in candidate_tokens
        ):
            return False

    return True


def resolve_source_name(
    source_name,
    by_exact,
    candidates,
):
    source_norm = normalize(
        source_name
    )

    if not source_norm:
        return {
            "status": "UNRESOLVED",
            "source_norm": source_norm,
        }

    exact = by_exact.get(
        source_norm
    )

    if exact is not None:
        return {
            "status": "EXACT",
            "source_norm": source_norm,
            "key": exact["key"],
            "canonical_name": exact["name"],
            "score": 1.0,
        }

    scored = []

    for candidate in candidates:
        ratio = SequenceMatcher(
            None,
            source_norm,
            candidate["norm"],
        ).ratio()

        abbrev = abbreviation_matches(
            source_norm,
            candidate["tokens"],
        )

        score = ratio

        if abbrev:
            score = max(
                score,
                0.97,
            )

        if score >= 0.88:
            scored.append(
                (
                    score,
                    int(abbrev),
                    candidate["matches"],
                    candidate,
                )
            )

    scored.sort(
        key=lambda item: (
            item[0],
            item[1],
            item[2],
        ),
        reverse=True,
    )

    if not scored:
        return {
            "status": "UNRESOLVED",
            "source_norm": source_norm,
        }

    best = scored[0]

    # Si dos candidatas quedan prácticamente empatadas,
    # no adivinamos.
    if len(scored) > 1:
        second = scored[1]

        if (
            best[0] - second[0]
            < 0.02
            and best[3]["key"]
            != second[3]["key"]
        ):
            return {
                "status": "AMBIGUOUS",
                "source_norm": source_norm,
                "best_name": best[3]["name"],
                "best_score": best[0],
                "second_name": second[3]["name"],
                "second_score": second[0],
            }

    candidate = best[3]

    return {
        "status":
            (
                "ABBREV"
                if best[1]
                else "FUZZY"
            ),
        "source_norm": source_norm,
        "key": candidate["key"],
        "canonical_name": candidate["name"],
        "score": best[0],
    }


def create_live_player(
    players,
    source_name,
):
    source_norm = normalize(
        source_name
    )

    safe = source_norm.replace(
        " ",
        "_",
    )

    key = (
        f"WTA_LIVE_NAME_{safe}"
    )

    suffix = 1
    original = key

    while key in players:
        suffix += 1
        key = (
            f"{original}_{suffix}"
        )

    players[key] = {
        "name": str(
            source_name
        ).strip(),
        "normalized_name":
            source_norm,
        "general":
            BASE_RATING,
        "surfaces":
            {},
        "matches":
            0,
    }

    return key


def round_players(players):
    for payload in players.values():
        general = safe_float(
            payload.get("general")
        )

        if general is not None:
            payload["general"] = round(
                general,
                4,
            )

        payload["surfaces"] = {
            surface:
                round(
                    float(rating),
                    4,
                )
            for surface, rating
            in payload.get(
                "surfaces",
                {}
            ).items()
        }


def main():
    print("=" * 94)
    print(
        "🐍 CULEBRIA WTA — RECONSTRUIR RATINGS "
        "CON MAPEO CANÓNICO"
    )
    print("=" * 94)
    print()
    print(
        "Este script reconstruye WTA current DESDE el baseline "
        "de mayo; no usa el archivo current defectuoso."
    )
    print(
        "No consulta APIs y no modifica fútbol."
    )

    if not BASE_RATINGS.exists():
        raise SystemExit(
            f"ERROR: falta {BASE_RATINGS}"
        )

    season_path = locate_season()

    if season_path is None:
        raise SystemExit(
            "ERROR: no encontré 2026-wta-season.csv"
        )

    print(
        f"Baseline: {BASE_RATINGS}"
    )
    print(
        f"Temporada: {season_path}"
    )

    baseline = json.loads(
        BASE_RATINGS.read_text(
            encoding="utf-8"
        )
    )

    params = baseline[
        "params"
    ]

    # Copia profunda para conservar el baseline intacto.
    players = json.loads(
        json.dumps(
            baseline[
                "players"
            ],
            ensure_ascii=False,
        )
    )

    by_exact, candidates = (
        build_base_index(
            players
        )
    )

    df = pd.read_csv(
        season_path,
        low_memory=False,
    )

    required = {
        "date_timestamp",
        "home_name",
        "away_name",
        "winner_code",
        "surface",
        "tournament",
        "home_rank",
        "away_rank",
    }

    missing = sorted(
        required
        - set(df.columns)
    )

    if missing:
        raise SystemExit(
            f"ERROR: faltan columnas: {missing}"
        )

    work = df.copy()

    work[
        "_date"
    ] = parse_date_series(
        work[
            "date_timestamp"
        ]
    )

    work[
        "_winner_code"
    ] = work[
        "winner_code"
    ].apply(
        parse_winner_code
    )

    work = work[
        work[
            "_date"
        ].notna()
        & work[
            "_winner_code"
        ].isin(
            [
                1,
                2,
            ]
        )
    ].copy()

    work = work[
        work[
            "_date"
        ]
        >= SAFE_START_DATE
    ].copy()

    work = work[
        work[
            "tournament"
        ].apply(
            main_tour_match
        )
    ].copy()

    work[
        "_home_norm"
    ] = work[
        "home_name"
    ].apply(
        normalize
    )

    work[
        "_away_norm"
    ] = work[
        "away_name"
    ].apply(
        normalize
    )

    work = work[
        work[
            "_home_norm"
        ].ne("")
        & work[
            "_away_norm"
        ].ne("")
        & work[
            "_home_norm"
        ].ne(
            work[
                "_away_norm"
            ]
        )
    ].copy()

    work[
        "_identity"
    ] = (
        work[
            "_date"
        ].dt.strftime(
            "%Y-%m-%d"
        )
        + "|"
        + work[
            "_home_norm"
        ]
        + "|"
        + work[
            "_away_norm"
        ]
        + "|"
        + work[
            "_winner_code"
        ].astype(int).astype(str)
    )

    work = work.drop_duplicates(
        subset=[
            "_identity"
        ],
        keep="last",
    ).sort_values(
        "_date"
    )

    # Resolvemos todos los nombres una vez.
    source_names = sorted(
        set(
            work[
                "_home_norm"
            ]
        )
        | set(
            work[
                "_away_norm"
            ]
        )
    )

    resolution = {}
    report_rows = []

    for source_norm in source_names:
        result = resolve_source_name(
            source_norm,
            by_exact,
            candidates,
        )

        resolution[
            source_norm
        ] = result

        report_rows.append(
            {
                "source_name":
                    source_norm,
                "status":
                    result[
                        "status"
                    ],
                "canonical_name":
                    result.get(
                        "canonical_name"
                    ),
                "score":
                    result.get(
                        "score"
                    ),
                "best_name":
                    result.get(
                        "best_name"
                    ),
                "best_score":
                    result.get(
                        "best_score"
                    ),
                "second_name":
                    result.get(
                        "second_name"
                    ),
                "second_score":
                    result.get(
                        "second_score"
                    ),
            }
        )

    counts = defaultdict(int)

    for result in resolution.values():
        counts[
            result[
                "status"
            ]
        ] += 1

    print()
    print("MAPEO DE NOMBRES DEL MAIN TOUR:")
    for status in (
        "EXACT",
        "ABBREV",
        "FUZZY",
        "AMBIGUOUS",
        "UNRESOLVED",
    ):
        print(
            f"  {status}: "
            f"{counts[status]}"
        )

    # Para nombres realmente nuevos creamos un estado LIVE.
    live_keys = {}

    for source_norm, result in (
        resolution.items()
    ):
        if result[
            "status"
        ] == "UNRESOLVED":
            live_keys[
                source_norm
            ] = create_live_player(
                players,
                source_norm,
            )

    rankings = {}
    aliases = {}
    matches_added = 0
    skipped_ambiguous_matches = 0
    unknown_surface = 0

    def resolved_key(source_name):
        source_norm = normalize(
            source_name
        )

        result = resolution.get(
            source_norm
        )

        if result is None:
            return None, None, "UNRESOLVED"

        status = result[
            "status"
        ]

        if status in {
            "EXACT",
            "ABBREV",
            "FUZZY",
        }:
            key = result[
                "key"
            ]

            canonical = str(
                players[
                    key
                ].get(
                    "name",
                    source_name,
                )
            )

            aliases[
                source_norm
            ] = {
                "key":
                    key,
                "canonical_name":
                    canonical,
                "method":
                    status,
            }

            return (
                key,
                canonical,
                status,
            )

        if status == "UNRESOLVED":
            key = live_keys.get(
                source_norm
            )

            if key is None:
                return (
                    None,
                    None,
                    status,
                )

            return (
                key,
                str(
                    players[
                        key
                    ][
                        "name"
                    ]
                ),
                status,
            )

        return (
            None,
            None,
            status,
        )

    for _, row in work.iterrows():
        home_name = str(
            row[
                "home_name"
            ]
        ).strip()

        away_name = str(
            row[
                "away_name"
            ]
        ).strip()

        (
            home_key,
            home_canonical,
            home_status,
        ) = resolved_key(
            home_name
        )

        (
            away_key,
            away_canonical,
            away_status,
        ) = resolved_key(
            away_name
        )

        if (
            home_key is None
            or away_key is None
            or home_key == away_key
        ):
            skipped_ambiguous_matches += 1
            continue

        winner_code = int(
            row[
                "_winner_code"
            ]
        )

        if winner_code == 1:
            winner_key = home_key
            loser_key = away_key
        else:
            winner_key = away_key
            loser_key = home_key

        surface = normalize_surface(
            row[
                "surface"
            ]
        )

        if surface == "Unknown":
            unknown_surface += 1

        update_match(
            players[
                winner_key
            ],
            players[
                loser_key
            ],
            surface,
            params,
        )

        match_date = str(
            row[
                "_date"
            ].date()
        )

        home_rank = safe_float(
            row[
                "home_rank"
            ]
        )

        away_rank = safe_float(
            row[
                "away_rank"
            ]
        )

        if home_rank is not None:
            canonical_norm = normalize(
                home_canonical
            )

            rankings[
                canonical_norm
            ] = {
                "name":
                    home_canonical,
                "rank":
                    int(
                        home_rank
                    ),
                "date":
                    match_date,
                "source_name":
                    home_name,
                "mapping_status":
                    home_status,
            }

            # Alias adicional para auditoría/compatibilidad.
            rankings[
                normalize(
                    home_name
                )
            ] = {
                "name":
                    home_canonical,
                "rank":
                    int(
                        home_rank
                    ),
                "date":
                    match_date,
                "source_name":
                    home_name,
                "mapping_status":
                    home_status,
            }

        if away_rank is not None:
            canonical_norm = normalize(
                away_canonical
            )

            rankings[
                canonical_norm
            ] = {
                "name":
                    away_canonical,
                "rank":
                    int(
                        away_rank
                    ),
                "date":
                    match_date,
                "source_name":
                    away_name,
                "mapping_status":
                    away_status,
            }

            rankings[
                normalize(
                    away_name
                )
            ] = {
                "name":
                    away_canonical,
                "rank":
                    int(
                        away_rank
                    ),
                "date":
                    match_date,
                "source_name":
                    away_name,
                "mapping_status":
                    away_status,
            }

        matches_added += 1

    round_players(
        players
    )

    through = (
        str(
            work[
                "_date"
            ].max().date()
        )
        if not work.empty
        else None
    )

    current_payload = {
        **baseline,
        "live_update": {
            "source":
                str(
                    season_path
                ),
            "safe_start_date":
                str(
                    SAFE_START_DATE.date()
                ),
            "updated_at_utc":
                datetime.now(
                    timezone.utc
                ).isoformat(),
            "matches_added":
                matches_added,
            "through":
                through,
            "unknown_surface_matches":
                unknown_surface,
            "skipped_ambiguous_matches":
                skipped_ambiguous_matches,
            "canonical_name_mapping":
                True,
            "note":
                (
                    "Rebuilt from frozen baseline using canonical "
                    "TennisData -> Sackmann name mapping."
                ),
        },
        "aliases":
            aliases,
        "players":
            players,
    }

    ranking_payload = {
        "tour":
            "WTA",
        "generated_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),
        "source":
            str(
                season_path
            ),
        "canonical_name_mapping":
            True,
        "players":
            rankings,
    }

    CURRENT_RATINGS.write_text(
        json.dumps(
            current_payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    CURRENT_RANKINGS.write_text(
        json.dumps(
            ranking_payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    pd.DataFrame(
        report_rows
    ).to_csv(
        MAPPING_REPORT,
        index=False,
        encoding="utf-8-sig",
    )

    summary = {
        "generated_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),
        "season_file":
            str(
                season_path
            ),
        "safe_start_date":
            str(
                SAFE_START_DATE.date()
            ),
        "through":
            through,
        "matches_added":
            matches_added,
        "skipped_ambiguous_matches":
            skipped_ambiguous_matches,
        "unknown_surface_matches":
            unknown_surface,
        "mapping_counts":
            dict(
                counts
            ),
        "live_players_created":
            len(
                live_keys
            ),
        "ranking_keys_written":
            len(
                rankings
            ),
    }

    SUMMARY_REPORT.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 94)
    print("RESULTADO")
    print("=" * 94)
    print(
        f"✅ Partidos añadidos: "
        f"{matches_added}"
    )
    print(
        f"✅ Ratings reconstruidos hasta: "
        f"{through}"
    )
    print(
        f"✅ Nuevas entradas LIVE_NAME reales: "
        f"{len(live_keys)}"
    )
    print(
        f"⚠️ Partidos omitidos por nombre ambiguo: "
        f"{skipped_ambiguous_matches}"
    )
    print(
        f"Rankings/aliases escritos: "
        f"{len(rankings)}"
    )
    print()
    print(
        f"Ratings actuales: "
        f"{CURRENT_RATINGS}"
    )
    print(
        f"Rankings actuales: "
        f"{CURRENT_RANKINGS}"
    )
    print(
        f"Reporte de mapeo: "
        f"{MAPPING_REPORT}"
    )
    print()
    print(
        "Ahora ejecuta:"
    )
    print()
    print(
        "  python culebria_tennis_operational_v1.py"
    )


if __name__ == "__main__":
    main()
