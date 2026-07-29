import { ChevronLeft, ChevronRight } from "lucide-react";

export function Pagination({
  label,
  page,
  pageSize,
  total,
  totalPages,
  busy,
  onPageChange,
}: {
  label: string;
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  busy: boolean;
  onPageChange: (page: number) => void;
}) {
  if (total <= pageSize) return null;

  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);

  return (
    <nav
      className="pagination"
      aria-label={`${label} pagination`}
      data-testid={`${label}-pagination`}
    >
      <p aria-live="polite">
        Showing{" "}
        <strong>
          {start}–{end}
        </strong>{" "}
        of <strong>{total}</strong>
      </p>
      <div>
        <button
          className="button secondary"
          onClick={() => onPageChange(page - 1)}
          disabled={busy || page <= 1}
          aria-label={`Previous ${label} page`}
        >
          <ChevronLeft size={15} /> Previous
        </button>
        <span>
          Page <strong>{page}</strong> of <strong>{totalPages}</strong>
        </span>
        <button
          className="button secondary"
          onClick={() => onPageChange(page + 1)}
          disabled={busy || page >= totalPages}
          aria-label={`Next ${label} page`}
        >
          Next <ChevronRight size={15} />
        </button>
      </div>
    </nav>
  );
}
