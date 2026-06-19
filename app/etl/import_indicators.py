"""
ETL for statistical indicator data (second and third data sources).

Handles two fallback CSV formats:
  1. accident_per_10000_per_city.csv
     — accident rate per 10,000 inhabitants per city/district per year
     — detected format: wide (years as columns) or long (Jahr, Gebiet, Wert)

  2. accidents_with_persons_per_month.csv
     — monthly accident totals with personal injury
     — used as a national-level time-series indicator

Also seeds state-level population figures from hardcoded Destatis 2023 values
(used for cross-source rate-per-100k queries when GENESIS API is unavailable).
"""

import json
import os
import sqlite3
from pathlib import Path

import pandas as pd

from ..database import get_connection
from ..utils.ags import STATE_NAMES, STATE_POPULATION_2023

DATA_DIR = Path(__file__).parent.parent.parent / "data"


# ─────────────────────────────────────────────────────────────────────────────
# Helper: ensure indicator exists and return its id
# ─────────────────────────────────────────────────────────────────────────────
def _upsert_indicator(conn, code: str, label: str, unit: str, source_system: str) -> int:
    conn.execute(
        """INSERT INTO statistical_indicators(code, label, unit, source_system)
           VALUES(?,?,?,?)
           ON CONFLICT(code) DO UPDATE
             SET label=excluded.label, unit=excluded.unit, source_system=excluded.source_system""",
        [code, label, unit, source_system],
    )
    row = conn.execute(
        "SELECT indicator_id FROM statistical_indicators WHERE code=?", [code]
    ).fetchone()
    return row["indicator_id"]


def _upsert_location(conn, ags: str, name: str, location_type: str, parent_ags=None) -> int:
    conn.execute(
        """INSERT INTO locations(ags, name, location_type, parent_ags)
           VALUES(?,?,?,?)
           ON CONFLICT(ags) DO UPDATE SET name=excluded.name""",
        [ags, name, location_type, parent_ags],
    )
    row = conn.execute("SELECT location_id FROM locations WHERE ags=?", [ags]).fetchone()
    return row["location_id"]


# ─────────────────────────────────────────────────────────────────────────────
# 1. Seed state population from hardcoded Destatis values
# ─────────────────────────────────────────────────────────────────────────────
def seed_population(conn=None):
    """
    Insert/update state-level population for 2023 from hardcoded Destatis values.
    This enables the cross-source rate-per-100k query even without GENESIS API.
    Source: Destatis, Bevölkerungsstand 2023 — dl-de/by-2-0
    """
    close = conn is None
    if conn is None:
        conn = get_connection()

    ind_id = _upsert_indicator(
        conn,
        code="population",
        label="Bevölkerung (Einwohner)",
        unit="persons",
        source_system="Destatis 2023 (hardcoded)",
    )

    for ags, pop in STATE_POPULATION_2023.items():
        name = STATE_NAMES[ags]
        loc_id = _upsert_location(conn, ags, name, "state")
        conn.execute(
            """INSERT INTO statistical_values(location_id, indicator_id, year, value)
               VALUES(?,?,2023,?)
               ON CONFLICT(location_id, indicator_id, year) DO UPDATE SET value=excluded.value""",
            [loc_id, ind_id, pop],
        )

    conn.commit()

    # Log provenance so the data-sources panel shows this source
    conn.execute(
        """INSERT INTO data_sources(name, origin_url, file_name, license, records_loaded, run_status)
           VALUES('Destatis — Bevölkerungsstand der Bundesländer 2023',
                  'https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Bevoelkerung/Bevoelkerungsstand/',
                  'hardcoded_seed', 'dl-de/by-2-0', 16, 'success')
           ON CONFLICT DO NOTHING""",
    )
    conn.commit()

    print("[ETL] Population seeded for 16 states (Destatis 2023)")
    if close:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Import accident_per_10000_per_city.csv
# ─────────────────────────────────────────────────────────────────────────────
def import_rate_per_10000(file_path: str):
    """
    Import accident rate per 10,000 inhabitants per city.

    Supported CSV formats:
      WIDE:  Schluessel;Gebiet;2016;2017;...;2023
      LONG:  Schluessel;Gebiet;Jahr;Wert   (or similar long-format names)
    """
    conn = get_connection()

    cur = conn.execute(
        """INSERT INTO data_sources(name, origin_url, file_name, license, run_status)
           VALUES('Unfallatlas — Unfälle je 10.000 Einwohner',
                  'https://www.opengeodata.nrw.de/produkte/transport_verkehr/unfallatlas/',
                  ?, 'dl-de/by-2-0', 'running')""",
        [os.path.basename(file_path)],
    )
    ds_id = cur.lastrowid
    conn.commit()

    try:
        df = pd.read_csv(file_path, sep=";", encoding="utf-8-sig", dtype=str)
        df.columns = [c.strip() for c in df.columns]
        print(f"[ETL] rate_per_10000: {len(df)} rows, columns={list(df.columns)}")

        ind_id = _upsert_indicator(
            conn,
            "accident_rate_per_10k",
            "Unfälle je 10.000 Einwohner",
            "accidents per 10,000",
            "Unfallatlas-Fallback",
        )

        # Detect format
        year_cols = [c for c in df.columns if c.isdigit() and 2016 <= int(c) <= 2025]
        inserted = 0

        if year_cols:
            # WIDE format: each year is a column
            key_col  = next((c for c in df.columns if "schluessel" in c.lower() or c.lower() == "ags"), None)
            name_col = next((c for c in df.columns if "gebiet" in c.lower() or "name" in c.lower()), None)

            for _, row in df.iterrows():
                ags  = str(row[key_col]).strip().zfill(2) if key_col else None
                name = str(row[name_col]).strip() if name_col else "Unknown"
                if not ags or not ags.isdigit():
                    continue
                loc_type = "state" if len(ags) == 2 else ("district" if len(ags) == 5 else "municipality")
                loc_id = _upsert_location(conn, ags, name, loc_type)

                for yr in year_cols:
                    val = row[yr]
                    try:
                        val_f = float(str(val).replace(",", "."))
                        conn.execute(
                            """INSERT INTO statistical_values(location_id, indicator_id, year, value)
                               VALUES(?,?,?,?)
                               ON CONFLICT(location_id, indicator_id, year) DO UPDATE SET value=excluded.value""",
                            [loc_id, ind_id, int(yr), val_f],
                        )
                        inserted += 1
                    except (ValueError, TypeError):
                        pass
        else:
            # LONG format: look for year column and value column
            year_col  = next((c for c in df.columns if "jahr" in c.lower() or "year" in c.lower()), None)
            val_col   = next((c for c in df.columns if "wert" in c.lower() or "rate" in c.lower() or "je" in c.lower()), None)
            key_col   = next((c for c in df.columns if "schluessel" in c.lower() or "ags" in c.lower()), None)
            name_col  = next((c for c in df.columns if "gebiet" in c.lower() or "name" in c.lower()), None)

            for _, row in df.iterrows():
                try:
                    ags  = str(row[key_col]).strip().zfill(2) if key_col else None
                    name = str(row[name_col]).strip()         if name_col else "Unknown"
                    year = int(row[year_col])                 if year_col else None
                    val  = float(str(row[val_col]).replace(",", ".")) if val_col else None
                    if not ags or not year or val is None:
                        continue
                    loc_type = "state" if len(ags) == 2 else ("district" if len(ags) == 5 else "municipality")
                    loc_id = _upsert_location(conn, ags, name, loc_type)
                    conn.execute(
                        """INSERT INTO statistical_values(location_id, indicator_id, year, value)
                           VALUES(?,?,?,?)
                           ON CONFLICT(location_id, indicator_id, year) DO UPDATE SET value=excluded.value""",
                        [loc_id, ind_id, year, val],
                    )
                    inserted += 1
                except (ValueError, TypeError, KeyError):
                    pass

        conn.commit()
        conn.execute(
            "UPDATE data_sources SET run_status='success', records_loaded=? WHERE source_id=?",
            [inserted, ds_id],
        )
        conn.commit()
        print(f"[ETL] rate_per_10000: {inserted} values imported")

    except Exception as exc:
        conn.execute(
            "UPDATE data_sources SET run_status='error', error_notes=? WHERE source_id=?",
            [str(exc), ds_id],
        )
        conn.commit()
        raise
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# 3. Import accidents_with_persons_per_month.csv
# ─────────────────────────────────────────────────────────────────────────────
def import_monthly_stats(file_path: str):
    """
    Import monthly accident totals (national level).
    Expected columns: Jahr;Monat;Unfaelle_mit_Personenschaden (or similar)
    Stored as a national-level indicator (ags='DG' placeholder not in locations).
    """
    conn = get_connection()

    cur = conn.execute(
        """INSERT INTO data_sources(name, origin_url, file_name, license, run_status)
           VALUES('Destatis — Unfälle mit Personenschaden (monatlich)',
                  'https://www.destatis.de/', ?, 'dl-de/by-2-0', 'running')""",
        [os.path.basename(file_path)],
    )
    ds_id = cur.lastrowid
    conn.commit()

    try:
        df = pd.read_csv(file_path, sep=";", encoding="utf-8-sig", dtype=str)
        df.columns = [c.strip() for c in df.columns]
        print(f"[ETL] monthly_stats: {len(df)} rows, columns={list(df.columns)}")

        ind_id = _upsert_indicator(
            conn,
            "monthly_accidents_personal_injury",
            "Unfälle mit Personenschaden (monatlich, Deutschland)",
            "accidents",
            "Destatis",
        )

        # Ensure a Germany-wide placeholder location exists
        conn.execute(
            """INSERT INTO locations(ags, name, location_type)
               VALUES('00','Deutschland','state')
               ON CONFLICT(ags) DO NOTHING""",
        )
        conn.commit()
        loc = conn.execute("SELECT location_id FROM locations WHERE ags='00'").fetchone()
        loc_id = loc["location_id"] if loc else None

        year_col  = next((c for c in df.columns if "jahr" in c.lower() or "year" in c.lower()), df.columns[0])
        month_col = next((c for c in df.columns if "monat" in c.lower() or "month" in c.lower()), None)
        val_col   = next((c for c in df.columns if "unfall" in c.lower() or "personenschaden" in c.lower() or "count" in c.lower()), None)
        if val_col is None and len(df.columns) >= 3:
            val_col = df.columns[2]

        inserted = 0
        for _, row in df.iterrows():
            try:
                year  = int(row[year_col])
                month = int(row[month_col]) if month_col else None
                val   = float(str(row[val_col]).replace(".", "").replace(",", ".")) if val_col else None
                if not val or not loc_id:
                    continue
                # Use year*100+month as a synthetic indicator code for monthly data
                code = f"monthly_accidents_{year}_{month:02d}" if month else f"annual_accidents_{year}"
                m_ind_id = _upsert_indicator(
                    conn, code,
                    f"Unfälle mit Personenschaden {year}" + (f"-{month:02d}" if month else ""),
                    "accidents", "Destatis"
                )
                conn.execute(
                    """INSERT INTO statistical_values(location_id, indicator_id, year, value)
                       VALUES(?,?,?,?)
                       ON CONFLICT(location_id, indicator_id, year) DO UPDATE SET value=excluded.value""",
                    [loc_id, m_ind_id, year, val],
                )
                inserted += 1
            except (ValueError, TypeError):
                pass

        conn.commit()
        conn.execute(
            "UPDATE data_sources SET run_status='success', records_loaded=? WHERE source_id=?",
            [inserted, ds_id],
        )
        conn.commit()
        print(f"[ETL] monthly_stats: {inserted} records imported")

    except Exception as exc:
        conn.execute(
            "UPDATE data_sources SET run_status='error', error_notes=? WHERE source_id=?",
            [str(exc), ds_id],
        )
        conn.commit()
        raise
    finally:
        conn.close()
