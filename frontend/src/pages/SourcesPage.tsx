import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Globe,
  Loader2,
  Pencil,
  Plus,
  Trash2,
  XCircle,
} from "lucide-react";
import TopNav from "../components/TopNav";
import {
  checkCustomConnectorHealth,
  deleteCustomConnector,
  listCustomConnectors,
  type CustomConnectorResponse,
} from "../api/customConnectors";

const BUILTIN_SOURCES = [
  { id: "arxiv", name: "arXiv", description: "Physics, Mathematics, Computer Science preprints" },
  { id: "openalex", name: "OpenAlex", description: "Global open index of scientific papers and metadata" },
  { id: "crossref", name: "Crossref", description: "Metadata registry with persistent DOIs for publications" },
  { id: "pubmed", name: "PubMed", description: "Biomedical and life sciences literature (NCBI)" },
  { id: "semantic_scholar", name: "Semantic Scholar", description: "AI-powered index across all fields of research" },
];

type HealthState = "unknown" | "checking" | "healthy" | "unhealthy";

export default function SourcesPage() {
  const navigate = useNavigate();
  const [connectors, setConnectors] = useState<CustomConnectorResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [health, setHealth] = useState<Record<string, HealthState>>({});
  const [deletingSlug, setDeletingSlug] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);

  useEffect(() => {
    listCustomConnectors()
      .then((response) => {
        setConnectors(response.data);
        setLoadError(null);
      })
      .catch((err) => setLoadError(err instanceof Error ? err.message : "Could not load custom sources."))
      .finally(() => setIsLoading(false));
  }, []);

  async function handleCheckHealth(slug: string) {
    setHealth((prev) => ({ ...prev, [slug]: "checking" }));
    try {
      const result = await checkCustomConnectorHealth(slug);
      setHealth((prev) => ({ ...prev, [slug]: result.healthy ? "healthy" : "unhealthy" }));
    } catch {
      setHealth((prev) => ({ ...prev, [slug]: "unhealthy" }));
    }
  }

  async function handleDelete(slug: string) {
    setDeletingSlug(slug);
    try {
      await deleteCustomConnector(slug);
      setConnectors((prev) => prev.filter((c) => c.id !== slug));
      setPendingDelete(null);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Could not delete this custom source.");
    } finally {
      setDeletingSlug(null);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <TopNav />
      <main className="mx-auto max-w-5xl px-8 py-10">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-3xl font-bold text-slate-900">Scientific Sources</h1>
            <div className="mt-2 h-0.5 w-16 bg-emerald-500" />
            <p className="mt-4 max-w-2xl text-slate-500">
              The 5 built-in connectors are always available. Add a custom connector for a source
              we don't ship yet, entirely through configuration.
            </p>
          </div>
          <button
            onClick={() => navigate("/sources/custom/new")}
            className="flex shrink-0 items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 font-medium text-white hover:bg-emerald-700"
          >
            <Plus className="h-4 w-4" />
            Add Custom Source
          </button>
        </div>

        <section className="mt-8">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Built-in sources</h2>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
            {BUILTIN_SOURCES.map((source) => (
              <div key={source.id} className="flex items-start gap-3 rounded-lg border border-slate-200 bg-white p-4">
                <Globe className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
                <div>
                  <span className="font-semibold text-slate-900">{source.name}</span>
                  <p className="mt-0.5 text-sm text-slate-500">{source.description}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="mt-10">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Custom sources</h2>

          {loadError && (
            <div className="mt-3 rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
              {loadError}
            </div>
          )}

          {isLoading ? (
            <div className="mt-3 flex items-center gap-2 rounded-xl border border-slate-200 bg-white py-10 text-slate-400 shadow-sm">
              <Loader2 className="mx-auto h-4 w-4 animate-spin" />
            </div>
          ) : connectors.length === 0 ? (
            <div className="mt-3 rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-400">
              No custom sources yet. Add one to collect from a source outside the built-in list.
            </div>
          ) : (
            <div className="mt-3 flex flex-col gap-3">
              {connectors.map((connector) => {
                const state = health[connector.id] ?? "unknown";
                return (
                  <div
                    key={connector.id}
                    className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white p-4"
                  >
                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={() => handleCheckHealth(connector.id)}
                        title="Check connection health"
                        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-slate-200 hover:bg-slate-50"
                      >
                        {state === "checking" ? (
                          <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
                        ) : state === "healthy" ? (
                          <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                        ) : state === "unhealthy" ? (
                          <XCircle className="h-4 w-4 text-rose-500" />
                        ) : (
                          <Activity className="h-4 w-4 text-slate-300" />
                        )}
                      </button>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-slate-900">{connector.name}</span>
                          {!connector.enabled && (
                            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
                              Disabled
                            </span>
                          )}
                        </div>
                        <p className="mt-0.5 break-all font-mono text-xs text-slate-400">
                          {connector.config.base_url}
                        </p>
                      </div>
                    </div>

                    <div className="flex shrink-0 items-center gap-2">
                      <button
                        onClick={() => navigate(`/sources/custom/${connector.id}/edit`)}
                        className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                        Edit
                      </button>
                      {pendingDelete === connector.id ? (
                        <div className="flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-2 py-1">
                          <span className="flex items-center gap-1 text-xs text-rose-700">
                            <AlertTriangle className="h-3.5 w-3.5" />
                            Delete?
                          </span>
                          <button
                            onClick={() => handleDelete(connector.id)}
                            disabled={deletingSlug === connector.id}
                            className="rounded-md bg-rose-600 px-2 py-1 text-xs font-medium text-white hover:bg-rose-700"
                          >
                            {deletingSlug === connector.id ? "..." : "Confirm"}
                          </button>
                          <button
                            onClick={() => setPendingDelete(null)}
                            className="rounded-md px-2 py-1 text-xs text-slate-500 hover:bg-slate-100"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => setPendingDelete(connector.id)}
                          className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-rose-600 hover:bg-rose-50"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          Delete
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
