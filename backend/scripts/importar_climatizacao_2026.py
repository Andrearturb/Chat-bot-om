"""
Carga única: Inventário de Climatização (Grupo Gentil, 2026) para `climate_assets`.

Lê a planilha (abas "Climatização" e "Revisar"), casa cada linha com uma loja do
banco pelo número BPCS e cria o equipamento. Campo obrigatório ausente na planilha
(Local, Tipo) vira texto vazio; campo opcional ausente (Marca, Capacidade) vira NULL.

Seguro pra rodar de novo: antes de inserir, apaga os equipamentos que uma rodada
anterior deste script criou (marcados em `notes`), então cada rodada substitui a
anterior sem duplicar nem mexer nos equipamentos cadastrados manualmente.

Uso (dentro do contêiner do backend, onde DATABASE_URL já aponta pro banco certo):
    python scripts/importar_climatizacao_2026.py --dry-run
    python scripts/importar_climatizacao_2026.py
    python scripts/importar_climatizacao_2026.py --arquivo /caminho/outra_planilha.xlsx
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.models.asset_store import AssetStore  # noqa: E402
from app.models.climate_asset import ClimateAsset  # noqa: E402
from app.services.assets import normalize_key  # noqa: E402

IMPORT_TAG = "Fonte: planilha Inventário Climatização 2026"
DEFAULT_FILE = Path(__file__).resolve().parent.parent / "Inventario_Climatizacao_Grupo_Gentil_2026.xlsx"


def _bpcs_digits(valor) -> int | None:
    """BPCS só com dígitos: alguns registros do banco trazem um '#'/'##' na frente."""
    digitos = re.sub(r"\D", "", str(valor or ""))
    return int(digitos) if digitos else None


def _parse_btu(texto) -> int | None:
    """'12.000 BTUs' -> 12000. Vazio na planilha fica NULL (campo opcional no banco)."""
    if texto is None:
        return None
    digitos = re.sub(r"\D", "", str(texto))
    return int(digitos) if digitos else None


def _revisar_bpcs(wb) -> dict[str, int]:
    """normalize_key('Nome no Documento') -> 'Possível BPCS', lido da aba Revisar.

    A aba Revisar escreve os nomes sem acento ('CEARA MIRIM'); a aba principal, com
    acento ('CEARÁ MIRIM') — por isso o cruzamento usa a mesma normalização de
    app.services.assets, não o texto exato.
    """
    ws = wb["Revisar"]
    sugestoes: dict[str, int] = {}
    for nome, _loja_sugerida, bpcs, _motivo in ws.iter_rows(min_row=2, values_only=True):
        if nome and bpcs:
            sugestoes[normalize_key(str(nome))] = int(bpcs)
    return sugestoes


def _carregar_linhas(caminho: Path) -> list[dict]:
    wb = load_workbook(caminho, data_only=True)
    revisar = _revisar_bpcs(wb)
    ws = wb["Climatização"]
    linhas = []
    for numero_linha, (bpcs, loja, tipo, marca, capacidade, local) in enumerate(
        ws.iter_rows(min_row=2, values_only=True), start=2
    ):
        bpcs_final, veio_da_revisao = bpcs, False
        if bpcs_final is None and loja and normalize_key(str(loja)) in revisar:
            bpcs_final, veio_da_revisao = revisar[normalize_key(str(loja))], True
        linhas.append({
            "linha": numero_linha,
            "bpcs": bpcs_final,
            "loja_planilha": loja,
            "veio_da_revisao": veio_da_revisao,
            "equipment_type": (str(tipo).strip() if tipo else ""),
            "brand": (str(marca).strip() if marca else None),
            "capacity_btu": _parse_btu(capacidade),
            "location": (str(local).strip() if local else ""),
        })
    return linhas


def _proximo_codigo(store: AssetStore, contadores: dict[int, int]) -> str:
    """Mesma fórmula de app.services.assets.asset_code — com contador em memória,
    pra Marca a prévia do --dry-run bater com o que a carga de verdade vai gerar."""
    identidade = normalize_key(store.sap_number or store.bpcs_number or str(store.id))[:30] or str(store.id)
    contadores[store.id] += 1
    return f"CLI-{identidade}-{contadores[store.id]:03d}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Só mostra o relatório, não grava no banco.")
    parser.add_argument("--arquivo", type=Path, default=DEFAULT_FILE, help="Caminho da planilha .xlsx.")
    args = parser.parse_args()

    linhas = _carregar_linhas(args.arquivo)
    db = SessionLocal()
    try:
        lojas = db.query(AssetStore).all()
        por_bpcs: dict[int, AssetStore] = {}
        for store in lojas:
            digitos = _bpcs_digits(store.bpcs_number)
            if digitos is not None:
                por_bpcs[digitos] = store

        anteriores = db.query(ClimateAsset).filter(ClimateAsset.notes == IMPORT_TAG)
        total_anteriores = anteriores.count()
        if args.dry_run:
            if total_anteriores:
                print(f"[DRY-RUN] Removeria {total_anteriores} equipamento(s) de uma rodada anterior deste script.")
        elif total_anteriores:
            anteriores.delete(synchronize_session=False)
            db.flush()
            print(f"Removidos {total_anteriores} equipamento(s) de uma rodada anterior deste script.")

        contadores: dict[int, int] = {}
        for store in lojas:
            maximo = 0
            for (codigo,) in db.query(ClimateAsset.asset_code).filter(ClimateAsset.store_id == store.id):
                m = re.search(r"-(\d+)$", codigo or "")
                if m:
                    maximo = max(maximo, int(m.group(1)))
            contadores[store.id] = maximo

        criados: list[ClimateAsset] = []
        pulados: Counter[str] = Counter()
        detalhes_pulados: list[str] = []

        for linha in linhas:
            store = por_bpcs.get(linha["bpcs"]) if linha["bpcs"] is not None else None
            if store is None:
                motivo = "loja não existe no banco" if linha["bpcs"] else "sem BPCS e sem correspondência na aba Revisar"
                pulados[motivo] += 1
                detalhes_pulados.append(
                    f"  linha {linha['linha']}: {linha['loja_planilha']} (BPCS {linha['bpcs']}) — {motivo}"
                )
                continue

            equipamento = ClimateAsset(
                store_id=store.id,
                asset_code=_proximo_codigo(store, contadores),
                equipment_type=linha["equipment_type"],
                capacity_btu=linha["capacity_btu"],
                location=linha["location"],
                brand=linha["brand"],
                notes=IMPORT_TAG,
            )
            criados.append(equipamento)
            if not args.dry_run:
                db.add(equipamento)

        if not args.dry_run and criados:
            db.flush()  # confere a UNIQUE de asset_code antes de decidir commitar

        rotulo = "[DRY-RUN] " if args.dry_run else ""
        print(f"\n{rotulo}Linhas na planilha: {len(linhas)}")
        print(f"{rotulo}Seriam criados: {len(criados)}" if args.dry_run else f"Criados: {len(criados)}")
        print(f"Pulados: {sum(pulados.values())}")
        for motivo, quantidade in pulados.most_common():
            print(f"  - {motivo}: {quantidade}")
        if detalhes_pulados:
            print("\nDetalhe das linhas puladas:")
            print("\n".join(detalhes_pulados))

        sem_local = sum(1 for e in criados if not e.location)
        sem_tipo = sum(1 for e in criados if not e.equipment_type)
        sem_btu = sum(1 for e in criados if e.capacity_btu is None)
        sem_marca = sum(1 for e in criados if e.brand is None)
        print(
            f"\nEntre os criados, ficaram vazios: Local={sem_local} · Tipo={sem_tipo} "
            f"· Capacidade(BTU)={sem_btu} · Marca={sem_marca}"
        )

        if args.dry_run:
            db.rollback()
            print("\n[DRY-RUN] Nada foi gravado no banco.")
        else:
            db.commit()
            print("\nGravado no banco.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
