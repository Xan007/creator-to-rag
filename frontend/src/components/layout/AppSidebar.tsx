import { memo, useState } from "react";
import {
  PlayCircle,
  PanelLeftClose,
  Globe,
  PlusCircle,
  Library as LibraryIcon,
  MessageSquare,
  Trash2,
  Loader2,
  Pencil,
} from "lucide-react";
import type { Library, ChatSession } from "../../lib/api-types";
import { useTranslation } from "../../lib/i18n";
import { NavItem } from "../ui/NavItem";
import { cn, focusInput } from "../../lib/utils";

interface AppSidebarProps {
  isOpen: boolean;
  width: number;
  isDragging: boolean;
  onStartDrag: (e: React.MouseEvent) => void;
  onResizeBy: (delta: number) => void;
  onClose: () => void;
  libraries: Library[];
  isLoadingLibraries?: boolean;
  activeLibrary: Library | null;
  activeTab: "knowledge" | "chat";
  onSelectGlobal: () => void;
  onSelectLibrary: (lib: Library) => void;
  onOpenNewLibrary: () => void;
  chatSessions: ChatSession[];
  activeChatId: string | null;
  onSelectChat: (chat: ChatSession) => void;
  onNewChat: () => void;
  onDeleteChat: (chatId: string, e: React.MouseEvent) => void;
  onRenameChat?: (chatId: string, newTitle: string) => void;
}

export const AppSidebar = memo(function AppSidebar({
  isOpen,
  width,
  isDragging,
  onStartDrag,
  onResizeBy,
  onClose,
  libraries,
  isLoadingLibraries = false,
  activeLibrary,
  activeTab,
  onSelectGlobal,
  onSelectLibrary,
  onOpenNewLibrary,
  chatSessions,
  activeChatId,
  onSelectChat,
  onNewChat,
  onDeleteChat,
  onRenameChat,
}: AppSidebarProps) {
  const { t } = useTranslation();
  const [editingChatId, setEditingChatId] = useState<string | null>(null);
  const [editingChatTitle, setEditingChatTitle] = useState("");

  const handleStartRename = (chat: ChatSession, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingChatId(chat.id);
    setEditingChatTitle(chat.title);
  };

  const handleSaveRename = (chatId: string) => {
    if (editingChatTitle.trim()) {
      onRenameChat?.(chatId, editingChatTitle.trim());
    }
    setEditingChatId(null);
  };

  return (
    <aside
      style={{ width: isOpen ? width : 0 }}
      className={cn(
        "absolute inset-y-0 left-0 z-30 md:relative border-slate-200 bg-white flex flex-col shrink-0 max-w-[85vw] md:max-w-none transition-[width] duration-300 ease-in-out overflow-hidden group",
        isDragging && "transition-none",
        isOpen ? "border-r" : "border-r-0",
      )}
    >
      <div style={{ width }} className="flex flex-col h-full bg-white relative">
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label={t("nav.resizeSidebar")}
          tabIndex={0}
          aria-valuenow={width}
          aria-valuemin={180}
          aria-valuemax={480}
          onKeyDown={(event) => {
            if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
              event.preventDefault();
              onResizeBy(event.key === "ArrowLeft" ? -16 : 16);
            }
          }}
          onMouseDown={onStartDrag}
          className="absolute top-0 -right-1.5 w-3 h-full cursor-col-resize z-50 flex justify-center group-hover:opacity-100 opacity-0 transition-opacity"
        >
          <div
            className={`w-0.5 h-full ${isDragging ? "bg-slate-400" : "bg-slate-200"}`}
          />
        </div>

        <div className="h-16 flex items-center px-6 border-b border-slate-200 justify-between shrink-0">
          <div className="flex items-center gap-2 font-semibold text-lg tracking-tight truncate">
            <div className="w-6 h-6 rounded-md bg-slate-900 text-white flex items-center justify-center shrink-0">
              <PlayCircle size={14} className="stroke-[2.5]" />
            </div>
            <span className="truncate">{t("app.name")}</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-900 transition-colors shrink-0 cursor-pointer"
            title={t("nav.closeSidebar")}
          >
            <PanelLeftClose size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-8">
          <div className="space-y-1">
            <NavItem
              icon={<Globe size={18} />}
              label={t("nav.globalDatabase")}
              active={activeLibrary === null}
              onClick={onSelectGlobal}
            />
          </div>

          <div className="space-y-3">
            <button
              type="button"
              className="px-3 flex items-center justify-between group cursor-pointer"
              onClick={onOpenNewLibrary}
              title={t("nav.createLibrary")}
            >
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                {t("nav.libraries")}
              </span>
              <PlusCircle
                size={14}
                className="text-slate-400 group-hover:text-slate-900 transition-colors"
              />
            </button>

            <div className="space-y-1">
              {isLoadingLibraries ? (
                <div className="px-3 py-2 space-y-2 animate-in fade-in duration-200">
                  <div className="flex items-center gap-2 text-xs text-slate-400 font-medium">
                    <Loader2
                      size={13}
                      className="animate-spin text-slate-500 shrink-0"
                    />
                    <span>{t("library.loading")}</span>
                  </div>
                  <div className="space-y-1.5 pt-1">
                    <div className="h-8 bg-slate-100 rounded-lg animate-pulse" />
                    <div className="h-8 bg-slate-100/70 rounded-lg animate-pulse" />
                  </div>
                </div>
              ) : libraries.length === 0 ? (
                <div className="px-3 py-2 text-xs text-slate-400 italic">
                  {t("nav.noLibraries")}
                </div>
              ) : (
                libraries.map((lib) => {
                  const isActiveLib = activeLibrary?.id === lib.id;
                  const libChats = chatSessions.filter(
                    (c) => c.libraryId === lib.id,
                  );
                  return (
                    <div key={lib.id} className="space-y-1">
                      <NavItem
                        icon={<LibraryIcon size={16} />}
                        label={lib.name}
                        active={isActiveLib && activeTab === "knowledge"}
                        onClick={() => onSelectLibrary(lib)}
                      />
                      {isActiveLib && (
                        <div className="ml-4 pl-2 border-l-2 border-slate-100 space-y-1 mt-1">
                          <div className="flex items-center justify-between px-3 pt-2 pb-1 text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                            <span>{t("nav.chatHistory")}</span>
                            <button
                              type="button"
                              onClick={() => onNewChat()}
                              className="text-slate-400 hover:text-slate-900 p-0.5 rounded transition-colors cursor-pointer"
                              title={t("nav.newChat")}
                            >
                              <PlusCircle size={13} />
                            </button>
                          </div>
                          {libChats.map((chat) => {
                            const isActiveChat =
                              activeTab === "chat" && activeChatId === chat.id;
                            const isEditingThis = editingChatId === chat.id;

                            if (isEditingThis) {
                              return (
                                <div
                                  key={chat.id}
                                  className="px-2 py-1 flex items-center gap-1.5 w-full animate-in fade-in-50 duration-150"
                                >
                                  <input
                                    ref={focusInput}
                                    aria-label={t("chat.clickToEdit")}
                                    type="text"
                                    value={editingChatTitle}
                                    onChange={(e) =>
                                      setEditingChatTitle(e.target.value)
                                    }
                                    onKeyDown={(e) => {
                                      if (e.nativeEvent.isComposing) return;
                                      if (e.key === "Enter") {
                                        e.preventDefault();
                                        handleSaveRename(chat.id);
                                      } else if (e.key === "Escape") {
                                        setEditingChatId(null);
                                      }
                                    }}
                                    onBlur={() => handleSaveRename(chat.id)}
                                    className="w-full text-xs font-medium bg-white border border-slate-300 rounded-md px-2 py-1 outline-none focus:ring-1 focus:ring-slate-900 text-slate-900 shadow-2xs"
                                  />
                                </div>
                              );
                            }

                            return (
                              <div
                                key={chat.id}
                                className="group relative flex items-center w-full"
                              >
                                <button
                                  type="button"
                                  onClick={() => onSelectChat(chat)}
                                  className={cn(
                                    "w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors relative overflow-hidden text-left cursor-pointer",
                                    isActiveChat
                                      ? "bg-slate-100 text-slate-900 font-medium"
                                      : "text-slate-500 hover:bg-slate-50 hover:text-slate-900",
                                  )}
                                >
                                  <span
                                    className={cn(
                                      "flex-shrink-0",
                                      isActiveChat
                                        ? "text-slate-800"
                                        : "text-slate-400",
                                    )}
                                  >
                                    <MessageSquare size={14} />
                                  </span>
                                  <span className="flex-1 truncate pr-12">
                                    {typeof chat.title === "string"
                                      ? chat.title
                                      : t("nav.newChat")}
                                  </span>

                                  <div
                                    className={cn(
                                      "absolute right-0 top-0 bottom-0 w-14 bg-gradient-to-l pointer-events-none",
                                      isActiveChat
                                        ? "from-slate-100 via-slate-100/80 to-transparent"
                                        : "from-white via-white/80 to-transparent group-hover:from-slate-50 group-hover:via-slate-50/80",
                                    )}
                                  />
                                </button>

                                <div className="absolute right-2 flex items-center gap-0.5 z-10 opacity-0 group-hover:opacity-100 transition-opacity">
                                  <button
                                    type="button"
                                    onClick={(e) => handleStartRename(chat, e)}
                                    className="p-1 rounded text-slate-400 hover:text-slate-800 hover:bg-slate-200/80 cursor-pointer transition-colors"
                                    title={t("chat.rename")}
                                  >
                                    <Pencil size={12} />
                                  </button>
                                  <button
                                    type="button"
                                    onClick={(e) => onDeleteChat(chat.id, e)}
                                    className="p-1 rounded text-slate-400 hover:text-red-500 hover:bg-slate-200/80 cursor-pointer transition-colors"
                                    title={t("nav.deleteChat")}
                                  >
                                    <Trash2 size={12} />
                                  </button>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
});
