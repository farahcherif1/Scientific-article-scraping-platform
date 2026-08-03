import { useState } from "react";
import { X } from "lucide-react";
import type { ExcelPreview } from "../api/keywords";
import Select from "./Select";

interface Props {
  fileName: string;
  preview: ExcelPreview;
  defaultSheet: string;
  defaultColumn: string | null;
  onCancel: () => void;
  onConfirm: (sheetName: string, columnName: string) => void;
}

export default function ColumnMappingDialog({
  fileName,
  preview,
  defaultSheet,
  defaultColumn,
  onCancel,
  onConfirm,
}: Props) {
  const [sheet, setSheet] = useState(defaultSheet);
  const [column, setColumn] = useState(defaultColumn ?? preview.columns[defaultSheet]?.[0] ?? "");

  const columnsForSheet = preview.columns[sheet] ?? [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 px-4">
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-lg font-semibold text-slate-900">Choose keyword column</h3>
            <p className="mt-1 text-sm text-slate-500">{fileName}</p>
          </div>
          <button
            onClick={onCancel}
            className="rounded-full p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="mt-5 space-y-4">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-700">Sheet</label>
            <Select
              value={sheet}
              onChange={(nextSheet) => {
                setSheet(nextSheet);
                setColumn(preview.columns[nextSheet]?.[0] ?? "");
              }}
              options={preview.sheet_names.map((s) => ({ value: s, label: s }))}
              aria-label="Sheet"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-700">
              Column containing keywords
            </label>
            <Select
              value={column}
              onChange={setColumn}
              options={columnsForSheet.map((c) => ({ value: c, label: c }))}
              aria-label="Column containing keywords"
            />
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
          >
            Cancel
          </button>
          <button
            onClick={() => column && onConfirm(sheet, column)}
            disabled={!column}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            Import
          </button>
        </div>
      </div>
    </div>
  );
}
