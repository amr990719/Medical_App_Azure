import type { ReactNode } from "react";
import { BeneficiaryTable } from "@/features/beneficiaries/BeneficiaryTable";
import { cx } from "@/utils/cx";
import { AttachmentsPanel } from "./AttachmentsPanel";
import { DeclarationSection } from "./DeclarationSection";
import { FormHeader } from "./FormHeader";
import { MemberSection } from "./MemberSection";

/**
 * The A4 sheet (PROMPT.md §9.2–9.7): header and photo, member grid, beneficiaries table,
 * declaration. "edit" adds the attachments panel; "print" forces the table layout.
 */
export function PaperForm({
  mode = "edit",
  banner,
  className,
}: {
  mode?: "edit" | "review" | "print";
  /** Reference number / submission date line on printed copies. */
  banner?: ReactNode;
  className?: string;
}) {
  return (
    <article
      className={cx(
        "paper-sheet space-y-6 border border-border-hover bg-paper p-3 shadow-[0_1px_2px_rgb(0_0_0/0.06),0_8px_24px_-12px_rgb(26_26_46/0.25)] sm:p-6 md:p-8",
        className,
      )}
    >
      {banner}
      <FormHeader />
      {mode === "edit" ? <AttachmentsPanel /> : null}
      <MemberSection />
      <BeneficiaryTable layout={mode === "print" ? "table" : "auto"} />
      <DeclarationSection />
    </article>
  );
}
