import { cn } from "../../lib/utils";
import type { ReactNode } from "react";

export function NavItem({
  icon,
  label,
  active,
  onClick,
  nested,
  actionIcon,
}: {
  icon: ReactNode;
  label: string;
  active?: boolean;
  onClick: () => void;
  nested?: boolean;
  actionIcon?: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-current={active ? "page" : undefined}
      onClick={onClick}
      className={cn(
        "w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors group relative overflow-hidden",
        nested ? "pl-5" : "",
        active
          ? "bg-slate-100/80 text-slate-900 font-medium shadow-sm ring-1 ring-slate-200/50"
          : "text-slate-500 hover:bg-slate-50 hover:text-slate-900",
      )}
    >
      {active && (
        <div className="absolute left-0 top-0 bottom-0 w-1 bg-slate-800 rounded-r-full" />
      )}
      <span
        className={cn(
          "flex-shrink-0 transition-colors",
          active
            ? "text-slate-800"
            : "text-slate-400 group-hover:text-slate-600",
        )}
      >
        {icon}
      </span>
      <span className="flex-1 text-left truncate">{label}</span>
      {actionIcon && (
        <span className="opacity-0 group-hover:opacity-100 transition-opacity text-slate-400 hover:text-slate-600">
          {actionIcon}
        </span>
      )}
    </button>
  );
}
