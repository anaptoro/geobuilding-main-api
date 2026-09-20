import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


# =========================================================
# CONFIGURATION
# =========================================================

SPATIAL_API_URL = os.getenv(
    "SPATIAL_API_URL",
    "http://spatial-api:8001",
)

DATABASE_PATH = Path(
    os.getenv(
        "DATABASE_PATH",
        "/app/data/geobuilding.db",
    )
)

RESULTS_DIR = Path(
    os.getenv(
        "RESULTS_DIR",
        "/app/results",
    )
)

DATABASE_PATH.parent.mkdir(
    parents=True,
    exist_ok=True,
)

RESULTS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# =========================================================
# FASTAPI APP
# =========================================================

app = FastAPI(
    title="GeoBuilding SP API",
    description=(
        "Main API for retrieving GeoSampa building footprints "
        "inside a user-defined polygon and persisting analysis "
        "metadata in SQLite."
    ),
    version="0.3.0",
)


# =========================================================
# REQUEST MODELS
# =========================================================

class AnalysisCreateRequest(BaseModel):
    boundary: dict
    name: Optional[str] = None
    description: Optional[str] = None


class AnalysisUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_connection():

    connection = sqlite3.connect(
        DATABASE_PATH
    )

    connection.row_factory = (
        sqlite3.Row
    )

    return connection


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

def initialize_database():

    connection = get_connection()

    try:

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analyses (
                id TEXT PRIMARY KEY,
                name TEXT,
                description TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL,
                boundary_json TEXT NOT NULL,
                total_buildings INTEGER,
                matched_buildings INTEGER,
                unmatched_buildings INTEGER,
                match_percentage REAL,
                summary_json TEXT,
                files_json TEXT
            )
            """
        )

        connection.commit()

    finally:

        connection.close()


initialize_database()


# =========================================================
# DATABASE HELPERS
# =========================================================

def row_to_dict(
    row,
):

    if row is None:
        return None

    result = dict(row)

    # -----------------------------------------------------
    # Decode stored JSON
    # -----------------------------------------------------

    for column in [
        "boundary_json",
        "summary_json",
        "files_json",
    ]:

        if result.get(
            column
        ):

            try:

                decoded = json.loads(
                    result[column]
                )

            except json.JSONDecodeError:

                decoded = None

        else:

            decoded = None

        if column == "boundary_json":
            result["boundary"] = decoded

        elif column == "summary_json":
            result["summary"] = decoded

        elif column == "files_json":
            result["files"] = decoded

        result.pop(
            column,
            None,
        )

    return result


# =========================================================
# ROOT ENDPOINT
# =========================================================

@app.get("/")
def root():

    return {
        "name":
            "GeoBuilding SP API",

        "version":
            "0.3.0",

        "status":
            "running",

        "database":
            str(
                DATABASE_PATH
            ),

        "spatial_api":
            SPATIAL_API_URL,
    }


# =========================================================
# HEALTH ENDPOINT
# =========================================================

@app.get("/health")
def health():

    spatial_api_status = (
        "unknown"
    )

    database_status = (
        "unknown"
    )


    # -----------------------------------------------------
    # Check Spatial API
    # -----------------------------------------------------

    try:

        response = requests.get(
            f"{SPATIAL_API_URL}/health",
            timeout=5,
        )

        if (
            response.status_code
            == 200
        ):

            spatial_api_status = (
                "ok"
            )

        else:

            spatial_api_status = (
                f"error_"
                f"{response.status_code}"
            )

    except requests.RequestException:

        spatial_api_status = (
            "unavailable"
        )


    # -----------------------------------------------------
    # Check SQLite
    # -----------------------------------------------------

    try:

        connection = (
            get_connection()
        )

        connection.execute(
            "SELECT 1"
        )

        connection.close()

        database_status = (
            "ok"
        )

    except sqlite3.Error:

        database_status = (
            "error"
        )


    return {
        "main_api":
            "ok",

        "spatial_api":
            spatial_api_status,

        "database":
            database_status,
    }


# =========================================================
# POST /analyses
# =========================================================
#
# Creates a new analysis.
#
# 1. Sends AOI to Spatial API
# 2. Receives GeoSampa result
# 3. Saves metadata in SQLite
# 4. Returns complete Spatial API result
# =========================================================

@app.post("/analyses")
def create_analysis(
    request: AnalysisCreateRequest,
):

    payload = {
        "boundary":
            request.boundary
    }


    # =====================================================
    # CALL SPATIAL API
    # =====================================================

    try:

        response = requests.post(
            f"{SPATIAL_API_URL}/buildings",
            json=payload,
            timeout=300,
        )

    except requests.Timeout:

        raise HTTPException(
            status_code=504,
            detail=(
                "Spatial API request timed out."
            ),
        )

    except requests.ConnectionError:

        raise HTTPException(
            status_code=503,
            detail=(
                "Spatial API is unavailable."
            ),
        )

    except requests.RequestException as exc:

        raise HTTPException(
            status_code=502,
            detail=(
                "Error communicating with "
                f"Spatial API: {exc}"
            ),
        )


    # =====================================================
    # SPATIAL API ERROR
    # =====================================================

    if (
        response.status_code
        != 200
    ):

        try:

            error_data = (
                response.json()
            )

            detail = (
                error_data.get(
                    "detail",
                    error_data,
                )
            )

        except ValueError:

            detail = (
                response.text
                or
                "Unknown Spatial API error."
            )

        raise HTTPException(
            status_code=
                response.status_code,

            detail=
                detail,
        )


    # =====================================================
    # PARSE RESULT
    # =====================================================

    try:

        spatial_result = (
            response.json()
        )

    except ValueError:

        raise HTTPException(
            status_code=502,
            detail=(
                "Spatial API returned "
                "invalid JSON."
            ),
        )


    # =====================================================
    # READ RESULT METADATA
    # =====================================================

    analysis_id = (
        spatial_result.get(
            "request_id"
        )
    )

    if not analysis_id:

        raise HTTPException(
            status_code=502,
            detail=(
                "Spatial API response does "
                "not contain request_id."
            ),
        )


    summary = (
        spatial_result.get(
            "summary",
            {},
        )
    )

    files = (
        spatial_result.get(
            "files",
            {},
        )
    )


    # =====================================================
    # TIMESTAMPS
    # =====================================================

    now = datetime.now().isoformat(
        timespec="seconds"
    )


    # =====================================================
    # SAVE TO SQLITE
    # =====================================================

    connection = (
        get_connection()
    )

    try:

        connection.execute(
            """
            INSERT INTO analyses (
                id,
                name,
                description,
                created_at,
                updated_at,
                status,
                boundary_json,
                total_buildings,
                matched_buildings,
                unmatched_buildings,
                match_percentage,
                summary_json,
                files_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                analysis_id,

                request.name,

                request.description,

                now,

                now,

                "completed",

                json.dumps(
                    request.boundary,
                    ensure_ascii=False,
                ),

                summary.get(
                    "total_buildings"
                ),

                summary.get(
                    "matched_to_active_lot"
                ),

                summary.get(
                    "without_active_lot_match"
                ),

                summary.get(
                    "match_percentage"
                ),

                json.dumps(
                    summary,
                    ensure_ascii=False,
                ),

                json.dumps(
                    files,
                    ensure_ascii=False,
                ),
            ),
        )

        connection.commit()

    except sqlite3.IntegrityError:

        raise HTTPException(
            status_code=409,
            detail=(
                f"Analysis {analysis_id} "
                "already exists."
            ),
        )

    finally:

        connection.close()


    # =====================================================
    # ADD METADATA TO RESPONSE
    # =====================================================

    spatial_result[
        "analysis"
    ] = {
        "id":
            analysis_id,

        "name":
            request.name,

        "description":
            request.description,

        "created_at":
            now,

        "status":
            "completed",
    }


    return spatial_result


# =========================================================
# BACKWARD-COMPATIBLE POST /analysis
# =========================================================
#
# Keeps your existing workflow working.
# Internally behaves exactly like POST /analyses.
# =========================================================

@app.post("/analysis")
def create_analysis_legacy(
    request: AnalysisCreateRequest,
):

    return create_analysis(
        request
    )


# =========================================================
# GET /analyses
# =========================================================
#
# Lists all saved analyses.
# =========================================================

@app.get("/analyses")
def list_analyses():

    connection = (
        get_connection()
    )

    try:

        rows = connection.execute(
            """
            SELECT *
            FROM analyses
            ORDER BY created_at DESC
            """
        ).fetchall()

    finally:

        connection.close()


    return {
        "count":
            len(rows),

        "analyses":
            [
                row_to_dict(
                    row
                )
                for row
                in rows
            ],
    }


# =========================================================
# GET /analyses/{analysis_id}
# =========================================================

@app.get(
    "/analyses/{analysis_id}"
)
def get_analysis(
    analysis_id: str,
):

    connection = (
        get_connection()
    )

    try:

        row = connection.execute(
            """
            SELECT *
            FROM analyses
            WHERE id = ?
            """,
            (
                analysis_id,
            ),
        ).fetchone()

    finally:

        connection.close()


    if row is None:

        raise HTTPException(
            status_code=404,
            detail=(
                f"Analysis "
                f"{analysis_id} "
                "not found."
            ),
        )


    return row_to_dict(
        row
    )


# =========================================================
# PUT /analyses/{analysis_id}
# =========================================================
#
# Updates editable metadata.
#
# We intentionally do NOT change:
# - geometry
# - result
# - building counts
#
# because those belong to the original analysis.
# =========================================================

@app.put(
    "/analyses/{analysis_id}"
)
def update_analysis(
    analysis_id: str,
    request: AnalysisUpdateRequest,
):

    connection = (
        get_connection()
    )

    try:

        existing = (
            connection.execute(
                """
                SELECT *
                FROM analyses
                WHERE id = ?
                """,
                (
                    analysis_id,
                ),
            ).fetchone()
        )

        if existing is None:

            raise HTTPException(
                status_code=404,
                detail=(
                    f"Analysis "
                    f"{analysis_id} "
                    "not found."
                ),
            )


        current_name = (
            existing["name"]
        )

        current_description = (
            existing[
                "description"
            ]
        )


        new_name = (
            request.name
            if request.name
            is not None
            else current_name
        )

        new_description = (
            request.description
            if request.description
            is not None
            else current_description
        )


        updated_at = (
            datetime.now()
            .isoformat(
                timespec="seconds"
            )
        )


        connection.execute(
            """
            UPDATE analyses
            SET
                name = ?,
                description = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                new_name,

                new_description,

                updated_at,

                analysis_id,
            ),
        )

        connection.commit()


        updated = (
            connection.execute(
                """
                SELECT *
                FROM analyses
                WHERE id = ?
                """,
                (
                    analysis_id,
                ),
            ).fetchone()
        )

    finally:

        connection.close()


    return row_to_dict(
        updated
    )


# =========================================================
# DELETE /analyses/{analysis_id}
# =========================================================
#
# Deletes:
#
# 1. database record
# 2. generated GeoJSON / summary files
#
# if those files exist.
# =========================================================

@app.delete(
    "/analyses/{analysis_id}"
)
def delete_analysis(
    analysis_id: str,
):

    connection = (
        get_connection()
    )

    try:

        row = connection.execute(
            """
            SELECT *
            FROM analyses
            WHERE id = ?
            """,
            (
                analysis_id,
            ),
        ).fetchone()


        if row is None:

            raise HTTPException(
                status_code=404,
                detail=(
                    f"Analysis "
                    f"{analysis_id} "
                    "not found."
                ),
            )


        analysis = row_to_dict(
            row
        )

        files = (
            analysis.get(
                "files"
            )
            or
            {}
        )


        # -------------------------------------------------
        # Delete result files
        # -------------------------------------------------

        deleted_files = []

        for filename in (
            files.values()
        ):

            if not filename:
                continue

            file_path = (
                RESULTS_DIR
                /
                filename
            )

            if file_path.exists():

                file_path.unlink()

                deleted_files.append(
                    filename
                )


        # -------------------------------------------------
        # Delete database row
        # -------------------------------------------------

        connection.execute(
            """
            DELETE FROM analyses
            WHERE id = ?
            """,
            (
                analysis_id,
            ),
        )

        connection.commit()

    finally:

        connection.close()


    return {
        "message":
            "Analysis deleted successfully.",

        "analysis_id":
            analysis_id,

        "deleted_files":
            deleted_files,
    }