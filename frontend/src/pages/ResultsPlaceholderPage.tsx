import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AlertTriangle, BarChart3, RefreshCw } from "lucide-react";
import TopNav from "../components/TopNav";
import {
  fetchCollectionDetail,
  fetchCollectionStats,
  type CollectionDetail,
  type CollectionStats,
} from "../api/collections";

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

/*
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
*/

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
  const [stats, setStats] = useState<CollectionStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadCollection();
  }, [id]);

  async function loadCollection() {
    setIsLoading(true);
    setError(null);
    try {
      const [detail, statsData] = await Promise.all([fetchCollectionDetail(id), fetchCollectionStats(id)]);
      setCollection(detail);
      setStats(statsData);
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
          ) : collection && stats ? (
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
                        {stats.total} articles
                      </p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-wide text-slate-500">Deduped</p>
                      <p className="mt-1 text-lg font-semibold text-slate-900">
                        {stats.deduped} articles
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
                        Dashboard KPIs
                      </h2>
                      <p className="mt-2 text-sm text-slate-600">
                        Summary counts and metadata completeness for the collected set.
                      </p>
                    </div>
                  </div>

                  <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
                    <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
                      <p className="text-xs uppercase tracking-wide text-slate-500">Total</p>
                      <p className="mt-3 text-3xl font-semibold text-slate-900">{stats.total}</p>
                    </div>
                    <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
                      <p className="text-xs uppercase tracking-wide text-slate-500">Deduped</p>
                      <p className="mt-3 text-3xl font-semibold text-slate-900">{stats.deduped}</p>
                    </div>
                    <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
                      <p className="text-xs uppercase tracking-wide text-slate-500">Duplicates</p>
                      <p className="mt-3 text-3xl font-semibold text-slate-900">{stats.duplicates}</p>
                    </div>
                    <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
                      <p className="text-xs uppercase tracking-wide text-slate-500">% with DOI</p>
                      <p className="mt-3 text-3xl font-semibold text-slate-900">{stats.doi_percentage.toFixed(1)}%</p>
                    </div>
                    <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
                      <p className="text-xs uppercase tracking-wide text-slate-500">% with abstract</p>
                      <p className="mt-3 text-3xl font-semibold text-slate-900">{stats.abstract_percentage.toFixed(1)}%</p>
                    </div>
                    <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
                      <p className="text-xs uppercase tracking-wide text-slate-500">Per-source counts</p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {stats.per_source_counts.map((item) => (
                          <span key={item.source} className="rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-slate-600">
                            {formatSourceLabel(item.source)}: {item.count}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                </section>

                <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                  <div className="flex items-center gap-2">
                    <BarChart3 className="h-4 w-4 text-emerald-600" />
                    <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                      Articles per year
                    </h2>
                  </div>
                  <div className="mt-6 flex h-56 items-end gap-3 rounded-2xl border border-slate-100 bg-slate-50 p-4">
                    {stats.articles_per_year.length === 0 ? (
                      <p className="text-sm text-slate-500">No year data is available for this collection yet.</p>
                    ) : (
                      stats.articles_per_year.map(([year, count]) => (
                        <div key={year} className="flex flex-1 flex-col items-center gap-2">
                          <div className="w-full rounded-t-lg bg-emerald-500" style={{ height: `${Math.max(10, (count / Math.max(...stats.articles_per_year.map(([, value]) => value), 1)) * 100)}%` }} />
                          <div className="text-center text-xs font-semibold text-slate-600">{year}</div>
                          <div className="text-center text-xs text-slate-500">{count}</div>
                        </div>
                      ))
                    )}
                  </div>
                </section>
              </div>
              <aside className="space-y-6">
                <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                  <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                    Notes
                  </h2>
                  <p className="mt-3 text-sm text-slate-600">
                    This dashboard summarizes the collected dataset, including deduplication counts and metadata completeness percentages.
                  </p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                  <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                    Result view status
                  </h2>
                  <p className="mt-3 text-sm text-slate-600">
                    The item-level results experience will follow in a later release; this view focuses on the requested KPI cards and year distribution chart.
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
