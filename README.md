# German Road Accident Data Platform — Backend

Python · FastAPI · SQLite · pandas

## Quick Start

```bash
# 1. Go to backend directory
cd backend

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Place your CSV files in data/
#    Required:
#      data/accident_per_location_2023.csv
#      data/accident_per_location_2021_in_Schleswig-Holstein.csv
#    Optional (for cross-source queries):
#      data/accident_per_10000_per_city.csv
#      data/accidents_with_persons_per_month.csv

# 5. Run ETL (imports data into SQLite)
python -m app.etl.run_etl

# 6. Start the API server
uvicorn app.main:app --reload --port 8000
```

## API Endpoints

| Category | Endpoint | Description |
|---|---|---|
| Health | `GET /health` | API status |
| Locations | `GET /api/locations` | List states/districts |
| Locations | `GET /api/locations/{ags}` | Get location by AGS |
| Accidents | `GET /api/accidents` | Filtered accident list (paginated) |
| Accidents | `GET /api/accidents/count` | Count matching accidents |
| Aggregates | `GET /api/aggregates/dashboard-stats` | Dashboard numbers |
| Aggregates | `GET /api/aggregates/by-location` | Counts by region |
| Aggregates | `GET /api/aggregates/trend` | Year-over-year trend |
| Aggregates | `GET /api/aggregates/top-locations` | Rankings |
| Aggregates | `GET /api/aggregates/participant-breakdown` | By participant type |
| Aggregates | `GET /api/aggregates/zero-accident-locations` | BONUS: zero cases |
| Questions | `GET /api/questions/earliest-year` | Q1 |
| Questions | `GET /api/questions/accidents-by-state-year` | Q2 |
| Questions | `GET /api/questions/earliest-year-by-state` | Q3/Q4 |
| Questions | `GET /api/questions/participant-accidents` | Q5 |
| Questions | `GET /api/questions/rate-per-100k` | Q6 cross-source |
| Questions | `GET /api/questions/trend-by-state` | Q7 time question |
| Provenance | `GET /api/data-sources` | Import history |
| Provenance | `GET /api/indicators` | Statistical indicators |

## Mandatory Test Queries

```bash
curl http://localhost:8000/api/questions/earliest-year
curl "http://localhost:8000/api/questions/accidents-by-state-year?state=Sachsen&year=2023"
curl "http://localhost:8000/api/questions/earliest-year-by-state?state=Nordrhein-Westfalen"
curl "http://localhost:8000/api/questions/earliest-year-by-state?state=Mecklenburg-Vorpommern"
curl "http://localhost:8000/api/questions/participant-accidents?state=Berlin&year=2023&participant_type=pedestrian"
curl "http://localhost:8000/api/questions/rate-per-100k?year=2023&level=state"
```

## Data Sources

| # | Source | Format | License |
|---|---|---|---|
| 1 | Unfallatlas 2023 — opengeodata.nrw.de | CSV | dl-de/by-2-0 |
| 2 | Unfallatlas 2021 Schleswig-Holstein | CSV | dl-de/by-2-0 |
| 3 | Destatis — Bevölkerungsstand 2023 | Hardcoded seed | dl-de/by-2-0 |
| 4 | Fallback — rate per 10,000 per city | CSV | dl-de/by-2-0 |
| 5 | Destatis — monthly statistics | CSV | dl-de/by-2-0 |
