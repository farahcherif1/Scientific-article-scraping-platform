import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  Calendar,
  CalendarOff,
  Check,
  ChevronLeft,
  ChevronRight,
  FileJson,
  FileSpreadsheet,
  FileText,
  FileWarning,
  Info,
  Link2Off,
  Loader2,
  Orbit,
  RefreshCw,
  RotateCcw,
  Search,
  X,
} from "lucide-react";
import TopNav from "../components/TopNav";
import Select from "../components/Select";
import ArticlesPerYearChart from "../components/ArticlesPerYearChart";
import {
  downloadExport,
  fetchArticles,
  fetchCollectionStats,
  type Article,
  type ArticlesResponse,
  type CollectionStats,
  type ExportFormat,
  type SortField,
} from "../api/articles";

const PAGE_SIZE_OPTIONS = ["25", "50", "100"] as const;
const DEFAULT_PAGE_SIZE = 50;
const KEYWORD_DEBOUNCE_MS = 300;
const MAX_PAGE_BUTTONS = 7;

const SOURCE_LABELS: Record<string, string> = {
  arxiv: "arXiv",
  openalex: "OpenAlex",
  crossref: "Crossref",
  pubmed: "PubMed",
  semantic_scholar: "Semantic Scholar",
};

const SORT_OPTIONS: { value: SortField; label: string }[] = [
  { value: "-relevance", label: "Relevance (high to low)" },
  { value: "relevance", label: "Relevance (low to high)" },
  { value: "-year", label: "Year (newest first)" },
  { value: "year", label: "Year (oldest first)" },
  { value: "-citation_count", label: "Citations (most first)" },
  { value: "citation_count", label: "Citations (least first)" },
];

const EXPORT_FORMATS: { format: ExportFormat; label: string; icon: typeof FileSpreadsheet }[] = [
  { format: "xlsx", label: "XLSX", icon: FileSpreadsheet },
  { format: "csv", label: "CSV", icon: FileText },
  { format: "json", label: "JSON", icon: FileJson },
  { format: "graph", label: "Graph JSON", icon: FileJson },
];

function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source;
}

/** Only http(s) links are ever rendered as clickable - article metadata comes
 * from external sources/connectors, so a javascript: or data: URI must never
 * reach an <a href>. */
function isSafeHttpUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "2-digit",
    year: "numeric",
  });
}

function lastName(fullName: string): string {
  const parts = fullName.trim().split(/\s+/);
  return parts[parts.length - 1] ?? fullName;
}

function authorsSummary(authors: string[]): string {
  if (authors.length === 0) return "";
  return authors.length > 1 ? `${lastName(authors[0])} et al.` : lastName(authors[0]);
}

function titleVenueSubtitle(article: Article): string {
  const parts = [article.venue, authorsSummary(article.authors)].filter(Boolean);
  return parts.join(" • ");
}

/** Windowed page numbers with ellipses, e.g. [1, "…", 4, 5, 6, "…", 20]. */
function buildPageWindow(current: number, total: number): (number | "…")[] {
  if (total <= MAX_PAGE_BUTTONS) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }
  const window: (number | "…")[] = [1];
  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);
  if (start > 2) window.push("…");
  for (let p = start; p <= end; p++) window.push(p);
  if (end < total - 1) window.push("…");
  window.push(total);
  return window;
}

interface FilterCheckboxProps {
  id: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
}

function FilterCheckbox({ id, checked, onChange, label }: FilterCheckboxProps) {
  return (
    <label htmlFor={id} className="flex cursor-pointer items-center gap-2 py-1 text-sm text-slate-700">
      <span className="relative flex h-4 w-4 shrink-0 items-center justify-center">
        <input
          id={id}
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          className="peer absolute inset-0 h-4 w-4 cursor-pointer opacity-0"
        />
        <span className="h-4 w-4 rounded border border-slate-300 bg-white peer-checked:border-emerald-600 peer-checked:bg-emerald-600 peer-focus-visible:ring-2 peer-focus-visible:ring-emerald-500 peer-focus-visible:ring-offset-1" />
        <Check className="pointer-events-none absolute h-3 w-3 text-white opacity-0 peer-checked:opacity-100" />
      </span>
      {label}
    </label>
  );
}

function MissingBadge({ icon: Icon, text }: { icon: typeof Link2Off; text: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700">
      <Icon className="h-3 w-3" aria-hidden="true" />
      {text}
    </span>
  );
}

function StatCard({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</p>
      <p className={`mt-1.5 text-2xl font-bold ${accent ?? "text-slate-900"}`}>{value}</p>
    </div>
  );
}

export default function ResultsPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const page = Number(searchParams.get("page") ?? "1") || 1;
  const pageSize = Number(searchParams.get("page_size") ?? String(DEFAULT_PAGE_SIZE)) || DEFAULT_PAGE_SIZE;
  const sort = (searchParams.get("sort") as SortField) || "-relevance";
  const yearFrom = searchParams.get("year_from") ?? "";
  const yearTo = searchParams.get("year_to") ?? "";
  const selectedSources = searchParams.getAll("source");
  const selectedSourcesKey = selectedSources.join(",");
  const hasDoi = searchParams.get("has_doi") === "true";
  const hasAbstract = searchParams.get("has_abstract") === "true";
  const keywordParam = searchParams.get("keyword") ?? "";

  const [keywordInput, setKeywordInput] = useState(keywordParam);
  // Syncs the local (debounced) input buffer when the URL's keyword param
  // changes from outside typing - e.g. Reset, or browser back/forward.
  // Adjusting state during render (React's documented pattern for "state
  // derived from a prop") rather than in an effect, so it doesn't trip
  // react-hooks/set-state-in-effect.
  const [prevKeywordParam, setPrevKeywordParam] = useState(keywordParam);
  if (keywordParam !== prevKeywordParam) {
    setPrevKeywordParam(keywordParam);
    setKeywordInput(keywordParam);
  }
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [articles, setArticles] = useState<ArticlesResponse | null>(null);
  const [stats, setStats] = useState<CollectionStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [selected, setSelected] = useState<Article | null>(null);
  const [exportingFormat, setExportingFormat] = useState<ExportFormat | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  // Shared with both the results fetch and export downloads, so "active
  // filters are reflected in the exported dataset" (US-06.1/US-06.2) holds
  // by construction - the export request always carries what's on screen.
  const activeFilters = {
    year_from: yearFrom ? Number(yearFrom) : undefined,
    year_to: yearTo ? Number(yearTo) : undefined,
    source: selectedSources.length > 0 ? selectedSources : undefined,
    has_doi: hasDoi || undefined,
    has_abstract: hasAbstract || undefined,
    keyword: keywordParam || undefined,
  };

  const updateParams = useCallback(
    (patch: Record<string, string | string[] | null>, resetPage = true) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        for (const [key, value] of Object.entries(patch)) {
          next.delete(key);
          if (value === null || value === "") continue;
          if (Array.isArray(value)) {
            for (const item of value) next.append(key, item);
          } else {
            next.set(key, value);
          }
        }
        if (resetPage) next.delete("page");
        return next;
      });
    },
    [setSearchParams]
  );

  const load = useCallback(() => {
    let cancelled = false;
    // Both setState calls below run inside a .then/.catch/.finally
    // continuation (a microtask), never synchronously within the effect
    // that calls `load()` - satisfies react-hooks/set-state-in-effect while
    // still surfacing a fresh error/loading state per fetch.
    Promise.all([
      fetchArticles(id, { page, page_size: pageSize, sort, ...activeFilters }),
      fetchCollectionStats(id),
    ])
      .then(([articlesRes, statsRes]) => {
        if (cancelled) return;
        setArticles(articlesRes);
        setStats(statsRes);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Could not load results.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, page, pageSize, sort, yearFrom, yearTo, selectedSourcesKey, hasDoi, hasAbstract, keywordParam]);

  useEffect(() => load(), [load]);

  function handleKeywordChange(value: string) {
    setKeywordInput(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      updateParams({ keyword: value || null });
    }, KEYWORD_DEBOUNCE_MS);
  }

  function toggleSource(source: string, checked: boolean) {
    const next = checked
      ? [...selectedSources, source]
      : selectedSources.filter((s) => s !== source);
    updateParams({ source: next.length > 0 ? next : null });
  }

  function handleReset() {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    setKeywordInput("");
    setSearchParams(new URLSearchParams());
  }

  async function handleExport(format: ExportFormat) {
    setExportingFormat(format);
    setExportError(null);
    try {
      await downloadExport(id, format, { sort, ...activeFilters });
    } catch (err) {
      setExportError(
        err instanceof Error ? err.message : `Could not export as ${format.toUpperCase()}.`
      );
    } finally {
      setExportingFormat(null);
    }
  }

  const filtersActive = Boolean(
    yearFrom || yearTo || selectedSources.length > 0 || hasDoi || hasAbstract || keywordParam
  );
  const total = articles?.pagination.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const availableSources = stats?.per_source.map((s) => s.source) ?? [];
  const rangeStart = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const rangeEnd = Math.min(page * pageSize, total);

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="border-b border-amber-200 bg-amber-50 px-8 py-3">
        <div className="mx-auto flex max-w-7xl items-center gap-2 text-sm text-amber-900">
          <Info className="h-4 w-4 shrink-0 text-amber-600" aria-hidden="true" />
          <p>
            <strong className="font-semibold">Results are not exhaustive</strong> — the corpus is
            limited by source coverage and API quotas.
          </p>
        </div>
      </div>
      <TopNav />
      <div className="h-0.5 bg-emerald-500" />

      <main className="mx-auto max-w-7xl px-8 py-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Scraped Literature Corpus</h1>
            <p className="mt-1 text-sm text-slate-500">
              Results of collection #{id}
              {stats ? ` • ${stats.total} articles found` : ""}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => navigate(`/collections/${id}/graph`)}
              className="flex items-center gap-2 rounded-lg border border-emerald-600 bg-white px-4 py-2.5 text-sm font-medium text-emerald-700 hover:bg-emerald-50"
              title="Open the interactive 3D knowledge graph"
            >
              <Orbit className="h-4 w-4" />
              View 3D Graph
            </button>
            <span className="text-sm text-slate-500">Export:</span>
            {EXPORT_FORMATS.map(({ format, label, icon: Icon }) => {
              const isExporting = exportingFormat === format;
              return (
                <button
                  key={format}
                  type="button"
                  onClick={() => handleExport(format)}
                  disabled={exportingFormat !== null}
                  title={`Export the current filtered results as ${label}`}
                  className="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isExporting ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Icon className="h-4 w-4" />
                  )}
                  {label}
                </button>
              );
            })}
          </div>
        </div>

        {exportError && (
          <div className="mt-4 flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            {exportError}
          </div>
        )}

        {error && !articles ? (
          <div className="mt-8 flex flex-col items-center justify-center gap-3 rounded-xl border border-slate-200 bg-white py-16 text-center shadow-sm">
            <AlertTriangle className="h-8 w-8 text-rose-500" />
            <p className="text-sm text-slate-600">{error}</p>
            <button
              onClick={load}
              className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Retry
            </button>
          </div>
        ) : (
          <>
            {/* KPI cards */}
            <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
              <StatCard label="Total Articles" value={stats ? String(stats.total) : "—"} />
              <StatCard
                label="Deduped"
                value={stats ? String(stats.deduped) : "—"}
                accent="text-emerald-700"
              />
              <StatCard
                label="Duplicates"
                value={stats ? String(stats.duplicates) : "—"}
                accent="text-amber-600"
              />
              <StatCard label="% With DOI" value={stats ? `${stats.pct_with_doi}%` : "—"} />
              <StatCard
                label="% With Abstract"
                value={stats ? `${stats.pct_with_abstract}%` : "—"}
              />
            </div>

            {/* Chart */}
            <div className="mt-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="font-semibold text-slate-900">Articles Published per Year</h2>
              <div className="mt-4">
                <ArticlesPerYearChart data={stats?.articles_per_year ?? []} />
              </div>
            </div>

            <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-4">
              {/* Filter sidebar */}
              <aside className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm lg:col-span-1">
                <div className="flex items-center justify-between">
                  <h2 className="font-semibold text-slate-900">Refine Corpus</h2>
                  {filtersActive && (
                    <button
                      onClick={handleReset}
                      className="flex items-center gap-1 text-xs font-medium text-emerald-700 hover:underline"
                    >
                      <RotateCcw className="h-3 w-3" />
                      Reset
                    </button>
                  )}
                </div>

                <div className="mt-4 flex flex-col gap-4 border-t border-slate-100 pt-4">
                  <div>
                    <label htmlFor="filter-keyword" className="mb-1.5 block text-sm text-slate-600">
                      Keyword Search
                    </label>
                    <div className="relative">
                      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-300" />
                      <input
                        id="filter-keyword"
                        type="text"
                        value={keywordInput}
                        onChange={(e) => handleKeywordChange(e.target.value)}
                        placeholder="Search keyword..."
                        className="w-full rounded-lg border border-slate-200 py-2 pl-9 pr-3 text-sm text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                      />
                    </div>
                  </div>

                  <div>
                    <span className="mb-1.5 flex items-center gap-1.5 text-sm text-slate-600">
                      <Calendar className="h-3.5 w-3.5" />
                      Publication Year
                    </span>
                    <div className="grid grid-cols-2 gap-2">
                      <input
                        type="number"
                        aria-label="Year from"
                        value={yearFrom}
                        onChange={(e) => updateParams({ year_from: e.target.value || null })}
                        placeholder="From"
                        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                      />
                      <input
                        type="number"
                        aria-label="Year to"
                        value={yearTo}
                        onChange={(e) => updateParams({ year_to: e.target.value || null })}
                        placeholder="To"
                        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                      />
                    </div>
                  </div>

                  {availableSources.length > 0 && (
                    <div>
                      <span className="mb-1 block text-sm text-slate-600">Sources</span>
                      <div className="flex flex-col">
                        {availableSources.map((s) => (
                          <FilterCheckbox
                            key={s}
                            id={`source-${s}`}
                            checked={selectedSources.includes(s)}
                            onChange={(checked) => toggleSource(s, checked)}
                            label={sourceLabel(s)}
                          />
                        ))}
                      </div>
                    </div>
                  )}

                  <div>
                    <span className="mb-1 block text-sm text-slate-600">Metadata Filters</span>
                    <div className="flex flex-col">
                      <FilterCheckbox
                        id="filter-has-doi"
                        checked={hasDoi}
                        onChange={(checked) => updateParams({ has_doi: checked ? "true" : null })}
                        label="Has DOI"
                      />
                      <FilterCheckbox
                        id="filter-has-abstract"
                        checked={hasAbstract}
                        onChange={(checked) =>
                          updateParams({ has_abstract: checked ? "true" : null })
                        }
                        label="Has Abstract"
                      />
                    </div>
                  </div>
                </div>

                {stats && stats.per_source.length > 0 && (
                  <div className="mt-6 border-t border-slate-100 pt-4">
                    <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                      Quality Summary
                    </span>
                    <div className="mt-2 flex flex-col gap-1.5">
                      {stats.per_source.map((s) => (
                        <p key={s.source} className="text-xs text-slate-500">
                          {sourceLabel(s.source)}: DOI {s.pct_with_doi}% · Abstract{" "}
                          {s.pct_with_abstract}%
                        </p>
                      ))}
                    </div>
                  </div>
                )}
              </aside>

              {/* Article table */}
              <div className="min-w-0 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm lg:col-span-3">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-6 py-3">
                  <span className="text-sm text-slate-500">
                    {isLoading ? "Loading…" : `${total} article${total === 1 ? "" : "s"}`}
                  </span>
                  <div className="flex items-center gap-2">
                    <label htmlFor="sort-select" className="text-sm text-slate-500">
                      Sort by
                    </label>
                    <Select
                      id="sort-select"
                      value={sort}
                      onChange={(next) => updateParams({ sort: next }, false)}
                      options={SORT_OPTIONS}
                      className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-left text-sm text-slate-700 hover:border-slate-300 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                    />
                  </div>
                </div>

                {isLoading ? (
                  <div className="flex items-center justify-center gap-2 py-16 text-slate-400">
                    <RefreshCw className="h-4 w-4 animate-spin" />
                    Loading results...
                  </div>
                ) : (articles?.data.length ?? 0) === 0 ? (
                  <div className="flex flex-col items-center justify-center gap-2 py-16 text-center text-slate-400">
                    <Search className="h-8 w-8" />
                    <p className="text-sm">No articles match these filters.</p>
                  </div>
                ) : (
                  <>
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-sm">
                        <thead>
                          <tr className="bg-emerald-800 text-xs font-semibold uppercase tracking-wide text-white">
                            <th className="px-6 py-4">Title &amp; Venue</th>
                            <th className="px-6 py-4">Year</th>
                            <th className="px-6 py-4">Source</th>
                            <th className="px-6 py-4">DOI</th>
                            <th className="px-6 py-4">Citations</th>
                            <th className="px-6 py-4">Warnings</th>
                          </tr>
                        </thead>
                        <tbody>
                          {articles?.data.map((article, i) => (
                            <tr
                              key={article.id}
                              onClick={() => setSelected(article)}
                              className={`cursor-pointer border-t border-slate-100 hover:bg-emerald-50/40 ${
                                i % 2 === 1 ? "bg-slate-50/60" : "bg-white"
                              }`}
                            >
                              <td className="max-w-sm px-6 py-4">
                                <span
                                  className="block truncate font-medium text-slate-900"
                                  title={article.title}
                                >
                                  {article.title}
                                </span>
                                {titleVenueSubtitle(article) && (
                                  <span className="text-xs text-slate-400">
                                    {titleVenueSubtitle(article)}
                                  </span>
                                )}
                              </td>
                              <td className="px-6 py-4 text-slate-600">{article.year ?? "—"}</td>
                              <td className="px-6 py-4">
                                <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600">
                                  {sourceLabel(article.source)}
                                </span>
                              </td>
                              <td className="max-w-[10rem] px-6 py-4">
                                {article.doi ? (
                                  <span
                                    className="block truncate font-mono text-xs text-emerald-700"
                                    title={article.doi}
                                  >
                                    {article.doi}
                                  </span>
                                ) : (
                                  <span className="text-slate-400">—</span>
                                )}
                              </td>
                              <td className="px-6 py-4 text-slate-600">
                                {article.citation_count ?? "—"}
                              </td>
                              <td className="px-6 py-4">
                                <div className="flex flex-wrap gap-1.5">
                                  {article.missing_fields.includes("doi") && (
                                    <MissingBadge icon={Link2Off} text="Missing DOI" />
                                  )}
                                  {article.missing_fields.includes("abstract") && (
                                    <MissingBadge icon={FileWarning} text="Missing Abstract" />
                                  )}
                                  {article.missing_fields.includes("year") && (
                                    <MissingBadge icon={CalendarOff} text="Missing Year" />
                                  )}
                                </div>
                                {(article.keywords_auto?.length ?? 0) > 0 && (
                                  <div className="mt-2 flex flex-wrap gap-1.5">
                                    {article.keywords_auto.slice(0, 3).map((keyword) => (
                                      <span
                                        key={keyword}
                                        className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-800"
                                      >
                                        {keyword}
                                      </span>
                                    ))}
                                    {(article.keywords_auto.length ?? 0) > 3 && (
                                      <span className="text-[11px] text-slate-400">
                                        +{article.keywords_auto.length - 3} more
                                      </span>
                                    )}
                                  </div>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-6 py-4">
                      <div className="flex items-center gap-2">
                        <label htmlFor="page-size-select" className="text-sm text-slate-500">
                          Rows per page:
                        </label>
                        <Select
                          id="page-size-select"
                          value={String(pageSize)}
                          onChange={(next) => updateParams({ page_size: next }, false)}
                          options={PAGE_SIZE_OPTIONS.map((n) => ({ value: n, label: n }))}
                          className="flex w-20 items-center justify-between gap-2 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-left text-sm text-slate-700 hover:border-slate-300 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                        />
                      </div>

                      <span className="text-sm text-slate-500">
                        Showing {rangeStart}-{rangeEnd} of {total} deduplicated articles
                      </span>

                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => updateParams({ page: String(page - 1) }, false)}
                          disabled={page <= 1}
                          aria-label="Previous page"
                          className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-300 text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <ChevronLeft className="h-4 w-4" />
                        </button>
                        {buildPageWindow(page, totalPages).map((p, idx) =>
                          p === "…" ? (
                            <span key={`ellipsis-${idx}`} className="px-1.5 text-sm text-slate-400">
                              …
                            </span>
                          ) : (
                            <button
                              key={p}
                              onClick={() => updateParams({ page: String(p) }, false)}
                              aria-current={p === page ? "page" : undefined}
                              className={`flex h-8 w-8 items-center justify-center rounded-lg border text-sm font-medium ${
                                p === page
                                  ? "border-emerald-600 bg-emerald-600 text-white"
                                  : "border-slate-300 text-slate-600 hover:bg-slate-50"
                              }`}
                            >
                              {p}
                            </button>
                          )
                        )}
                        <button
                          onClick={() => updateParams({ page: String(page + 1) }, false)}
                          disabled={page >= totalPages}
                          aria-label="Next page"
                          className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-300 text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <ChevronRight className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>
          </>
        )}

        <div className="mt-8">
          <button
            onClick={() => navigate("/history")}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Back to History
          </button>
        </div>
      </main>

      {selected && (
        <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/40" onClick={() => setSelected(null)}>
          <div
            className="h-full w-full max-w-md overflow-y-auto bg-white p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4">
              <h2 className="text-lg font-bold text-slate-900">{selected.title}</h2>
              <button
                onClick={() => setSelected(null)}
                className="shrink-0 rounded-full p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                aria-label="Close"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="mt-4 flex flex-wrap gap-1.5">
              {selected.missing_fields.includes("doi") && (
                <MissingBadge icon={Link2Off} text="Missing DOI" />
              )}
              {selected.missing_fields.includes("abstract") && (
                <MissingBadge icon={FileWarning} text="Missing Abstract" />
              )}
              {selected.missing_fields.includes("year") && (
                <MissingBadge icon={CalendarOff} text="Missing Year" />
              )}
            </div>

            <dl className="mt-6 flex flex-col gap-4 text-sm">
              <div>
                <dt className="font-medium text-slate-500">Authors</dt>
                <dd className="mt-1 text-slate-800">
                  {selected.authors.length > 0 ? selected.authors.join(", ") : "—"}
                </dd>
              </div>
              <div>
                <dt className="font-medium text-slate-500">Abstract</dt>
                <dd className="mt-1 text-slate-800">{selected.abstract ?? "—"}</dd>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <dt className="font-medium text-slate-500">Year</dt>
                  <dd className="mt-1 text-slate-800">{selected.year ?? "—"}</dd>
                </div>
                <div>
                  <dt className="font-medium text-slate-500">Citations</dt>
                  <dd className="mt-1 text-slate-800">{selected.citation_count ?? "—"}</dd>
                </div>
              </div>
              <div>
                <dt className="font-medium text-slate-500">DOI</dt>
                <dd className="mt-1 break-all font-mono text-xs text-slate-800">
                  {selected.doi ?? "—"}
                </dd>
              </div>
              <div>
                <dt className="font-medium text-slate-500">Venue</dt>
                <dd className="mt-1 text-slate-800">{selected.venue ?? "—"}</dd>
              </div>
              <div>
                <dt className="font-medium text-slate-500">Categories</dt>
                <dd className="mt-1 text-slate-800">
                  {selected.categories.length > 0 ? selected.categories.join(", ") : "—"}
                </dd>
              </div>
              <div>
                <dt className="font-medium text-slate-500">Keywords</dt>
                <dd className="mt-2 flex flex-wrap gap-2">
                  {(selected.keywords_auto?.length ?? 0) > 0 ? (
                    selected.keywords_auto.map((keyword) => (
                      <span
                        key={keyword}
                        className="rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-medium text-emerald-800"
                      >
                        {keyword}
                      </span>
                    ))
                  ) : (
                    <span className="text-slate-500">No generated keywords yet</span>
                  )}
                </dd>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <dt className="font-medium text-slate-500">Source</dt>
                  <dd className="mt-1 text-slate-800">{sourceLabel(selected.source)}</dd>
                </div>
                <div>
                  <dt className="font-medium text-slate-500">Found via keyword</dt>
                  <dd className="mt-1 text-slate-800">{selected.search_keyword}</dd>
                </div>
              </div>
              <div>
                <dt className="font-medium text-slate-500">Collected</dt>
                <dd className="mt-1 text-slate-800">{formatDate(selected.collection_date)}</dd>
              </div>
              {selected.duplicate_group_id && (
                <div>
                  <dt className="font-medium text-slate-500">Duplicate group</dt>
                  <dd className="mt-1 text-slate-800">{selected.duplicate_group_id}</dd>
                </div>
              )}
              {selected.url && (
                <div>
                  <dt className="font-medium text-slate-500">Link</dt>
                  <dd className="mt-1 break-all">
                    {isSafeHttpUrl(selected.url) ? (
                      <a
                        href={selected.url}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="text-emerald-700 hover:underline"
                      >
                        {selected.url}
                      </a>
                    ) : (
                      <span className="text-slate-600">{selected.url}</span>
                    )}
                  </dd>
                </div>
              )}
            </dl>
          </div>
        </div>
      )}
    </div>
  );
}
