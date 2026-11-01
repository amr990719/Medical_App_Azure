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

  it("places the dues request right after طلب تصحيح when the server allows it", async () => {
    const onRequestDues = vi.fn();
    const { user } = renderWithProviders(
      <TransitionButtons
        allowed={["REJECTED", "NEEDS_CORRECTION", "APPROVED"]}
        status="UNDER_REVIEW"
        paymentStatus="CONFIRMED"
        onSelect={vi.fn()}
        canRequestDues
        onRequestDues={onRequestDues}
      />,
    );
    expect(buttonLabels()).toEqual(["قبول الطلب", "طلب تصحيح", "طلب سداد مستحقات نقابية", "رفض الطلب"]);
    await user.click(screen.getByRole("button", { name: "طلب سداد مستحقات نقابية" }));
    expect(onRequestDues).toHaveBeenCalledOnce();
  });

  it("hides the dues request when the server does not allow it", () => {
    renderWithProviders(
      <TransitionButtons
        allowed={[]}
        status="APPROVED"
        paymentStatus="CONFIRMED"
        onSelect={vi.fn()}
        canRequestDues={false}
        onRequestDues={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: "طلب سداد مستحقات نقابية" })).not.toBeInTheDocument();
  });

  it("explains that outstanding dues block the approval", () => {
    renderWithProviders(
      <TransitionButtons
        allowed={["NEEDS_CORRECTION", "REJECTED"]}
        status="UNDER_REVIEW"
        paymentStatus="CONFIRMED"
        onSelect={vi.fn()}
        outstandingDues={2}
      />,
    );
    expect(screen.getByText("لا يمكن قبول الطلب قبل تأكيد سداد المستحقات النقابية المطلوبة (2).")).toBeInTheDocument();
    expect(screen.queryByText("يجب تأكيد الدفع قبل قبول الطلب.")).not.toBeInTheDocument();
  });
});
