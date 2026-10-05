import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("shows the label with the §7.3 colours of the status", () => {
    render(<StatusBadge status="SUBMITTED" label="مقدم" />);
    const badge = screen.getByText("مقدم").closest("[data-status]")!;
    expect(badge).toHaveAttribute("data-status", "SUBMITTED");
    expect(badge.className).toContain("bg-status-submitted-bg");
    expect(badge.className).toContain("text-status-submitted-fg");
  });

  it("has a pulsing dot while under review", () => {
    render(<StatusBadge status="UNDER_REVIEW" label="قيد المراجعة" />);
    const badge = screen.getByText("قيد المراجعة").closest("[data-status]")!;
    expect(badge.querySelector("[data-pulse]")).not.toBeNull();
  });

  it("has a check icon when approved and no pulse", () => {
    render(<StatusBadge status="APPROVED" label="مقبول" />);
    const badge = screen.getByText("مقبول").closest("[data-status]")!;
    expect(badge.querySelector("svg[data-icon='check']")).not.toBeNull();
    expect(badge.querySelector("[data-pulse]")).toBeNull();
  });

  it.each([
    ["DRAFT", "draft"],
    ["NEEDS_CORRECTION", "correction"],
    ["REJECTED", "rejected"],
  ] as const)("maps %s to its colour token", (status, token) => {
    render(<StatusBadge status={status} label={status} />);
    expect(screen.getByText(status).closest("[data-status]")!.className).toContain(`bg-status-${token}-bg`);
  });
});
