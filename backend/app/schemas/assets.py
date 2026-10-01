from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ASSET_STATUSES = {"Operacional", "Atenção", "Inativo"}
DOCUMENT_TYPES = {"AVCB", "Certificado de Dedetização", "Outro"}
WATER_TYPES = {"Purificador", "Gelágua"}


def _validate_year(value: int | None) -> int | None:
    if value is not None and not 1900 <= value <= datetime.now().year + 1:
        raise ValueError("Ano inválido.")
    return value


def _blank_to_none(value):
    if isinstance(value, str) and not value.strip():
        return None
    return value


class AssetStoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    store_key: str
    store_name: str
    bpcs_number: str | None
    sap_number: str | None
    praca: str | None
    climatization_count: int = 0
    fire_safety_count: int = 0
    water_count: int = 0
    documents_count: int = 0
    documents_expiring_count: int = 0
    documents_expired_count: int = 0
    updated_at: datetime


class AssetStoreOptionResponse(BaseModel):
    id: int
    name: str
    praca: str | None
    bpcs: str | None
    sap: str | None


class AssetSummaryResponse(BaseModel):
    stores_count: int
    equipment_count: int
    documents_count: int


class AssetStoreFiltersResponse(BaseModel):
    pracas: list[str]


class ClimateAssetCreate(BaseModel):
    equipment_type: str = Field(min_length=1, max_length=100)
    capacity_btu: int = Field(ge=1, le=200000)
    location: str = Field(min_length=1, max_length=255)
    brand: str | None = Field(default=None, max_length=150)
    model: str | None = Field(default=None, max_length=150)
    serial_number: str | None = Field(default=None, max_length=150)
    manufacture_year: int | None = None
    installation_year: int | None = None
    voltage: str | None = Field(default=None, max_length=50)
    refrigerant_gas: str | None = Field(default=None, max_length=80)
    status: str = "Operacional"
    notes: str | None = None

    _year_1 = field_validator("manufacture_year", "installation_year")(_validate_year)
    _optional_text = field_validator(
        "brand", "model", "serial_number", "voltage", "refrigerant_gas", "notes", mode="before"
    )(_blank_to_none)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        if value not in ASSET_STATUSES:
            raise ValueError("Status de equipamento inválido.")
        return value


class ClimateAssetUpdate(BaseModel):
    equipment_type: str | None = Field(default=None, min_length=1, max_length=100)
    capacity_btu: int | None = Field(default=None, ge=1, le=200000)
    location: str | None = Field(default=None, min_length=1, max_length=255)
    brand: str | None = Field(default=None, max_length=150)
    model: str | None = Field(default=None, max_length=150)
    serial_number: str | None = Field(default=None, max_length=150)
    manufacture_year: int | None = None
    installation_year: int | None = None
    voltage: str | None = Field(default=None, max_length=50)
    refrigerant_gas: str | None = Field(default=None, max_length=80)
    status: str | None = None
    notes: str | None = None

    _year_1 = field_validator("manufacture_year", "installation_year")(_validate_year)
    _optional_text = field_validator(
        "brand", "model", "serial_number", "voltage", "refrigerant_gas", "notes", mode="before"
    )(_blank_to_none)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str | None) -> str | None:
        if value is not None and value not in ASSET_STATUSES:
            raise ValueError("Status de equipamento inválido.")
        return value


class ClimateAssetResponse(ClimateAssetCreate):
    model_config = ConfigDict(from_attributes=True)

    # Compatibilidade com cadastros legados criados antes de BTU ser obrigatório.
    capacity_btu: int | None = Field(default=None, ge=1, le=200000)
    id: int
    store_id: int
    asset_code: str
    created_at: datetime
    updated_at: datetime


class FireAssetCreate(BaseModel):
    equipment_type: str = Field(default="Extintor", min_length=1, max_length=100)
    extinguisher_agent: str | None = Field(default=None, max_length=80)
    capacity: str | None = Field(default=None, max_length=80)
    location: str = Field(min_length=1, max_length=255)
    manufacture_year: int | None = None
    expiration_date: date | None = None
    hydrostatic_test_date: date | None = None
    status: str = "Operacional"
    notes: str | None = None

    _year = field_validator("manufacture_year")(_validate_year)
    _optional_text = field_validator("extinguisher_agent", "capacity", "notes", mode="before")(_blank_to_none)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        if value not in ASSET_STATUSES:
            raise ValueError("Status de equipamento inválido.")
        return value


class FireAssetUpdate(BaseModel):
    equipment_type: str | None = Field(default=None, min_length=1, max_length=100)
    extinguisher_agent: str | None = Field(default=None, max_length=80)
    capacity: str | None = Field(default=None, max_length=80)
    location: str | None = Field(default=None, min_length=1, max_length=255)
    manufacture_year: int | None = None
    expiration_date: date | None = None
    hydrostatic_test_date: date | None = None
    status: str | None = None
    notes: str | None = None

    _year = field_validator("manufacture_year")(_validate_year)
    _optional_text = field_validator("extinguisher_agent", "capacity", "notes", mode="before")(_blank_to_none)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str | None) -> str | None:
        if value is not None and value not in ASSET_STATUSES:
            raise ValueError("Status de equipamento inválido.")
        return value


class FireAssetResponse(FireAssetCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    store_id: int
    asset_code: str
    created_at: datetime
    updated_at: datetime


class WaterAssetCreate(BaseModel):
    equipment_type: str = "Purificador"
    location: str = Field(min_length=1, max_length=255)
    brand: str | None = Field(default=None, max_length=150)
    model: str | None = Field(default=None, max_length=150)
    serial_number: str | None = Field(default=None, max_length=150)
    manufacture_year: int | None = None
    installation_year: int | None = None
    voltage: str | None = Field(default=None, max_length=50)
    last_filter_change: date | None = None
    next_filter_change: date | None = None
    status: str = "Operacional"
    notes: str | None = None

    _year_1 = field_validator("manufacture_year", "installation_year")(_validate_year)
    _optional_text = field_validator("brand", "model", "serial_number", "voltage", "notes", mode="before")(_blank_to_none)

    @field_validator("equipment_type")
    @classmethod
    def valid_type(cls, value: str) -> str:
        if value not in WATER_TYPES:
            raise ValueError("Tipo de equipamento de água inválido.")
        return value

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        if value not in ASSET_STATUSES:
            raise ValueError("Status de equipamento inválido.")
        return value


class WaterAssetUpdate(BaseModel):
    equipment_type: str | None = None
    location: str | None = Field(default=None, min_length=1, max_length=255)
    brand: str | None = Field(default=None, max_length=150)
    model: str | None = Field(default=None, max_length=150)
    serial_number: str | None = Field(default=None, max_length=150)
    manufacture_year: int | None = None
    installation_year: int | None = None
    voltage: str | None = Field(default=None, max_length=50)
    last_filter_change: date | None = None
    next_filter_change: date | None = None
    status: str | None = None
    notes: str | None = None

    _year_1 = field_validator("manufacture_year", "installation_year")(_validate_year)
    _optional_text = field_validator("brand", "model", "serial_number", "voltage", "notes", mode="before")(_blank_to_none)

    @field_validator("equipment_type")
    @classmethod
    def valid_type(cls, value: str | None) -> str | None:
        if value is not None and value not in WATER_TYPES:
            raise ValueError("Tipo de equipamento de água inválido.")
        return value

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str | None) -> str | None:
        if value is not None and value not in ASSET_STATUSES:
            raise ValueError("Status de equipamento inválido.")
        return value


class WaterAssetResponse(WaterAssetCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    store_id: int
    asset_code: str
    created_at: datetime
    updated_at: datetime


class StoreDocumentCreate(BaseModel):
    document_type: str
    custom_document_type: str | None = Field(default=None, max_length=150)
    document_number: str | None = Field(default=None, max_length=150)
    issue_date: date | None = None
    expiration_date: date | None = None
    issuer: str | None = Field(default=None, max_length=255)
    notes: str | None = None

    _optional_text = field_validator(
        "custom_document_type", "document_number", "issuer", "notes", mode="before"
    )(_blank_to_none)

    @field_validator("document_type")
    @classmethod
    def valid_type(cls, value: str) -> str:
        if value not in DOCUMENT_TYPES:
            raise ValueError("Tipo de documento inválido.")
        return value

    @model_validator(mode="after")
    def validate_custom_type(self):
        if self.document_type == "Outro" and not self.custom_document_type:
            raise ValueError("Informe o nome do documento quando o tipo for 'Outro'.")
        if self.document_type != "Outro":
            self.custom_document_type = None
        return self


class StoreDocumentUpdate(BaseModel):
    document_type: str | None = None
    custom_document_type: str | None = Field(default=None, max_length=150)
    document_number: str | None = Field(default=None, max_length=150)
    issue_date: date | None = None
    expiration_date: date | None = None
    issuer: str | None = Field(default=None, max_length=255)
    notes: str | None = None

    _optional_text = field_validator(
        "custom_document_type", "document_number", "issuer", "notes", mode="before"
    )(_blank_to_none)

    @field_validator("document_type")
    @classmethod
    def valid_type(cls, value: str | None) -> str | None:
        if value is not None and value not in DOCUMENT_TYPES:
            raise ValueError("Tipo de documento inválido.")
        return value

    @model_validator(mode="after")
    def validate_custom_type(self):
        if self.document_type == "Outro" and not self.custom_document_type:
            raise ValueError("Informe o nome do documento quando o tipo for 'Outro'.")
        if self.document_type is not None and self.document_type != "Outro":
            self.custom_document_type = None
        return self


class StoreDocumentResponse(StoreDocumentCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    store_id: int
    original_filename: str
    mime_type: str
    file_size: int
    status: str
    created_at: datetime
    updated_at: datetime


class AssetStoreDetailResponse(AssetStoreResponse):
    climatization: list[ClimateAssetResponse]
    fire_safety: list[FireAssetResponse]
    water: list[WaterAssetResponse]
    documents: list[StoreDocumentResponse]
