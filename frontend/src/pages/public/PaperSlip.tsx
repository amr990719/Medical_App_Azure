import { ar } from "@/i18n/ar";

// A partly "inked" national ID to suggest the form being filled; purely decorative.
const SAMPLE_DIGITS = ["2", "9", "5", "0", "1", "2", "3"];
const NID_BOXES = 14;

/**
 * The landing hero's illustration: the real header of the union's paper form (PROMPT.md §9.2),
 * drawn with the paper-form styling the doctor will meet inside the app.
 */
export function PaperSlip() {
  return (
    <figure className="relative mx-auto w-full max-w-md select-none">
      {/* The sheet underneath, slightly turned, so the form reads as paper on a desk. */}
      <div aria-hidden className="absolute inset-0 translate-y-3 rotate-2 border-[1.5px] border-paper-line/40 bg-white" />
      <div
        aria-hidden
        className="relative -rotate-1 border-[1.5px] border-paper-line bg-paper p-5 shadow-[6px_8px_0_rgb(26_26_46/0.08)]"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="text-[0.8rem] leading-snug">
            <p className="border-b-[1.5px] border-paper-line pb-1 font-extrabold">{ar.app.union}</p>
            <p className="pt-1 font-bold">{ar.app.project}</p>
          </div>
          <div className="hidden pt-1 text-center text-[0.8rem] leading-snug min-[420px]:block">
            <p className="font-extrabold">{ar.app.formTitle}</p>
            <p className="font-bold">{ar.app.formSubtitle}</p>
          </div>
          <div className="grid h-24 w-[4.6rem] shrink-0 place-items-center border-[1.5px] border-paper-line p-1 text-center text-[0.65rem] font-bold leading-tight">
            {ar.landing.slipPhoto}
          </div>
        </div>
        <div className="mt-5 flex flex-wrap items-center gap-2">
          <span className="text-sm font-bold">{ar.landing.slipNid}</span>
          <span dir="ltr" className="flex gap-0.5">
            {Array.from({ length: NID_BOXES }, (_, index) => (
              <span
                key={index}
                className="grid h-7 w-[1.15rem] place-items-center border-[1.5px] border-paper-line text-sm font-bold text-ink sm:w-5"
              >
                {SAMPLE_DIGITS[index] ?? ""}
              </span>
            ))}
          </span>
        </div>
        <div className="mt-4 space-y-3">
          <div className="h-5 border-b-[1.5px] border-dashed border-paper-line" />
          <div className="flex gap-3">
            <div className="h-5 flex-[2] border-b-[1.5px] border-dashed border-paper-line" />
            <div className="h-5 flex-1 border-b-[1.5px] border-dashed border-paper-line" />
          </div>
        </div>
      </div>
      <figcaption className="mt-5 text-center text-sm text-muted">{ar.landing.slipCaption}</figcaption>
    </figure>
  );
}
