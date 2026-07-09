import { useMemo, useRef, useState } from "react";
import {
  Pencil,
  List,
  Upload,
  FileText,
  CheckCircle2,
  Trash2,
  Shield,
  ArrowRight,
  X,
} from "lucide-react";
import TopNav from "../components/TopNav";
import ColumnMappingDialog from "../components/ColumnMappingDialog";
import {
  splitKeywordString,
  dedupeCaseInsensitive,
  previewExcelFile,
  extractExcelKeywords,
  guessKeywordColumn,
  type ExcelPreview,
  type ImportReport,
} from "../api/keywords";

export default function KeywordsPage() {
  const [manualText, setManualText] = useState("");
  const [excelKeywords, setExcelKeywords] = useState<string[]>([]);
  const [removed, setRemoved] = useState<Set<string>>(new Set());

  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [pendingPreview, setPendingPreview] = useState<ExcelPreview | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [importReport, setImportReport] = useState<{
    fileName: string;
    report: ImportReport;
  } | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const manualKeywords = useMemo(() => splitKeywordString(manualText), [manualText]);

  const keywords = useMemo(() => {
    const merged = dedupeCaseInsensitive([...manualKeywords, ...excelKeywords]);
    return merged.filter((k) => !removed.has(k.toLowerCase()));
  }, [manualKeywords, excelKeywords, removed]);

  function removeKeyword(keyword: string) {
    setRemoved((prev) => new Set(prev).add(keyword.toLowerCase()));
  }

  function clearAll() {
    setManualText("");
    setExcelKeywords([]);
    setImportReport(null);
    setRemoved(new Set());
  }

  async function handleFile(file: File) {
    if (!file.name.toLowerCase().endsWith(".xlsx") && !file.name.toLowerCase().endsWith(".xlsm")) {
      setUploadError("Only .xlsx files are supported.");
      return;
    }
    setUploadError(null);
    setIsUploading(true);
    try {
      const preview = await previewExcelFile(file);
      setPendingFile(file);
      setPendingPreview(preview);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Could not read that file.");
    } finally {
      setIsUploading(false);
    }
  }

  async function confirmImport(sheetName: string, columnName: string) {
    if (!pendingFile) return;
    setIsUploading(true);
    setUploadError(null);
    try {
      const result = await extractExcelKeywords(pendingFile, sheetName, columnName);
      setExcelKeywords((prev) => dedupeCaseInsensitive([...prev, ...result.keywords]));
      setImportReport({ fileName: pendingFile.name, report: result.report });
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Could not extract keywords.");
    } finally {
      setIsUploading(false);
      setPendingFile(null);
      setPendingPreview(null);
    }
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }

  const skippedTotal = importReport
    ? Object.values(importReport.report.skipped_reasons).reduce((a, b) => a + b, 0)
    : 0;
  const skippedLabel = importReport
    ? Object.keys(importReport.report.skipped_reasons)[0] === "duplicate"
      ? "Skipped (Duplicate)"
      : "Skipped (Empty)"
    : "";

  return (
    <div className="min-h-screen bg-slate-50">
      <TopNav />

      <main className="mx-auto max-w-7xl px-8 py-10">
        <h1 className="text-3xl font-bold text-slate-900">Define Scraper Keywords</h1>
        <div className="mt-2 h-0.5 w-16 bg-emerald-500" />
        <p className="mt-4 max-w-2xl text-slate-500">
          Enter your research keywords manually or upload an Excel file to extract keywords
          from a specific column. Cleaned, deduplicated preview chips will update automatically.
        </p>

        <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* Left column */}
          <div className="flex flex-col gap-6">
            {/* Manual entry */}
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Pencil className="h-4 w-4 text-emerald-600" />
                  <h2 className="font-semibold text-slate-900">Manual Keyword Entry</h2>
                </div>
                <span className="text-xs text-slate-400">
                  Separators: comma, semicolon, or newline
                </span>
              </div>
              <div className="mt-4 border-t border-slate-100 pt-4">
                <textarea
                  value={manualText}
                  onChange={(e) => setManualText(e.target.value)}
                  placeholder={
                    "Type or paste keywords here...\nExample:\nlarge language models\nretrieval-augmented generation, prompt engineering; transformer models"
                  }
                  className="h-44 w-full resize-none rounded-lg border border-slate-200 p-4 text-sm text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>
            </div>

            {/* Import from Excel */}
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Upload className="h-4 w-4 text-emerald-600" />
                  <h2 className="font-semibold text-slate-900">Import from Excel</h2>
                </div>
                <span className="text-xs text-slate-400">Supports .xlsx files</span>
              </div>

              <div className="mt-4 border-t border-slate-100 pt-4">
                <div
                  onClick={() => fileInputRef.current?.click()}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setIsDragging(true);
                  }}
                  onDragLeave={() => setIsDragging(false)}
                  onDrop={handleDrop}
                  className={`flex cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed py-14 transition-colors ${
                    isDragging
                      ? "border-emerald-400 bg-emerald-50/50"
                      : "border-slate-200 hover:border-emerald-300 hover:bg-emerald-50/30"
                  }`}
                >
                  <FileText className="h-10 w-10 text-slate-300" />
                  <div className="text-center">
                    <p className="font-medium text-slate-700">
                      {isUploading ? "Reading file..." : "Drag and drop your Excel file here"}
                    </p>
                    <p className="text-sm text-slate-400">or click to browse local files</p>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      fileInputRef.current?.click();
                    }}
                    className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                  >
                    Browse Files
                  </button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".xlsx,.xlsm"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) handleFile(file);
                      e.target.value = "";
                    }}
                  />
                </div>
                {uploadError && (
                  <p className="mt-3 text-sm text-rose-600">{uploadError}</p>
                )}
              </div>
            </div>

            {/* Import report */}
            {importReport && (
              <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex items-center gap-3">
                  <div className="rounded-full bg-emerald-50 p-2">
                    <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                  </div>
                  <div>
                    <p className="font-semibold text-slate-900">
                      Import Report ({importReport.fileName})
                    </p>
                    <p className="text-sm text-slate-500">
                      {importReport.report.rows_read} rows read successfully
                    </p>
                  </div>
                </div>
                <div className="flex gap-8 text-right">
                  <div>
                    <p className="text-xl font-bold text-emerald-600">
                      {importReport.report.rows_kept}
                    </p>
                    <p className="text-xs text-slate-500">Kept</p>
                  </div>
                  <div>
                    <p className="text-xl font-bold text-rose-500">{skippedTotal}</p>
                    <p className="text-xs text-slate-500">{skippedLabel}</p>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Right column: live preview */}
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <List className="h-4 w-4 text-emerald-600" />
                <h2 className="font-semibold text-slate-900">Live Keyword Preview</h2>
              </div>
              <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">
                {keywords.length} Unique
              </span>
            </div>

            <div className="mt-4 flex min-h-[300px] flex-wrap content-start gap-2 border-t border-slate-100 pt-4">
              {keywords.length === 0 ? (
                <p className="text-sm text-slate-400">
                  Your cleaned keywords will appear here as you type or import a file.
                </p>
              ) : (
                keywords.map((kw) => (
                  <span
                    key={kw}
                    className="inline-flex items-center gap-1.5 rounded-full border border-emerald-100 bg-emerald-50 px-3 py-1.5 text-sm font-medium text-emerald-700"
                  >
                    {kw}
                    <button
                      onClick={() => removeKeyword(kw)}
                      className="text-emerald-500 hover:text-emerald-900"
                      aria-label={`Remove ${kw}`}
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </span>
                ))
              )}
            </div>

            <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-4 text-xs text-slate-500">
              <div className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                Deduplication active
              </div>
              <button
                onClick={clearAll}
                className="flex items-center gap-1 text-emerald-600 hover:text-emerald-700"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Clear All
              </button>
            </div>
          </div>
        </div>

        <div className="mt-8 flex items-center justify-between border-t border-slate-200 pt-6">
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Shield className="h-4 w-4 text-emerald-600" />
            Keywords are parsed client-side and saved to your session configuration.
          </div>
          <button
            disabled={keywords.length === 0}
            className="flex items-center gap-2 rounded-lg bg-emerald-600 px-6 py-3 font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            Continue to Configuration
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </main>

      {pendingFile && pendingPreview && (
        <ColumnMappingDialog
          fileName={pendingFile.name}
          preview={pendingPreview}
          defaultSheet={pendingPreview.sheet_names[0]}
          defaultColumn={guessKeywordColumn(
            pendingPreview.columns[pendingPreview.sheet_names[0]] ?? []
          )}
          onCancel={() => {
            setPendingFile(null);
            setPendingPreview(null);
          }}
          onConfirm={confirmImport}
        />
      )}
    </div>
  );
}
