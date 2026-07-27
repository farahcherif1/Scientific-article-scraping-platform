import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import CustomConnectorWizardPage from "./CustomConnectorWizardPage";
import * as customConnectorsApi from "../api/customConnectors";

vi.mock("../api/customConnectors", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/customConnectors")>();
  return {
    ...actual,
    testCustomConnector: vi.fn(),
    createCustomConnector: vi.fn(),
    updateCustomConnector: vi.fn(),
    getCustomConnector: vi.fn(),
  };
});

function renderWizard() {
  return render(
    <MemoryRouter initialEntries={["/sources/custom/new"]}>
      <Routes>
        <Route path="/sources/custom/new" element={<CustomConnectorWizardPage />} />
      </Routes>
    </MemoryRouter>
  );
}

async function goToStep2(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByPlaceholderText("e.g. IEEE Xplore"), "My Source");
  await user.type(
    screen.getByPlaceholderText("https://api.example.org/search"),
    "https://api.example.org/search"
  );
  await user.type(screen.getByPlaceholderText("e.g. q, query, querytext"), "q");
  await user.click(screen.getByRole("button", { name: /next/i }));
}

async function goToStep3(user: ReturnType<typeof userEvent.setup>) {
  await goToStep2(user);
  await user.type(
    screen.getByPlaceholderText("e.g. results, response.docs, resultList.result"),
    "items"
  );
  await user.click(screen.getByRole("button", { name: /next/i }));
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("CustomConnectorWizardPage - step validation", () => {
  it("blocks saving until the required step-1 fields are filled", async () => {
    const user = userEvent.setup();
    renderWizard();

    await user.click(screen.getByRole("button", { name: /next/i }));
    expect(
      screen.getByText(/give this source a name/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/base url must start with http/i)
    ).toBeInTheDocument();
  });

  it("requires a results path before step 2 is satisfied", async () => {
    const user = userEvent.setup();
    renderWizard();
    await goToStep2(user);

    expect(
      screen.getByText(/say where the list of results lives/i)
    ).toBeInTheDocument();
  });

  it("requires the title field mapping before saving is enabled", async () => {
    const user = userEvent.setup();
    renderWizard();
    await goToStep3(user);

    expect(screen.getByText(/map at least the title field/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /save custom connector/i })).toBeDisabled();
  });

  it("enables Save once all required fields across all 3 steps are filled", async () => {
    const user = userEvent.setup();
    renderWizard();
    await goToStep3(user);

    await user.type(screen.getByPlaceholderText("e.g. title or bibjson.title"), "title");

    expect(screen.getByRole("button", { name: /save custom connector/i })).toBeEnabled();
  });
});

describe("CustomConnectorWizardPage - test connection preview", () => {
  it("shows mapped articles on a successful test connection", async () => {
    vi.mocked(customConnectorsApi.testCustomConnector).mockResolvedValue({
      success: true,
      status_code: 200,
      request_url: "https://api.example.org/search?q=test",
      raw_response: { items: [{ title: "A Great Paper" }] },
      sample_records: [{ title: "A Great Paper" }],
      mapped_articles: [
        {
          title: "A Great Paper",
          authors: ["Ada Lovelace"],
          year: 2021,
          abstract: null,
          doi: null,
          venue: null,
          citation_count: null,
          url: null,
        },
      ],
      error: null,
    });

    const user = userEvent.setup();
    renderWizard();
    await goToStep3(user);
    await user.type(screen.getByPlaceholderText("e.g. title or bibjson.title"), "title");

    await user.click(screen.getByRole("button", { name: /run test query/i }));

    await waitFor(() => {
      expect(screen.getByText(/connected - http 200/i)).toBeInTheDocument();
    });
    expect(screen.getByText("A Great Paper")).toBeInTheDocument();
    expect(screen.getByText(/ada lovelace/i)).toBeInTheDocument();
  });

  it("shows an error banner instead of a 500 when the source rejects the request", async () => {
    vi.mocked(customConnectorsApi.testCustomConnector).mockResolvedValue({
      success: false,
      status_code: null,
      request_url: null,
      raw_response: null,
      sample_records: [],
      mapped_articles: [],
      error: "HTTP503: request failed after retries",
    });

    const user = userEvent.setup();
    renderWizard();
    await goToStep3(user);
    await user.type(screen.getByPlaceholderText("e.g. title or bibjson.title"), "title");

    await user.click(screen.getByRole("button", { name: /run test query/i }));

    await waitFor(() => {
      expect(screen.getByText(/test connection failed/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/http503/i)).toBeInTheDocument();
  });

  it("fills empty field-mapping paths from a pasted sample JSON response", async () => {
    const user = userEvent.setup();
    renderWizard();
    await goToStep3(user);

    const textarea = screen.getByPlaceholderText(/"results":/);
    fireEvent.change(textarea, {
      target: { value: '{"items": [{"title": "Sample", "authors": [{"name": "A"}]}]}' },
    });
    await user.click(screen.getByRole("button", { name: /suggest field paths/i }));

    const titleInput = screen.getByPlaceholderText("e.g. title or bibjson.title") as HTMLInputElement;
    await waitFor(() => expect(titleInput.value).toBe("title"));
  });
});
