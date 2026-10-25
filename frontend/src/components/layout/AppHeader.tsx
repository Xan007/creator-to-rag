import { memo, useState, type FormEvent } from "react";
import {
  PanelLeft,
  Settings,
  Languages,
  Pencil,
  Check,
  X,
  Layers,
  MessageSquare,
} from "lucide-react";
import { useTranslation } from "../../lib/i18n";
import { cn, focusInput } from "../../lib/utils";
import { NotificationsBell } from "../ui/NotificationsBell";

interface AppHeaderProps {
  title: string;
  isSidebarOpen: boolean;
  onOpenSidebar: () => void;
  onOpenSettings: () => void;
  isChat?: boolean;
  onRenameTitle?: (newTitle: string) => void;
  activeTab?: "knowledge" | "chat";
  onTabChange?: (tab: "knowledge" | "chat") => void;
}

export const AppHeader = memo(function AppHeader({
  title,
  isSidebarOpen,
  onOpenSidebar,
  onOpenSettings,
  isChat,
  onRenameTitle,
  activeTab,
  onTabChange,
}: AppHeaderProps) {
  const { lang, toggleLang, t } = useTranslation();

  return (
    <header className="h-16 flex items-center px-6 border-b border-gray-200 bg-white z-10 justify-between shrink-0 relative">
      <div className="flex items-center gap-4 min-w-0 flex-1 mr-4 max-w-[calc(50%-130px)]">
        {!isSidebarOpen && (
          <button
            type="button"
            onClick={onOpenSidebar}
            className="p-2 -ml-2 text-slate-500 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors duration-200 cursor-pointer animate-in fade-in-50 zoom-in-95 shrink-0"
            title={t("nav.openSidebar")}
          >
            <PanelLeft size={20} />
          </button>
        )}

        <HeaderTitle
          key={title}
          title={title}
          isChat={isChat}
          onRenameTitle={onRenameTitle}
        />
      </div>

      {onTabChange && (
        <div className="hidden sm:flex items-center absolute left-1/2 -translate-x-1/2 bg-slate-100 p-1 rounded-xl border border-slate-200/80 shadow-2xs z-10">
          <button
            type="button"
            onClick={() => onTabChange("knowledge")}
            className={cn(
              "px-3.5 py-1.5 text-xs font-semibold rounded-lg flex items-center gap-1.5 transition-colors duration-150 cursor-pointer",
              activeTab === "knowledge"
                ? "bg-white text-slate-900 shadow-2xs font-bold"
                : "text-slate-500 hover:text-slate-900",
            )}
          >
            <Layers size={13} />
            <span>{t("library.tabKnowledge")}</span>
          </button>
          <button
            type="button"
            onClick={() => onTabChange("chat")}
            className={cn(
              "px-3.5 py-1.5 text-xs font-semibold rounded-lg flex items-center gap-1.5 transition-colors duration-150 cursor-pointer",
              activeTab === "chat"
                ? "bg-white text-slate-900 shadow-2xs font-bold"
                : "text-slate-500 hover:text-slate-900",
            )}
          >
            <MessageSquare
              size={13}
              className={
                activeTab === "chat" ? "text-slate-900" : "text-slate-400"
              }
            />
            <span>{t("library.tabChat")}</span>
          </button>
        </div>
      )}

      <div className="flex items-center gap-2 shrink-0">
        <button
          type="button"
          onClick={toggleLang}
          className="px-2.5 py-1 text-xs font-semibold text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors duration-200 cursor-pointer flex items-center gap-1.5 border border-slate-200 shadow-2xs"
          title={
            lang === "es"
              ? t("header.switchToEnglish")
              : t("header.switchToSpanish")
          }
        >
          <Languages size={15} />
          <span className="tracking-wide uppercase font-bold">{lang}</span>
        </button>

        <button
          type="button"
          onClick={onOpenSettings}
          className="p-2 text-slate-400 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors duration-150 cursor-pointer"
          title={t("header.settings")}
        >
          <Settings size={20} />
        </button>

        <NotificationsBell />
      </div>
    </header>
  );
});

function HeaderTitle({
  title,
  isChat,
  onRenameTitle,
}: Pick<AppHeaderProps, "title" | "isChat" | "onRenameTitle">) {
  const { t } = useTranslation();
  const safeTitle = typeof title === "string" ? title : "";
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(safeTitle);

  const handleSave = (e?: FormEvent) => {
    e?.preventDefault();
    if (editValue.trim() && editValue.trim() !== safeTitle) {
      onRenameTitle?.(editValue.trim());
    }
    setIsEditing(false);
  };

  return (
    <>
      {" "}
      {isChat && onRenameTitle && isEditing ? (
        <form
          onSubmit={handleSave}
          className="flex items-center gap-1.5 min-w-0"
        >
          <input
            ref={focusInput}
            aria-label={t("chat.clickToEdit")}
            type="text"
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                setIsEditing(false);
                setEditValue(title);
              }
            }}
            onBlur={handleSave}
            className="text-base md:text-lg font-medium bg-slate-50 border border-slate-300 rounded-md px-2.5 py-1 outline-none focus:ring-2 focus:ring-slate-900 focus:bg-white text-slate-900 max-w-xs md:max-w-md shadow-2xs"
          />
          <button
            type="submit"
            className="p-1.5 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-md transition-colors cursor-pointer"
            title={t("chat.save")}
          >
            <Check size={16} />
          </button>
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => {
              setIsEditing(false);
              setEditValue(title);
            }}
            className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-md transition-colors cursor-pointer"
            title={t("chat.cancel")}
          >
            <X size={16} />
          </button>
        </form>
      ) : (
        <div className="flex items-center gap-2 group min-w-0">
          <h1
            className={cn(
              "text-lg font-medium truncate",
              isChat && onRenameTitle && "cursor-pointer hover:text-slate-600",
            )}
            title={isChat && onRenameTitle ? t("chat.clickToEdit") : safeTitle}
          >
            {safeTitle}
          </h1>
          {isChat && onRenameTitle && (
            <button
              type="button"
              onClick={() => {
                setEditValue(safeTitle);
                setIsEditing(true);
              }}
              className="p-1 text-slate-400 hover:text-slate-800 opacity-0 group-hover:opacity-100 transition-opacity rounded cursor-pointer"
              title={t("chat.renameTitle")}
            >
              <Pencil size={14} />
            </button>
          )}
        </div>
      )}
    </>
  );
}
