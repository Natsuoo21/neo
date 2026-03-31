"""Excel tool — Create and edit .xlsx files via openpyxl."""

import os

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

_DEFAULT_SAVE_DIR = os.path.expanduser(os.environ.get("DEFAULT_SAVE_DIR", "~/Documents/Neo"))

# Default header style
_HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
_HEADER_FILL = PatternFill(start_color="2B5797", end_color="2B5797", fill_type="solid")
_HEADER_ALIGNMENT = Alignment(horizontal="center", vertical="center")


def create_workbook(
    title: str,
    sheets: list[dict] | None = None,
    formatting: dict | None = None,
) -> str:
    """Create a new Excel workbook with optional sheets and formatting.

    Args:
        title: Filename (without extension) or full path.
        sheets: List of dicts with keys: name, headers (list[str]), rows (list[list]).
        formatting: Optional dict with style overrides.

    Returns:
        Absolute path to the created .xlsx file.
    """
    wb = Workbook()

    if not sheets:
        # Create a single empty sheet with the title
        ws = wb.active
        # Use just the filename part for sheet title (no path separators)
        sheet_name = os.path.basename(title).replace("/", "_").replace("\\", "_")
        ws.title = sheet_name[:31]  # Excel limits sheet names to 31 chars
    else:
        # Remove default sheet if we're creating named ones
        wb.remove(wb.active)

        for sheet_def in sheets:
            ws = wb.create_sheet(title=sheet_def.get("name", "Sheet")[:31])
            headers = sheet_def.get("headers", [])
            rows = sheet_def.get("rows", [])

            # Write headers with styling
            if headers:
                for col_idx, header in enumerate(headers, 1):
                    cell = ws.cell(row=1, column=col_idx, value=header)
                    cell.font = _HEADER_FONT
                    cell.fill = _HEADER_FILL
                    cell.alignment = _HEADER_ALIGNMENT

                # Freeze header row
                ws.freeze_panes = "A2"

            # Write data rows
            for row_idx, row_data in enumerate(rows, 2):
                for col_idx, value in enumerate(row_data, 1):
                    ws.cell(row=row_idx, column=col_idx, value=value)

            # Auto-fit column widths (approximate)
            for col_idx in range(1, len(headers) + 1):
                col_letter = get_column_letter(col_idx)
                max_len = len(str(headers[col_idx - 1])) if col_idx <= len(headers) else 8
                for row in rows:
                    if col_idx - 1 < len(row):
                        max_len = max(max_len, len(str(row[col_idx - 1])))
                ws.column_dimensions[col_letter].width = min(max_len + 4, 50)

    # Determine save path
    file_path = _resolve_path(title, ".xlsx")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    wb.save(file_path)
    return file_path


def _resolve_path(title: str, extension: str) -> str:
    """Resolve a title to an absolute file path."""
    if os.path.isabs(title):
        if not title.endswith(extension):
            title += extension
        return title

    # Sanitize filename
    safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
    safe_name = safe_name.strip().replace(" ", "_")
    if not safe_name.endswith(extension):
        safe_name += extension

    save_dir = os.path.expanduser(_DEFAULT_SAVE_DIR)
    return os.path.join(save_dir, safe_name)
