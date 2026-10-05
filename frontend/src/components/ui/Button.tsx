import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cx } from "@/utils/cx";
import { buttonClasses, type ButtonSize, type ButtonVariant } from "./buttonClasses";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", className, type = "button", ...rest },
  ref,
) {
  return <button ref={ref} type={type} className={cx(buttonClasses(variant, size), className)} {...rest} />;
});
