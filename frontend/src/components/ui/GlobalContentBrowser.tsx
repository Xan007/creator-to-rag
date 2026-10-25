import { useCallback, useEffect, useMemo, useState } from "react";
import { CheckCircle2 } from "lucide-react";
import { api, isAbortError } from "../../lib/api";
import { useTranslation } from "../../lib/i18n";
import type { GlobalPost, Library } from "../../lib/api-types";
import { ContentTable } from "./ContentTable";
import type { ContentItem } from "./ContentTable";

interface GlobalContentBrowserProps {
  libraries: Library[];
  onPlayItem?: (url: string) => void;
  onPostLinked?: () => void;
}

const SEARCH_DEBOUNCE_MS = 300;

export function GlobalContentBrowser({
  libraries,
  onPlayItem,
  onPostLinked,
}: GlobalContentBrowserProps) {
  const { t } = useTranslation();
  const [posts, setPosts] = useState<GlobalPost[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  // Filters & Pagination
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [searchMode, setSearchMode] = useState<"keyword" | "semantic">(
    "keyword",
  );
  const [selectedCreator, setSelectedCreator] = useState<string>("all");
  const [unlinkedOnly, setUnlinkedOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [sortBy, setSortBy] = useState<string | undefined>(undefined);
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [refreshToken, setRefreshToken] = useState(0);
  const [feedback, setFeedback] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  // Creators list for filter dropdown
  const [profiles, setProfiles] = useState<string[]>([]);

  // Debounce the search box: without this every keystroke fired a request.
  useEffect(() => {
    const timer = setTimeout(
      () => setDebouncedSearch(search.trim()),
      SEARCH_DEBOUNCE_MS,
    );
    return () => clearTimeout(timer);
  }, [search]);

  const loadProfiles = useCallback(async (signal?: AbortSignal) => {
    try {
      const data = await api.getProfiles({ signal });
      setProfiles(data.map((profile) => profile.username).filter(Boolean));
    } catch (error) {
      if (!isAbortError(error)) console.error("Failed to load profiles", error);
    }
  }, []);

  const loadPosts = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true);
      try {
        const response = await api.getPosts(
          {
            page,
            page_size: pageSize,
            creator: selectedCreator === "all" ? undefined : selectedCreator,
            unlinked_only: unlinkedOnly || undefined,
            query: debouncedSearch || undefined,
            search_mode: searchMode,
            sort_by: sortBy,
            sort_order: sortOrder,
          },
          { signal },
        );
        if (signal?.aborted) return;
        setPosts(response.items || []);
        setTotal(response.total || 0);
      } catch (error) {
        if (isAbortError(error) || signal?.aborted) return;
        setFeedback({
          type: "error",
          message:
            error instanceof Error ? error.message : t("global.loadPostsError"),
        });
      } finally {
        setLoading(false);
      }
    },
    [
      debouncedSearch,
      page,
      pageSize,
      searchMode,
      selectedCreator,
      sortBy,
      sortOrder,
      t,
      unlinkedOnly,
    ],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadProfiles(controller.signal);
    return () => controller.abort();
  }, [loadProfiles]);

  // Changing filters aborts the previous request, so stale responses can never
  // overwrite the newest one.
  useEffect(() => {
    const controller = new AbortController();
    void loadPosts(controller.signal);
    return () => controller.abort();
  }, [loadPosts, refreshToken]);

  const refresh = useCallback(() => setRefreshToken((token) => token + 1), []);

  const handleLinkToLibrary = async (targetId: string, postIds: string[]) => {
    if (!targetId || postIds.length === 0) return;
    try {
      await api.linkPosts(targetId, postIds);
      const targetLibName =
        libraries.find((library) => library.id === targetId)?.name || "library";
      setFeedback({
        type: "success",
        message: t("global.linkedSuccess", {
          count: postIds.length,
          library: targetLibName,
        }),
      });
      refresh();
      onPostLinked?.();
    } catch (error) {
      setFeedback({
        type: "error",
        message: error instanceof Error ? error.message : t("global.linkError"),
      });
    }
  };

  const handleDeleteSinglePost = async (id: string) => {
    try {
      await api.deleteGlobalPost(id);
      setFeedback({
        type: "success",
        message: t("global.deletedSingleSuccess"),
      });
      refresh();
      onPostLinked?.();
    } catch (error) {
      setFeedback({
        type: "error",
        message:
          error instanceof Error ? error.message : t("global.deleteError"),
      });
    }
  };

  const handleDeleteBulkPosts = async (ids: Set<string>) => {
    try {
      const response = await api.deleteGlobalPostsBulk(Array.from(ids));
      setFeedback({
        type: "success",
        message: t("global.deletedBulkSuccess", {
          count: response.deleted_count || ids.size,
        }),
      });
      refresh();
      onPostLinked?.();
    } catch (error) {
      setFeedback({
        type: "error",
        message:
          error instanceof Error ? error.message : t("global.deleteError"),
      });
    }
  };

  const handleSearchSubmit = useCallback(() => {
    setSortBy(undefined);
    setSortOrder("desc");
    setPage(1);
    setDebouncedSearch(search.trim());
    refresh();
  }, [refresh, search]);

  const tableData = useMemo<ContentItem[]>(
    () =>
      posts.map((post) => ({
        id: post.id,
        realId: post.id,
        itemType: "post",
        creator: post.creator_username || post.creator || "unknown",
        url: post.url,
        title: post.title,
        description: post.description,
        extracted_knowledge: post.extracted_knowledge,
        published_at: post.published_at,
        indexed_at: post.indexed_at,
        library_id: post.library_id,
        type: post.type || "Reel",
        score: post.score,
      })),
    [posts],
  );

  return (
    <div className="max-w-7xl mx-auto p-6 md:p-8 space-y-6 animate-in fade-in zoom-in-95 duration-300">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-slate-900 tracking-tight">
            {t("global.title")}
          </h1>
          <p className="text-sm text-slate-500 mt-1">{t("global.desc")}</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500 bg-slate-100 px-2.5 py-1 rounded-md font-medium">
            {t("global.reelsCount", { count: total })}
          </span>
        </div>
      </div>

      {feedback && (
        <div
          className={`p-3 rounded-lg text-xs md:text-sm flex items-center gap-2 border ${
            feedback.type === "success"
              ? "bg-emerald-50 border-emerald-200 text-emerald-800"
              : "bg-red-50 border-red-200 text-red-800"
          }`}
        >
          <CheckCircle2
            size={15}
            className={
              feedback.type === "success"
                ? "text-emerald-600 shrink-0"
                : "text-red-600 shrink-0"
            }
          />
          <span>{feedback.message}</span>
        </div>
      )}

      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden flex flex-col">
        <ContentTable
          data={tableData}
          deleteMode="permanent"
          showLibraryColumn={true}
          libraries={libraries}
          creators={profiles}
          onDeletePost={handleDeleteSinglePost}
          onBatchDelete={handleDeleteBulkPosts}
          onLinkToLibrary={handleLinkToLibrary}
          onPlayItem={onPlayItem}
          isLoading={loading}
          emptyMessage={t("table.noContent")}
          serverPagination={{
            total,
            page,
            pageSize,
            onPageChange: setPage,
            onPageSizeChange: (newSize) => {
              setPageSize(newSize);
              setPage(1);
            },
            sortBy,
            sortOrder,
            onSortChange: (newSortBy, newSortOrder) => {
              setSortBy(newSortBy);
              setSortOrder(newSortOrder);
              setPage(1);
            },
          }}
          searchQuery={search}
          onSearchChange={(query) => {
            setSearch(query);
            if (!query.trim()) {
              setSortBy(undefined);
              setSortOrder("desc");
              setPage(1);
            }
          }}
          searchMode={searchMode}
          onSearchModeChange={(mode) => {
            setSearchMode(mode);
            setPage(1);
          }}
          onSearchSubmit={handleSearchSubmit}
          creatorFilter={selectedCreator}
          onCreatorFilterChange={(creator) => {
            setSelectedCreator(creator);
            setPage(1);
          }}
          unlinkedOnly={unlinkedOnly}
          onUnlinkedOnlyChange={(value) => {
            setUnlinkedOnly(value);
            setPage(1);
          }}
          onRefresh={refresh}
        />
      </div>
    </div>
  );
}
