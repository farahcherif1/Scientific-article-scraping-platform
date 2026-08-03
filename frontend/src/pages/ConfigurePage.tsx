import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  Globe,
  AlignLeft,
  Calendar,
  Shield,
  CheckCircle2,
  AlertTriangle,
  Check,
  ArrowLeft,
  Play,
  Languages,
  Tag,
  Pencil,
  Activity,
  XCircle,
  Loader2,
} from "lucide-react";
import TopNav from "../components/TopNav";
import Toggle from "../components/Toggle";
import Select from "../components/Select";
import { startCollection } from "../api/collections";
import { checkCustomConnectorHealth, listCustomConnectors } from "../api/customConnectors";

interface SourceMeta {
  id: string;
  name: string;
  description: string;
  defaultChecked: boolean;
  custom?: boolean;
}

const BUILTIN_SOURCES: SourceMeta[] = [
  {
    id: "arxiv",
    name: "arXiv",
    description: "Physics, Mathematics, Computer Science preprints",
    defaultChecked: true,
  },
  {
    id: "openalex",
    name: "OpenAlex",
    description: "Global open index of scientific papers and metadata",
    defaultChecked: true,
  },
  {
    id: "crossref",
    name: "Crossref",
    description: "Metadata registry with persistent DOIs for publications",
    defaultChecked: true,
  },
  {
    id: "pubmed",
    name: "PubMed",
    description: "Biomedical and life sciences literature (NCBI)",
    defaultChecked: false,
  },
  {
    id: "semantic_scholar",
    name: "Semantic Scholar",
    description: "AI-powered index across all fields of research",
    defaultChecked: false,
  },
];

const LANGUAGE_OPTIONS = ["Any", "English", "French", "German", "Spanish", "Other"];

function clamp(n: number): number {
  if (Number.isNaN(n)) return 10;
  return Math.min(100, Math.max(10, n));
}

type HealthState = "unknown" | "checking" | "healthy" | "unhealthy";

export default function ConfigurePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const keywords: string[] = (location.state as { keywords?: string[] } | null)?.keywords ?? [];

  const [customSources, setCustomSources] = useState<SourceMeta[]>([]);
  const [customHealth, setCustomHealth] = useState<Record<string, HealthState>>({});
  const sources = useMemo(() => [...BUILTIN_SOURCES, ...customSources], [customSources]);

  const [selectedSources, setSelectedSources] = useState<Record<string, boolean>>(
    Object.fromEntries(BUILTIN_SOURCES.map((s) => [s.id, s.defaultChecked]))
  );

  useEffect(() => {
    listCustomConnectors()
      .then((response) => {
        const enabled = response.data.filter((c) => c.enabled);
        const asSources: SourceMeta[] = enabled.map((c) => ({
          id: c.id,
          name: c.name,
          description: c.config.base_url,
          // Opt-in default, same reasoning as PubMed/Semantic Scholar: a
          // newly added source shouldn't silently change what an existing
          // collection setup fetches.
          defaultChecked: false,
          custom: true,
        }));
        setCustomSources(asSources);
        setSelectedSources((prev) => ({
          ...Object.fromEntries(asSources.map((s) => [s.id, false])),
          ...prev,
        }));
      })
      .catch(() => {
        // Custom sources are additive - if they fail to load, the built-in
        // checklist still works, so this is silent rather than blocking.
      });
  }, []);

  async function handleCheckHealth(id: string) {
    setCustomHealth((prev) => ({ ...prev, [id]: "checking" }));
    try {
      const result = await checkCustomConnectorHealth(id);
      setCustomHealth((prev) => ({ ...prev, [id]: result.healthy ? "healthy" : "unhealthy" }));
    } catch {
      setCustomHealth((prev) => ({ ...prev, [id]: "unhealthy" }));
    }
  }

  const [maxArticles, setMaxArticles] = useState(50);
  const [yearFrom, setYearFrom] = useState("2018");
  const [yearTo, setYearTo] = useState("2024");
  const [language, setLanguage] = useState("Any");
  const [domain, setDomain] = useState("");
  const [includeMissingAbstract, setIncludeMissingAbstract] = useState(true);
  const [excludeDuplicates, setExcludeDuplicates] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [serverMessage, setServerMessage] = useState<{ kind: "success" | "error"; text: string } | null>(
    null
  );

  const activeSourceIds = useMemo(
    () => Object.entries(selectedSources).filter(([, v]) => v).map(([id]) => id),
    [selectedSources]
  );

  const errors = useMemo(() => {
    const list: string[] = [];
    if (activeSourceIds.length === 0) {
      list.push("Select at least one source to continue.");
    }
    const from = Number(yearFrom);
    const to = Number(yearTo);
    if (yearFrom && yearTo && !Number.isNaN(from) && !Number.isNaN(to) && from > to) {
      list.push("'From' year must not be after 'To' year.");
    }
    if (maxArticles < 10 || maxArticles > 100) {
      list.push("Max articles per keyword must be between 10 and 100.");
    }
    return list;
  }, [activeSourceIds, yearFrom, yearTo, maxArticles]);

  const maxPotentialYield = maxArticles * Math.max(keywords.length, 0) * activeSourceIds.length;
  const estimatedRuntime = 15 * activeSourceIds.length;

  async function handleStart() {
    if (errors.length > 0) return;
    setIsSubmitting(true);
    setServerMessage(null);
    try {
      const { id } = await startCollection({
        keywords,
        sources: activeSourceIds,
        max_articles_per_keyword: maxArticles,
        year_from: yearFrom ? Number(yearFrom) : undefined,
        year_to: yearTo ? Number(yearTo) : undefined,
        language: language !== "Any" ? language : undefined,
        domain: domain.trim() || undefined,
        include_missing_abstract: includeMissingAbstract,
        exclude_duplicates_on_export: excludeDuplicates,
      });
      navigate(`/collections/${id}/progress`);
    } catch (err) {
      setServerMessage({
        kind: "error",
        text: err instanceof Error ? err.message : "The backend rejected this configuration.",
      });
      setIsSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <TopNav />

      <main className="mx-auto max-w-7xl px-8 py-10">
        <h1 className="text-3xl font-bold text-slate-900">Configure Collection Parameters</h1>
        <div className="mt-2 h-0.5 w-16 bg-emerald-500" />
        <p className="mt-4 max-w-2xl text-slate-500">
          Select target databases, limit the article yield per keyword, and define publication
          date boundaries before launching the extraction process.
        </p>

        <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* Left column */}
          <div className="flex flex-col gap-6">
            {/* Sources */}
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Globe className="h-4 w-4 text-emerald-600" />
                  <h2 className="font-semibold text-slate-900">Target Scientific Sources</h2>
                </div>
                <span className="text-xs text-slate-400">Select at least one</span>
              </div>

              <div className="mt-4 flex flex-col gap-3 border-t border-slate-100 pt-4">
                {sources.map((source) => {
                  const checked = selectedSources[source.id];
                  const healthState = customHealth[source.id] ?? "unknown";
                  return (
                    <div
                      key={source.id}
                      onClick={() =>
                        setSelectedSources((prev) => ({ ...prev, [source.id]: !prev[source.id] }))
                      }
                      className="flex cursor-pointer items-start gap-3 rounded-lg border border-slate-200 p-4 hover:border-emerald-200"
                    >
                      <span
                        className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded ${
                          checked ? "bg-emerald-600" : "border border-slate-300 bg-white"
                        }`}
                      >
                        {checked && <Check className="h-3.5 w-3.5 text-white" />}
                      </span>
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-slate-900">{source.name}</span>
                          {source.custom && (
                            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
                              Custom
                            </span>
                          )}
                        </div>
                        <p className="mt-0.5 truncate text-sm text-slate-500">{source.description}</p>
                      </div>
                      {source.custom && (
                        <div
                          className="flex shrink-0 items-center gap-1"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <button
                            type="button"
                            title="Check connection health"
                            onClick={() => handleCheckHealth(source.id)}
                            className="flex h-7 w-7 items-center justify-center rounded-full border border-slate-200 hover:bg-slate-50"
                          >
                            {healthState === "checking" ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin text-slate-400" />
                            ) : healthState === "healthy" ? (
                              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                            ) : healthState === "unhealthy" ? (
                              <XCircle className="h-3.5 w-3.5 text-rose-500" />
                            ) : (
                              <Activity className="h-3.5 w-3.5 text-slate-300" />
                            )}
                          </button>
                          <button
                            type="button"
                            title="Edit this custom source"
                            onClick={() => navigate(`/sources/custom/${source.id}/edit`)}
                            className="flex h-7 w-7 items-center justify-center rounded-full border border-slate-200 hover:bg-slate-50"
                          >
                            <Pencil className="h-3.5 w-3.5 text-slate-500" />
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
              <button
                type="button"
                onClick={() => navigate("/sources/custom/new")}
                className="mt-3 text-sm font-medium text-emerald-700 hover:underline"
              >
                + Add a custom source
              </button>
            </div>

            {/* Date range */}
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Calendar className="h-4 w-4 text-emerald-600" />
                  <h2 className="font-semibold text-slate-900">Publication Date Range</h2>
                </div>
                <span className="text-xs text-slate-400">Optional filter</span>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-4 border-t border-slate-100 pt-4">
                <div>
                  <label className="mb-1.5 block text-sm text-slate-600">From (Year)</label>
                  <input
                    type="number"
                    value={yearFrom}
                    onChange={(e) => setYearFrom(e.target.value)}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm text-slate-600">To (Year)</label>
                  <input
                    type="number"
                    value={yearTo}
                    onChange={(e) => setYearTo(e.target.value)}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
              </div>
            </div>

            {/* Additional filters */}
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Tag className="h-4 w-4 text-emerald-600" />
                  <h2 className="font-semibold text-slate-900">Additional Filters</h2>
                </div>
                <span className="text-xs text-slate-400">Applied where the source supports it</span>
              </div>

              <div className="mt-4 grid grid-cols-2 gap-4 border-t border-slate-100 pt-4">
                <div>
                  <label className="mb-1.5 flex items-center gap-1.5 text-sm text-slate-600">
                    <Languages className="h-3.5 w-3.5" />
                    Language (if available)
                  </label>
                  <Select
                    value={language}
                    onChange={setLanguage}
                    options={LANGUAGE_OPTIONS.map((opt) => ({ value: opt, label: opt }))}
                    aria-label="Language"
                  />
                </div>
                <div>
                  <label className="mb-1.5 flex items-center gap-1.5 text-sm text-slate-600">
                    <Tag className="h-3.5 w-3.5" />
                    Domain (if available)
                  </label>
                  <input
                    type="text"
                    value={domain}
                    onChange={(e) => setDomain(e.target.value)}
                    placeholder="e.g. Computer Science"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
              </div>

              <div className="mt-2 divide-y divide-slate-100 border-t border-slate-100">
                <Toggle
                  checked={includeMissingAbstract}
                  onChange={setIncludeMissingAbstract}
                  label="Include articles without an abstract"
                  description="Off: skip records missing an abstract entirely"
                />
                <Toggle
                  checked={excludeDuplicates}
                  onChange={setExcludeDuplicates}
                  label="Exclude duplicates from export"
                  description="Duplicates are always kept and flagged internally; this only affects the exported file"
                />
              </div>
            </div>
          </div>

          {/* Right column */}
          <div className="flex flex-col gap-6">
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-center gap-2">
                <AlignLeft className="h-4 w-4 text-emerald-600" />
                <h2 className="font-semibold text-slate-900">Article Limits</h2>
              </div>

              <div className="mt-4 border-t border-slate-100 pt-4">
                <label className="mb-2 block text-sm font-medium text-slate-700">
                  Max articles per keyword
                </label>
                <div className="flex items-center overflow-hidden rounded-lg border border-slate-200">
                  <button
                    type="button"
                    onClick={() => setMaxArticles((n) => clamp(n - 5))}
                    className="px-4 py-2.5 text-slate-500 hover:bg-slate-50"
                  >
                    −
                  </button>
                  <input
                    type="number"
                    value={maxArticles}
                    onChange={(e) => setMaxArticles(Number(e.target.value))}
                    onBlur={() => setMaxArticles((n) => clamp(n))}
                    className="w-full flex-1 border-x border-slate-200 py-2.5 text-center text-lg font-semibold text-slate-900 focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => setMaxArticles((n) => clamp(n + 5))}
                    className="px-4 py-2.5 text-slate-500 hover:bg-slate-50"
                  >
                    +
                  </button>
                </div>
                <p className="mt-2 text-xs text-slate-400">Allowed range: 10 to 100 articles.</p>

                <div className="mt-4 flex gap-3 rounded-lg border border-slate-200 bg-slate-50 p-4">
                  <Shield className="h-4 w-4 shrink-0 text-slate-400" />
                  <p className="text-sm text-slate-600">
                    <span className="font-semibold text-slate-700">Compliance note:</span> The
                    platform enforces a strict{" "}
                    <span className="font-semibold text-slate-700">100-article hard cap</span> per
                    keyword to respect API rate limits and avoid provider blocking.
                  </p>
                </div>
              </div>
            </div>

            {errors.length === 0 ? (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-5">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                  <h3 className="font-semibold text-emerald-800">Configuration Valid</h3>
                </div>
                <p className="mt-2 text-sm text-emerald-700">
                  Your configuration complies with all source quotas. Estimated runtime: ~
                  {estimatedRuntime} seconds.
                </p>
                <div className="mt-4 space-y-2 border-t border-emerald-200 pt-4 text-sm">
                  <div className="flex justify-between">
                    <span className="text-emerald-700">Selected keywords:</span>
                    <span className="font-semibold text-emerald-900">
                      {keywords.length} terms
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-emerald-700">Active sources:</span>
                    <span className="font-semibold text-emerald-900">
                      {activeSourceIds.length} sources
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-emerald-700">Max potential yield:</span>
                    <span className="font-semibold text-emerald-900">
                      {maxPotentialYield} articles
                    </span>
                  </div>
                </div>
              </div>
            ) : (
              <div className="rounded-xl border border-amber-200 bg-amber-50 p-5">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="h-5 w-5 text-amber-600" />
                  <h3 className="font-semibold text-amber-800">Configuration Incomplete</h3>
                </div>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-amber-700">
                  {errors.map((err) => (
                    <li key={err}>{err}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>

        {serverMessage && (
          <div
            className={`mt-6 rounded-lg border p-4 text-sm ${
              serverMessage.kind === "success"
                ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                : "border-rose-200 bg-rose-50 text-rose-700"
            }`}
          >
            {serverMessage.text}
          </div>
        )}

        <div className="mt-8 flex items-center justify-between border-t border-slate-200 pt-6">
          <button
            onClick={() => navigate("/keywords")}
            className="flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-5 py-2.5 font-medium text-slate-700 hover:bg-slate-50"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Keywords
          </button>

          <div className="flex flex-col items-end gap-1.5">
            {errors.length > 0 && <span className="text-sm text-rose-600">{errors[0]}</span>}
            <button
              onClick={handleStart}
              disabled={errors.length > 0 || isSubmitting}
              className="flex items-center gap-2 rounded-lg bg-emerald-600 px-6 py-3 font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Play className="h-4 w-4" />
              {isSubmitting ? "Validating..." : "Start Collection"}
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
