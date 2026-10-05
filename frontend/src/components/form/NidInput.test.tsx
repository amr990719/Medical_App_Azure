import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { NidInput } from "./NidInput";

const LABEL = "الرقم القومي";

function Harness(props: { initial?: string; readOnly?: boolean; onChange?: (v: string) => void }) {
  const [value, setValue] = useState(props.initial ?? "");
  return (
    <NidInput
      label={LABEL}
      value={value}
      readOnly={props.readOnly}
      onChange={(next) => {
        setValue(next);
        props.onChange?.(next);
      }}
    />
  );
}

const boxes = () => screen.getAllByRole("textbox", { name: /^الرقم \d+ من 14$/ });
const box = (index: number) => boxes()[index] as HTMLInputElement;
const fullValue = () => screen.getByRole("textbox", { name: LABEL });

describe("NidInput", () => {
  it("renders 14 LTR boxes inside one labelled group", () => {
    render(<Harness />);
    const group = screen.getByRole("group", { name: LABEL });
    expect(group).toHaveAttribute("dir", "ltr");
    expect(boxes()).toHaveLength(14);
    expect(box(0)).toHaveAttribute("inputmode", "numeric");
  });

  it("exposes the whole value through one labelled read-only input", () => {
    render(<Harness initial="29501230101234" />);
    expect(fullValue()).toHaveValue("29501230101234");
    expect(fullValue()).toHaveAttribute("readonly");
  });

  it("auto-advances while typing", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(box(0));
    await user.keyboard("295");
    expect(fullValue()).toHaveValue("295");
    expect(box(3)).toHaveFocus();
  });

  it("normalizes Eastern Arabic digits", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(box(0));
    await user.keyboard("٢٩٥");
    expect(fullValue()).toHaveValue("295");
    expect(box(0)).toHaveValue("2");
  });

  it("ignores non-digits", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    await user.click(box(0));
    await user.keyboard("a-ب ");
    expect(onChange).not.toHaveBeenCalled();
    expect(box(0)).toHaveValue("");
    expect(box(0)).toHaveFocus();
  });

  it("replaces the digit of a filled box", async () => {
    const user = userEvent.setup();
    render(<Harness initial="295" />);
    await user.click(box(1));
    await user.keyboard("7");
    expect(fullValue()).toHaveValue("275");
    expect(box(2)).toHaveFocus();
  });

  it("Backspace on an empty box moves back and clears the previous digit", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(box(0));
    await user.keyboard("295");
    expect(box(3)).toHaveFocus();
    await user.keyboard("{Backspace}");
    expect(fullValue()).toHaveValue("29");
    expect(box(2)).toHaveFocus();
  });

  it("Backspace on a filled box clears it and stays", async () => {
    const user = userEvent.setup();
    render(<Harness initial="295" />);
    await user.click(box(2));
    await user.keyboard("{Backspace}");
    expect(fullValue()).toHaveValue("29");
    expect(box(2)).toHaveFocus();
  });

  it("Backspace on the first empty box does nothing", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    await user.click(box(0));
    await user.keyboard("{Backspace}");
    expect(onChange).not.toHaveBeenCalled();
    expect(box(0)).toHaveFocus();
  });

  it("clicking past the end focuses the first empty box", async () => {
    const user = userEvent.setup();
    render(<Harness initial="29" />);
    await user.click(box(9));
    expect(box(2)).toHaveFocus();
  });

  it("paste of a spaced Arabic-digit number fills all 14 boxes with Western digits", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(box(0));
    await user.paste("٢٩٥٠١٢٣ ٠١٠١٢٣٤");
    expect(fullValue()).toHaveValue("29501230101234");
    expect(boxes().map((b) => (b as HTMLInputElement).value).join("")).toBe("29501230101234");
    expect(box(13)).toHaveFocus();
  });

  it("a full-length paste into any box replaces the whole number", async () => {
    const user = userEvent.setup();
    render(<Harness initial="111" />);
    await user.click(box(2));
    await user.paste("29501230101234");
    expect(fullValue()).toHaveValue("29501230101234");
  });

  it("a partial paste fills from the focused box", async () => {
    const user = userEvent.setup();
    render(<Harness initial="29" />);
    await user.click(box(2));
    await user.paste("5-01");
    expect(fullValue()).toHaveValue("29501");
    expect(box(5)).toHaveFocus();
  });

  it("never exceeds 14 digits", async () => {
    const user = userEvent.setup();
    render(<Harness initial="2950123010123" />);
    await user.click(box(13));
    await user.keyboard("45");
    expect(fullValue()).toHaveValue("29501230101235");
  });

  it("arrow keys move between boxes in visual LTR order", async () => {
    const user = userEvent.setup();
    render(<Harness initial="29501" />);
    await user.click(box(2));
    await user.keyboard("{ArrowRight}");
    expect(box(3)).toHaveFocus();
    await user.keyboard("{ArrowLeft}{ArrowLeft}");
    expect(box(1)).toHaveFocus();
  });

  it("readOnly prevents edits", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness initial="295" readOnly onChange={onChange} />);
    await user.click(box(1));
    await user.keyboard("7{Backspace}");
    await user.paste("29501230101234");
    expect(onChange).not.toHaveBeenCalled();
    expect(box(0)).toHaveAttribute("readonly");
  });

  it("shows the error and marks the boxes invalid", () => {
    render(<NidInput label={LABEL} value="" onChange={() => {}} error="الرقم القومي غير صحيح" />);
    const group = screen.getByRole("group", { name: LABEL });
    expect(group).toHaveAccessibleDescription(/الرقم القومي غير صحيح/);
    expect(box(0)).toHaveAttribute("aria-invalid", "true");
  });

  it("handles a mobile keyboard that sends the digit without a key event", () => {
    const onChange = vi.fn();
    render(<NidInput label={LABEL} value="" onChange={onChange} />);
    fireEvent.change(box(0), { target: { value: "٣" } });
    expect(onChange).toHaveBeenCalledWith("3");
  });

  it("supports the small size", () => {
    render(<NidInput label={LABEL} value="" onChange={() => {}} size="small" />);
    expect(screen.getByRole("group", { name: LABEL })).toHaveAttribute("data-size", "small");
  });
});
