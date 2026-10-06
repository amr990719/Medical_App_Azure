import {
  useId,
  useRef,
  type ChangeEvent,
  type ClipboardEvent,
  type KeyboardEvent,
} from "react";
import { cx } from "@/utils/cx";

export type BoxSize = "large" | "small";

export interface BoxInputProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  length: number;
  /** Turns raw typed/pasted text into the characters this input accepts. */
  sanitize: (raw: string) => string;
  boxLabel: (position: number, total: number) => string;
  inputMode: "numeric" | "text" | "email";
  size?: BoxSize;
  wrap?: boolean;
  /** Indexes that start a new visual segment (a slightly wider gap before them). */
  segmentStarts?: readonly number[];
  readOnly?: boolean;
  error?: string;
  name?: string;
  className?: string;
}

const SIZE_CLASSES: Record<BoxSize, { box: string; fixed: string }> = {
  large: { box: "h-11 text-lg", fixed: "w-8 sm:w-9" },
  small: { box: "h-7 text-sm", fixed: "w-6" },
};

/**
 * Paper-form character boxes (PROMPT.md §11) shared by NidInput and BoxStringInput.
 *
 * The value is always contiguous: focus never lands past the first empty box, typing replaces
 * or appends, Backspace on an empty box steps back and clears, paste distributes characters.
 * The boxes always run left-to-right (`dir="ltr"`), so ArrowRight means "next" even on an RTL page.
 * Screen readers get one labelled group plus one read-only input holding the whole value.
 */
export function BoxInput({
  label,
  value,
  onChange,
  length,
  sanitize,
  boxLabel,
  inputMode,
  size = "large",
  wrap = false,
  segmentStarts = [],
  readOnly = false,
  error,
  name,
  className,
}: BoxInputProps) {
  const refs = useRef<(HTMLInputElement | null)[]>([]);
  // Auto-advance focuses the next box before the parent re-renders with the new value, so the
  // "never past the first empty box" redirect must only apply to focus the user initiated.
  const movingFocus = useRef(false);
  // Last selection of each box (select events), so a multi-character change (autofill, IME)
  // knows whether it replaced the box's character or was inserted before/after it.
  const selections = useRef<({ start: number; end: number } | undefined)[]>([]);
  const errorId = useId();
  const chars = Array.from(value).slice(0, length);
  const filled = chars.length;
  const sizes = SIZE_CLASSES[size];

  const focusBox = (index: number) => {
    const target = refs.current[Math.max(0, Math.min(index, length - 1))];
    movingFocus.current = true;
    try {
      target?.focus();
      target?.select();
    } finally {
      movingFocus.current = false;
    }
  };

  const commit = (next: string[]) => {
    const joined = next.slice(0, length).join("");
    if (joined !== value) onChange(joined);
  };

  /** Write `text` starting at `index`, overwriting what is there. Returns the next focus index. */
  const writeAt = (index: number, text: string[]): number => {
    if (text.length >= length) {
      commit(text);
      return length - 1;
    }
    const next = [...chars];
    text.forEach((ch, offset) => {
      next[index + offset] = ch;
    });
    commit(next);
    return Math.min(index + text.length, length - 1);
  };

  const removeAt = (index: number) => {
    commit(chars.filter((_, i) => i !== index));
  };

  const rememberSelection = (index: number, input: HTMLInputElement) => {
    selections.current[index] = { start: input.selectionStart ?? 0, end: input.selectionEnd ?? 0 };
  };

  const handleFocus = (index: number) => {
    if (!readOnly && !movingFocus.current && index > filled) {
      focusBox(filled);
      return;
    }
    refs.current[index]?.select();
  };

  const handleChange = (index: number, event: ChangeEvent<HTMLInputElement>) => {
    if (readOnly) return;
    const raw = event.target.value;
    const previous = chars[index] ?? "";
    if (raw === "") {
      // Some mobile keyboards delete without a key event.
      if (previous) removeAt(index);
      return;
    }
    let typed = raw;
    const selection = selections.current[index];
    selections.current[index] = undefined;
    if (previous && raw.length > 1) {
      if (selection && selection.end > selection.start) {
        typed = raw; // the existing character was selected and replaced
      } else if (selection?.start === 0 && raw.endsWith(previous)) {
        typed = raw.slice(0, -previous.length); // inserted before it
      } else if (raw.startsWith(previous)) {
        typed = raw.slice(previous.length); // the caret was after the existing character
      } else if (raw.endsWith(previous)) {
        typed = raw.slice(0, -previous.length);
      }
    }
    const accepted = Array.from(sanitize(typed));
    if (accepted.length === 0) return;
    focusBox(writeAt(index, accepted));
  };

  const handleKeyDown = (index: number, event: KeyboardEvent<HTMLInputElement>) => {
    switch (event.key) {
      case "Backspace": {
        event.preventDefault();
        if (readOnly) return;
        if (chars[index] !== undefined) {
          removeAt(index);
        } else if (index > 0) {
          removeAt(index - 1);
          focusBox(index - 1);
        }
        return;
      }
      case "Delete": {
        event.preventDefault();
        if (!readOnly && chars[index] !== undefined) removeAt(index);
        return;
      }
      case "ArrowRight":
        event.preventDefault();
        focusBox(Math.min(index + 1, filled));
        return;
      case "ArrowLeft":
        event.preventDefault();
        focusBox(index - 1);
        return;
      case "Home":
        event.preventDefault();
        focusBox(0);
        return;
      case "End":
        event.preventDefault();
        focusBox(filled);
        return;
      default:
        return;
    }
  };

  const handlePaste = (index: number, event: ClipboardEvent<HTMLInputElement>) => {
    event.preventDefault();
    if (readOnly) return;
    const accepted = Array.from(sanitize(event.clipboardData.getData("text")));
    if (accepted.length === 0) return;
    focusBox(writeAt(Math.min(index, filled), accepted));
  };

  return (
    <div className={cx("min-w-0", className)}>
      <div
        role="group"
        aria-label={label}
        aria-describedby={error ? errorId : undefined}
        dir="ltr"
        data-size={size}
        className={cx("flex gap-1", wrap ? "flex-wrap" : "flex-nowrap")}
      >
        {Array.from({ length }, (_, index) => (
          <input
            key={index}
            ref={(element) => {
              refs.current[index] = element;
            }}
            type="text"
            inputMode={inputMode}
            autoComplete="off"
            spellCheck={false}
            aria-label={boxLabel(index + 1, length)}
            aria-invalid={error ? true : undefined}
            readOnly={readOnly}
            value={chars[index] ?? ""}
            onFocus={() => handleFocus(index)}
            onSelect={(event) => rememberSelection(index, event.currentTarget)}
            onMouseUp={(event) => rememberSelection(index, event.currentTarget)}
            onKeyUp={(event) => rememberSelection(index, event.currentTarget)}
            onChange={(event) => handleChange(index, event)}
            onKeyDown={(event) => handleKeyDown(index, event)}
            onPaste={(event) => handlePaste(index, event)}
            className={cx(
              "paper-box rounded-none p-0",
              sizes.box,
              wrap ? sizes.fixed : "min-w-0 flex-1 basis-0",
              !wrap && (size === "large" ? "max-w-10" : "max-w-6"),
              segmentStarts.includes(index) && "ms-1.5",
              error && "border-danger",
              readOnly && "cursor-default bg-smoke",
            )}
          />
        ))}
      </div>
      <input
        className="sr-only"
        tabIndex={-1}
        readOnly
        dir="ltr"
        aria-label={label}
        name={name}
        value={value}
      />
      {error ? (
        <p id={errorId} className="mt-1 text-sm font-semibold text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}
