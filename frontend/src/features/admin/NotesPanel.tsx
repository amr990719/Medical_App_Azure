import { useId, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { ar } from "@/i18n/ar";
import { formatDate } from "@/utils/format";
import { useAddNote, useAdminNotes } from "./queries";

/** Internal notes: admin-only, never on a doctor endpoint (PROMPT.md §24, §44). */
export function NotesPanel({ applicationId }: { applicationId: string }) {
  const titleId = useId();
  const inputId = useId();
  const notes = useAdminNotes(applicationId);
  const add = useAddNote(applicationId);
  const [body, setBody] = useState("");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const text = body.trim();
    if (!text) return;
    add.mutate(text, { onSuccess: () => setBody("") });
  };

  return (
    <section aria-labelledby={titleId} className="space-y-3 rounded-xl border border-border bg-white p-5">
      <div>
        <h2 id={titleId} className="text-lg font-extrabold text-charcoal">
          {ar.admin.notes.title}
        </h2>
        <p className="text-xs text-muted">{ar.admin.notes.hint}</p>
      </div>
      {notes.isLoading ? (
        <Skeleton className="h-10 w-full" />
      ) : notes.error ? (
        <p role="alert" className="text-sm text-danger">
          {notes.error.message}
        </p>
      ) : notes.data && notes.data.length > 0 ? (
        <ol className="space-y-2">
          {notes.data.map((note) => (
            <li key={note.id} className="rounded-lg bg-smoke p-3">
              <p className="whitespace-pre-line text-sm text-charcoal">{note.body}</p>
              <p className="mt-1 text-xs text-muted">
                <bdi dir="ltr">{note.authorEmail}</bdi> · {formatDate(note.createdAt)}
              </p>
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-sm text-slate">{ar.admin.notes.empty}</p>
      )}
      <form onSubmit={submit} className="space-y-2">
        <label htmlFor={inputId} className="text-sm font-bold text-charcoal">
          {ar.admin.notes.label}
        </label>
        <textarea
          id={inputId}
          rows={3}
          value={body}
          onChange={(event) => setBody(event.target.value)}
          className="w-full rounded-lg border border-border-hover bg-white p-2.5 text-sm focus:border-teal"
        />
        {add.error ? (
          <p role="alert" className="text-sm font-semibold text-danger">
            {add.error.message}
          </p>
        ) : null}
        <Button type="submit" variant="outline" disabled={add.isPending || !body.trim()}>
          {ar.admin.notes.add}
        </Button>
      </form>
    </section>
  );
}
