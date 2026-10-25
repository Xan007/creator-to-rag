import { useState, useEffect, useCallback } from "react";
import { X, Search, CheckSquare, Square, Loader2, Check } from "lucide-react";
import { api } from "../../lib/api";
import { resolvePostTitle } from "../../lib/utils";
import { useTranslation } from "../../lib/i18n";
import type { GlobalPost } from "../../lib/api-types";

function GlobalPostSelectorModalContent({
  isOpen,
  onClose,
  libraryId,
  onAdded,
}: {
  isOpen: boolean;
  onClose: () => void;
  libraryId: string;
  onAdded: () => void;
}) {
  const { t } = useTranslation();
  const [posts, setPosts] = useState<GlobalPost[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const loadPosts = useCallback(async (queryStr: string = "") => {
    setLoading(true);
    try {
      const res = await api.getPosts({
        page_size: 50,
        query: queryStr.trim() || undefined,
      });
      setPosts(res.items || []);
      setTotal(res.total || 0);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      loadPosts();
    }
  }, [isOpen, loadPosts]);

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === posts.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(posts.map((p) => p.id)));
    }
  };

  const handleLink = async () => {
    if (!libraryId || selectedIds.size === 0) return;
    setSubmitting(true);
    try {
      await api.linkPosts(libraryId, Array.from(selectedIds));
      setSuccessMsg(t("globalSelector.success", { count: selectedIds.size }));
      setTimeout(() => {
        onAdded();
        onClose();
      }, 700);
    } catch (e: any) {
      alert(e.message || t("globalSelector.error"));
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-2xl overflow-hidden animate-in zoom-in-95 duration-200 flex flex-col max-h-[85vh]">
        <div className="flex items-center justify-between p-4 border-b border-gray-100">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">
              {t("globalSelector.title")}
            </h2>
            <p className="text-xs text-gray-500 mt-0.5">
              {t("globalSelector.desc")}
            </p>
          </div>
          <button
            aria-label={t("modal.cancel")}
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 rounded-full hover:bg-gray-100 cursor-pointer"
          >
            <X size={20} />
          </button>
        </div>

        <div className="p-4 space-y-3 flex-1 overflow-hidden flex flex-col">
          {successMsg && (
            <div className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg text-xs flex items-center gap-2">
              <Check size={14} className="text-emerald-600" />
              <span>{successMsg}</span>
            </div>
          )}

          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search
                size={15}
                className="absolute left-3 top-2.5 text-slate-400"
              />
              <input
                aria-label={t("globalSelector.searchPlaceholder")}
                type="text"
                placeholder={t("globalSelector.searchPlaceholder")}
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  loadPosts(e.target.value);
                }}
                className="w-full pl-9 pr-3 py-1.5 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-900"
              />
            </div>
            {posts.length > 0 && (
              <button
                type="button"
                onClick={toggleSelectAll}
                className="px-3 py-1.5 text-xs font-medium border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-700 cursor-pointer"
              >
                {selectedIds.size === posts.length
                  ? t("globalSelector.deselectAll")
                  : t("globalSelector.selectAll")}
              </button>
            )}
          </div>

          <div className="flex-1 overflow-y-auto border border-slate-100 rounded-lg divide-y divide-slate-100 min-h-[200px]">
            {loading ? (
              <div className="py-12 flex justify-center">
                <Loader2 className="animate-spin text-slate-400" />
              </div>
            ) : posts.length === 0 ? (
              <div className="py-12 text-center text-sm text-slate-500">
                {t("globalSelector.noPosts")}
              </div>
            ) : (
              posts.map((p) => {
                const isSelected = selectedIds.has(p.id);
                return (
                  <div
                    tabIndex={0}
                    onKeyDown={(event) => {
                      if (
                        event.target === event.currentTarget &&
                        (event.key === "Enter" || event.key === " ")
                      ) {
                        event.preventDefault();
                        event.currentTarget.click();
                      }
                    }}
                    role="button"
                    key={p.id}
                    onClick={() => toggleSelect(p.id)}
                    className={`flex items-start gap-3 p-3 hover:bg-slate-50 cursor-pointer transition-colors ${
                      isSelected ? "bg-slate-50/80" : ""
                    }`}
                  >
                    <div className="mt-0.5 text-slate-400">
                      {isSelected ? (
                        <CheckSquare size={16} className="text-slate-900" />
                      ) : (
                        <Square size={16} />
                      )}
                    </div>
                    <div className="min-w-0 flex-1 text-xs">
                      <div className="flex items-center gap-2 font-medium text-slate-900 mb-0.5">
                        <span className="font-semibold text-slate-800">
                          @{p.creator_username || p.creator || "unknown"}
                        </span>
                        <span className="text-[10px] text-slate-400 uppercase bg-slate-100 px-1 py-0.5 rounded font-mono">
                          {p.type || "REEL"}
                        </span>
                      </div>
                      <p className="font-semibold text-slate-900 text-xs line-clamp-1 mb-0.5">
                        {resolvePostTitle(p)}
                      </p>
                      <p className="text-slate-500 text-[11px] line-clamp-2 leading-relaxed">
                        {p.description || p.extracted_knowledge || p.url}
                      </p>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          <div className="flex justify-between items-center pt-2 border-t border-slate-100">
            <span className="text-xs text-slate-500">
              {t("globalSelector.selectedCount", {
                selected: selectedIds.size,
                total,
              })}
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={onClose}
                className="px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 rounded-lg transition-colors cursor-pointer"
              >
                {t("globalSelector.cancel")}
              </button>
              <button
                type="button"
                onClick={handleLink}
                disabled={selectedIds.size === 0 || submitting}
                className="px-4 py-1.5 bg-slate-900 text-white rounded-lg text-xs font-medium hover:bg-slate-800 disabled:opacity-50 transition-colors flex items-center gap-1.5 cursor-pointer"
              >
                {submitting && <Loader2 size={12} className="animate-spin" />}
                {t("globalSelector.addToLibrary", { count: selectedIds.size })}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function GlobalPostSelectorModal(
  props: Parameters<typeof GlobalPostSelectorModalContent>[0],
) {
  return props.isOpen ? (
    <GlobalPostSelectorModalContent key={props.libraryId} {...props} />
  ) : null;
}
