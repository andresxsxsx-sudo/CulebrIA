import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


# ============================================================
# CULEBRIA - CONTROLADOR DIARIO
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"

POISSON_FILE = DATA_DIR / "poisson_predictions.csv"
GATE_FILE = DATA_DIR / "reliability_gate_signals.csv"
PREMATCH_FILE = DATA_DIR / "prematch_odds_candidates.csv"
PLAN_FILE = DATA_DIR / "paid_odds_plan.csv"
VALUE_FILE = DATA_DIR / "value_candidates.csv"
LEDGER_FILE = (
    DATA_DIR
    / "prospective"
    / "prospective_ledger.csv"
)


# ============================================================
# FLUJO DIARIO
# ============================================================

STAGES = [
    (
        "1. Obtener y filtrar partidos",
        "main.py",
    ),

    (
        "2. Evaluar calidad de competiciones",
        "build_quality_candidates.py",
    ),

    (
        "3. Construir mercado CORE",
        "build_market_pool.py",
    ),

    (
        "4. Cruzar football-data.org",
        "cross_fdorg_core.py",
    ),

    (
        "5. Actualizar históricos",
        "download_fdorg_core_matches.py",
    ),

    (
        "6. Validar partidos entre fuentes",
        "validate_core_cross_source.py",
    ),

    (
        "7. Construir estadísticas",
        "build_team_stats.py",
    ),

    (
        "8. Ejecutar Poisson V1 RAW",
        "build_poisson_predictions.py",
    ),

    (
        "9. Aplicar Reliability Gate",
        "build_reliability_gate.py",
    ),

    (
        "10. Localizar eventos de cuotas",
        "match_odds_events.py",
    ),

    (
        "11. Filtrar únicamente PREMATCH",
        "inspect_prematch_odds_candidates.py",
    ),

    (
        "12. Planificar consultas de cuotas",
        "plan_paid_odds.py",
    ),

    (
        "13. Consultar cuotas autorizadas",
        "fetch_authorized_odds.py",
    ),

    (
        "14. Evaluar valor",
        "build_value_candidates.py",
    ),

    (
        "15. Guardar snapshots prospectivos",
        "build_prospective_snapshots.py",
    ),

    (
        "16. Liquidar resultados disponibles",
        "settle_prospective_ledger.py",
    ),
]


# ============================================================
# EJECUTAR UN SCRIPT
# ============================================================

def run_script(
    title,
    script_name,
):

    script_path = (
        ROOT_DIR
        / script_name
    )

    print()
    print("=" * 90)

    print(
        title
    )

    print("=" * 90)

    if not script_path.exists():

        print()
        print(
            "❌ No existe:"
        )

        print(
            script_path
        )

        return False

    result = subprocess.run(
        [
            sys.executable,
            str(
                script_path
            ),
        ],
        cwd=str(
            ROOT_DIR
        ),
    )

    if result.returncode != 0:

        print()
        print(
            "❌ ERROR EN:"
        )

        print(
            script_name
        )

        print(
            f"Código de salida: "
            f"{result.returncode}"
        )

        return False

    print()
    print(
        "✅ Paso completado:"
    )

    print(
        script_name
    )

    return True


# ============================================================
# LEER CSV DE FORMA SEGURA
# ============================================================

def read_csv_safe(
    path,
):

    if not path.exists():

        return pd.DataFrame()

    if path.stat().st_size == 0:

        return pd.DataFrame()

    try:

        return pd.read_csv(
            path
        )

    except (
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
        OSError,
    ):

        return pd.DataFrame()


# ============================================================
# COMPROBAR SI UN CSV TIENE FILAS
# ============================================================

def csv_has_rows(
    path,
):

    df = read_csv_safe(
        path
    )

    return not df.empty


# ============================================================
# CONVERTIR BOOLEANO DESDE CSV
# ============================================================

def csv_boolean(
    value,
):

    if isinstance(
        value,
        bool
    ):

        return value

    return (
        str(
            value
        )
        .strip()
        .lower()
        in {
            "true",
            "1",
            "yes",
            "si",
            "sí",
        }
    )


# ============================================================
# CONTAR CONSULTAS DE CUOTAS AUTORIZADAS
# ============================================================

def count_authorized_odds():

    df = read_csv_safe(
        PLAN_FILE
    )

    if (
        df.empty
        or
        "authorized"
        not in df.columns
    ):

        return 0

    authorized = (
        df[
            "authorized"
        ]
        .apply(
            csv_boolean
        )
    )

    return int(
        authorized.sum()
    )


# ============================================================
# CONTAR CANDIDATOS CON EV BRUTO POSITIVO
# ============================================================

def count_positive_value_candidates():

    df = read_csv_safe(
        VALUE_FILE
    )

    if (
        df.empty
        or
        "status"
        not in df.columns
    ):

        return 0

    statuses = (
        df[
            "status"
        ]
        .fillna(
            ""
        )
        .astype(
            str
        )
        .str.upper()
    )

    return int(
        (
            statuses
            ==
            "NEEDS_VIG_CHECK"
        ).sum()
    )


# ============================================================
# MOSTRAR NO BET
# ============================================================

def print_no_bet(
    reason,
    detail=None,
):

    print()
    print()

    print("=" * 90)

    print(
        "🐍 CULEBRIA - RESULTADO DEL DÍA"
    )

    print("=" * 90)

    print()

    print(
        "⛔ NO BET"
    )

    print()

    print(
        f"Motivo: "
        f"{reason}"
    )

    if detail:

        print(
            detail
        )

    print()

    print(
        "CulebrIA no bajará sus criterios "
        "solo para generar una apuesta."
    )

    print(
        "Parlay objetivo: exactamente "
        "2 eventos de partidos distintos."
    )

    print(
        "Cuota combinada mínima: 2.00"
    )

    print("=" * 90)


# ============================================================
# MOSTRAR ERROR DEL PIPELINE
# ============================================================

def print_pipeline_error(
    script_name,
):

    print()
    print("=" * 90)

    print(
        "❌ CULEBRIA DETENIDA"
    )

    print("=" * 90)

    print()

    print(
        "El problema apareció en:"
    )

    print(
        script_name
    )

    print()

    print(
        "No se ejecutarán los pasos "
        "posteriores hasta corregirlo."
    )


# ============================================================
# RESUMEN FINAL
# ============================================================

def final_summary():

    plan_df = read_csv_safe(
        PLAN_FILE
    )

    value_df = read_csv_safe(
        VALUE_FILE
    )

    ledger_df = read_csv_safe(
        LEDGER_FILE
    )

    # --------------------------------------------------------
    # PLAN DE CUOTAS
    # --------------------------------------------------------

    signals = len(
        plan_df
    )

    if (
        not plan_df.empty
        and
        "authorized"
        in plan_df.columns
    ):

        authorized_mask = (
            plan_df[
                "authorized"
            ]
            .apply(
                csv_boolean
            )
        )

        authorized_df = (
            plan_df[
                authorized_mask
            ]
            .copy()
        )

    else:

        authorized_df = (
            pd.DataFrame()
        )

    authorized = len(
        authorized_df
    )

    if (
        not authorized_df.empty
        and
        {
            "event_id",
            "api_market",
        }.issubset(
            authorized_df.columns
        )
    ):

        unique_requests = (
            authorized_df[
                [
                    "event_id",
                    "api_market",
                ]
            ]
            .drop_duplicates()
            .shape[
                0
            ]
        )

    else:

        unique_requests = 0

    # --------------------------------------------------------
    # VALUE ENGINE
    # --------------------------------------------------------

    if (
        not value_df.empty
        and
        "status"
        in value_df.columns
    ):

        statuses = (
            value_df[
                "status"
            ]
            .fillna(
                ""
            )
            .astype(
                str
            )
            .str.upper()
        )

        no_bet_price = int(
            (
                statuses
                ==
                "NO_BET_PRICE"
            ).sum()
        )

        needs_vig = int(
            (
                statuses
                ==
                "NEEDS_VIG_CHECK"
            ).sum()
        )

    else:

        no_bet_price = 0
        needs_vig = 0

    # --------------------------------------------------------
    # LEDGER
    # --------------------------------------------------------

    if (
        not ledger_df.empty
        and
        "settled"
        in ledger_df.columns
    ):

        settled_values = (
            ledger_df[
                "settled"
            ]
            .fillna(
                "NO"
            )
            .astype(
                str
            )
            .str.upper()
        )

        settled = int(
            (
                settled_values
                ==
                "YES"
            ).sum()
        )

        pending = (
            len(
                ledger_df
            )
            -
            settled
        )

    else:

        settled = 0
        pending = 0

    # --------------------------------------------------------
    # MOSTRAR
    # --------------------------------------------------------

    print()
    print()

    print("=" * 90)

    print(
        "🐍 CULEBRIA - RESULTADO DEL DÍA"
    )

    print("=" * 90)

    print()

    print(
        "MODELO:"
    )

    print(
        "Poisson V1 RAW + Reliability Gate V1"
    )

    print()

    print(
        "POLÍTICA:"
    )

    print(
        "Mercados permitidos: "
        "1X / AWAY_SCORES"
    )

    print(
        "Parlay: exactamente "
        "2 eventos de partidos distintos"
    )

    print(
        "Cuota combinada mínima: 2.00"
    )

    print()

    print("-" * 90)

    print(
        f"Señales para cuotas:       "
        f"{signals}"
    )

    print(
        f"Señales autorizadas:       "
        f"{authorized}"
    )

    print(
        f"Consultas necesarias:      "
        f"{unique_requests}"
    )

    print()

    print(
        f"Evaluaciones de precio:    "
        f"{len(value_df)}"
    )

    print(
        f"NO BET por precio:         "
        f"{no_bet_price}"
    )

    print(
        f"Pendientes de vig:         "
        f"{needs_vig}"
    )

    print()

    print(
        f"Snapshots prospectivos:    "
        f"{len(ledger_df)}"
    )

    print(
        f"Pendientes de resultado:   "
        f"{pending}"
    )

    print(
        f"Liquidados:                "
        f"{settled}"
    )

    print("-" * 90)

    print()

    if needs_vig > 0:

        print(
            "🟡 HAY CANDIDATOS"
        )

        print()

        print(
            "Existe al menos una señal "
            "con EV bruto positivo."
        )

        print(
            "Todavía debe superar "
            "la validación final de vig"
        )

        print(
            "antes de poder formar "
            "un parlay aprobado."
        )

    else:

        print(
            "⛔ NO BET"
        )

        print()

        print(
            "No existen actualmente "
            "señales con precio suficiente"
        )

        print(
            "para pasar a la "
            "validación final."
        )

    print()

    print("=" * 90)


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    start_time = (
        datetime.now()
    )

    print()
    print("=" * 90)

    print(
        "🐍 CULEBRIA"
    )

    print(
        "ANÁLISIS DIARIO"
    )

    print("=" * 90)

    print()

    print(
        f"Inicio: "
        f"{start_time.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    print()

    print(
        "Modo: PRECISIÓN"
    )

    print(
        "Parlay: 2 eventos"
    )

    print(
        "Cuota combinada mínima: 2.00"
    )

    print()

    print(
        "Si no existe valor suficiente:"
    )

    print(
        "NO BET"
    )

    total_steps = len(
        STAGES
    )

    # ========================================================
    # EJECUTAR PIPELINE
    # ========================================================

    for index, (
        title,
        script_name,
    ) in enumerate(
        STAGES,
        start=1,
    ):

        full_title = (
            f"[{index}/{total_steps}] "
            f"{title}"
        )

        success = run_script(
            title=
                full_title,

            script_name=
                script_name,
        )

        # ----------------------------------------------------
        # ERROR REAL
        # ----------------------------------------------------

        if not success:

            print_pipeline_error(
                script_name
            )

            return

        # ====================================================
        # CORTE 1
        #
        # POISSON NO GENERÓ PREDICCIONES
        # ====================================================

        if (
            script_name
            ==
            "build_poisson_predictions.py"
        ):

            if not csv_has_rows(
                POISSON_FILE
            ):

                print_no_bet(
                    (
                        "No existen partidos "
                        "con muestra histórica "
                        "suficiente."
                    ),

                    (
                        "Poisson generó 0 predicciones. "
                        "No se ejecutará Reliability Gate "
                        "ni se consultarán cuotas."
                    ),
                )

                return

        # ====================================================
        # CORTE 2
        #
        # NINGUNA PREDICCIÓN SUPERA EL GATE
        # ====================================================

        if (
            script_name
            ==
            "build_reliability_gate.py"
        ):

            if not csv_has_rows(
                GATE_FILE
            ):

                print_no_bet(
                    (
                        "Ninguna predicción superó "
                        "el Reliability Gate."
                    ),

                    (
                        "No se consultarán cuotas."
                    ),
                )

                return

        # ====================================================
        # CORTE 3
        #
        # NO EXISTEN SEÑALES PREMATCH
        # ====================================================

        if (
            script_name
            ==
            "inspect_prematch_odds_candidates.py"
        ):

            if not csv_has_rows(
                PREMATCH_FILE
            ):

                print_no_bet(
                    (
                        "No existen señales válidas "
                        "PREMATCH en este momento."
                    ),

                    (
                        "No se consultarán cuotas."
                    ),
                )

                return

        # ====================================================
        # CORTE 4
        #
        # NO EXISTEN CONSULTAS DE CUOTAS AUTORIZADAS
        # ====================================================

        if (
            script_name
            ==
            "plan_paid_odds.py"
        ):

            authorized_count = (
                count_authorized_odds()
            )

            if authorized_count == 0:

                print_no_bet(
                    (
                        "No existe ninguna consulta "
                        "de cuotas autorizada."
                    ),

                    (
                        "Las señales fueron bloqueadas "
                        "por las reglas operativas "
                        "o los partidos ya no eran "
                        "válidos para análisis PREMATCH."
                    ),
                )

                return

        # ====================================================
        # VALUE ENGINE
        #
        # Si no hay EV bruto positivo, NO cortamos todavía.
        # Queremos permitir que el Prospective Tracker guarde
        # NO_BET_PRICE cuando corresponda.
        # ====================================================

        if (
            script_name
            ==
            "build_value_candidates.py"
        ):

            positive_candidates = (
                count_positive_value_candidates()
            )

            if positive_candidates == 0:

                pass

    # ========================================================
    # TODOS LOS PASOS TERMINARON
    # ========================================================

    final_summary()

    end_time = (
        datetime.now()
    )

    elapsed = (
        end_time
        -
        start_time
    )

    print()

    print(
        f"Tiempo total: "
        f"{elapsed}"
    )


if __name__ == "__main__":

    main()