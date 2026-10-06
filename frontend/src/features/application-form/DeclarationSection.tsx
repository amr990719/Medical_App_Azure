import { useId } from "react";
import { ar } from "@/i18n/ar";
import { cx } from "@/utils/cx";
import { useApplicationForm } from "./context";
import { useMemberError } from "./inlineErrors";

const D = ar.form.declaration;

/**
 * `إقــــــــرار` exactly as on the paper (PROMPT.md §9.7): the inline dashed name, the red
 * underlined middle paragraph, and the signature block on the end side for the printed copy.
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
              "mx-1 inline-block w-full max-w-72 border-0 border-b-[1.5px] border-dashed bg-transparent px-1 text-center align-baseline font-bold text-ink outline-none",
              "focus:border-solid focus:border-ink focus:bg-banana-light/60",
              error ? "border-danger" : "border-paper-line",
            )}
          />{" "}
          {D.after}
        </p>
        {error ? (
          <p id={errorId} className="text-sm font-semibold leading-6 text-danger">
            {error}
          </p>
        ) : null}
        <p>
          <u className="font-bold decoration-danger decoration-2 underline-offset-[6px]">{D.underlined}</u>
        </p>
        <p>{D.closing}</p>
      </div>
      <div className="mt-6 flex justify-end">
        <div className="w-56 text-center">
          <p className="font-bold text-charcoal">{D.signature}</p>
          <div className="mt-10 border-b-2 border-dotted border-paper-line" />
        </div>
      </div>
    </section>
  );
}
