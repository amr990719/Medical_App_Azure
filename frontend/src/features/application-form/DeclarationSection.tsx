import { useId } from "react";
import { ar } from "@/i18n/ar";
import { cx } from "@/utils/cx";
import { useApplicationForm } from "./context";
import { useMemberError } from "./inlineErrors";

const D = ar.form.declaration;

/**
 * `إقــــــــرار` (owner wording of 2026-10-28): the declarant's name on the dotted line of the
 * first sentence, then the acceptance paragraph. The text wraps naturally on narrow screens.
 */
export function DeclarationSection() {
  const titleId = useId();
  const errorId = useId();
  const { state, readOnly, updateField } = useApplicationForm();
  const error = useMemberError("declarationName");
  if (!state) return null;

  return (
    <section aria-labelledby={titleId} className="border-t-[1.5px] border-paper-line pt-5">
      <h2 id={titleId} className="mb-3 text-center text-xl font-extrabold text-charcoal">
        {D.title}
      </h2>
      <div className="space-y-2 text-start leading-9 text-charcoal md:text-justify">
        <p>
          {D.before}{" "}
          <input
            aria-label={D.nameLabel}
            value={state.declarationName}
            readOnly={readOnly}
            dir="auto"
            maxLength={200}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? errorId : undefined}
            onChange={(event) => updateField("declarationName", event.target.value)}
            className={cx(
              "mx-1 inline-block w-full max-w-72 border-0 border-b-2 border-dotted bg-transparent px-1 text-center align-baseline font-bold text-ink outline-none print:hidden",
              "focus:border-solid focus:border-ink focus:bg-banana-light/60",
              error ? "border-danger" : "border-paper-line",
            )}
          />
          {/* The input would clip a long name on paper: print the name itself, on the dotted line. */}
          <span
            data-print-value
            aria-hidden
            dir="auto"
            className="mx-1 hidden border-b-2 border-dotted border-paper-line px-1 font-bold text-ink print:inline"
          >
            {state.declarationName}
          </span>{" "}
          {D.after}
        </p>
        {error ? (
          <p id={errorId} className="text-sm font-semibold leading-6 text-danger">
            {error}
          </p>
        ) : null}
        <p>{D.closing}</p>
      </div>
    </section>
  );
}
