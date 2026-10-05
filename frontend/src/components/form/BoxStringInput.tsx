import { ar, t } from "@/i18n/ar";
import { normalizeDigits } from "@/utils/digits";
import { BoxInput, type BoxSize } from "./BoxInput";

export interface BoxStringInputProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  /** Number of boxes on the paper form (the e-mail row has 26). */
  length?: number;
  size?: BoxSize;
  error?: string;
  readOnly?: boolean;
  name?: string;
  className?: string;
}

const sanitizeText = (raw: string) => normalizeDigits(raw).replace(/\s+/g, "");

/** Free-text boxes (e-mail on the paper form), LTR, wrapping on small screens. */
export function BoxStringInput({ length = 26, ...props }: BoxStringInputProps) {
  return (
    <BoxInput
      {...props}
      length={length}
      sanitize={sanitizeText}
      inputMode="email"
      wrap
      boxLabel={(index, total) => t(ar.boxString.character, { index, total })}
    />
  );
}
