import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Link as LinkIcon,
  Trash2,
  Globe,
  Edit2,
  UserPlus,
  Layers,
  Users,
} from "lucide-react";
import { api, isAbortError } from "../../lib/api";
import type { Library, LibraryDetails, GlobalPost } from "../../lib/api-types";
import { resolvePostTitle } from "../../lib/utils";
import { useTranslation } from "../../lib/i18n";
import { ContentTable } from "./ContentTable";
import type { ContentItem } from "./ContentTable";

export function LibraryDashboard({
  library,
  onLibraryDeleted,
  onAddSource,
  onAddProfile,
  onAddFromGlobal,
  onPlayItem,
}: {
  library: Library;
  onLibraryDeleted: () => void;
  onAddSource: () => void;
  onAddProfile: () => void;
  onAddFromGlobal: () => void;
  onPlayItem?: (url: string) => void;
}) {
  const {
    t,
    details,
    loading,
    isEditing,
    setIsEditing,
    editName,
    setEditName,
    editDesc,
    setEditDesc,
    isDeleting,
    fetchDetails,
    handleSave,
    handleDelete,
    tableData,
    uniqueCreators,
  } = useLibraryDashboard(library, onLibraryDeleted);

  if (loading) {
    return (
      <div className="w-full h-full flex flex-col items-center justify-center space-y-4 text-slate-400">
        <div className="w-8 h-8 border-2 border-slate-200 border-t-slate-800 rounded-full animate-spin" />
        <p className="text-sm">{t("library.loading")}</p>
      </div>
    );
  }

  const totalItems = tableData.length;

  return (
    <div className="max-w-7xl mx-auto p-6 md:p-8 space-y-8 animate-in fade-in zoom-in-95 duration-300">
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-8">
        <div className="flex justify-between items-start">
          <div className="flex-1">
            {isEditing ? (
              <div className="space-y-4 max-w-md">
                <div>
                  <label
                    htmlFor="field-librarydashboard-117"
                    className="text-xs font-semibold text-slate-500 uppercase tracking-wider"
                  >
                    {t("library.nameLabel")}
                  </label>
                  <input
                    id="field-librarydashboard-117"
                    className="w-full mt-1.5 border border-slate-300 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-slate-900 focus:border-slate-900 transition-colors outline-none"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                  />
                </div>
                <div>
                  <label
                    htmlFor="field-librarydashboard-121"
                    className="text-xs font-semibold text-slate-500 uppercase tracking-wider"
                  >
                    {t("library.descLabel")}
                  </label>
                  <textarea
                    id="field-librarydashboard-121"
                    className="w-full mt-1.5 border border-slate-300 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-slate-900 focus:border-slate-900 transition-colors outline-none min-h-[100px]"
                    value={editDesc}
                    onChange={(e) => setEditDesc(e.target.value)}
                  />
                </div>
                <div className="flex gap-2 pt-2">
                  <button
                    onClick={handleSave}
                    className="bg-slate-900 text-white px-5 py-2.5 rounded-lg text-sm font-medium hover:bg-slate-800 transition-colors cursor-pointer"
                  >
                    {t("library.saveChanges")}
                  </button>
                  <button
                    onClick={() => setIsEditing(false)}
                    className="bg-slate-100 text-slate-700 px-5 py-2.5 rounded-lg text-sm font-medium hover:bg-slate-200 transition-colors cursor-pointer"
                  >
                    {t("modal.cancel")}
                  </button>
                </div>
              </div>
            ) : (
              <div>
                <h1 className="text-3xl font-bold text-slate-900 tracking-tight">
                  {details?.name}
                </h1>
                <p className="text-slate-500 mt-2 max-w-2xl leading-relaxed">
                  {details?.description || t("library.noDescription")}
                </p>
              </div>
            )}
          </div>

          {!isEditing && (
            <div className="flex items-center gap-1">
              <button
                onClick={() => {
                  setEditName(details?.name ?? library.name);
                  setEditDesc(
                    details?.description ?? library.description ?? "",
                  );
                  setIsEditing(true);
                }}
                className="p-2 text-slate-400 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors cursor-pointer"
                title={t("library.editDetails")}
              >
                <Edit2 size={18} />
              </button>
              <button
                onClick={handleDelete}
                disabled={isDeleting}
                className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors cursor-pointer"
                title={t("library.deleteLibrary")}
              >
                <Trash2 size={18} />
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 max-w-sm">
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-medium text-slate-500">
              {t("library.indexedReels")}
            </p>
            <p className="text-xl font-bold text-slate-900 mt-0.5">
              {totalItems}
            </p>
          </div>
          <div className="w-8 h-8 rounded-lg bg-slate-100 text-slate-600 flex items-center justify-center">
            <Layers size={16} />
          </div>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-medium text-slate-500">
              {t("library.creators")}
            </p>
            <p className="text-xl font-bold text-slate-900 mt-0.5">
              {uniqueCreators}
            </p>
          </div>
          <div className="w-8 h-8 rounded-lg bg-slate-100 text-slate-600 flex items-center justify-center">
            <Users size={16} />
          </div>
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden flex flex-col">
        <div className="px-6 py-5 border-b border-slate-100 flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4">
          <div>
            <h3 className="text-lg font-semibold text-slate-900 tracking-tight">
              {t("library.contentInventory")}
            </h3>
            <p className="text-sm text-slate-500 mt-1">
              {t("library.contentInventoryDesc")}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={onAddFromGlobal}
              className="bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2 shadow-sm cursor-pointer"
            >
              <Globe size={16} className="text-slate-400" />{" "}
              {t("library.fromGlobal")}
            </button>
            <button
              onClick={onAddSource}
              className="bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2 shadow-sm cursor-pointer"
            >
              <LinkIcon size={16} className="text-slate-400" />{" "}
              {t("library.addSource")}
            </button>
            <button
              onClick={onAddProfile}
              className="bg-slate-900 hover:bg-slate-800 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2 shadow-sm cursor-pointer"
            >
              <UserPlus size={16} /> {t("library.addCreator")}
            </button>
          </div>
        </div>

        <ContentTable
          data={tableData}
          showFilters={true}
          emptyMessage={t("library.empty")}
          onPlayItem={onPlayItem}
          onDeletePost={async (id) => {
            await api.deletePost(library.id, id);
            fetchDetails();
          }}
          onDeleteSource={async (id) => {
            await api.deleteSource(library.id, id);
            fetchDetails();
          }}
          onDeleteProfile={async (username) => {
            await api.deleteProfileFromLibrary(library.id, username);
            fetchDetails();
          }}
          onBatchDelete={async (ids) => {
            const idList = Array.from(ids);
            const postIds = idList
              .filter((id) => id.startsWith("post-"))
              .map((id) => id.replace("post-", ""));
            const sourceIds = idList
              .filter((id) => id.startsWith("source-"))
              .map((id) => id.replace("source-", ""));

            if (postIds.length > 0) {
              await api
                .deletePostsBulk(library.id, postIds)
                .catch((err) => console.error("Bulk post unlink failed", err));
            }
            if (sourceIds.length > 0) {
              await Promise.all(
                sourceIds.map((sid) =>
                  api.deleteSource(library.id, sid).catch(() => {}),
                ),
              );
            }
            fetchDetails();
          }}
          onRefresh={fetchDetails}
        />
      </div>
    </div>
  );
}

function useLibraryDashboard(library: Library, onLibraryDeleted: () => void) {
  const { t } = useTranslation();
  const [details, setDetails] = useState<LibraryDetails | null>(null);
  const [loading, setLoading] = useState(true);

  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);

  const fetchDetails = useCallback(
    async (signal?: AbortSignal) => {
      try {
        setLoading(true);
        const response = await api.getLibrary(library.id, { signal });
        if (signal?.aborted) return;
        setDetails(response);
      } catch (error) {
        if (!isAbortError(error)) console.error(error);
      } finally {
        setLoading(false);
      }
    },
    [library.id],
  );

  useEffect(() => {
    const controller = new AbortController();
    void fetchDetails(controller.signal);
    return () => controller.abort();
  }, [fetchDetails]);

  const handleSave = async () => {
    try {
      await api.updateLibrary(library.id, editName, editDesc);
      setIsEditing(false);
      fetchDetails();
    } catch {
      alert(t("library.updateFailed"));
    }
  };

  const handleDelete = async () => {
    if (!confirm(t("library.deleteConfirm"))) return;
    try {
      setIsDeleting(true);
      await api.deleteLibrary(library.id);
      onLibraryDeleted();
    } catch {
      alert(t("library.deleteFailed"));
    } finally {
      setIsDeleting(false);
    }
  };

  const tableData = useMemo<ContentItem[]>(() => {
    if (!details?.posts) return [];
    return details.posts.map((post: GlobalPost) => ({
      id: `post-${post.id}`,
      realId: post.id,
      itemType: "post" as const,
      creator: post.creator_username || post.creator || "unknown",
      title: resolvePostTitle(post),
      url: post.url,
      description: post.description,
      extracted_knowledge: post.extracted_knowledge,
      type: post.type || "Reel",
      published_at: post.published_at,
      indexed_at: post.indexed_at,
    }));
  }, [details]);

  const uniqueCreators = useMemo(
    () => new Set(tableData.map((item) => item.creator).filter(Boolean)).size,
    [tableData],
  );

  return {
    t,
    details,
    loading,
    isEditing,
    setIsEditing,
    editName,
    setEditName,
    editDesc,
    setEditDesc,
    isDeleting,
    fetchDetails,
    handleSave,
    handleDelete,
    tableData,
    uniqueCreators,
  };
}
