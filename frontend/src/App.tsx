import { useState } from "react";
import { createBrowserRouter, RouterProvider } from "react-router";
import { AppProviders } from "./AppProviders";
import { createQueryClient } from "./queryClient";
import { routes } from "./router";

const router = createBrowserRouter(routes);

export function App() {
  const [queryClient] = useState(createQueryClient);
  return (
    <AppProviders queryClient={queryClient}>
      <RouterProvider router={router} />
    </AppProviders>
  );
}
