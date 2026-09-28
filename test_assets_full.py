"""
Testes integrados da Central de Ativos.
Executa dentro do container: docker exec chatbot-backend python /tmp/test_assets_full.py
"""
import io
import requests

BASE = "http://localhost:8000"
STORE_ID = None  # será descoberto dinamicamente

def test_summary():
    r = requests.get(f"{BASE}/assets/summary")
    assert r.status_code == 200, f"summary failed: {r.status_code}"
    data = r.json()
    assert "stores_count" in data
    assert "equipment_count" in data
    assert "documents_count" in data
    print(f"[OK] summary: stores={data['stores_count']} equip={data['equipment_count']} docs={data['documents_count']}")
    return data

def get_first_store():
    r = requests.get(f"{BASE}/assets/stores?page_size=1")
    assert r.status_code == 200, f"stores failed: {r.status_code}"
    data = r.json()
    assert len(data) > 0, "No stores returned"
    store = data[0]
    print(f"[OK] stores list: first={store['store_name']} id={store['id']}")
    return store

def test_search():
    r = requests.get(f"{BASE}/assets/stores?q=a&page_size=5")
    assert r.status_code == 200
    data = r.json()
    print(f"[OK] search 'a': {len(data)} results")

def test_store_detail(store_id):
    r = requests.get(f"{BASE}/assets/stores/{store_id}")
    assert r.status_code == 200, f"store detail failed: {r.status_code}"
    data = r.json()
    assert "climatization" in data
    assert "fire_safety" in data
    assert "water" in data
    assert "documents" in data
    print(f"[OK] store detail: {data['store_name']}")
    return data

def test_climatization_crud(store_id):
    # Create
    payload = {"equipment_type": "Cassete", "capacity_btu": 36000, "location": "Sala de vendas", "status": "Operacional"}
    r = requests.post(f"{BASE}/assets/stores/{store_id}/climatization", json=payload)
    assert r.status_code == 201, f"create clima failed: {r.status_code} {r.text}"
    item = r.json()
    asset_id = item["id"]
    assert item["asset_code"].startswith("CLI-")
    print(f"[OK] create climatization: {item['asset_code']}")

    # Read
    r = requests.get(f"{BASE}/assets/stores/{store_id}/climatization")
    assert r.status_code == 200
    items = r.json()
    assert any(i["id"] == asset_id for i in items)
    print(f"[OK] list climatization: {len(items)} items")

    # Update
    r = requests.put(f"{BASE}/assets/climatization/{asset_id}", json={"brand": "Carrier", "status": "Atenção"})
    assert r.status_code == 200, f"update clima failed: {r.status_code} {r.text}"
    updated = r.json()
    assert updated["brand"] == "Carrier"
    print(f"[OK] update climatization: brand={updated['brand']}")

    # Delete
    r = requests.delete(f"{BASE}/assets/climatization/{asset_id}")
    assert r.status_code == 204, f"delete clima failed: {r.status_code}"
    print("[OK] delete climatization")

def test_fire_safety_crud(store_id):
    from datetime import date, timedelta
    future = (date.today() + timedelta(days=90)).isoformat()
    payload = {"equipment_type": "Extintor", "extinguisher_agent": "ABC", "capacity": "6 kg",
               "location": "Salão", "expiration_date": future, "status": "Operacional"}
    r = requests.post(f"{BASE}/assets/stores/{store_id}/fire-safety", json=payload)
    assert r.status_code == 201, f"create fire failed: {r.status_code} {r.text}"
    item = r.json()
    asset_id = item["id"]
    assert item["asset_code"].startswith("INC-")
    print(f"[OK] create fire-safety: {item['asset_code']}")

    r = requests.put(f"{BASE}/assets/fire-safety/{asset_id}", json={"status": "Inativo"})
    assert r.status_code == 200
    print("[OK] update fire-safety")

    r = requests.delete(f"{BASE}/assets/fire-safety/{asset_id}")
    assert r.status_code == 204
    print("[OK] delete fire-safety")

def test_water_crud(store_id):
    payload = {"equipment_type": "Purificador", "location": "Copa", "brand": "IBBL", "status": "Operacional"}
    r = requests.post(f"{BASE}/assets/stores/{store_id}/water", json=payload)
    assert r.status_code == 201, f"create water failed: {r.status_code} {r.text}"
    item = r.json()
    asset_id = item["id"]
    assert item["asset_code"].startswith("AGU-")
    print(f"[OK] create water: {item['asset_code']}")

    r = requests.put(f"{BASE}/assets/water/{asset_id}", json={"brand": "Consul"})
    assert r.status_code == 200
    print("[OK] update water")

    r = requests.delete(f"{BASE}/assets/water/{asset_id}")
    assert r.status_code == 204
    print("[OK] delete water")

def test_document_crud(store_id):
    from datetime import date, timedelta
    future = (date.today() + timedelta(days=90)).isoformat()
    pdf_content = b"%PDF-1.4 fake pdf content for testing"
    files = {"file": ("avcb_teste.pdf", io.BytesIO(pdf_content), "application/pdf")}
    data = {
        "document_type": "AVCB",
        "document_number": "123456",
        "issue_date": date.today().isoformat(),
        "expiration_date": future,
        "issuer": "Corpo de Bombeiros",
    }
    r = requests.post(f"{BASE}/assets/stores/{store_id}/documents", files=files, data=data)
    assert r.status_code == 201, f"create doc failed: {r.status_code} {r.text}"
    doc = r.json()
    doc_id = doc["id"]
    assert doc["status"] == "Válido"
    assert doc["original_filename"] == "avcb_teste.pdf"
    print(f"[OK] create document: {doc['document_type']} status={doc['status']}")

    # Visualizar arquivo
    r = requests.get(f"{BASE}/assets/documents/{doc_id}/file")
    assert r.status_code == 200
    print(f"[OK] file view: mime={r.headers.get('content-type')}")

    # Download
    r = requests.get(f"{BASE}/assets/documents/{doc_id}/file?download=true")
    assert r.status_code == 200
    print("[OK] file download")

    # Update metadata + replace file (multipart)
    replacement = b"%PDF-1.4 replacement file"
    files_update = {"file": ("avcb_atualizado.pdf", io.BytesIO(replacement), "application/pdf")}
    data_update = {
        "document_type": "AVCB",
        "custom_document_type": "",
        "document_number": "",  # limpa o valor anterior
        "issue_date": date.today().isoformat(),
        "expiration_date": future,
        "issuer": "CBMCE",
        "notes": "",
    }
    r = requests.put(
        f"{BASE}/assets/documents/{doc_id}",
        files=files_update,
        data=data_update,
    )
    assert r.status_code == 200, f"update doc failed: {r.status_code} {r.text}"
    updated = r.json()
    assert updated["issuer"] == "CBMCE"
    assert updated["document_number"] is None
    assert updated["original_filename"] == "avcb_atualizado.pdf"
    r = requests.get(f"{BASE}/assets/documents/{doc_id}/file")
    assert r.content == replacement
    print("[OK] update document metadata + file replacement")

    # Delete
    r = requests.delete(f"{BASE}/assets/documents/{doc_id}")
    assert r.status_code == 204
    print("[OK] delete document + file")

def _document_status(expiration_date, today=None):
    """Replica da lógica do backend para teste isolado."""
    from datetime import date, timedelta
    if expiration_date is None:
        return "Sem validade"
    current = today or date.today()
    if expiration_date < current:
        return "Vencido"
    if expiration_date <= current + timedelta(days=60):
        return "Próximo do vencimento"
    return "Válido"


def test_document_validity():
    from datetime import date, timedelta
    today = date.today()
    cases = [
        (today + timedelta(days=90), "Válido"),
        (today + timedelta(days=30), "Próximo do vencimento"),
        (today - timedelta(days=1), "Vencido"),
        (None, "Sem validade"),
    ]
    for exp, expected in cases:
        status = _document_status(exp, today)
        assert status == expected, f"Expected '{expected}' for {exp}, got '{status}'"
        print(f"[OK] validity {exp} => {status}")

def test_404():
    r = requests.get(f"{BASE}/assets/stores/999999")
    assert r.status_code == 404, f"Expected 404 for nonexistent store, got {r.status_code}"
    print("[OK] 404 on nonexistent store")

    r = requests.delete(f"{BASE}/assets/climatization/999999")
    assert r.status_code == 404, f"Expected 404 for nonexistent asset, got {r.status_code}"
    print("[OK] 404 on nonexistent asset delete")

def test_file_validation(store_id):
    # File too large
    big = b"A" * (15 * 1024 * 1024 + 1)
    files = {"file": ("big.pdf", io.BytesIO(big), "application/pdf")}
    r = requests.post(f"{BASE}/assets/stores/{store_id}/documents", files=files,
                      data={"document_type": "AVCB"})
    assert r.status_code in (422, 400), f"Expected 422/400 for large file, got {r.status_code}"
    print(f"[OK] large file rejected: {r.status_code}")

    # Wrong extension
    files2 = {"file": ("doc.exe", io.BytesIO(b"not valid"), "application/octet-stream")}
    r = requests.post(f"{BASE}/assets/stores/{store_id}/documents", files=files2,
                      data={"document_type": "AVCB"})
    assert r.status_code in (422, 400), f"Expected 422/400 for bad file type, got {r.status_code}"
    print(f"[OK] invalid file type rejected: {r.status_code}")

def test_deduplication():
    # Call stores twice — count should be stable (no duplication on sync)
    r1 = requests.get(f"{BASE}/assets/stores?page_size=1000")
    count1 = len(r1.json())
    r2 = requests.get(f"{BASE}/assets/stores?page_size=1000")
    count2 = len(r2.json())
    assert count1 == count2, f"Stores count changed after double call: {count1} vs {count2}"
    print(f"[OK] deduplication: stable at {count1} stores")

if __name__ == "__main__":
    print("=== Central de Ativos — Integration Tests ===\n")
    try:
        test_summary()
        store = get_first_store()
        store_id = store["id"]
        test_search()
        test_store_detail(store_id)
        test_climatization_crud(store_id)
        test_fire_safety_crud(store_id)
        test_water_crud(store_id)
        test_document_crud(store_id)
        test_document_validity()
        test_404()
        test_file_validation(store_id)
        test_deduplication()
        print("\n=== ALL TESTS PASSED ===")
    except Exception as e:
        import traceback
        print(f"\n[FAIL] {e}")
        traceback.print_exc()
