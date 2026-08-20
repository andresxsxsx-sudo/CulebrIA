from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

FOOTBALL_RUN = ROOT / "culebria.py"
FOOTBALL_CONFIRM = ROOT / "confirm_culebria_bet.py"

WTA_REBUILD = ROOT / "rebuild_culebria_wta_current_ratings.py"
TENNIS_RUN = ROOT / "culebria_tennis_operational_v1.py"
TENNIS_CONFIRM = ROOT / "confirm_culebria_tennis_bet.py"

FOOTBALL_CONFIRM_JSON = DATA / "culebria_bet_confirmation.json"
TENNIS_CONFIRM_JSON = DATA / "culebria_tennis_bet_confirmation.json"
DAILY_JSON = DATA / "culebria_daily_precision.json"

SEPARATOR = "=" * 100


def run_script(title: str, script_path: Path) -> tuple[bool, str]:
    print()
    print(SEPARATOR)
    print(title)
    print(SEPARATOR)
    print()

    if not script_path.exists():
        print(f"❌ Falta: {script_path.name}")
        return False, f"Falta {script_path.name}"

    child_env = os.environ.copy()
    child_env["PYTHONIOENCODING"] = "utf-8"
    child_env["PYTHONUTF8"] = "1"

    process = subprocess.Popen(
        [sys.executable, "-X", "utf8", str(script_path)],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=child_env,
    )

    lines: list[str] = []

    assert process.stdout is not None

    for line in process.stdout:
        print(line, end="")
        lines.append(line)

    return_code = process.wait()
    output = "".join(lines)

    if return_code != 0:
        print()
        print(
            f"❌ {script_path.name} terminó con código "
            f"{return_code}."
        )
        return False, output

    return True, output


def safe_unlink(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def load_json(path: Path):
    if not path.exists():
        return None

    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError):
        return None


def parse_datetime(value):
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def is_fresh_payload(payload, started_at: datetime) -> bool:
    if not isinstance(payload, dict):
        return False

    generated = None

    for key in (
        "generated_at_utc",
        "confirmed_at_utc",
        "confirmation_time_utc",
        "timestamp_utc",
    ):
        generated = parse_datetime(
            payload.get(key)
        )
        if generated is not None:
            break

    if generated is None:
        return True

    return (
        generated.timestamp()
        >= started_at.timestamp() - 120
    )


def recursive_first(obj, keys):
    if isinstance(obj, dict):
        for key in keys:
            if key in obj and obj[key] not in (
                None,
                "",
                [],
                {},
            ):
                return obj[key]

        for value in obj.values():
            found = recursive_first(
                value,
                keys,
            )
            if found not in (
                None,
                "",
                [],
                {},
            ):
                return found

    elif isinstance(obj, list):
        for value in obj:
            found = recursive_first(
                value,
                keys,
            )
            if found not in (
                None,
                "",
                [],
                {},
            ):
                return found

    return None


def status_text(payload) -> str:
    if not isinstance(payload, dict):
        return "UNKNOWN"

    if payload.get("confirmed") is True:
        return "CONFIRMED"

    if payload.get("confirmed") is False:
        return "REJECTED"

    value = recursive_first(
        payload,
        (
            "status",
            "decision",
            "result",
            "confirmation_status",
        ),
    )

    if value is None:
        return "UNKNOWN"

    text = str(value).strip().upper()

    if (
        "CONFIRM" in text
        and "NOT" not in text
        and "NO_" not in text
    ):
        return "CONFIRMED"

    if (
        "NO_BET" in text
        or "NO BET" in text
        or "REJECT" in text
        or "BLOCK" in text
        or "NOT_CONFIRMED" in text
    ):
        return "REJECTED"

    return text


def extract_legs(payload):
    if not isinstance(payload, dict):
        return []

    legs = payload.get("legs")

    if isinstance(legs, list) and len(legs) >= 2:
        return legs[:2]

    for container_key in (
        "best_parlay",
        "parlay",
        "confirmation",
        "bet",
    ):
        container = payload.get(
            container_key
        )

        if isinstance(container, dict):
            legs = container.get("legs")

            if isinstance(legs, list) and len(legs) >= 2:
                return legs[:2]

            leg1 = container.get("leg1")
            leg2 = container.get("leg2")

            if isinstance(leg1, dict) and isinstance(leg2, dict):
                return [leg1, leg2]

    found = recursive_first(
        payload,
        ("legs",),
    )

    if isinstance(found, list) and len(found) >= 2:
        return found[:2]

    return []


def extract_bookmaker(payload):
    value = recursive_first(
        payload,
        (
            "bookmaker",
            "sportsbook",
            "book",
            "house",
        ),
    )

    return str(value) if value is not None else "?"


def extract_combined_odds(payload):
    value = recursive_first(
        payload,
        (
            "combined_odds",
            "fresh_combined_odds",
            "parlay_odds",
            "total_odds",
        ),
    )

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def describe_leg(leg):
    if not isinstance(leg, dict):
        return "Selección no disponible", None

    selection = (
        leg.get("selection")
        or leg.get("pick")
        or leg.get("bet")
        or leg.get("market")
        or "Selección"
    )

    odds = (
        leg.get("fresh_odds")
        or leg.get("odds")
        or leg.get("price")
    )

    event = (
        leg.get("players")
        or leg.get("event")
        or leg.get("match")
    )

    if not event:
        home = (
            leg.get("home")
            or leg.get("home_team")
        )
        away = (
            leg.get("away")
            or leg.get("away_team")
        )

        if home and away:
            event = f"{home} vs {away}"

    label = str(selection)

    if event:
        label = f"{event} — {selection}"

    try:
        odds_value = float(odds)
    except (TypeError, ValueError):
        odds_value = None

    return label, odds_value


def infer_confirmation_from_output(output: str) -> str:
    text = output.upper()

    if (
        "✅ PARLAY CONFIRMADO" in text
        or "APUESTA CONFIRMADA" in text
        or "BET CONFIRMED" in text
    ):
        return "CONFIRMED"

    if (
        "⛔ NO BET" in text
        or "NO CONFIRMADO" in text
        or "REJECTED" in text
    ):
        return "REJECTED"

    return "UNKNOWN"


def summarize_sport(
    sport_name: str,
    payload,
    confirmation_output: str,
):
    status = status_text(
        payload
    )

    if status == "UNKNOWN":
        status = infer_confirmation_from_output(
            confirmation_output
        )

    summary = {
        "sport": sport_name,
        "status": status,
        "bookmaker": None,
        "combined_odds": None,
        "legs": [],
    }

    if status != "CONFIRMED":
        return summary

    summary["bookmaker"] = extract_bookmaker(
        payload
    )

    summary["combined_odds"] = extract_combined_odds(
        payload
    )

    for leg in extract_legs(
        payload
    ):
        label, odds = describe_leg(
            leg
        )

        summary["legs"].append(
            {
                "label": label,
                "odds": odds,
            }
        )

    return summary


def print_compact_result(summary):
    status = summary["status"]

    if status == "PIPELINE_ERROR":
        print(
            f"❌ {summary['sport']}: ERROR TÉCNICO — "
            "sin decisión válida del día"
        )
        return

    if status != "CONFIRMED":
        print(
            f"⛔ {summary['sport']}: NO BET / NO CONFIRMADO"
        )
        return

    print(
        f"✅ {summary['sport']}: PARLAY CONFIRMADO"
    )

    if summary["bookmaker"]:
        print(
            f"   Casa: {summary['bookmaker']}"
        )

    for index, leg in enumerate(
        summary["legs"],
        start=1,
    ):
        if leg["odds"] is None:
            print(
                f"   {index}. {leg['label']}"
            )
        else:
            print(
                f"   {index}. {leg['label']} "
                f"@ {leg['odds']:.3f}"
            )

    if summary["combined_odds"] is not None:
        print(
            f"   Cuota combinada: "
            f"{summary['combined_odds']:.3f}"
        )


def main():
    started_at = datetime.now(
        timezone.utc
    )

    print(SEPARATOR)
    print(
        "🐍 CULEBRIA DAILY PRECISION — FÚTBOL + TENIS"
    )
    print(SEPARATOR)
    print()
    print(
        "Una sola ejecución diaria."
    )
    print(
        "Genera y confirma por separado:"
    )
    print(
        "  • el mejor parlay de FÚTBOL"
    )
    print(
        "  • el mejor parlay WTA de TENIS"
    )
    print()
    print(
        "NO mezcla deportes en un mismo parlay."
    )
    print(
        "Si un deporte no tiene 2 selecciones válidas, "
        "mantiene NO BET."
    )

    # ---------------------------------------------------------
    # FÚTBOL
    # ---------------------------------------------------------
    safe_unlink(
        FOOTBALL_CONFIRM_JSON
    )

    football_run_ok, football_run_output = run_script(
        "⚽ FASE 1 — CULEBRIA FÚTBOL",
        FOOTBALL_RUN,
    )

    football_no_core = (
        "NO_CORE_COVERED"
        in football_run_output
    )

    football_confirm_output = ""
    football_confirm_ok = False

    if football_run_ok and not football_no_core:
        (
            football_confirm_ok,
            football_confirm_output,
        ) = run_script(
            "⚽ FASE 2 — CONFIRMACIÓN FRESCA FÚTBOL",
            FOOTBALL_CONFIRM,
        )

    football_pipeline_ok = (
        football_run_ok
        and (
            football_confirm_ok
            or football_no_core
        )
    )

    football_payload = (
        load_json(
            FOOTBALL_CONFIRM_JSON
        )
        if football_pipeline_ok
        else None
    )

    if (
        football_payload is not None
        and not is_fresh_payload(
            football_payload,
            started_at,
        )
    ):
        football_payload = None

    football_summary = summarize_sport(
        "FÚTBOL",
        football_payload,
        football_confirm_output,
    )

    if football_no_core:
        football_summary["status"] = "REJECTED"
    elif not football_pipeline_ok:
        football_summary["status"] = "PIPELINE_ERROR"

    # ---------------------------------------------------------
    # TENIS WTA
    # ---------------------------------------------------------
    safe_unlink(
        TENNIS_CONFIRM_JSON
    )

    tennis_ready = True

    if WTA_REBUILD.exists():
        rebuild_ok, _ = run_script(
            "🎾 FASE 3 — ACTUALIZAR RATINGS WTA",
            WTA_REBUILD,
        )

        if not rebuild_ok:
            tennis_ready = False
    else:
        print()
        print(
            "⚠️ No existe rebuild_culebria_wta_current_ratings.py."
        )
        print(
            "Se intentará usar los ratings WTA actuales."
        )

    tennis_run_ok = False
    tennis_confirm_ok = False
    tennis_confirm_output = ""

    if tennis_ready:
        tennis_run_ok, _ = run_script(
            "🎾 FASE 4 — CULEBRIA TENIS WTA",
            TENNIS_RUN,
        )

    if tennis_run_ok:
        (
            tennis_confirm_ok,
            tennis_confirm_output,
        ) = run_script(
            "🎾 FASE 5 — CONFIRMACIÓN FRESCA TENIS",
            TENNIS_CONFIRM,
        )

    tennis_pipeline_ok = (
        tennis_ready
        and tennis_run_ok
        and tennis_confirm_ok
    )

    tennis_payload = (
        load_json(
            TENNIS_CONFIRM_JSON
        )
        if tennis_pipeline_ok
        else None
    )

    if (
        tennis_payload is not None
        and not is_fresh_payload(
            tennis_payload,
            started_at,
        )
    ):
        tennis_payload = None

    tennis_summary = summarize_sport(
        "TENIS WTA",
        tennis_payload,
        tennis_confirm_output,
    )

    if not tennis_pipeline_ok:
        tennis_summary["status"] = "PIPELINE_ERROR"

    # ---------------------------------------------------------
    # RESUMEN
    # ---------------------------------------------------------
    daily_payload = {
        "generated_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),
        "policy": {
            "separate_sports":
                True,
            "football_parlays_requested":
                1,
            "tennis_parlays_requested":
                1,
            "force_bet":
                False,
        },
        "football":
            football_summary,
        "tennis":
            tennis_summary,
    }

    DAILY_JSON.write_text(
        json.dumps(
            daily_payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print()
    print(SEPARATOR)
    print(
        "🏆 CULEBRIA — LOS 2 PARLAYS DE MAYOR PRECISIÓN DEL DÍA"
    )
    print(SEPARATOR)
    print()

    print_compact_result(
        football_summary
    )

    print()

    print_compact_result(
        tennis_summary
    )

    print()
    print(SEPARATOR)
    print(
        f"Resumen diario: {DAILY_JSON}"
    )
    print(SEPARATOR)
    print()
    print(
        "⚠️ CulebrIA no fuerza una apuesta. "
        "Si fútbol o tenis no superan sus filtros y "
        "la confirmación fresca, ese deporte queda en NO BET."
    )


if __name__ == "__main__":
    main()
