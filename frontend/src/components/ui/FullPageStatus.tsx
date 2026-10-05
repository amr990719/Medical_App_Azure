import { ar } from "@/i18n/ar";
import { Button } from "./Button";
import { Icon } from "./Icon";

export interface FullPageStatusProps {
  message: string;
  isError?: boolean;
  onRetry?: () => void;
}

/** Centered loading or error state for a whole page. */
export function FullPageStatus({ message, isError = false, onRetry }: FullPageStatusProps) {
  return (
    <div className="grid min-h-[50dvh] place-items-center px-4">
      <div
        role={isError ? "alert" : "status"}
        className="flex max-w-md flex-col items-center gap-3 text-center text-slate"
      >
        {isError ? (
          <Icon name="alert" className="size-8 text-danger" />
        ) : (
          <span className="size-8 animate-spin rounded-full border-[3px] border-border border-t-teal" />
        )}
        <p className={isError ? "font-semibold text-charcoal" : undefined}>{message}</p>
        {onRetry ? (
          <Button variant="outline" onClick={onRetry}>
            {ar.common.retry}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
