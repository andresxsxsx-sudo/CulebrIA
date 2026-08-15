def normalize_yes_no(value):
    """
    Convierte valores SI/NO del CSV a booleano.
    """

    if isinstance(value, bool):
        return value

    value = str(value).strip().upper()

    return value == "SI"


def classify_market_eligibility(row):
    """
    Clasifica una competición según los datos
    disponibles para los mercados iniciales
    de CulebrIA.
    """

    grade = str(
        row.get("Nivel", "")
    ).strip().upper()

    fixture_stats = normalize_yes_no(
        row.get(
            "Estadisticas_partido",
            "NO"
        )
    )

    standings = normalize_yes_no(
        row.get(
            "Clasificacion",
            "NO"
        )
    )

    lineups = normalize_yes_no(
        row.get(
            "Alineaciones",
            "NO"
        )
    )

    injuries = normalize_yes_no(
        row.get(
            "Lesiones",
            "NO"
        )
    )

    odds = normalize_yes_no(
        row.get(
            "Odds",
            "NO"
        )
    )

    # ------------------------------------------
    # NIVEL CORE
    # ------------------------------------------

    # Queremos datos suficientes para construir
    # modelos básicos de equipos y goles.

    if (
        fixture_stats
        and standings
        and grade in {"A", "B"}
    ):

        status = "CORE"

    # ------------------------------------------
    # NIVEL CONTEXTUAL
    # ------------------------------------------

    elif (
        fixture_stats
        and grade == "C"
    ):

        status = "CONTEXTUAL"

    # ------------------------------------------
    # DESCARTADO
    # ------------------------------------------

    else:

        status = "DESCARTADO"

    return {
        "status": status,
        "fixture_stats": fixture_stats,
        "standings": standings,
        "lineups": lineups,
        "injuries": injuries,
        "odds_signal": odds,
    }