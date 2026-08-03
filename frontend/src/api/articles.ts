const API_BASE = import.meta.env.VITE_API_BASE_URL;

export type SortField =
  | "relevance"
  | "-relevance"
  | "year"
  | "-year"
  | "citation_count"
  | "-citation_count";

export interface Article {
  id: number;
  title: string;
  authors: string[];
  year: number | null;
  abstract: string | null;
  url: string | null;
  doi: string | null;
  venue: string | null;
  domain: string | null;
  categories: string[];
  citation_count: number | null;
  source: string;
  search_keyword: string;
  collection_date: string;
  duplicate_group_id: string | null;
  is_duplicate: boolean;
  missing_fields: string[];
  relevance_score: number;
}

export interface ArticleFilters {
  year_from?: number;
  year_to?: number;
  source?: string[];
  has_doi?: boolean;
  has_abstract?: boolean;
  keyword?: string;
}

export interface ArticlesQuery extends ArticleFilters {
  page?: number;
  page_size?: number;
  sort?: SortField;
}

export interface ArticlesResponse {
  data: Article[];
  pagination: { total: number; page: number; page_size: number };
  sort: SortField;
  filters: Record<string, unknown>;
}

export interface PerSourceStat {
  source: string;
  count: number;
  pct_with_doi: number;
  pct_with_abstract: number;
  pct_with_year: number;
}

export interface YearCount {
  year: number;
  count: number;
}

export interface CollectionStats {
  total: number;
  deduped: number;
  duplicates: number;
  pct_with_doi: number;
  pct_with_abstract: number;
  per_source: PerSourceStat[];
  articles_per_year: YearCount[];
}

async function parseErrorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    return body.error?.message || body.detail || fallback;
  } catch {
    return fallback;
  }
}

function buildQueryString(query: ArticlesQuery): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      for (const item of value) params.append(key, String(item));
    } else {
      params.set(key, String(value));
    }
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export async function fetchArticles(
  collectionId: string,
  query: ArticlesQuery = {}
): Promise<ArticlesResponse> {
  const res = await fetch(
    `${API_BASE}/api/v1/collections/${collectionId}/articles${buildQueryString(query)}`
  );
  if (!res.ok) {
    throw new Error(await parseErrorDetail(res, "Could not load articles for this collection."));
  }
  return res.json();
}

export async function fetchCollectionStats(collectionId: string): Promise<CollectionStats> {
  const res = await fetch(`${API_BASE}/api/v1/collections/${collectionId}/stats`);
  if (!res.ok) {
    throw new Error(await parseErrorDetail(res, "Could not load collection stats."));
  }
  return res.json();
}
