import { Navigate, type RouteObject } from "react-router";
import { RequireRole } from "@/auth/RequireRole";
import { ar } from "@/i18n/ar";
import { AdminLayout } from "@/layouts/AdminLayout";
import { DoctorLayout } from "@/layouts/DoctorLayout";
import { PublicLayout } from "@/layouts/PublicLayout";
import { ApplicationRedirectPage } from "@/pages/application/ApplicationRedirectPage";
import { FormPage } from "@/pages/application/FormPage";
import { NewApplicationPage } from "@/pages/application/NewApplicationPage";
import { PaymentPage } from "@/pages/application/PaymentPage";
import { PrintPage } from "@/pages/application/PrintPage";
import { ReviewPage } from "@/pages/application/ReviewPage";
import { StatusPage } from "@/pages/application/StatusPage";
import { DashboardPage } from "@/pages/doctor/DashboardPage";
import { PlaceholderPage } from "@/pages/PlaceholderPage";
import { LandingPage } from "@/pages/public/LandingPage";
import { NotFoundPage } from "@/pages/public/NotFoundPage";
import { SignedOutPage } from "@/pages/public/SignedOutPage";

const placeholder = (path: string, title: string): RouteObject => ({
  path,
  element: <PlaceholderPage title={title} />,
});

/**
 * Every route of PROMPT.md §8. Wizard steps (form, payment, review) bring their own frame
 * (top bar + stepper, §9.1) and the print view has no chrome; admin pages arrive in Session 6.
 */
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
          { path: "application/:id", element: <ApplicationRedirectPage /> },
          { path: "application/:id/status", element: <StatusPage /> },
        ],
      },
      { path: "application/:id/form", element: <FormPage /> },
      { path: "application/:id/payment", element: <PaymentPage /> },
      { path: "application/:id/review", element: <ReviewPage /> },
      { path: "application/:id/print", element: <PrintPage /> },
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
