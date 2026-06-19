"""
Master ETL runner.

Usage:
    cd backend
    python -m app.etl.run_etl

Place these CSV files in backend/data/ before running:
    accident_per_location_2023.csv
    accident_per_location_2021_in_Schleswig-Holstein.csv
    accident_per_10000_per_city.csv
    accidents_with_persons_per_month.csv
"""

from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data"


def main():
    print("=" * 60)
    print("  DBW ETL Runner — German Road Accident Platform")
    print("=" * 60)

    from ..database import init_db
    init_db()

    from .import_accidents import import_accidents_csv
    from .import_indicators import import_rate_per_10000, import_monthly_stats, seed_population

    # ── Seed population data (cross-source baseline) ──────────────────────────
    print("\n[1/6] Seeding state population data (Destatis 2023)...")
    seed_population()

    # ── Unfallatlas CSVs ──────────────────────────────────────────────────────
    accident_files = [
        (
            "accident_per_location_2023.csv",
            "Unfallatlas 2023 — Deutschland",
            "https://www.opengeodata.nrw.de/produkte/transport_verkehr/unfallatlas/",
        ),
        (
            "accident_per_location_2021_in_Schleswig-Holstein.csv",
            "Unfallatlas 2021 — Schleswig-Holstein",
            "https://www.opengeodata.nrw.de/produkte/transport_verkehr/unfallatlas/",
        ),
        (
            "Unfallorte2022_EPSG25832_CSV.csv",
            "Unfallatlas 2022 — Deutschland",
            "https://www.opengeodata.nrw.de/produkte/transport_verkehr/unfallatlas/",
        ),
        (
            "Unfallorte2021_EPSG25832_CSV.csv",
            "Unfallatlas 2021 — Deutschland",
            "https://www.opengeodata.nrw.de/produkte/transport_verkehr/unfallatlas/",
        ),
    ]

    step = 2
    for fname, name, url in accident_files:
        path = DATA_DIR / fname
        if path.exists():
            print(f"\n[{step}/6] Importing: {name}")
            try:
                result = import_accidents_csv(str(path), name, url)
                print(f"        Result: {result}")
            except Exception as exc:
                print(f"        ERROR: {exc}")
            step += 1
        else:
            print(f"\n[{step}/6] SKIP — {fname} not found in data/")
            step += 1

    # ── Rate per 10,000 CSV ───────────────────────────────────────────────────
    rate_file = DATA_DIR / "accident_per_10000_per_city.csv"
    if rate_file.exists():
        print(f"\n[5/6] Importing: Accident rate per 10,000 per city")
        try:
            import_rate_per_10000(str(rate_file))
        except Exception as exc:
            print(f"      ERROR: {exc}")
    else:
        print("\n[5/6] SKIP — accident_per_10000_per_city.csv not found")

    # ── Monthly statistics CSV ────────────────────────────────────────────────
    monthly_file = DATA_DIR / "accidents_with_persons_per_month.csv"
    if monthly_file.exists():
        print(f"\n[6/6] Importing: Monthly accident statistics")
        try:
            import_monthly_stats(str(monthly_file))
        except Exception as exc:
            print(f"      ERROR: {exc}")
    else:
        print("\n[6/6] SKIP — accidents_with_persons_per_month.csv not found")

    print("\n" + "=" * 60)
    print("  ETL Complete!")
    print("  Start API:    uvicorn app.main:app --reload --port 8000")
    print("  Swagger docs: http://localhost:8000/api/docs")
    print("  Frontend:     http://localhost:8000/")
    print("=" * 60)


if __name__ == "__main__":
    main()
