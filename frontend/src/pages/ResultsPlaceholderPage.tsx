import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AlertTriangle, Clock, RefreshCw } from "lucide-react";
import TopNav from "../components/TopNav";
import { fetchCollectionDetail, type CollectionDetail } from "../api/collections";

const KPI_TARGETS = {
  title: 95,
  year: 80,
};

function formatTimestamp(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString("en-US", {
    month: "short",
    day: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function metricBadge(name: string, value: number) {
  const target = KPI_TARGETS[name as keyof typeof KPI_TARGETS];
  const success = target !== undefined && value >= target;
  return (
    <span
      className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${
        success
          ? "bg-emerald-100 text-emerald-700"
          : "bg-slate-100 text-slate-600"
      }`}
    >
      {name} {value.toFixed(1)}%
    </span>
  );
}

function formatSourceLabel(source: string) {
  const labels: Record<string, string> = {
    arxiv: "arXiv",
    openalex: "OpenAlex",
    crossref: "Crossref",
    pubmed: "PubMed",
    semantic_scholar: "Semantic Scholar",
  };
  return labels[source] || source;
}

export default function ResultsPlaceholderPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [collection, setCollection] = useState<CollectionDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadCollection();
  }, [id]);

  async function loadCollection() {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchCollectionDetail(id);
      setCollection(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load collection details.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <TopNav />
      <main className="mx-auto max-w-6xl px-8 py-10">
        <div className="flex flex-col gap-6">
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-emerald-600">
                  Collection #{id}
                </p>
                <h1 className="mt-2 text-3xl font-bold text-slate-900">Data Quality Report</h1>
                <p className="mt-2 max-w-2xl text-sm text-slate-500">
                  View the percent coverage for title, year, DOI, abstract, and duplicate rate across sources and overall.
                </p>
              </div>
              <button
                onClick={() => navigate("/history")}
                className="self-start rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Back to History
              </button>
            </div>
          </div>

          {isLoading ? (
            <div className="rounded-xl border border-slate-200 bg-white p-12 text-center text-slate-500 shadow-sm">
              <RefreshCw className="mx-auto h-6 w-6 animate-spin text-slate-400" />
              <p className="mt-3">Loading collection quality metrics...</p>
            </div>
          ) : error ? (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-8 text-center text-rose-700 shadow-sm">
              <AlertTriangle className="mx-auto h-6 w-6" />
              <p className="mt-3">{error}</p>
              <button
                onClick={loadCollection}
                className="mt-4 rounded-lg border border-rose-200 bg-white px-4 py-2 text-sm font-medium text-rose-700 hover:bg-rose-50"
              >
                Retry
              </button>
            </div>
          ) : collection ? (
            <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
              <div className="space-y-6">
                <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                  <div className="flex flex-wrap items-center gap-4">
                    <div>
                      <p className="text-xs uppercase tracking-wide text-slate-500">Status</p>
                      <p className="mt-1 text-lg font-semibold text-slate-900">
                        {collection.status}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-wide text-slate-500">Collected</p>
                      <p className="mt-1 text-lg font-semibold text-slate-900">
                        {collection.article_count} articles
                      </p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-wide text-slate-500">Duplicates</p>
                      <p className="mt-1 text-lg font-semibold text-slate-900">
                        {collection.duplicate_count}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-wide text-slate-500">Created</p>
                      <p className="mt-1 text-lg font-semibold text-slate-900">
                        {formatTimestamp(collection.created_at)}
                      </p>
                    </div>
                  </div>
                </div>

                <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                  <div className="flex items-center justify-between">
                    <div>
                      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                        Overall Metrics
                      </h2>
                      <p className="mt-2 text-sm text-slate-600">
                        KPIs are highlighted when the coverage targets are met.
                      </p>
                    </div>
                    <div className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
                      title ≥ {KPI_TARGETS.title}%, year ≥ {KPI_TARGETS.year}%
                    </div>
                  </div>

                  <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
                    {Object.entries(collection.quality_report.overall).map(([metric, value]) => (
                      <div key={metric} className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
                        <p className="text-xs uppercase tracking-wide text-slate-500">{metric.replace("_", " ")}</p>
                        <p className="mt-3 text-3xl font-semibold text-slate-900">
                          {metric === "duplicate_rate" ? `${value.toFixed(1)}%` : `${value.toFixed(1)}%`}
                        </p>
                        {metric in KPI_TARGETS ? (
                          <div className="mt-2">
                            {metricBadge(metric, value)}
                          </div>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </section>

                <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                  <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                    Per-Source Quality
                  </h2>
                  <div className="mt-4 space-y-4">
                    {Object.entries(collection.quality_report.sources).map(([source, stats]) => (
                      <div key={source} className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <h3 className="text-base font-semibold text-slate-900">
                            {formatSourceLabel(source)}
                          </h3>
                          <div className="flex flex-wrap gap-2">
                            {Object.entries(stats).map(([metric, value]) => (
                              metric === "duplicate_rate" ? (
                                <span
                                  key={metric}
                                  className="inline-flex items-center rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600"
                                >
                                  dup {value.toFixed(1)}%
                                </span>
                              ) : (
                                <span
                                  key={metric}
                                  className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${
                                    metric in KPI_TARGETS && value >= KPI_TARGETS[metric as keyof typeof KPI_TARGETS]
                                      ? "bg-emerald-100 text-emerald-700"
                                      : "bg-slate-100 text-slate-600"
                                  }`}
                                >
                                  {metric} {value.toFixed(1)}%
                                </span>
                              )
                            ))}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              </div>
              <aside className="space-y-6">
                <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                  <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                    Notes
                  </h2>
                  <p className="mt-3 text-sm text-slate-600">
                    This report shows how complete the collected metadata is. Missing or invalid fields are included in the quality percentages, and duplicates are counted after deduplication.
                  </p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                  <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                    Result view status
                  </h2>
                  <p className="mt-3 text-sm text-slate-600">
                    The full item-level results screen is planned for a later release. This page currently focuses on the requested data quality report.
                  </p>
                </div>
              </aside>
            </div>
          ) : null}
        </div>
      </main>
    </div>
  );
}
