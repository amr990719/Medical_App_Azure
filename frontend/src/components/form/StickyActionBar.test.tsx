import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StickyActionBar } from "./StickyActionBar";

describe("StickyActionBar", () => {
  it("renders the start and end slots in a fixed bottom toolbar", () => {
    render(<StickyActionBar label="إجراءات" start={<button>تسجيل الخروج</button>} end={<button>متابعة</button>} />);
    const bar = screen.getByRole("toolbar", { name: "إجراءات" });
    expect(bar.className).toContain("fixed");
    expect(bar.className).toContain("bottom-0");
    expect(screen.getByText("تسجيل الخروج").closest("[data-slot]")).toHaveAttribute("data-slot", "start");
    expect(screen.getByText("متابعة").closest("[data-slot]")).toHaveAttribute("data-slot", "end");
  });
});
