import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AlertTriangle, RefreshCw, XCircle } from "lucide-react";
import TopNav from "../components/TopNav";
import {
  abortCollection,
  fetchCollectionProgress,
  type CollectionProgress,
  type SourceRunStatus,
} from "../api/collections";

const POLL_INTERVAL_MS = 2000;

const SOURCE_LABELS: Record<string, string> = {
  arxiv: "arXiv",
  openalex: "OpenAlex",
  crossref: "Crossref",
  pubmed: "PubMed",
  semantic_scholar: "Semantic Scholar",
};

const SOURCE_PILL_STYLES: Record<SourceRunStatus, string> = {
  done: "bg-emerald-100 text-emerald-700",
  running: "bg-emerald-600 text-white",
  pending: "bg-slate-100 text-slate-500",
  failed: "bg-rose-100 text-rose-700",
};

const SOURCE_PILL_LABELS: Record<SourceRunStatus, string> = {
  done: "Done",
  running: "Running",
  pending: "Pending",
  failed: "Failed",
};

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${minutes}m ${rest.toString().padStart(2, "0")}s`;
}

export default function CollectionPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();

  const [progress, setProgress] = useState<CollectionProgress | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isAborting, setIsAborting] = useState(false);
  const [isPolling, setIsPolling] = useState(true);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    poll();
    intervalRef.current = setInterval(poll, POLL_INTERVAL_MS);
    return stopPolling;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  function stopPolling() {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    setIsPolling(false);
  }

  async function poll() {
    try {
      const data = await fetchCollectionProgress(id);
      setProgress(data);
      setLoadError(null);
      if (data.status === "completed") {
        stopPolling();
        navigate(`/collections/${id}`);
      } else if (data.status === "failed") {
        stopPolling();
      }
    } catch (err) {
      // Transient network hiccup: keep the last known progress on screen and
      // keep retrying rather than wiping the UI (see US-03.4: one bad
      // request must not block visibility into the rest of the collection).
      setLoadError(err instanceof Error ? err.message : "Could not reach the collection status endpoint.");
    }
  }

  async function handleAbort() {
    setIsAborting(true);
    try {
      await abortCollection(id);
      stopPolling();
      navigate("/history");
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Could not abort the collection.");
    } finally {
      setIsAborting(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <TopNav />

      <main className="mx-auto max-w-3xl px-8 py-16">
        {!progress && !loadError ? (
          <div className="flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white py-16 text-slate-400 shadow-sm">
            <RefreshCw className="h-4 w-4 animate-spin" />
            Loading collection status...
          </div>
        ) : !progress && loadError ? (
          <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-slate-200 bg-white py-16 text-center shadow-sm">
            <AlertTriangle className="h-8 w-8 text-rose-500" />
            <p className="text-sm text-slate-600">{loadError}</p>
            <button
              onClick={poll}
              className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Retry
            </button>
          </div>
        ) : (
          progress && (
            <>
              <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-amber-600">
                      <span className="h-2 w-2 rounded-full bg-amber-500" />
                      Collection Run #{progress.id || id}
                    </div>
                    <h1 className="mt-1 text-2xl font-bold text-slate-900">
                      {progress.status === "failed"
                        ? "Collection Failed"
                        : progress.status === "completed"
                          ? "Collection Complete"
                          : "Extracting Research Corpus..."}
                    </h1>
                  </div>
                  <span className="whitespace-nowrap text-xs text-slate-400">
                    {isPolling ? `Polling API... (${POLL_INTERVAL_MS / 1000}s interval)` : "Polling stopped"}
                  </span>
                </div>

                <div className="mt-6 border-t border-slate-100 pt-6">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-slate-700">Overall Progress</span>
                    <span className="text-lg font-bold text-emerald-600">
                      {Math.round(progress.overall_progress)}%
                    </span>
                  </div>
                  <div className="mt-2 h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-emerald-600 transition-all duration-500"
                      style={{ width: `${Math.min(100, Math.max(0, progress.overall_progress))}%` }}
                    />
                  </div>

                  <div className="mt-3 flex items-center justify-between text-sm">
                    <span className="text-slate-500">
                      {progress.current_keyword ? (
                        <>
                          Processing keyword:{" "}
                          <span className="font-medium text-slate-700">
                            "{progress.current_keyword}"
                          </span>
                        </>
                      ) : (
                        "Waiting to start..."
                      )}
                    </span>
                    <span className="whitespace-nowrap text-slate-500">
                      Elapsed: <span className="font-semibold text-slate-700">{formatElapsed(progress.elapsed_seconds)}</span>
                    </span>
                  </div>
                </div>

                <div className="mt-6 border-t border-slate-100 pt-6">
                  <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                    Per-Source Status
                  </h2>
                  <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
                    {progress.sources.map((source) => (
                      <div
                        key={source.source}
                        className={`flex items-center justify-between gap-3 rounded-lg border p-4 ${
                          source.status === "running"
                            ? "border-emerald-200 bg-emerald-50"
                            : "border-slate-200 bg-white"
                        }`}
                      >
                        <div>
                          <div className="font-semibold text-slate-900">
                            {SOURCE_LABELS[source.source] ?? source.source}
                          </div>
                          <p className="mt-0.5 text-sm text-slate-500">
                            {source.detail ??
                              (source.status === "done"
                                ? `${source.articles_fetched} articles fetched`
                                : source.status === "pending"
                                  ? "Queued"
                                  : "")}
                          </p>
                        </div>
                        <span
                          className={`shrink-0 rounded-full px-3 py-1 text-xs font-semibold ${SOURCE_PILL_STYLES[source.status]}`}
                        >
                          {SOURCE_PILL_LABELS[source.status]}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {progress.status === "failed" && (
                <div className="mt-6 rounded-xl border border-rose-200 bg-rose-50 p-5">
                  <div className="flex items-center gap-2">
                    <XCircle className="h-5 w-5 text-rose-600" />
                    <h3 className="font-semibold text-rose-800">Collection Failed</h3>
                  </div>
                  <p className="mt-2 text-sm text-rose-700">
                    {progress.error ?? "The collection stopped before finishing. Partial results, if any, are shown above."}
                  </p>
                </div>
              )}

              {progress.warning && progress.status !== "failed" && (
                <div className="mt-6 rounded-xl border border-amber-200 bg-white p-6">
                  <h3 className="font-semibold text-slate-900">Source Connection Warning</h3>
                  <p className="mt-2 text-sm text-slate-600">{progress.warning}</p>
                </div>
              )}

              {loadError && (
                <div className="mt-6 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700">
                  Lost connection to the status endpoint, retrying every {POLL_INTERVAL_MS / 1000}s: {loadError}
                </div>
              )}

              <div className="mt-8 flex items-center justify-between border-t border-slate-200 pt-6">
                <button
                  onClick={handleAbort}
                  disabled={isAborting || progress.status === "failed" || progress.status === "completed"}
                  className="rounded-lg border border-slate-300 bg-white px-5 py-2.5 font-medium text-rose-600 hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isAborting ? "Aborting..." : "Abort Collection"}
                </button>
                <button
                  onClick={() => navigate(`/collections/${id}`)}
                  className="rounded-lg bg-emerald-600 px-6 py-3 font-medium text-white hover:bg-emerald-700"
                >
                  Go to Live Results
                </button>
              </div>
            </>
          )
        )}
      </main>
    </div>
  );
}
