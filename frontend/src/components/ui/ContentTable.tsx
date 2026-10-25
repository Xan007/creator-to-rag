import {
  lazy,
  Suspense,
  useCallback,
  useDeferredValue,
  useMemo,
  useState,
  type FormEvent,
} from "react";
import {
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Trash2,
  Search,
  X,
  Eye,
  Globe,
  FolderPlus,
  Loader2,
  RefreshCw,
} from "lucide-react";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getPaginationRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
  type ColumnSizingState,
  type OnChangeFn,
} from "@tanstack/react-table";
import { resolvePostTitle, cn } from "../../lib/utils";
import { matchesSearchQuery } from "../../lib/search-parser";
import { SearchHelpPopover } from "./SearchHelpPopover";
import { useTranslation } from "../../lib/i18n";

// The details sheet and dialogs pull in the markdown renderer and Radix
// primitives; only download them when the user actually opens them.
const ContentDetailSheet = lazy(() =>
  import("./ContentDetailSheet").then((module) => ({
    default: module.ContentDetailSheet,
  })),
);
const ConfirmDialog = lazy(() =>
  import("./ConfirmDialog").then((module) => ({
    default: module.ConfirmDialog,
  })),
);

export interface ContentItem {
  id: string;
  realId: string;
  itemType: "post" | "source";
  creator: string;
  url: string;
  title?: string;
  description?: string;
  extracted_knowledge?: string;
  platform?: string;
  type?: string;
  score?: number;
  published_at?: number | null;
  indexed_at?: number;
  status?: string;
  ingest_status?: string;
  library_id?: string | null;
}

export interface ContentTableProps {
  data: ContentItem[];
  onDeletePost?: (id: string) => Promise<void>;
  onDeleteSource?: (id: string) => Promise<void>;
  onDeleteProfile?: (username: string) => Promise<void>;
  onBatchDelete?: (ids: Set<string>) => Promise<void>;
  deleteMode?: "library" | "permanent";
  showFilters?: boolean;
  emptyMessage?: string;
  onPlayItem?: (url: string) => void;
  isLoading?: boolean;

  // Global library integration
  showLibraryColumn?: boolean;
  libraries?: { id: string; name: string }[];
  onLinkToLibrary?: (
    targetLibraryId: string,
    postIds: string[],
  ) => Promise<void>;

  // External / Server-controlled filtering & pagination
  serverPagination?: {
    total: number;
    page: number;
    pageSize: number;
    onPageChange: (page: number) => void;
    onPageSizeChange?: (size: number) => void;
    sortBy?: string;
    sortOrder?: "asc" | "desc";
    onSortChange?: (
      sortBy: string | undefined,
      sortOrder: "asc" | "desc",
    ) => void;
  };
  searchQuery?: string;
  onSearchChange?: (q: string) => void;
  onSearchSubmit?: () => void;
  searchMode?: "keyword" | "semantic";
  onSearchModeChange?: (mode: "keyword" | "semantic") => void;
  creatorFilter?: string;
  onCreatorFilterChange?: (creator: string) => void;
  creators?: string[];
  unlinkedOnly?: boolean;
  onUnlinkedOnlyChange?: (val: boolean) => void;
  onRefresh?: () => void;
}

interface ContentTableMeta {
  selectedIds: Set<string>;
  toggleRow: (id: string) => void;
  setVisibleRowsSelected: (ids: string[], selected: boolean) => void;
}

function InstagramIcon({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect width="20" height="20" x="2" y="2" rx="5" ry="5" />
      <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" />
      <line x1="17.5" x2="17.51" y1="6.5" y2="6.5" />
    </svg>
  );
}

function TikTokIcon({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 0 1-5.2 1.74 2.89 2.89 0 0 1 2.31-4.64 2.93 2.93 0 0 1 .88.13V9.4a6.84 6.84 0 0 0-1-.05A6.33 6.33 0 0 0 3 15.68 6.34 6.34 0 0 0 9.37 22a6.33 6.33 0 0 0 6.32-6.32V8.71a8.21 8.21 0 0 0 4.9 1.6V6.86a4.83 4.83 0 0 1-1-.17z" />
    </svg>
  );
}

function PlatformIcon({
  url,
  platform,
  className = "w-4 h-4",
}: {
  url?: string;
  platform?: string;
  className?: string;
}) {
  const target = (platform || url || "").toLowerCase();
  if (target.includes("instagram") || target.includes("ig")) {
    return <InstagramIcon className={className} />;
  }
  if (target.includes("tiktok")) {
    return <TikTokIcon className={className} />;
  }
  return <Globe className={className} />;
}

function useContentTableModel({
  data,
  onDeletePost,
  onDeleteSource,
  onDeleteProfile,
  onBatchDelete,
  deleteMode = "library",
  showFilters = true,
  emptyMessage = "No content found in this library",
  onPlayItem,
  isLoading = false,
  showLibraryColumn = false,
  libraries,
  onLinkToLibrary,
  serverPagination,
  searchQuery,
  onSearchChange,
  onSearchSubmit,
  searchMode,
  onSearchModeChange,
  creatorFilter,
  onCreatorFilterChange,
  creators,
  unlinkedOnly,
  onUnlinkedOnlyChange,
  onRefresh,
}: ContentTableProps) {
  const { t, lang } = useTranslation();
  // Selected item for the side sheet
  const [activeItem, setActiveItem] = useState<ContentItem | null>(null);

  // Table selection
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const toggleRow = useCallback((id: string) => {
    setSelectedIds((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const setVisibleRowsSelected = useCallback(
    (ids: string[], selected: boolean) => {
      setSelectedIds((previous) => {
        const next = new Set(previous);
        ids.forEach((id) => (selected ? next.add(id) : next.delete(id)));
        return next;
      });
    },
    [],
  );

  // Local search & filter states (used when not controlled by parent)
  const [localSearchQuery, setLocalSearchQuery] = useState("");
  const [localSearchMode, setLocalSearchMode] = useState<
    "keyword" | "semantic"
  >("keyword");
  const [localCreatorFilter, setLocalCreatorFilter] = useState<string>("all");

  // Local pagination (used when serverPagination is not provided)
  const [localPage, setLocalPage] = useState(1);
  const [localPageSize, setLocalPageSize] = useState(25);

  const effectiveSearchQuery =
    searchQuery !== undefined ? searchQuery : localSearchQuery;
  const effectiveSearchMode =
    searchMode !== undefined ? searchMode : localSearchMode;
  const effectiveCreatorFilter =
    creatorFilter !== undefined ? creatorFilter : localCreatorFilter;

  // Sorting & Column Sizing State (TanStack Table)
  const isServerSorting = !!serverPagination?.onSortChange;

  const [internalSorting, setInternalSorting] = useState<SortingState>(() => {
    // If not searching, default to date desc; if searching, default to natural relevance order
    return effectiveSearchQuery ? [] : [{ id: "date", desc: true }];
  });

  const sorting: SortingState = useMemo(() => {
    if (isServerSorting) {
      if (serverPagination.sortBy) {
        return [
          {
            id: serverPagination.sortBy,
            desc: serverPagination.sortOrder === "desc",
          },
        ];
      }
      return [];
    }
    return internalSorting;
  }, [
    isServerSorting,
    serverPagination?.sortBy,
    serverPagination?.sortOrder,
    internalSorting,
  ]);

  const handleSortingChange: OnChangeFn<SortingState> = (updaterOrValue) => {
    const nextSorting =
      typeof updaterOrValue === "function"
        ? updaterOrValue(sorting)
        : updaterOrValue;
    setInternalSorting(nextSorting);

    if (serverPagination?.onSortChange) {
      if (nextSorting && nextSorting.length > 0) {
        const top = nextSorting[0];
        serverPagination.onSortChange(top.id, top.desc ? "desc" : "asc");
      } else {
        serverPagination.onSortChange(undefined, "desc");
      }
    }
  };

  const [columnSizing, setColumnSizing] = useState<ColumnSizingState>({
    select: 44,
    reel: 440,
    creator: 140,
    library: 120,
    date: 160,
    actions: 90,
  });

  // Bulk library linking state
  const [bulkTargetLibrary, setBulkTargetLibrary] = useState<string>("");
  const [isLinking, setIsLinking] = useState(false);

  // Confirmation modal states
  const [itemToDelete, setItemToDelete] = useState<{
    id: string;
    type: string;
    title: string;
  } | null>(null);
  const [showBatchDeleteModal, setShowBatchDeleteModal] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const handleModeChange = (mode: "keyword" | "semantic") => {
    if (onSearchModeChange) {
      onSearchModeChange(mode);
    } else {
      setLocalSearchMode(mode);
    }
  };

  const allCreators = useMemo(() => {
    if (creators && creators.length > 0) return creators;
    return Array.from(new Set(data.map((d) => d.creator))).filter(Boolean);
  }, [creators, data]);

  const libraryMap = useMemo(() => {
    const map = new Map<string, string>();
    (libraries || []).forEach((l) => map.set(l.id, l.name));
    return map;
  }, [libraries]);

  const formatDate = useCallback(
    (timestamp?: number | null) => {
      if (!timestamp) return "—";
      try {
        const date = new Date(timestamp * 1000);
        return date.toLocaleDateString(lang === "en" ? "en-US" : "es-ES", {
          month: "short",
          day: "numeric",
          year: "numeric",
        });
      } catch {
        return "—";
      }
    },
    [lang],
  );

  const hasActions = !!onDeletePost || !!onDeleteSource || !!onBatchDelete;

  // Keep typing responsive on large client-side filtered lists.
  const deferredSearchQuery = useDeferredValue(effectiveSearchQuery);

  // Local filtering (applied when serverPagination is not active)
  const localFilteredData = useMemo(() => {
    if (serverPagination) {
      return data;
    }

    let result = [...data];
    if (deferredSearchQuery.trim()) {
      result = result.filter((item) =>
        matchesSearchQuery(item, deferredSearchQuery),
      );
    }
    if (showFilters && effectiveCreatorFilter !== "all") {
      result = result.filter((item) => item.creator === effectiveCreatorFilter);
    }
    return result;
  }, [
    data,
    serverPagination,
    deferredSearchQuery,
    effectiveCreatorFilter,
    showFilters,
  ]);

  // Column definitions for TanStack Table
  const columns = useMemo<ColumnDef<ContentItem>[]>(() => {
    const cols: ColumnDef<ContentItem>[] = [];

    // Checkbox column
    if (hasActions) {
      cols.push({
        id: "select",
        size: 44,
        minSize: 44,
        maxSize: 44,
        enableResizing: false,
        enableSorting: false,
        header: ({ table }) => {
          const meta = table.options.meta as ContentTableMeta;
          const currentRows = table.getRowModel().rows;
          const isAllSelected =
            currentRows.length > 0 &&
            currentRows.every((r) => meta.selectedIds.has(r.original.id));
          return (
            <div className="flex items-center justify-center">
              <input
                type="checkbox"
                className="rounded border-slate-300 text-slate-900 focus:ring-slate-900 w-4 h-4 cursor-pointer"
                checked={isAllSelected}
                onChange={(e) => {
                  meta.setVisibleRowsSelected(
                    currentRows.map((r) => r.original.id),
                    e.target.checked,
                  );
                }}
                title={t("table.selectAllPage")}
              />
            </div>
          );
        },
        cell: ({ row, table }) => {
          const meta = table.options.meta as ContentTableMeta;
          return (
            <div className="flex items-center justify-center">
              <input
                aria-label={t("table.selectAllPage")}
                type="checkbox"
                className="rounded border-slate-300 text-slate-900 focus:ring-slate-900 w-4 h-4 cursor-pointer"
                checked={meta.selectedIds.has(row.original.id)}
                onChange={() => meta.toggleRow(row.original.id)}
              />
            </div>
          );
        },
      });
    }

    // Reel column (Title + Platform)
    cols.push({
      id: "reel",
      accessorFn: (item) => resolvePostTitle(item),
      header: () => t("table.reel"),
      size: 440,
      minSize: 220,
      maxSize: 850,
      enableResizing: true,
      enableSorting: true,
      sortingFn: (rowA, rowB) => {
        const titleA = resolvePostTitle(rowA.original).toLowerCase();
        const titleB = resolvePostTitle(rowB.original).toLowerCase();
        return titleA.localeCompare(titleB);
      },
      cell: ({ row }) => {
        const item = row.original;
        const displayTitle = resolvePostTitle(item);
        const scoreTooltip =
          typeof item.score === "number" && item.score > 0
            ? t("table.relevance", {
                title: displayTitle,
                percent: Math.round(item.score * 100),
              })
            : displayTitle;

        return (
          <div className="flex items-center gap-2.5 min-w-0 pr-3">
            <span className="text-slate-400 group-hover:text-slate-900 transition-colors shrink-0">
              <PlatformIcon
                url={item.url}
                platform={item.platform}
                className="w-4 h-4"
              />
            </span>
            <span
              className="font-medium text-slate-900 group-hover:text-blue-600 transition-colors truncate"
              title={scoreTooltip}
            >
              {displayTitle}
            </span>
          </div>
        );
      },
    });

    // Creator column
    cols.push({
      id: "creator",
      accessorKey: "creator",
      header: () => t("table.creator"),
      size: 140,
      minSize: 100,
      maxSize: 260,
      enableResizing: true,
      enableSorting: true,
      cell: ({ row }) => (
        <span
          className="text-slate-600 font-normal truncate block"
          title={`@${row.original.creator}`}
        >
          @{row.original.creator}
        </span>
      ),
    });

    // Library column (Optional)
    if (showLibraryColumn) {
      cols.push({
        id: "library",
        header: () => t("table.library"),
        size: 130,
        minSize: 90,
        maxSize: 220,
        enableResizing: true,
        enableSorting: false,
        cell: ({ row }) => {
          const item = row.original;
          const assignedLibName = item.library_id
            ? libraryMap.get(item.library_id)
            : null;
          return (
            <div
              className="text-xs truncate"
              title={assignedLibName || t("table.unlinked")}
            >
              {assignedLibName ? (
                <span className="text-slate-700 font-medium truncate block">
                  {assignedLibName}
                </span>
              ) : (
                <span className="text-slate-400 italic">
                  {t("table.unlinked")}
                </span>
              )}
            </div>
          );
        },
      });
    }

    // Date column (Published + Indexed dates with generous spacing)
    cols.push({
      id: "date",
      accessorFn: (item) => item.published_at || item.indexed_at || 0,
      header: () => t("table.date"),
      size: 160,
      minSize: 140,
      maxSize: 240,
      enableResizing: true,
      enableSorting: true,
      sortingFn: (rowA, rowB) => {
        const timeA =
          rowA.original.published_at || rowA.original.indexed_at || 0;
        const timeB =
          rowB.original.published_at || rowB.original.indexed_at || 0;
        return timeA - timeB;
      },
      cell: ({ row }) => {
        const item = row.original;
        return (
          <div className="text-xs whitespace-nowrap pr-4">
            {item.published_at ? (
              <div className="flex flex-col">
                <span
                  className="text-slate-700 font-medium"
                  title={t("sheet.published")}
                >
                  {formatDate(item.published_at)}
                </span>
                <span
                  className="text-[10px] text-slate-400 font-mono"
                  title={t("sheet.indexed")}
                >
                  {t("table.indexedDate", {
                    date: formatDate(item.indexed_at),
                  })}
                </span>
              </div>
            ) : (
              <span className="text-slate-500 font-medium">
                {formatDate(item.indexed_at)}
              </span>
            )}
          </div>
        );
      },
    });

    // Actions column (No play triangle button; spacious padding)
    cols.push({
      id: "actions",
      header: () => (
        <span className="block text-right pr-2">{t("table.actions")}</span>
      ),
      size: 90,
      minSize: 80,
      maxSize: 120,
      enableResizing: false,
      enableSorting: false,
      cell: ({ row }) => {
        const item = row.original;
        return (
          <div className="flex items-center justify-end gap-2 pr-2">
            <button
              type="button"
              onClick={() => setActiveItem(item)}
              className="p-1.5 text-slate-400 hover:text-slate-900 hover:bg-slate-100 rounded-md transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100 cursor-pointer"
              title={t("table.viewDetails")}
            >
              <Eye size={15} />
            </button>

            {hasActions && (
              <button
                type="button"
                onClick={() => {
                  setItemToDelete({
                    id: item.realId,
                    type: item.itemType,
                    title: resolvePostTitle(item),
                  });
                }}
                className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-md transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100 cursor-pointer"
                title={
                  deleteMode === "permanent"
                    ? t("table.deletePermanent")
                    : t("table.unlink")
                }
              >
                <Trash2 size={15} />
              </button>
            )}
          </div>
        );
      },
    });

    return cols;
  }, [hasActions, showLibraryColumn, libraryMap, deleteMode, formatDate, t]);

  // TanStack Table Instance
  const tableData = serverPagination ? data : localFilteredData;

  const table = useReactTable({
    data: tableData,
    columns,
    state: {
      sorting,
      columnSizing,
      pagination: {
        pageIndex: (serverPagination ? serverPagination.page : localPage) - 1,
        pageSize: serverPagination ? serverPagination.pageSize : localPageSize,
      },
    },
    meta: {
      selectedIds,
      toggleRow,
      setVisibleRowsSelected,
    } satisfies ContentTableMeta,
    pageCount: serverPagination
      ? Math.max(
          1,
          Math.ceil(serverPagination.total / serverPagination.pageSize),
        )
      : undefined,
    columnResizeMode: "onChange",
    onSortingChange: handleSortingChange,
    onColumnSizingChange: setColumnSizing,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: isServerSorting ? undefined : getSortedRowModel(),
    getPaginationRowModel: serverPagination
      ? undefined
      : getPaginationRowModel(),
    manualPagination: !!serverPagination,
    manualSorting: isServerSorting,
  });

  // Pagination metrics
  const totalCount = serverPagination
    ? serverPagination.total
    : localFilteredData.length;
  const pageSize = serverPagination ? serverPagination.pageSize : localPageSize;
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
  const currentPage = serverPagination ? serverPagination.page : localPage;

  const handleSearchSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (onSearchSubmit) {
      onSearchSubmit();
    } else if (!serverPagination) {
      setLocalPage(1);
    }
  };

  const handleClearSearch = () => {
    if (onSearchChange) {
      onSearchChange("");
    } else {
      setLocalSearchQuery("");
    }
    if (onSearchSubmit) {
      onSearchSubmit();
    } else if (!serverPagination) {
      setLocalPage(1);
    }
  };

  return {
    data,
    onDeletePost,
    onDeleteSource,
    onDeleteProfile,
    onBatchDelete,
    deleteMode,
    showFilters,
    emptyMessage,
    onPlayItem,
    isLoading,
    showLibraryColumn,
    libraries,
    onLinkToLibrary,
    serverPagination,
    onSearchChange,
    onCreatorFilterChange,
    unlinkedOnly,
    onUnlinkedOnlyChange,
    onRefresh,
    t,
    activeItem,
    setActiveItem,
    selectedIds,
    setSelectedIds,
    setLocalSearchQuery,
    setLocalCreatorFilter,
    setLocalPage,
    setLocalPageSize,
    effectiveSearchQuery,
    effectiveSearchMode,
    effectiveCreatorFilter,
    bulkTargetLibrary,
    setBulkTargetLibrary,
    isLinking,
    setIsLinking,
    itemToDelete,
    setItemToDelete,
    showBatchDeleteModal,
    setShowBatchDeleteModal,
    isDeleting,
    setIsDeleting,
    handleModeChange,
    allCreators,
    libraryMap,
    formatDate,
    hasActions,
    table,
    totalCount,
    pageSize,
    totalPages,
    currentPage,
    handleSearchSubmit,
    handleClearSearch,
  };
}

export function ContentTable(
  props: Parameters<typeof useContentTableModel>[0],
) {
  const model = useContentTableModel(props);
  return <TableWorkspace model={model} />;
}

function TableWorkspace({
  model,
}: {
  model: ReturnType<typeof useContentTableModel>;
}) {
  const {
    activeItem,
    setActiveItem,
    onPlayItem,
    libraries,
    libraryMap,
    onLinkToLibrary,
    hasActions,
    deleteMode,
    showLibraryColumn,
    setItemToDelete,
    onRefresh,
    formatDate,
  } = model;
  return (
    <div className="flex flex-col w-full bg-white">
      <TableToolbar model={model} />

      <TableViewport model={model} />

      <TablePagination model={model} />

      {activeItem && (
        <Suspense fallback={null}>
          <ContentDetailSheet
            activeItem={activeItem}
            onClose={() => setActiveItem(null)}
            onPlayItem={onPlayItem}
            libraries={libraries}
            libraryMap={libraryMap}
            onLinkToLibrary={onLinkToLibrary}
            hasActions={hasActions}
            deleteMode={deleteMode}
            showLibraryColumn={showLibraryColumn}
            onRequestDelete={(item) => setItemToDelete(item)}
            onRefresh={onRefresh}
            formatDate={formatDate}
          />
        </Suspense>
      )}

      <DeleteItemDialog model={model} />

      <DeleteSelectionDialog model={model} />
    </div>
  );
}

function TableToolbar({
  model,
}: {
  model: ReturnType<typeof useContentTableModel>;
}) {
  const { showFilters } = model;
  return (
    <>
      {" "}
      {showFilters && (
        <div className="relative z-20 p-3.5 border-b border-slate-200 flex flex-col xl:flex-row gap-3 items-stretch xl:items-center justify-between">
          <TableSearchControls model={model} />

          <TableActions model={model} />
        </div>
      )}{" "}
    </>
  );
}

function TableViewport({
  model,
}: {
  model: ReturnType<typeof useContentTableModel>;
}) {
  return (
    <div className="relative w-full overflow-x-auto">
      <TableRows model={model} />
    </div>
  );
}

function TableActions({
  model,
}: {
  model: ReturnType<typeof useContentTableModel>;
}) {
  const {
    t,
    effectiveCreatorFilter,
    onCreatorFilterChange,
    setLocalCreatorFilter,
    setLocalPage,
    allCreators,
    onUnlinkedOnlyChange,
    unlinkedOnly,
    onRefresh,
    selectedIds,
    onBatchDelete,
    setShowBatchDeleteModal,
    deleteMode,
    onDeleteProfile,
    data,
  } = model;
  return (
    <div className="flex items-center gap-2.5 shrink-0 flex-wrap justify-between xl:justify-end">
      <select
        aria-label={t("table.allCreators")}
        value={effectiveCreatorFilter}
        onChange={(e) => {
          const val = e.target.value;
          if (onCreatorFilterChange) {
            onCreatorFilterChange(val);
          } else {
            setLocalCreatorFilter(val);
            setLocalPage(1);
          }
        }}
        className="px-3 py-1.5 text-xs font-medium border border-slate-200 rounded-lg bg-white text-slate-700 hover:border-slate-300 focus:outline-none focus:ring-2 focus:ring-slate-900 cursor-pointer shrink-0"
      >
        <option value="all">{t("table.allCreators")}</option>
        {allCreators.map((c) => (
          <option key={c} value={c}>
            @{c}
          </option>
        ))}
      </select>

      {onUnlinkedOnlyChange && (
        <label className="flex items-center gap-1.5 text-xs text-slate-700 cursor-pointer select-none shrink-0 font-medium px-1">
          <input
            type="checkbox"
            checked={!!unlinkedOnly}
            onChange={(e) => onUnlinkedOnlyChange(e.target.checked)}
            className="rounded border-slate-300 text-slate-900 focus:ring-slate-900 w-3.5 h-3.5 cursor-pointer"
          />
          <span>{t("table.unlinkedOnly")}</span>
        </label>
      )}

      {onRefresh && (
        <button
          type="button"
          onClick={onRefresh}
          className="p-1.5 border border-slate-200 hover:bg-slate-50 rounded-lg text-slate-500 hover:text-slate-900 transition-colors shrink-0 cursor-pointer"
          title={t("table.refresh")}
        >
          <RefreshCw size={14} />
        </button>
      )}

      <LinkSelectionControl model={model} />

      {onBatchDelete && selectedIds.size > 0 && (
        <button
          onClick={() => setShowBatchDeleteModal(true)}
          className="text-xs font-medium text-red-600 bg-red-50 hover:bg-red-100 px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 border border-red-200 cursor-pointer"
        >
          <Trash2 size={13} />{" "}
          {deleteMode === "permanent" ? t("sheet.delete") : t("sheet.remove")} (
          {selectedIds.size})
        </button>
      )}

      {effectiveCreatorFilter !== "all" &&
        (onBatchDelete || onDeleteProfile) &&
        selectedIds.size === 0 && (
          <button
            onClick={async () => {
              if (
                !confirm(
                  onDeleteProfile
                    ? t("table.deleteCreatorConfirmWithProfile", {
                        creator: effectiveCreatorFilter,
                      })
                    : t("table.deleteCreatorConfirm", {
                        creator: effectiveCreatorFilter,
                      }),
                )
              )
                return;

              if (onDeleteProfile) {
                await onDeleteProfile(effectiveCreatorFilter);
              } else if (onBatchDelete) {
                const creatorItemIds = data
                  .filter((d) => d.creator === effectiveCreatorFilter)
                  .map((d) => d.id);
                await onBatchDelete(new Set(creatorItemIds));
              }
              if (onCreatorFilterChange) {
                onCreatorFilterChange("all");
              } else {
                setLocalCreatorFilter("all");
              }
            }}
            className="text-xs font-medium text-red-600 hover:text-red-700 underline cursor-pointer"
          >
            {t("table.deleteCreator", { creator: effectiveCreatorFilter })}
          </button>
        )}
    </div>
  );
}

function TableSearchControls({
  model,
}: {
  model: ReturnType<typeof useContentTableModel>;
}) {
  const { handleModeChange, effectiveSearchMode, t } = model;
  return (
    <div className="flex flex-1 items-center gap-2.5 min-w-0">
      <div className="inline-flex items-center p-0.5 bg-slate-100 rounded-lg border border-slate-200 text-xs font-medium shrink-0">
        <button
          type="button"
          onClick={() => handleModeChange("keyword")}
          className={`px-2.5 py-1 rounded-md transition-colors ${
            effectiveSearchMode === "keyword"
              ? "bg-white text-slate-900 shadow-sm font-semibold"
              : "text-slate-500 hover:text-slate-800"
          }`}
        >
          {t("table.keywordSearch")}
        </button>
        <button
          type="button"
          onClick={() => handleModeChange("semantic")}
          className={`px-2.5 py-1 rounded-md transition-colors ${
            effectiveSearchMode === "semantic"
              ? "bg-white text-slate-900 shadow-sm font-semibold"
              : "text-slate-500 hover:text-slate-800"
          }`}
        >
          {t("table.semanticSearch")}
        </button>
      </div>

      <TableSearchForm model={model} />
    </div>
  );
}

function DeleteItemDialog({
  model,
}: {
  model: ReturnType<typeof useContentTableModel>;
}) {
  const {
    itemToDelete,
    setItemToDelete,
    setIsDeleting,
    onDeletePost,
    onDeleteSource,
    activeItem,
    setActiveItem,
    deleteMode,
    t,
    isDeleting,
  } = model;
  return (
    <>
      {" "}
      {itemToDelete && (
        <Suspense fallback={null}>
          <ConfirmDialog
            isOpen
            onClose={() => setItemToDelete(null)}
            onConfirm={async () => {
              if (!itemToDelete) return;
              setIsDeleting(true);
              try {
                if (itemToDelete.type === "post" && onDeletePost) {
                  await onDeletePost(itemToDelete.id);
                } else if (itemToDelete.type === "source" && onDeleteSource) {
                  await onDeleteSource(itemToDelete.id);
                }
                if (activeItem?.realId === itemToDelete.id) {
                  setActiveItem(null);
                }
                setItemToDelete(null);
              } catch (err) {
                console.error("Failed to remove item", err);
              } finally {
                setIsDeleting(false);
              }
            }}
            title={
              deleteMode === "permanent"
                ? t("table.deleteSingleTitle")
                : t("table.unlinkSingleTitle")
            }
            description={
              deleteMode === "permanent"
                ? t("table.deleteSingleDesc")
                : t("table.unlinkSingleDesc")
            }
            confirmText={
              deleteMode === "permanent"
                ? t("table.deleteConfirm")
                : t("table.unlinkConfirm")
            }
            cancelText={t("table.cancel")}
            variant="destructive"
            isLoading={isDeleting}
          />
        </Suspense>
      )}{" "}
    </>
  );
}

function DeleteSelectionDialog({
  model,
}: {
  model: ReturnType<typeof useContentTableModel>;
}) {
  const {
    showBatchDeleteModal,
    setShowBatchDeleteModal,
    onBatchDelete,
    selectedIds,
    setIsDeleting,
    setSelectedIds,
    deleteMode,
    t,
    isDeleting,
  } = model;
  return (
    <>
      {" "}
      {showBatchDeleteModal && (
        <Suspense fallback={null}>
          <ConfirmDialog
            isOpen
            onClose={() => setShowBatchDeleteModal(false)}
            onConfirm={async () => {
              if (!onBatchDelete || selectedIds.size === 0) return;
              setIsDeleting(true);
              try {
                await onBatchDelete(selectedIds);
                setSelectedIds(new Set());
                setShowBatchDeleteModal(false);
              } catch (err) {
                console.error("Failed to batch delete", err);
              } finally {
                setIsDeleting(false);
              }
            }}
            title={
              deleteMode === "permanent"
                ? t("table.deleteBatchTitle", { count: selectedIds.size })
                : t("table.unlinkBatchTitle", { count: selectedIds.size })
            }
            description={
              deleteMode === "permanent"
                ? t("table.deleteBatchDesc", { count: selectedIds.size })
                : t("table.unlinkBatchDesc", { count: selectedIds.size })
            }
            confirmText={
              deleteMode === "permanent"
                ? t("table.deleteBatchConfirm")
                : t("table.unlinkBatchConfirm")
            }
            cancelText={t("table.cancel")}
            variant="destructive"
            isLoading={isDeleting}
          />
        </Suspense>
      )}{" "}
    </>
  );
}

function TablePagination({
  model,
}: {
  model: ReturnType<typeof useContentTableModel>;
}) {
  const {
    totalCount,
    t,
    pageSize,
    serverPagination,
    setLocalPageSize,
    setLocalPage,
    currentPage,
    totalPages,
    selectedIds,
  } = model;
  return (
    <>
      {" "}
      {totalCount > 0 && (
        <div className="p-4 border-t border-slate-200 bg-white flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-500">
          <div className="flex items-center gap-3">
            <span>{t("table.rows")}</span>
            <select
              aria-label={t("table.rows")}
              value={pageSize}
              onChange={(e) => {
                const nextSize = Number(e.target.value);
                if (serverPagination) {
                  serverPagination.onPageSizeChange?.(nextSize);
                  serverPagination.onPageChange(1);
                } else {
                  setLocalPageSize(nextSize);
                  setLocalPage(1);
                }
              }}
              className="border border-slate-200 rounded px-2 py-1 bg-white text-slate-700 focus:outline-none focus:ring-1 focus:ring-slate-900 cursor-pointer"
            >
              <option value={15}>15</option>
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
            <span>
              {t("table.pageOf", {
                page: currentPage,
                totalPages,
                total: totalCount,
              })}
            </span>
            {selectedIds.size > 0 && (
              <span className="font-medium text-slate-900">
                {t("table.selectedCountBadge", { count: selectedIds.size })}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                if (serverPagination) {
                  serverPagination.onPageChange(Math.max(1, currentPage - 1));
                } else {
                  setLocalPage((prev) => Math.max(1, prev - 1));
                }
              }}
              disabled={currentPage <= 1}
              className="px-3 py-1.5 border border-slate-200 rounded-md text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:hover:bg-white transition-colors font-medium cursor-pointer"
            >
              {t("table.prev")}
            </button>
            <button
              type="button"
              onClick={() => {
                if (serverPagination) {
                  serverPagination.onPageChange(
                    Math.min(totalPages, currentPage + 1),
                  );
                } else {
                  setLocalPage((prev) => Math.min(totalPages, prev + 1));
                }
              }}
              disabled={currentPage >= totalPages}
              className="px-3 py-1.5 border border-slate-200 rounded-md text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:hover:bg-white transition-colors font-medium cursor-pointer"
            >
              {t("table.next")}
            </button>
          </div>
        </div>
      )}{" "}
    </>
  );
}

function LinkSelectionControl({
  model,
}: {
  model: ReturnType<typeof useContentTableModel>;
}) {
  const {
    libraries,
    onLinkToLibrary,
    selectedIds,
    t,
    bulkTargetLibrary,
    setBulkTargetLibrary,
    isLinking,
    setIsLinking,
    setSelectedIds,
  } = model;
  return (
    <>
      {" "}
      {libraries &&
        libraries.length > 0 &&
        onLinkToLibrary &&
        selectedIds.size > 0 && (
          <div className="flex items-center gap-2">
            <select
              aria-label={t("table.addToLibrary")}
              value={bulkTargetLibrary}
              onChange={(e) => setBulkTargetLibrary(e.target.value)}
              className="px-2.5 py-1.5 text-xs font-medium border border-slate-200 rounded-lg bg-white text-slate-700 hover:border-slate-300 focus:outline-none focus:ring-2 focus:ring-slate-900 cursor-pointer"
            >
              <option value="" disabled>
                {t("table.addToLibrary")}
              </option>
              {libraries.map((lib) => (
                <option key={lib.id} value={lib.id}>
                  {lib.name}
                </option>
              ))}
            </select>
            <button
              type="button"
              disabled={!bulkTargetLibrary || isLinking}
              onClick={async () => {
                if (!bulkTargetLibrary) return;
                setIsLinking(true);
                try {
                  await onLinkToLibrary(
                    bulkTargetLibrary,
                    Array.from(selectedIds),
                  );
                  setSelectedIds(new Set());
                  setBulkTargetLibrary("");
                } finally {
                  setIsLinking(false);
                }
              }}
              className="text-xs font-medium bg-slate-900 text-white hover:bg-slate-800 px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 disabled:opacity-40 cursor-pointer shadow-sm"
            >
              {isLinking ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <FolderPlus size={13} />
              )}
              <span>{t("table.bulkAddBtn", { count: selectedIds.size })}</span>
            </button>
          </div>
        )}{" "}
    </>
  );
}

function TableSearchForm({
  model,
}: {
  model: ReturnType<typeof useContentTableModel>;
}) {
  const {
    handleSearchSubmit,
    t,
    effectiveSearchQuery,
    onSearchChange,
    setLocalSearchQuery,
    setLocalPage,
    handleClearSearch,
    effectiveSearchMode,
  } = model;
  return (
    <form
      onSubmit={handleSearchSubmit}
      className="relative flex-1 min-w-[200px]"
    >
      <Search
        size={15}
        className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
      />
      <input
        aria-label={t("table.searchPlaceholder")}
        type="text"
        value={effectiveSearchQuery}
        onChange={(e) => {
          if (onSearchChange) {
            onSearchChange(e.target.value);
          } else {
            setLocalSearchQuery(e.target.value);
            setLocalPage(1);
          }
        }}
        placeholder={t("table.searchPlaceholder")}
        className="w-full pl-9 pr-14 py-1.5 text-sm bg-white border border-slate-200 rounded-lg text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-900 transition-colors"
      />
      <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1">
        {effectiveSearchQuery && (
          <button
            type="button"
            onClick={handleClearSearch}
            className="text-slate-400 hover:text-slate-700 p-0.5 cursor-pointer"
            title="Limpiar búsqueda"
          >
            <X size={13} />
          </button>
        )}
        <SearchHelpPopover currentMode={effectiveSearchMode} align="right" />
      </div>
    </form>
  );
}

function TableRows({
  model,
}: {
  model: ReturnType<typeof useContentTableModel>;
}) {
  const { isLoading, t, table, emptyMessage, selectedIds, setActiveItem } =
    model;
  return (
    <>
      {" "}
      {isLoading ? (
        <div className="py-20 text-center text-slate-400 flex flex-col items-center justify-center gap-2">
          <Loader2 size={24} className="animate-spin text-slate-600" />
          <span className="text-xs font-medium">{t("table.loadingReels")}</span>
        </div>
      ) : table.getRowModel().rows.length === 0 ? (
        <div className="py-16 text-center text-slate-500">
          <p className="text-sm font-medium text-slate-700">{emptyMessage}</p>
        </div>
      ) : (
        <table
          className="w-full table-fixed text-left border-collapse"
          style={{ minWidth: "100%" }}
        >
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr
                key={headerGroup.id}
                className="border-b border-slate-200 text-xs text-slate-500 select-none bg-slate-50/60 h-11"
              >
                {headerGroup.headers.map((header) => {
                  const canSort = header.column.getCanSort();
                  const isSorted = header.column.getIsSorted();

                  return (
                    <th
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
                      key={header.id}
                      style={{ width: `${header.getSize()}px` }}
                      className={cn(
                        "relative py-3 px-4 font-medium align-middle select-none group/th transition-colors",
                        canSort && "cursor-pointer hover:text-slate-900",
                      )}
                      onClick={header.column.getToggleSortingHandler()}
                    >
                      <div className="flex items-center gap-1.5 min-w-0">
                        <div className="truncate">
                          {flexRender(
                            header.column.columnDef.header,
                            header.getContext(),
                          )}
                        </div>
                        {canSort && (
                          <span className="shrink-0">
                            {isSorted === "asc" ? (
                              <ArrowUp
                                size={12}
                                className="text-slate-900 font-bold"
                              />
                            ) : isSorted === "desc" ? (
                              <ArrowDown
                                size={12}
                                className="text-slate-900 font-bold"
                              />
                            ) : (
                              <ArrowUpDown
                                size={12}
                                className="text-slate-300 group-hover/th:text-slate-600"
                              />
                            )}
                          </span>
                        )}
                      </div>

                      {header.column.getCanResize() && (
                        <div
                          role="separator"
                          aria-orientation="vertical"
                          tabIndex={0}
                          onMouseDown={header.getResizeHandler()}
                          onTouchStart={header.getResizeHandler()}
                          onDoubleClick={() => header.column.resetSize()}
                          onKeyDown={(event) => {
                            if (
                              event.key === "ArrowLeft" ||
                              event.key === "ArrowRight"
                            ) {
                              event.preventDefault();
                              event.stopPropagation();
                              const change =
                                event.key === "ArrowLeft" ? -16 : 16;
                              table.setColumnSizing((previous) => ({
                                ...previous,
                                [header.id]: Math.max(
                                  44,
                                  header.getSize() + change,
                                ),
                              }));
                            }
                          }}
                          className={cn(
                            "absolute right-0 top-0 h-full w-2 cursor-col-resize select-none touch-none hover:bg-slate-300 group-hover/th:bg-slate-200/80 transition-colors z-10",
                            header.column.getIsResizing() && "bg-slate-900 w-1",
                          )}
                          title={t("table.resizerTooltip")}
                        />
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y divide-slate-100 text-sm">
            {table.getRowModel().rows.map((row) => {
              const item = row.original;
              const isSelected = selectedIds.has(item.id);

              return (
                <tr
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
                  key={row.id}
                  onClick={event => {
                    if (!(event.target as HTMLElement).closest('button, input, a, select')) setActiveItem(item);
                  }}
                  className={cn(
                    "group transition-colors cursor-pointer",
                    isSelected ? "bg-slate-50" : "hover:bg-slate-50/70",
                  )}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td
                      key={cell.id}
                      style={{ width: `${cell.column.getSize()}px` }}
                      className={cn(
                        "py-3 px-4 align-middle",
                        cell.column.id !== "actions" &&
                          cell.column.id !== "select" &&
                          "truncate",
                      )}
                    >
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext(),
                      )}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      )}{" "}
    </>
  );
}
