const API_BASE = import.meta.env.VITE_API_BASE_URL;

export function splitKeywordString(raw: string): string[] {
  return raw
    .split(/[\n,;]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function dedupeCaseInsensitive(list: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const item of list) {
    const key = item.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(item);
  }
  return result;
}

export interface ExcelPreview {
  sheet_names: string[];
  columns: Record<string, string[]>;
}

export interface ImportReport {
  rows_read: number;
  rows_kept: number;
  rows_skipped: number;
  skipped_reasons: Record<string, number>;
}

export interface ExcelExtractResult {
  keywords: string[];
  report: ImportReport;
}

async function parseErrorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    return body.detail || fallback;
  } catch {
    return fallback;
  }
}

export async function previewExcelFile(file: File): Promise<ExcelPreview> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/api/v1/keywords/import-excel/preview`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    throw new Error(await parseErrorDetail(res, "Could not read that file."));
  }
  return res.json();
}

export async function extractExcelKeywords(
  file: File,
  sheetName: string,
  columnName: string
): Promise<ExcelExtractResult> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("sheet_name", sheetName);
  formData.append("column_name", columnName);
  const res = await fetch(`${API_BASE}/api/v1/keywords/import-excel/extract`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    throw new Error(await parseErrorDetail(res, "Could not extract keywords from that column."));
  }
  return res.json();
}

/** Best-effort guess at which column holds keywords, for a sensible default in the mapping dialog. */
export function guessKeywordColumn(headers: string[]): string | null {
  const preferred = headers.find((h) => /keyword|term|topic|query/i.test(h));
  return preferred ?? headers[0] ?? null;
}
