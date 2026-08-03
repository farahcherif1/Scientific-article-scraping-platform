import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import ResultsPage from "./ResultsPage";
import * as articlesApi from "../api/articles";
import type { Article, ArticlesResponse, CollectionStats } from "../api/articles";

vi.mock("../api/articles", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/articles")>();
  return {
    ...actual,
    fetchArticles: vi.fn(),
    fetchCollectionStats: vi.fn(),
  };
});

function makeArticle(overrides: Partial<Article> = {}): Article {
  return {
    id: 1,
    title: "Deep Learning for Genomics",
    authors: ["Ada Lovelace", "Grace Hopper"],
    year: 2021,
    abstract: "An abstract about deep learning.",
    url: "https://example.org/article",
    doi: "10.1/xyz",
    venue: "Journal of AI",
    domain: "cs",
    categories: ["cs.AI"],
    citation_count: 12,
    source: "arxiv",
    search_keyword: "deep learning",
    collection_date: "2026-01-01T00:00:00Z",
    duplicate_group_id: null,
    is_duplicate: false,
    missing_fields: [],
    relevance_score: 3,
    ...overrides,
  };
}

function makeArticlesResponse(overrides: Partial<ArticlesResponse> = {}): ArticlesResponse {
  return {
    data: [makeArticle()],
    pagination: { total: 1, page: 1, page_size: 50 },
    sort: "-relevance",
    filters: {},
    ...overrides,
  };
}

function makeStats(overrides: Partial<CollectionStats> = {}): CollectionStats {
  return {
    total: 10,
    deduped: 8,
    duplicates: 2,
    pct_with_doi: 80,
    pct_with_abstract: 90,
    per_source: [
      { source: "arxiv", count: 6, pct_with_doi: 83.33, pct_with_abstract: 100, pct_with_year: 100 },
      { source: "openalex", count: 2, pct_with_doi: 50, pct_with_abstract: 50, pct_with_year: 100 },
    ],
    articles_per_year: [
      { year: 2019, count: 2 },
      { year: 2020, count: 6 },
    ],
    ...overrides,
  };
}

function renderResultsPage(initialEntry = "/collections/COL-0001") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/collections/:id" element={<ResultsPage />} />
      </Routes>
    </MemoryRouter>
  );
}

function lastArticlesCallParams() {
  return vi.mocked(articlesApi.fetchArticles).mock.calls.at(-1)?.[1];
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(articlesApi.fetchArticles).mockResolvedValue(makeArticlesResponse());
  vi.mocked(articlesApi.fetchCollectionStats).mockResolvedValue(makeStats());
});

describe("ResultsPage - banner and header", () => {
  it("shows the persistent not-exhaustive banner", async () => {
    renderResultsPage();
    expect(await screen.findByText(/results are not exhaustive/i)).toBeInTheDocument();
  });

  it("shows a disabled Export Dataset button (Sprint 6 feature, not built yet)", async () => {
    renderResultsPage();
    const exportButton = await screen.findByRole("button", { name: /export dataset/i });
    expect(exportButton).toBeDisabled();
  });
});

describe("ResultsPage - KPI cards", () => {
  it("renders KPI numbers from the stats endpoint", async () => {
    renderResultsPage();
    await waitFor(() => expect(articlesApi.fetchCollectionStats).toHaveBeenCalled());

    await screen.findByText("Total Articles");
    expect(screen.getByText("Total Articles").parentElement).toHaveTextContent("10");
    expect(screen.getByText("Deduped").parentElement).toHaveTextContent("8");
    expect(screen.getByText("Duplicates").parentElement).toHaveTextContent("2");
    expect(screen.getByText("% With DOI").parentElement).toHaveTextContent("80%");
    expect(screen.getByText("% With Abstract").parentElement).toHaveTextContent("90%");
  });
});

describe("ResultsPage - article table", () => {
  it("renders title, venue/author subtitle, DOI and citation columns", async () => {
    renderResultsPage();
    expect(await screen.findByText("Deep Learning for Genomics")).toBeInTheDocument();
    expect(screen.getByText("Journal of AI • Lovelace et al.")).toBeInTheDocument();
    expect(screen.getByText("10.1/xyz")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
  });

  it("shows an em dash for a missing DOI and a Missing DOI warning badge", async () => {
    vi.mocked(articlesApi.fetchArticles).mockResolvedValue(
      makeArticlesResponse({
        data: [makeArticle({ id: 2, doi: null, missing_fields: ["doi"] })],
      })
    );
    renderResultsPage();
    await screen.findByText("Deep Learning for Genomics");

    const row = screen.getByText("Deep Learning for Genomics").closest("tr");
    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).getByText("—")).toBeInTheDocument();
    expect(within(row as HTMLElement).getByText("Missing DOI")).toBeInTheDocument();
  });

  it("shows pagination summary text from the response envelope", async () => {
    vi.mocked(articlesApi.fetchArticles).mockResolvedValue(
      makeArticlesResponse({ pagination: { total: 120, page: 1, page_size: 50 } })
    );
    renderResultsPage();
    expect(await screen.findByText(/showing 1-50 of 120 deduplicated articles/i)).toBeInTheDocument();
  });
});

describe("ResultsPage - sort and rows-per-page (Select component)", () => {
  it("changing Sort by requests the API with the new sort value", async () => {
    const user = userEvent.setup();
    renderResultsPage();
    await screen.findByText("Deep Learning for Genomics");

    await user.click(screen.getByRole("combobox", { name: /sort by/i }));
    await user.click(screen.getByRole("option", { name: /year \(newest first\)/i }));

    await waitFor(() => {
      expect(lastArticlesCallParams()).toMatchObject({ sort: "-year" });
    });
  });

  it("changing Rows per page requests the API with the new page size", async () => {
    const user = userEvent.setup();
    renderResultsPage();
    await screen.findByText("Deep Learning for Genomics");

    await user.click(screen.getByRole("combobox", { name: /rows per page/i }));
    await user.click(screen.getByRole("option", { name: "100" }));

    await waitFor(() => {
      expect(lastArticlesCallParams()).toMatchObject({ page_size: 100 });
    });
  });
});

describe("ResultsPage - pagination controls", () => {
  it("clicking page 2 requests the second page", async () => {
    const user = userEvent.setup();
    vi.mocked(articlesApi.fetchArticles).mockResolvedValue(
      makeArticlesResponse({ pagination: { total: 120, page: 1, page_size: 50 } })
    );
    renderResultsPage();
    await screen.findByText("Deep Learning for Genomics");

    await user.click(screen.getByRole("button", { name: "2" }));

    await waitFor(() => {
      expect(lastArticlesCallParams()).toMatchObject({ page: 2 });
    });
  });

  it("disables Previous on the first page", async () => {
    renderResultsPage();
    await screen.findByText("Deep Learning for Genomics");
    expect(screen.getByRole("button", { name: /previous page/i })).toBeDisabled();
  });
});

describe("ResultsPage - filters", () => {
  it("checking a source checkbox refetches with that source", async () => {
    const user = userEvent.setup();
    renderResultsPage();
    await screen.findByText("Deep Learning for Genomics");

    await user.click(screen.getByRole("checkbox", { name: "OpenAlex" }));

    await waitFor(() => {
      expect(lastArticlesCallParams()).toMatchObject({ source: ["openalex"] });
    });
  });

  it("checking Has DOI refetches with has_doi true", async () => {
    const user = userEvent.setup();
    renderResultsPage();
    await screen.findByText("Deep Learning for Genomics");

    await user.click(screen.getByRole("checkbox", { name: "Has DOI" }));

    await waitFor(() => {
      expect(lastArticlesCallParams()).toMatchObject({ has_doi: true });
    });
  });

  it("entering a year range refetches with year_from/year_to", async () => {
    const user = userEvent.setup();
    renderResultsPage();
    await screen.findByText("Deep Learning for Genomics");

    await user.type(screen.getByLabelText(/year from/i), "2020");

    await waitFor(() => {
      expect(lastArticlesCallParams()).toMatchObject({ year_from: 2020 });
    });
  });

  it("reflects an active filter and Reset clears it", async () => {
    const user = userEvent.setup();
    renderResultsPage("/collections/COL-0001?source=openalex");
    await screen.findByText("Deep Learning for Genomics");

    expect(screen.getByRole("checkbox", { name: "OpenAlex" })).toBeChecked();
    expect(screen.getByRole("button", { name: /reset/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /reset/i }));

    await waitFor(() => {
      expect(lastArticlesCallParams()).not.toMatchObject({ source: ["openalex"] });
    });
    expect(screen.queryByRole("button", { name: /reset/i })).not.toBeInTheDocument();
  });
});

describe("ResultsPage - missing-metadata badges", () => {
  it("shows a visible text label for missing DOI/abstract/year, not color alone", async () => {
    vi.mocked(articlesApi.fetchArticles).mockResolvedValue(
      makeArticlesResponse({
        data: [
          makeArticle({
            id: 2,
            title: "Incomplete Record",
            doi: null,
            abstract: null,
            year: null,
            missing_fields: ["doi", "abstract", "year"],
          }),
        ],
      })
    );
    renderResultsPage();

    expect(await screen.findByText("Missing DOI")).toBeInTheDocument();
    expect(screen.getByText("Missing Abstract")).toBeInTheDocument();
    expect(screen.getByText("Missing Year")).toBeInTheDocument();
  });
});

describe("ResultsPage - article detail drawer", () => {
  it("opens with the article's full metadata when a row is clicked", async () => {
    const user = userEvent.setup();
    renderResultsPage();
    await user.click(await screen.findByText("Deep Learning for Genomics"));

    expect(await screen.findByText("Ada Lovelace, Grace Hopper")).toBeInTheDocument();
    expect(within(document.body).getByText("An abstract about deep learning.")).toBeInTheDocument();
  });

  it("renders a safe http(s) article link as a clickable anchor", async () => {
    const user = userEvent.setup();
    renderResultsPage();
    await user.click(await screen.findByText("Deep Learning for Genomics"));

    const link = await screen.findByRole("link", { name: "https://example.org/article" });
    expect(link).toHaveAttribute("href", "https://example.org/article");
    expect(link.getAttribute("rel")).toContain("noreferrer");
  });

  it("never renders a javascript: article URL as a clickable link", async () => {
    vi.mocked(articlesApi.fetchArticles).mockResolvedValue(
      makeArticlesResponse({
        data: [makeArticle({ id: 3, url: "javascript:alert(1)" })],
      })
    );
    const user = userEvent.setup();
    renderResultsPage();
    await user.click(await screen.findByText("Deep Learning for Genomics"));

    await screen.findByText("javascript:alert(1)");
    expect(screen.queryByRole("link", { name: /javascript:/i })).not.toBeInTheDocument();
  });

  it("closes when the close button is clicked", async () => {
    const user = userEvent.setup();
    renderResultsPage();
    await user.click(await screen.findByText("Deep Learning for Genomics"));
    await screen.findByText("An abstract about deep learning.");

    await user.click(screen.getByRole("button", { name: /close/i }));

    await waitFor(() => {
      expect(screen.queryByText("An abstract about deep learning.")).not.toBeInTheDocument();
    });
  });
});
