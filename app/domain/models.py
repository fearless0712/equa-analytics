from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["equa-analytics"] = "equa-analytics"


class CsvValueType(StrEnum):
    DATE = "date"
    STRING = "string"
    NUMERIC = "numeric"


class CsvErrorCode(StrEnum):
    EMPTY_FILE = "CSV_EMPTY_FILE"
    FILE_TOO_LARGE = "CSV_FILE_TOO_LARGE"
    INVALID_FILE_TYPE = "CSV_INVALID_FILE_TYPE"
    INVALID_ENCODING = "CSV_INVALID_ENCODING"
    NUL_BYTE = "CSV_NUL_BYTE"
    PARSE_ERROR = "CSV_PARSE_ERROR"
    TOO_MANY_ROWS = "CSV_TOO_MANY_ROWS"
    MISSING_REQUIRED_COLUMN = "CSV_MISSING_REQUIRED_COLUMN"
    DUPLICATE_COLUMN = "CSV_DUPLICATE_COLUMN"
    UNKNOWN_COLUMN = "CSV_UNKNOWN_COLUMN"
    INVALID_DATE = "CSV_INVALID_DATE"
    INVALID_NUMBER = "CSV_INVALID_NUMBER"
    INVALID_QUANTITY = "CSV_INVALID_QUANTITY"
    NEGATIVE_QUANTITY = "CSV_NEGATIVE_QUANTITY"
    NEGATIVE_UNIT_PRICE = "CSV_NEGATIVE_UNIT_PRICE"
    UNIT_PRICE_TOO_LARGE = "CSV_UNIT_PRICE_TOO_LARGE"
    INVALID_DISCOUNT = "CSV_INVALID_DISCOUNT"
    EMPTY_PRODUCT = "CSV_EMPTY_PRODUCT"
    EMPTY_CATEGORY = "CSV_EMPTY_CATEGORY"
    EMPTY_REGION = "CSV_EMPTY_REGION"
    STRING_TOO_LONG = "CSV_STRING_TOO_LONG"
    NO_VALID_ROWS = "CSV_NO_VALID_ROWS"


class CsvColumnSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    value_type: CsvValueType
    required: bool
    minimum: float | None = None
    maximum: float | None = None
    default_value: str | float | None = None


class CsvValidationError(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: CsvErrorCode
    field: str | None = None
    row: int | None = Field(default=None, ge=1)

    @computed_field
    @property
    def message(self) -> str:
        from app.domain.csv_spec import CSV_ERROR_MESSAGES

        return CSV_ERROR_MESSAGES[self.code]


class CsvValidationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    is_valid: bool
    errors: tuple[CsvValidationError, ...] = ()
    total_rows: int = Field(ge=0)
    valid_rows: int = Field(ge=0)
    invalid_rows: int = Field(ge=0)


class CsvRawRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    row_number: int = Field(ge=2)
    values: tuple[str, ...]


class CsvReadResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    normalized_headers: tuple[str, ...] = ()
    rows: tuple[CsvRawRow, ...] = ()
    total_rows: int = Field(ge=0)
    encoding: Literal["utf-8", "utf-8-sig"] | None = None
    validation: CsvValidationResult


class CsvValidationSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    is_valid: bool
    errors: tuple[CsvValidationError, ...] = ()
    total_rows: int = Field(ge=0)
    valid_rows: int = Field(default=0, ge=0)
    invalid_rows: int = Field(default=0, ge=0)
    normalized_headers: tuple[str, ...] = ()
    encoding: Literal["utf-8", "utf-8-sig"] | None = None


class NormalizedSalesRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    row_number: int = Field(ge=2)
    date: date
    product: str
    category: str
    region: str
    quantity: int = Field(ge=0)
    unit_price: Decimal = Field(ge=0)
    discount: Decimal = Field(ge=0, le=1)
    customer_type: str | None = None
    sales: Decimal = Field(ge=0)


class CsvNormalizationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    valid_rows: tuple[NormalizedSalesRow, ...] = ()
    errors: tuple[CsvValidationError, ...] = ()
    total_rows: int = Field(ge=0)
    valid_count: int = Field(ge=0)
    invalid_count: int = Field(ge=0)
    is_valid: bool


class KpiSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_sales: Decimal
    total_quantity: int = Field(ge=0)
    transaction_count: int = Field(ge=0)
    average_order_value: Decimal | None
    average_unit_price: Decimal | None
    unique_products: int = Field(ge=0)
    unique_categories: int = Field(ge=0)
    unique_regions: int = Field(ge=0)


class MonthlyMetric(BaseModel):
    model_config = ConfigDict(frozen=True)

    year_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    sales: Decimal
    quantity: int = Field(ge=0)
    transaction_count: int = Field(ge=0)
    sales_change: Decimal | None
    sales_change_pct: Decimal | None
    quantity_change: int | None
    quantity_change_pct: Decimal | None
    is_imputed: bool = False


class DimensionMetric(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    sales: Decimal
    quantity: int = Field(ge=0)
    transaction_count: int = Field(ge=0)
    sales_share: Decimal | None
    rank: int = Field(ge=1)


class CategoryChange(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    current_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    previous_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    current_sales: Decimal
    previous_sales: Decimal
    change_amount: Decimal
    change_pct: Decimal | None


class DataQualityReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_rows: int = Field(ge=0)
    valid_rows: int = Field(ge=0)
    invalid_rows: int = Field(ge=0)
    duplicate_rows: int = Field(ge=0)
    missing_optional_values: int = Field(ge=0)


class AnalysisResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    kpis: KpiSummary
    monthly: tuple[MonthlyMetric, ...] = ()
    products: tuple[DimensionMetric, ...] = ()
    categories: tuple[DimensionMetric, ...] = ()
    regions: tuple[DimensionMetric, ...] = ()
    top_products: tuple[DimensionMetric, ...] = ()
    bottom_products: tuple[DimensionMetric, ...] = ()
    largest_category_growth: CategoryChange | None = None
    largest_category_decline: CategoryChange | None = None
    quality: DataQualityReport


class InsightSeverity(StrEnum):
    INFO = "info"
    POSITIVE = "positive"
    WARNING = "warning"
    CRITICAL = "critical"


class InsightType(StrEnum):
    SALES_GROWTH = "sales_growth"
    SALES_DECLINE = "sales_decline"
    SALES_STABLE = "sales_stable"
    CONCENTRATION = "concentration"
    ZERO_ACTIVITY = "zero_activity"
    CATEGORY_GROWTH = "category_growth"
    CATEGORY_DECLINE = "category_decline"
    CATEGORY_STABLE = "category_stable"
    DATA_GAP = "data_gap"
    DATA_QUALITY = "data_quality"
    INSUFFICIENT_DATA = "insufficient_data"
    POTENTIAL_OUTLIER = "potential_outlier"


class BusinessInsight(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    type: InsightType
    severity: InsightSeverity
    title: str
    summary: str
    metric_name: str | None = None
    current_value: Decimal | int | None = None
    previous_value: Decimal | int | None = None
    change_amount: Decimal | int | None = None
    change_pct: Decimal | None = None
    dimension: str | None = None
    dimension_value: str | None = None
    period: str | None = None
    evidence: tuple[str, ...] = ()


class AnalysisMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    date_from: date | None = None
    date_to: date | None = None
    observed_months: int = Field(ge=0)
    imputed_months: int = Field(ge=0)
    row_count: int = Field(ge=0)
    product_count: int = Field(ge=0)
    category_count: int = Field(ge=0)
    region_count: int = Field(ge=0)
    potential_outliers: int = Field(default=0, ge=0)


class InsightCollection(BaseModel):
    model_config = ConfigDict(frozen=True)

    business_insights: tuple[BusinessInsight, ...] = ()
    quality_insights: tuple[BusinessInsight, ...] = ()
    outlier_insights: tuple[BusinessInsight, ...] = ()
    metadata: AnalysisMetadata
