from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


# ============================================================
# CULEBRIA - CONTROLADOR OPERATIVO FINAL
# ============================================================
#
# Flujo:
#   1) obtiene partidos
#   2) filtra calidad / CORE
#   3) cruza y valida football-data.org
#   4) audita muestra histórica
#   5) genera Poisson V1 RAW
#   6) aplica Reliability Gate
#   7) confirma PREMATCH
#   8) ejecuta culebria_operational.py
#   9) liquida resultados prospectivos anteriores
#
# IMPORTANTE:
# Ya NO ejecuta plan_paid_odds.py / fetch_authorized_odds.py /
# build_value_candidates.py antes del modo operativo. De este modo
# evitamos consultar cuotas dos veces en la misma ejecución.
# ============================================================


ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"

POISSON_FILE = DATA_DIR / "poisson_predictions.csv"
GATE_FILE = DATA_DIR / "reliability_gate_signals.csv"
PREMATCH_FILE = DATA_DIR / "prematch_odds_candidates.csv"

OPERATIONAL_FINAL_FILE = (
    DATA_DIR
    / "culebria_operational_final.json"
)


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
        "7. Auditar muestra histórica",
        "audit_model_samples.py",
    ),
    (
        "8. Construir estadísticas",
        "build_team_stats.py",
    ),
    (
        "9. Ejecutar Poisson V1 RAW",
        "build_poisson_predictions.py",
    ),
    (
        "10. Aplicar Reliability Gate",
        "build_reliability_gate.py",
    ),
    (
        "11. Localizar eventos de cuotas",
        "match_odds_events.py",
    ),
    (
        "12. Confirmar señales PREMATCH",
        "inspect_prematch_odds_candidates.py",
    ),
    (
        "13. Decisión operativa cuota 1.80+",
        "culebria_operational.py",
    ),
    (
        "14. Liquidar resultados anteriores",
        "settle_prospective_ledger.py",
    ),
    (
        "15. Liquidar parlays operativos",
        "settle_operational_parlays.py",
    ),
]


def run_script(title, script_name):
    path = ROOT_DIR / script_name

    print()
    print("=" * 92)
    print(title)
    print("=" * 92)

    if not path.exists():
        print(f"❌ No existe: {path}")
        return False

    result = subprocess.run(
        [
            sys.executable,
            str(path),
        ],
        cwd=str(ROOT_DIR),
    )

    if result.returncode != 0:
        print()
        print(f"❌ ERROR EN: {script_name}")
        print(
            f"Código de salida: "
            f"{result.returncode}"
        )
        return False

    # CULEBRIA_SAFE_NO_CORE_V1
    if script_name == "cross_fdorg_core.py":
        core_file = (
            ROOT_DIR
            / "data"
            / "fdorg_core_matches.csv"
        )

        no_core_covered = True

        try:
            if (
                core_file.exists()
                and core_file.stat().st_size > 0
            ):
                core_check = pd.read_csv(core_file)
                no_core_covered = core_check.empty
        except (
            pd.errors.EmptyDataError,
            pd.errors.ParserError,
            OSError,
        ):
            no_core_covered = True

        if no_core_covered:
            for stale_name in (
                "culebria_operational_final.json",
                "culebria_bet_confirmation.json",
            ):
                stale = (
                    ROOT_DIR
                    / "data"
                    / stale_name
                )
                try:
                    if stale.exists():
                        stale.unlink()
                except OSError:
                    pass

            print()
            print("=" * 90)
            print("⛔ NO BET — NO_CORE_COVERED")
            print(
                "Hoy no hay partidos CORE cubiertos "
                "por la segunda fuente football-data.org."
            )
            print(
                "No se bajan filtros y no se reutiliza "
                "ninguna decisión anterior."
            )
            print("=" * 90)
            raise SystemExit(0)

    print()
    print(f"✅ Paso completado: {script_name}")
    return True


def read_csv_safe(path):
    if (
        not path.exists()
        or path.stat().st_size == 0
    ):
        return pd.DataFrame()

    try:
        return pd.read_csv(path)
    except (
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
        OSError,
    ):
        return pd.DataFrame()


def csv_has_rows(path):
    return not read_csv_safe(path).empty


def print_no_bet(reason, detail=None):
    print()
    print("=" * 92)
    print("🐍 CULEBRIA - RESULTADO DEL DÍA")
    print("=" * 92)
    print()
    print("⛔ NO BET")
    print()
    print(f"Motivo: {reason}")

    if detail:
        print(detail)

    print()
    print(
        "CulebrIA no bajará sus criterios "
        "solo para generar una apuesta."
    )
    print(
        "Objetivo operativo: cuota 1.80+."
    )
    print("=" * 92)


def print_operational_summary():
    if not OPERATIONAL_FINAL_FILE.exists():
        print()
        print(
            "⚠️ No se encontró el archivo "
            "de decisión operativa final."
        )
        return

    try:
        data = json.loads(
            OPERATIONAL_FINAL_FILE.read_text(
                encoding="utf-8"
            )
        )
    except (
        json.JSONDecodeError,
        OSError,
    ):
        print()
        print(
            "⚠️ No se pudo leer la "
            "decisión operativa final."
        )
        return

    decision = str(
        data.get(
            "decision",
            "UNKNOWN",
        )
    ).upper()

    print()
    print("=" * 92)
    print("🐍 CULEBRIA - DECISIÓN OPERATIVA")
    print("=" * 92)
    print()

    if decision == "PARLAY":
        print("✅ APUESTA PROPUESTA")
        print("Tipo: PARLAY")
        print(
            f"Casa: "
            f"{data.get('bookmaker', '?')}"
        )
        print(
            f"Cuota combinada: "
            f"{data.get('combined_odds', '?')}"
        )

        for index, leg in enumerate(
            data.get(
                "legs",
                [],
            ),
            start=1,
        ):
            print()
            print(
                f"{index}. "
                f"{leg.get('home', '?')} vs "
                f"{leg.get('away', '?')}"
            )
            print(
                f"   Apostar: "
                f"{leg.get('selection', '?')}"
            )
            print(
                f"   Cuota: "
                f"{leg.get('odds', '?')}"
            )
            print(
                f"   Prob. modelo: "
                f"{leg.get('model_probability_pct', '?')}%"
            )
            print(
                f"   Edge sin vig: "
                f"{leg.get('novig_edge_pp', '?')} pp"
            )

    elif decision == "NO_BET":
        print("⛔ NO BET")
        print()
        print(
            "No se encontraron selecciones "
            "aprobadas que alcanzaran la "
            "política de cuota 1.80+."
        )

    else:
        print(
            "⚠️ Decisión operativa "
            f"no reconocida: {decision}"
        )

    print()
    print(
        "⚠️ El modelo estadístico no "
        "garantiza resultados ganadores."
    )
    print("=" * 92)


def main():
    start = datetime.now()

    print()
    print("=" * 92)
    print("🐍 CULEBRIA")
    print("MODO OPERATIVO — UN SOLO COMANDO")
    print("=" * 92)
    print()
    print(
        f"Inicio: "
        f"{start.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    print(
        "Mercados: 1X / AWAY_SCORES"
    )
    print(
        "Objetivo de cuota: 1.80+"
    )
    print(
        "Si no hay valor suficiente: NO BET"
    )

    total = len(STAGES)

    for index, (
        title,
        script_name,
    ) in enumerate(
        STAGES,
        start=1,
    ):
        success = run_script(
            f"[{index}/{total}] {title}",
            script_name,
        )

        if not success:
            print()
            print("=" * 92)
            print("❌ CULEBRIA DETENIDA")
            print("=" * 92)
            print(
                f"El problema apareció en: "
                f"{script_name}"
            )
            return

        # ----------------------------------------------------
        # CORTES SEGUROS ANTES DE CONSULTAR CUOTAS
        # ----------------------------------------------------

        if (
            script_name
            == "build_poisson_predictions.py"
            and not csv_has_rows(
                POISSON_FILE
            )
        ):
            print_no_bet(
                "Poisson generó 0 predicciones.",
                (
                    "No hay partidos con muestra "
                    "histórica suficiente."
                ),
            )
            return

        if (
            script_name
            == "build_reliability_gate.py"
            and not csv_has_rows(
                GATE_FILE
            )
        ):
            print_no_bet(
                (
                    "Ninguna predicción superó "
                    "el Reliability Gate."
                )
            )
            return

        if (
            script_name
            == "inspect_prematch_odds_candidates.py"
            and not csv_has_rows(
                PREMATCH_FILE
            )
        ):
            print_no_bet(
                (
                    "No existen señales PREMATCH "
                    "válidas en este momento."
                )
            )
            return

    print_operational_summary()

    end = datetime.now()

    print()
    print(
        f"Tiempo total: "
        f"{end - start}"
    )


if __name__ == "__main__":
    main()
