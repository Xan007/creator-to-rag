import { useState, useEffect, useCallback } from "react";
import { Modal } from "../ui/Modal";
import { SearchHelpPopover } from "../ui/SearchHelpPopover";
import { api } from "../../lib/api";
import { resolvePostTitle } from "../../lib/utils";
import { useTranslation } from "../../lib/i18n";
import type { GlobalPost, Library, ProfileInfo } from "../../lib/api-types";
import {
  Loader2,
  Search,
  User,
  FileText,
  CheckSquare,
  Square,
  Check,
  ChevronLeft,
  ChevronRight,
  ArrowLeft,
  X,
} from "lucide-react";

interface AddFromGlobalModalProps {
  isOpen: boolean;
  onClose: () => void;
  activeLibrary: Library | null;
  onSuccess?: () => void;
}

function useAddFromGlobalModalModel({
  isOpen,
  onClose,
  activeLibrary,
  onSuccess,
}: AddFromGlobalModalProps) {
  const { t, lang } = useTranslation();
  const [activeTab, setActiveTab] = useState<"profiles" | "posts">("profiles");

  const formatDate = (timestamp?: number | null) => {
    if (!timestamp) return "";
    const ms = timestamp > 1e11 ? timestamp : timestamp * 1000;
    return new Date(ms).toLocaleDateString(lang === "en" ? "en-US" : "es-ES", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  // Library's existing posts (for duplicate prevention)
  const [libraryPostIds, setLibraryPostIds] = useState<Set<string>>(new Set());
  const [libraryPosts, setLibraryPosts] = useState<GlobalPost[]>([]);

  // Profiles tab state
  const [profiles, setProfiles] = useState<ProfileInfo[]>([]);
  const [loadingProfiles, setLoadingProfiles] = useState(false);
  const [selectedProfile, setSelectedProfile] = useState<ProfileInfo | null>(null);

  // Posts state (used for both selectedProfile and global posts tab)
  const [posts, setPosts] = useState<GlobalPost[]>([]);
  const [totalPosts, setTotalPosts] = useState(0);
  const [loadingPosts, setLoadingPosts] = useState(false);
  const [page, setPage] = useState(1);
  const pageSize = 20;

  // Search states
  const [searchQuery, setSearchQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [searchMode, setSearchMode] = useState<"keyword" | "semantic">(
    "keyword",
  );

  // Selection state (persists across page changes)
  const [selectedPostIds, setSelectedPostIds] = useState<Set<string>>(
    new Set(),
  );

  // Linking & Confirmation state
  const [confirmModal, setConfirmModal] = useState<{
    type: "all_profile" | "selected";
    count?: number;
    creator?: string;
  } | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  const loadLibraryPosts = useCallback(async () => {
    if (!activeLibrary) return;
    try {
      const targetLibId = activeLibrary.id || activeLibrary.slug;
      const lib = await api.getLibrary(targetLibId);
      if (lib && lib.posts) {
        setLibraryPosts(lib.posts);
        setLibraryPostIds(new Set(lib.posts.map(p => p.id)));
      }
    } catch (e) {
      console.error("Error fetching library details:", e);
    }
  }, [activeLibrary]);

  const loadProfiles = useCallback(async () => {
    setLoadingProfiles(true);
    try {
      const data = await api.getProfiles();
      setProfiles(data);
    } catch (e) {
      console.error("Error fetching profiles:", e);
    } finally {
      setLoadingProfiles(false);
    }
  }, []);

  const loadPosts = useCallback(
    async (
      pageNum: number,
      queryStr: string,
      mode: "keyword" | "semantic",
      creatorUsername?: string,
    ) => {
      setLoadingPosts(true);
      try {
        const res = await api.getPosts({
          page: pageNum,
          page_size: pageSize,
          creator: creatorUsername || undefined,
          query: queryStr.trim() || undefined,
          search_mode: mode,
        });
        setPosts(res.items || []);
        setTotalPosts(res.total || 0);
      } catch (e) {
        console.error("Error fetching posts:", e);
      } finally {
        setLoadingPosts(false);
      }
    },
    [pageSize],
  );

  // Reset and load on open
  useEffect(() => {
    if (isOpen) {
      loadLibraryPosts();
      loadProfiles();
      loadPosts(1, "", "keyword", undefined);
    }
  }, [isOpen, loadPosts, loadLibraryPosts, loadProfiles]);

  const activeCreatorUsername =
    activeTab === "profiles" && selectedProfile
      ? selectedProfile.username
      : undefined;

  const handleSearchSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setSubmittedQuery(searchQuery);
    setPage(1);
    loadPosts(1, searchQuery, searchMode, activeCreatorUsername);
  };

  const handleSearchModeChange = (newMode: "keyword" | "semantic") => {
    setSearchMode(newMode);
    setPage(1);
    loadPosts(1, submittedQuery, newMode, activeCreatorUsername);
  };

  const handlePageChange = (newPage: number) => {
    setPage(newPage);
    loadPosts(newPage, submittedQuery, searchMode, activeCreatorUsername);
  };

  const handleSelectCreator = (p: ProfileInfo) => {
    setSelectedProfile(p);
    setSearchQuery("");
    setSubmittedQuery("");
    setPage(1);
    loadPosts(1, "", searchMode, p.username);
  };

  const handleBackToProfiles = () => {
    setSelectedProfile(null);
    setSearchQuery("");
    setSubmittedQuery("");
    setPage(1);
  };

  const handleTabChange = (tab: "profiles" | "posts") => {
    setActiveTab(tab);
    setSearchQuery("");
    setSubmittedQuery("");
    setPage(1);
    if (tab === "profiles") {
      setSelectedProfile(null);
    } else {
      loadPosts(1, "", searchMode, undefined);
    }
  };

  // Selection handlers
  const toggleSelectPost = (id: string) => {
    if (libraryPostIds.has(id)) return;
    setSelectedPostIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectableCurrentPageIds = posts
    .filter((p) => !libraryPostIds.has(p.id))
    .map((p) => p.id);
  const allCurrentSelected =
    selectableCurrentPageIds.length > 0 &&
    selectableCurrentPageIds.every((id) => selectedPostIds.has(id));

  const toggleSelectCurrentPage = () => {
    setSelectedPostIds((prev) => {
      const next = new Set(prev);
      if (allCurrentSelected) {
        selectableCurrentPageIds.forEach((id) => next.delete(id));
      } else {
        selectableCurrentPageIds.forEach((id) => next.add(id));
      }
      return next;
    });
  };

  const clearSelection = () => {
    setSelectedPostIds(new Set());
  };

  const handleConfirmLink = async () => {
    if (!activeLibrary || !confirmModal) return;
    setIsSubmitting(true);
    setFeedback(null);
    try {
      if (confirmModal.type === "all_profile" && confirmModal.creator) {
        await api.linkProfile(activeLibrary.id, confirmModal.creator);
        setFeedback({
          type: "success",
          message: t("addFromGlobal.linkProfileSuccess", {
            creator: confirmModal.creator,
          }),
        });
      } else if (confirmModal.type === "selected") {
        const ids = Array.from(selectedPostIds).filter(
          (id) => !libraryPostIds.has(id),
        );
        if (ids.length > 0) {
          await api.linkPosts(activeLibrary.id, ids);
          setFeedback({
            type: "success",
            message: t("addFromGlobal.linkSelectedSuccess", {
              count: ids.length,
            }),
          });
        } else {
          setFeedback({
            type: "success",
            message: t("addFromGlobal.alreadyLinked"),
          });
        }
      }
      setConfirmModal(null);
      await loadLibraryPosts();
      setTimeout(() => {
        onSuccess?.();
        onClose();
      }, 1000);
    } catch (e: any) {
      console.error("Error linking posts:", e);
      setFeedback({
        type: "error",
        message: e?.message || t("addFromGlobal.linkError"),
      });
      setConfirmModal(null);
    } finally {
      setIsSubmitting(false);
    }
  };

  const totalPages = Math.ceil(totalPosts / pageSize) || 1;

  return {
    isOpen,
    onClose,
    activeLibrary,
    t,
    activeTab,
    formatDate,
    libraryPostIds,
    libraryPosts,
    profiles,
    loadingProfiles,
    selectedProfile,
    posts,
    totalPosts,
    loadingPosts,
    page,
    setPage,
    searchQuery,
    setSearchQuery,
    setSubmittedQuery,
    searchMode,
    selectedPostIds,
    confirmModal,
    setConfirmModal,
    isSubmitting,
    feedback,
    loadPosts,
    activeCreatorUsername,
    handleSearchSubmit,
    handleSearchModeChange,
    handlePageChange,
    handleSelectCreator,
    handleBackToProfiles,
    handleTabChange,
    toggleSelectPost,
    selectableCurrentPageIds,
    allCurrentSelected,
    toggleSelectCurrentPage,
    clearSelection,
    handleConfirmLink,
    totalPages,
  };
}

function GlobalPickerDialog({
  model,
}: {
  model: ReturnType<typeof useAddFromGlobalModalModel>;
}) {
  const { isOpen, onClose, t } = model;
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={t("addFromGlobal.title")}
      className="max-w-3xl"
    >
      <GlobalPickerContent model={model} />
    </Modal>
  );
}

export function AddFromGlobalModal(
  props: Parameters<typeof useAddFromGlobalModalModel>[0],
) {
  return props.isOpen ? (
    <GlobalLibraryPicker key={props.activeLibrary?.id} {...props} />
  ) : null;
}

function GlobalLibraryPicker(
  props: Parameters<typeof useAddFromGlobalModalModel>[0],
) {
  const model = useAddFromGlobalModalModel(props);
  return <GlobalPickerDialog model={model} />;
}

function PostSearchToolbar({
  model,
}: {
  model: ReturnType<typeof useAddFromGlobalModalModel>;
}) {
  const {
    t,
    searchMode,
    selectableCurrentPageIds,
    toggleSelectCurrentPage,
    allCurrentSelected,
  } = model;
  return (
    <div className="relative z-20 flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
      <PostSearchForm model={model} />

      <SearchHelpPopover currentMode={searchMode} align="right" />

      <PostSearchMode model={model} />

      {selectableCurrentPageIds.length > 0 && (
        <button
          type="button"
          onClick={toggleSelectCurrentPage}
          className="px-2.5 py-1.5 text-xs font-medium border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-700 shrink-0 cursor-pointer"
        >
          {allCurrentSelected
            ? t("addFromGlobal.deselectPage")
            : t("addFromGlobal.selectPage")}
        </button>
      )}
    </div>
  );
}

function GlobalPostBrowser({
  model,
}: {
  model: ReturnType<typeof useAddFromGlobalModalModel>;
}) {
  const {
    activeTab,
    selectedProfile,
    totalPosts,
    libraryPosts,
    handleBackToProfiles,
    t,
    setConfirmModal,
    page,
    totalPages,
    loadingPosts,
    handlePageChange,
    selectedPostIds,
    clearSelection,
    isSubmitting,
  } = model;
  return (
    <>
      {" "}
      {((activeTab === "profiles" && selectedProfile) ||
        activeTab === "posts") && (
        <div className="space-y-3">
          {activeTab === "profiles" &&
            selectedProfile &&
            (() => {
              const creatorTotal =
                selectedProfile.total_posts_scraped ||
                selectedProfile.total_posts ||
                totalPosts;
              const creatorInLib = libraryPosts.filter(
                (post: any) =>
                  (
                    post.creator_username ||
                    post.creator ||
                    ""
                  ).toLowerCase() === selectedProfile.username.toLowerCase(),
              ).length;
              const creatorRemaining = Math.max(0, creatorTotal - creatorInLib);
              const isAllLinked = creatorTotal > 0 && creatorRemaining === 0;

              return (
                <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                  <button
                    type="button"
                    onClick={handleBackToProfiles}
                    className="text-xs text-slate-500 hover:text-slate-900 flex items-center gap-1 font-medium transition-colors cursor-pointer"
                  >
                    <ArrowLeft size={13} />
                    <span>{t("addFromGlobal.backToCreators")}</span>
                  </button>
                  <div className="flex items-center gap-3">
                    <span className="text-xs font-semibold text-slate-800">
                      {t("addFromGlobal.creatorSummary", {
                        creator: selectedProfile.username,
                        total: creatorTotal,
                        inLib:
                          creatorInLib > 0
                            ? t("addFromGlobal.inLibSuffix", {
                                count: creatorInLib,
                              })
                            : "",
                      })}
                    </span>
                    <button
                      type="button"
                      disabled={isAllLinked}
                      onClick={() =>
                        setConfirmModal({
                          type: "all_profile",
                          creator: selectedProfile.username,
                          count: creatorRemaining,
                        })
                      }
                      className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                        isAllLinked
                          ? "bg-slate-100 text-slate-400 cursor-not-allowed"
                          : "text-slate-700 bg-slate-100 hover:bg-slate-200 cursor-pointer"
                      }`}
                    >
                      {isAllLinked
                        ? t("addFromGlobal.allLinked")
                        : creatorInLib > 0
                          ? t("addFromGlobal.linkRemaining", {
                              count: creatorRemaining,
                            })
                          : t("addFromGlobal.linkAll")}
                    </button>
                  </div>
                </div>
              );
            })()}

          <PostSearchToolbar model={model} />

          <SelectablePosts model={model} />

          <div className="flex items-center justify-between pt-2 border-t border-slate-100 text-xs text-slate-500">
            <div className="flex items-center gap-2">
              <span>{t("addFromGlobal.pageOf", { page, totalPages })}</span>
              <span className="text-slate-300">|</span>
              <span>
                {t("addFromGlobal.totalPostsCount", { count: totalPosts })}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                disabled={page <= 1 || loadingPosts}
                onClick={() => handlePageChange(page - 1)}
                className="px-2.5 py-1 border border-slate-200 rounded-md hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors font-medium flex items-center gap-1 text-slate-700 cursor-pointer"
              >
                <ChevronLeft size={13} />
                <span>{t("addFromGlobal.prev")}</span>
              </button>
              <button
                type="button"
                disabled={page >= totalPages || loadingPosts}
                onClick={() => handlePageChange(page + 1)}
                className="px-2.5 py-1 border border-slate-200 rounded-md hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors font-medium flex items-center gap-1 text-slate-700 cursor-pointer"
              >
                <span>{t("addFromGlobal.next")}</span>
                <ChevronRight size={13} />
              </button>
            </div>
          </div>

          <div className="flex justify-between items-center pt-2 border-t border-slate-100">
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <span>
                {t("addFromGlobal.selectedPostsCount", {
                  count: selectedPostIds.size,
                })}
              </span>
              {selectedPostIds.size > 0 && (
                <button
                  type="button"
                  onClick={clearSelection}
                  className="text-xs text-slate-400 hover:text-slate-600 underline cursor-pointer"
                >
                  {t("addFromGlobal.clearSelection")}
                </button>
              )}
            </div>
            <button
              type="button"
              onClick={() =>
                setConfirmModal({
                  type: "selected",
                  count: selectedPostIds.size,
                })
              }
              disabled={selectedPostIds.size === 0 || isSubmitting}
              className="px-4 py-2 bg-slate-900 text-white rounded-lg text-xs font-medium hover:bg-slate-800 disabled:opacity-50 transition-colors flex items-center gap-2 cursor-pointer"
            >
              {isSubmitting && <Loader2 size={13} className="animate-spin" />}
              {t("addFromGlobal.linkSelected", { count: selectedPostIds.size })}
            </button>
          </div>
        </div>
      )}{" "}
    </>
  );
}

function LinkConfirmation({
  model,
}: {
  model: ReturnType<typeof useAddFromGlobalModalModel>;
}) {
  const {
    confirmModal,
    t,
    activeLibrary,
    isSubmitting,
    setConfirmModal,
    handleConfirmLink,
  } = model;
  return (
    <>
      {" "}
      {confirmModal && (
        <div className="fixed inset-0 z-[60] bg-black/40 flex items-center justify-center p-4 animate-in fade-in">
          <div className="bg-white rounded-xl max-w-sm w-full p-5 shadow-xl border border-slate-200 space-y-4">
            <div className="space-y-1.5">
              <h4 className="text-base font-semibold text-slate-900">
                {t("addFromGlobal.confirmTitle")}
              </h4>
              <p className="text-xs text-slate-600 leading-relaxed">
                {confirmModal.type === "all_profile"
                  ? t("addFromGlobal.confirmProfileDesc", {
                      count: confirmModal.count,
                      creator: confirmModal.creator,
                      library: activeLibrary?.name || "",
                    })
                  : t("addFromGlobal.confirmSelectedDesc", {
                      count: confirmModal.count,
                      library: activeLibrary?.name || "",
                    })}
              </p>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                disabled={isSubmitting}
                onClick={() => setConfirmModal(null)}
                className="px-3.5 py-1.5 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors cursor-pointer"
              >
                {t("addFromGlobal.cancel")}
              </button>
              <button
                type="button"
                disabled={isSubmitting}
                onClick={handleConfirmLink}
                className="px-3.5 py-1.5 text-xs font-medium text-white bg-slate-900 hover:bg-slate-800 rounded-lg transition-colors flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
              >
                {isSubmitting && <Loader2 size={12} className="animate-spin" />}
                <span>{t("addFromGlobal.confirmAndLink")}</span>
              </button>
            </div>
          </div>
        </div>
      )}{" "}
    </>
  );
}

function GlobalPickerContent({
  model,
}: {
  model: ReturnType<typeof useAddFromGlobalModalModel>;
}) {
  const { feedback, handleTabChange, activeTab, t, profiles } = model;
  return (
    <div className="space-y-4">
      {feedback && (
        <div
          className={`p-3 rounded-lg text-xs md:text-sm flex items-center gap-2 border ${
            feedback.type === "success"
              ? "bg-emerald-50 border-emerald-200 text-emerald-800"
              : "bg-red-50 border-red-200 text-red-800"
          }`}
        >
          <Check size={15} className="shrink-0" />
          <span>{feedback.message}</span>
        </div>
      )}

      <div className="flex border-b border-slate-200 gap-6 text-sm font-medium">
        <button
          type="button"
          onClick={() => handleTabChange("profiles")}
          className={`pb-2.5 transition-colors border-b-2 flex items-center gap-2 cursor-pointer ${
            activeTab === "profiles"
              ? "border-slate-900 text-slate-900 font-semibold"
              : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          <User size={15} />
          {t("addFromGlobal.tabCreators", { count: profiles.length })}
        </button>
        <button
          type="button"
          onClick={() => handleTabChange("posts")}
          className={`pb-2.5 transition-colors border-b-2 flex items-center gap-2 cursor-pointer ${
            activeTab === "posts"
              ? "border-slate-900 text-slate-900 font-semibold"
              : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          <FileText size={15} />
          {t("addFromGlobal.tabPosts")}
        </button>
      </div>

      <CreatorList model={model} />

      <GlobalPostBrowser model={model} />

      <LinkConfirmation model={model} />
    </div>
  );
}

function PostSearchForm({
  model,
}: {
  model: ReturnType<typeof useAddFromGlobalModalModel>;
}) {
  const {
    handleSearchSubmit,
    activeTab,
    selectedProfile,
    t,
    searchQuery,
    setSearchQuery,
    setSubmittedQuery,
    setPage,
    loadPosts,
    searchMode,
    activeCreatorUsername,
  } = model;
  return (
    <form onSubmit={handleSearchSubmit} className="relative flex-1">
      <Search size={14} className="absolute left-3 top-2.5 text-slate-400" />
      <input
        aria-label={
          activeTab === "profiles" && selectedProfile
            ? t("addFromGlobal.searchCreatorPosts", {
                creator: selectedProfile.username,
              })
            : t("addFromGlobal.searchGlobalPosts")
        }
        type="text"
        placeholder={
          activeTab === "profiles" && selectedProfile
            ? t("addFromGlobal.searchCreatorPosts", {
                creator: selectedProfile.username,
              })
            : t("addFromGlobal.searchGlobalPosts")
        }
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        className="w-full pl-9 pr-8 py-1.5 text-xs sm:text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-900"
      />
      {searchQuery && (
        <button
          aria-label={t("modal.cancel")}
          type="button"
          onClick={() => {
            setSearchQuery("");
            setSubmittedQuery("");
            setPage(1);
            loadPosts(1, "", searchMode, activeCreatorUsername);
          }}
          className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-600 cursor-pointer"
        >
          <X size={14} />
        </button>
      )}
    </form>
  );
}

function PostSearchMode({
  model,
}: {
  model: ReturnType<typeof useAddFromGlobalModalModel>;
}) {
  const { handleSearchModeChange, searchMode, t } = model;
  return (
    <div className="flex items-center gap-1 bg-slate-100 p-0.5 rounded-lg border border-slate-200 shrink-0">
      <button
        type="button"
        onClick={() => handleSearchModeChange("keyword")}
        className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors cursor-pointer ${
          searchMode === "keyword"
            ? "bg-white text-slate-900 shadow-xs"
            : "text-slate-500 hover:text-slate-800"
        }`}
        title={t("addFromGlobal.exactMatchTooltip")}
      >
        {t("addFromGlobal.exactMatch")}
      </button>
      <button
        type="button"
        onClick={() => handleSearchModeChange("semantic")}
        className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors cursor-pointer ${
          searchMode === "semantic"
            ? "bg-white text-slate-900 shadow-xs"
            : "text-slate-500 hover:text-slate-800"
        }`}
        title={t("addFromGlobal.semanticMatchTooltip")}
      >
        {t("addFromGlobal.semanticMatch")}
      </button>
    </div>
  );
}

function CreatorList({
  model,
}: {
  model: ReturnType<typeof useAddFromGlobalModalModel>;
}) {
  const {
    activeTab,
    selectedProfile,
    t,
    loadingProfiles,
    profiles,
    libraryPosts,
    handleSelectCreator,
    setConfirmModal,
  } = model;
  return (
    <>
      {" "}
      {activeTab === "profiles" && !selectedProfile && (
        <div className="space-y-3">
          <p className="text-xs text-slate-500">
            {t("addFromGlobal.creatorsHint")}
          </p>

          {loadingProfiles ? (
            <div className="py-12 flex flex-col items-center justify-center gap-2 text-slate-400">
              <Loader2 className="animate-spin" size={24} />
              <span className="text-xs">
                {t("addFromGlobal.loadingProfiles")}
              </span>
            </div>
          ) : profiles.length === 0 ? (
            <div className="py-12 text-center text-sm text-slate-500 border border-dashed border-slate-200 rounded-lg">
              {t("addFromGlobal.noProfiles")}
            </div>
          ) : (
            <div className="border border-slate-200 rounded-lg overflow-hidden divide-y divide-slate-100 max-h-[380px] overflow-y-auto">
              {profiles.map((p) => {
                const totalCount =
                  p.total_posts_scraped ||
                  p.total_posts ||
                  p.processed_count ||
                  0;
                const inLibraryCount = libraryPosts.filter(
                  (post: any) =>
                    (
                      post.creator_username ||
                      post.creator ||
                      ""
                    ).toLowerCase() === p.username.toLowerCase(),
                ).length;
                const availableCount = Math.max(0, totalCount - inLibraryCount);
                const isAllLinked = totalCount > 0 && availableCount === 0;

                return (
                  <div
                    key={p.username}
                    className="flex items-center justify-between p-3.5 hover:bg-slate-50 transition-colors"
                  >
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
                      onClick={() => handleSelectCreator(p)}
                      className="flex items-center gap-3 cursor-pointer flex-1 min-w-0"
                    >
                      <div className="w-9 h-9 bg-slate-100 rounded-full flex items-center justify-center text-slate-600 shrink-0 font-semibold text-xs">
                        @{p.username.slice(0, 2).toUpperCase()}
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-slate-900 hover:underline">
                          @{p.username}
                        </p>
                        <p className="text-xs text-slate-500 flex items-center gap-1.5 flex-wrap">
                          <span>
                            {t("addFromGlobal.postsTotal", {
                              count: totalCount,
                            })}
                          </span>
                          {inLibraryCount > 0 && (
                            <span className="text-slate-400">
                              {t("addFromGlobal.inThisLibrary", {
                                count: inLibraryCount,
                              })}
                            </span>
                          )}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        type="button"
                        onClick={() => handleSelectCreator(p)}
                        className="px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-300 hover:bg-slate-50 rounded-md transition-colors cursor-pointer"
                      >
                        {t("addFromGlobal.viewSelectPosts")}
                      </button>
                      <button
                        type="button"
                        disabled={isAllLinked}
                        onClick={() =>
                          setConfirmModal({
                            type: "all_profile",
                            creator: p.username,
                            count: availableCount,
                          })
                        }
                        className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                          isAllLinked
                            ? "bg-slate-100 text-slate-400 cursor-not-allowed"
                            : "bg-slate-900 text-white hover:bg-slate-800 cursor-pointer"
                        }`}
                      >
                        {isAllLinked
                          ? t("addFromGlobal.allLinked")
                          : inLibraryCount > 0
                            ? t("addFromGlobal.linkRemaining", {
                                count: availableCount,
                              })
                            : t("addFromGlobal.linkAll")}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}{" "}
    </>
  );
}

function SelectablePosts({
  model,
}: {
  model: ReturnType<typeof useAddFromGlobalModalModel>;
}) {
  const {
    loadingPosts,
    t,
    posts,
    libraryPostIds,
    selectedPostIds,
    toggleSelectPost,
    formatDate,
  } = model;
  return (
    <>
      {" "}
      {loadingPosts ? (
        <div className="py-12 flex flex-col items-center justify-center gap-2 text-slate-400">
          <Loader2 className="animate-spin" size={24} />
          <span className="text-xs">{t("addFromGlobal.searchingPosts")}</span>
        </div>
      ) : posts.length === 0 ? (
        <div className="py-12 text-center text-sm text-slate-500 border border-dashed border-slate-200 rounded-lg">
          {t("addFromGlobal.noMatchingPosts")}
        </div>
      ) : (
        <div className="border border-slate-200 rounded-lg overflow-hidden divide-y divide-slate-100 max-h-[320px] overflow-y-auto">
          {posts.map((p) => {
            const isAlreadyInLibrary = libraryPostIds.has(p.id);
            const isSelected = selectedPostIds.has(p.id);
            const displayTitle = resolvePostTitle(p);
            const creator = p.creator_username || p.creator || "unknown";

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
                onClick={() => {
                  if (!isAlreadyInLibrary) toggleSelectPost(p.id);
                }}
                className={`flex items-start gap-3 p-3 transition-colors ${
                  isAlreadyInLibrary
                    ? "bg-slate-50/40 cursor-not-allowed opacity-60"
                    : `hover:bg-slate-50 cursor-pointer ${isSelected ? "bg-slate-50/90" : ""}`
                }`}
              >
                <div className="mt-0.5 shrink-0">
                  {isAlreadyInLibrary ? (
                    <Check size={16} className="text-slate-400" />
                  ) : isSelected ? (
                    <CheckSquare size={16} className="text-slate-900" />
                  ) : (
                    <Square size={16} className="text-slate-400" />
                  )}
                </div>
                <div className="min-w-0 flex-1 text-xs">
                  <div className="flex items-center gap-2 text-slate-800 mb-0.5">
                    <span className="font-semibold text-slate-900">
                      @{creator}
                    </span>
                    <span className="text-[10px] text-slate-500 uppercase font-mono">
                      {p.type || "REEL"}
                    </span>
                    {(p.published_at || p.indexed_at) && (
                      <span className="text-[10px] text-slate-400">
                        {formatDate(p.published_at || p.indexed_at)}
                      </span>
                    )}
                    {isAlreadyInLibrary && (
                      <span className="text-[11px] text-slate-400 font-normal">
                        {t("addFromGlobal.alreadyInLib")}
                      </span>
                    )}
                    {p.score !== undefined && (
                      <span className="text-[10px] text-slate-400 ml-auto">
                        score: {p.score}
                      </span>
                    )}
                  </div>
                  <p className="font-medium text-slate-900 text-xs line-clamp-1 mb-0.5">
                    {displayTitle}
                  </p>
                  <p className="text-slate-500 text-[11px] line-clamp-2 leading-relaxed">
                    {p.description || p.extracted_knowledge || p.url}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      )}{" "}
    </>
  );
}
