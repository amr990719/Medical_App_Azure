import { useId, useRef } from "react";
import { RadioBoxGroup } from "@/components/form/RadioBoxGroup";
import { Icon } from "@/components/ui/Icon";
import { useUploadDocument } from "@/features/documents/useUploadDocument";
import { ar } from "@/i18n/ar";
import { cx } from "@/utils/cx";
import { useApplicationForm } from "./context";

/** Member photo box (PERSONAL_PHOTO, image only), clickable to upload, shows the stored photo. */
function PhotoBox() {
  const { application, memberDocuments, readOnly, documentsChanged } = useApplicationForm();
  const inputRef = useRef<HTMLInputElement>(null);
  const errorId = useId();
  const photo = memberDocuments.PERSONAL_PHOTO;
  const upload = useUploadDocument({
    applicationId: application?.id ?? "",
    documentType: "PERSONAL_PHOTO",
    imagesOnly: true,
    onUploaded: documentsChanged,
  });
  const interactive = !readOnly && upload.ready && !upload.isPending;
  const P = ar.form.photo;

  return (
    <div className="flex flex-col items-center gap-1">
      <button
        type="button"
        disabled={!interactive}
        onClick={() => inputRef.current?.click()}
        aria-label={photo ? P.replace : P.upload}
        aria-describedby={upload.error ? errorId : undefined}
        className={cx(
          "relative grid h-36 w-28 shrink-0 place-items-center overflow-hidden border-[1.5px] border-paper-line bg-paper",
          interactive ? "cursor-pointer hover:bg-banana-light" : "cursor-default",
        )}
      >
        {photo ? (
          <img src={photo.contentUrl} alt={P.alt} className="size-full object-cover" />
        ) : (
          <span className="flex flex-col items-center text-sm font-bold leading-6 text-charcoal">
            {P.placeholder.map((line) => (
              <span key={line}>{line}</span>
            ))}
            {!readOnly ? <Icon name="upload" className="mt-1 size-4 text-muted print:hidden" /> : null}
          </span>
        )}
        {upload.isPending ? (
          <span className="absolute inset-x-0 bottom-0 bg-charcoal/75 py-0.5 text-center text-xs text-white">
            {P.uploading} {upload.progress}٪
          </span>
        ) : null}
      </button>
      <input
        ref={inputRef}
        type="file"
        className="sr-only"
        tabIndex={-1}
        aria-hidden
        accept={upload.accept}
        onChange={(event) => {
          upload.select(event.target.files?.[0]);
          event.target.value = "";
        }}
      />
      {upload.error ? (
        <p id={errorId} role="alert" className="max-w-28 text-center text-xs font-semibold text-danger">
          {upload.error}
        </p>
      ) : null}
    </div>
  );
}

/** The paper form's header (PROMPT.md §9.2): union, title, application type, photo box. */
export function FormHeader() {
  const { state, reference, readOnly, updateField } = useApplicationForm();
  if (!state || !reference) return null;

  return (
    <header className="grid grid-cols-[1fr_auto] items-start gap-4 border-b-[1.5px] border-paper-line pb-5 md:grid-cols-[1fr_1.4fr_auto]">
      <div className="min-w-0">
        <p className="text-base font-extrabold text-charcoal md:text-lg">{ar.app.union}</p>
        <div className="my-1.5 h-[1.5px] w-40 max-w-full bg-paper-line" />
        <p className="text-sm font-bold text-slate">{ar.app.project}</p>
      </div>
      <div className="col-span-2 row-start-2 flex flex-col items-center gap-3 text-center md:col-span-1 md:row-start-auto">
        <div>
          <h1 className="text-lg font-extrabold text-charcoal md:text-xl">{ar.app.formTitle}</h1>
          <p className="font-bold text-charcoal">{ar.app.formSubtitle}</p>
        </div>
        <RadioBoxGroup
          label={ar.form.applicationType}
          name="applicationType"
          options={reference.applicationTypes}
          value={state.applicationType}
          onChange={(value) => updateField("applicationType", value)}
          disabled={readOnly}
          className="items-center"
        />
      </div>
      <PhotoBox />
    </header>
  );
}
