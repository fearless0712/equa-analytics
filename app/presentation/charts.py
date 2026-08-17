import base64
from dataclasses import dataclass

import plotly.graph_objects as go

from app.domain.models import AnalysisResult, DimensionMetric

SALES_COLOR = "#55d6be"
QUANTITY_COLOR = "#f2b84b"
GRID_COLOR = "#2b333c"
TEXT_COLOR = "#dfe6ed"


@dataclass(frozen=True)
class ChartSpec:
    chart_id: str
    title: str
    payload: str


@dataclass(frozen=True)
class DashboardCharts:
    monthly_sales: ChartSpec
    monthly_quantity: ChartSpec
    top_products: ChartSpec
    categories: ChartSpec
    regions: ChartSpec


def _base_layout(figure: go.Figure, title: str) -> None:
    figure.update_layout(
        title={"text": title, "font": {"size": 16}},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": TEXT_COLOR, "family": "Inter, system-ui, sans-serif"},
        margin={"l": 56, "r": 20, "t": 54, "b": 48},
        hoverlabel={"bgcolor": "#171c21", "font": {"color": TEXT_COLOR}},
        showlegend=False,
    )
    figure.update_xaxes(gridcolor=GRID_COLOR, zerolinecolor=GRID_COLOR, automargin=True)
    figure.update_yaxes(gridcolor=GRID_COLOR, zerolinecolor=GRID_COLOR, automargin=True)


def _encode(chart_id: str, title: str, figure: go.Figure) -> ChartSpec:
    payload = base64.b64encode(figure.to_json().encode("utf-8")).decode("ascii")
    return ChartSpec(chart_id=chart_id, title=title, payload=payload)


def _monthly_sales_chart(analysis: AnalysisResult) -> ChartSpec:
    metrics = analysis.monthly
    marker_colors = ["#6b7580" if item.is_imputed else SALES_COLOR for item in metrics]
    source_status = [
        "No source rows / imputed zero" if item.is_imputed else "Source rows present"
        for item in metrics
    ]
    figure = go.Figure(
        go.Scatter(
            x=[item.year_month for item in metrics],
            y=[float(item.sales) for item in metrics],
            mode="lines+markers",
            line={"color": SALES_COLOR, "width": 2},
            marker={"color": marker_colors, "size": 8},
            customdata=source_status,
            hovertemplate="%{x}<br>Sales: %{y:,.2f}<br>%{customdata}<extra></extra>",
        )
    )
    _base_layout(figure, "Monthly Sales")
    figure.update_yaxes(title_text="Sales")
    return _encode("monthly-sales-chart", "Monthly Sales", figure)


def _monthly_quantity_chart(analysis: AnalysisResult) -> ChartSpec:
    metrics = analysis.monthly
    figure = go.Figure(
        go.Bar(
            x=[item.year_month for item in metrics],
            y=[item.quantity for item in metrics],
            marker={
                "color": [
                    "#6b7580" if item.is_imputed else QUANTITY_COLOR for item in metrics
                ]
            },
            customdata=[
                "No source rows / imputed zero"
                if item.is_imputed
                else "Source rows present"
                for item in metrics
            ],
            hovertemplate="%{x}<br>Quantity: %{y:,}<br>%{customdata}<extra></extra>",
        )
    )
    _base_layout(figure, "Monthly Quantity")
    figure.update_yaxes(title_text="Quantity")
    return _encode("monthly-quantity-chart", "Monthly Quantity", figure)


def _dimension_bar(
    chart_id: str,
    title: str,
    metrics: tuple[DimensionMetric, ...],
    color: str,
) -> ChartSpec:
    figure = go.Figure(
        go.Bar(
            x=[float(item.sales) for item in metrics],
            y=[item.name for item in metrics],
            orientation="h",
            marker={"color": color},
            hovertemplate="%{y}<br>Sales: %{x:,.2f}<extra></extra>",
        )
    )
    _base_layout(figure, title)
    figure.update_layout(margin={"l": 120, "r": 20, "t": 54, "b": 48})
    figure.update_xaxes(title_text="Sales")
    figure.update_yaxes(autorange="reversed")
    return _encode(chart_id, title, figure)


def build_dashboard_charts(analysis: AnalysisResult) -> DashboardCharts:
    return DashboardCharts(
        monthly_sales=_monthly_sales_chart(analysis),
        monthly_quantity=_monthly_quantity_chart(analysis),
        top_products=_dimension_bar(
            "top-products-chart",
            "Top Products by Sales",
            analysis.top_products,
            SALES_COLOR,
        ),
        categories=_dimension_bar(
            "category-sales-chart",
            "Sales by Category",
            analysis.categories,
            "#72a8ff",
        ),
        regions=_dimension_bar(
            "region-sales-chart",
            "Sales by Region",
            analysis.regions,
            QUANTITY_COLOR,
        ),
    )
