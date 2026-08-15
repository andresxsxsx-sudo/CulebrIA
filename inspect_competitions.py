import csv
from pathlib import Path

from src.api.football_api import get_today_fixtures
from src.analysis.fixture_filter import filter_candidate_fixtures
from src.analysis.competition_report import get_competition_report


ROOT_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = ROOT_DIR / "data" / "competition_report.csv"


def main():

    print("=" * 70)
    print("CulebrIA - INSPECCIÓN DE COMPETICIONES")
    print("=" * 70)

    # 1. Cargar partidos
    data = get_today_fixtures()

    # 2. Aplicar filtro
    filtered = filter_candidate_fixtures(
        data["fixtures"]
    )

    candidates = filtered["fixtures"]

    # 3. Agrupar por competición
    report = get_competition_report(
        candidates
    )

    # 4. Control de integridad
    report_total = sum(
        matches
        for competition, matches in report
    )

    print()
    print("CONTROL DE INTEGRIDAD")
    print("-" * 70)

    print(
        f"Candidatos del filtro: {len(candidates)}"
    )

    print(
        f"Partidos agrupados:    {report_total}"
    )

    if len(candidates) == report_total:
        print("✅ El reporte está completo.")

    else:
        difference = len(candidates) - report_total

        print(
            f"❌ Diferencia detectada: "
            f"{difference} partidos."
        )

    # 5. Resumen
    print()
    print(
        f"Eventos candidatos: "
        f"{len(candidates)}"
    )

    print(
        f"Competiciones diferentes: "
        f"{len(report)}"
    )

    # 6. Crear CSV
    with open(
        OUTPUT_FILE,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.writer(file)

        writer.writerow([
            "Pais",
            "Competicion",
            "League_ID",
            "Partidos_futuros"
        ])

        for competition, matches in report:

            country, league_name, league_id = competition

            writer.writerow([
                country,
                league_name,
                league_id,
                matches
            ])

    print()
    print("✅ Informe creado correctamente:")
    print(OUTPUT_FILE)

    # 7. Mostrar competiciones
    print()
    print("=" * 70)
    print("COMPETICIONES DISPONIBLES")
    print("=" * 70)

    for index, (competition, matches) in enumerate(
        report,
        start=1
    ):

        country, league_name, league_id = competition

        print()
        print(
            f"{index}. "
            f"{country} - {league_name}"
        )

        print(
            f"   League ID: {league_id}"
        )

        print(
            f"   Partidos futuros: {matches}"
        )

    print()
    print("=" * 70)


if __name__ == "__main__":
    main()