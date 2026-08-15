import json
from pathlib import Path


# ============================================================
# CONFIGURACIÓN
# ============================================================

ROOT_DIR = Path(__file__).resolve().parents[2]

FDORG_DIR = (
    ROOT_DIR
    / "data"
    / "fdorg_matches"
)


# ============================================================
# CLAVE PARA EVITAR PARTIDOS DUPLICADOS
# ============================================================

def build_match_key(match):
    """
    Genera una clave única para evitar que
    un mismo partido aparezca dos veces.
    """

    match_id = match.get("id")

    if match_id is not None:
        return (
            "id",
            str(match_id)
        )

    utc_date = match.get(
        "utcDate",
        ""
    )

    home = (
        match
        .get("homeTeam", {})
        .get("id")
    )

    away = (
        match
        .get("awayTeam", {})
        .get("id")
    )

    return (
        "fallback",
        str(utc_date),
        str(home),
        str(away)
    )


# ============================================================
# LEER UN ARCHIVO
# ============================================================

def load_match_file(file_path):
    """
    Lee uno de los JSON descargados desde
    football-data.org.
    """

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
# CARGAR TODO EL HISTÓRICO DISPONIBLE
# ============================================================

def load_competition_history(code):
    """
    Combina todos los archivos locales existentes
    de una competición.

    Ejemplo PPL:

    PPL_matches.json
    PPL_2025_matches.json

    Si en el futuro añadimos:
    PPL_2024_matches.json

    también lo utilizará automáticamente.
    """

    code = str(
        code
    ).strip().upper()

    # --------------------------------------------------------
    # ARCHIVO DE TEMPORADA ACTUAL
    # --------------------------------------------------------

    current_file = (
        FDORG_DIR
        / f"{code}_matches.json"
    )

    # --------------------------------------------------------
    # ARCHIVOS HISTÓRICOS
    # --------------------------------------------------------

    historical_files = sorted(
        FDORG_DIR.glob(
            f"{code}_*_matches.json"
        )
    )

    files = []

    if current_file.exists():
        files.append(
            current_file
        )

    for file_path in historical_files:

        if file_path not in files:
            files.append(
                file_path
            )

    if not files:

        raise RuntimeError(
            f"No existen archivos históricos "
            f"para {code}"
        )

    # --------------------------------------------------------
    # COMBINAR
    # --------------------------------------------------------

    matches_by_key = {}

    for file_path in files:

        matches = load_match_file(
            file_path
        )

        for match in matches:

            key = build_match_key(
                match
            )

            matches_by_key[
                key
            ] = match

    matches = list(
        matches_by_key.values()
    )

    # --------------------------------------------------------
    # ORDENAR CRONOLÓGICAMENTE
    # --------------------------------------------------------

    matches.sort(
        key=lambda match:
            match.get(
                "utcDate",
                ""
            )
    )

    return {
        "competition":
            code,

        "matches":
            matches,

        "files":
            [
                file_path.name
                for file_path in files
            ],

        "file_count":
            len(files),

        "match_count":
            len(matches),
    }