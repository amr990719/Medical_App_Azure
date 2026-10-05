import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProgressStepper } from "./ProgressStepper";

describe("ProgressStepper", () => {
  it("renders the five wizard steps in order", () => {
    render(<ProgressStepper current={1} completed={new Set()} />);
    const nav = screen.getByRole("navigation", { name: "مراحل الاستمارة" });
    const items = within(nav).getAllByRole("listitem");
    expect(items.map((li) => li.textContent)).toEqual([
      expect.stringContaining("البيانات"),
      expect.stringContaining("المستفيدون"),
      expect.stringContaining("المستندات"),
      expect.stringContaining("الإيصال"),
      expect.stringContaining("المراجعة"),
    ]);
  });

  it("marks the current step with aria-current", () => {
    render(<ProgressStepper current={3} completed={new Set([1, 2])} />);
    const items = screen.getAllByRole("listitem");
    expect(items[2]).toHaveAttribute("aria-current", "step");
    expect(items[0]).not.toHaveAttribute("aria-current");
  });

  it("announces completed, current and upcoming states", () => {
    render(<ProgressStepper current={3} completed={new Set([1, 2])} />);
    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("مكتملة");
    expect(items[2]).toHaveTextContent("الخطوة الحالية");
    expect(items[4]).toHaveTextContent("لم تبدأ");
    expect(items[0]!.dataset.state).toBe("complete");
    expect(items[2]!.dataset.state).toBe("current");
    expect(items[4]!.dataset.state).toBe("upcoming");
  });

  it("hides the step labels below 640px", () => {
    render(<ProgressStepper current={1} completed={new Set()} />);
    const label = screen.getByText("المستفيدون");
    expect(label.className).toContain("hidden");
    expect(label.className).toContain("sm:inline");
  });

  it("a completed current step still reads as current", () => {
    render(<ProgressStepper current={2} completed={new Set([1, 2])} />);
    expect(screen.getAllByRole("listitem")[1]!.dataset.state).toBe("current");
  });
});
