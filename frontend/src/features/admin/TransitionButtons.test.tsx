import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ApplicationStatus, PaymentStatus } from "@/api/types";
import { renderWithProviders } from "@/test/render";
import { TransitionButtons } from "./TransitionButtons";

function renderButtons(allowed: ApplicationStatus[], status: ApplicationStatus, paymentStatus: PaymentStatus = "PENDING_REVIEW") {
  const onSelect = vi.fn();
  const view = renderWithProviders(
    <TransitionButtons allowed={allowed} status={status} paymentStatus={paymentStatus} onSelect={onSelect} />,
  );
  return { ...view, onSelect };
}

const buttonLabels = () => screen.queryAllByRole("button").map((b) => b.textContent?.trim());

describe("TransitionButtons", () => {
  it("renders one button per allowed target, in the review order", () => {
    renderButtons(["REJECTED", "NEEDS_CORRECTION", "APPROVED"], "UNDER_REVIEW", "CONFIRMED");
    expect(buttonLabels()).toEqual(["قبول الطلب", "طلب تصحيح", "رفض الطلب"]);
  });

  it("renders nothing to click for a final status", () => {
    renderButtons([], "APPROVED", "CONFIRMED");
    expect(buttonLabels()).toEqual([]);
    expect(screen.getByText("لا توجد إجراءات متاحة لهذه الحالة.")).toBeInTheDocument();
  });

  it("ignores targets the admin cannot choose (SUBMITTED, DRAFT)", () => {
    renderButtons(["SUBMITTED", "DRAFT", "UNDER_REVIEW"] as ApplicationStatus[], "SUBMITTED");
    expect(buttonLabels()).toEqual(["بدء المراجعة"]);
  });

  it("reports the chosen target", async () => {
    const { user, onSelect } = renderButtons(["UNDER_REVIEW"], "SUBMITTED");
    await user.click(screen.getByRole("button", { name: "بدء المراجعة" }));
    expect(onSelect).toHaveBeenCalledWith("UNDER_REVIEW");
  });

  it("hints that approval waits for the payment while under review", () => {
    renderButtons(["NEEDS_CORRECTION", "REJECTED"], "UNDER_REVIEW", "PENDING_REVIEW");
    expect(screen.getByText("يجب تأكيد الدفع قبل قبول الطلب.")).toBeInTheDocument();
  });
});
