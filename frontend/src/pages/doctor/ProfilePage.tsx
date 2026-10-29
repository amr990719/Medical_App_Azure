import { zodResolver } from "@hookform/resolvers/zod";
import { useState, type ReactNode } from "react";
import { Controller, useForm } from "react-hook-form";
import { Link } from "react-router";
import { ApiError } from "@/api/client";
import type { ProfilePatch } from "@/api/endpoints/profile";
import type { DoctorProfile, ReferenceData } from "@/api/types";
import { DashedField } from "@/components/form/DashedField";
import { DashedSelect } from "@/components/form/DashedSelect";
import { Button } from "@/components/ui/Button";
import { FullPageStatus } from "@/components/ui/FullPageStatus";
import { Skeleton } from "@/components/ui/Skeleton";
import {
  contactApiField,
  contactSchema,
  type ContactField,
  type ContactInput,
  type ContactValues,
} from "@/features/profile/contactSchema";
import { useProfile, useUpdateProfile } from "@/features/profile/useProfile";
import { useReferenceData } from "@/features/reference/useReferenceData";
import { ar } from "@/i18n/ar";
import { normalizeDigits } from "@/utils/digits";

const L = ar.profile;
const contactFields = Object.keys(contactApiField) as ContactField[];

function contactDefaults(profile: DoctorProfile): ContactInput {
  return {
    phoneNumber: profile.phoneNumber ?? "",
    governorate: profile.governorate ?? "",
    neighborhood: profile.neighborhood ?? "",
    address: profile.address ?? "",
  };
}

function Item({ label, value, ltr = false }: { label: string; value: ReactNode; ltr?: boolean }) {
  const empty = value === null || value === undefined || value === "";
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-sm font-bold text-slate">{label}</dt>
      <dd className="font-semibold text-ink">
        {empty ? (
          <span className="text-muted">{L.notProvided}</span>
        ) : ltr ? (
          <span dir="ltr">{value}</span>
        ) : (
          value
        )}
      </dd>
    </div>
  );
}

function IdentitySummary({ profile, reference }: { profile: DoctorProfile; reference: ReferenceData }) {
  const syndicate = reference.syndicateTypes.find((choice) => choice.value === profile.syndicateType)?.label;
  return (
    <section aria-labelledby="profile-identity" className="mt-6 rounded-xl border border-border bg-white p-5">
      <h2 id="profile-identity" className="text-lg font-extrabold text-charcoal">
        {L.identityTitle}
      </h2>
      <dl className="mt-4 grid gap-4 sm:grid-cols-2">
        <Item label={L.fields.fullName} value={profile.fullName} />
        <Item label={L.fields.email} value={profile.email} ltr />
        <Item label={L.fields.nationalId} value={profile.nationalId} ltr />
        <Item label={L.fields.syndicate} value={syndicate} />
        <Item label={L.fields.subSyndicate} value={profile.subSyndicate} />
        <Item label={L.fields.registrationNumber} value={profile.syndicateRegistrationNumber} ltr />
        <Item label={L.fields.registrationYear} value={profile.syndicateRegistrationYear} ltr />
      </dl>
      <p className="mt-4 text-sm text-slate">
        {L.identityHint}{" "}
        <Link to="/application/new" className="font-bold text-teal underline underline-offset-4">
          {L.editInForm}
        </Link>
      </p>
    </section>
  );
}

function ContactForm({ profile, reference }: { profile: DoctorProfile; reference: ReferenceData }) {
  const update = useUpdateProfile();
  const [formError, setFormError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const {
    control,
    handleSubmit,
    reset,
    setError,
    formState: { dirtyFields, errors, isDirty, isSubmitting },
  } = useForm<ContactInput, unknown, ContactValues>({
    resolver: zodResolver(contactSchema),
    defaultValues: contactDefaults(profile),
  });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    setSaved(false);
    // Only the edited fields: the form autosave may have changed the others meanwhile.
    const changes: ProfilePatch = {};
    for (const field of contactFields) {
      if (dirtyFields[field]) Object.assign(changes, { [contactApiField[field]]: values[field] });
    }
    try {
      const updated = await update.mutateAsync(changes);
      reset(contactDefaults(updated));
      setSaved(true);
    } catch (error) {
      if (!(error instanceof ApiError)) {
        setFormError(ar.errors.unexpected);
        return;
      }
      let mapped = false;
      for (const field of contactFields) {
        const message = error.fields[contactApiField[field]]?.[0];
        if (message) {
          setError(field, { type: "server", message });
          mapped = true;
        }
      }
      if (!mapped) setFormError(error.message);
    }
  });

  const governorates = reference.governorates.map((name) => ({ value: name, label: name }));

  return (
    <section aria-labelledby="profile-contact" className="mt-6 rounded-xl border border-border bg-white p-5">
      <h2 id="profile-contact" className="text-lg font-extrabold text-charcoal">
        {L.contactTitle}
      </h2>
      <form noValidate onSubmit={(event) => void onSubmit(event)} className="mt-4 grid gap-5">
        <Controller
          control={control}
          name="phoneNumber"
          render={({ field }) => (
            <DashedField
              label={L.fields.phone}
              value={field.value}
              onChange={(value) => field.onChange(normalizeDigits(value))}
              onBlur={field.onBlur}
              type="tel"
              dir="ltr"
              inputMode="tel"
              autoComplete="tel"
              maxLength={16}
              error={errors.phoneNumber?.message}
            />
          )}
        />
        <Controller
          control={control}
          name="governorate"
          render={({ field }) => (
            <DashedSelect
              label={L.fields.governorate}
              value={field.value}
              onChange={field.onChange}
              onBlur={field.onBlur}
              options={governorates}
              placeholder={L.fields.governoratePlaceholder}
              error={errors.governorate?.message}
            />
          )}
        />
        <Controller
          control={control}
          name="neighborhood"
          render={({ field }) => (
            <DashedField
              label={L.fields.neighborhood}
              value={field.value}
              onChange={field.onChange}
              onBlur={field.onBlur}
              maxLength={100}
              error={errors.neighborhood?.message}
            />
          )}
        />
        <Controller
          control={control}
          name="address"
          render={({ field }) => (
            <DashedField
              label={L.fields.address}
              value={field.value}
              onChange={field.onChange}
              onBlur={field.onBlur}
              maxLength={300}
              autoComplete="street-address"
              error={errors.address?.message}
            />
          )}
        />

        {formError ? (
          <p role="alert" className="rounded-lg border border-danger/40 bg-danger/5 p-3 font-semibold text-danger">
            {formError}
          </p>
        ) : null}
        {saved && !isDirty ? (
          <p role="status" className="font-semibold text-success">
            {L.saved}
          </p>
        ) : null}

        <div>
          <Button type="submit" disabled={!isDirty || isSubmitting}>
            {isSubmitting ? L.saving : L.save}
          </Button>
        </div>
      </form>
    </section>
  );
}

export function ProfilePage() {
  const profile = useProfile();
  const reference = useReferenceData();
  const loadError = profile.error ?? reference.error;

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6 sm:py-10">
      <h1 className="text-2xl font-extrabold text-charcoal sm:text-3xl">{ar.pages.profile}</h1>
      {loadError ? (
        <FullPageStatus
          isError
          message={loadError.message}
          onRetry={() => {
            void profile.refetch();
            void reference.refetch();
          }}
        />
      ) : profile.data && reference.data ? (
        <>
          <IdentitySummary profile={profile.data} reference={reference.data} />
          <ContactForm profile={profile.data} reference={reference.data} />
        </>
      ) : (
        <div aria-busy="true" className="mt-6 space-y-3">
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-56 w-full" />
        </div>
      )}
    </div>
  );
}
