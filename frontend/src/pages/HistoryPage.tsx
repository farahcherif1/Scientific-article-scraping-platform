import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, Clock, History as HistoryIcon, RefreshCw } from "lucide-react";
import TopNav from "../components/TopNav";
import {
  fetchCollectionHistory,
  type CollectionStatus,
  type CollectionSummary,
} from "../api/history";

const STATUS_STYLES: Record<CollectionStatus, { label: string; className: string }> = {
  completed: {
    label: "Completed",
    className: "border border-emerald-200 bg-emerald-50 text-emerald-700",
  },
  warning: {
    label: "Warning",
    className: "border border-amber-200 bg-amber-50 text-amber-700",
  },
  failed: {
    label: "Failed",
    className: "border border-rose-200 bg-rose-50 text-rose-700",
  },
  running: {
    label: "In Progress",
    className: "border border-slate-200 bg-slate-50 text-slate-600",
  },
};

function formatTimestamp(iso: string) {
  const d = new Date(iso);
  return {
    date: d.toLocaleDateString("en-US", { month: "short", day: "2-digit", year: "numeric" }),
    time: d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false }),
  };
}

export default function HistoryPage() {
  const navigate = useNavigate();
  const [collections, setCollections] = useState<CollectionSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadHistory();
  }, []);

  async function loadHistory() {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchCollectionHistory();
      setCollections(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load collection history.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <TopNav />

      <main className="mx-auto max-w-7xl px-8 py-10">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-slate-900">Collection History</h1>
            <div className="mt-2 h-0.5 w-16 bg-emerald-500" />
            <p className="mt-4 max-w-2xl text-slate-500">
              Review, filter, and instantly access previous scientific collection runs.
            </p>
          </div>
          <button
            onClick={() => navigate("/keywords")}
            className="rounded-lg bg-emerald-600 px-5 py-3 font-medium text-white hover:bg-emerald-700"
          >
            Start New Collection
          </button>
        </div>

        <div className="mt-8 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          {isLoading ? (
            <div className="flex items-center justify-center gap-2 py-16 text-slate-400">
              <RefreshCw className="h-4 w-4 animate-spin" />
              Loading collection history...
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
              <AlertTriangle className="h-8 w-8 text-rose-500" />
              <p className="text-sm text-slate-600">{error}</p>
              <button
                onClick={loadHistory}
                className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Retry
              </button>
            </div>
          ) : collections.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 py-16 text-center text-slate-400">
              <HistoryIcon className="h-8 w-8" />
              <p className="text-sm">No collections yet. Start one to see it here.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="bg-emerald-800 text-xs font-semibold uppercase tracking-wide text-white">
                    <th className="px-6 py-4">Collection ID</th>
                    <th className="px-6 py-4">Keywords Used</th>
                    <th className="px-6 py-4">Target Sources</th>
                    <th className="px-6 py-4">Articles Scraped</th>
                    <th className="px-6 py-4">Duplicates Removed</th>
                    <th className="px-6 py-4">Timestamp</th>
                    <th className="px-6 py-4">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {collections.map((c, i) => {
                    const { date, time } = formatTimestamp(c.created_at);
                    const status = STATUS_STYLES[c.status];
                    return (
                      <tr
                        key={c.id}
                        onClick={() => navigate(`/collections/${c.id}`)}
                        className={`cursor-pointer border-t border-slate-100 hover:bg-emerald-50/40 ${
                          i % 2 === 1 ? "bg-slate-50/60" : "bg-white"
                        }`}
                      >
                        <td className="px-6 py-4 font-medium text-emerald-700">#{c.id}</td>
                        <td className="max-w-xs px-6 py-4 text-slate-700">
                          <span className="block truncate" title={c.keywords.join(", ")}>
                            {c.keywords.join(", ")}
                          </span>
                        </td>
                        <td className="px-6 py-4">
                          <div className="flex flex-wrap gap-1.5">
                            {c.sources.map((s) => (
                              <span
                                key={s}
                                className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600"
                              >
                                {s}
                              </span>
                            ))}
                          </div>
                        </td>
                        <td className="px-6 py-4 font-semibold text-slate-900">
                          {c.article_count}
                        </td>
                        <td className="px-6 py-4 font-semibold text-amber-600">
                          {c.duplicate_count}
                        </td>
                        <td className="px-6 py-4 text-slate-600">
                          <div className="flex items-center gap-1.5">
                            <Clock className="h-3.5 w-3.5 text-slate-300" />
                            <div>
                              <div>{date}</div>
                              <div className="text-xs text-slate-400">{time}</div>
                            </div>
                          </div>
                        </td>
                        <td className="px-6 py-4">
                          <span
                            className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-medium ${status.className}`}
                          >
                            {status.label}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
