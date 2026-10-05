import { ar } from "@/i18n/ar";
import { SignedInLayout } from "./SignedInLayout";

const NAV = [
  { to: "/dashboard", label: ar.nav.dashboard },
  { to: "/profile", label: ar.nav.profile },
] as const;

export function DoctorLayout() {
  return <SignedInLayout home="/dashboard" nav={NAV} variant="doctor" />;
}
