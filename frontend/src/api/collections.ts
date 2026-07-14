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

export async function validateCollectionParams(
  payload: CollectionParamsPayload
): Promise<CollectionParamsResponse> {
  const res = await fetch(`${API_BASE}/api/v1/collections/params/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail: string =
      Array.isArray(body?.detail)
        ? body.detail
            .map((d: PydanticErrorItem) => d.msg)
            .filter(Boolean)
            .join(" ")
        : body?.detail || "The backend rejected this configuration.";
    throw new Error(detail);
  }
  return res.json();
}
