"""Load the demo sample data + users into the configured database.

Idempotent-ish convenience for demo deploys (e.g. Render free tier):
    cd backend && python -m app.seed_demo
Runs the two SQL seed files against DATABASE_URL.
"""
import pathlib
from sqlalchemy import text
from .database import engine

REPO = pathlib.Path(__file__).resolve().parents[2]
SEEDS = [REPO / "db" / "seeds" / "0001_sample_data.sql",
         REPO / "db" / "seeds" / "0002_users.sql"]


def main() -> None:
    with engine.begin() as conn:
        for f in SEEDS:
            print(f"applying {f.name}…")
            conn.execute(text(f.read_text()))
    print("demo data + users loaded.")


if __name__ == "__main__":
    main()
