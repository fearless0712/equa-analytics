from decimal import Decimal
from types import MappingProxyType

from app.domain.models import CsvColumnSpec, CsvErrorCode, CsvValueType

SUPPORTED_CSV_ENCODINGS = ("utf-8", "utf-8-sig")
CSV_HEADER_NORMALIZATION = ("remove_bom", "strip", "lowercase")

CSV_ERROR_MESSAGES = MappingProxyType(
    {
        CsvErrorCode.EMPTY_FILE: "The CSV file is empty.",
        CsvErrorCode.FILE_TOO_LARGE: "The CSV file exceeds the allowed size.",
        CsvErrorCode.INVALID_FILE_TYPE: "The uploaded file must have a .csv extension.",
        CsvErrorCode.INVALID_ENCODING: "The CSV file must use UTF-8 encoding.",
        CsvErrorCode.NUL_BYTE: "The CSV file contains a prohibited NUL byte.",
        CsvErrorCode.PARSE_ERROR: "The CSV file could not be parsed.",
        CsvErrorCode.TOO_MANY_ROWS: "The CSV file contains too many rows.",
        CsvErrorCode.MISSING_REQUIRED_COLUMN: "A required column is missing.",
        CsvErrorCode.DUPLICATE_COLUMN: "A column name appears more than once.",
        CsvErrorCode.UNKNOWN_COLUMN: "The CSV file contains an unknown column.",
        CsvErrorCode.INVALID_DATE: "Date must be a valid date.",
        CsvErrorCode.INVALID_NUMBER: "The value must be numeric.",
        CsvErrorCode.INVALID_QUANTITY: "Quantity must be a whole number within the allowed range.",
        CsvErrorCode.NEGATIVE_QUANTITY: "Quantity must be zero or greater.",
        CsvErrorCode.NEGATIVE_UNIT_PRICE: "Unit price must be zero or greater.",
        CsvErrorCode.UNIT_PRICE_TOO_LARGE: "Unit price exceeds the allowed maximum.",
        CsvErrorCode.INVALID_DISCOUNT: "Discount must be between zero and one.",
        CsvErrorCode.EMPTY_PRODUCT: "Product must not be empty.",
        CsvErrorCode.EMPTY_CATEGORY: "Category must not be empty.",
        CsvErrorCode.EMPTY_REGION: "Region must not be empty.",
        CsvErrorCode.STRING_TOO_LONG: "The value exceeds the maximum length.",
        CsvErrorCode.NO_VALID_ROWS: "The CSV file contains no valid data rows.",
    }
)

CSV_COLUMN_SPECS = (
    CsvColumnSpec(name="date", value_type=CsvValueType.DATE, required=True),
    CsvColumnSpec(name="product", value_type=CsvValueType.STRING, required=True),
    CsvColumnSpec(name="category", value_type=CsvValueType.STRING, required=True),
    CsvColumnSpec(name="region", value_type=CsvValueType.STRING, required=True),
    CsvColumnSpec(
        name="quantity", value_type=CsvValueType.NUMERIC, required=True, minimum=0
    ),
    CsvColumnSpec(
        name="unit_price", value_type=CsvValueType.NUMERIC, required=True, minimum=0
    ),
    CsvColumnSpec(
        name="discount",
        value_type=CsvValueType.NUMERIC,
        required=False,
        minimum=0,
        maximum=1,
        default_value=0,
    ),
    CsvColumnSpec(
        name="customer_type", value_type=CsvValueType.STRING, required=False
    ),
)

REQUIRED_COLUMNS = tuple(spec.name for spec in CSV_COLUMN_SPECS if spec.required)
OPTIONAL_COLUMNS = tuple(spec.name for spec in CSV_COLUMN_SPECS if not spec.required)
ALLOWED_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

SALES_FORMULA = "quantity * unit_price * (1 - discount)"
SALES_FORMULA_FIELDS = ("quantity", "unit_price", "discount")
MAX_TEXT_LENGTH = 200
MAX_NUMERIC_TEXT_LENGTH = 64
MAX_QUANTITY = 1_000_000_000
MAX_UNIT_PRICE = Decimal("1000000000")


def normalize_csv_column_name(name: str) -> str:
    """Apply the canonical header normalization without reading CSV content."""
    return name.removeprefix("\ufeff").strip().lower()
