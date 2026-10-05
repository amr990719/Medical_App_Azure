import { QueryClient } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { createMemoryRouter, MemoryRouter, RouterProvider } from "react-router";
import { toCamel } from "@/api/case";
import { queryKeys } from "@/api/keys";
import { AppProviders } from "@/AppProviders";
import { routes } from "@/router";
import { apiReferenceData } from "./fixtures";

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity, staleTime: 0 },
      mutations: { retry: false },
    },
  });
}

/** Render the whole app (real route table, guards, layouts) at `path`. */
export function renderApp(path: string) {
  const queryClient = createTestQueryClient();
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const user = userEvent.setup();
  const view = render(
    <AppProviders queryClient={queryClient}>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  return { ...view, router, queryClient, user };
}

/** Render one component with a query client (reference data pre-seeded) and a router context. */
export function renderWithProviders(ui: ReactElement, { seedReferenceData = true } = {}) {
  const queryClient = createTestQueryClient();
  if (seedReferenceData) {
    queryClient.setQueryData(queryKeys.referenceData, toCamel(apiReferenceData));
  }
  const user = userEvent.setup();
  const view = render(
    <AppProviders queryClient={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </AppProviders>,
  );
  return { ...view, queryClient, user };
}
