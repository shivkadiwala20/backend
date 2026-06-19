from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel


class LocationResponse(BaseModel):
    location_id: int
    ags: str
    name: str
    location_type: str
    parent_ags: Optional[str] = None
    population: Optional[int] = None
    area_km2: Optional[float] = None


class ParticipantBreakdown(BaseModel):
    bicycle: int = 0
    car: int = 0
    pedestrian: int = 0
    motorcycle: int = 0
    truck: int = 0
    other: int = 0


class AccidentSummary(BaseModel):
    event_id: int
    year: int
    month: Optional[int] = None
    hour: Optional[int] = None
    weekday: Optional[int] = None
    severity: Optional[int] = None
    accident_type: Optional[int] = None
    road_type: Optional[int] = None
    light_cond: Optional[int] = None
    ags: Optional[str] = None
    lon: Optional[float] = None
    lat: Optional[float] = None
    participants: List[str] = []


class PaginatedAccidents(BaseModel):
    total: int
    limit: int
    offset: int
    items: List[AccidentSummary]


class AccidentCount(BaseModel):
    count: int
    filters_applied: dict


class EarliestYearResponse(BaseModel):
    earliest_year: int
    source: str = "Unfallatlas (imported)"
    license: str = "dl-de/by-2-0"


class EarliestYearByStateResponse(BaseModel):
    state: str
    ags: str
    earliest_year: int
    license: str = "dl-de/by-2-0"


class AccidentsByStateYearResponse(BaseModel):
    state: str
    ags: str
    year: int
    accident_count: int
    source_license: str = "dl-de/by-2-0"


class ParticipantAccidentsResponse(BaseModel):
    state: str
    ags: str
    year: int
    participant_type: str
    accident_count: int
    license: str = "dl-de/by-2-0"


class AggregateRow(BaseModel):
    ags: str
    name: str
    year: int
    accident_count: int
    population: Optional[int] = None
    rate_per_100k: Optional[float] = None


class RankingRow(BaseModel):
    rank: int
    ags: str
    name: str
    accident_count: int
    population: Optional[int] = None
    rate_per_100k: Optional[float] = None


class TrendPoint(BaseModel):
    year: int
    count: int


class RatePer100kResponse(BaseModel):
    year: int
    level: str
    license: str = "dl-de/by-2-0"
    ranking: List[RankingRow]


class DataSourceResponse(BaseModel):
    source_id: int
    name: str
    origin_url: Optional[str] = None
    file_name: Optional[str] = None
    license: Optional[str] = None
    retrieved_at: Optional[datetime] = None
    records_loaded: Optional[int] = None
    run_status: str


class IndicatorResponse(BaseModel):
    indicator_id: int
    code: str
    label: str
    unit: Optional[str] = None
    source_system: Optional[str] = None


class ZeroAccidentLocation(BaseModel):
    ags: str
    name: str
    location_type: str


class DashboardStats(BaseModel):
    total_accidents: int
    total_states: int
    total_districts: int
    year_range: dict
    latest_import: Optional[datetime] = None
