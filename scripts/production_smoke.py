"""Offline production-runtime smoke check; never invokes an AI provider."""

from pathlib import Path
import subprocess
import sys

import weasyprint

from app.main import app
from app.presentation.pdf_report_renderer import MAX_PDF_REPORT_BYTES, PdfReportRenderer
from app.services.analyzer import analyze_rows
from app.services.csv_reader import read_csv_bytes
from app.services.insight_detector import detect_insights
from app.services.normalizer import normalize_csv_result
from app.services.report_builder import build_business_report


def main() -> None:
    assert sys.version_info[:2] == (3, 12), sys.version
    subprocess.run(
        [sys.executable, "-m", "weasyprint", "--info"],
        check=True,
    )
    assert app is not None

    source = Path("sample_data/valid_sales.csv").read_bytes()
    loaded = read_csv_bytes(
        source,
        max_file_size=5 * 1024 * 1024,
        max_rows=10_000,
    )
    normalized = normalize_csv_result(loaded)
    assert normalized.is_valid
    analysis = analyze_rows(
        normalized.valid_rows,
        total_rows=normalized.total_rows,
        invalid_rows=normalized.invalid_count,
    )
    insights = detect_insights(analysis, normalized.valid_rows)
    report = build_business_report(analysis, insights)
    pdf = PdfReportRenderer().render_pdf(report)
    assert pdf.startswith(b"%PDF-")
    assert 0 < len(pdf) < MAX_PDF_REPORT_BYTES
    print(f"Python {sys.version.split()[0]}")
    print(f"WeasyPrint {weasyprint.__version__}")
    print(f"Application {app.title}")
    print(f"Deterministic PDF {len(pdf)} bytes")


if __name__ == "__main__":
    main()
