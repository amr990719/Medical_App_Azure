import { cx } from "@/utils/cx";

export type ButtonVariant = "primary" | "outline" | "ghost" | "danger";
export type ButtonSize = "md" | "lg";

const VARIANTS: Record<ButtonVariant, string> = {
  // Banana is reserved for the one primary action of a screen (§7.2).
  primary:
    "bg-banana text-charcoal hover:bg-banana-deep shadow-[inset_0_-2px_0_rgb(0_0_0/0.12)] disabled:bg-border disabled:text-muted disabled:shadow-none",
  outline:
    "border-2 border-teal text-teal-deep bg-white hover:bg-teal-light disabled:border-border disabled:text-muted",
  ghost: "text-slate hover:bg-smoke hover:text-charcoal disabled:text-muted",
  danger: "bg-danger text-white hover:bg-danger/85 disabled:bg-border disabled:text-muted",
};

const SIZES: Record<ButtonSize, string> = {
  md: "min-h-10 px-4 text-sm",
  lg: "min-h-12 px-6 text-base",
};

/** Button look, shared by <Button> and by links styled as buttons. */
export const buttonClasses = (variant: ButtonVariant = "primary", size: ButtonSize = "md") =>
  cx(
    "inline-flex items-center justify-center gap-2 rounded-lg font-bold transition-colors",
    "disabled:cursor-not-allowed",
    VARIANTS[variant],
    SIZES[size],
  );
