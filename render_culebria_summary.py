from __future__ import annotations

import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

DECISION_FILE = DATA / "culebria_operational_final.json"
CONFIRMATION_FILE = DATA / "culebria_bet_confirmation.json"
FOOTBALL_LOG = ROOT / "culebria-football.log"


def load_json(path: Path):
    if not path.exists():
        return None

    try:
        return json.loads(
            path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        )
    except Exception:
        return None


def safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def market_description(leg):
    market = str(
        leg.get("market", "")
    ).strip().upper()

    home = str(
        leg.get("home", "Local")
    ).strip()

    away = str(
        leg.get("away", "Visitante")
    ).strip()

    if market == "1X":
        return f"{home} gana o empata"

    if market == "X2":
        return f"{away} gana o empata"

    if market == "AWAY_SCORES":
        return f"{away} marca al menos 1 gol"

    return f"Mercado {market}"


def no_bet_reason_from_log():
    if not FOOTBALL_LOG.exists():
        return []

    lines = FOOTBALL_LOG.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines()

    for index, line in enumerate(lines):
        if (
            "NO BET —" not in line
            and "NO BET -" not in line
        ):
            continue

        result = []

        for candidate in lines[index:index + 6]:
            text = candidate.strip()

            if not text:
                continue

            if set(text) <= {"=", "-"}:
                continue

            result.append(text)

            if len(result) == 3:
                break

        return result

    return []


def render_confirmed(confirmation):
    bookmaker = str(
        confirmation.get("bookmaker", "?")
    ).strip()

    combined_odds = safe_float(
        confirmation.get("combined_odds")
    )

    combined_ev = safe_float(
        confirmation.get("combined_ev_pct")
    )

    legs = confirmation.get("legs", [])

    lines = [
        "## 🐍 CulebrIA Fútbol",
        "",
        "# ✅ PARLEY CONFIRMADO",
        "",
        f"**Casa:** {bookmaker}",
    ]

    if combined_odds is not None:
        lines.append(
            f"**Cuota combinada confirmada:** {combined_odds:.2f}"
        )

    if combined_ev is not None:
        lines.append(
            f"**EV estimado:** {combined_ev:+.2f}%"
        )

    lines += [
        "",
        "## 📋 APOSTAR",
        "",
    ]

    parlay_parts = []

    for number, leg in enumerate(legs, start=1):
        home = str(
            leg.get("home", "Local")
        ).strip()

        away = str(
            leg.get("away", "Visitante")
        ).strip()

        market = str(
            leg.get("market", "")
        ).strip().upper()

        odds = safe_float(
            leg.get("odds")
        )

        selection = market_description(leg)

        parlay_parts.append(selection)

        lines += [
            f"### {number}. {home} vs {away}",
            "",
            f"**➡️ Selección: {selection}**",
            f"Mercado: `{market}`",
        ]

        if odds is not None:
            lines.append(
                f"Cuota confirmada: **{odds:.2f}**"
            )

        lines.append("")

    if parlay_parts:
        lines += [
            "---",
            "",
            "## 🎯 PARLEY",
            "",
            f"**{' + '.join(parlay_parts)}**",
            "",
        ]

        if combined_odds is not None:
            lines += [
                f"### Cuota total: **{combined_odds:.2f}**",
                "",
            ]

    lines += [
        "### ✅ Confirmación final superada",
        "",
        "Las dos selecciones pasaron la comprobación fresca de cuotas de CulebrIA.",
        "",
        "### ⚠️ Antes de realizarla",
        "",
        "**Usar este parley solamente si las cuotas disponibles siguen iguales o mejores que las cuotas confirmadas arriba.**",
        "",
        "Si una cuota cambió de forma importante, vuelve a ejecutar CulebrIA antes de usar la selección.",
    ]

    return lines


def render_no_bet(decision=None):
    lines = [
        "## 🐍 CulebrIA Fútbol",
        "",
        "# ⛔ NO BET",
        "",
    ]

    if decision:
        approved = decision.get(
            "approved_candidates"
        )

        if approved is not None:
            lines += [
                f"**Candidatos aprobados:** {approved}",
                "",
            ]

    reason = no_bet_reason_from_log()

    if reason:
        lines += [
            "**Motivo:**",
            "",
        ]

        lines += [
            f"> {item}"
            for item in reason
        ]

        lines.append("")

    lines += [
        "## 🚫 NO APOSTAR",
        "",
        "CulebrIA no encontró un parley que superara todos los filtros y la confirmación requerida.",
        "",
        "**No se bajan los filtros para forzar una apuesta.**",
    ]

    return lines


def render_unconfirmed(decision=None):
    lines = [
        "## 🐍 CulebrIA Fútbol",
        "",
        "# ⚠️ PARLEY NO CONFIRMADO",
        "",
        "**NO APOSTAR.**",
        "",
        "CulebrIA generó una decisión operativa, pero no superó o no completó la confirmación fresca final.",
    ]

    if decision:
        bookmaker = decision.get(
            "bookmaker"
        )

        combined_odds = safe_float(
            decision.get("combined_odds")
        )

        if bookmaker:
            lines += [
                "",
                f"Casa detectada: **{bookmaker}**",
            ]

        if combined_odds is not None:
            lines.append(
                f"Cuota detectada: **{combined_odds:.2f}**"
            )

    return lines


def main():
    job_status = os.environ.get(
        "JOB_STATUS",
        "success",
    ).strip().lower()

    confirmation = load_json(
        CONFIRMATION_FILE
    )

    decision = load_json(
        DECISION_FILE
    )

    if job_status != "success":
        lines = [
            "## 🐍 CulebrIA Fútbol",
            "",
            "# ❌ ERROR DE EJECUCIÓN",
            "",
            "CulebrIA no terminó correctamente.",
            "",
            "**NO APOSTAR.** Revisa el paso rojo del workflow.",
        ]

    elif (
        confirmation
        and str(
            confirmation.get(
                "decision",
                "",
            )
        ).strip().upper()
        == "BET_CONFIRMED"
    ):
        lines = render_confirmed(
            confirmation
        )

    elif decision:
        decision_type = str(
            decision.get(
                "decision",
                "",
            )
        ).strip().upper().replace(
            " ",
            "_",
        )

        if decision_type == "NO_BET":
            lines = render_no_bet(
                decision
            )
        else:
            lines = render_unconfirmed(
                decision
            )

    else:
        lines = render_no_bet()

    output = "\n".join(lines) + "\n"

    summary_path = os.environ.get(
        "GITHUB_STEP_SUMMARY"
    )

    if summary_path:
        Path(summary_path).write_text(
            output,
            encoding="utf-8",
        )
    else:
        print(output)


if __name__ == "__main__":
    main()
