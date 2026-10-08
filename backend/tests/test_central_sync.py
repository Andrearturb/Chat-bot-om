"""Manual Tape sync from the browser: auth, CSRF, isolation and real imports orchestration."""
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.api_harness import SESSION_COOKIE, TestSession, fastapi_app, reset_database, seed_session
from app.api.routes import imports
from app.models.auth import AuditLog
from app.services.tape_sync_guard import tape_sync_guard


@pytest.fixture(autouse=True)
def clean():
    reset_database()
    yield
    reset_database()


@pytest.fixture
def importer(monkeypatch):
    mock = Mock(return_value=dict(message='Sincronizado', total_rows=10, inserted=2,
                                 updated=3, unchanged=5, upload_data=datetime.now(timezone.utc),
                                 source_file_name='Tape API'))
    monkeypatch.setattr(imports, 'importar_servicos_tape', mock)
    return mock


def client_for(permissions):
    token, csrf = seed_session(permissions)
    client = TestClient(fastapi_app)
    client.cookies.set(SESSION_COOKIE, token)
    return client, csrf


def test_sync_requires_session(importer):
    with TestClient(fastapi_app) as client:
        assert client.post('/imports/tape/central').status_code == 401
    importer.assert_not_called()


@pytest.mark.parametrize('permissions,with_csrf', [(['indicators.view'], True), (['sync.tape'], False)])
def test_sync_requires_permission_and_csrf(importer, permissions, with_csrf):
    client, csrf = client_for(permissions)
    with client:
        response = client.post('/imports/tape/central', headers={'X-CSRF-Token': csrf} if with_csrf else {})
    assert response.status_code == 403
    importer.assert_not_called()


def test_sync_calls_all_sources_and_audits_without_browser_api_key(importer):
    client, csrf = client_for(['sync.tape'])
    with client:
        response = client.post('/imports/tape/central', headers={'X-CSRF-Token': csrf})
    assert response.status_code == 200
    assert [call.kwargs['app_id'] for call in importer.call_args_list] == [30902, 57531, 57532]
    assert [source['status'] for source in response.json()['sources']] == ['success'] * 3
    assert response.json()['sources'][1]['result']['updated'] == 3
    with TestSession() as db:
        events = db.scalars(select(AuditLog).where(AuditLog.action == 'SYNC_TAPE')).all()
        assert len(events) == 3


def test_partial_failure_attempts_remaining_sources_and_hides_internal_errors(importer):
    good = importer.return_value
    importer.side_effect = [RuntimeError('private-token-value'), good, good]
    client, csrf = client_for(['sync.tape'])
    with client:
        response = client.post('/imports/tape/central', headers={'X-CSRF-Token': csrf})
    assert response.status_code == 200
    assert [source['status'] for source in response.json()['sources']] == ['error', 'success', 'success']
    assert 'private-token-value' not in response.text
    assert importer.call_count == 3


def test_empty_collection_is_reported_without_claiming_update(importer):
    importer.return_value = {**importer.return_value, 'total_rows': 0, 'inserted': 0,
                             'updated': 0, 'unchanged': 0, 'upload_data': None}
    client, csrf = client_for(['sync.tape'])
    with client:
        response = client.post('/imports/tape/central', headers={'X-CSRF-Token': csrf})
    assert [source['status'] for source in response.json()['sources']] == ['empty'] * 3


def test_busy_sync_is_rejected_and_can_retry_after_release(importer):
    client, csrf = client_for(['sync.tape'])
    with client:
        with tape_sync_guard():
            response = client.post('/imports/tape/central', headers={'X-CSRF-Token': csrf})
        assert response.status_code == 409
        importer.assert_not_called()
        assert client.post('/imports/tape/central', headers={'X-CSRF-Token': csrf}).status_code == 200


def test_legacy_sync_still_requires_api_key(importer):
    client, csrf = client_for(['sync.tape'])
    with client:
        assert client.post('/imports/tape', headers={'X-CSRF-Token': csrf}).status_code == 422
    importer.assert_not_called()
