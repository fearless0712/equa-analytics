from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.ai.models import AiInsightResponse
from app.domain.models import (
    BusinessInsight,
    CategoryChange,
    DataQualityReport,
    DimensionMetric,
    KpiSummary,
    MonthlyMetric,
)


class ReportAiStatus(StrEnum):
    NOT_REQUESTED = "not_requested"
    INCLUDED = "included"
    UNAVAILABLE = "unavailable"


class ReportTrend(StrEnum):
    INCREASE = "increase"
    DECREASE = "decrease"
    STABLE = "stable"
    UNAVAILABLE = "unavailable"


class ReportMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    generated_at: datetime
    locale: Literal["en"] = "en"
    date_from: date | None = None
    date_to: date | None = None
    observed_months: int = Field(ge=0)
    imputed_months: int = Field(ge=0)
    total_rows: int = Field(ge=0)
    analyzed_rows: int = Field(ge=0)
    potential_outliers: int = Field(default=0, ge=0)
    currency: None = None

    @model_validator(mode="after")
    def require_timezone(self) -> "ReportMetadata":
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware")
        return self


class ReportExecutiveSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    headline: str = Field(min_length=1, max_length=400)
    observations: tuple[str, ...] = Field(default=(), max_length=4)
    total_sales: Decimal
    latest_month: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    latest_sales: Decimal | None = None
    latest_change_amount: Decimal | None = None
    latest_change_pct: Decimal | None = None
    latest_trend: ReportTrend
    leading_product: str | None = None
    leading_category: str | None = None
    leading_region: str | None = None


class ReportInsightSection(BaseModel):
    model_config = ConfigDict(frozen=True)

    business: tuple[BusinessInsight, ...] = ()
    quality: tuple[BusinessInsight, ...] = ()
    outliers: tuple[BusinessInsight, ...] = ()


class ReportMethodology(BaseModel):
    model_config = ConfigDict(frozen=True)

    sales_formula: Literal["quantity * unit_price * (1 - discount)"] = (
        "quantity * unit_price * (1 - discount)"
    )
    currency_note: Literal["Currency is not specified by the Phase 1 CSV schema."] = (
        "Currency is not specified by the Phase 1 CSV schema."
    )
    decimal_note: Literal["Decimal precision is preserved in calculations; rounding is presentation-only."] = (
        "Decimal precision is preserved in calculations; rounding is presentation-only."
    )
    missing_month_note: Literal["Calendar months without source rows are marked as imputed zero values."] = (
        "Calendar months without source rows are marked as imputed zero values."
    )
    duplicate_note: Literal["Duplicate rows are reported and retained in calculations."] = (
        "Duplicate rows are reported and retained in calculations."
    )
    outlier_note: Literal["Potential outliers are IQR review candidates and are not removed."] = (
        "Potential outliers are IQR review candidates and are not removed."
    )
    ai_note: Literal["AI is optional, interprets bounded calculated results, and does not calculate KPIs."] = (
        "AI is optional, interprets bounded calculated results, and does not calculate KPIs."
    )


class BusinessReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    metadata: ReportMetadata
    executive_summary: ReportExecutiveSummary
    kpis: KpiSummary
    monthly: tuple[MonthlyMetric, ...] = ()
    top_products: tuple[DimensionMetric, ...] = ()
    top_categories: tuple[DimensionMetric, ...] = ()
    top_regions: tuple[DimensionMetric, ...] = ()
    largest_category_growth: CategoryChange | None = None
    largest_category_decline: CategoryChange | None = None
    insights: ReportInsightSection
    quality: DataQualityReport
    ai_status: ReportAiStatus
    ai: AiInsightResponse | None = None
    methodology: ReportMethodology

    @model_validator(mode="after")
    def validate_ai_state(self) -> "BusinessReport":
        if self.ai_status is ReportAiStatus.INCLUDED and self.ai is None:
            raise ValueError("included AI status requires an AI response")
        if self.ai_status is not ReportAiStatus.INCLUDED and self.ai is not None:
            raise ValueError("AI response requires included AI status")
        return self
