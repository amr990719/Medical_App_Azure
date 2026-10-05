import { Navigate, type RouteObject } from "react-router";
import { RequireRole } from "@/auth/RequireRole";
import { ar } from "@/i18n/ar";
import { AdminLayout } from "@/layouts/AdminLayout";
import { DoctorLayout } from "@/layouts/DoctorLayout";
import { PublicLayout } from "@/layouts/PublicLayout";
import { NewApplicationPage } from "@/pages/application/NewApplicationPage";
import { DashboardPage } from "@/pages/doctor/DashboardPage";
import { PlaceholderPage } from "@/pages/PlaceholderPage";
import { LandingPage } from "@/pages/public/LandingPage";
import { NotFoundPage } from "@/pages/public/NotFoundPage";
import { SignedOutPage } from "@/pages/public/SignedOutPage";

const placeholder = (path: string, title: string): RouteObject => ({
  path,
  element: <PlaceholderPage title={title} />,
});

/** Every route of PROMPT.md §8. Pages built in Sessions 5–6 are placeholders for now. */
export const routes: RouteObject[] = [
  {
    element: <PublicLayout />,
    children: [
      { index: true, element: <LandingPage /> },
      { path: "signed-out", element: <SignedOutPage /> },
    ],
  },
  {
    element: <RequireRole role="DOCTOR" />,
    children: [
      {
        element: <DoctorLayout />,
        children: [
          { path: "dashboard", element: <DashboardPage /> },
          placeholder("profile", ar.pages.profile),
          { path: "application/new", element: <NewApplicationPage /> },
          placeholder("application/:id", ar.pages.application),
          placeholder("application/:id/form", ar.pages.form),
          placeholder("application/:id/payment", ar.pages.payment),
          placeholder("application/:id/review", ar.pages.review),
          placeholder("application/:id/status", ar.pages.status),
          placeholder("application/:id/print", ar.pages.print),
        ],
      },
    ],
  },
  {
    path: "admin",
    element: <RequireRole role="ADMIN" />,
    children: [
      {
        element: <AdminLayout />,
        children: [
          { index: true, element: <Navigate to="dashboard" replace /> },
          placeholder("dashboard", ar.admin.welcome),
          placeholder("applications", ar.nav.adminApplications),
          placeholder("applications/:id", ar.pages.adminApplication),
          placeholder("applications/:id/print", ar.pages.print),
          placeholder("doctors", ar.nav.adminDoctors),
          placeholder("doctors/:id", ar.pages.adminDoctor),
          placeholder("fee-schedules", ar.nav.adminFeeSchedules),
        ],
      },
    ],
  },
  {
    element: <PublicLayout />,
    children: [{ path: "*", element: <NotFoundPage /> }],
  },
];
