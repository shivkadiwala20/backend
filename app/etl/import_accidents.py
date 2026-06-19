"""
ETL pipeline — Unfallatlas accident CSV → PostgreSQL.

Steps:
  1. Log data_sources provenance entry (status=running)
  2. Read CSV (utf-8-sig, semicolon delimiter)
  3. Fix German decimal comma in coordinates
  4. Parse integer columns
  5. Build 8-digit AGS
  6. Plausibility filter (year range, Germany bounding box)
  7. Upsert state locations
  8. Batch-insert accident_events (ON CONFLICT DO NOTHING)
  9. Insert accident_participants (normalised — one row per type)
 10. Update data_sources with final count and status
"""

import json
import os

import pandas as pd

from ..database import get_connection
from ..utils.ags import STATE_NAMES, build_ags, PARTICIPANT_COLUMNS


def import_accidents_csv(
    file_path: str,
    source_name: str,
    source_url: str = None,
    license: str = "dl-de/by-2-0",
) -> dict:
    conn = get_connection()

    # 1. Log provenance entry
    row = conn.execute(
        """INSERT INTO data_sources(name, origin_url, file_name, license, run_status)
           VALUES(%s, %s, %s, %s, 'running')
           RETURNING source_id""",
        [source_name, source_url, os.path.basename(file_path), license],
    ).fetchone()
    ds_id = row["source_id"]
    conn.commit()

    try:
        # 2. Read CSV
        df = pd.read_csv(file_path, sep=";", encoding="utf-8-sig", dtype=str, low_memory=False)
        df.columns = [c.strip().lstrip("﻿") for c in df.columns]
        print(f"[ETL] Loaded {len(df)} rows | columns: {list(df.columns[:6])}...")

        # 3. Fix German decimal comma in coordinates
        for col in ("XGCSWGS84", "YGCSWGS84"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].str.replace(",", ".", regex=False), errors="coerce")

        # 4. Parse integer columns
        int_cols = [
            "UJAHR", "UMONAT", "USTUNDE", "UWOCHENTAG", "UKATEGORIE",
            "UART", "UTYP1", "ULICHTVERH",
            "IstRad", "IstPKW", "IstFuss", "IstKrad", "IstGkfz", "IstSonstige",
        ]
        for col in int_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

        # 5. Build AGS
        df["ags_full"]  = df.apply(
            lambda r: build_ags(
                r.get("ULAND", ""), r.get("UREGBEZ", "0"),
                r.get("UKREIS", "00"), r.get("UGEMEINDE", "000"),
            ),
            axis=1,
        )
        df["ags_state"] = df["ags_full"].str[:2]

        # 6. Plausibility filter
        before = len(df)
        df = df[df["UJAHR"].between(2016, 2025)]
        df = df[df["XGCSWGS84"].between(5.8, 15.1)]
        df = df[df["YGCSWGS84"].between(47.2, 55.1)]
        removed = before - len(df)
        print(f"[ETL] Plausibility: removed {removed} rows")

        # 7. Upsert state locations
        for ags in df["ags_state"].unique():
            ags = str(ags).zfill(2)
            name = STATE_NAMES.get(ags, f"State {ags}")
            conn.execute(
                """INSERT INTO locations(ags, name, location_type)
                   VALUES(%s, %s, 'state')
                   ON CONFLICT (ags) DO NOTHING""",
                [ags, name],
            )
        conn.commit()

        location_cache: dict = {}
        for r in conn.execute(
            "SELECT location_id, ags FROM locations WHERE location_type = 'state'"
        ).fetchall():
            location_cache[r["ags"]] = r["location_id"]

        # 8 + 9. Insert events and participants
        inserted = 0
        skipped  = 0
        records  = df.to_dict("records")
        BATCH    = 500

        for i in range(0, len(records), BATCH):
            batch = records[i : i + BATCH]
            for r in batch:
                state_ags   = str(r.get("ULAND", "")).zfill(2)
                location_id = location_cache.get(state_ags)

                # RETURNING tells us whether the row was inserted or skipped by ON CONFLICT
                result_row = conn.execute(
                    """INSERT INTO accident_events
                           (source_id, year, month, hour, weekday, severity,
                            accident_type, road_type, light_cond,
                            lon, lat, location_id, ags, data_source_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (source_id, year) DO NOTHING
                       RETURNING event_id""",
                    [
                        r.get("UIDENTSTLAE"), r.get("UJAHR"), r.get("UMONAT"),
                        r.get("USTUNDE"),     r.get("UWOCHENTAG"), r.get("UKATEGORIE"),
                        r.get("UART"),        r.get("UTYP1"),      r.get("ULICHTVERH"),
                        r.get("XGCSWGS84"),   r.get("YGCSWGS84"),
                        location_id, r.get("ags_full"), ds_id,
                    ],
                ).fetchone()

                if result_row is None:
                    skipped += 1
                    continue

                event_id = result_row["event_id"]
                inserted += 1

                # One participant row per type involved (normalised 3NF design)
                for csv_col, ptype in PARTICIPANT_COLUMNS.items():
                    if int(r.get(csv_col, 0)) == 1:
                        conn.execute(
                            """INSERT INTO accident_participants(event_id, participant_type)
                               VALUES(%s, %s)
                               ON CONFLICT DO NOTHING""",
                            [event_id, ptype],
                        )

            conn.commit()
            print(f"  {min(i + BATCH, len(records))}/{len(records)} processed …")

        # 10. Finalise provenance
        notes = json.dumps({"plausibility_removed": removed, "duplicates_skipped": skipped})
        conn.execute(
            "UPDATE data_sources SET run_status='success', records_loaded=%s, error_notes=%s WHERE source_id=%s",
            [inserted, notes, ds_id],
        )
        conn.commit()
        print(f"[ETL] Done: {inserted} inserted, {skipped} skipped")
        return {"inserted": inserted, "skipped": skipped, "plausibility_removed": removed}

    except Exception as exc:
        conn.execute(
            "UPDATE data_sources SET run_status='error', error_notes=%s WHERE source_id=%s",
            [str(exc), ds_id],
        )
        conn.commit()
        raise
    finally:
        conn.close()
