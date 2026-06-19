"""
Aggregate endpoints — /api/aggregates/*

GET /by-location            accident counts grouped by region
GET /trend                  year-over-year trend for an AGS
GET /top-locations          ranking by count or rate
GET /participant-breakdown  breakdown by participant type
GET /zero-accident-locations BONUS: locations with zero accidents in a year
GET /dashboard-stats        quick numbers for the frontend dashboard
"""

import sqlite3
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..database import get_db
from ..models.schemas import (
    AggregateRow,
    DashboardStats,
    ParticipantBreakdown,
    RankingRow,
    TrendPoint,
    ZeroAccidentLocation,
)
from ..utils.ags import resolve_state_ags

router = APIRouter()


@router.get(
    "/dashboard-stats",
    response_model=DashboardStats,
    summary="Quick summary statistics for the dashboard",
)
def dashboard_stats(db: sqlite3.Connection = Depends(get_db)):
    total   = db.execute("SELECT COUNT(*) AS c FROM accident_events").fetchone()["c"]
    states  = db.execute("SELECT COUNT(*) AS c FROM locations WHERE location_type='state' AND ags != '00'").fetchone()["c"]
    dists   = db.execute("SELECT COUNT(*) AS c FROM locations WHERE location_type='district'").fetchone()["c"]
    yr_row  = db.execute("SELECT MIN(year) AS mn, MAX(year) AS mx FROM accident_events").fetchone()
    src_row = db.execute("SELECT MAX(retrieved_at) AS la FROM data_sources WHERE run_status='success'").fetchone()
    return DashboardStats(
        total_accidents=total,
        total_states=states,
        total_districts=dists,
        year_range={"min": yr_row["mn"], "max": yr_row["mx"]},
        latest_import=src_row["la"],
    )


@router.get(
    "/by-location",
    response_model=List[AggregateRow],
    summary="Accident counts per region with optional population rate",
)
def by_location(
    level:    str           = Query("state", enum=["state", "district"]),
    year:     Optional[int] = Query(None, ge=2016, le=2025),
    severity: Optional[int] = Query(None, enum=[1, 2, 3]),
    participant: Optional[str] = Query(
        None, enum=["bicycle", "car", "pedestrian", "motorcycle", "truck", "other"]
    ),
    db: sqlite3.Connection = Depends(get_db),
):
    where  = ["l.location_type = ?"]
    params = [level]
    p_join = ""

    if year:
        where.append("ae.year = ?")
        params.append(year)

    if severity:
        where.append("ae.severity = ?")
        params.append(severity)

    if participant:
        p_join = "JOIN accident_participants ap ON ap.event_id = ae.event_id AND ap.participant_type = ?"

    yr_val = year if year else 2023
    where_sql = " AND ".join(where)

    # Param order: [participant?] [yr_val for SELECT] [yr_val for sv JOIN] [level, year?, severity?]
    sql_params = (
        ([participant] if participant else [])
        + [yr_val, yr_val]
        + params          # [level] + optional [year] + optional [severity]
    )

    rows = db.execute(
        f"""
        SELECT
            l.ags, l.name,
            COALESCE(ae.year, ?) AS year,
            COUNT(DISTINCT ae.event_id) AS accident_count,
            sv.value AS population,
            CASE WHEN sv.value > 0
                 THEN ROUND(CAST(COUNT(DISTINCT ae.event_id) AS REAL) / sv.value * 100000, 2)
                 ELSE NULL END AS rate_per_100k
        FROM locations l
        LEFT JOIN accident_events ae ON ae.location_id = l.location_id
        {p_join}
        LEFT JOIN statistical_values sv
               ON sv.location_id = l.location_id
              AND sv.indicator_id = (SELECT indicator_id FROM statistical_indicators WHERE code='population' LIMIT 1)
              AND sv.year = ?
        WHERE {where_sql}
        GROUP BY l.ags, l.name
        ORDER BY accident_count DESC
        """,
        sql_params,
    ).fetchall()

    return [
        AggregateRow(
            ags=r["ags"],
            name=r["name"],
            year=r["year"] or yr_val,
            accident_count=r["accident_count"],
            population=r["population"],
            rate_per_100k=r["rate_per_100k"],
        )
        for r in rows
    ]


@router.get(
    "/trend",
    response_model=List[TrendPoint],
    summary="Year-over-year accident count trend for an AGS region",
)
def trend(
    ags:        str = Query(..., description="2-digit state or 5-digit district AGS"),
    start_year: int = Query(2016, ge=2016, le=2025),
    end_year:   int = Query(2025, ge=2016, le=2025),
    db: sqlite3.Connection = Depends(get_db),
):
    rows = db.execute(
        """
        SELECT year, COUNT(*) AS count
        FROM accident_events
        WHERE ags LIKE ? AND year BETWEEN ? AND ?
        GROUP BY year ORDER BY year
        """,
        [f"{ags}%", start_year, end_year],
    ).fetchall()
    return [TrendPoint(year=r["year"], count=r["count"]) for r in rows]


@router.get(
    "/top-locations",
    response_model=List[RankingRow],
    summary="Top/bottom regions ranked by accident count or rate per 100k",
)
def top_locations(
    year:   int = Query(2023, ge=2016, le=2025),
    level:  str = Query("state", enum=["state", "district"]),
    limit:  int = Query(10, ge=1, le=50),
    metric: str = Query("count", enum=["count", "rate"]),
    order:  str = Query("desc", enum=["asc", "desc"]),
    db: sqlite3.Connection = Depends(get_db),
):
    direction = "DESC" if order == "desc" else "ASC"
    order_col = "rate_per_100k" if metric == "rate" else "accident_count"

    rows = db.execute(
        f"""
        SELECT
            l.ags, l.name,
            COUNT(ae.event_id) AS accident_count,
            sv.value AS population,
            CASE WHEN sv.value > 0
                 THEN ROUND(CAST(COUNT(ae.event_id) AS REAL) / sv.value * 100000, 2)
                 ELSE NULL END AS rate_per_100k
        FROM accident_events ae
        JOIN locations l ON ae.location_id = l.location_id
        LEFT JOIN statistical_values sv
               ON sv.location_id = l.location_id AND sv.year = ae.year
              AND sv.indicator_id = (SELECT indicator_id FROM statistical_indicators WHERE code='population' LIMIT 1)
        WHERE l.location_type = ? AND ae.year = ?
        GROUP BY l.ags, l.name, sv.value
        ORDER BY {order_col} {direction} NULLS LAST
        LIMIT ?
        """,
        [level, year, limit],
    ).fetchall()

    return [
        RankingRow(
            rank=i + 1,
            ags=r["ags"],
            name=r["name"],
            accident_count=r["accident_count"],
            population=r["population"],
            rate_per_100k=r["rate_per_100k"],
        )
        for i, r in enumerate(rows)
    ]


@router.get(
    "/participant-breakdown",
    response_model=ParticipantBreakdown,
    summary="Count accidents per participant type for a given year and optional state",
)
def participant_breakdown(
    year:  int           = Query(2023, ge=2016, le=2025),
    state: Optional[str] = Query(None, description="State name or AGS (optional)"),
    db: sqlite3.Connection = Depends(get_db),
):
    where  = ["ae.year = ?"]
    params = [year]

    if state:
        try:
            ags = resolve_state_ags(state)
            where.append("ae.ags LIKE ?")
            params.append(f"{ags}%")
        except ValueError:
            pass

    where_sql = " AND ".join(where)

    rows = db.execute(
        f"""
        SELECT ap.participant_type, COUNT(DISTINCT ae.event_id) AS cnt
        FROM accident_events ae
        JOIN accident_participants ap ON ap.event_id = ae.event_id
        WHERE {where_sql}
        GROUP BY ap.participant_type
        """,
        params,
    ).fetchall()

    breakdown = {r["participant_type"]: r["cnt"] for r in rows}
    return ParticipantBreakdown(
        bicycle=breakdown.get("bicycle", 0),
        car=breakdown.get("car", 0),
        pedestrian=breakdown.get("pedestrian", 0),
        motorcycle=breakdown.get("motorcycle", 0),
        truck=breakdown.get("truck", 0),
        other=breakdown.get("other", 0),
    )


@router.get(
    "/zero-accident-locations",
    response_model=List[ZeroAccidentLocation],
    summary="BONUS: Locations with zero recorded accidents in a given year",
    description=(
        "Returns locations that have no accident_events in the given year. "
        "Requires a full region reference (locations table) — not just event rows."
    ),
)
def zero_accident_locations(
    year:  int           = Query(2023, ge=2016, le=2025),
    level: str           = Query("state", enum=["state", "district", "municipality"]),
    state: Optional[str] = Query(None, description="Filter to locations within a state"),
    limit: int           = Query(100, ge=1, le=500),
    db: sqlite3.Connection = Depends(get_db),
):
    where  = ["l.location_type = ?"]
    params: list = [level]

    if state:
        try:
            ags = resolve_state_ags(state)
            where.append("l.ags LIKE ?")
            params.append(f"{ags}%")
        except ValueError:
            pass

    where_sql = " AND ".join(where)

    rows = db.execute(
        f"""
        SELECT l.ags, l.name, l.location_type
        FROM locations l
        WHERE {where_sql}
          AND l.location_id NOT IN (
              SELECT DISTINCT location_id
              FROM accident_events
              WHERE year = ? AND location_id IS NOT NULL
          )
          AND l.ags != '00'
        ORDER BY l.name
        LIMIT ?
        """,
        params + [year, limit],
    ).fetchall()

    return [
        ZeroAccidentLocation(ags=r["ags"], name=r["name"], location_type=r["location_type"])
        for r in rows
    ]
