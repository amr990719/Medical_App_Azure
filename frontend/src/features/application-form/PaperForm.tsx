import { BeneficiaryTable } from "@/features/beneficiaries/BeneficiaryTable";
import { cx } from "@/utils/cx";
import { AttachmentsPanel } from "./AttachmentsPanel";
import { DeclarationSection } from "./DeclarationSection";
import { FormHeader } from "./FormHeader";
import { MemberSection } from "./MemberSection";

/**
 * The paper sheet (PROMPT.md §9.2–9.7): header and photo, member grid, beneficiaries table,
 * declaration. "edit" adds the attachments panel.
 */
export function PaperForm({ mode = "edit", className }: { mode?: "edit" | "review"; className?: string }) {
  return (
    <article
      className={cx(
        "paper-sheet space-y-6 border border-border-hover bg-paper p-3 shadow-[0_1px_2px_rgb(0_0_0/0.06),0_8px_24px_-12px_rgb(26_26_46/0.25)] sm:p-6 md:p-8",
        className,
      )}
    >
      <FormHeader />
      {mode === "edit" ? <AttachmentsPanel /> : null}
      <MemberSection />
      <BeneficiaryTable />
      <DeclarationSection />
    </article>
  );
}
