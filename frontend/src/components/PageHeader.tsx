import type { ReactNode } from "react";

interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  meta?: string;
  action?: ReactNode;
}

export function PageHeader({ eyebrow, title, meta, action }: PageHeaderProps) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3 px-5 pt-6 sm:px-8 sm:pt-8">
      <div className="min-w-0">
        {eyebrow && (
          <p className="mb-1.5 font-mono text-[11px] uppercase tracking-[0.14em] text-stone">
            {eyebrow}
          </p>
        )}
        <h1 className="font-display text-[28px] leading-tight tracking-tight text-ink sm:text-[34px]">
          {title}
        </h1>
        {meta && (
          <p className="mt-2 font-mono text-[13px] text-stone">{meta}</p>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </header>
  );
}
