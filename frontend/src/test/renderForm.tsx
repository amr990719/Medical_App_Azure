import { screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { ApplicationFormProvider } from "@/features/application-form/ApplicationFormProvider";
import {
  apiApplication,
  apiProfile,
  draftHandlers,
  type ApiApplication,
  type ApiProfile,
} from "./fixtures";
import { renderWithProviders } from "./render";
import { server } from "./server";

export const FAST_DRAFT = { debounceMs: 20, retryDelays: [5, 10, 20] };

/** Render `ui` inside a live ApplicationFormProvider for `app` (MSW serves app/profile/fees/validation). */
export async function renderInForm(
  ui: ReactElement,
  { app = apiApplication(), profile = apiProfile() }: { app?: ApiApplication; profile?: ApiProfile } = {},
) {
  server.use(
    draftHandlers.application(app),
    draftHandlers.profile(profile),
    draftHandlers.fees(app.id),
    draftHandlers.validation(app.id),
  );
  const view = renderWithProviders(
    <ApplicationFormProvider applicationId={app.id} options={FAST_DRAFT}>
      <div data-testid="form-ready-probe">{ui}</div>
    </ApplicationFormProvider>,
  );
  await waitFor(() => expect(screen.getByTestId("form-ready-probe").childElementCount).toBeGreaterThan(0));
  return view;
}
