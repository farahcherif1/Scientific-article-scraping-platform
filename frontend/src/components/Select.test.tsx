import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Select from "./Select";

const OPTIONS = [
  { value: "a", label: "Alpha" },
  { value: "b", label: "Beta" },
  { value: "c", label: "Gamma" },
];

function ControlledSelect({ onChange }: { onChange?: (v: string) => void }) {
  const [value, setValue] = useState("a");
  return (
    <Select
      value={value}
      onChange={(v) => {
        setValue(v);
        onChange?.(v);
      }}
      options={OPTIONS}
      aria-label="Demo select"
    />
  );
}

describe("Select", () => {
  it("shows the selected option's label on the trigger", () => {
    render(<ControlledSelect />);
    expect(screen.getByRole("combobox")).toHaveTextContent("Alpha");
  });

  it("opens the listbox on click and lists all options", async () => {
    const user = userEvent.setup();
    render(<ControlledSelect />);
    await user.click(screen.getByRole("combobox"));

    expect(screen.getByRole("listbox")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Beta" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Gamma" })).toBeInTheDocument();
  });

  it("calls onChange and closes when an option is clicked", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<ControlledSelect onChange={onChange} />);
    await user.click(screen.getByRole("combobox"));
    await user.click(screen.getByRole("option", { name: "Beta" }));

    expect(onChange).toHaveBeenCalledWith("b");
    expect(screen.getByRole("combobox")).toHaveTextContent("Beta");
    await waitFor(() => expect(screen.queryByRole("listbox")).not.toBeInTheDocument());
  });

  it("supports keyboard navigation: ArrowDown then Enter selects the next option", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<ControlledSelect onChange={onChange} />);
    const trigger = screen.getByRole("combobox");
    trigger.focus();

    await user.keyboard("{ArrowDown}"); // opens, highlights current (Alpha)
    await user.keyboard("{ArrowDown}"); // highlights Beta
    await user.keyboard("{Enter}");

    expect(onChange).toHaveBeenCalledWith("b");
  });

  it("closes without changing the value on Escape", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<ControlledSelect onChange={onChange} />);
    await user.click(screen.getByRole("combobox"));
    await user.keyboard("{Escape}");

    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("closes when clicking outside", async () => {
    const user = userEvent.setup();
    render(
      <div>
        <ControlledSelect />
        <button>Outside</button>
      </div>
    );
    await user.click(screen.getByRole("combobox"));
    expect(screen.getByRole("listbox")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Outside" }));
    await waitFor(() => expect(screen.queryByRole("listbox")).not.toBeInTheDocument());
  });

  it("marks the selected option with aria-selected", async () => {
    const user = userEvent.setup();
    render(<ControlledSelect />);
    await user.click(screen.getByRole("combobox"));

    expect(screen.getByRole("option", { name: "Alpha" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("option", { name: "Beta" })).toHaveAttribute("aria-selected", "false");
  });

  it("does not open when disabled", async () => {
    const user = userEvent.setup();
    render(<Select value="a" onChange={() => {}} options={OPTIONS} disabled aria-label="Disabled select" />);
    await user.click(screen.getByRole("combobox"));
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });
});
