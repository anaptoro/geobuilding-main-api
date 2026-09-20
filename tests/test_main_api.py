import os
import tempfile
from pathlib import Path


# =========================================================
# TEST ENVIRONMENT
# =========================================================
#
# The production app normally uses:
#
#   /app/data
#   /app/results
#
# inside Docker.
#
# For local pytest execution, use a temporary directory
# instead.
# =========================================================

TEST_DIR = Path(
    tempfile.mkdtemp(
        prefix="geobuilding_main_api_test_"
    )
)

TEST_DATABASE = (
    TEST_DIR
    / "geobuilding_test.db"
)

TEST_RESULTS = (
    TEST_DIR
    / "results"
)

TEST_RESULTS.mkdir(
    parents=True,
    exist_ok=True,
)


os.environ["DATABASE_PATH"] = str(
    TEST_DATABASE
)

os.environ["RESULTS_DIR"] = str(
    TEST_RESULTS
)


# =========================================================
# IMPORT APP AFTER ENVIRONMENT VARIABLES
# =========================================================

from fastapi.testclient import TestClient

from main_api.main import app


client = TestClient(app)


# =========================================================
# TESTS
# =========================================================

def test_root():

    response = client.get("/")

    assert response.status_code == 200

    data = response.json()

    assert (
        data["name"]
        == "GeoBuilding SP API"
    )

    assert (
        data["status"]
        == "running"
    )


def test_list_analyses():

    response = client.get(
        "/analyses"
    )

    assert response.status_code == 200

    data = response.json()

    assert "count" in data
    assert "analyses" in data

    assert isinstance(
        data["analyses"],
        list,
    )


def test_missing_analysis_returns_404():

    response = client.get(
        "/analyses/does-not-exist"
    )

    assert response.status_code == 404

    data = response.json()

    assert (
        "not found"
        in data["detail"].lower()
    )