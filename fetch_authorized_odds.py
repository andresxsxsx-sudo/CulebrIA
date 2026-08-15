import json
import os

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from dotenv import load_dotenv


# ============================================================
# CONFIGURACIÓN
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"

PLAN_FILE = (
    DATA_DIR
    / "paid_odds_plan.csv"
)

ODDS_RAW_DIR = (
    DATA_DIR
    / "odds_raw"
)

ARCHIVE_DIR = (
    ODDS_RAW_DIR
    / "archive"
)

REPORT_FILE = (
    DATA_DIR
    / "paid_odds_fetch_report.csv"
)


# ============================================================
# SEGURIDAD DE CRÉDITOS
#
# Aunque hubiese 20 señales, este script JAMÁS
# hará más de 4 llamadas en una ejecución.
# ============================================================

MAX_REQUESTS_PER_RUN = 4

REGIONS = "eu"
ODDS_FORMAT = "decimal"
DATE_FORMAT = "iso"

TIMEOUT_SECONDS = 20

BASE_URL = (
    "https://api.the-odds-api.com/v4"
)


# ============================================================
# UTILIDADES
# ============================================================

def utc_now():

    return datetime.now(
        timezone.utc
    )


def utc_file_stamp():

    return (
        utc_now()
        .strftime(
            "%Y%m%dT%H%M%SZ"
        )
    )


def is_authorized(value):

    if isinstance(
        value,
        bool
    ):

        return value

    text = str(
        value
    ).strip().lower()

    return text in {
        "true",
        "1",
        "yes",
        "si",
        "sí",
    }


def grade_priority(value):

    grade = str(
        value
    ).strip().upper()

    priorities = {
        "A": 0,
        "B": 1,
        "C": 2,
        "D": 3,
    }

    return priorities.get(
        grade,
        99
    )


# ============================================================
# GUARDAR JSON
# ============================================================

def save_json(
    path,
    data
):

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 90)
    print(
        "CulebrIA - AUTHORIZED ODDS FETCHER"
    )
    print("=" * 90)

    print()
    print(
        f"Límite duro por ejecución: "
        f"{MAX_REQUESTS_PER_RUN} llamadas"
    )

    # --------------------------------------------------------
    # PLAN
    # --------------------------------------------------------

    if not PLAN_FILE.exists():

        print()
        print(
            "❌ No existe:"
        )

        print(
            PLAN_FILE
        )

        return

    plan = pd.read_csv(
        PLAN_FILE
    )

    if plan.empty:

        print()
        print(
            "No existen señales en el plan."
        )

        print()
        print(
            "Solicitudes API realizadas: 0"
        )

        print(
            "Créditos utilizados: 0"
        )

        return

    # --------------------------------------------------------
    # AUTORIZADAS
    # --------------------------------------------------------

    plan[
        "_authorized"
    ] = plan[
        "authorized"
    ].apply(
        is_authorized
    )

    authorized = plan[
        plan[
            "_authorized"
        ]
    ].copy()

    print()
    print(
        f"Filas del plan: "
        f"{len(plan)}"
    )

    print(
        f"Señales autorizadas: "
        f"{len(authorized)}"
    )

    # ========================================================
    # SI NO HAY NADA, PARAMOS ANTES DE LEER LA API KEY
    # ========================================================

    if authorized.empty:

        print()
        print(
            "✅ No hay consultas de cuotas autorizadas."
        )

        print(
            "The Odds API NO será consultada."
        )

        print()
        print(
            "Solicitudes API realizadas: 0"
        )

        print(
            "Créditos utilizados: 0"
        )

        return

    # ========================================================
    # PRIORIZAR
    #
    # Grade A primero.
    # Después mayor probabilidad del modelo.
    # ========================================================

    authorized[
        "_grade_priority"
    ] = authorized[
        "grade"
    ].apply(
        grade_priority
    )

    authorized[
        "_probability"
    ] = pd.to_numeric(
        authorized[
            "model_probability_pct"
        ],
        errors="coerce"
    ).fillna(
        0
    )

    authorized = (
        authorized
        .sort_values(
            [
                "_grade_priority",
                "_probability",
            ],
            ascending=[
                True,
                False,
            ]
        )
    )

    # --------------------------------------------------------
    # EVITAR PEDIR DOS VECES EL MISMO
    # EVENTO + MERCADO API
    # --------------------------------------------------------

    authorized = (
        authorized
        .drop_duplicates(
            subset=[
                "event_id",
                "api_market",
            ],
            keep="first"
        )
        .reset_index(
            drop=True
        )
    )

    total_unique = len(
        authorized
    )

    print(
        f"Consultas únicas autorizadas: "
        f"{total_unique}"
    )

    # --------------------------------------------------------
    # LÍMITE DURO
    # --------------------------------------------------------

    selected = authorized.head(
        MAX_REQUESTS_PER_RUN
    ).copy()

    if total_unique > MAX_REQUESTS_PER_RUN:

        print()
        print(
            "⚠️ Hay más candidatos que el "
            "límite permitido."
        )

        print(
            f"Solo se consultarán los "
            f"{MAX_REQUESTS_PER_RUN} prioritarios."
        )

    # ========================================================
    # API KEY
    # ========================================================

    load_dotenv(
        ROOT_DIR
        / ".env"
    )

    api_key = os.getenv(
        "THE_ODDS_API_KEY"
    )

    if not api_key:

        print()
        print(
            "❌ THE_ODDS_API_KEY no encontrada "
            "en .env"
        )

        return

    # ========================================================
    # CARPETAS
    # ========================================================

    ODDS_RAW_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    ARCHIVE_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # ========================================================
    # CONTADORES
    # ========================================================

    requests_made = 0

    credits_last_total = 0

    successful = 0
    failed = 0

    report_rows = []

    # ========================================================
    # CONSULTAR
    # ========================================================

    for _, row in selected.iterrows():

        sport_key = str(
            row[
                "sport_key"
            ]
        ).strip()

        event_id = str(
            row[
                "event_id"
            ]
        ).strip()

        api_market = str(
            row[
                "api_market"
            ]
        ).strip()

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

        signal_market = str(
            row[
                "market"
            ]
        ).upper()

        print()
        print("-" * 90)

        print(
            f"{home} vs {away}"
        )

        print(
            f"Señal CulebrIA: "
            f"{signal_market}"
        )

        print(
            f"Mercado API: "
            f"{api_market}"
        )

        # ====================================================
        # PROTECCIÓN EXTRA
        # ====================================================

        if requests_made >= MAX_REQUESTS_PER_RUN:

            print(
                "⛔ Límite duro alcanzado."
            )

            break

        url = (
            f"{BASE_URL}"
            f"/sports/"
            f"{sport_key}"
            f"/events/"
            f"{event_id}"
            f"/odds"
        )

        params = {
            "apiKey":
                api_key,

            "regions":
                REGIONS,

            "markets":
                api_market,

            "oddsFormat":
                ODDS_FORMAT,

            "dateFormat":
                DATE_FORMAT,
        }

        request_time = (
            utc_now()
            .replace(
                microsecond=0
            )
            .isoformat()
        )

        try:

            response = requests.get(
                url,
                params=params,
                timeout=TIMEOUT_SECONDS
            )

            requests_made += 1

        except requests.RequestException as error:

            failed += 1

            print(
                f"❌ Error de conexión: "
                f"{error}"
            )

            report_rows.append(
                {
                    "event_id":
                        event_id,

                    "home":
                        home,

                    "away":
                        away,

                    "signal_market":
                        signal_market,

                    "api_market":
                        api_market,

                    "request_time_utc":
                        request_time,

                    "http_status":
                        "",

                    "success":
                        False,

                    "credits_last":
                        "",

                    "credits_used":
                        "",

                    "credits_remaining":
                        "",

                    "saved_file":
                        "",

                    "error":
                        str(
                            error
                        ),
                }
            )

            continue

        # ====================================================
        # HEADERS DE CRÉDITOS
        # ====================================================

        credits_last = response.headers.get(
            "x-requests-last"
        )

        credits_used = response.headers.get(
            "x-requests-used"
        )

        credits_remaining = response.headers.get(
            "x-requests-remaining"
        )

        try:

            credits_last_number = int(
                credits_last
            )

        except (
            TypeError,
            ValueError
        ):

            credits_last_number = 0

        credits_last_total += (
            credits_last_number
        )

        print(
            f"HTTP: "
            f"{response.status_code}"
        )

        print(
            f"Coste última llamada: "
            f"{credits_last}"
        )

        print(
            f"Créditos usados: "
            f"{credits_used}"
        )

        print(
            f"Créditos restantes: "
            f"{credits_remaining}"
        )

        # ====================================================
        # ERROR HTTP
        # ====================================================

        if response.status_code != 200:

            failed += 1

            try:

                error_data = (
                    response.json()
                )

                error_text = json.dumps(
                    error_data,
                    ensure_ascii=False
                )

            except ValueError:

                error_text = (
                    response.text[
                        :500
                    ]
                )

            print(
                f"❌ Respuesta API: "
                f"{error_text}"
            )

            report_rows.append(
                {
                    "event_id":
                        event_id,

                    "home":
                        home,

                    "away":
                        away,

                    "signal_market":
                        signal_market,

                    "api_market":
                        api_market,

                    "request_time_utc":
                        request_time,

                    "http_status":
                        response.status_code,

                    "success":
                        False,

                    "credits_last":
                        credits_last,

                    "credits_used":
                        credits_used,

                    "credits_remaining":
                        credits_remaining,

                    "saved_file":
                        "",

                    "error":
                        error_text,
                }
            )

            continue

        # ====================================================
        # JSON
        # ====================================================

        try:

            data = response.json()

        except ValueError:

            failed += 1

            print(
                "❌ La respuesta no contiene JSON válido."
            )

            continue

        # ====================================================
        # GUARDAR ARCHIVO ACTUAL
        #
        # Mantiene compatibilidad con los scripts
        # que ya construimos.
        # ====================================================

        latest_file = (
            ODDS_RAW_DIR
            / (
                f"{event_id}_"
                f"{api_market}.json"
            )
        )

        save_json(
            latest_file,
            data
        )

        # ====================================================
        # ARCHIVO HISTÓRICO
        #
        # Nunca sobrescribe snapshots anteriores.
        # ====================================================

        archive_file = (
            ARCHIVE_DIR
            / (
                f"{event_id}_"
                f"{api_market}_"
                f"{utc_file_stamp()}.json"
            )
        )

        save_json(
            archive_file,
            data
        )

        successful += 1

        bookmaker_count = len(
            data.get(
                "bookmakers",
                []
            )
        ) if isinstance(
            data,
            dict
        ) else 0

        print(
            f"✅ Cuotas guardadas."
        )

        print(
            f"Bookmakers recibidos: "
            f"{bookmaker_count}"
        )

        print(
            f"Archivo: "
            f"{latest_file.name}"
        )

        report_rows.append(
            {
                "event_id":
                    event_id,

                "home":
                    home,

                "away":
                    away,

                "signal_market":
                    signal_market,

                "api_market":
                    api_market,

                "request_time_utc":
                    request_time,

                "http_status":
                    response.status_code,

                "success":
                    True,

                "credits_last":
                    credits_last,

                "credits_used":
                    credits_used,

                "credits_remaining":
                    credits_remaining,

                "saved_file":
                    str(
                        latest_file
                    ),

                "archive_file":
                    str(
                        archive_file
                    ),

                "bookmakers":
                    bookmaker_count,

                "error":
                    "",
            }
        )

    # ========================================================
    # REPORTE
    # ========================================================

    if report_rows:

        pd.DataFrame(
            report_rows
        ).to_csv(
            REPORT_FILE,
            index=False,
            encoding="utf-8-sig"
        )

    # ========================================================
    # FINAL
    # ========================================================

    print()
    print("=" * 90)
    print(
        "RESULTADO FINAL"
    )
    print("=" * 90)

    print()

    print(
        f"Solicitudes API realizadas: "
        f"{requests_made}"
    )

    print(
        f"Respuestas correctas: "
        f"{successful}"
    )

    print(
        f"Errores: "
        f"{failed}"
    )

    print(
        f"Créditos consumidos "
        f"según x-requests-last: "
        f"{credits_last_total}"
    )

    print()

    if requests_made == 0:

        print(
            "✅ No se consumieron créditos."
        )

    print()

    print(
        "IMPORTANTE:"
    )

    print(
        "Los valores definitivos de cuota "
        "y EV todavía serán evaluados "
        "por el Value Engine."
    )


if __name__ == "__main__":
    main()