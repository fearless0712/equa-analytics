from decimal import Decimal

from app.presentation.formatters import (
    format_ai_evidence,
    format_decimal,
    format_insight_evidence,
    format_integer,
    format_percentage,
    format_ratio,
    format_signed_number,
    format_signed_percentage,
)


def test_ai_evidence_formats_known_metrics_and_comparisons() -> None:
    assert (
        format_ai_evidence("North sales_share 30.436348667284141")
        == "North sales share: 30.44%"
    )
    assert (
        format_ai_evidence("Desk Chair sales_share 27.606257075228980")
        == "Desk Chair sales share: 27.61%"
    )
    assert (
        format_ai_evidence("North sales_share is 30.436348667284141")
        == "North sales share: 30.44%"
    )
    assert (
        format_ai_evidence(
            "North sales_share is reported as 30.436348667284141"
        )
        == "North sales share: 30.44%"
    )
    assert (
        format_ai_evidence("Office sales 32750 versus 35150.00 previously")
        == "Office sales 32,750 versus 35,150 previously"
    )
    assert format_ai_evidence("Office sales 20520.00") == "Office sales: 20,520"
    assert format_ai_evidence("quantity 11340.00") == "Quantity: 11,340"


def test_ai_evidence_formats_bounded_context_path_values() -> None:
    assert format_ai_evidence(
        "monthly[2026-04].sales_change_pct = "
        "-12.514370175726720315322713089"
    ) == "Sales change: -12.51%"
    assert format_ai_evidence(
        "regions[North].sales_share = 30.436348667284141195842338170217"
    ) == "North sales share: 30.44%"
    assert format_ai_evidence(
        "categories[Office].sales_change_amount = -2400.00"
    ) == "Office sales change amount: -2,400"
    assert format_ai_evidence(
        "products[Desk Chair].current_value = 27.606257075228980"
    ) == "Desk Chair current value: 27.61"
    assert format_ai_evidence(
        "dimensions.regions[North].sales_share "
        "30.436348667284141195842338..."
    ) == "North sales share: 30.44%"
    assert format_ai_evidence(
        "dimensions.products[Desk Chair].sales_share 27.606257075228980..."
    ) == "Desk Chair sales share: 27.61%"


def test_ai_evidence_formats_semicolon_parts_and_preserves_unknown_text() -> None:
    evidence = (
        "High sales concentration by region; "
        "North sales_share 30.436348667284141; severity warning."
    )
    assert format_ai_evidence(evidence) == (
        "High sales concentration by region; "
        "North sales share: 30.44%; Severity: warning"
    )
    unknown = "Review value 30.436348667284141 only after source validation."
    assert format_ai_evidence(unknown) == unknown


def test_ai_evidence_returns_malicious_input_as_plain_text() -> None:
    attack = '</div><script>alert(1)</script> "><img src=x onerror=alert(1)>'
    assert format_ai_evidence(attack) == attack


def test_decimal_display_formats_large_and_fractional_values() -> None:
    assert format_decimal(Decimal("1234567890.6700")) == "1,234,567,890.67"
    assert format_decimal(Decimal("12345.00")) == "12,345"
    assert format_decimal(Decimal("2857.941176470588235294117647")) == "2,857.94"
    assert format_decimal(Decimal("0.125")) == "0.13"
    assert format_decimal(Decimal("-20.50")) == "-20.50"


def test_none_and_percentage_display() -> None:
    assert format_decimal(None) == "N/A"
    assert format_percentage(None) == "N/A"
    assert format_percentage(Decimal("12.500")) == "12.50%"
    assert format_decimal(Decimal("NaN")) == "N/A"
    assert format_decimal(Decimal("Infinity")) == "N/A"
    assert format_integer(1234567) == "1,234,567"


def test_ratio_and_signed_business_formats() -> None:
    assert format_ratio(Decimal("0.30436346867284")) == "30.44%"
    assert format_signed_percentage(Decimal("0.952380952380")) == "+0.95%"
    assert format_signed_percentage(Decimal("-6.827")) == "-6.83%"
    assert format_signed_percentage(Decimal("0")) == "0.00%"
    assert format_signed_number(Decimal("20610")) == "+20,610"
    assert format_signed_number(Decimal("-7620")) == "-7,620"
    assert format_signed_number(Decimal("0")) == "0"
    assert format_signed_number(None) == "N/A"


def test_report_evidence_formats_percentages_amounts_and_bounds() -> None:
    evidence = format_insight_evidence(
        (
            "top_one_share=30.436348667284141195842338170",
            "top_three_share=81.85139446331172172481218483",
            "significant_change_pct=10.0000",
            "minimum_total_sales_share_pct=5.0000",
            "lower_bound=-4.000",
            "upper_bound=28237.500",
            "change_amount=2737.500",
            "change_pct=-6.827123",
        )
    )

    assert evidence == (
        "Leading share: 30.44%",
        "Top three share: 81.85%",
        "Significant change threshold: 10.00%",
        "Minimum total sales share: 5.00%",
        "Lower bound: -4",
        "Upper bound: 28,237.50",
        "Change amount: +2,737.50",
        "Change percentage: -6.83%",
    )


def test_report_evidence_formats_boolean_none_and_unknown_values() -> None:
    evidence = format_insight_evidence(
        (
            "significant=true",
            "reviewed=false",
            "top_one_share=None",
            "custom_value=1234.567",
            "note=<script>alert(1)</script>",
            "Plain evidence",
        )
    )

    assert evidence == (
        "Significant: true",
        "Reviewed: false",
        "Leading share: N/A",
        "Custom Value: 1,234.57",
        "Note: <script>alert(1)</script>",
        "Plain evidence",
    )
