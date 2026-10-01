"""
Registra todos os modelos em ``Base.metadata``.

Importe este módulo antes de usar ``Base.metadata`` (subida do app, migrações, testes):
um modelo que ninguém importou não existe para o SQLAlchemy nem para o Alembic.
"""

from app.models.asset_store import AssetStore            # noqa: F401
from app.models.auth import (                            # noqa: F401
    AiUsage, AppUser, AssistantConversation, AssistantMessage, AuditLog,
    OidcIdentity, OidcLoginRequest, SecurityEvent, UserSession,
)
from app.models.climate_asset import ClimateAsset        # noqa: F401
from app.models.fire_asset import FireAsset              # noqa: F401
from app.models.service import Service                   # noqa: F401
from app.models.store_document import StoreDocument      # noqa: F401
from app.models.upload import Upload                     # noqa: F401
from app.models.water_asset import WaterAsset            # noqa: F401
