/**
 * Turns a pasted sample JSON response into dot-path suggestions matching the
 * backend's `resolve_path` mini-DSL (app/connectors/generic_config.py):
 * `key.nested`, `key[].nested` (array of objects), or a bare `key` whose
 * value is already an array of scalars. Lets a researcher paste one example
 * response and get field-mapping paths suggested instead of hand-writing
 * them from API docs.
 */
import type { TargetField } from "../api/customConnectors";

export interface PathCandidate {
  path: string;
  sampleValue: string;
}

export interface ArrayContainerCandidate {
  path: string;
  itemCount: number;
  sampleKeys: string[];
}

function preview(value: unknown): string {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text.length > 60 ? `${text.slice(0, 57)}...` : text;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

/** Every leaf field (scalar, or array of scalars) reachable from the sample, as a resolve_path-compatible dot-path. */
export function flattenLeafPaths(sample: unknown, prefix = ""): PathCandidate[] {
  if (Array.isArray(sample)) {
    if (sample.length === 0) return [];
    const [first] = sample;
    if (isPlainObject(first)) {
      return flattenLeafPaths(first, prefix ? `${prefix}[]` : "[]");
    }
    // Array of scalars: the array itself is the leaf value (no [] needed).
    return prefix ? [{ path: prefix, sampleValue: preview(sample) }] : [];
  }
  if (isPlainObject(sample)) {
    return Object.entries(sample).flatMap(([key, value]) =>
      flattenLeafPaths(value, prefix ? `${prefix}.${key}` : key)
    );
  }
  return prefix ? [{ path: prefix, sampleValue: preview(sample) }] : [];
}

/** Every array-of-objects reachable from the sample, as a candidate for `pagination.results_path`. */
export function flattenArrayContainers(
  sample: unknown,
  prefix = ""
): ArrayContainerCandidate[] {
  const found: ArrayContainerCandidate[] = [];
  if (Array.isArray(sample)) {
    if (sample.length > 0 && isPlainObject(sample[0])) {
      found.push({
        path: prefix || "[]",
        itemCount: sample.length,
        sampleKeys: Object.keys(sample[0]),
      });
      found.push(...flattenArrayContainers(sample[0], prefix ? `${prefix}[]` : "[]"));
    }
    return found;
  }
  if (isPlainObject(sample)) {
    for (const [key, value] of Object.entries(sample)) {
      found.push(...flattenArrayContainers(value, prefix ? `${prefix}.${key}` : key));
    }
  }
  return found;
}

/** Picks the array-of-objects most likely to be the paginated result list (deepest, most fields = most likely a record). */
export function suggestResultsPath(sample: unknown): string | null {
  const containers = flattenArrayContainers(sample);
  if (containers.length === 0) return null;
  return [...containers].sort((a, b) => b.sampleKeys.length - a.sampleKeys.length)[0].path;
}

const FIELD_KEYWORDS: Record<TargetField, string[]> = {
  title: ["title", "headline", "name"],
  // "auth" catches real-world abbreviated field names (e.g. HAL's
  // authFullName_s) that don't contain the full word "author".
  authors: ["author", "creator", "contributor", "auth"],
  year: ["year", "date", "published"],
  abstract: ["abstract", "summary", "description"],
  doi: ["doi"],
  citation_count: ["citation", "citedby", "cited_by", "citing"],
  url: ["url", "link", "href", "downloadurl"],
  venue: ["venue", "journal", "publisher", "source"],
};

function score(path: string, field: TargetField): number {
  const lower = path.toLowerCase();
  const keywords = FIELD_KEYWORDS[field];
  let best = 0;
  for (const kw of keywords) {
    if (lower === kw || lower.endsWith(`.${kw}`) || lower.endsWith(`[].${kw}`)) {
      best = Math.max(best, 3);
    } else if (lower.includes(kw)) {
      best = Math.max(best, 1);
    }
  }
  return best;
}

/**
 * Suggests one path per target field by keyword-matching the sample's
 * flattened leaf paths - relative to the chosen `resultsPath` (paths are
 * resolved per-record, so a container prefix like "results[]" is stripped).
 */
export function suggestFieldMappings(
  sample: unknown,
  resultsPath: string | null
): Partial<Record<TargetField, string>> {
  let recordSample: unknown = sample;
  if (resultsPath) {
    const containers = flattenArrayContainers(sample);
    const container = containers.find((c) => c.path === resultsPath);
    if (container) {
      // Re-derive one example record to flatten leaf paths from, by walking the path.
      recordSample = _firstRecordAt(sample, resultsPath);
    }
  }

  const candidates = flattenLeafPaths(recordSample);
  const suggestions: Partial<Record<TargetField, string>> = {};
  (Object.keys(FIELD_KEYWORDS) as TargetField[]).forEach((field) => {
    let bestPath: string | null = null;
    let bestScore = 0;
    for (const candidate of candidates) {
      const s = score(candidate.path, field);
      if (s > bestScore) {
        bestScore = s;
        bestPath = candidate.path;
      }
    }
    if (bestPath) suggestions[field] = bestPath;
  });
  return suggestions;
}

function _firstRecordAt(sample: unknown, path: string): unknown {
  if (path === "[]") {
    return Array.isArray(sample) && sample.length > 0 ? sample[0] : sample;
  }
  let current: unknown = sample;
  for (const rawSegment of path.split(".")) {
    const isArraySegment = rawSegment.endsWith("[]");
    const key = isArraySegment ? rawSegment.slice(0, -2) : rawSegment;
    if (!isPlainObject(current)) return current;
    current = current[key];
    if (isArraySegment) {
      current = Array.isArray(current) && current.length > 0 ? current[0] : current;
    }
  }
  // `results_path` itself points straight at the array (no trailing `[]` -
  // that marker is only used mid-path, to fan out into a nested field). If
  // we landed on the array itself, descend to its first element.
  if (Array.isArray(current)) {
    return current.length > 0 ? current[0] : current;
  }
  return current;
}
