import { Construction } from "lucide-react";

/** Temporary view for screens that arrive in later stages. */
export function PlaceholderView({ title, stage }: { title: string; stage: string }) {
  return (
    <div className="page-heading">
      <div>
        <p className="kicker">{stage.toUpperCase()}</p>
        <h1 data-testid="view-title">{title}</h1>
        <p>This screen is delivered in {stage} of the implementation plan.</p>
      </div>
      <div className="placeholder-badge">
        <Construction size={16} />
        Coming in {stage}
      </div>
    </div>
  );
}
