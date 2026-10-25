import React, { useState } from "react";
import {
  Play,
  ExternalLink,
  Trash2,
  RefreshCw,
  Copy,
  Check,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Sheet } from "./Sheet";
import { resolvePostTitle } from "../../lib/utils";
import { api } from "../../lib/api";
import { useTranslation } from "../../lib/i18n";
import type { ContentItem } from "./ContentTable";

interface ContentDetailSheetProps {
  activeItem: ContentItem | null;
  onClose: () => void;
  onPlayItem?: (url: string) => void;
  libraries?: { id: string; name: string }[];
  libraryMap: Map<string, string>;
  onLinkToLibrary?: (
    targetLibraryId: string,
    postIds: string[],
  ) => Promise<void>;
  hasActions: boolean;
  deleteMode?: "library" | "permanent";
  showLibraryColumn?: boolean;
  onRequestDelete: (item: { id: string; type: string; title: string }) => void;
  onRefresh?: () => void;
  formatDate: (timestamp?: number | null) => string;
}

function useContentDetailSheetModel({
  activeItem,
  onClose,
  onPlayItem,
  libraries,
  libraryMap,
  onLinkToLibrary,
  hasActions,
  deleteMode = "library",
  showLibraryColumn = false,
  onRequestDelete,
  onRefresh,
  formatDate,
}: ContentDetailSheetProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<"knowledge" | "caption">(
    "knowledge",
  );
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [isReindexing, setIsReindexing] = useState(false);
  const [reindexSuccess, setReindexSuccess] = useState(false);
  const [reindexError, setReindexError] = useState<string | null>(null);
  const [localItem, setLocalItem] = useState<ContentItem | null>(null);

  const currentItem = localItem || activeItem;

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedField(id);
    setTimeout(() => setCopiedField(null), 2000);
  };

  const handleReindex = async () => {
    if (!currentItem || isReindexing) return;
    setIsReindexing(true);
    setReindexError(null);
    try {
      const res = await api.reindexSource(currentItem.realId || currentItem.id);
      if (res && res.extracted_knowledge) {
        setLocalItem({
          ...currentItem,
          title: res.title || currentItem.title,
          extracted_knowledge: res.extracted_knowledge,
        });
        setReindexSuccess(true);
        setTimeout(() => setReindexSuccess(false), 3500);
        onRefresh?.();
      }
    } catch (err: any) {
      console.error("Reindex error:", err);
      setReindexError(err?.message || "Error al reindexar");
      setTimeout(() => setReindexError(null), 4000);
    } finally {
      setIsReindexing(false);
    }
  };

  if (!currentItem) return null;

  return {
    activeItem,
    onClose,
    onPlayItem,
    libraries,
    libraryMap,
    onLinkToLibrary,
    hasActions,
    deleteMode,
    showLibraryColumn,
    onRequestDelete,
    formatDate,
    t,
    activeTab,
    setActiveTab,
    copiedField,
    isReindexing,
    reindexSuccess,
    reindexError,
    setLocalItem,
    currentItem,
    handleCopy,
    handleReindex,
  };
}

export function ContentDetailSheet(
  props: Parameters<typeof useContentDetailSheetModel>[0],
) {
  const model = useContentDetailSheetModel(props);
  if (!model) return null;
  return <DetailPanel model={model} />;
}

function DetailPanel({
  model,
}: {
  model: NonNullable<ReturnType<typeof useContentDetailSheetModel>>;
}) {
  const {
    activeItem,
    onClose,
    setLocalItem,
    currentItem,
    t,
    formatDate,
    onPlayItem,
  } = model;
  return (
    <Sheet
      isOpen={!!activeItem}
      onClose={() => {
        setLocalItem(null);
        onClose();
      }}
      title={
        <h2 className="text-base font-semibold text-slate-900 leading-snug">
          {resolvePostTitle(currentItem)}
        </h2>
      }
      description={
        <div className="flex items-center gap-3 text-xs text-slate-500 pt-0.5">
          <span className="font-medium text-slate-700">
            @{currentItem.creator}
          </span>
          <span>•</span>
          <span>
            {currentItem.published_at
              ? `${t("sheet.published")} ${formatDate(currentItem.published_at)}`
              : `${t("sheet.indexed")} ${formatDate(currentItem.indexed_at)}`}
          </span>
        </div>
      }
      footer={
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            {onPlayItem && currentItem.url && (
              <button
                type="button"
                onClick={() => {
                  onPlayItem(currentItem.url);
                  onClose();
                }}
                className="px-3.5 py-2 text-xs font-medium bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition-colors flex items-center gap-1.5 cursor-pointer"
              >
                <Play size={13} /> {t("sheet.watchVideo")}
              </button>
            )}
            {currentItem.url && (
              <a
                href={currentItem.url}
                target="_blank"
                rel="noreferrer"
                className="px-3 py-2 text-xs font-medium border border-slate-200 text-slate-700 rounded-lg hover:bg-slate-50 transition-colors flex items-center gap-1.5"
              >
                <ExternalLink size={13} /> {t("sheet.openLink")}
              </a>
            )}
          </div>

          <DetailLibraryControl model={model} />
        </div>
      }
    >
      <DetailContent model={model} />
    </Sheet>
  );
}

function DetailContent({
  model,
}: {
  model: NonNullable<ReturnType<typeof useContentDetailSheetModel>>;
}) {
  return (
    <div className="space-y-6">
      <DetailMetadata model={model} />

      <DetailTabs model={model} />

      <DetailText model={model} />
    </div>
  );
}

function DetailLibraryControl({
  model,
}: {
  model: NonNullable<ReturnType<typeof useContentDetailSheetModel>>;
}) {
  const {
    libraries,
    onLinkToLibrary,
    t,
    currentItem,
    hasActions,
    onRequestDelete,
    deleteMode,
  } = model;
  return (
    <div className="flex items-center gap-2">
      {libraries && libraries.length > 0 && onLinkToLibrary && (
        <select
          aria-label={t("table.selectAll")}
          defaultValue=""
          onChange={async (e) => {
            const targetLibId = e.target.value;
            if (targetLibId) {
              await onLinkToLibrary(targetLibId, [currentItem.realId]);
              e.target.value = "";
            }
          }}
          className="text-xs border border-slate-200 rounded-lg px-2.5 py-2 bg-white text-slate-800 font-medium cursor-pointer"
        >
          <option value="" disabled>
            {t("sheet.addToLibrary")}
          </option>
          {libraries.map((lib) => (
            <option key={lib.id} value={lib.id}>
              {lib.name}
            </option>
          ))}
        </select>
      )}

      {hasActions && (
        <button
          type="button"
          onClick={() => {
            onRequestDelete({
              id: currentItem.realId,
              type: currentItem.itemType,
              title: resolvePostTitle(currentItem),
            });
          }}
          className="px-3 py-2 text-xs font-medium text-red-600 hover:bg-red-50 rounded-lg transition-colors flex items-center gap-1.5 cursor-pointer"
        >
          <Trash2 size={13} />{" "}
          {deleteMode === "permanent" ? t("sheet.delete") : t("sheet.remove")}
        </button>
      )}
    </div>
  );
}

function DetailText({
  model,
}: {
  model: NonNullable<ReturnType<typeof useContentDetailSheetModel>>;
}) {
  const { activeTab, t, currentItem, handleCopy, copiedField } = model;
  return (
    <>
      {" "}
      {activeTab === "knowledge" ? (
        <div>
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              {t("sheet.transcriptionNotes")}
            </span>
            <div className="flex items-center gap-3">
              <ReindexButton model={model} />
              {currentItem.extracted_knowledge && (
                <button
                  type="button"
                  onClick={() =>
                    handleCopy(
                      currentItem.extracted_knowledge || "",
                      "knowledge",
                    )
                  }
                  className="text-xs text-slate-500 hover:text-slate-900 flex items-center gap-1 transition-colors cursor-pointer"
                >
                  {copiedField === "knowledge" ? (
                    <>
                      <Check size={12} className="text-emerald-600" />
                      <span className="text-emerald-600 font-medium">
                        {t("sheet.copied")}
                      </span>
                    </>
                  ) : (
                    <>
                      <Copy size={12} />
                      <span>{t("sheet.copy")}</span>
                    </>
                  )}
                </button>
              )}
            </div>
          </div>
          {currentItem.extracted_knowledge ? (
            <div className="prose prose-sm prose-slate max-w-none bg-slate-50/50 p-4 rounded-xl border border-slate-100 text-xs md:text-sm leading-relaxed">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {currentItem.extracted_knowledge}
              </ReactMarkdown>
            </div>
          ) : (
            <div className="py-12 text-center text-slate-400 text-xs">
              {t("sheet.noKnowledge")}
            </div>
          )}
        </div>
      ) : (
        <div>
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              {t("sheet.captionTab")}
            </span>
            {currentItem.description && (
              <button
                type="button"
                onClick={() =>
                  handleCopy(currentItem.description || "", "caption")
                }
                className="text-xs text-slate-500 hover:text-slate-900 flex items-center gap-1 transition-colors cursor-pointer"
              >
                {copiedField === "caption" ? (
                  <>
                    <Check size={12} className="text-emerald-600" />
                    <span className="text-emerald-600 font-medium">
                      {t("sheet.copied")}
                    </span>
                  </>
                ) : (
                  <>
                    <Copy size={12} />
                    <span>{t("sheet.copy")}</span>
                  </>
                )}
              </button>
            )}
          </div>
          <p className="text-xs md:text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">
            {currentItem.description || (
              <span className="text-xs text-slate-400 italic">
                {t("sheet.noCaption")}
              </span>
            )}
          </p>
        </div>
      )}{" "}
    </>
  );
}

function DetailMetadata({
  model,
}: {
  model: NonNullable<ReturnType<typeof useContentDetailSheetModel>>;
}) {
  const { t, currentItem, formatDate, showLibraryColumn, libraryMap } = model;
  return (
    <div className="bg-slate-50 rounded-xl p-4 border border-slate-100 flex flex-wrap items-center gap-y-2 gap-x-6 text-xs">
      <div>
        <span className="text-slate-400 block uppercase tracking-wider text-[10px] font-semibold">
          {t("sheet.author")}
        </span>
        <span className="text-slate-800 font-semibold text-sm">
          @{currentItem.creator}
        </span>
      </div>
      <div>
        <span className="text-slate-400 block uppercase tracking-wider text-[10px] font-semibold">
          {t("sheet.type")}
        </span>
        <span className="text-slate-800 font-medium capitalize">
          {currentItem.type || "Reel"}
        </span>
      </div>
      {currentItem.published_at && (
        <div>
          <span className="text-slate-400 block uppercase tracking-wider text-[10px] font-semibold">
            {t("sheet.published")}
          </span>
          <span className="text-slate-800 font-medium">
            {formatDate(currentItem.published_at)}
          </span>
        </div>
      )}
      <div>
        <span className="text-slate-400 block uppercase tracking-wider text-[10px] font-semibold">
          {t("sheet.indexed")}
        </span>
        <span className="text-slate-800 font-medium">
          {formatDate(currentItem.indexed_at)}
        </span>
      </div>
      {showLibraryColumn && currentItem.library_id && (
        <div>
          <span className="text-slate-400 block uppercase tracking-wider text-[10px] font-semibold">
            {t("sheet.library")}
          </span>
          <span className="text-slate-800 font-medium">
            {libraryMap.get(currentItem.library_id) || "Asignada"}
          </span>
        </div>
      )}
    </div>
  );
}

function DetailTabs({
  model,
}: {
  model: NonNullable<ReturnType<typeof useContentDetailSheetModel>>;
}) {
  const { setActiveTab, activeTab, t } = model;
  return (
    <div className="border-b border-slate-200">
      <div className="flex gap-6 -mb-px">
        <button
          type="button"
          onClick={() => setActiveTab("knowledge")}
          className={`pb-3 text-sm font-semibold transition-colors border-b-2 cursor-pointer ${
            activeTab === "knowledge"
              ? "border-slate-900 text-slate-900"
              : "border-transparent text-slate-400 hover:text-slate-700"
          }`}
        >
          {t("sheet.knowledgeTab")}
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("caption")}
          className={`pb-3 text-sm font-semibold transition-colors border-b-2 cursor-pointer ${
            activeTab === "caption"
              ? "border-slate-900 text-slate-900"
              : "border-transparent text-slate-400 hover:text-slate-700"
          }`}
        >
          {t("sheet.captionTab")}
        </button>
      </div>
    </div>
  );
}

function ReindexButton({
  model,
}: {
  model: NonNullable<ReturnType<typeof useContentDetailSheetModel>>;
}) {
  const { t, isReindexing, handleReindex, reindexSuccess, reindexError } =
    model;
  return (
    <button
      type="button"
      disabled={isReindexing}
      onClick={handleReindex}
      className="text-xs text-slate-500 hover:text-slate-900 flex items-center gap-1.5 transition-colors cursor-pointer disabled:opacity-50"
      title={t("sheet.reindexAi")}
    >
      <RefreshCw
        size={12}
        className={
          isReindexing
            ? "animate-spin text-slate-900"
            : reindexSuccess
              ? "text-emerald-600"
              : ""
        }
      />
      <span
        className={
          reindexSuccess
            ? "text-emerald-600 font-medium"
            : reindexError
              ? "text-red-500"
              : ""
        }
      >
        {isReindexing
          ? t("sheet.reindexing")
          : reindexSuccess
            ? t("sheet.updated")
            : reindexError || t("sheet.reindexAi")}
      </span>
    </button>
  );
}
