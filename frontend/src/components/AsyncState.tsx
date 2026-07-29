import { LoaderCircle } from "lucide-react";

export function Spinner({
  size = 16,
  label,
}: {
  size?: number;
  label?: string;
}) {
  return (
    <span className="spinner-wrap" role={label ? "status" : undefined} aria-label={label}>
      <LoaderCircle className="spinner" size={size} aria-hidden="true" />
      {label && <span className="sr-only">{label}</span>}
    </span>
  );
}

export function LoadingState({
  title,
  detail = "This should only take a moment.",
  compact = false,
  testId,
}: {
  title: string;
  detail?: string;
  compact?: boolean;
  testId?: string;
}) {
  return (
    <div
      className={`loading-state ${compact ? "compact" : ""}`}
      role="status"
      aria-live="polite"
      aria-busy="true"
      data-testid={testId}
    >
      <Spinner size={compact ? 18 : 24} />
      <div>
        <strong>{title}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}
