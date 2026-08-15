import math
import unicodedata


# ============================================================
# UTILIDADES
# ============================================================

def normalize_text(value):
    """
    Normaliza nombres y textos procedentes
    de diferentes casas de apuestas.
    """

    text = str(value).strip().lower()

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

    return " ".join(
        text.split()
    )


def fair_odds(probability):
    """
    Cuota justa según la probabilidad del modelo.
    """

    if probability <= 0:
        return None

    return 1 / probability


def implied_probability(decimal_odds):
    """
    Probabilidad break-even de una cuota decimal.
    """

    if decimal_odds <= 0:
        return None

    return 1 / decimal_odds


def expected_value(
    probability,
    decimal_odds
):
    """
    EV por unidad apostada.

    Ejemplo:
    0.80 * 1.40 - 1 = +0.12
    = +12 %
    """

    return (
        probability
        * decimal_odds
        - 1
    )


# ============================================================
# MERCADOS SOPORTADOS
# ============================================================

def get_api_market(signal_market):

    signal_market = str(
        signal_market
    ).strip().upper()

    mapping = {
        "1X":
            "double_chance",

        "X2":
            "double_chance",

        "AWAY_SCORES":
            "team_totals",
    }

    return mapping.get(
        signal_market
    )


# ============================================================
# IDENTIFICAR OUTCOME
# ============================================================

def is_double_chance_target(
    outcome_name,
    signal_market,
    event_home,
    event_away
):

    outcome = normalize_text(
        outcome_name
    )

    home = normalize_text(
        event_home
    )

    away = normalize_text(
        event_away
    )

    signal_market = str(
        signal_market
    ).strip().upper()

    # --------------------------------------------------------
    # 1X
    # --------------------------------------------------------

    if signal_market == "1X":

        return (
            home in outcome
            and
            "draw" in outcome
        )

    # --------------------------------------------------------
    # X2
    # --------------------------------------------------------

    if signal_market == "X2":

        return (
            away in outcome
            and
            "draw" in outcome
        )

    return False


# ============================================================
# EXTRAER CUOTAS DOUBLE CHANCE
# ============================================================

def extract_double_chance_prices(
    odds_data,
    signal_market
):

    event_home = odds_data.get(
        "home_team",
        ""
    )

    event_away = odds_data.get(
        "away_team",
        ""
    )

    prices = []

    for bookmaker in odds_data.get(
        "bookmakers",
        []
    ):

        bookmaker_name = bookmaker.get(
            "title",
            "?"
        )

        bookmaker_key = bookmaker.get(
            "key",
            ""
        )

        for market in bookmaker.get(
            "markets",
            []
        ):

            if (
                market.get("key")
                != "double_chance"
            ):
                continue

            for outcome in market.get(
                "outcomes",
                []
            ):

                outcome_name = outcome.get(
                    "name",
                    ""
                )

                if not is_double_chance_target(
                    outcome_name=
                        outcome_name,

                    signal_market=
                        signal_market,

                    event_home=
                        event_home,

                    event_away=
                        event_away
                ):
                    continue

                try:

                    price = float(
                        outcome["price"]
                    )

                except (
                    KeyError,
                    TypeError,
                    ValueError
                ):

                    continue

                prices.append(
                    {
                        "bookmaker":
                            bookmaker_name,

                        "bookmaker_key":
                            bookmaker_key,

                        "outcome":
                            outcome_name,

                        "odds":
                            price,

                        "last_update":
                            market.get(
                                "last_update",
                                ""
                            ),
                    }
                )

    return prices


# ============================================================
# EVALUAR PRECIOS
# ============================================================

def evaluate_prices(
    model_probability,
    prices
):

    evaluations = []

    for item in prices:

        decimal_odds = float(
            item["odds"]
        )

        implied = implied_probability(
            decimal_odds
        )

        edge = (
            model_probability
            - implied
        )

        ev = expected_value(
            probability=
                model_probability,

            decimal_odds=
                decimal_odds
        )

        evaluation = dict(
            item
        )

        evaluation.update(
            {
                "implied_probability":
                    implied,

                "edge":
                    edge,

                "ev":
                    ev,
            }
        )

        evaluations.append(
            evaluation
        )

    return evaluations


# ============================================================
# MOTOR PRINCIPAL
# ============================================================

def evaluate_value_candidate(
    signal_market,
    model_probability_pct,
    odds_data
):
    """
    Evalúa una señal de CulebrIA contra
    las cuotas reales disponibles.

    IMPORTANTE:
    POSITIVE_EV_RAW todavía NO significa
    apuesta aprobada.

    Un EV positivo tendrá que pasar
    posteriormente por validación del mercado
    sin vig y filtros adicionales.
    """

    signal_market = str(
        signal_market
    ).strip().upper()

    model_probability = (
        float(
            model_probability_pct
        )
        / 100
    )

    api_market = get_api_market(
        signal_market
    )

    # --------------------------------------------------------
    # MERCADO NO SOPORTADO
    # --------------------------------------------------------

    if api_market is None:

        return {
            "status":
                "BLOCKED_MARKET",

            "reason":
                "Mercado no soportado.",

            "api_market":
                None,

            "model_probability":
                model_probability,

            "model_fair_odds":
                fair_odds(
                    model_probability
                ),

            "prices":
                [],
        }

    # --------------------------------------------------------
    # TEAM TOTALS
    # --------------------------------------------------------

    if signal_market == "AWAY_SCORES":

        return {
            "status":
                "NEEDS_MARKET_STRUCTURE",

            "reason":
                (
                    "Necesitamos inspeccionar "
                    "un JSON real de team_totals "
                    "antes de interpretar este mercado."
                ),

            "api_market":
                api_market,

            "model_probability":
                model_probability,

            "model_fair_odds":
                fair_odds(
                    model_probability
                ),

            "prices":
                [],
        }

    # --------------------------------------------------------
    # DOUBLE CHANCE
    # --------------------------------------------------------

    prices = extract_double_chance_prices(
        odds_data=
            odds_data,

        signal_market=
            signal_market
    )

    if not prices:

        return {
            "status":
                "NO_ODDS",

            "reason":
                (
                    "No se encontró una cuota "
                    "correspondiente al mercado."
                ),

            "api_market":
                api_market,

            "model_probability":
                model_probability,

            "model_fair_odds":
                fair_odds(
                    model_probability
                ),

            "prices":
                [],
        }

    evaluations = evaluate_prices(
        model_probability=
            model_probability,

        prices=
            prices
    )

    best = max(
        evaluations,
        key=lambda item:
            item["odds"]
    )

    best_odds = float(
        best["odds"]
    )

    best_ev = float(
        best["ev"]
    )

    best_edge = float(
        best["edge"]
    )

    break_even = float(
        best[
            "implied_probability"
        ]
    )

    model_fair = fair_odds(
        model_probability
    )

    # --------------------------------------------------------
    # CLASIFICACIÓN
    # --------------------------------------------------------

    if best_ev <= 0:

        status = (
            "NO_BET_PRICE"
        )

        reason = (
            "La mejor cuota disponible "
            "no supera la cuota justa "
            "del modelo."
        )

    else:

        status = (
            "NEEDS_VIG_CHECK"
        )

        reason = (
            "Existe EV bruto positivo. "
            "Falta comparar contra una "
            "probabilidad de mercado sin vig."
        )

    return {
        "status":
            status,

        "reason":
            reason,

        "api_market":
            api_market,

        "model_probability":
            model_probability,

        "model_fair_odds":
            model_fair,

        "best_bookmaker":
            best[
                "bookmaker"
            ],

        "best_bookmaker_key":
            best[
                "bookmaker_key"
            ],

        "best_outcome":
            best[
                "outcome"
            ],

        "best_odds":
            best_odds,

        "break_even_probability":
            break_even,

        "raw_edge":
            best_edge,

        "raw_ev":
            best_ev,

        "last_update":
            best[
                "last_update"
            ],

        "prices":
            evaluations,
    }