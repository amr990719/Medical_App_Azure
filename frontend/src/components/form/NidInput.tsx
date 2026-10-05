import { ar, t } from "@/i18n/ar";
import { digitsOnly } from "@/utils/digits";
import { BoxInput, type BoxSize } from "./BoxInput";

export const NID_LENGTH = 14;

// Century | birth date (6) | governorate (2) | serial (4) | check digit — PROMPT.md §13.
const NID_SEGMENT_STARTS = [1, 7, 9, 13] as const;

export interface NidInputProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  size?: BoxSize;
  error?: string;
  readOnly?: boolean;
  name?: string;
  className?: string;
}

/** 14-box national ID input: Western digits only (Arabic digits normalized), LTR. */
export function NidInput(props: NidInputProps) {
  return (
    <BoxInput
      {...props}
      length={NID_LENGTH}
      sanitize={digitsOnly}
      inputMode="numeric"
      segmentStarts={NID_SEGMENT_STARTS}
      boxLabel={(index, total) => t(ar.nid.digit, { index, total })}
    />
  );
}
