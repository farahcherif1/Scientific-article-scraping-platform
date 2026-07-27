import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ClipboardPaste,
  Info,
  Loader2,
  Play,
  Plus,
  Save,
  Trash2,
  XCircle,
} from "lucide-react";
import TopNav from "../components/TopNav";
import {
  createCustomConnector,
  emptyCustomConnectorConfig,
  getCustomConnector,
  testCustomConnector,
  updateCustomConnector,
  type AuthType,
  type CustomConnectorConfig,
  type CustomConnectorTestResponse,
  type PaginationStyle,
  type TargetField,
} from "../api/customConnectors";
import { suggestFieldMappings, suggestResultsPath } from "../lib/jsonPathSuggest";

const STEPS = ["Basic Info & Auth", "Pagination", "Field Mapping & Test"] as const;

const AUTH_LABELS: Record<AuthType, string> = {
  none: "No authentication",
  api_key_header: "API key in a header",
  api_key_query_param: "API key in the query string",
};

const PAGINATION_LABELS: Record<PaginationStyle, string> = {
  none: "No pagination (source returns one page)",
  page: "Page number",
  offset: "Offset / limit",
  cursor: "Cursor / next-page token",
};

const FIELD_META: { field: TargetField; label: string; required?: boolean; hint: string }[] = [
  { field: "title", label: "Title", required: true, hint: "e.g. title or bibjson.title" },
  { field: "authors", label: "Authors", hint: "e.g. authors[].name or authFullName_s" },
  { field: "year", label: "Publication year", hint: "e.g. yearPublished or pubYear" },
  { field: "doi", label: "DOI", hint: "e.g. doi or externalIds.DOI" },
  { field: "abstract", label: "Abstract", hint: "e.g. abstract or abstractText" },
  { field: "citation_count", label: "Citation count", hint: "e.g. citationCount" },
  { field: "url", label: "URL / link", hint: "e.g. url or downloadUrl" },
  { field: "venue", label: "Venue / journal", hint: "e.g. venue or publisher" },
];

type KeyValueRow = { key: string; value: string };

function rowsToRecord(rows: KeyValueRow[]): Record<string, string> {
  const record: Record<string, string> = {};
  for (const row of rows) {
    if (row.key.trim()) record[row.key.trim()] = row.value;
  }
  return record;
}

function recordToRows(record: Record<string, string>): KeyValueRow[] {
  return Object.entries(record).map(([key, value]) => ({ key, value }));
}

function KeyValueEditor({
  label,
  rows,
  onChange,
}: {
  label: string;
  rows: KeyValueRow[];
  onChange: (rows: KeyValueRow[]) => void;
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <label className="text-sm font-medium text-slate-700">{label}</label>
        <button
          type="button"
          onClick={() => onChange([...rows, { key: "", value: "" }])}
          className="flex items-center gap-1 text-xs font-medium text-emerald-700 hover:text-emerald-800"
        >
          <Plus className="h-3.5 w-3.5" /> Add
        </button>
      </div>
      {rows.length === 0 && <p className="text-xs text-slate-400">None configured.</p>}
      <div className="flex flex-col gap-2">
        {rows.map((row, i) => (
          <div key={i} className="flex items-center gap-2">
            <input
              value={row.key}
              onChange={(e) =>
                onChange(rows.map((r, j) => (j === i ? { ...r, key: e.target.value } : r)))
              }
              placeholder="param name"
              className="w-1/2 rounded-lg border border-slate-200 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
            <input
              value={row.value}
              onChange={(e) =>
                onChange(rows.map((r, j) => (j === i ? { ...r, value: e.target.value } : r)))
              }
              placeholder="value"
              className="w-1/2 rounded-lg border border-slate-200 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
            <button
              type="button"
              onClick={() => onChange(rows.filter((_, j) => j !== i))}
              className="shrink-0 rounded-lg p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
              aria-label="Remove"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function CustomConnectorWizardPage() {
  const navigate = useNavigate();
  const { slug: editingSlug } = useParams();
  const isEditing = Boolean(editingSlug);

  const [step, setStep] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(isEditing);

  const [name, setName] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [baseUrl, setBaseUrl] = useState("");
  const [httpMethod, setHttpMethod] = useState<"GET" | "POST">("GET");
  const [authType, setAuthType] = useState<AuthType>("none");
  const [authKeyName, setAuthKeyName] = useState("");
  const [authKeyValue, setAuthKeyValue] = useState("");
  const [hasStoredAuthKey, setHasStoredAuthKey] = useState(false);
  const [keywordParam, setKeywordParam] = useState("");
  const [yearFromParam, setYearFromParam] = useState("");
  const [yearToParam, setYearToParam] = useState("");
  const [staticParams, setStaticParams] = useState<KeyValueRow[]>([]);
  const [headers, setHeaders] = useState<KeyValueRow[]>([]);
  const [rateLimitRps, setRateLimitRps] = useState("1");
  const [connectTimeoutS, setConnectTimeoutS] = useState("10");
  const [readTimeoutS, setReadTimeoutS] = useState("30");

  const [paginationStyle, setPaginationStyle] = useState<PaginationStyle>("none");
  const [pageSize, setPageSize] = useState("20");
  const [pageSizeParam, setPageSizeParam] = useState("");
  const [pageParam, setPageParam] = useState("");
  const [startPage, setStartPage] = useState("1");
  const [offsetParam, setOffsetParam] = useState("");
  const [startOffset, setStartOffset] = useState("0");
  const [cursorParam, setCursorParam] = useState("");
  const [nextCursorPath, setNextCursorPath] = useState("");
  const [resultsPath, setResultsPath] = useState("");
  const [totalPath, setTotalPath] = useState("");
  const [stopWhenEmpty, setStopWhenEmpty] = useState(true);

  const [fieldPaths, setFieldPaths] = useState<Record<TargetField, string>>({
    title: "",
    authors: "",
    year: "",
    abstract: "",
    doi: "",
    citation_count: "",
    url: "",
    venue: "",
  });

  const [pasteJson, setPasteJson] = useState("");
  const [pasteError, setPasteError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<Partial<Record<TargetField, string>>>({});

  const [testKeyword, setTestKeyword] = useState("test");
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<CustomConnectorTestResponse | null>(null);

  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  function applyConfig(config: CustomConnectorConfig) {
    setBaseUrl(config.base_url);
    setHttpMethod(config.http_method);
    setAuthType(config.auth.type);
    setAuthKeyName(config.auth.key_name ?? "");
    setAuthKeyValue(config.auth.key_value ?? "");
    setKeywordParam(config.query_mapping.keyword_param);
    setYearFromParam(config.query_mapping.year_from_param ?? "");
    setYearToParam(config.query_mapping.year_to_param ?? "");
    setStaticParams(recordToRows(config.query_mapping.static_params));
    setHeaders(recordToRows(config.headers));
    setRateLimitRps(String(config.rate_limit_rps));
    setConnectTimeoutS(String(config.connect_timeout_s));
    setReadTimeoutS(String(config.read_timeout_s));
    setPaginationStyle(config.pagination.style);
    setPageSize(String(config.pagination.page_size));
    setPageSizeParam(config.pagination.page_size_param ?? "");
    setPageParam(config.pagination.page_param ?? "");
    setStartPage(String(config.pagination.start_page));
    setOffsetParam(config.pagination.offset_param ?? "");
    setStartOffset(String(config.pagination.start_offset));
    setCursorParam(config.pagination.cursor_param ?? "");
    setNextCursorPath(config.pagination.next_cursor_path ?? "");
    setResultsPath(config.pagination.results_path);
    setTotalPath(config.pagination.total_path ?? "");
    setStopWhenEmpty(config.pagination.stop_when_empty);
    setFieldPaths({
      title: config.field_mapping.title.path ?? "",
      authors: config.field_mapping.authors.path ?? "",
      year: config.field_mapping.year.path ?? "",
      abstract: config.field_mapping.abstract.path ?? "",
      doi: config.field_mapping.doi.path ?? "",
      citation_count: config.field_mapping.citation_count.path ?? "",
      url: config.field_mapping.url.path ?? "",
      venue: config.field_mapping.venue.path ?? "",
    });
  }

  useEffect(() => {
    if (!editingSlug) return;
    getCustomConnector(editingSlug)
      .then((row) => {
        setName(row.name);
        setEnabled(row.enabled);
        setHasStoredAuthKey(row.auth_key_configured);
        applyConfig(row.config);
      })
      .catch((err) => setLoadError(err instanceof Error ? err.message : "Could not load this custom source."))
      .finally(() => setIsLoading(false));
  }, [editingSlug]);

  function buildConfig(): CustomConnectorConfig {
    const base = emptyCustomConnectorConfig();
    return {
      ...base,
      base_url: baseUrl.trim(),
      http_method: httpMethod,
      auth: {
        type: authType,
        key_name: authType === "none" ? null : authKeyName.trim() || null,
        key_value: authType === "none" ? null : authKeyValue,
      },
      query_mapping: {
        keyword_param: keywordParam.trim(),
        year_from_param: yearFromParam.trim() || null,
        year_to_param: yearToParam.trim() || null,
        static_params: rowsToRecord(staticParams),
      },
      pagination: {
        style: paginationStyle,
        page_size: Number(pageSize) || 20,
        page_size_param: pageSizeParam.trim() || null,
        page_param: pageParam.trim() || null,
        start_page: Number(startPage) || 1,
        offset_param: offsetParam.trim() || null,
        start_offset: Number(startOffset) || 0,
        cursor_param: cursorParam.trim() || null,
        next_cursor_path: nextCursorPath.trim() || null,
        results_path: resultsPath.trim(),
        total_path: totalPath.trim() || null,
        stop_when_empty: stopWhenEmpty,
      },
      field_mapping: FIELD_META.reduce((acc, { field }) => {
        acc[field] = { path: fieldPaths[field].trim() || null };
        return acc;
      }, {} as CustomConnectorConfig["field_mapping"]),
      headers: rowsToRecord(headers),
      rate_limit_rps: Number(rateLimitRps) || 1,
      connect_timeout_s: Number(connectTimeoutS) || 10,
      read_timeout_s: Number(readTimeoutS) || 30,
    };
  }

  const step1Errors = useMemo(() => {
    const errors: string[] = [];
    if (!name.trim()) errors.push("Give this source a name.");
    if (!/^https?:\/\/.+/i.test(baseUrl.trim())) errors.push("Base URL must start with http:// or https://.");
    if (!keywordParam.trim()) errors.push("Name the query parameter that carries the search keyword.");
    if (authType !== "none" && !authKeyName.trim()) errors.push("Name the header or query parameter that carries the API key.");
    return errors;
  }, [name, baseUrl, keywordParam, authType, authKeyName]);

  const step2Errors = useMemo(() => {
    const errors: string[] = [];
    if (!resultsPath.trim()) errors.push("Say where the list of results lives in the response body.");
    if (paginationStyle === "page" && !pageParam.trim()) errors.push("Name the page-number query parameter.");
    if (paginationStyle === "offset" && !offsetParam.trim()) errors.push("Name the offset query parameter.");
    if (paginationStyle === "cursor" && (!cursorParam.trim() || !nextCursorPath.trim())) {
      errors.push("Cursor pagination needs both the cursor query parameter and where the next cursor appears in the response.");
    }
    return errors;
  }, [resultsPath, paginationStyle, pageParam, offsetParam, cursorParam, nextCursorPath]);

  const step3Errors = useMemo(() => {
    const errors: string[] = [];
    if (!fieldPaths.title.trim()) errors.push("Map at least the Title field.");
    return errors;
  }, [fieldPaths]);

  const allErrors = [...step1Errors, ...step2Errors, ...step3Errors];

  function handleSuggestFromSample() {
    setPasteError(null);
    let parsed: unknown;
    try {
      parsed = JSON.parse(pasteJson);
    } catch {
      setPasteError("That doesn't look like valid JSON - check for a trailing comma or unclosed bracket.");
      return;
    }
    const guessedResultsPath = suggestResultsPath(parsed);
    if (guessedResultsPath && !resultsPath.trim()) {
      setResultsPath(guessedResultsPath);
    }
    const fieldSuggestions = suggestFieldMappings(parsed, guessedResultsPath ?? (resultsPath || null));
    setSuggestions(fieldSuggestions);
    setFieldPaths((prev) => {
      const next = { ...prev };
      for (const meta of FIELD_META) {
        if (!next[meta.field].trim() && fieldSuggestions[meta.field]) {
          next[meta.field] = fieldSuggestions[meta.field]!;
        }
      }
      return next;
    });
  }

  async function handleTestConnection() {
    setIsTesting(true);
    setTestResult(null);
    try {
      const result = await testCustomConnector(buildConfig(), testKeyword.trim() || "test", 3);
      setTestResult(result);
    } catch (err) {
      setTestResult({
        success: false,
        status_code: null,
        request_url: null,
        raw_response: null,
        sample_records: [],
        mapped_articles: [],
        error: err instanceof Error ? err.message : "The test-connection request failed.",
      });
    } finally {
      setIsTesting(false);
    }
  }

  async function handleSave() {
    if (allErrors.length > 0) return;
    setIsSaving(true);
    setSaveError(null);
    try {
      const config = buildConfig();
      if (isEditing && editingSlug) {
        await updateCustomConnector(editingSlug, name.trim(), config, enabled);
      } else {
        await createCustomConnector(name.trim(), config, enabled);
      }
      navigate("/sources");
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Could not save this custom source.");
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-50">
        <TopNav />
        <main className="mx-auto max-w-3xl px-8 py-16">
          <div className="flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white py-16 text-slate-400 shadow-sm">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading custom source...
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <TopNav />
      <main className="mx-auto max-w-4xl px-8 py-10">
        <h1 className="text-3xl font-bold text-slate-900">
          {isEditing ? "Edit Custom Connector" : "Add a Custom Connector"}
        </h1>
        <div className="mt-2 h-0.5 w-16 bg-emerald-500" />
        <p className="mt-4 max-w-2xl text-slate-500">
          Configure a scientific source outside our built-in list (e.g. IEEE Xplore, HAL, DOAJ,
          CORE, Europe PMC, or an institutional repository) purely through settings - no code
          required.
        </p>

        {loadError && (
          <div className="mt-6 rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
            {loadError}
          </div>
        )}

        {/* Step indicator */}
        <div className="mt-8 flex items-center gap-2">
          {STEPS.map((label, i) => (
            <div key={label} className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setStep(i)}
                className={`flex items-center gap-1.5 rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                  step === i
                    ? "border border-emerald-200 bg-emerald-50 text-emerald-700"
                    : "text-slate-400 hover:text-slate-600"
                }`}
              >
                <span
                  className={`flex h-5 w-5 items-center justify-center rounded-full text-xs ${
                    step === i ? "bg-emerald-600 text-white" : "bg-slate-200 text-slate-500"
                  }`}
                >
                  {i + 1}
                </span>
                {label}
              </button>
              {i < STEPS.length - 1 && <div className="h-px w-6 bg-slate-200" />}
            </div>
          ))}
        </div>

        <div className="mt-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          {step === 0 && (
            <div className="flex flex-col gap-5">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">Source name</label>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. IEEE Xplore"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">Base URL</label>
                <input
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder="https://api.example.org/search"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2.5 font-mono text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-slate-700">HTTP method</label>
                  <select
                    value={httpMethod}
                    onChange={(e) => setHttpMethod(e.target.value as "GET" | "POST")}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  >
                    <option value="GET">GET</option>
                    <option value="POST">POST</option>
                  </select>
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-slate-700">
                    Keyword query parameter
                  </label>
                  <input
                    value={keywordParam}
                    onChange={(e) => setKeywordParam(e.target.value)}
                    placeholder="e.g. q, query, querytext"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
              </div>

              <div className="border-t border-slate-100 pt-5">
                <label className="mb-1.5 block text-sm font-medium text-slate-700">Authentication</label>
                <select
                  value={authType}
                  onChange={(e) => setAuthType(e.target.value as AuthType)}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                >
                  {(Object.keys(AUTH_LABELS) as AuthType[]).map((type) => (
                    <option key={type} value={type}>
                      {AUTH_LABELS[type]}
                    </option>
                  ))}
                </select>

                {authType !== "none" && (
                  <div className="mt-3 grid grid-cols-2 gap-4">
                    <div>
                      <label className="mb-1.5 block text-sm text-slate-600">
                        {authType === "api_key_header" ? "Header name" : "Query parameter name"}
                      </label>
                      <input
                        value={authKeyName}
                        onChange={(e) => setAuthKeyName(e.target.value)}
                        placeholder={authType === "api_key_header" ? "e.g. Authorization or x-api-key" : "e.g. apikey"}
                        className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                      />
                    </div>
                    <div>
                      <label className="mb-1.5 block text-sm text-slate-600">API key / value</label>
                      <input
                        value={authKeyValue}
                        onChange={(e) => setAuthKeyValue(e.target.value)}
                        type="password"
                        placeholder={
                          hasStoredAuthKey ? "Leave blank to keep the saved key" : "Paste the key or token"
                        }
                        className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                      />
                      {hasStoredAuthKey && (
                        <p className="mt-1 text-xs text-slate-400">
                          An API key is already saved for this source (never shown again for
                          security) - leave this blank to keep it, or enter a new value to
                          replace it. Testing with the saved key requires re-entering it here.
                        </p>
                      )}
                    </div>
                  </div>
                )}
              </div>

              <div className="border-t border-slate-100 pt-5">
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <label className="mb-1.5 block text-sm text-slate-600">From-year parameter</label>
                    <input
                      value={yearFromParam}
                      onChange={(e) => setYearFromParam(e.target.value)}
                      placeholder="optional"
                      className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                    />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-sm text-slate-600">To-year parameter</label>
                    <input
                      value={yearToParam}
                      onChange={(e) => setYearToParam(e.target.value)}
                      placeholder="optional"
                      className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                    />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-sm text-slate-600">Rate limit (req/s)</label>
                    <input
                      value={rateLimitRps}
                      onChange={(e) => setRateLimitRps(e.target.value)}
                      type="number"
                      min="0"
                      step="0.1"
                      className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                    />
                  </div>
                </div>
              </div>

              <div className="border-t border-slate-100 pt-5">
                <KeyValueEditor label="Static query parameters (sent on every request)" rows={staticParams} onChange={setStaticParams} />
              </div>
              <div className="border-t border-slate-100 pt-5">
                <KeyValueEditor label="Extra static headers" rows={headers} onChange={setHeaders} />
              </div>
            </div>
          )}

          {step === 1 && (
            <div className="flex flex-col gap-5">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">Pagination style</label>
                <select
                  value={paginationStyle}
                  onChange={(e) => setPaginationStyle(e.target.value as PaginationStyle)}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                >
                  {(Object.keys(PAGINATION_LABELS) as PaginationStyle[]).map((style) => (
                    <option key={style} value={style}>
                      {PAGINATION_LABELS[style]}
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="mb-1.5 block text-sm text-slate-600">Page size</label>
                  <input
                    value={pageSize}
                    onChange={(e) => setPageSize(e.target.value)}
                    type="number"
                    min="1"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm text-slate-600">Page-size parameter</label>
                  <input
                    value={pageSizeParam}
                    onChange={(e) => setPageSizeParam(e.target.value)}
                    placeholder="e.g. rows, limit, max_records"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
              </div>

              {paginationStyle === "page" && (
                <div className="grid grid-cols-2 gap-4 rounded-lg border border-slate-100 bg-slate-50 p-4">
                  <div>
                    <label className="mb-1.5 block text-sm text-slate-600">Page-number parameter</label>
                    <input
                      value={pageParam}
                      onChange={(e) => setPageParam(e.target.value)}
                      className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                    />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-sm text-slate-600">First page number</label>
                    <input
                      value={startPage}
                      onChange={(e) => setStartPage(e.target.value)}
                      type="number"
                      className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                    />
                  </div>
                </div>
              )}

              {paginationStyle === "offset" && (
                <div className="grid grid-cols-2 gap-4 rounded-lg border border-slate-100 bg-slate-50 p-4">
                  <div>
                    <label className="mb-1.5 block text-sm text-slate-600">Offset parameter</label>
                    <input
                      value={offsetParam}
                      onChange={(e) => setOffsetParam(e.target.value)}
                      className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                    />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-sm text-slate-600">Starting offset</label>
                    <input
                      value={startOffset}
                      onChange={(e) => setStartOffset(e.target.value)}
                      type="number"
                      className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                    />
                  </div>
                </div>
              )}

              {paginationStyle === "cursor" && (
                <div className="grid grid-cols-2 gap-4 rounded-lg border border-slate-100 bg-slate-50 p-4">
                  <div>
                    <label className="mb-1.5 block text-sm text-slate-600">Cursor parameter</label>
                    <input
                      value={cursorParam}
                      onChange={(e) => setCursorParam(e.target.value)}
                      className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                    />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-sm text-slate-600">
                      Where the next cursor appears in the response
                    </label>
                    <input
                      value={nextCursorPath}
                      onChange={(e) => setNextCursorPath(e.target.value)}
                      placeholder="e.g. nextCursorMark"
                      className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                    />
                  </div>
                </div>
              )}

              <div className="border-t border-slate-100 pt-5">
                <label className="mb-1.5 block text-sm font-medium text-slate-700">
                  Where the list of results lives in the response
                </label>
                <input
                  value={resultsPath}
                  onChange={(e) => setResultsPath(e.target.value)}
                  placeholder="e.g. results, response.docs, resultList.result"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2.5 font-mono text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
                <p className="mt-1 text-xs text-slate-400">
                  You'll pin this down precisely in step 3 using a pasted sample response.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="mb-1.5 block text-sm text-slate-600">Total-count field (optional)</label>
                  <input
                    value={totalPath}
                    onChange={(e) => setTotalPath(e.target.value)}
                    placeholder="e.g. totalHits, hitCount"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
                <label className="mt-6 flex items-center gap-2 text-sm text-slate-600">
                  <input
                    type="checkbox"
                    checked={stopWhenEmpty}
                    onChange={(e) => setStopWhenEmpty(e.target.checked)}
                    className="h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                  />
                  Treat a shorter-than-requested page as the last page
                </label>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="flex flex-col gap-6">
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-700">
                  <ClipboardPaste className="h-4 w-4 text-emerald-600" />
                  Paste an example JSON response (optional, speeds this up)
                </div>
                <textarea
                  value={pasteJson}
                  onChange={(e) => setPasteJson(e.target.value)}
                  rows={6}
                  placeholder='{"results": [{"title": "...", "authors": [{"name": "..."}], ...}]}'
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 font-mono text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
                {pasteError && <p className="mt-1.5 text-xs text-rose-600">{pasteError}</p>}
                <button
                  type="button"
                  onClick={handleSuggestFromSample}
                  disabled={!pasteJson.trim()}
                  className="mt-2 flex items-center gap-1.5 rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-900 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Suggest field paths from this sample
                </button>
              </div>

              <div className="flex flex-col gap-3">
                {FIELD_META.map((meta) => (
                  <div key={meta.field} className="grid grid-cols-[160px_1fr] items-center gap-3">
                    <label className="text-sm font-medium text-slate-700">
                      {meta.label}
                      {meta.required && <span className="text-rose-500"> *</span>}
                    </label>
                    <div>
                      <input
                        value={fieldPaths[meta.field]}
                        onChange={(e) =>
                          setFieldPaths((prev) => ({ ...prev, [meta.field]: e.target.value }))
                        }
                        placeholder={meta.hint}
                        className="w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                      />
                      {suggestions[meta.field] &&
                        suggestions[meta.field] !== fieldPaths[meta.field] && (
                          <button
                            type="button"
                            onClick={() =>
                              setFieldPaths((prev) => ({
                                ...prev,
                                [meta.field]: suggestions[meta.field]!,
                              }))
                            }
                            className="mt-1 text-xs text-emerald-700 hover:underline"
                          >
                            Use suggestion: <code>{suggestions[meta.field]}</code>
                          </button>
                        )}
                    </div>
                  </div>
                ))}
              </div>

              <div className="border-t border-slate-200 pt-6">
                <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-700">
                  <Play className="h-4 w-4 text-emerald-600" />
                  Test connection
                </div>
                <div className="flex items-center gap-3">
                  <input
                    value={testKeyword}
                    onChange={(e) => setTestKeyword(e.target.value)}
                    placeholder="Sample keyword to search"
                    className="w-64 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                  <button
                    type="button"
                    onClick={handleTestConnection}
                    disabled={isTesting || step1Errors.length > 0 || step2Errors.length > 0}
                    className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {isTesting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                    {isTesting ? "Testing..." : "Run test query"}
                  </button>
                </div>

                {testResult && (
                  <div className="mt-4">
                    {testResult.success ? (
                      <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
                        <div className="flex items-center gap-2 text-emerald-800">
                          <CheckCircle2 className="h-4 w-4" />
                          <span className="font-medium">
                            Connected - HTTP {testResult.status_code}, {testResult.mapped_articles.length} record(s) mapped
                          </span>
                        </div>
                        {testResult.request_url && (
                          <p className="mt-1 break-all font-mono text-xs text-emerald-700">
                            {testResult.request_url}
                          </p>
                        )}
                        <div className="mt-3 grid grid-cols-1 gap-2">
                          {testResult.mapped_articles.map((article, i) => (
                            <div key={i} className="rounded-lg border border-emerald-100 bg-white p-3 text-sm">
                              <p className="font-semibold text-slate-900">{article.title || "(no title mapped)"}</p>
                              <p className="mt-0.5 text-xs text-slate-500">
                                {article.authors.join(", ") || "No authors mapped"}
                                {article.year ? ` - ${article.year}` : ""}
                                {article.doi ? ` - DOI ${article.doi}` : ""}
                              </p>
                            </div>
                          ))}
                          {testResult.mapped_articles.length === 0 && (
                            <p className="text-xs text-slate-500">
                              The request succeeded but no records were found at the configured results path.
                            </p>
                          )}
                        </div>
                        <details className="mt-3">
                          <summary className="cursor-pointer text-xs font-medium text-emerald-700">
                            View raw response
                          </summary>
                          <pre className="mt-2 max-h-64 overflow-auto rounded-lg bg-slate-900 p-3 text-xs text-emerald-200">
                            {JSON.stringify(testResult.raw_response, null, 2)}
                          </pre>
                        </details>
                      </div>
                    ) : (
                      <div className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
                        <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
                        <div>
                          <p className="font-medium">Test connection failed</p>
                          <p className="mt-1">{testResult.error}</p>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {allErrors.length > 0 && (
          <div className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-5">
            <div className="flex items-center gap-2">
              <Info className="h-4 w-4 text-amber-600" />
              <h3 className="font-semibold text-amber-800">Before you can save</h3>
            </div>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-amber-700">
              {allErrors.map((err) => (
                <li key={err}>{err}</li>
              ))}
            </ul>
          </div>
        )}

        {saveError && (
          <div className="mt-6 rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
            {saveError}
          </div>
        )}

        <div className="mt-8 flex items-center justify-between border-t border-slate-200 pt-6">
          <button
            onClick={() => (step === 0 ? navigate("/sources") : setStep((s) => s - 1))}
            className="flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-5 py-2.5 font-medium text-slate-700 hover:bg-slate-50"
          >
            <ArrowLeft className="h-4 w-4" />
            {step === 0 ? "Cancel" : "Back"}
          </button>

          {step < STEPS.length - 1 ? (
            <button
              onClick={() => setStep((s) => s + 1)}
              className="flex items-center gap-2 rounded-lg bg-emerald-600 px-6 py-3 font-medium text-white hover:bg-emerald-700"
            >
              Next
              <ArrowRight className="h-4 w-4" />
            </button>
          ) : (
            <button
              onClick={handleSave}
              disabled={allErrors.length > 0 || isSaving}
              className="flex items-center gap-2 rounded-lg bg-emerald-600 px-6 py-3 font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Save className="h-4 w-4" />
              {isSaving ? "Saving..." : isEditing ? "Save Changes" : "Save Custom Connector"}
            </button>
          )}
        </div>
      </main>
    </div>
  );
}
