import csv
from io import StringIO

from app.domain.models import (
    CsvErrorCode,
    CsvRawRow,
    CsvReadResult,
    CsvValidationError,
    CsvValidationResult,
)
from app.services.csv_validator import validate_csv_headers

UTF8_BOM = b"\xef\xbb\xbf"


def _failed_result(
    *errors: CsvValidationError,
    headers: tuple[str, ...] = (),
    rows: tuple[CsvRawRow, ...] = (),
    total_rows: int = 0,
    valid_rows: int = 0,
    invalid_rows: int = 0,
    encoding: str | None = None,
) -> CsvReadResult:
    validation = CsvValidationResult(
        is_valid=False,
        errors=errors,
        total_rows=total_rows,
        valid_rows=valid_rows,
        invalid_rows=invalid_rows,
    )
    return CsvReadResult(
        normalized_headers=headers,
        rows=rows,
        total_rows=total_rows,
        encoding=encoding,
        validation=validation,
    )


def read_csv_bytes(
    data: bytes,
    *,
    max_file_size: int,
    max_rows: int,
) -> CsvReadResult:
    if len(data) > max_file_size:
        return _failed_result(
            CsvValidationError(code=CsvErrorCode.FILE_TOO_LARGE)
        )
    if not data:
        return _failed_result(CsvValidationError(code=CsvErrorCode.EMPTY_FILE))

    encoding = "utf-8-sig" if data.startswith(UTF8_BOM) else "utf-8"
    try:
        decoded = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return _failed_result(
            CsvValidationError(code=CsvErrorCode.INVALID_ENCODING)
        )

    if "\x00" in decoded:
        return _failed_result(
            CsvValidationError(code=CsvErrorCode.NUL_BYTE), encoding=encoding
        )
    if not decoded.strip():
        return _failed_result(
            CsvValidationError(code=CsvErrorCode.EMPTY_FILE), encoding=encoding
        )

    if csv.field_size_limit() < max_file_size:
        csv.field_size_limit(max_file_size)
    reader = csv.reader(StringIO(decoded, newline=""), delimiter=",", strict=True)
    try:
        source_headers = next(reader)
    except StopIteration:
        return _failed_result(
            CsvValidationError(code=CsvErrorCode.EMPTY_FILE), encoding=encoding
        )
    except csv.Error:
        return _failed_result(
            CsvValidationError(code=CsvErrorCode.PARSE_ERROR, row=1),
            encoding=encoding,
        )

    headers, header_errors = validate_csv_headers(source_headers)
    if header_errors:
        return _failed_result(*header_errors, headers=headers, encoding=encoding)

    rows: list[CsvRawRow] = []
    total_rows = 0
    while True:
        row_number = reader.line_num + 1
        try:
            values = next(reader)
        except StopIteration:
            break
        except csv.Error:
            return _failed_result(
                CsvValidationError(code=CsvErrorCode.PARSE_ERROR, row=row_number),
                headers=headers,
                rows=tuple(rows),
                total_rows=total_rows + 1,
                valid_rows=len(rows),
                invalid_rows=1,
                encoding=encoding,
            )

        total_rows += 1
        if total_rows > max_rows:
            return _failed_result(
                CsvValidationError(
                    code=CsvErrorCode.TOO_MANY_ROWS,
                    row=row_number,
                ),
                headers=headers,
                rows=tuple(rows),
                total_rows=total_rows,
                valid_rows=len(rows),
                invalid_rows=1,
                encoding=encoding,
            )
        if len(values) != len(headers):
            return _failed_result(
                CsvValidationError(
                    code=CsvErrorCode.PARSE_ERROR,
                    row=row_number,
                ),
                headers=headers,
                rows=tuple(rows),
                total_rows=total_rows,
                valid_rows=len(rows),
                invalid_rows=1,
                encoding=encoding,
            )
        rows.append(CsvRawRow(row_number=row_number, values=tuple(values)))

    if not rows:
        return _failed_result(
            CsvValidationError(code=CsvErrorCode.NO_VALID_ROWS),
            headers=headers,
            encoding=encoding,
        )

    validation = CsvValidationResult(
        is_valid=True,
        total_rows=total_rows,
        valid_rows=total_rows,
        invalid_rows=0,
    )
    return CsvReadResult(
        normalized_headers=headers,
        rows=tuple(rows),
        total_rows=total_rows,
        encoding=encoding,
        validation=validation,
    )
