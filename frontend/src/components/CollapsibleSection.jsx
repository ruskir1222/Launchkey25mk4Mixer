import { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";

/**
 * Collapsible card section with title row + chevron, persists open/closed
 * state per-id in localStorage.
 */
export default function CollapsibleSection({
  id,
  title,
  defaultOpen = true,
  children,
  headerExtra = null,
  className = "",
}) {
  const storageKey = `lkmixer.section.${id}`;
  const [open, setOpen] = useState(() => {
    try {
      const v = localStorage.getItem(storageKey);
      return v === null ? defaultOpen : v === "1";
    } catch {
      return defaultOpen;
    }
  });
  useEffect(() => {
    try { localStorage.setItem(storageKey, open ? "1" : "0"); } catch {}
  }, [storageKey, open]);

  return (
    <div className={`surface ${className}`} data-testid={`section-${id}`}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        data-testid={`section-toggle-${id}`}
        className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-[#1a1a1a] transition-colors border-b border-transparent data-[open=true]:border-[#262626]"
        data-open={open}
      >
        <div className="overline text-left">{title}</div>
        <div className="flex items-center gap-2">
          {headerExtra}
          <ChevronDown
            className={`w-3.5 h-3.5 text-neutral-500 transition-transform duration-200 ${open ? "" : "-rotate-90"}`}
            strokeWidth={2}
          />
        </div>
      </button>
      {open && <div className="p-4 animate-slideUp">{children}</div>}
    </div>
  );
}
