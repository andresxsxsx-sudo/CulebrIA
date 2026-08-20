from pathlib import Path

import pandas as pd

from src.analysis.poisson_model import (
    calculate_expected_goals,
    calculate_market_probabilities,
    fair_odds,
    parse_api_date
)

from src.api.fdorg_local_history import (
    load_competition_history
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"

VALIDATION_FILE = (
    DATA_DIR
    / "cross_source_validation.csv"
)

AUDIT_FILE = (
    DATA_DIR
    / "model_sample_audit.csv"
)

OUTPUT_FILE = (
    DATA_DIR
    / "poisson_predictions.csv"
)


# ============================================================
# FORMATO
# ============================================================

def pct(value):

    return round(
        value * 100,
        2
    )


def odds(value):

    result = fair_odds(
        value
    )

    if result is None:
        return None

    return round(
        result,
        3
    )


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    print("=" * 76)
    print(
        "CulebrIA - MODELO POISSON V1"
    )
    print("=" * 76)

    # --------------------------------------------------------
    # PARTIDOS VERIFICADOS
    # --------------------------------------------------------

    validation = pd.read_csv(
        VALIDATION_FILE
    )

    validation[
        "fixture_id"
    ] = validation[
        "fixture_id"
    ].astype(int)

    # --------------------------------------------------------
    # PARTIDOS APROBADOS POR AUDITORÍA
    # --------------------------------------------------------

    audit = pd.read_csv(
        AUDIT_FILE
    )

    # --------------------------------------------------------
    # COMPROBAR QUE LA AUDITORÍA PERTENECE A LOS FIXTURES ACTUALES
    # --------------------------------------------------------

    required_audit_columns = {
        "fixture_id",
        "model_status",
    }

    missing_audit_columns = (
        required_audit_columns
        - set(audit.columns)
    )

    if missing_audit_columns:

        raise RuntimeError(
            "model_sample_audit.csv no tiene las columnas requeridas: "
            + ", ".join(
                sorted(
                    missing_audit_columns
                )
            )
        )

    audit[
        "fixture_id"
    ] = audit[
        "fixture_id"
    ].astype(int)

    verified_ids = set(
        validation[
            validation[
                "validation"
            ] == "VERIFICADO"
        ][
            "fixture_id"
        ].astype(int)
    )

    audited_ids = set(
        audit[
            "fixture_id"
        ].astype(int)
    )

    if audited_ids != verified_ids:

        missing_ids = sorted(
            verified_ids
            - audited_ids
        )

        extra_ids = sorted(
            audited_ids
            - verified_ids
        )

        raise RuntimeError(
            "La auditoría histórica está desactualizada. "
            "Ejecute audit_model_samples.py antes de Poisson. "
            f"Fixtures sin auditar: {missing_ids}. "
            f"Fixtures ajenos a la ejecución actual: {extra_ids}."
        )

    ready_ids = set(
        audit[
            audit[
                "model_status"
            ] == "LISTO"
        ][
            "fixture_id"
        ].astype(int)
    )

    ready = validation[
        (
            validation[
                "validation"
            ] == "VERIFICADO"
        )
        &
        (
            validation[
                "fixture_id"
            ].isin(
                ready_ids
            )
        )
    ].copy()

    print()
    print(
        f"Partidos aptos: "
        f"{len(ready)}"
    )

    # --------------------------------------------------------
    # CARGAR HISTÓRICOS
    # --------------------------------------------------------

    histories = {}

    for code in (
        ready[
            "fdorg_code"
        ]
        .astype(str)
        .str.upper()
        .unique()
    ):

        history = (
            load_competition_history(
                code
            )
        )

        histories[
            code
        ] = history[
            "matches"
        ]

        print(
            f"{code}: "
            f"{history['match_count']} "
            f"partidos históricos locales"
        )

    output_rows = []
    errors = 0

    # ========================================================
    # PREDICCIONES
    # ========================================================

    for _, match in ready.iterrows():

        code = str(
            match[
                "fdorg_code"
            ]
        ).strip().upper()

        home = str(
            match[
                "fdorg_home"
            ]
        )

        away = str(
            match[
                "fdorg_away"
            ]
        )

        kickoff = parse_api_date(
            match[
                "fdorg_date"
            ]
        )

        if kickoff is None:

            errors += 1

            print()
            print(
                f"❌ Fecha inválida: "
                f"{home} vs {away}"
            )

            continue

        try:

            # ------------------------------------------------
            # EXPECTED GOALS
            # ------------------------------------------------

            model = (
                calculate_expected_goals(
                    matches=
                        histories[
                            code
                        ],

                    home_team=
                        home,

                    away_team=
                        away,

                    kickoff=
                        kickoff
                )
            )

            lambda_home = (
                model[
                    "lambda_home"
                ]
            )

            lambda_away = (
                model[
                    "lambda_away"
                ]
            )

            league = (
                model[
                    "league"
                ]
            )

            home_strength = (
                model[
                    "home_strength"
                ]
            )

            away_strength = (
                model[
                    "away_strength"
                ]
            )

            # ------------------------------------------------
            # PROBABILIDADES
            # ------------------------------------------------

            probabilities = (
                calculate_market_probabilities(
                    lambda_home,
                    lambda_away
                )
            )

            best_score = (
                probabilities[
                    "best_score"
                ]
            )

            # ------------------------------------------------
            # CSV
            # ------------------------------------------------

            row = {
                "fixture_id":
                    match[
                        "fixture_id"
                    ],

                "competition":
                    code,

                "kickoff":
                    match[
                        "fdorg_date"
                    ],

                "home":
                    home,

                "away":
                    away,

                "league_sample":
                    league[
                        "matches"
                    ],

                "league_home_goal_avg":
                    round(
                        league[
                            "home_goals_avg"
                        ],
                        3
                    ),

                "league_away_goal_avg":
                    round(
                        league[
                            "away_goals_avg"
                        ],
                        3
                    ),

                "home_venue_sample":
                    home_strength[
                        "venue_matches"
                    ],

                "away_venue_sample":
                    away_strength[
                        "venue_matches"
                    ],

                "home_attack_strength":
                    round(
                        home_strength[
                            "attack_strength"
                        ],
                        3
                    ),

                "home_defense_factor":
                    round(
                        home_strength[
                            "defense_factor"
                        ],
                        3
                    ),

                "away_attack_strength":
                    round(
                        away_strength[
                            "attack_strength"
                        ],
                        3
                    ),

                "away_defense_factor":
                    round(
                        away_strength[
                            "defense_factor"
                        ],
                        3
                    ),

                "lambda_home":
                    round(
                        lambda_home,
                        3
                    ),

                "lambda_away":
                    round(
                        lambda_away,
                        3
                    ),

                "lambda_total":
                    round(
                        lambda_home
                        + lambda_away,
                        3
                    ),

                # -----------------------------
                # 1X2
                # -----------------------------

                "home_win_pct":
                    pct(
                        probabilities[
                            "home_win"
                        ]
                    ),

                "draw_pct":
                    pct(
                        probabilities[
                            "draw"
                        ]
                    ),

                "away_win_pct":
                    pct(
                        probabilities[
                            "away_win"
                        ]
                    ),

                # -----------------------------
                # DOBLE OPORTUNIDAD
                # -----------------------------

                "home_or_draw_pct":
                    pct(
                        probabilities[
                            "home_or_draw"
                        ]
                    ),

                "away_or_draw_pct":
                    pct(
                        probabilities[
                            "away_or_draw"
                        ]
                    ),

                # -----------------------------
                # DNB
                # -----------------------------

                "home_dnb_pct":
                    pct(
                        probabilities[
                            "home_dnb"
                        ]
                    ),

                "away_dnb_pct":
                    pct(
                        probabilities[
                            "away_dnb"
                        ]
                    ),

                # -----------------------------
                # GOLES
                # -----------------------------

                "over15_pct":
                    pct(
                        probabilities[
                            "over_15"
                        ]
                    ),

                "over25_pct":
                    pct(
                        probabilities[
                            "over_25"
                        ]
                    ),

                "under35_pct":
                    pct(
                        probabilities[
                            "under_35"
                        ]
                    ),

                "btts_pct":
                    pct(
                        probabilities[
                            "btts"
                        ]
                    ),

                "home_scores_pct":
                    pct(
                        probabilities[
                            "home_scores"
                        ]
                    ),

                "away_scores_pct":
                    pct(
                        probabilities[
                            "away_scores"
                        ]
                    ),

                # -----------------------------
                # CUOTAS JUSTAS
                # -----------------------------

                "fair_home_win":
                    odds(
                        probabilities[
                            "home_win"
                        ]
                    ),

                "fair_draw":
                    odds(
                        probabilities[
                            "draw"
                        ]
                    ),

                "fair_away_win":
                    odds(
                        probabilities[
                            "away_win"
                        ]
                    ),

                "fair_over15":
                    odds(
                        probabilities[
                            "over_15"
                        ]
                    ),

                "fair_over25":
                    odds(
                        probabilities[
                            "over_25"
                        ]
                    ),

                "fair_under35":
                    odds(
                        probabilities[
                            "under_35"
                        ]
                    ),

                "fair_btts":
                    odds(
                        probabilities[
                            "btts"
                        ]
                    ),

                # -----------------------------
                # MARCADOR MODAL
                # -----------------------------

                "most_likely_score":
                    (
                        f"{best_score[0]}"
                        f"-"
                        f"{best_score[1]}"
                    ),

                "most_likely_score_pct":
                    pct(
                        probabilities[
                            "best_score_probability"
                        ]
                    ),
            }

            output_rows.append(
                row
            )

            # =================================================
            # TERMINAL
            # =================================================

            print()
            print("-" * 76)

            print(
                f"{home} vs {away}"
            )

            print(
                f"Competición: {code}"
            )

            print(
                f"Muestra liga: "
                f"{league['matches']}"
            )

            print()

            print(
                "GOLES ESPERADOS"
            )

            print(
                f"{home}: "
                f"{lambda_home:.2f}"
            )

            print(
                f"{away}: "
                f"{lambda_away:.2f}"
            )

            print(
                f"Total esperado: "
                f"{lambda_home + lambda_away:.2f}"
            )

            print()

            print(
                "1X2"
            )

            print(
                f"1: "
                f"{pct(probabilities['home_win'])}%"
            )

            print(
                f"X: "
                f"{pct(probabilities['draw'])}%"
            )

            print(
                f"2: "
                f"{pct(probabilities['away_win'])}%"
            )

            print()

            print(
                "GOLES"
            )

            print(
                f"Over 1.5: "
                f"{pct(probabilities['over_15'])}%"
            )

            print(
                f"Over 2.5: "
                f"{pct(probabilities['over_25'])}%"
            )

            print(
                f"Under 3.5: "
                f"{pct(probabilities['under_35'])}%"
            )

            print(
                f"BTTS: "
                f"{pct(probabilities['btts'])}%"
            )

            print(
                f"{home} marca: "
                f"{pct(probabilities['home_scores'])}%"
            )

            print(
                f"{away} marca: "
                f"{pct(probabilities['away_scores'])}%"
            )

            print()

            print(
                "DOBLE OPORTUNIDAD"
            )

            print(
                f"1X: "
                f"{pct(probabilities['home_or_draw'])}%"
            )

            print(
                f"X2: "
                f"{pct(probabilities['away_or_draw'])}%"
            )

            print()

            print(
                "MARCADOR MÁS PROBABLE"
            )

            print(
                f"{best_score[0]}"
                f"-"
                f"{best_score[1]}"
                f" "
                f"("
                f"{pct(probabilities['best_score_probability'])}%"
                f")"
            )

        except Exception as error:

            errors += 1

            print()
            print(
                f"❌ Error en "
                f"{home} vs {away}:"
            )

            print(
                error
            )

    # ========================================================
    # GUARDAR
    # ========================================================

    output_df = pd.DataFrame(
        output_rows
    )

    output_df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # RESULTADO
    # ========================================================

    print()
    print("=" * 76)
    print(
        "POISSON V1 FINALIZADO"
    )
    print("=" * 76)

    print()

    print(
        f"Predicciones generadas: "
        f"{len(output_rows)}"
    )

    print(
        f"Errores: "
        f"{errors}"
    )

    print()

    print(
        "Solicitudes API realizadas: 0"
    )

    print()

    print(
        "Archivo:"
    )

    print(
        OUTPUT_FILE
    )

    print()

    print(
        "⚠️ MODELO V1 NO CALIBRADO"
    )

    print(
        "Estas probabilidades todavía "
        "no deben interpretarse como "
        "recomendaciones de apuesta."
    )


if __name__ == "__main__":
    main()