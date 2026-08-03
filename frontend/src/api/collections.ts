const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export interface CollectionParamsPayload {
  keywords: string[];
  sources: string[];
  max_articles_per_keyword: number;
  year_from?: number;
  year_to?: number;
  language?: string;
  domain?: string;
  include_missing_abstract: boolean;
  exclude_duplicates_on_export: boolean;
}

export interface CollectionParamsSummary {
  selected_keywords: number;
  active_sources: number;
  max_potential_yield: number;
  estimated_runtime_seconds: number;
}

export interface CollectionParamsResponse {
  valid: boolean;
  summary: CollectionParamsSummary;
}

interface PydanticErrorItem {
  msg?: string;
}

async function parseCollectionParamsError(res: Response, fallback: string): Promise<string> {
  const body = await res.json().catch(() => null);
  return Array.isArray(body?.detail)
    ? body.detail
        .map((d: PydanticErrorItem) => d.msg)
        .filter(Boolean)
        .join(" ") || fallback
    : body?.detail || fallback;
}

export async function validateCollectionParams(
  payload: CollectionParamsPayload
): Promise<CollectionParamsResponse> {
  const res = await fetch(`${API_BASE}/api/v1/collections/params/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(await parseCollectionParamsError(res, "The backend rejected this configuration."));
  }
  return res.json();
}

export interface StartCollectionResponse {
  id: string;
  status: CollectionRunStatus;
}

export async function startCollection(
  payload: CollectionParamsPayload
): Promise<StartCollectionResponse> {
  const res = await fetch(`${API_BASE}/api/v1/collections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(await parseCollectionParamsError(res, "Could not start the collection."));
  }
  return res.json();
}

export type CollectionRunStatus = "running" | "completed" | "warning" | "failed";
export type SourceRunStatus = "pending" | "running" | "done" | "failed";

export interface SourceProgress {
  source: string;
  status: SourceRunStatus;
  detail: string | null;
  articles_fetched: number;
}

export interface CollectionProgress {
  id: string;
  status: CollectionRunStatus;
  overall_progress: number; // 0-100
  current_keyword: string | null;
  elapsed_seconds: number;
  sources: SourceProgress[];
  warning: string | null;
  error: string | null;
}

export interface CollectionQualityStats {
  title: number;
  year: number;
  doi: number;
  abstract: number;
  duplicate_rate: number;
}

export interface CollectionDetail {
  id: string;
  keywords: string[];
  sources: string[];
  article_count: number;
  duplicate_count: number;
  quality_report: {
    overall: CollectionQualityStats;
    sources: Record<string, CollectionQualityStats>;
  };
  created_at: string;
  status: CollectionRunStatus;
}

export interface CollectionStats {
  total: number;
  deduped: number;
  duplicates: number;
  doi_percentage: number;
  abstract_percentage: number;
  per_source_counts: Array<{ source: string; count: number }>;
  articles_per_year: Array<[number, number]>;
}

async function parseErrorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    return body.error?.message || body.detail || fallback;
  } catch {
    return fallback;
  }
}

export async function fetchCollectionProgress(id: string): Promise<CollectionProgress> {
  const res = await fetch(`${API_BASE}/api/v1/collections/${id}/progress`);
  if (!res.ok) {
    throw new Error(await parseErrorDetail(res, "Could not reach the collection status endpoint."));
  }
  return res.json();
}

export async function fetchCollectionDetail(id: string): Promise<CollectionDetail> {
  const res = await fetch(`${API_BASE}/api/v1/collections/${id}`);
  if (!res.ok) {
    throw new Error(await parseErrorDetail(res, "Could not load collection details."));
  }
  return res.json();
}

export async function fetchCollectionStats(id: string): Promise<CollectionStats> {
  const res = await fetch(`${API_BASE}/api/v1/collections/${id}/stats`);
  if (!res.ok) {
    throw new Error(await parseErrorDetail(res, "Could not load collection stats."));
  }
  return res.json();
}

export async function abortCollection(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/collections/${id}/abort`, { method: "POST" });
  if (!res.ok) {
    throw new Error(await parseErrorDetail(res, "Could not abort the collection."));
  }
}
