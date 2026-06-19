"""
Accident endpoints — /api/accidents

GET /api/accidents        filtered + paginated list of accident events
GET /api/accidents/count  same filters, returns only the count
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from ..database import DBConnection, get_db
from ..models.schemas import AccidentCount, AccidentSummary, PaginatedAccidents
from ..utils.ags import resolve_state_ags

router = APIRouter()


@router.get(
    "",
    response_model=PaginatedAccidents,
    summary="List accident events with optional filters",
)
def list_accidents(
    state:       Optional[str] = Query(None),
    year:        Optional[int] = Query(None, ge=2016, le=2025),
    month:       Optional[int] = Query(None, ge=1, le=12),
    weekday:     Optional[int] = Query(None, ge=1, le=7),
    hour:        Optional[int] = Query(None, ge=0, le=23),
    severity:    Optional[int] = Query(None, enum=[1, 2, 3]),
    participant: Optional[str] = Query(
        None, enum=["bicycle", "car", "pedestrian", "motorcycle", "truck", "other"]
    ),
    limit:  int = Query(100, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db: DBConnection = Depends(get_db),
):
    select_params = []
    where_clauses = ["1=1"]
    p_join_sql    = ""

    if participant:
        p_join_sql = "JOIN accident_participants ap ON ap.event_id = ae.event_id AND ap.participant_type = %s"
        select_params.append(participant)

    if state:
        try:
            ags = resolve_state_ags(state)
            where_clauses.append("ae.ags LIKE %s")
            select_params.append(f"{ags}%")
        except ValueError:
            pass

    if year:
        where_clauses.append("ae.year = %s")
        select_params.append(year)

    if month:
        where_clauses.append("ae.month = %s")
        select_params.append(month)

    if weekday:
        where_clauses.append("ae.weekday = %s")
        select_params.append(weekday)

    if hour is not None:
        where_clauses.append("ae.hour = %s")
        select_params.append(hour)

    if severity:
        where_clauses.append("ae.severity = %s")
        select_params.append(severity)

    where_sql = " AND ".join(where_clauses)

    count_row = db.execute(
        f"SELECT COUNT(DISTINCT ae.event_id) AS c FROM accident_events ae {p_join_sql} WHERE {where_sql}",
        select_params,
    ).fetchone()
    total = count_row["c"]

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
        LIMIT %s OFFSET %s
        """,
        select_params + [limit, offset],
    ).fetchall()

    items = []
    for r in rows:
        ptypes = [
            p["participant_type"]
            for p in db.execute(
                "SELECT participant_type FROM accident_participants WHERE event_id=%s",
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
    summary="Count accident events matching filters",
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
    db: DBConnection = Depends(get_db),
):
    select_params = []
    where_clauses = ["1=1"]
    p_join_sql    = ""

    if participant:
        p_join_sql = "JOIN accident_participants ap ON ap.event_id = ae.event_id AND ap.participant_type = %s"
        select_params.append(participant)

    if state:
        try:
            ags = resolve_state_ags(state)
            where_clauses.append("ae.ags LIKE %s")
            select_params.append(f"{ags}%")
        except ValueError:
            pass

    if year:
        where_clauses.append("ae.year = %s")
        select_params.append(year)

    if month:
        where_clauses.append("ae.month = %s")
        select_params.append(month)

    if weekday:
        where_clauses.append("ae.weekday = %s")
        select_params.append(weekday)

    if hour is not None:
        where_clauses.append("ae.hour = %s")
        select_params.append(hour)

    if severity:
        where_clauses.append("ae.severity = %s")
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
