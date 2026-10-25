import {
  useState,
  useRef,
  useEffect,
  useCallback,
  useEffectEvent,
} from "react";
import { createPortal } from "react-dom";
import { HelpCircle, X, Search } from "lucide-react";
import { cn } from "../../lib/utils";
import { useTranslation } from "../../lib/i18n";

export interface SearchHelpPopoverProps {
  align?: "left" | "right";
  currentMode?: "keyword" | "semantic";
  className?: string;
  isOpen?: boolean;
  onClose?: () => void;
}

export function SearchHelpPopover({
  align = "right",
  currentMode,
  className,
  isOpen,
  onClose,
}: SearchHelpPopoverProps) {
  const { t } = useTranslation();
  const [internalOpen, setInternalOpen] = useState(false);
  const [coords, setCoords] = useState<{
    top: number;
    right?: number;
    left?: number;
  }>({ top: 0 });
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  const isControlled = typeof isOpen === "boolean";
  const show = isControlled ? isOpen : internalOpen;

  const updatePosition = useCallback(() => {
    if (!triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    const isMobile = window.innerWidth < 440;

    if (isMobile) {
      setCoords({
        top: Math.round(rect.bottom + 8),
        left: 16,
        right: 16,
      });
    } else if (align === "right") {
      const rightDistance = Math.max(
        16,
        Math.round(window.innerWidth - rect.right),
      );
      setCoords({
        top: Math.round(rect.bottom + 8),
        right: rightDistance,
      });
    } else {
      setCoords({
        top: Math.round(rect.bottom + 8),
        left: Math.max(16, Math.round(rect.left)),
      });
    }
  }, [align]);

  const handleClose = useCallback(() => {
    if (isControlled && onClose) {
      onClose();
    } else {
      setInternalOpen(false);
    }
  }, [isControlled, onClose]);

  const handleToggle = () => {
    if (isControlled) {
      if (show && onClose) {
        onClose();
      }
    } else {
      if (!internalOpen) updatePosition();
      setInternalOpen(!internalOpen);
    }
  };

  const closeFromEvent = useEffectEvent(handleClose);
  useEffect(() => {
    if (show) {
      updatePosition();
      const onReposition = () => updatePosition();
      window.addEventListener("resize", onReposition);
      window.addEventListener("scroll", onReposition, {
        passive: true,
        capture: true,
      });

      const handleClickOutside = (event: MouseEvent) => {
        const target = event.target as Node;
        if (
          triggerRef.current &&
          !triggerRef.current.contains(target) &&
          popoverRef.current &&
          !popoverRef.current.contains(target)
        ) {
          closeFromEvent();
        }
      };

      const handleKeyDown = (event: KeyboardEvent) => {
        if (event.key === "Escape") {
          closeFromEvent();
        }
      };

      document.addEventListener("mousedown", handleClickOutside);
      document.addEventListener("keydown", handleKeyDown);

      return () => {
        window.removeEventListener("resize", onReposition);
        window.removeEventListener("scroll", onReposition, true);
        document.removeEventListener("mousedown", handleClickOutside);
        document.removeEventListener("keydown", handleKeyDown);
      };
    }
  }, [show, updatePosition]);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={handleToggle}
        className={cn(
          "p-1 rounded-md text-slate-400 hover:text-slate-800 hover:bg-slate-100 transition-colors cursor-pointer",
          show ? "bg-slate-100 text-slate-800" : "",
        )}
        title={t("searchHelp.tooltip")}
      >
        <HelpCircle size={15} />
      </button>

      {show &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            ref={popoverRef}
            style={{
              position: "fixed",
              top: `${coords.top}px`,
              ...(coords.left !== undefined
                ? { left: `${coords.left}px` }
                : {}),
              ...(coords.right !== undefined
                ? { right: `${coords.right}px` }
                : {}),
              zIndex: 9999,
            }}
            className={cn(
              "w-80 sm:w-96 max-w-[calc(100vw-2rem)]",
              "bg-white border border-slate-200 shadow-2xl rounded-xl p-4 text-slate-700",
              "animate-in fade-in zoom-in-95",
              className,
            )}
          >
            <div className="flex items-center justify-between pb-2.5 mb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <Search size={14} className="text-slate-700" />
                <h4 className="text-xs font-semibold text-slate-900">
                  {t("searchHelp.title")}
                </h4>
              </div>
              <button
                type="button"
                onClick={handleClose}
                className="text-slate-400 hover:text-slate-700 p-1 rounded-md transition-colors cursor-pointer"
                title={t("searchHelp.close")}
              >
                <X size={14} />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-slate-800">
                    {t("searchHelp.textSearch")}
                  </span>
                  {currentMode === "keyword" && (
                    <span className="text-[10px] text-slate-500 font-medium bg-slate-100 px-1.5 py-0.5 rounded">
                      {t("searchHelp.activeMode")}
                    </span>
                  )}
                </div>
                <p className="text-slate-500 text-[11px] leading-relaxed">
                  {t("searchHelp.textSearchDesc")}
                </p>
                <div className="flex flex-wrap gap-1.5 pt-0.5">
                  <code className="text-[11px] bg-slate-50 border border-slate-200 text-slate-800 px-1.5 py-0.5 rounded font-mono">
                    pancakes
                  </code>
                  <code className="text-[11px] bg-slate-50 border border-slate-200 text-slate-800 px-1.5 py-0.5 rounded font-mono">
                    avena proteina
                  </code>
                </div>
              </div>

              <div className="space-y-1 pt-2 border-t border-slate-100">
                <span className="font-semibold text-slate-800 block">
                  {t("searchHelp.creatorFilter")}
                </span>
                <p className="text-slate-500 text-[11px] leading-relaxed">
                  {t("searchHelp.creatorFilterDesc")}
                </p>
                <div className="flex flex-wrap gap-1.5 pt-0.5">
                  <code className="text-[11px] bg-slate-50 border border-slate-200 text-slate-800 px-1.5 py-0.5 rounded font-mono">
                    @bejaranofit
                  </code>
                  <code className="text-[11px] bg-slate-50 border border-slate-200 text-slate-800 px-1.5 py-0.5 rounded font-mono">
                    @alejomendezchef
                  </code>
                </div>
              </div>

              <div className="space-y-1 pt-2 border-t border-slate-100">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-slate-800">
                    {t("searchHelp.semanticSearch")}
                  </span>
                  {currentMode === "semantic" && (
                    <span className="text-[10px] text-slate-500 font-medium bg-slate-100 px-1.5 py-0.5 rounded">
                      {t("searchHelp.activeMode")}
                    </span>
                  )}
                </div>
                <p className="text-slate-500 text-[11px] leading-relaxed">
                  {t("searchHelp.semanticSearchDesc")}
                </p>
                <div className="space-y-1 pt-0.5">
                  <div className="text-[11px] bg-slate-50 border border-slate-200 text-slate-800 px-2 py-1 rounded font-mono">
                    {t("searchHelp.example1")}
                  </div>
                  <div className="text-[11px] bg-slate-50 border border-slate-200 text-slate-800 px-2 py-1 rounded font-mono">
                    {t("searchHelp.example2")}
                  </div>
                </div>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
