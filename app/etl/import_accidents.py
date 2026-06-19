"""
ETL pipeline: Unfallatlas CSV → SQLite

Flow:
1.  Log a 'running' entry in data_sources (provenance)
2.  Read CSV with pandas (handles BOM, semicolon delimiter)
3.  Fix German comma decimal separator in coordinates
4.  Parse numeric columns
5.  Build full AGS codes from ULAND/UREGBEZ/UKREIS/UGEMEINDE
6.  Plausibility filter (year range, coordinate bounds)
7.  Upsert locations (states) with population
8.  Batch-insert accident_events (ON CONFLICT DO NOTHING for deduplication)
9.  Insert accident_participants (one row per participant type — normalised design)
10. Update data_sources with final inserted count and notes
"""

import json
import os
import sqlite3
from pathlib import Path

import pandas as pd

from ..database import get_connection
from ..utils.ags import STATE_NAMES, STATE_POPULATION_2023, build_ags, PARTICIPANT_COLUMNS
from ..utils.validators import plausibility_report

DATA_DIR = Path(__file__).parent.parent.parent / "data"


def import_accidents_csv(
    file_path: str,
    source_name: str,
    source_url: str = None,
    license: str = "dl-de/by-2-0",
) -> dict:
    conn = get_connection()

    # 1. Log start
    cur = conn.execute(
        """INSERT INTO data_sources(name, origin_url, file_name, license, run_status)
           VALUES(?,?,?,?,'running')""",
        [source_name, source_url, os.path.basename(file_path), license],
    )
    ds_id = cur.lastrowid
    conn.commit()
    print(f"[ETL] data_source_id={ds_id}  file={file_path}")

    try:
        # 2. Read CSV (Unfallatlas uses UTF-8 with BOM, semicolon separator)
        df = pd.read_csv(
            file_path,
            sep=";",
            encoding="utf-8-sig",
            dtype=str,
            low_memory=False,
        )
        df.columns = [c.strip().lstrip("﻿") for c in df.columns]
        print(f"[ETL] Loaded {len(df)} rows | Columns: {list(df.columns[:8])}...")

        # 3. Fix German decimal comma in coordinates (e.g. "8,123456" → 8.123456)
        for col in ["XGCSWGS84", "YGCSWGS84"]:
            if col in df.columns:
                df[col] = pd.to_numeric(
                    df[col].str.replace(",", ".", regex=False), errors="coerce"
                )

        # 4. Parse integer columns
        int_cols = [
            "UJAHR", "UMONAT", "USTUNDE", "UWOCHENTAG", "UKATEGORIE",
            "UART", "UTYP1", "ULICHTVERH",
            "IstRad", "IstPKW", "IstFuss", "IstKrad", "IstGkfz", "IstSonstige",
        ]
        for col in int_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

        # Plausibility report (before filtering — for provenance notes)
        quality = plausibility_report(df)
        print(f"[ETL] Quality report: {quality}")

        # 5. Build AGS codes
        df["ags_full"] = df.apply(
            lambda r: build_ags(
                r.get("ULAND", ""), r.get("UREGBEZ", "0"),
                r.get("UKREIS", "00"), r.get("UGEMEINDE", "000"),
            ),
            axis=1,
        )
        df["ags_state"] = df["ags_full"].str[:2]

        # 6. Plausibility filter
        before = len(df)
        if "UJAHR" in df.columns:
            df = df[df["UJAHR"].between(2016, 2025)]
        if "XGCSWGS84" in df.columns:
            df = df[df["XGCSWGS84"].between(5.8, 15.1)]
        if "YGCSWGS84" in df.columns:
            df = df[df["YGCSWGS84"].between(47.2, 55.1)]
        removed = before - len(df)
        print(f"[ETL] Plausibility: removed {removed} rows, {len(df)} remaining")

        # 7. Upsert locations (states)
        location_cache: dict[str, int] = {}
        for ags in df["ags_state"].unique():
            ags = str(ags).zfill(2)
            name = STATE_NAMES.get(ags, f"State {ags}")
            pop  = STATE_POPULATION_2023.get(ags)
            conn.execute(
                """INSERT INTO locations(ags, name, location_type, population)
                   VALUES(?,?,'state',?)
                   ON CONFLICT(ags) DO UPDATE SET population=excluded.population""",
                [ags, name, pop],
            )
        conn.commit()

        for row in conn.execute(
            "SELECT location_id, ags FROM locations WHERE location_type='state'"
        ):
            location_cache[row["ags"]] = row["location_id"]

        # 8 + 9. Insert accident_events + accident_participants in batches
        inserted = 0
        skipped  = 0
        records  = df.to_dict("records")
        BATCH    = 500

        for i in range(0, len(records), BATCH):
            batch = records[i : i + BATCH]
            for r in batch:
                state_ags   = str(r.get("ULAND", "")).zfill(2)
                location_id = location_cache.get(state_ags)
                try:
                    cur = conn.execute(
                        """
                        INSERT INTO accident_events
                            (source_id, year, month, hour, weekday, severity,
                             accident_type, road_type, light_cond,
                             lon, lat, location_id, ags, data_source_id)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(source_id, year) DO NOTHING
                        """,
                        [
                            r.get("UIDENTSTLAE"),
                            r.get("UJAHR"),
                            r.get("UMONAT") or None,
                            r.get("USTUNDE") or None,
                            r.get("UWOCHENTAG") or None,
                            r.get("UKATEGORIE") or None,
                            r.get("UART") or None,
                            r.get("UTYP1") or None,
                            r.get("ULICHTVERH") or None,
                            r.get("XGCSWGS84"),
                            r.get("YGCSWGS84"),
                            location_id,
                            r.get("ags_full"),
                            ds_id,
                        ],
                    )
                    if cur.rowcount == 0:
                        skipped += 1
                        continue

                    event_id = cur.lastrowid
                    inserted += 1

                    for csv_col, ptype in PARTICIPANT_COLUMNS.items():
                        if int(r.get(csv_col, 0)) == 1:
                            conn.execute(
                                """INSERT INTO accident_participants(event_id, participant_type)
                                   VALUES(?,?) ON CONFLICT DO NOTHING""",
                                [event_id, ptype],
                            )
                except sqlite3.Error as exc:
                    print(f"[ETL] Row error (skipped): {exc}")
                    skipped += 1

            conn.commit()
            done = min(i + BATCH, len(records))
            print(f"[ETL]   {done}/{len(records)} rows processed")

        # 10. Finalise provenance record
        notes = json.dumps(
            {
                "quality_report": quality,
                "plausibility_removed": removed,
                "duplicates_skipped": skipped,
            }
        )
        conn.execute(
            """UPDATE data_sources
               SET run_status='success', records_loaded=?, error_notes=?
               WHERE source_id=?""",
            [inserted, notes, ds_id],
        )
        conn.commit()
        print(f"[ETL] Done: {inserted} inserted, {skipped} skipped")
        return {"inserted": inserted, "skipped": skipped, "plausibility_removed": removed}

    except Exception as exc:
        conn.execute(
            "UPDATE data_sources SET run_status='error', error_notes=? WHERE source_id=?",
            [str(exc), ds_id],
        )
        conn.commit()
        raise
    finally:
        conn.close()
