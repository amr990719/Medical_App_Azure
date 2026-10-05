import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { RadioBoxGroup } from "./RadioBoxGroup";

type Religion = "MUSLIM" | "CHRISTIAN";
const OPTIONS = [
  { value: "MUSLIM" as const, label: "مسلم" },
  { value: "CHRISTIAN" as const, label: "مسيحي" },
];

function Harness(props: { initial?: Religion | ""; onChange?: (v: Religion) => void; disabled?: boolean }) {
  const [value, setValue] = useState<Religion | "">(props.initial ?? "");
  return (
    <RadioBoxGroup<Religion>
      label="الديانة :"
      name="religion"
      options={OPTIONS}
      value={value}
      disabled={props.disabled}
      onChange={(next) => {
        setValue(next);
        props.onChange?.(next);
      }}
    />
  );
}

describe("RadioBoxGroup", () => {
  it("renders real radios inside a labelled group", () => {
    render(<Harness />);
    expect(screen.getByRole("radiogroup", { name: "الديانة :" })).toBeInTheDocument();
    expect(screen.getAllByRole("radio")).toHaveLength(2);
  });

  it("selects by clicking the box", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    await user.click(screen.getByText("مسيحي"));
    expect(onChange).toHaveBeenCalledWith("CHRISTIAN");
    expect(screen.getByRole("radio", { name: "مسيحي" })).toBeChecked();
  });

  it("arrow keys move the selection", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness initial="MUSLIM" onChange={onChange} />);
    screen.getByRole("radio", { name: "مسلم" }).focus();
    await user.keyboard("{ArrowDown}");
    expect(onChange).toHaveBeenLastCalledWith("CHRISTIAN");
    expect(screen.getByRole("radio", { name: "مسيحي" })).toBeChecked();
  });

  it("gives the selected box the grey inset style", () => {
    render(<Harness initial="MUSLIM" />);
    const selected = screen.getByText("مسلم").closest("label")!;
    const other = screen.getByText("مسيحي").closest("label")!;
    expect(selected.className).toContain("inset");
    expect(other.className).not.toContain("inset");
  });

  it("disabled radios cannot change", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness disabled onChange={onChange} />);
    await user.click(screen.getByText("مسيحي"));
    expect(onChange).not.toHaveBeenCalled();
  });

  it("shows the error", () => {
    render(
      <RadioBoxGroup label="النوع :" name="gender" options={OPTIONS} value="" onChange={() => {}} error="يرجى اختيار النوع" />,
    );
    expect(screen.getByRole("radiogroup", { name: "النوع :" })).toHaveAccessibleDescription("يرجى اختيار النوع");
  });
});
