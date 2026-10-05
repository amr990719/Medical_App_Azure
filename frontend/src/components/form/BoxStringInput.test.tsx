import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { BoxStringInput } from "./BoxStringInput";

const LABEL = "البريد الالكتروني";

function Harness(props: { initial?: string; readOnly?: boolean; onChange?: (v: string) => void }) {
  const [value, setValue] = useState(props.initial ?? "");
  return (
    <BoxStringInput
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

const boxes = () => screen.getAllByRole("textbox", { name: /^الحرف \d+ من 26$/ });
const box = (index: number) => boxes()[index] as HTMLInputElement;
const fullValue = () => screen.getByRole("textbox", { name: LABEL });

describe("BoxStringInput", () => {
  it("renders 26 LTR boxes by default in a labelled, wrapping group", () => {
    render(<Harness />);
    const group = screen.getByRole("group", { name: LABEL });
    expect(group).toHaveAttribute("dir", "ltr");
    expect(group.className).toContain("flex-wrap");
    expect(boxes()).toHaveLength(26);
  });

  it("honours a custom length", () => {
    render(<BoxStringInput label={LABEL} value="" onChange={() => {}} length={10} />);
    expect(screen.getAllByRole("textbox", { name: /^الحرف \d+ من 10$/ })).toHaveLength(10);
  });

  it("exposes the whole value through one labelled input", () => {
    render(<Harness initial="doctor@dev.local" />);
    expect(fullValue()).toHaveValue("doctor@dev.local");
  });

  it("types free text and auto-advances", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(box(0));
    await user.keyboard("a.b@x");
    expect(fullValue()).toHaveValue("a.b@x");
    expect(box(5)).toHaveFocus();
  });

  it("normalizes Arabic digits and drops whitespace", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(box(0));
    await user.keyboard("d ٢٠");
    expect(fullValue()).toHaveValue("d20");
  });

  it("paste fills the boxes", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(box(0));
    await user.paste(" doctor١@dev.local ");
    expect(fullValue()).toHaveValue("doctor1@dev.local");
    expect(box(16)).toHaveValue("l");
  });

  it("paste is truncated to the box count", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(box(0));
    await user.paste("a".repeat(40));
    expect(fullValue()).toHaveValue("a".repeat(26));
  });

  it("Backspace on an empty box moves back and clears", async () => {
    const user = userEvent.setup();
    render(<Harness initial="ab" />);
    await user.click(box(2));
    await user.keyboard("{Backspace}");
    expect(fullValue()).toHaveValue("a");
    expect(box(1)).toHaveFocus();
  });

  it("readOnly prevents edits", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness initial="ab" readOnly onChange={onChange} />);
    await user.click(box(0));
    await user.keyboard("z{Backspace}");
    expect(onChange).not.toHaveBeenCalled();
  });
});
