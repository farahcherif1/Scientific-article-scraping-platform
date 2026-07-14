const API_BASE = import.meta.env.VITE_API_BASE_URL;

export type CollectionStatus = "completed" | "warning" | "failed" | "running";

export interface CollectionSummary {
  id: string;
  keywords: string[];
  sources: string[];
  article_count: number;
  duplicate_count: number;
  created_at: string;
  status: CollectionStatus;
}

interface ListEnvelope<T> {
  data: T[];
  pagination: { total: number; page: number; page_size: number };
  sort: string;
  filters: Record<string, unknown>;
}

async function parseErrorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    return body.error?.message || body.detail || fallback;
  } catch {
    return fallback;
  }
}

export async function fetchCollectionHistory(): Promise<CollectionSummary[]> {
  const res = await fetch(`${API_BASE}/api/v1/history`);
  if (!res.ok) {
    throw new Error(await parseErrorDetail(res, "Could not load collection history."));
  }
  try {
    const body: ListEnvelope<CollectionSummary> = await res.json();
    return body.data;
  } catch {
    throw new Error("Could not load collection history.");
  }
}
