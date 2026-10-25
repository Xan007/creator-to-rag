import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { api, isAbortError } from "../lib/api";
import type {
  Library,
  ChatSession,
  ChatTurn,
  QueryResponse,
  SourceInfo,
} from "../lib/api-types";
import { useTranslation } from "../lib/i18n";

const STORAGE_KEY = "creators_rag_chat_sessions";
const PERSIST_DEBOUNCE_MS = 250;

function newId(): string {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return crypto.randomUUID();
  }
  return `chat-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function readStoredSessions(): ChatSession[] {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (!saved) return [];
    const parsed: unknown = JSON.parse(saved);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((chat): chat is Record<string, unknown> =>
        Boolean(chat && typeof chat === "object" && chat.id),
      )
      .map((chat) => {
        const rawTitle = typeof chat.title === "string" ? chat.title : "";
        const title =
          rawTitle.trim() && !rawTitle.includes("[object Object]")
            ? rawTitle.trim()
            : "Nuevo chat";
        return {
          ...(chat as unknown as ChatSession),
          title,
          history: Array.isArray(chat.history)
            ? (chat.history as ChatTurn[]).map((turn) => ({
                ...turn,
                id: turn.id ?? newId(),
              }))
            : [],
          isCustomTitle: Boolean(chat.isCustomTitle),
        };
      });
  } catch (error) {
    console.error("Failed to parse chat sessions from localStorage", error);
    return [];
  }
}

export function useChatSessions(activeLibrary: Library | null, persist = true) {
  const { t } = useTranslation();

  const [chatSessions, setChatSessions] = useState<ChatSession[]>(() =>
    persist ? readStoredSessions() : [],
  );
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [currentResponse, setCurrentResponse] = useState<QueryResponse | null>(
    null,
  );
  const requestRef = useRef<AbortController | null>(null);

  // Persist debounced: writing the full history on every keystroke/turn is
  // synchronous and can block the main thread with long conversations.
  useEffect(() => {
    if (!persist) return;
    const timer = setTimeout(() => {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(chatSessions));
      } catch (error) {
        console.error("Failed to save chat sessions to localStorage", error);
      }
    }, PERSIST_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [chatSessions, persist]);

  useEffect(
    () => () => {
      requestRef.current?.abort();
    },
    [],
  );

  const activeChat = useMemo(
    () => chatSessions.find((chat) => chat.id === activeChatId) || null,
    [chatSessions, activeChatId],
  );

  const handleNewChat = useCallback(
    (initialTitle?: unknown) => {
      if (!activeLibrary) return null;
      const hasCustomTitle =
        typeof initialTitle === "string" && Boolean(initialTitle.trim());
      const title =
        hasCustomTitle && !String(initialTitle).includes("[object Object]")
          ? String(initialTitle).trim()
          : t("nav.newChat");
      const newChat: ChatSession = {
        id: newId(),
        libraryId: activeLibrary.id,
        title,
        history: [],
        isCustomTitle: hasCustomTitle,
      };
      setChatSessions((previous) => [newChat, ...previous]);
      setActiveChatId(newChat.id);
      setCurrentResponse(null);
      return newChat;
    },
    [activeLibrary, t],
  );

  const handleRenameChat = useCallback((chatId: string, newTitle: string) => {
    const trimmed = newTitle.trim();
    if (!trimmed) return;
    setChatSessions((previous) =>
      previous.map((chat) =>
        chat.id === chatId
          ? { ...chat, title: trimmed, isCustomTitle: true }
          : chat,
      ),
    );
  }, []);

  const handleDeleteChat = useCallback(
    (chatId: string, event?: React.MouseEvent) => {
      if (event) event.stopPropagation();
      setChatSessions((previous) =>
        previous.filter((chat) => chat.id !== chatId),
      );
      if (activeChatId === chatId) setActiveChatId(null);
    },
    [activeChatId],
  );

  const handleSendChat = useCallback(
    async (
      onSourcesReceived?: (source: SourceInfo) => void,
      overrideMessage?: string,
      targetChatId?: string,
    ) => {
      const userMessage = (overrideMessage ?? "").trim();
      const effectiveChatId = targetChatId || activeChatId;
      const effectiveChat =
        chatSessions.find((chat) => chat.id === effectiveChatId) || activeChat;

      if (!userMessage || !effectiveChat || !effectiveChatId || isLoading)
        return;

      const isFirstMessage = effectiveChat.history.length === 0;
      let updatedTitle = effectiveChat.title;
      if (isFirstMessage && !effectiveChat.isCustomTitle) {
        const words = userMessage.split(/\s+/);
        updatedTitle =
          words.length > 5
            ? `${words.slice(0, 5).join(" ")}...`
            : words.join(" ");
      }

      const newHistory: ChatTurn[] = [
        ...effectiveChat.history,
        { id: newId(), role: "user", content: userMessage },
      ];

      setChatSessions((previous) =>
        previous.map((chat) =>
          chat.id === effectiveChatId
            ? { ...chat, title: updatedTitle, history: newHistory }
            : chat,
        ),
      );
      setIsLoading(true);

      requestRef.current?.abort();
      const controller = new AbortController();
      requestRef.current = controller;

      try {
        const response = await api.query(
          {
            question: userMessage,
            library: activeLibrary?.slug,
            // The backend accepts at most 12 turns; send only what fits.
            history:
              effectiveChat.history.length > 0
                ? effectiveChat.history.slice(-12)
                : undefined,
          },
          { signal: controller.signal },
        );

        setCurrentResponse(response);
        setChatSessions((previous) =>
          previous.map((chat) =>
            chat.id === effectiveChatId
              ? {
                  ...chat,
                  history: [
                    ...newHistory,
                    {
                      id: newId(),
                      role: "assistant",
                      content: response.answer,
                      sources: response.sources,
                    },
                  ],
                }
              : chat,
          ),
        );

        if (response.sources && response.sources.length > 0) {
          const citedSources = response.sources.filter(
            (source) => source.cited,
          );
          onSourcesReceived?.(citedSources[0] ?? response.sources[0]);
        }
      } catch (error) {
        if (isAbortError(error)) return;
        console.error(error);
        const message =
          error instanceof Error && error.message
            ? `${t("chat.errorSearching")}\n\n_${error.message}_`
            : t("chat.errorSearching");
        setChatSessions((previous) =>
          previous.map((chat) =>
            chat.id === effectiveChatId
              ? {
                  ...chat,
                  history: [
                    ...newHistory,
                    { id: newId(), role: "assistant", content: message },
                  ],
                }
              : chat,
          ),
        );
      } finally {
        if (requestRef.current === controller) {
          requestRef.current = null;
        }
        setIsLoading(false);
      }
    },
    [activeChat, activeChatId, chatSessions, isLoading, activeLibrary, t],
  );

  return {
    chatSessions,
    setChatSessions,
    activeChatId,
    setActiveChatId,
    activeChat,
    isLoading,
    currentResponse,
    handleNewChat,
    handleDeleteChat,
    handleRenameChat,
    handleSendChat,
  };
}
