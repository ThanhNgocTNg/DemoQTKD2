"""Pure-Python parsers and writers for CSV, XLSX, and Google Sheets links."""

from __future__ import annotations

import csv
import datetime as dt
import io
import posixpath
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


# Standard Excel built-in date format IDs
_BUILTIN_DATE_NUMFMTS = {
    14, 15, 16, 17, 18, 19, 20, 21, 22,
    45, 46, 47,
}

_SHEET_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


@dataclass
class ParsedSheet:
    """Represents a single tabular sheet extracted from CSV, XLSX, or Google Sheets."""

    name: str
    headers: List[str]
    rows: List[Dict[str, str]]
    raw_rows: List[List[str]]


class DataImportError(Exception):
    """Raised when an uploaded file or Google Sheets URL cannot be parsed or accessed."""


def _decode_text_bytes(content: bytes) -> str:
    """Decode text bytes trying UTF-8 (with BOM) first, then common Windows encodings."""
    for encoding in ("utf-8-sig", "utf-8", "cp1258", "cp1252", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _clean_cell_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _deduplicate_headers(raw_headers: List[str]) -> List[str]:
    """Ensure headers are non-empty and unique while keeping readable column names."""
    seen: Dict[str, int] = {}
    headers: List[str] = []
    for idx, h in enumerate(raw_headers):
        base = h.strip() or f"Cot_{idx + 1}"
        count = seen.get(base, 0) + 1
        seen[base] = count
        headers.append(base if count == 1 else f"{base}_{count}")
    return headers


def _rows_to_parsed_sheet(name: str, matrix: List[List[str]]) -> Optional[ParsedSheet]:
    """Convert a 2D list of strings into a ParsedSheet, finding the first non-empty header row."""
    non_empty_rows = [row for row in matrix if any(cell.strip() for cell in row)]
    if not non_empty_rows:
        return None

    # First non-empty row is treated as header row; trim trailing empty header columns
    header_row = list(non_empty_rows[0])
    while header_row and not header_row[-1].strip():
        header_row.pop()
    if not header_row:
        return None

    headers = _deduplicate_headers(header_row)
    col_count = len(headers)

    dict_rows: List[Dict[str, str]] = []
    clean_raw_rows: List[List[str]] = [headers]

    for row in non_empty_rows[1:]:
        padded = list(row[:col_count]) + [""] * max(0, col_count - len(row))
        # Preserve extra trailing non-empty cells if data extends beyond header width
        if len(row) > col_count and any(c.strip() for c in row[col_count:]):
            extra_len = len(row) - col_count
            for k in range(extra_len):
                col_name = f"Cot_{col_count + k + 1}"
                headers.append(col_name)
            col_count = len(headers)
            padded = list(row)
            for existing in dict_rows:
                for k in range(extra_len):
                    existing[headers[col_count - extra_len + k]] = ""

        if not any(cell.strip() for cell in padded):
            continue
        row_dict = {headers[i]: padded[i].strip() for i in range(col_count)}
        dict_rows.append(row_dict)
        clean_raw_rows.append([padded[i].strip() for i in range(col_count)])

    return ParsedSheet(
        name=name,
        headers=headers,
        rows=dict_rows,
        raw_rows=clean_raw_rows,
    )


def parse_csv_bytes(content: bytes, sheet_name: str = "Sheet1") -> List[ParsedSheet]:
    """Parse CSV bytes into a single-element list of ParsedSheet."""
    text = _decode_text_bytes(content)
    if not text.strip():
        raise DataImportError(f"File CSV '{sheet_name}' rỗng.")

    sample = text[:8192]
    delimiter = ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        # Fallback heuristic: check if semicolons dominate in the header line
        first_line = sample.splitlines()[0] if sample.splitlines() else sample
        if first_line.count(";") > first_line.count(","):
            delimiter = ";"
        elif first_line.count("\t") > first_line.count(","):
            delimiter = "\t"

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    matrix = [[_clean_cell_value(cell) for cell in row] for row in reader]
    parsed = _rows_to_parsed_sheet(sheet_name, matrix)
    if parsed is None:
        raise DataImportError(f"Không tìm thấy dữ liệu hợp lệ trong CSV '{sheet_name}'.")
    return [parsed]


def _col_letters_to_index(letters: str) -> int:
    """Convert Excel column letters (e.g., 'A' -> 0, 'AA' -> 26)."""
    idx = 0
    for ch in letters.upper():
        if "A" <= ch <= "Z":
            idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return max(0, idx - 1)


def _index_to_col_letters(idx: int) -> str:
    """Convert 0-based column index to Excel column letters (0 -> 'A')."""
    result = []
    n = idx + 1
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result.append(chr(ord("A") + rem))
    return "".join(reversed(result))


def _cell_ref_to_col_idx(ref: str) -> Optional[int]:
    match = re.match(r"^([A-Za-z]+)\d+$", ref.strip())
    if not match:
        return None
    return _col_letters_to_index(match.group(1))


def _extract_xml_text_runs(element: ET.Element) -> str:
    """Extract concatenated text from <t> or rich-text <r><t> elements inside an XML node."""
    parts: List[str] = []
    for node in element.iter():
        tag = node.tag.split("}")[-1]
        if tag == "t" and node.text is not None:
            parts.append(node.text)
    return "".join(parts)


def _parse_xlsx_shared_strings(zf: zipfile.ZipFile) -> List[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    strings: List[str] = []
    for si in root:
        if si.tag.split("}")[-1] == "si":
            strings.append(_extract_xml_text_runs(si))
    return strings


def _parse_xlsx_date_style_indices(zf: zipfile.ZipFile) -> set[int]:
    """Identify cell style indices (`cellXfs`) that correspond to date formats."""
    if "xl/styles.xml" not in zf.namelist():
        return set()
    try:
        root = ET.fromstring(zf.read("xl/styles.xml"))
    except ET.ParseError:
        return set()

    custom_date_fmts: set[int] = set()
    num_fmts = root.find(f"{{{_SHEET_MAIN_NS}}}numFmts")
    if num_fmts is not None:
        for nf in num_fmts:
            fmt_id = nf.attrib.get("numFmtId")
            code = (nf.attrib.get("formatCode") or "").lower()
            # Heuristic: contains y/m/d date tokens and not purely currency/text
            if fmt_id and any(tok in code for tok in ("yy", "mm", "dd")) and "red" not in code:
                try:
                    custom_date_fmts.add(int(fmt_id))
                except ValueError:
                    pass

    date_style_indices: set[int] = set()
    cell_xfs = root.find(f"{{{_SHEET_MAIN_NS}}}cellXfs")
    if cell_xfs is not None:
        for idx, xf in enumerate(cell_xfs):
            try:
                num_fmt_id = int(xf.attrib.get("numFmtId", "0"))
            except ValueError:
                continue
            if num_fmt_id in _BUILTIN_DATE_NUMFMTS or num_fmt_id in custom_date_fmts:
                date_style_indices.add(idx)
    return date_style_indices


def _excel_serial_to_date_str(serial_val: float) -> str:
    """Convert Excel 1900-epoch serial number to YYYY-MM-DD."""
    base = dt.datetime(1899, 12, 30)
    target = base + dt.timedelta(days=serial_val)
    if target.hour == 0 and target.minute == 0 and target.second == 0:
        return target.strftime("%Y-%m-%d")
    return target.strftime("%Y-%m-%d %H:%M")


def _format_numeric_cell(raw_val: str, style_idx: Optional[int], date_styles: set[int]) -> str:
    if not raw_val:
        return ""
    try:
        num = float(raw_val)
    except ValueError:
        return raw_val

    if style_idx is not None and style_idx in date_styles and 1 <= num <= 2958465:
        return _excel_serial_to_date_str(num)

    if num.is_integer():
        return str(int(num))
    return f"{num:g}" if abs(num) >= 1e12 else str(num)


def _resolve_workbook_sheets(zf: zipfile.ZipFile) -> List[Tuple[str, str]]:
    """Return ordered list of (sheet_name, zip_entry_path) inside the XLSX archive."""
    if "xl/workbook.xml" not in zf.namelist():
        raise DataImportError("File XLSX không hợp lệ: thiếu xl/workbook.xml.")

    wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
    rel_map: Dict[str, str] = {}
    rels_path = "xl/_rels/workbook.xml.rels"
    if rels_path in zf.namelist():
        rels_root = ET.fromstring(zf.read(rels_path))
        for rel in rels_root:
            rid = rel.attrib.get("Id")
            target = rel.attrib.get("Target", "")
            if rid and target:
                normalized = target.lstrip("/")
                if not normalized.startswith("xl/"):
                    normalized = posixpath.normpath(posixpath.join("xl", normalized))
                rel_map[rid] = normalized

    sheets: List[Tuple[str, str]] = []
    sheets_node = wb_root.find(f"{{{_SHEET_MAIN_NS}}}sheets")
    if sheets_node is not None:
        for idx, sh in enumerate(sheets_node, start=1):
            name = sh.attrib.get("name") or f"Sheet{idx}"
            rid = sh.attrib.get(f"{{{_REL_NS}}}id")
            target_path = rel_map.get(rid or "", f"xl/worksheets/sheet{idx}.xml")
            if target_path in zf.namelist():
                sheets.append((name, target_path))

    if not sheets:
        # Fallback: discover worksheet XMLs directly
        ws_paths = sorted(
            p for p in zf.namelist() if re.match(r"^xl/worksheets/sheet\d+\.xml$", p)
        )
        for idx, p in enumerate(ws_paths, start=1):
            sheets.append((f"Sheet{idx}", p))

    return sheets


def parse_xlsx_bytes(content: bytes) -> List[ParsedSheet]:
    """Parse all non-empty worksheets from an XLSX file bytes payload."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise DataImportError("File không đúng định dạng XLSX hợp lệ.") from exc

    with zf:
        shared_strings = _parse_xlsx_shared_strings(zf)
        date_styles = _parse_xlsx_date_style_indices(zf)
        sheet_specs = _resolve_workbook_sheets(zf)

        parsed_sheets: List[ParsedSheet] = []
        for sheet_name, entry_path in sheet_specs:
            root = ET.fromstring(zf.read(entry_path))
            sheet_data = root.find(f"{{{_SHEET_MAIN_NS}}}sheetData")
            if sheet_data is None:
                continue

            matrix: List[List[str]] = []
            for row_el in sheet_data:
                if row_el.tag.split("}")[-1] != "row":
                    continue
                row_cells: Dict[int, str] = {}
                fallback_col = 0
                for cell_el in row_el:
                    if cell_el.tag.split("}")[-1] != "c":
                        continue
                    ref = cell_el.attrib.get("r", "")
                    col_idx = _cell_ref_to_col_idx(ref)
                    if col_idx is None:
                        col_idx = fallback_col
                    fallback_col = col_idx + 1

                    cell_type = cell_el.attrib.get("t", "n")
                    style_raw = cell_el.attrib.get("s")
                    style_idx = int(style_raw) if style_raw and style_raw.isdigit() else None

                    val_el = cell_el.find(f"{{{_SHEET_MAIN_NS}}}v")
                    is_el = cell_el.find(f"{{{_SHEET_MAIN_NS}}}is")
                    raw_val = val_el.text if val_el is not None and val_el.text is not None else ""

                    if cell_type == "s":
                        if raw_val.isdigit():
                            s_idx = int(raw_val)
                            val = shared_strings[s_idx] if 0 <= s_idx < len(shared_strings) else ""
                        else:
                            val = ""
                    elif cell_type == "inlineStr":
                        val = _extract_xml_text_runs(is_el) if is_el is not None else ""
                    elif cell_type == "b":
                        val = "TRUE" if raw_val == "1" else "FALSE"
                    elif cell_type in ("str", "e"):
                        val = raw_val
                    else:
                        val = _format_numeric_cell(raw_val, style_idx, date_styles)

                    row_cells[col_idx] = val.strip()

                if row_cells:
                    max_col = max(row_cells.keys())
                    matrix.append([row_cells.get(i, "") for i in range(max_col + 1)])

            parsed = _rows_to_parsed_sheet(sheet_name, matrix)
            if parsed is not None:
                parsed_sheets.append(parsed)

    if not parsed_sheets:
        raise DataImportError("File XLSX không chứa sheet dữ liệu nào hợp lệ.")
    return parsed_sheets


def extract_google_sheets_info(url: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Extract (spreadsheet_id, gid, published_id) from any common Google Sheets URL."""
    cleaned = url.strip()
    if not cleaned:
        return None, None, None

    parsed = urllib.parse.urlparse(cleaned)
    if "docs.google.com" not in parsed.netloc and "spreadsheets" not in cleaned:
        raise DataImportError("URL không phải là đường dẫn Google Sheets hợp lệ.")

    # Published link format: /spreadsheets/d/e/2PACX-.../pubhtml or /pub?output=csv
    pub_match = re.search(r"/spreadsheets/d/e/(2PACX-[a-zA-Z0-9_-]+)", parsed.path)
    gid_match = re.search(r"gid=(\d+)", cleaned)
    gid = gid_match.group(1) if gid_match else None
    if pub_match:
        return None, gid, pub_match.group(1)

    id_match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", parsed.path)
    if not id_match:
        raise DataImportError(
            "Không tìm thấy Spreadsheet ID trong link Google Sheets. "
            "Ví dụ hợp lệ: https://docs.google.com/spreadsheets/d/<ID>/edit"
        )
    return id_match.group(1), gid, None


def fetch_google_sheets(url: str, timeout: int = 20) -> Tuple[List[ParsedSheet], str]:
    """Fetch a Google Sheets URL as XLSX (multi-sheet) or CSV (single tab / published)."""
    sheet_id, gid, pub_id = extract_google_sheets_info(url)
    candidate_urls: List[Tuple[str, str]] = []

    if pub_id:
        csv_url = f"https://docs.google.com/spreadsheets/d/e/{pub_id}/pub?output=csv"
        if gid:
            csv_url += f"&gid={gid}&single=true"
        candidate_urls.append(("csv", csv_url))
    elif sheet_id:
        # Prefer XLSX export to load all tabs at once, unless user explicitly targets a specific non-zero gid
        xlsx_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
        csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
        if gid:
            csv_url += f"&gid={gid}"
            # Still include xlsx so multi-tab workbooks load completely when sharing a default URL
        candidate_urls.append(("xlsx", xlsx_url))
        candidate_urls.append(("csv", csv_url))

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; MinhAnSalesAgent/1.0)"
    }
    last_error: Optional[str] = None

    for fmt, target_url in candidate_urls:
        req = urllib.request.Request(target_url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content_type = (resp.headers.get("Content-Type") or "").lower()
                data = resp.read()
                if "text/html" in content_type or data.lstrip().startswith(b"<!DOCTYPE html") or b"accounts.google.com" in data[:4096]:
                    last_error = (
                        "Google Sheets chưa được mở quyền xem công khai. "
                        "Vui lòng vào Chia sẻ (Share) -> chọn 'Bất kỳ ai có đường liên kết đều có thể xem' (Viewer) "
                        "hoặc tải xuống thành file .xlsx / .csv rồi tải lên."
                    )
                    continue

                if fmt == "xlsx" and data[:2] == b"PK":
                    sheets = parse_xlsx_bytes(data)
                    return sheets, "xlsx"
                if fmt == "csv":
                    sheets = parse_csv_bytes(data, sheet_name=f"GoogleSheet_{gid or '1'}")
                    return sheets, "csv"
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                last_error = (
                    "Không có quyền truy cập Google Sheets (HTTP 401/403). "
                    "Hãy bật 'Bất kỳ ai có đường liên kết đều có thể xem' hoặc xuất file .xlsx/.csv."
                )
            elif exc.code == 404:
                last_error = "Không tìm thấy Google Sheets theo link đã nhập (HTTP 404)."
            else:
                last_error = f"Lỗi HTTP {exc.code} khi tải Google Sheets."
        except urllib.error.URLError as exc:
            last_error = f"Không thể kết nối tới Google Sheets ({exc.reason}). Hãy kiểm tra kết nối mạng hoặc tải trực tiếp file CSV/XLSX."
        except Exception as exc:  # noqa: BLE001
            last_error = f"Lỗi đọc dữ liệu Google Sheets: {exc}"

    raise DataImportError(last_error or "Không thể đọc dữ liệu từ link Google Sheets.")


def parse_uploaded_file(filename: str, content: bytes) -> List[ParsedSheet]:
    """Dispatch uploaded CSV or XLSX file to the appropriate parser."""
    lower = filename.lower()
    if lower.endswith(".xlsx"):
        return parse_xlsx_bytes(content)
    if lower.endswith(".csv"):
        base_name = filename.rsplit(".", 1)[0]
        return parse_csv_bytes(content, sheet_name=base_name)
    if lower.endswith(".xls"):
        raise DataImportError(
            "Định dạng .xls cũ chưa được hỗ trợ trực tiếp. Vui lòng lưu file sang .xlsx hoặc .csv rồi tải lên."
        )
    # Try magic bytes fallback
    if content[:2] == b"PK":
        return parse_xlsx_bytes(content)
    return parse_csv_bytes(content, sheet_name=filename)


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def build_xlsx_bytes(sheets: List[Tuple[str, List[str], List[List[Any]]]]) -> bytes:
    """Create a valid multi-sheet XLSX file in memory without third-party packages."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        sheet_overrides = "\n".join(
            f'  <Override PartName="/xl/worksheets/sheet{i}.xml" '
            f'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(1, len(sheets) + 1)
        )
        content_types = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
{sheet_overrides}
</Types>"""
        zf.writestr("[Content_Types].xml", content_types)

        root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
        zf.writestr("_rels/.rels", root_rels)

        sheet_entries = []
        wb_rel_entries = []
        for idx, (sheet_name, _, _) in enumerate(sheets, start=1):
            safe_name = _xml_escape(sheet_name[:31])
            sheet_entries.append(f'    <sheet name="{safe_name}" sheetId="{idx}" r:id="rId{idx}"/>')
            wb_rel_entries.append(
                f'  <Relationship Id="rId{idx}" '
                f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                f'Target="worksheets/sheet{idx}.xml"/>'
            )
        style_rid = f"rId{len(sheets) + 1}"
        wb_rel_entries.append(
            f'  <Relationship Id="{style_rid}" '
            f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
            f'Target="styles.xml"/>'
        )

        workbook_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
{chr(10).join(sheet_entries)}
  </sheets>
</workbook>"""
        zf.writestr("xl/workbook.xml", workbook_xml)

        wb_rels = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
{chr(10).join(wb_rel_entries)}
</Relationships>"""
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels)

        styles_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2">
    <font><sz val="11"/><name val="Calibri"/></font>
    <font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
  </fonts>
  <fills count="3">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF1D6FD8"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="2">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>
  </cellXfs>
</styleSheet>"""
        zf.writestr("xl/styles.xml", styles_xml)

        for idx, (_, headers, rows) in enumerate(sheets, start=1):
            all_rows: List[List[Any]] = [headers] + rows
            row_xml_parts: List[str] = []
            for r_idx, row_vals in enumerate(all_rows, start=1):
                cells_xml: List[str] = []
                style_attr = ' s="1"' if r_idx == 1 else ""
                for c_idx, val in enumerate(row_vals):
                    ref = f"{_index_to_col_letters(c_idx)}{r_idx}"
                    if isinstance(val, (int, float)) and not isinstance(val, bool):
                        cells_xml.append(f'<c r="{ref}"{style_attr}><v>{val}</v></c>')
                    else:
                        text_val = "" if val is None else str(val)
                        # Strip ASCII control characters invalid in XML 1.0
                        text_val = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text_val)
                        cells_xml.append(
                            f'<c r="{ref}" t="inlineStr"{style_attr}><is><t xml:space="preserve">{_xml_escape(text_val)}</t></is></c>'
                        )
                row_xml_parts.append(f'    <row r="{r_idx}">{"".join(cells_xml)}</row>')

            ws_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
{chr(10).join(row_xml_parts)}
  </sheetData>
</worksheet>"""
            zf.writestr(f"xl/worksheets/sheet{idx}.xml", ws_xml)

    return buf.getvalue()

