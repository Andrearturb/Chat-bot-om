"""Carga administrativa local de uma extração FBL3N, sem interface de upload.

Uso dentro do container: python -m scripts.import_cost_file /tmp/EXPORT_20261002_160635.XLSX
O fluxo automático deve usar POST /imports/costs com sessão e x-api-key.
"""

import sys
from pathlib import Path

from app.db.session import SessionLocal
from app.services.auth import record_audit
from app.services.maintenance_costs_importer import import_maintenance_costs


def main(path: Path) -> None:
    with SessionLocal() as db:
        try:
            result = import_maintenance_costs(db, path.read_bytes(), path.name)
            record_audit(db, user_id=None, action="IMPORT_COSTS", entity_type="upload",
                         entity_id=str(result["upload_id"]), new_values={
                             "source_file_name": result["source_file_name"],
                             "total_rows": result["total_rows"],
                             "rejected": result["rejected"],
                             "origin": "local_cli",
                         })
            db.commit()
        except Exception:
            db.rollback()
            raise
    print(f"Importados {result['total_rows']} lançamentos; rejeitados {result['rejected']}.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python -m scripts.import_cost_file <arquivo.xlsx>")
    main(Path(sys.argv[1]))
