# GeoBuilding SP — Main API

## Overview

GeoBuilding SP is a geospatial MVP that retrieves building footprints from the City of São Paulo's GeoSampa platform for a user-defined area of interest.

The application receives a polygon or multipolygon, communicates with a secondary spatial-processing API, and returns building geometries enriched with cadastral information from active fiscal lots.

The Main API also stores analysis metadata and results using SQLite, allowing previous analyses to be listed, retrieved, updated, and deleted.

The project follows a service-oriented architecture composed of:

- Main API
- Spatial API
- GeoSampa WFS external service
- SQLite database

The architecture follows the proposed **Scenario 2.1**, where the Main API operates as an entry point/proxy and communicates with a secondary API responsible for business logic and external-service communication.

---

## Objective

The objective of this application is to simplify access to GeoSampa geospatial data for a user-defined area.

Given a GeoJSON polygon, the system:

1. receives the area of interest;
2. sends it to the Spatial API;
3. retrieves building footprints from GeoSampa;
4. retrieves active cadastral lots from GeoSampa;
5. spatially associates buildings with cadastral lots;
6. enriches the building geometries with land-use information;
7. returns the resulting features as GeoJSON;
8. persists analysis metadata in SQLite;
9. saves generated GeoJSON files locally.

A typical use case is obtaining the number and geometry of buildings in a given area and identifying the cadastral use associated with those buildings, such as residential or non-residential use.

---

## Architecture

![GeoBuilding SP architecture](docs/miro_architecture.png)

The system contains three main service components:

```text
Client
  |
  | REST
  v
Main API
  |
  |---- SQLite
  |
  | REST
  v
Spatial API
  |
  | WFS
  v
GeoSampa
```

### Main API

The Main API is implemented using FastAPI.

Responsibilities:

- receive requests from the client;
- provide the public REST interface;
- call the Spatial API;
- persist analysis metadata in SQLite;
- provide CRUD operations for saved analyses;
- expose health information.

Default port:

```text
8000
```

Swagger:

```text
http://localhost:8000/docs
```