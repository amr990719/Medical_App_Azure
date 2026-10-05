import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { DashedField } from "./DashedField";

function Harness(props: { numeric?: boolean; maxLength?: number; onChange?: (v: string) => void }) {
  const [value, setValue] = useState("");
  return (
    <DashedField
      label="سنة قيد النقابة :"
      value={value}
      numeric={props.numeric}
      maxLength={props.maxLength}
      onChange={(next) => {
        setValue(next);
        props.onChange?.(next);
      }}
    />
  );
}

describe("DashedField", () => {
  it("associates the label with a dashed-underline input", () => {
    render(<DashedField label="أسم العضو :" value="" onChange={() => {}} />);
    const input = screen.getByLabelText("أسم العضو :");
    expect(input.className).toContain("border-dashed");
  });

  it("numeric fields are LTR, numeric keyboard, and normalize Arabic digits", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness numeric maxLength={4} onChange={onChange} />);
    const input = screen.getByLabelText("سنة قيد النقابة :");
    expect(input).toHaveAttribute("dir", "ltr");
    expect(input).toHaveAttribute("inputmode", "numeric");
    await user.type(input, "٢٠a٢٦٩");
    expect(input).toHaveValue("2026");
    expect(onChange).toHaveBeenLastCalledWith("2026");
  });

  it("shows the error inline and marks the input invalid", () => {
    render(<DashedField label="المحمول :" value="" onChange={() => {}} error="رقم الهاتف غير صحيح" />);
    const input = screen.getByLabelText("المحمول :");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription("رقم الهاتف غير صحيح");
  });

  it("passes dir and readOnly through", () => {
    render(<DashedField label="البريد :" value="a@b.c" onChange={() => {}} dir="ltr" readOnly />);
    const input = screen.getByLabelText("البريد :");
    expect(input).toHaveAttribute("dir", "ltr");
    expect(input).toHaveAttribute("readonly");
  });

  it("stacks the label above the input on narrow screens", () => {
    const { container } = render(<DashedField label="الحي :" value="" onChange={() => {}} />);
    expect((container.firstChild as HTMLElement).className).toMatch(/flex-col.*md:flex-row/);
  });
});
