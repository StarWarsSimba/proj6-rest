# Project 6: Brevet Time Calculator Service (REST)

Flask REST API + MongoDB + PHP consumer for ACP brevet open/close times. Extends Project 5 with `listAll` / `listOpenOnly` / `listCloseOnly` endpoints in JSON and CSV, plus `?top=k` filtering and a separate consumer container.

Skeleton by Michal Young for CIS 322. RUSA rules: https://rusa.org/octime_acp.html

## Overview

Three Docker Compose services (`DockerRestAPI/docker-compose.yml`):

* `laptop-service` (`DockerRestAPI/laptop/api.py`, host `:5001` -> container `:80`) — Flask REST API, computes times via `acp_times.py`, stores brevets in MongoDB `brevetdb.brevets`.
* `website` (`php:apache`, host `:5002`) — consumer: `index.html` calculator + submit form, `controls.html` display via jQuery `getJSON`.
* `db` (`mongo:7.0`) — persistence.

Flow: enter controls on `:5002` (Ajax `GET /_calc_times` for live open/close) -> `POST /submit` saves `{distance, begin_date, begin_time, controls:[{km, mi, location, open, close}]}` -> view on `controls.html?view=all|open|close`.

## API (`laptop/api.py`)

Default representation is JSON.

| Endpoint | Description |
|----------|-------------|
| `GET /listAll`, `/listAll/json` | All brevets, full controls |
| `GET /listAll/csv` | Same in CSV |
| `GET /listOpenOnly`, `/listOpenOnly/json`, `/listOpenOnly/csv` | Controls with only `open` |
| `GET /listCloseOnly`, `/listCloseOnly/json`, `/listCloseOnly/csv` | Controls with only `close` |
| `GET /listOpenOnly/csv?top=3`, `/listOpenOnly/json?top=5`, etc. | Top `k` controls sorted ascending by that field |
| `GET /_calc_times?km=&brevet_distance=&begin_date=YYYY-MM-DD&begin_time=HH:MM` | `{"result":{"open":"...","close":"..."}}` (ISO 8601) |
| `POST /submit` | Form (`distance`, `begin_date`, `begin_time`, `miles[]`, `km[]`, `location[]`), recomputes times server-side, `insert_one`, redirects to `:5002` |

Consumer (`website/`): `index.html` posts to `http://localhost:5001/submit`, fetches `/_calc_times`; `controls.html` fetches `/listAll|listOpenOnly|listCloseOnly` with optional `?top=`, plus CSV download links.

## Running

```bash
cd DockerRestAPI
docker compose up --build
# website: http://localhost:5002
# api e.g.: http://localhost:5001/listAll, http://localhost:5001/listOpenOnly/csv?top=3
docker compose down
```

## Structure

```
DockerRestAPI/docker-compose.yml  # laptop-service (:5001), website (:5002), db
DockerRestAPI/laptop/api.py       # REST API + /submit + /_calc_times
DockerRestAPI/laptop/acp_times.py # open_time / close_time (RUSA rules)
DockerRestAPI/laptop/Dockerfile, requirements.txt, config.py
DockerRestAPI/website/index.html  # calculator + submit
DockerRestAPI/website/controls.html # display (view=all|open|close, top=k, CSV links)
data-samples/                     # sample-data.{json,csv,pivoted.csv} format reference
```

## Author

**Miles Gurney** — CIS 322, University of Oregon — `mgurney@uoregon.edu` — [@StarWarsSimba](https://github.com/StarWarsSimba) — https://github.com/StarWarsSimba/proj6-rest
