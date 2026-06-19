"""
Accident endpoints — /api/accidents

GET /api/accidents        filtered + paginated list of accident events
GET /api/accidents/count  same filters, returns only the count
"""

import sqlite3
from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from ..database import get_db
from ..models.schemas import AccidentCount, AccidentSummary, PaginatedAccidents
from ..utils.ags import resolve_state_ags

router = APIRouter()


def _build_where(state, year, month, weekday, hour, severity, participant):
    """Build the WHERE clause and params list for accident queries."""
    clauses = ["1=1"]
    params  = []

    if state:
        try:
            ags = resolve_state_ags(state)
            clauses.append("ae.ags LIKE ?")
            params.append(f"{ags}%")
        except ValueError:
            pass

    if year:
        clauses.append("ae.year = ?")
        params.append(year)

    if month:
        clauses.append("ae.month = ?")
        params.append(month)

    if weekday:
        clauses.append("ae.weekday = ?")
        params.append(weekday)

    if hour is not None:
        clauses.append("ae.hour = ?")
        params.append(hour)

    if severity:
        clauses.append("ae.severity = ?")
        params.append(severity)

    # participant filter uses normalised table — JOIN required
    participant_join = ""
    if participant:
        participant_join = (
            "JOIN accident_participants ap ON ap.event_id = ae.event_id "
            f"AND ap.participant_type = ?"
        )
        params.insert(0 if not state else len(params), participant)

    return " AND ".join(clauses), params, participant_join


@router.get(
    "",
    response_model=PaginatedAccidents,
    summary="List accident events with optional filters",
)
def list_accidents(
    state:       Optional[str] = Query(None, description="State name or AGS code"),
    year:        Optional[int] = Query(None, ge=2016, le=2025),
    month:       Optional[int] = Query(None, ge=1, le=12),
    weekday:     Optional[int] = Query(None, ge=1, le=7, description="1=Sunday … 7=Saturday"),
    hour:        Optional[int] = Query(None, ge=0, le=23),
    severity:    Optional[int] = Query(None, enum=[1, 2, 3], description="1=fatal,2=severe,3=light"),
    participant: Optional[str] = Query(
        None,
        enum=["bicycle", "car", "pedestrian", "motorcycle", "truck", "other"],
    ),
    limit:  int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: sqlite3.Connection = Depends(get_db),
):
    where, params, p_join = _build_where(state, year, month, weekday, hour, severity, participant)

    # Build params correctly: participant param must be before state params if join is present
    select_params = []
    where_clauses = ["1=1"]
    p_join_sql = ""

    if participant:
        p_join_sql = "JOIN accident_participants ap ON ap.event_id = ae.event_id AND ap.participant_type = ?"
        select_params.append(participant)

    if state:
        try:
            ags = resolve_state_ags(state)
            where_clauses.append("ae.ags LIKE ?")
            select_params.append(f"{ags}%")
        except ValueError:
            pass

    if year:
        where_clauses.append("ae.year = ?")
        select_params.append(year)

    if month:
        where_clauses.append("ae.month = ?")
        select_params.append(month)

    if weekday:
        where_clauses.append("ae.weekday = ?")
        select_params.append(weekday)

    if hour is not None:
        where_clauses.append("ae.hour = ?")
        select_params.append(hour)

    if severity:
        where_clauses.append("ae.severity = ?")
        select_params.append(severity)

    where_sql = " AND ".join(where_clauses)

    # Count
    count_row = db.execute(
        f"SELECT COUNT(DISTINCT ae.event_id) AS c FROM accident_events ae {p_join_sql} WHERE {where_sql}",
        select_params,
    ).fetchone()
    total = count_row["c"]

    # Fetch rows
    rows = db.execute(
        f"""
        SELECT DISTINCT
            ae.event_id, ae.year, ae.month, ae.hour, ae.weekday,
            ae.severity, ae.accident_type, ae.road_type, ae.light_cond,
            ae.ags, ae.lon, ae.lat
        FROM accident_events ae
        {p_join_sql}
        WHERE {where_sql}
        ORDER BY ae.year DESC, ae.event_id DESC
        LIMIT ? OFFSET ?
        """,
        select_params + [limit, offset],
    ).fetchall()

    # Attach participants list for each event
    items = []
    for r in rows:
        ptypes = [
            p["participant_type"]
            for p in db.execute(
                "SELECT participant_type FROM accident_participants WHERE event_id=?",
                [r["event_id"]],
            ).fetchall()
        ]
        items.append(
            AccidentSummary(
                event_id=r["event_id"],
                year=r["year"],
                month=r["month"],
                hour=r["hour"],
                weekday=r["weekday"],
                severity=r["severity"],
                accident_type=r["accident_type"],
                road_type=r["road_type"],
                light_cond=r["light_cond"],
                ags=r["ags"],
                lon=r["lon"],
                lat=r["lat"],
                participants=ptypes,
            )
        )

    return PaginatedAccidents(total=total, limit=limit, offset=offset, items=items)


@router.get(
    "/count",
    response_model=AccidentCount,
    summary="Count accident events matching filters (same params as /api/accidents)",
)
def count_accidents(
    state:       Optional[str] = Query(None),
    year:        Optional[int] = Query(None, ge=2016, le=2025),
    month:       Optional[int] = Query(None, ge=1, le=12),
    weekday:     Optional[int] = Query(None, ge=1, le=7),
    hour:        Optional[int] = Query(None, ge=0, le=23),
    severity:    Optional[int] = Query(None, enum=[1, 2, 3]),
    participant: Optional[str] = Query(
        None, enum=["bicycle", "car", "pedestrian", "motorcycle", "truck", "other"]
    ),
    db: sqlite3.Connection = Depends(get_db),
):
    select_params = []
    where_clauses = ["1=1"]
    p_join_sql = ""

    if participant:
        p_join_sql = "JOIN accident_participants ap ON ap.event_id = ae.event_id AND ap.participant_type = ?"
        select_params.append(participant)

    if state:
        try:
            ags = resolve_state_ags(state)
            where_clauses.append("ae.ags LIKE ?")
            select_params.append(f"{ags}%")
        except ValueError:
            pass

    if year:
        where_clauses.append("ae.year = ?")
        select_params.append(year)

    if month:
        where_clauses.append("ae.month = ?")
        select_params.append(month)

    if weekday:
        where_clauses.append("ae.weekday = ?")
        select_params.append(weekday)

    if hour is not None:
        where_clauses.append("ae.hour = ?")
        select_params.append(hour)

    if severity:
        where_clauses.append("ae.severity = ?")
        select_params.append(severity)

    where_sql = " AND ".join(where_clauses)

    row = db.execute(
        f"SELECT COUNT(DISTINCT ae.event_id) AS c FROM accident_events ae {p_join_sql} WHERE {where_sql}",
        select_params,
    ).fetchone()

    filters = {k: v for k, v in {
        "state": state, "year": year, "month": month,
        "weekday": weekday, "hour": hour,
        "severity": severity, "participant": participant,
    }.items() if v is not None}

    return AccidentCount(count=row["c"], filters_applied=filters)
