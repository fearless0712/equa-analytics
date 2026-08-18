from html import escape
from pathlib import Path

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from app.domain.models import (
    CsvNormalizationResult,
    CsvReadResult,
    CsvErrorCode,
    CsvValidationError,
    CsvValidationSummary,
    HealthResponse,
)
from app.ai.context_builder import build_ai_context
from app.ai.models import AiErrorCode, AiServiceError
from app.ai.service import build_ai_provider
from app.config import Environment
from app.services.analyzer import analyze_rows
from app.services.csv_reader import read_csv_bytes
from app.services.normalizer import normalize_csv_result
from app.services.insight_detector import detect_insights
from app.services.report_builder import build_business_report
from app.web.responses import SafeJSONResponse
from app.web.upload_adapter import read_bounded_upload
from app.presentation.charts import build_dashboard_charts
from app.presentation.formatters import (
    format_decimal,
    format_insight_summary,
    format_integer,
    format_percentage,
    format_signed_number,
    format_signed_percentage,
)
from app.presentation.html_report_renderer import (
    HtmlReportRenderer,
    HtmlReportTooLargeError,
)
from app.presentation.pdf_report_renderer import (
    PdfErrorCode,
    PdfReportError,
    PdfReportRenderer,
)
from app.security.csrf import CSRF_COOKIE_NAME, require_csrf, set_csrf_cookie

router = APIRouter()
html_report_renderer = HtmlReportRenderer()
pdf_report_renderer = PdfReportRenderer(html_report_renderer)
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")
templates.env.filters.update(
    decimal=format_decimal,
    insight_summary=format_insight_summary,
    integer=format_integer,
    percentage=format_percentage,
    signed_number=format_signed_number,
    signed_percentage=format_signed_percentage,
)


def _public_errors(
    errors: tuple[CsvValidationError, ...],
) -> tuple[CsvValidationError, ...]:
    return tuple(
        error.model_copy(
            update={"field": escape(error.field) if error.field else None}
        )
        for error in errors
    )


def _summary_for_result(
    result: CsvReadResult,
) -> tuple[CsvValidationSummary, CsvNormalizationResult | None]:
    normalized: CsvNormalizationResult | None = None
    if result.validation.is_valid:
        normalized = normalize_csv_result(result)
        is_valid = normalized.is_valid
        errors = normalized.errors
        valid_rows = normalized.valid_count
        invalid_rows = normalized.invalid_count
    else:
        is_valid = False
        errors = result.validation.errors
        valid_rows = result.validation.valid_rows
        invalid_rows = result.validation.invalid_rows

    return (
        CsvValidationSummary(
            is_valid=is_valid,
            errors=_public_errors(errors),
            total_rows=result.total_rows,
            valid_rows=valid_rows,
            invalid_rows=invalid_rows,
            normalized_headers=tuple(
                escape(header) for header in result.normalized_headers
            ),
            encoding=result.encoding,
        ),
        normalized,
    )


def _summary_status(summary: CsvValidationSummary) -> int:
    if summary.is_valid:
        return 200
    if any(error.code is CsvErrorCode.FILE_TOO_LARGE for error in summary.errors):
        return 413
    if any(error.code is CsvErrorCode.INVALID_FILE_TYPE for error in summary.errors):
        return 400
    return 422


async def _load_csv_upload(
    request: Request, file: UploadFile
) -> CsvReadResult | CsvValidationSummary:
    settings = request.app.state.settings
    if not file.filename or not file.filename.lower().endswith(".csv"):
        await file.close()
        summary = CsvValidationSummary(
            is_valid=False,
            errors=(CsvValidationError(code=CsvErrorCode.INVALID_FILE_TYPE),),
            total_rows=0,
        )
        return summary

    try:
        data = await read_bounded_upload(file, max_size=settings.max_csv_file_size)
    except OSError:
        summary = CsvValidationSummary(
            is_valid=False,
            errors=(CsvValidationError(code=CsvErrorCode.PARSE_ERROR),),
            total_rows=0,
        )
        return summary
    return read_csv_bytes(
        data,
        max_file_size=settings.max_csv_file_size,
        max_rows=settings.max_csv_rows,
    )


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    token = request.app.state.csrf.issue()
    response = templates.TemplateResponse(
        request=request, name="index.html", context={"csrf_token": token}
    )
    set_csrf_cookie(
        response,
        token,
        secure=request.app.state.settings.environment is Environment.PRODUCTION,
    )
    return response


@router.post("/csv/validate", response_model=CsvValidationSummary)
async def validate_csv_upload(
    request: Request,
    _: None = Depends(require_csrf),
    file: UploadFile = File(...),
) -> JSONResponse:
    loaded = await _load_csv_upload(request, file)
    if isinstance(loaded, CsvValidationSummary):
        return SafeJSONResponse(
            status_code=_summary_status(loaded),
            content=loaded.model_dump(mode="json"),
        )
    summary, _ = _summary_for_result(loaded)
    return SafeJSONResponse(
        status_code=_summary_status(summary),
        content=summary.model_dump(mode="json"),
    )


@router.post("/csv/analyze")
async def analyze_csv_upload(
    request: Request,
    _: None = Depends(require_csrf),
    file: UploadFile = File(...),
) -> JSONResponse:
    loaded = await _load_csv_upload(request, file)
    if isinstance(loaded, CsvValidationSummary):
        return SafeJSONResponse(
            status_code=_summary_status(loaded),
            content=loaded.model_dump(mode="json"),
        )
    summary, normalized = _summary_for_result(loaded)
    if not summary.is_valid or normalized is None:
        return SafeJSONResponse(
            status_code=_summary_status(summary),
            content=summary.model_dump(mode="json"),
        )

    analysis = analyze_rows(
        normalized.valid_rows,
        total_rows=normalized.total_rows,
        invalid_rows=normalized.invalid_count,
    )
    return SafeJSONResponse(status_code=200, content=analysis.model_dump(mode="json"))


@router.get("/dashboard", include_in_schema=False)
async def dashboard_without_upload() -> RedirectResponse:
    # Dashboard state is intentionally not persisted; a CSV POST is required.
    return RedirectResponse(url="/", status_code=303)


@router.post("/dashboard", response_class=HTMLResponse)
async def render_dashboard(
    request: Request,
    _: None = Depends(require_csrf),
    file: UploadFile = File(...),
) -> HTMLResponse:
    csrf_token = request.cookies.get(CSRF_COOKIE_NAME)
    loaded = await _load_csv_upload(request, file)
    if isinstance(loaded, CsvValidationSummary):
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"errors": loaded.errors, "csrf_token": csrf_token},
            status_code=_summary_status(loaded),
        )

    summary, normalized = _summary_for_result(loaded)
    if not summary.is_valid or normalized is None:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"errors": summary.errors, "csrf_token": csrf_token},
            status_code=_summary_status(summary),
        )

    analysis = analyze_rows(
        normalized.valid_rows,
        total_rows=normalized.total_rows,
        invalid_rows=normalized.invalid_count,
    )
    insights = detect_insights(analysis, normalized.valid_rows)
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "analysis": analysis,
            "charts": build_dashboard_charts(analysis),
            "insights": insights,
            "csrf_token": csrf_token,
            "ai_mode": request.app.state.settings.ai_mode.value,
        },
    )


@router.post("/reports/html")
async def download_html_report(
    request: Request,
    _: None = Depends(require_csrf),
    file: UploadFile = File(...),
) -> Response:
    loaded = await _load_csv_upload(request, file)
    if isinstance(loaded, CsvValidationSummary):
        return SafeJSONResponse(
            status_code=_summary_status(loaded),
            content=loaded.model_dump(mode="json"),
        )
    summary, normalized = _summary_for_result(loaded)
    if not summary.is_valid or normalized is None:
        return SafeJSONResponse(
            status_code=_summary_status(summary),
            content=summary.model_dump(mode="json"),
        )

    analysis = analyze_rows(
        normalized.valid_rows,
        total_rows=normalized.total_rows,
        invalid_rows=normalized.invalid_count,
    )
    insights = detect_insights(analysis, normalized.valid_rows)
    report = build_business_report(analysis, insights)
    try:
        content = html_report_renderer.render_bytes(report)
    except HtmlReportTooLargeError:
        return SafeJSONResponse(
            status_code=413,
            content={"detail": "HTML report exceeds the safe size limit."},
        )

    report_date = report.metadata.generated_at.date().isoformat()
    return Response(
        content=content,
        media_type="text/html",
        headers={
            "Content-Disposition": (
                f'attachment; filename="equa-analytics-report-{report_date}.html"'
            ),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _pdf_error_response(code: PdfErrorCode) -> SafeJSONResponse:
    statuses = {
        PdfErrorCode.RENDER_FAILED: 500,
        PdfErrorCode.TOO_LARGE: 413,
        PdfErrorCode.BUSY: 503,
        PdfErrorCode.RATE_LIMITED: 429,
    }
    messages = {
        PdfErrorCode.RENDER_FAILED: "PDF report generation failed.",
        PdfErrorCode.TOO_LARGE: "PDF report exceeds the safe size limit.",
        PdfErrorCode.BUSY: "PDF report generation is currently busy.",
        PdfErrorCode.RATE_LIMITED: "PDF report generation rate limit exceeded.",
    }
    return SafeJSONResponse(
        status_code=statuses[code],
        content={"code": code.value, "message": messages[code]},
    )


@router.post("/reports/pdf")
async def download_pdf_report(
    request: Request,
    _: None = Depends(require_csrf),
    file: UploadFile = File(...),
) -> Response:
    client_host = request.client.host if request.client else "unknown"
    if not request.app.state.pdf_rate_limiter.allow(client_host):
        await file.close()
        return _pdf_error_response(PdfErrorCode.RATE_LIMITED)

    loaded = await _load_csv_upload(request, file)
    if isinstance(loaded, CsvValidationSummary):
        return SafeJSONResponse(
            status_code=_summary_status(loaded),
            content=loaded.model_dump(mode="json"),
        )
    summary, normalized = _summary_for_result(loaded)
    if not summary.is_valid or normalized is None:
        return SafeJSONResponse(
            status_code=_summary_status(summary),
            content=summary.model_dump(mode="json"),
        )

    semaphore = request.app.state.pdf_semaphore
    if semaphore.locked():
        return _pdf_error_response(PdfErrorCode.BUSY)
    await semaphore.acquire()
    try:
        analysis = analyze_rows(
            normalized.valid_rows,
            total_rows=normalized.total_rows,
            invalid_rows=normalized.invalid_count,
        )
        insights = detect_insights(analysis, normalized.valid_rows)
        report = build_business_report(analysis, insights)
        try:
            content = await run_in_threadpool(pdf_report_renderer.render_pdf, report)
        except PdfReportError as exc:
            return _pdf_error_response(exc.code)
    finally:
        semaphore.release()

    report_date = report.metadata.generated_at.date().isoformat()
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="equa-analytics-report-{report_date}.pdf"'
            ),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _ai_status(code: AiErrorCode) -> int:
    if code is AiErrorCode.RATE_LIMITED:
        return 429
    if code in {AiErrorCode.DISABLED, AiErrorCode.CONFIGURATION_ERROR}:
        return 503
    return 502


@router.post("/ai/insights", response_class=HTMLResponse)
async def generate_ai_insights(
    request: Request,
    _: None = Depends(require_csrf),
    file: UploadFile = File(...),
) -> HTMLResponse:
    csrf_token = request.cookies.get(CSRF_COOKIE_NAME)
    loaded = await _load_csv_upload(request, file)
    if isinstance(loaded, CsvValidationSummary):
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"errors": loaded.errors, "csrf_token": csrf_token},
            status_code=_summary_status(loaded),
        )
    summary, normalized = _summary_for_result(loaded)
    if not summary.is_valid or normalized is None:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"errors": summary.errors, "csrf_token": csrf_token},
            status_code=_summary_status(summary),
        )

    analysis = analyze_rows(
        normalized.valid_rows,
        total_rows=normalized.total_rows,
        invalid_rows=normalized.invalid_count,
    )
    insights = detect_insights(analysis, normalized.valid_rows)
    context = {
        "analysis": analysis,
        "charts": build_dashboard_charts(analysis),
        "insights": insights,
        "csrf_token": csrf_token,
        "ai_mode": request.app.state.settings.ai_mode.value,
    }
    client_host = request.client.host if request.client else "unknown"
    if not request.app.state.ai_rate_limiter.allow(client_host):
        context["ai_error"] = AiErrorCode.RATE_LIMITED
        return templates.TemplateResponse(
            request=request, name="dashboard.html", context=context, status_code=429
        )
    try:
        provider = build_ai_provider(request.app.state.settings)
        context["ai_response"] = provider.generate(build_ai_context(analysis, insights))
    except AiServiceError as exc:
        context["ai_error"] = exc.code
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context=context,
            status_code=_ai_status(exc.code),
        )
    return templates.TemplateResponse(
        request=request, name="dashboard.html", context=context
    )
