const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export type AuthType = "none" | "api_key_header" | "api_key_query_param";
export type PaginationStyle = "page" | "offset" | "cursor" | "none";

export interface AuthConfig {
  type: AuthType;
  key_name?: string | null;
  key_value?: string | null;
}

export interface QueryMapping {
  keyword_param: string;
  year_from_param?: string | null;
  year_to_param?: string | null;
  static_params: Record<string, string>;
}

export interface PaginationConfig {
  style: PaginationStyle;
  page_size: number;
  page_size_param?: string | null;
  page_param?: string | null;
  start_page: number;
  offset_param?: string | null;
  start_offset: number;
  cursor_param?: string | null;
  next_cursor_path?: string | null;
  results_path: string;
  total_path?: string | null;
  stop_when_empty: boolean;
}

export type TargetField =
  | "title"
  | "authors"
  | "year"
  | "abstract"
  | "doi"
  | "citation_count"
  | "url"
  | "venue";

export interface FieldMapping {
  path?: string | null;
  default?: unknown;
}

export type FieldMappingConfig = Record<TargetField, FieldMapping>;

export interface CustomConnectorConfig {
  base_url: string;
  http_method: "GET" | "POST";
  auth: AuthConfig;
  query_mapping: QueryMapping;
  pagination: PaginationConfig;
  field_mapping: FieldMappingConfig;
  headers: Record<string, string>;
  rate_limit_rps: number;
  connect_timeout_s: number;
  read_timeout_s: number;
}

export interface CustomConnectorResponse {
  id: string;
  name: string;
  config: CustomConnectorConfig;
  enabled: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface CustomConnectorListResponse {
  data: CustomConnectorResponse[];
  pagination: { total: number; page: number; page_size: number };
  sort: string;
  filters: Record<string, string>;
}

export interface RawArticlePreview {
  title: string;
  authors: string[];
  year: number | null;
  abstract: string | null;
  doi: string | null;
  venue: string | null;
  citation_count: number | null;
  url: string | null;
}

export interface CustomConnectorTestResponse {
  success: boolean;
  status_code: number | null;
  request_url: string | null;
  raw_response: unknown;
  sample_records: unknown[];
  mapped_articles: RawArticlePreview[];
  error: string | null;
}

interface PydanticErrorItem {
  msg?: string;
  loc?: (string | number)[];
}

async function parseError(res: Response, fallback: string): Promise<string> {
  const body = await res.json().catch(() => null);
  if (Array.isArray(body?.detail)) {
    return (
      body.detail
        .map((d: PydanticErrorItem) =>
          d.loc ? `${d.loc[d.loc.length - 1]}: ${d.msg}` : d.msg
        )
        .filter(Boolean)
        .join(" ") || fallback
    );
  }
  return body?.detail || body?.error?.message || fallback;
}

export function emptyCustomConnectorConfig(): CustomConnectorConfig {
  return {
    base_url: "",
    http_method: "GET",
    auth: { type: "none", key_name: "", key_value: "" },
    query_mapping: { keyword_param: "", static_params: {} },
    pagination: {
      style: "none",
      page_size: 20,
      page_size_param: "",
      page_param: "",
      start_page: 1,
      offset_param: "",
      start_offset: 0,
      cursor_param: "",
      next_cursor_path: "",
      results_path: "",
      total_path: "",
      stop_when_empty: true,
    },
    field_mapping: {
      title: { path: "" },
      authors: { path: "" },
      year: { path: "" },
      abstract: { path: "" },
      doi: { path: "" },
      citation_count: { path: "" },
      url: { path: "" },
      venue: { path: "" },
    },
    headers: {},
    rate_limit_rps: 1,
    connect_timeout_s: 10,
    read_timeout_s: 30,
  };
}

export async function testCustomConnector(
  config: CustomConnectorConfig,
  keyword = "test",
  maxResults = 3
): Promise<CustomConnectorTestResponse> {
  const res = await fetch(`${API_BASE}/api/v1/custom-connectors/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ config, keyword, max_results: maxResults }),
  });
  if (!res.ok) {
    throw new Error(await parseError(res, "The test-connection request was rejected."));
  }
  return res.json();
}

export async function listCustomConnectors(): Promise<CustomConnectorListResponse> {
  const res = await fetch(`${API_BASE}/api/v1/custom-connectors`);
  if (!res.ok) {
    throw new Error(await parseError(res, "Could not load custom sources."));
  }
  return res.json();
}

export async function getCustomConnector(slug: string): Promise<CustomConnectorResponse> {
  const res = await fetch(`${API_BASE}/api/v1/custom-connectors/${slug}`);
  if (!res.ok) {
    throw new Error(await parseError(res, "Could not load this custom source."));
  }
  return res.json();
}

export async function createCustomConnector(
  name: string,
  config: CustomConnectorConfig,
  enabled = true
): Promise<CustomConnectorResponse> {
  const res = await fetch(`${API_BASE}/api/v1/custom-connectors`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, config, enabled }),
  });
  if (!res.ok) {
    throw new Error(await parseError(res, "Could not save this custom source."));
  }
  return res.json();
}

export async function updateCustomConnector(
  slug: string,
  name: string,
  config: CustomConnectorConfig,
  enabled: boolean
): Promise<CustomConnectorResponse> {
  const res = await fetch(`${API_BASE}/api/v1/custom-connectors/${slug}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, config, enabled }),
  });
  if (!res.ok) {
    throw new Error(await parseError(res, "Could not update this custom source."));
  }
  return res.json();
}

export async function deleteCustomConnector(slug: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/custom-connectors/${slug}`, { method: "DELETE" });
  if (!res.ok) {
    throw new Error(await parseError(res, "Could not delete this custom source."));
  }
}

export async function checkCustomConnectorHealth(
  slug: string
): Promise<{ id: string; healthy: boolean }> {
  const res = await fetch(`${API_BASE}/api/v1/custom-connectors/${slug}/health`);
  if (!res.ok) {
    throw new Error(await parseError(res, "Could not check this source's health."));
  }
  return res.json();
}
