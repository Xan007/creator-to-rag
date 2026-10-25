import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type MouseEvent as ReactMouseEvent,
} from "react";
import { AlertTriangle, Loader2, RefreshCw } from "lucide-react";
import { api } from "./lib/api";
import type { Library, SourceInfo, ChatSession } from "./lib/api-types";
import { useTranslation } from "./lib/i18n";
import { useSidebarResize } from "./hooks/useSidebarResize";
import { useChatSessions } from "./hooks/useChatSessions";
import { AppSidebar } from "./components/layout/AppSidebar";
import { AppHeader } from "./components/layout/AppHeader";

// Heavy views (markdown renderer, table, modals) load on demand. This keeps the
// initial bundle focused on the app shell.
const ChatView = lazy(() =>
  import("./components/chat/ChatView").then((module) => ({
    default: module.ChatView,
  })),
);
const VideoPlayer = lazy(() =>
  import("./components/chat/VideoPlayer").then((module) => ({
    default: module.VideoPlayer,
  })),
);
const LibraryDashboard = lazy(() =>
  import("./components/ui/LibraryDashboard").then((module) => ({
    default: module.LibraryDashboard,
  })),
);
const GlobalContentBrowser = lazy(() =>
  import("./components/ui/GlobalContentBrowser").then((module) => ({
    default: module.GlobalContentBrowser,
  })),
);
const LibraryModals = lazy(() =>
  import("./components/modals/LibraryModals").then((module) => ({
    default: module.LibraryModals,
  })),
);
const SettingsModal = lazy(() =>
  import("./components/modals/SettingsModal").then((module) => ({
    default: module.SettingsModal,
  })),
);

function ViewFallback() {
  return (
    <div className="w-full h-64 flex flex-col items-center justify-center gap-3 text-slate-400">
      <Loader2 size={22} className="animate-spin text-slate-500" />
    </div>
  );
}

function useAppModel() {
  const { t } = useTranslation();

  // Libraries state
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [isLoadingLibraries, setIsLoadingLibraries] = useState(true);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [activeLibrary, setActiveLibrary] = useState<Library | null>(null);
  const [activeTab, setActiveTab] = useState<"knowledge" | "chat">("knowledge");
  const [dashboardKey, setDashboardKey] = useState(0);

  // Sidebar resizable state
  const {
    isSidebarOpen,
    setIsSidebarOpen,
    sidebarWidth,
    isDragging,
    startDragging,
    resizeBy,
  } = useSidebarResize();

  // Chat sessions state
  const {
    chatSessions,
    activeChatId,
    setActiveChatId,
    activeChat,
    isLoading,
    currentResponse,
    handleNewChat,
    handleDeleteChat: deleteChatSession,
    handleRenameChat,
    handleSendChat,
  } = useChatSessions(activeLibrary);

  // Inspector / VideoPlayer state
  const [playingSource, setPlayingSource] = useState<SourceInfo | null>(null);
  const [isRightPanelOpen, setIsRightPanelOpen] = useState(true);
  const [iframeLoaded, setIframeLoaded] = useState(false);
  const [hasOpenedPlayer, setHasOpenedPlayer] = useState(false);
  const playingUrlRef = useRef<string | undefined>(undefined);

  // Modals state
  const [isNewLibraryOpen, setIsNewLibraryOpen] = useState(false);
  const [isAddSourceOpen, setIsAddSourceOpen] = useState(false);
  const [isAddProfileOpen, setIsAddProfileOpen] = useState(false);
  const [isUploadZipOpen, setIsUploadZipOpen] = useState(false);
  const [isAddFromGlobalOpen, setIsAddFromGlobalOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [newLibraryName, setNewLibraryName] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const refreshDashboard = useCallback(
    () => setDashboardKey((previous) => previous + 1),
    [],
  );

  const loadLibraries = useCallback(async () => {
    setIsLoadingLibraries(true);
    try {
      const libs = await api.getLibraries();
      setLibraries(libs);
      setBackendError(null);
    } catch (error) {
      console.error("Failed to load libraries", error);
      setBackendError(
        error instanceof Error
          ? error.message
          : "No se pudo conectar con el backend.",
      );
    } finally {
      setIsLoadingLibraries(false);
    }
  }, []);

  useEffect(() => {
    void loadLibraries();
  }, [loadLibraries]);

  const handleCreateLibrary = async (event: FormEvent) => {
    event.preventDefault();
    if (!newLibraryName.trim()) return;
    setIsSubmitting(true);
    try {
      const library = await api.createLibrary({ name: newLibraryName });
      await loadLibraries();
      setActiveLibrary(library);
      setActiveTab("knowledge");
      setIsNewLibraryOpen(false);
      setNewLibraryName("");
    } catch (error) {
      console.error(error);
      alert(t("alerts.createLibError"));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleUploadZip = async (event: FormEvent) => {
    event.preventDefault();
    if (!selectedFile) return;
    setIsSubmitting(true);
    try {
      await api.importSaved(selectedFile);
      await api.processSaved();
      alert(t("alerts.zipSuccess"));
      setIsUploadZipOpen(false);
      setSelectedFile(null);
    } catch (error) {
      console.error(error);
      alert(t("alerts.zipError"));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSelectSource = useCallback((source: SourceInfo) => {
    if (playingUrlRef.current !== source.url) setIframeLoaded(false);
    playingUrlRef.current = source.url;
    setPlayingSource(source);
    setHasOpenedPlayer(true);
    setIsRightPanelOpen(true);
  }, []);

  const handleSelectChat = useCallback(
    (chat: ChatSession) => {
      setActiveTab("chat");
      setActiveChatId(chat.id);
      const lastWithSources = [...chat.history]
        .reverse()
        .find(
          (turn) =>
            turn.role === "assistant" &&
            turn.sources &&
            turn.sources.length > 0,
        );
      if (lastWithSources?.sources && lastWithSources.sources.length > 0) {
        const citedSources = lastWithSources.sources.filter(
          (source) => source.cited,
        );
        const sourceToPlay =
          citedSources.length > 0
            ? citedSources[0]
            : lastWithSources.sources[0];
        setIframeLoaded(false);
        playingUrlRef.current = sourceToPlay.url;
        setPlayingSource(sourceToPlay);
        setHasOpenedPlayer(true);
        setIsRightPanelOpen(true);
      }
    },
    [setActiveChatId],
  );

  const handleChatSubmit = useCallback(
    (message: string) => {
      void handleSendChat(handleSelectSource, message);
    },
    [handleSendChat, handleSelectSource],
  );

  const openInPlayer = useCallback((url: string) => {
    setIframeLoaded(false);
    playingUrlRef.current = url;
    setPlayingSource({ url, cited: true, creator: "" });
    setHasOpenedPlayer(true);
    setIsRightPanelOpen(true);
  }, []);

  const handleSelectGlobal = useCallback(() => {
    setActiveLibrary(null);
    setActiveTab("knowledge");
  }, []);

  const handleSelectLibrary = useCallback((library: Library) => {
    setActiveLibrary(library);
    setActiveTab("knowledge");
  }, []);

  const handleDeleteChat = useCallback(
    (id: string, event: ReactMouseEvent) => {
      deleteChatSession(id, event);
      const remaining = chatSessions.filter(
        (chat) => chat.id !== id && chat.libraryId === activeLibrary?.id,
      );
      if (remaining.length === 0) setActiveTab("knowledge");
    },
    [activeLibrary?.id, chatSessions, deleteChatSession],
  );

  const handleTabChange = useCallback(
    (tab: "knowledge" | "chat") => setActiveTab(tab),
    [],
  );

  const handleNewChatClick = useCallback(() => {
    handleNewChat();
    setActiveTab("chat");
  }, [handleNewChat]);

  const handleOpenNewLibrary = useCallback(() => setIsNewLibraryOpen(true), []);
  const handleOpenSettings = useCallback(() => setIsSettingsOpen(true), []);
  const handleSidebarClose = useCallback(
    () => setIsSidebarOpen(false),
    [setIsSidebarOpen],
  );
  const handleSidebarOpen = useCallback(
    () => setIsSidebarOpen(true),
    [setIsSidebarOpen],
  );

  const handleRenameTitle = useCallback(
    (newTitle: string) => {
      if (activeChatId) handleRenameChat(activeChatId, newTitle);
    },
    [activeChatId, handleRenameChat],
  );

  const handlePostLinked = useCallback(() => {
    void loadLibraries();
    refreshDashboard();
  }, [loadLibraries, refreshDashboard]);

  const handleLibraryDeleted = useCallback(() => {
    if (!activeLibrary) return;
    setLibraries((previous) =>
      previous.filter((library) => library.id !== activeLibrary.id),
    );
    setActiveLibrary(null);
    setActiveTab("knowledge");
  }, [activeLibrary]);

  const handleContentLinked = useCallback(() => {
    refreshDashboard();
    void loadLibraries();
  }, [loadLibraries, refreshDashboard]);

  const handleClosePlayer = useCallback(() => {
    setIsRightPanelOpen(false);
    setPlayingSource(null);
  }, []);

  const activeTitle =
    activeTab === "chat" && activeChat
      ? activeChat.title
      : activeLibrary
        ? activeLibrary.name
        : t("nav.globalDatabase");

  const anyLibraryModalOpen =
    isNewLibraryOpen ||
    isAddSourceOpen ||
    isAddProfileOpen ||
    isUploadZipOpen ||
    isAddFromGlobalOpen;

  return {
    t,
    libraries,
    isLoadingLibraries,
    backendError,
    activeLibrary,
    activeTab,
    dashboardKey,
    isSidebarOpen,
    sidebarWidth,
    isDragging,
    startDragging,
    resizeBy,
    chatSessions,
    activeChatId,
    activeChat,
    isLoading,
    currentResponse,
    handleNewChat,
    handleRenameChat,
    playingSource,
    setPlayingSource,
    isRightPanelOpen,
    iframeLoaded,
    setIframeLoaded,
    hasOpenedPlayer,
    isNewLibraryOpen,
    setIsNewLibraryOpen,
    isAddSourceOpen,
    setIsAddSourceOpen,
    isAddProfileOpen,
    setIsAddProfileOpen,
    isUploadZipOpen,
    setIsUploadZipOpen,
    isAddFromGlobalOpen,
    setIsAddFromGlobalOpen,
    isSettingsOpen,
    setIsSettingsOpen,
    newLibraryName,
    setNewLibraryName,
    selectedFile,
    setSelectedFile,
    isSubmitting,
    loadLibraries,
    handleCreateLibrary,
    handleUploadZip,
    handleSelectSource,
    handleSelectChat,
    handleChatSubmit,
    openInPlayer,
    handleSelectGlobal,
    handleSelectLibrary,
    handleDeleteChat,
    handleTabChange,
    handleNewChatClick,
    handleOpenNewLibrary,
    handleOpenSettings,
    handleSidebarClose,
    handleSidebarOpen,
    handleRenameTitle,
    handlePostLinked,
    handleLibraryDeleted,
    handleContentLinked,
    handleClosePlayer,
    activeTitle,
    anyLibraryModalOpen,
  };
}

export default function App() {
  const model = useAppModel();
  return <AppView model={model} />;
}

function AppView({ model }: { model: ReturnType<typeof useAppModel> }) {
  const {
    libraries,
    isLoadingLibraries,
    activeLibrary,
    activeTab,
    isSidebarOpen,
    sidebarWidth,
    isDragging,
    startDragging,
    chatSessions,
    activeChatId,
    handleRenameChat,
    isSettingsOpen,
    setIsSettingsOpen,
    handleSelectChat,
    handleSelectGlobal,
    handleSelectLibrary,
    handleDeleteChat,
    handleNewChatClick,
    handleOpenNewLibrary,
    handleSidebarClose,
  } = model;
  return (
    <div className="flex h-screen w-full bg-[#f9fafb] text-[#111827] font-sans antialiased overflow-hidden">
      <AppSidebar
        isOpen={isSidebarOpen}
        width={sidebarWidth}
        isDragging={isDragging}
        onStartDrag={startDragging}
        onResizeBy={model.resizeBy}
        onClose={handleSidebarClose}
        libraries={libraries}
        isLoadingLibraries={isLoadingLibraries}
        activeLibrary={activeLibrary}
        activeTab={activeTab}
        onSelectGlobal={handleSelectGlobal}
        onSelectLibrary={handleSelectLibrary}
        onOpenNewLibrary={handleOpenNewLibrary}
        chatSessions={chatSessions}
        activeChatId={activeChatId}
        onSelectChat={handleSelectChat}
        onNewChat={handleNewChatClick}
        onDeleteChat={handleDeleteChat}
        onRenameChat={handleRenameChat}
      />

      <Workspace model={model} />

      {isSettingsOpen && (
        <Suspense fallback={null}>
          <SettingsModal isOpen onClose={() => setIsSettingsOpen(false)} />
        </Suspense>
      )}
      <LibraryDialogs model={model} />
    </div>
  );
}

function Workspace({ model }: { model: ReturnType<typeof useAppModel> }) {
  const {
    playingSource,
    hasOpenedPlayer,
    isRightPanelOpen,
    setPlayingSource,
    iframeLoaded,
    setIframeLoaded,
    handleClosePlayer,
  } = model;
  return (
    <main className="flex-1 flex bg-white relative overflow-hidden">
      <WorkspaceContent model={model} />

      {hasOpenedPlayer && (
        <Suspense fallback={null}>
          <VideoPlayer
            key={playingSource?.url}
            isOpen={isRightPanelOpen && Boolean(playingSource)}
            playingSource={playingSource}
            setPlayingSource={setPlayingSource}
            iframeLoaded={iframeLoaded}
            setIframeLoaded={setIframeLoaded}
            onClose={handleClosePlayer}
          />
        </Suspense>
      )}
    </main>
  );
}

function WorkspaceContent({
  model,
}: {
  model: ReturnType<typeof useAppModel>;
}) {
  const {
    activeTitle,
    isSidebarOpen,
    handleSidebarOpen,
    handleOpenSettings,
    activeTab,
    activeChat,
    handleRenameTitle,
    activeLibrary,
    handleTabChange,
    backendError,
    t,
    loadLibraries,
  } = model;
  return (
    <div className="flex-1 flex flex-col relative min-w-0">
      <AppHeader
        key={activeTitle}
        title={activeTitle}
        isSidebarOpen={isSidebarOpen}
        onOpenSidebar={handleSidebarOpen}
        onOpenSettings={handleOpenSettings}
        isChat={activeTab === "chat" && Boolean(activeChat)}
        onRenameTitle={handleRenameTitle}
        activeTab={activeLibrary ? activeTab : undefined}
        onTabChange={activeLibrary ? handleTabChange : undefined}
      />

      {backendError && (
        <div className="px-6 py-2.5 bg-amber-50 border-b border-amber-200 text-amber-900 text-xs flex items-center gap-2 shrink-0">
          <AlertTriangle size={14} className="shrink-0" />
          <span className="font-medium">{t("errors.backendOffline")}</span>
          <span className="text-amber-800/80 truncate hidden sm:inline">
            {backendError}
          </span>
          <button
            type="button"
            onClick={() => void loadLibraries()}
            className="ml-auto inline-flex items-center gap-1.5 font-semibold text-amber-900 hover:text-amber-950 underline underline-offset-2 cursor-pointer shrink-0"
          >
            <RefreshCw size={12} />
            {t("errors.retry")}
          </button>
        </div>
      )}

      <ActiveLibraryView model={model} />
    </div>
  );
}

function LibraryDialogs({ model }: { model: ReturnType<typeof useAppModel> }) {
  const {
    anyLibraryModalOpen,
    activeLibrary,
    isNewLibraryOpen,
    setIsNewLibraryOpen,
    newLibraryName,
    setNewLibraryName,
    handleCreateLibrary,
    isSubmitting,
    isAddSourceOpen,
    setIsAddSourceOpen,
    isAddProfileOpen,
    setIsAddProfileOpen,
    isUploadZipOpen,
    setIsUploadZipOpen,
    setSelectedFile,
    selectedFile,
    handleUploadZip,
    isAddFromGlobalOpen,
    setIsAddFromGlobalOpen,
    handleContentLinked,
  } = model;
  return (
    <>
      {" "}
      {anyLibraryModalOpen && (
        <Suspense fallback={null}>
          <LibraryModals
            activeLibrary={activeLibrary}
            isNewLibraryOpen={isNewLibraryOpen}
            setIsNewLibraryOpen={setIsNewLibraryOpen}
            newLibraryName={newLibraryName}
            setNewLibraryName={setNewLibraryName}
            handleCreateLibrary={handleCreateLibrary}
            isSubmitting={isSubmitting}
            isAddSourceOpen={isAddSourceOpen}
            setIsAddSourceOpen={setIsAddSourceOpen}
            isAddProfileOpen={isAddProfileOpen}
            setIsAddProfileOpen={setIsAddProfileOpen}
            isUploadZipOpen={isUploadZipOpen}
            setIsUploadZipOpen={setIsUploadZipOpen}
            setSelectedFile={setSelectedFile}
            selectedFile={selectedFile}
            handleUploadZip={handleUploadZip}
            isAddFromGlobalOpen={isAddFromGlobalOpen}
            setIsAddFromGlobalOpen={setIsAddFromGlobalOpen}
            onContentLinked={handleContentLinked}
          />
        </Suspense>
      )}{" "}
    </>
  );
}

function ActiveLibraryView({
  model,
}: {
  model: ReturnType<typeof useAppModel>;
}) {
  const {
    activeLibrary,
    libraries,
    openInPlayer,
    handlePostLinked,
    activeTab,
    dashboardKey,
    handleLibraryDeleted,
    setIsAddSourceOpen,
    setIsAddProfileOpen,
    setIsAddFromGlobalOpen,
    activeChat,
    isLoading,
    currentResponse,
    playingSource,
    handleSelectSource,
    handleNewChat,
    handleChatSubmit,
  } = model;
  return (
    <div className="flex-1 overflow-y-auto">
      <Suspense fallback={<ViewFallback />}>
        {!activeLibrary ? (
          <GlobalContentBrowser
            libraries={libraries}
            onPlayItem={openInPlayer}
            onPostLinked={handlePostLinked}
          />
        ) : activeTab === "knowledge" ? (
          <LibraryDashboard
            key={`${activeLibrary.id}-${dashboardKey}`}
            library={activeLibrary}
            onLibraryDeleted={handleLibraryDeleted}
            onAddSource={() => setIsAddSourceOpen(true)}
            onAddProfile={() => setIsAddProfileOpen(true)}
            onAddFromGlobal={() => setIsAddFromGlobalOpen(true)}
            onPlayItem={openInPlayer}
          />
        ) : (
          <div className="p-6 pb-36 max-w-4xl mx-auto min-h-full">
            <ChatView
              activeLibrary={activeLibrary}
              activeChat={activeChat}
              isLoading={isLoading}
              currentResponse={currentResponse}
              playingSource={playingSource}
              onSelectSource={handleSelectSource}
              onNewChat={() => handleNewChat()}
              onSubmit={handleChatSubmit}
            />
          </div>
        )}
      </Suspense>
    </div>
  );
}
