import type { ComponentType } from "react";
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

/** Admin pages load on demand: doctors never download the review UI. */
const admin = (path: string, load: () => Promise<{ Component: ComponentType }>): RouteObject => ({
  path,
  lazy: load,
});

const placeholder = (path: string, title: string): RouteObject => ({
  path,
  element: <PlaceholderPage title={title} />,
});

/**
 * Every route of PROMPT.md §8. Wizard steps (form, payment, review) bring their own frame
 * (top bar + stepper, §9.1) and the print views (doctor and admin) have no chrome.
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
          admin("dashboard", () => import("@/pages/admin/AdminDashboardPage").then((m) => ({ Component: m.AdminDashboardPage }))),
          admin("applications", () =>
            import("@/pages/admin/AdminApplicationsPage").then((m) => ({ Component: m.AdminApplicationsPage })),
          ),
          admin("applications/:id", () =>
            import("@/pages/admin/AdminApplicationDetailPage").then((m) => ({ Component: m.AdminApplicationDetailPage })),
          ),
          admin("doctors", () => import("@/pages/admin/AdminDoctorsPage").then((m) => ({ Component: m.AdminDoctorsPage }))),
          admin("doctors/:id", () =>
            import("@/pages/admin/AdminDoctorDetailPage").then((m) => ({ Component: m.AdminDoctorDetailPage })),
          ),
          admin("fee-schedules", () =>
            import("@/pages/admin/AdminFeeSchedulesPage").then((m) => ({ Component: m.AdminFeeSchedulesPage })),
          ),
        ],
      },
      admin("applications/:id/print", () => import("@/pages/admin/AdminPrintPage").then((m) => ({ Component: m.AdminPrintPage }))),
    ],
  },
  {
    element: <PublicLayout />,
    children: [{ path: "*", element: <NotFoundPage /> }],
  },
];
