import { describe, expect, it } from "vitest";
import {
  flattenArrayContainers,
  flattenLeafPaths,
  suggestFieldMappings,
  suggestResultsPath,
} from "./jsonPathSuggest";

describe("flattenLeafPaths", () => {
  it("flattens nested objects into dot paths", () => {
    const paths = flattenLeafPaths({ bibjson: { title: "X" } });
    expect(paths).toEqual([{ path: "bibjson.title", sampleValue: "X" }]);
  });

  it("uses [] for arrays of objects and recurses into the first element", () => {
    const paths = flattenLeafPaths({ authors: [{ name: "A" }, { name: "B" }] });
    expect(paths).toEqual([{ path: "authors[].name", sampleValue: "A" }]);
  });

  it("treats an array of scalars as a single leaf (no [] needed)", () => {
    const paths = flattenLeafPaths({ authFullName_s: ["Ada", "Alan"] });
    expect(paths).toEqual([{ path: "authFullName_s", sampleValue: '["Ada","Alan"]' }]);
  });

  it("returns nothing for an empty array", () => {
    expect(flattenLeafPaths({ authors: [] })).toEqual([]);
  });
});

describe("flattenArrayContainers", () => {
  it("finds a nested array-of-objects container", () => {
    const sample = { response: { docs: [{ title_s: "A" }, { title_s: "B" }] } };
    const containers = flattenArrayContainers(sample);
    expect(containers).toEqual([
      { path: "response.docs", itemCount: 2, sampleKeys: ["title_s"] },
    ]);
  });

  it("finds a root-level array container as []", () => {
    const containers = flattenArrayContainers([{ title: "A" }]);
    expect(containers[0]).toEqual({ path: "[]", itemCount: 1, sampleKeys: ["title"] });
  });
});

describe("suggestResultsPath", () => {
  it("picks the array container with the most fields (most record-like)", () => {
    const sample = {
      meta: { tags: ["a", "b"] },
      results: [{ title: "A", authors: [], year: 2020, doi: "x" }],
    };
    expect(suggestResultsPath(sample)).toBe("results");
  });

  it("returns null when there is no array-of-objects at all", () => {
    expect(suggestResultsPath({ title: "A" })).toBeNull();
  });
});

describe("suggestFieldMappings", () => {
  it("matches HAL-shaped fields by keyword", () => {
    const sample = {
      response: {
        docs: [
          {
            title_s: "Deep Learning",
            authFullName_s: ["Ada Lovelace"],
            producedDateY_i: 2021,
            doiId_s: "10.1234/x",
            abstract_s: "An abstract",
          },
        ],
      },
    };
    const suggestions = suggestFieldMappings(sample, "response.docs");
    expect(suggestions.title).toBe("title_s");
    expect(suggestions.authors).toBe("authFullName_s");
    expect(suggestions.year).toBe("producedDateY_i");
    expect(suggestions.doi).toBe("doiId_s");
    expect(suggestions.abstract).toBe("abstract_s");
  });

  it("matches nested author objects and citation counts (CORE-shaped)", () => {
    const sample = {
      results: [
        {
          title: "Federated Learning Survey",
          authors: [{ name: "Jane Doe" }],
          yearPublished: 2022,
          citationCount: 17,
          doi: "10.5555/x",
        },
      ],
    };
    const suggestions = suggestFieldMappings(sample, "results");
    expect(suggestions.title).toBe("title");
    expect(suggestions.authors).toBe("authors[].name");
    expect(suggestions.citation_count).toBe("citationCount");
    expect(suggestions.year).toBe("yearPublished");
  });

  it("falls back to flattening the whole sample when resultsPath is null", () => {
    const suggestions = suggestFieldMappings({ title: "Solo Record" }, null);
    expect(suggestions.title).toBe("title");
  });
});
