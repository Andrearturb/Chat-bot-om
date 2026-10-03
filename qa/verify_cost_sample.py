"""Valida uma extração FBL3N contra o dCentros atual sem alterar o banco operacional.

Uso no container backend: python /tmp/verify_cost_sample.py /tmp/EXPORT_20261002_160635.XLSX
"""

from collections import defaultdict
from decimal import Decimal
from pathlib import Path
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models.registry  # noqa: F401
from app.db.base import Base
from app.db.session import SessionLocal
from app.models.maintenance_cost import MaintenanceCost
from app.models.tape_center import TapeCenter
from app.models.upload import Upload
from app.services.maintenance_costs_importer import import_maintenance_costs


def main(path: Path) -> None:
    with SessionLocal() as live:
        centers = [
            {name: getattr(center, name) for name in (
                "record_id", "unique_number", "title", "name", "sap_number",
                "cost_center", "status", "praca",
            )}
            for center in live.query(TapeCenter).all()
        ]
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as isolated:
        isolated.add(Upload(id=1, source_file_name="dCentros para validação", total_rows=0))
        isolated.flush()
        isolated.add_all(TapeCenter(**center, upload_id=1) for center in centers)
        isolated.flush()
        result = import_maintenance_costs(isolated, path.read_bytes(), path.name)
        isolated.flush()
        groups = defaultdict(lambda: {"count": 0, "amount": Decimal()})
        for row in isolated.query(MaintenanceCost).all():
            group = groups[row.attribution_source or "unattributed"]
            group["count"] += 1
            group["amount"] += row.amount
        print(f"centers={len(centers)} rows={result['total_rows']} rejected={result['rejected']}")
        for source, stats in sorted(groups.items()):
            print(f"{source}: {stats['count']} rows; {stats['amount']:.2f}")
        print(f"total={sum((group['amount'] for group in groups.values()), Decimal()):.2f}")
    engine.dispose()


if __name__ == "__main__":
    main(Path(sys.argv[1]))
