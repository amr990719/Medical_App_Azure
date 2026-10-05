import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { Modal } from "./Modal";

function Harness({ onClose }: { onClose?: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>فتح</button>
      <Modal
        open={open}
        title="مستندات المستفيد: سارة"
        onClose={() => {
          setOpen(false);
          onClose?.();
        }}
        footer={<button>حفظ وإغلاق</button>}
      >
        <input aria-label="أول حقل" />
      </Modal>
    </>
  );
}

describe("Modal", () => {
  it("is a labelled modal dialog", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByText("فتح"));
    const dialog = screen.getByRole("dialog", { name: "مستندات المستفيد: سارة" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
  });

  it("moves focus inside on open", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByText("فتح"));
    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true);
  });

  it("closes on Escape and returns focus to the opener", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    await user.click(screen.getByText("فتح"));
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByText("فتح")).toHaveFocus();
  });

  it("traps Tab inside the dialog", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByText("فتح"));
    const dialog = screen.getByRole("dialog");
    for (let i = 0; i < 6; i += 1) {
      await user.tab();
      expect(dialog.contains(document.activeElement)).toBe(true);
    }
    await user.tab({ shift: true });
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it("has a labelled close button", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    await user.click(screen.getByText("فتح"));
    await user.click(screen.getByRole("button", { name: "إغلاق" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("renders nothing when closed", () => {
    render(<Harness />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
