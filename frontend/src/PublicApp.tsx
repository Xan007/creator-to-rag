import { useState, type FormEvent } from "react";
import { Languages, LogOut, PlayCircle } from "lucide-react";
import { api, setAccessToken } from "./lib/api";
import type { Library, SourceInfo } from "./lib/api-types";
import { useTranslation } from "./lib/i18n";
import { useChatSessions } from "./hooks/useChatSessions";
import { ChatView } from "./components/chat/ChatView";
import { VideoPlayer } from "./components/chat/VideoPlayer";

function QueryWorkspace({
  libraries,
  onLogout,
}: {
  libraries: Library[];
  onLogout: () => void;
}) {
  const { t, toggleLang } = useTranslation();
  const [libraryId, setLibraryId] = useState(libraries[0]?.id ?? "");
  const library = libraries.find((item) => item.id === libraryId) ?? null;
  const chat = useChatSessions(library, false);
  const [source, setSource] = useState<SourceInfo | null>(null);
  const [loaded, setLoaded] = useState(false);
  const selectSource = (item: SourceInfo) => {
    setSource(item);
    setLoaded(false);
  };
  return (
    <div className="flex h-dvh flex-col bg-white text-slate-900">
      <header className="flex flex-wrap items-center gap-3 border-b border-slate-200 px-4 py-3 sm:px-6">
        <PlayCircle size={22} aria-hidden="true" />
        <h1 className="font-semibold">CreatorRAG</h1>
        <select
          aria-label={t("nav.libraries")}
          disabled={chat.isLoading}
          value={libraryId}
          onChange={(event) => {
            setLibraryId(event.target.value);
            chat.setActiveChatId(null);
            setSource(null);
          }}
          className="min-w-0 max-w-64 rounded-lg border border-slate-200 px-3 py-2 text-sm"
        >
          {libraries.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={toggleLang}
          aria-label={t("settings.languageSection")}
          className="ml-auto rounded-lg p-2 hover:bg-slate-100"
        >
          <Languages size={18} />
        </button>
        <button
          type="button"
          onClick={onLogout}
          aria-label={t("access.logout")}
          className="rounded-lg p-2 hover:bg-slate-100"
        >
          <LogOut size={18} />
        </button>
      </header>
      <main className="flex min-h-0 flex-1 overflow-hidden">
        <div className="min-w-0 flex-1 overflow-y-auto p-4 pb-36 sm:p-6">
          {library ? (
            <ChatView
              activeLibrary={library}
              activeChat={chat.activeChat}
              isLoading={chat.isLoading}
              currentResponse={chat.currentResponse}
              playingSource={source}
              onSelectSource={selectSource}
              onNewChat={() => chat.handleNewChat()}
              onSubmit={(message) =>
                void chat.handleSendChat(selectSource, message)
              }
            />
          ) : (
            <p role="status" className="p-8 text-center text-slate-500">
              {t("access.empty")}
            </p>
          )}
        </div>
        {source && (
          <VideoPlayer
            key={source.url}
            playingSource={source}
            setPlayingSource={setSource}
            iframeLoaded={loaded}
            setIframeLoaded={setLoaded}
            onClose={() => setSource(null)}
          />
        )}
      </main>
    </div>
  );
}

export default function PublicApp() {
  const { t } = useTranslation();
  const [libraries, setLibraries] = useState<Library[] | null>(null);
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function login(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setAccessToken(token.trim());
    try {
      setLibraries(await api.getLibraries());
      setToken("");
    } catch (cause) {
      setAccessToken("");
      setError(cause instanceof Error ? cause.message : t("access.failed"));
    } finally {
      setBusy(false);
    }
  }
  if (libraries)
    return (
      <QueryWorkspace
        libraries={libraries}
        onLogout={() => {
          setAccessToken("");
          setLibraries(null);
        }}
      />
    );
  return (
    <main className="grid min-h-dvh place-items-center bg-slate-50 p-6">
      <form
        onSubmit={login}
        className="w-full max-w-sm space-y-5 rounded-xl border border-slate-200 bg-white p-7"
      >
        <h1 className="text-xl font-semibold">CreatorRAG</h1>
        <p className="text-sm text-slate-600">{t("access.description")}</p>
        <label className="block space-y-2 text-sm font-medium">
          <span>{t("access.token")}</span>
          <input
            type="password"
            autoComplete="off"
            required
            value={token}
            onChange={(event) => setToken(event.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2"
          />
        </label>
        {error && (
          <p role="alert" className="text-sm text-red-700">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={busy || !token.trim()}
          className="w-full rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? t("library.loading") : t("access.enter")}
        </button>
      </form>
    </main>
  );
}
