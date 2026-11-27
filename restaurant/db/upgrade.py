"""Apply reviewed incremental PostgreSQL migrations, never during web startup."""
import argparse
import os
from pathlib import Path

import psycopg


def upgrade(database_url, through, *, dry_run=False):
    directory = Path(__file__).with_name("migrations")
    applied = []
    with psycopg.connect(database_url, autocommit=True) as db:
        if db.execute("SELECT to_regclass('reservation_schema_versions')").fetchone()[0] is None:
            raise RuntimeError("Apply the initial reservation schema (002) before this upgrade command.")
        versions = {row[0] for row in db.execute("SELECT version FROM reservation_schema_versions")}
        if 5 not in versions:
            raise RuntimeError("This release requires baseline migration 005.")
        for path in sorted(directory.glob("*.sql")):
            version = int(path.name.split("_",1)[0])
            if version <= 5 or version > through or version in versions:
                continue
            if not dry_run:
                db.execute(path.read_text(encoding="utf-8"))
            applied.append(path.name)
    return applied


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--through", type=int, choices=(6,7,8), default=8)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    url = os.environ.get("DATABASE_URL")
    if not url:
        parser.error("Set DATABASE_URL securely before running migrations.")
    for name in upgrade(url, args.through, dry_run=args.dry_run):
        print(("Planned: " if args.dry_run else "Applied: ") + name)


if __name__ == "__main__":
    main()
