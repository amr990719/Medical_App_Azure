import { ar } from "@/i18n/ar";
import { SignedInLayout } from "./SignedInLayout";

const NAV = [
  { to: "/admin/dashboard", label: ar.nav.adminDashboard },
  { to: "/admin/applications", label: ar.nav.adminApplications },
  { to: "/admin/doctors", label: ar.nav.adminDoctors },
  { to: "/admin/fee-schedules", label: ar.nav.adminFeeSchedules },
] as const;

export function AdminLayout() {
  return <SignedInLayout home="/admin/dashboard" nav={NAV} variant="admin" />;
}
