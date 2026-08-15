import json
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd


# ============================================================
# CONFIGURACIÓN
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"

CORE_FILE = (
    DATA_DIR
    / "fdorg_core_matches.csv"
)

FDORG_DIR = (
    DATA_DIR
    / "fdorg_matches"
)

OUTPUT_FILE = (
    DATA_DIR
    / "cross_source_validation.csv"
)


# ============================================================
# NORMALIZACIÓN DE NOMBRES
# ============================================================

def normalize_name(text):
    """
    Normaliza nombres de equipos procedentes
    de diferentes proveedores deportivos.
    """

    text = str(text).strip().lower()

    # Eliminar acentos
    text = unicodedata.normalize(
        "NFKD",
        text
    )

    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )

    # --------------------------------------------------------
    # EQUIVALENCIAS CONOCIDAS
    # --------------------------------------------------------

    replacements = {
        "athletico":
            "atletico",

        "ca paranaense":
            "atletico paranaense",

        "club athletico paranaense":
            "atletico paranaense",

        "club atletico paranaense":
            "atletico paranaense",

        "sport lisboa e benfica":
            "benfica",

        "academico de viseu":
            "academico viseu",

        "sporting clube de braga":
            "braga",

        "sc braga":
            "braga",

        "red bull bragantino":
            "rb bragantino",
    }

    for old, new in replacements.items():
        text = text.replace(
            old,
            new
        )

    # --------------------------------------------------------
    # ELIMINAR SIGNOS
    # --------------------------------------------------------

    text = (
        text
        .replace("-", " ")
        .replace(".", " ")
        .replace("'", "")
        .replace(",", " ")
        .replace("/", " ")
    )

    # --------------------------------------------------------
    # PALABRAS QUE NO APORTAN IDENTIDAD
    # --------------------------------------------------------

    removable_words = {
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
        if token not in removable_words
    ]

    return " ".join(tokens)


# ============================================================
# SIMILITUD ENTRE EQUIPOS
# ============================================================

def team_similarity(name_a, name_b):
    """
    Devuelve una similitud entre 0 y 1.

    Utiliza:
    - coincidencia exacta
    - inclusión de palabras
    - similitud textual
    - similitud Jaccard
    """

    a = normalize_name(name_a)
    b = normalize_name(name_b)

    # Coincidencia exacta
    if a == b:
        return 1.0

    tokens_a = set(a.split())
    tokens_b = set(b.split())

    containment_score = 0
    jaccard = 0

    if tokens_a and tokens_b:

        # Si un nombre está contenido
        # completamente en el otro
        if (
            tokens_a.issubset(tokens_b)
            or
            tokens_b.issubset(tokens_a)
        ):
            containment_score = 0.96

        intersection = (
            tokens_a
            & tokens_b
        )

        union = (
            tokens_a
            | tokens_b
        )

        if union:
            jaccard = (
                len(intersection)
                / len(union)
            )

    # Similitud de texto
    sequence_score = SequenceMatcher(
        None,
        a,
        b
    ).ratio()

    return max(
        sequence_score,
        jaccard,
        containment_score
    )


# ============================================================
# FECHAS
# ============================================================

def parse_datetime(value):
    """
    Convierte fechas ISO en datetime.
    """

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


# ============================================================
# LOCALIZAR FIXTURES DEL DÍA
# ============================================================

def find_daily_fixture_file():
    """
    Busca el archivo fixtures_YYYY-MM-DD.json
    más reciente.
    """

    files = sorted(
        DATA_DIR.glob(
            "fixtures_*.json"
        )
    )

    if not files:
        raise RuntimeError(
            "No se encontró ningún archivo "
            "fixtures_YYYY-MM-DD.json"
        )

    return files[-1]


# ============================================================
# CARGAR API-FOOTBALL DESDE CACHÉ
# ============================================================

def load_api_football_fixtures():

    file_path = (
        find_daily_fixture_file()
    )

    with open(
        file_path,
        "r",
        encoding="utf-8"
    ) as file:

        cached = json.load(file)

    api_data = cached.get(
        "api_data",
        {}
    )

    fixtures = api_data.get(
        "response",
        []
    )

    return {
        item.get(
            "fixture",
            {}
        ).get("id"): item

        for item in fixtures

        if item.get(
            "fixture",
            {}
        ).get("id") is not None
    }


# ============================================================
# CARGAR FOOTBALL-DATA.ORG DESDE CACHÉ
# ============================================================

def load_fdorg_matches(code):

    file_path = (
        FDORG_DIR
        / f"{code}_matches.json"
    )

    if not file_path.exists():

        raise RuntimeError(
            f"No existe el archivo: "
            f"{file_path}"
        )

    with open(
        file_path,
        "r",
        encoding="utf-8"
    ) as file:

        cached = json.load(file)

    api_data = cached.get(
        "api_data",
        {}
    )

    return api_data.get(
        "matches",
        []
    )


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    print("=" * 72)
    print("CulebrIA - VALIDACIÓN CRUZADA")
    print("=" * 72)

    # --------------------------------------------------------
    # CARGAR LOS PARTIDOS CORE
    # --------------------------------------------------------

    core_df = pd.read_csv(
        CORE_FILE
    )

    print()
    print(
        f"Partidos CORE a validar: "
        f"{len(core_df)}"
    )

    # --------------------------------------------------------
    # CARGAR API-FOOTBALL LOCAL
    # --------------------------------------------------------

    daily_index = (
        load_api_football_fixtures()
    )

    results = []

    verified = 0
    review = 0
    not_matched = 0

    # --------------------------------------------------------
    # VALIDAR PARTIDO POR PARTIDO
    # --------------------------------------------------------

    for _, row in core_df.iterrows():

        fixture_id = int(
            row["fixture_id"]
        )

        code = str(
            row["fdorg_code"]
        ).strip().upper()

        home = str(
            row["home"]
        )

        away = str(
            row["away"]
        )

        api_fixture = daily_index.get(
            fixture_id
        )

        if api_fixture is None:

            print()
            print(
                f"⚠️ Fixture ID "
                f"{fixture_id} "
                f"no encontrado."
            )

            not_matched += 1

            continue

        api_date = parse_datetime(
            api_fixture[
                "fixture"
            ].get(
                "date"
            )
        )

        fdorg_matches = (
            load_fdorg_matches(
                code
            )
        )

        best_match = None
        best_score = 0
        best_orientation = ""

        # ----------------------------------------------------
        # BUSCAR EL MEJOR PARTIDO EN LA SEGUNDA FUENTE
        # ----------------------------------------------------

        for candidate in fdorg_matches:

            fd_date = parse_datetime(
                candidate.get(
                    "utcDate"
                )
            )

            # Solo partidos del mismo día
            # o ±1 día por zonas horarias.
            if (
                api_date is not None
                and fd_date is not None
            ):

                difference = abs(
                    (
                        fd_date.date()
                        - api_date.date()
                    ).days
                )

                if difference > 1:
                    continue

            fd_home = candidate.get(
                "homeTeam",
                {}
            ).get(
                "name",
                ""
            )

            fd_away = candidate.get(
                "awayTeam",
                {}
            ).get(
                "name",
                ""
            )

            # ------------------------------------------------
            # ORIENTACIÓN NORMAL
            # ------------------------------------------------

            straight_score = (
                team_similarity(
                    home,
                    fd_home
                )
                +
                team_similarity(
                    away,
                    fd_away
                )
            ) / 2

            # ------------------------------------------------
            # ORIENTACIÓN INVERTIDA
            # ------------------------------------------------

            swapped_score = (
                team_similarity(
                    home,
                    fd_away
                )
                +
                team_similarity(
                    away,
                    fd_home
                )
            ) / 2

            if (
                straight_score
                >= swapped_score
            ):

                score = (
                    straight_score
                )

                orientation = (
                    "NORMAL"
                )

            else:

                score = (
                    swapped_score
                )

                orientation = (
                    "INVERTIDO"
                )

            if score > best_score:

                best_score = score
                best_match = candidate
                best_orientation = orientation

        # ----------------------------------------------------
        # CLASIFICACIÓN
        # ----------------------------------------------------

        if best_match is None:

            status = "NO_MATCH"

            not_matched += 1

            fd_home = ""
            fd_away = ""
            fd_date_text = ""
            fd_status = ""

        else:

            fd_home = best_match.get(
                "homeTeam",
                {}
            ).get(
                "name",
                ""
            )

            fd_away = best_match.get(
                "awayTeam",
                {}
            ).get(
                "name",
                ""
            )

            fd_date_text = best_match.get(
                "utcDate",
                ""
            )

            fd_status = best_match.get(
                "status",
                ""
            )

            # -----------------------------------------------
            # UMBRALES
            # -----------------------------------------------

            if best_score >= 0.82:

                status = "VERIFICADO"
                verified += 1

            elif best_score >= 0.70:

                status = "REVISAR"
                review += 1

            else:

                status = "NO_MATCH"
                not_matched += 1

        # ----------------------------------------------------
        # GUARDAR RESULTADO
        # ----------------------------------------------------

        results.append(
            {
                "fixture_id":
                    fixture_id,

                "competition":
                    row[
                        "competition"
                    ],

                "fdorg_code":
                    code,

                "api_home":
                    home,

                "api_away":
                    away,

                "api_date":
                    (
                        api_date.isoformat()
                        if api_date
                        else ""
                    ),

                "fdorg_home":
                    fd_home,

                "fdorg_away":
                    fd_away,

                "fdorg_date":
                    fd_date_text,

                "fdorg_status":
                    fd_status,

                "similarity":
                    round(
                        best_score,
                        3
                    ),

                "orientation":
                    best_orientation,

                "validation":
                    status,
            }
        )

        # ----------------------------------------------------
        # MOSTRAR EN TERMINAL
        # ----------------------------------------------------

        print()
        print(
            f"{home} vs {away}"
        )

        print(
            f"→ {status}"
        )

        print(
            f"Similitud: "
            f"{best_score:.1%}"
        )

        if best_match:

            print(
                f"football-data.org: "
                f"{fd_home} vs "
                f"{fd_away}"
            )

            print(
                f"Estado: "
                f"{fd_status}"
            )

            print(
                f"Orientación: "
                f"{best_orientation}"
            )

    # ========================================================
    # GUARDAR CSV
    # ========================================================

    output_df = pd.DataFrame(
        results
    )

    output_df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # RESUMEN
    # ========================================================

    print()
    print("=" * 72)
    print("RESULTADO FINAL")
    print("=" * 72)

    print()

    print(
        f"VERIFICADOS: "
        f"{verified}"
    )

    print(
        f"REVISAR: "
        f"{review}"
    )

    print(
        f"NO MATCH: "
        f"{not_matched}"
    )

    print()

    print(
        f"Total procesado: "
        f"{len(results)}"
    )

    print()

    print(
        "Solicitudes API realizadas: 0"
    )

    print()

    print(
        "Informe guardado en:"
    )

    print(
        OUTPUT_FILE
    )

    print()
    print("=" * 72)


# ============================================================
# EJECUTAR
# ============================================================

if __name__ == "__main__":
    main()