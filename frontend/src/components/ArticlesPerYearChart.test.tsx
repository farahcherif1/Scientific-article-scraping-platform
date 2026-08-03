import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import ArticlesPerYearChart from "./ArticlesPerYearChart";

describe("ArticlesPerYearChart", () => {
  it("renders one bar per year with a year-axis label", () => {
    const { container } = render(
      <ArticlesPerYearChart
        data={[
          { year: 2019, count: 2 },
          { year: 2020, count: 8 },
        ]}
      />
    );
    expect(container.querySelectorAll("rect")).toHaveLength(2);
    expect(screen.getByText("2019")).toBeInTheDocument();
    expect(screen.getByText("2020")).toBeInTheDocument();
  });

  it("shows an empty state when there is no dated data", () => {
    render(<ArticlesPerYearChart data={[]} />);
    expect(screen.getByText(/no dated articles/i)).toBeInTheDocument();
  });
});
