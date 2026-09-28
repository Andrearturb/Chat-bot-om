"""
Script de teste integrado: upload de documento, listagem e download.
"""
import sys
import requests
import io
import os

BASE = "http://localhost:8040"


def main():
    # Pegar primeiro store
    r = requests.get(f"{BASE}/assets/stores?page=1&page_size=1")
    r.raise_for_status()
    stores = r.json()
    store_id = stores[0]["id"]
    store_name = stores[0]["store_name"]
    print(f"[OK] Store: {store_name} (id={store_id})")

    # Criar um PDF mínimo válido em memória
    pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n194\n%%EOF"

    # Upload do documento
    files = {"file": ("avcb_teste.pdf", io.BytesIO(pdf_content), "application/pdf")}
    data = {
        "document_type": "AVCB",
        "document_number": "123456",
        "issue_date": "2026-04-12",
        "expiration_date": "2027-04-12",
        "issuer": "Corpo de Bombeiros",
        "notes": "Documento de teste automatizado",
    }
    r = requests.post(f"{BASE}/assets/stores/{store_id}/documents", files=files, data=data)
    r.raise_for_status()
    doc = r.json()
    doc_id = doc["id"]
    print(f"[OK] Documento criado: id={doc_id} | status={doc['status']} | arquivo={doc['original_filename']}")

    # Listar documentos
    r = requests.get(f"{BASE}/assets/stores/{store_id}/documents")
    r.raise_for_status()
    docs = r.json()
    print(f"[OK] Documentos da loja: {len(docs)}")

    # Verificar status calculado automaticamente
    assert doc["status"] == "Válido", f"Status esperado 'Válido', obtido '{doc['status']}'"
    print(f"[OK] Status calculado automaticamente: {doc['status']}")

    # Download (inline)
    r = requests.get(f"{BASE}/assets/documents/{doc_id}/file")
    r.raise_for_status()
    assert r.headers["content-type"] == "application/pdf"
    assert len(r.content) == len(pdf_content)
    print(f"[OK] Download inline: {len(r.content)} bytes, content-type={r.headers['content-type']}")

    # Download (attachment)
    r = requests.get(f"{BASE}/assets/documents/{doc_id}/file?download=true")
    r.raise_for_status()
    assert "attachment" in r.headers.get("content-disposition", "")
    print(f"[OK] Download attachment: content-disposition={r.headers.get('content-disposition')}")

    # Excluir documento
    r = requests.delete(f"{BASE}/assets/documents/{doc_id}")
    assert r.status_code == 204
    print(f"[OK] Documento excluído (204)")

    # Confirmar que foi removido
    r = requests.get(f"{BASE}/assets/documents/{doc_id}/file")
    assert r.status_code == 404
    print(f"[OK] Arquivo não encontrado após exclusão (404)")

    print("\n=== Todos os testes integrados passaram! ===")


if __name__ == "__main__":
    main()
