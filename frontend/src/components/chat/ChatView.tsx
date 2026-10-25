import {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  MessageSquare,
  PlusCircle,
  PlayCircle,
  Loader2,
  Send,
  ArrowRight,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type {
  Library,
  ChatSession,
  ChatTurn,
  QueryResponse,
  SourceInfo,
} from "../../lib/api-types";
import { useTranslation } from "../../lib/i18n";
import { cn } from "../../lib/utils";

interface ChatViewProps {
  activeLibrary: Library;
  activeChat: ChatSession | null;
  isLoading: boolean;
  currentResponse: QueryResponse | null;
  playingSource: SourceInfo | null;
  onSelectSource: (source: SourceInfo) => void;
  onNewChat: () => void;
  onSubmit: (message: string) => void;
}

function formatCitationText(rawContent: string): string {
  if (!rawContent) return "";
  let cleaned = rawContent.replace(
    /(\\?\[\s*Source\s*(\d+)\s*\\?\])\s+([,.;])/gi,
    "$1$3",
  );
  cleaned = cleaned.replace(
    /(\\?\[\s*Source\s*(\d+)\s*\\?\])(?:\s*,?\s*\\?\[\s*Source\s*\2\s*\\?\])+/gi,
    "$1",
  );
  cleaned = cleaned.replace(
    /\\?\[\s*Source\s*(\d+)\s*\\?\]/gi,
    "[$1](#source-$1)",
  );
  return cleaned;
}

function scrollToSourceCard(messageIndex: number, sourceNumber: number) {
  window.setTimeout(() => {
    document
      .getElementById(`source-card-${messageIndex}-${sourceNumber}`)
      ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, 60);
}

function scrollToCitation(messageIndex: number, sourceNumber: number) {
  window.setTimeout(() => {
    document
      .getElementById(`citation-ref-${messageIndex}-${sourceNumber}`)
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, 60);
}

interface ChatMessageProps {
  turn: ChatTurn;
  index: number;
  isLastAssistant: boolean;
  currentSources?: SourceInfo[];
  playingUrl?: string;
  playingIndex?: number;
  onSelectSource: (source: SourceInfo) => void;
}

/**
 * Memoized message bubble.
 *
 * Without this, every keystroke in the composer re-renders the whole history
 * and makes react-markdown re-parse every answer.
 */
const ChatMessage = memo(function ChatMessage({
  turn,
  index,
  isLastAssistant,
  currentSources,
  playingUrl,
  playingIndex,
  onSelectSource,
}: ChatMessageProps) {
  const { t } = useTranslation();

  const turnSources =
    turn.sources ?? (isLastAssistant ? currentSources : undefined);
  const citationComponents = useMemo(
    () => ({
      a: ({
        href,
        children,
      }: {
        href?: string;
        children?: React.ReactNode;
      }) => {
        if (!href?.startsWith("#source-")) {
          return (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          );
        }
        const sourceNumber = Number.parseInt(href.split("-")[1] ?? "", 10);
        const source = Number.isFinite(sourceNumber)
          ? turnSources?.[sourceNumber - 1]
          : undefined;
        const isActive = Boolean(
          source &&
            (playingUrl === source.url || playingIndex === sourceNumber),
        );

        return (
          <button
            type="button"
            id={`citation-ref-${index}-${sourceNumber}`}
            onClick={(event) => {
              event.preventDefault();
              if (!source) return;
              onSelectSource(source);
              scrollToSourceCard(index, sourceNumber);
            }}
            className={cn(
              "inline-flex items-center justify-center font-bold text-[11px] px-1.5 py-0.5 rounded transition-colors duration-200 cursor-pointer mx-0.5 align-baseline select-none",
              isActive
                ? "bg-slate-900 text-white shadow-xs ring-1 ring-slate-900 scale-105"
                : "bg-slate-100 text-slate-700 hover:bg-slate-200 hover:text-slate-900 hover:scale-105 active:scale-95",
            )}
            title={
              source?.title ||
              source?.summary ||
              t("chat.source", { number: sourceNumber })
            }
          >
            <span>{children}</span>
          </button>
        );
      },
    }),
    [index, onSelectSource, playingIndex, playingUrl, t, turnSources],
  );

  const citedSources = useMemo(
    () => (turnSources ?? []).filter((source) => source.cited),
    [turnSources],
  );

  return (
    <div className="flex gap-4 pb-8 border-b border-slate-100 last:border-b-0 last:pb-0 animate-in fade-in-50 duration-300">
      <div
        className={cn(
          "w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 font-medium text-sm",
          turn.role === "user"
            ? "bg-slate-100 text-slate-600"
            : "bg-slate-900 text-white",
        )}
      >
        {turn.role === "user" ? t("chat.you") : <PlayCircle size={16} />}
      </div>

      <div className="pt-1 text-[15px] leading-relaxed space-y-2 min-w-0 flex-1">
        {turn.role === "user" ? (
          <div className="whitespace-pre-wrap">{turn.content}</div>
        ) : (
          <div className="prose prose-sm max-w-none prose-slate prose-a:text-slate-900 prose-a:font-medium prose-a:underline-offset-2 hover:prose-a:text-slate-700">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={citationComponents}
            >
              {formatCitationText(turn.content)}
            </ReactMarkdown>
          </div>
        )}

        {turn.role === "assistant" &&
          turnSources &&
          turnSources.length > 0 &&
          (() => {
            const displaySources =
              citedSources.length > 0 ? citedSources : turnSources;
            return (
              <div className="mt-4 pt-3 border-t border-slate-100">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                    {citedSources.length > 0
                      ? t("chat.citedSources", { count: displaySources.length })
                      : t("chat.sources", { count: displaySources.length })}
                  </span>
                </div>
                <div className="grid gap-2 grid-cols-1">
                  {displaySources.map((source, sourceIndex) => {
                    const sourceNumber =
                      source.source_index || turnSources.indexOf(source) + 1;
                    const isPlaying = playingUrl === source.url;
                    const titleText =
                      source.title ||
                      (source.creator
                        ? `@${source.creator}`
                        : t("chat.source", { number: sourceNumber }));
                    return (
                      <button
                        key={source.source_id || sourceIndex}
                        type="button"
                        id={`source-card-${index}-${sourceNumber}`}
                        onClick={() => {
                          onSelectSource(source);
                          scrollToCitation(index, sourceNumber);
                        }}
                        className={cn(
                          "flex items-center text-left gap-3 px-3.5 py-2 rounded-lg text-sm transition-colors duration-200 border overflow-hidden cursor-pointer w-full group",
                          isPlaying
                            ? "bg-slate-50 border-slate-900 ring-1 ring-slate-900 shadow-xs"
                            : "bg-white border-slate-200/90 hover:border-slate-300 hover:bg-slate-50 hover:shadow-xs hover:-translate-y-0.5",
                        )}
                      >
                        <div
                          className={cn(
                            "shrink-0 flex items-center justify-center rounded-full transition-colors duration-200 w-6 h-6",
                            isPlaying
                              ? "bg-slate-900 text-white scale-105"
                              : "bg-slate-100 text-slate-700 group-hover:bg-slate-200 group-hover:text-slate-900",
                          )}
                        >
                          <PlayCircle size={13} />
                        </div>
                        <div className="min-w-0 flex-1 flex items-center justify-between gap-3">
                          <span
                            className={cn(
                              "truncate text-[13px]",
                              isPlaying
                                ? "font-bold text-slate-900"
                                : "font-medium text-slate-800",
                            )}
                          >
                            <span className="font-semibold text-slate-900 mr-2">
                              [{t("chat.source", { number: sourceNumber })}]
                            </span>
                            {titleText}
                          </span>
                          {source.creator && source.title && (
                            <span className="text-xs text-slate-400 shrink-0 font-normal">
                              @{source.creator}
                            </span>
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })()}
      </div>
    </div>
  );
});

export function ChatView({
  activeLibrary,
  activeChat,
  isLoading,
  currentResponse,
  playingSource,
  onSelectSource,
  onNewChat,
  onSubmit,
}: ChatViewProps) {
  const { t } = useTranslation();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");

  const suggestions = useMemo(
    () => [
      t("chat.suggestTopicSummary"),
      t("chat.suggestKeyAdvice"),
      t("chat.suggestRecentContent"),
      t("chat.suggestActionableTips"),
    ],
    [t],
  );

  // Auto-scroll to bottom of chat
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeChat?.history, isLoading]);

  const submit = useCallback(
    (override?: string) => {
      const message = (override ?? query).trim();
      if (!message || isLoading) return;
      onSubmit(message);
      if (override === undefined) setQuery("");
    },
    [isLoading, onSubmit, query],
  );

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    submit();
  };

  if (!activeChat) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center space-y-4 pt-10 animate-in fade-in zoom-in duration-500">
        <div className="w-12 h-12 bg-slate-50 rounded-2xl flex items-center justify-center text-slate-900">
          <MessageSquare size={24} />
        </div>
        <div>
          <h2 className="text-xl font-semibold">
            {t("chat.startConversation")}
          </h2>
          <p className="text-slate-500 mt-1 max-w-md mx-auto">
            {t("chat.startConversationDesc", { name: activeLibrary.name })}
          </p>
        </div>
        <button
          type="button"
          onClick={() => onNewChat()}
          className="bg-slate-900 hover:bg-slate-800 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2 cursor-pointer"
        >
          <PlusCircle size={16} /> {t("chat.newChatBtn")}
        </button>
      </div>
    );
  }

  const history = activeChat.history;
  const lastAssistantIndex = (() => {
    for (let index = history.length - 1; index >= 0; index -= 1) {
      if (history[index]?.role === "assistant") return index;
    }
    return -1;
  })();

  return (
    <div className="relative min-h-full">
      <div className="space-y-6">
        {history.length === 0 ? (
          <div className="py-10 md:py-16 max-w-2xl mx-auto flex flex-col items-center text-center animate-in fade-in-50 zoom-in-95 duration-400">
            <div className="w-14 h-14 bg-gradient-to-b from-slate-50 to-slate-100 border border-slate-200/90 rounded-2xl flex items-center justify-center shadow-xs text-slate-800 mb-4">
              <MessageSquare size={24} className="text-slate-800" />
            </div>

            <h2 className="text-xl md:text-2xl font-semibold text-slate-900 tracking-tight">
              {t("chat.welcomeTitle")}
            </h2>
            <p className="text-slate-500 text-sm max-w-md mt-2 leading-relaxed">
              {t("chat.welcomeSubtitle", { name: activeLibrary.name })}
            </p>

            <div className="w-full mt-8 pt-6 border-t border-slate-100">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3 text-left">
                {t("chat.suggestionsTitle")}
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                {suggestions.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => submit(suggestion)}
                    className="flex items-center justify-between text-left p-3.5 rounded-xl border border-slate-200/90 bg-white hover:border-slate-400 hover:bg-slate-50 hover:shadow-xs transition-colors duration-200 group cursor-pointer"
                  >
                    <span className="text-xs text-slate-700 font-medium group-hover:text-slate-900 leading-snug">
                      {suggestion}
                    </span>
                    <ArrowRight
                      size={14}
                      className="text-slate-300 group-hover:text-slate-900 group-hover:translate-x-0.5 transition-colors shrink-0 ml-2"
                    />
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          history.map((turn, index) => (
            <ChatMessage
              key={turn.id}
              turn={turn}
              index={index}
              isLastAssistant={index === lastAssistantIndex}
              currentSources={currentResponse?.sources}
              playingUrl={playingSource?.url}
              playingIndex={playingSource?.source_index}
              onSelectSource={onSelectSource}
            />
          ))
        )}

        {isLoading && (
          <div className="flex gap-4">
            <div className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center flex-shrink-0">
              <Loader2 size={16} className="text-slate-900 animate-spin" />
            </div>
            <div className="pt-1 text-[15px] text-slate-400">
              {t("chat.thinking")}
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="fixed bottom-0 left-0 right-0 p-6 pointer-events-none z-30">
        <div className="max-w-3xl mx-auto pointer-events-auto">
          <form
            onSubmit={handleSubmit}
            className="shadow-lg ring-1 ring-slate-200 rounded-xl bg-white focus-within:ring-2 focus-within:ring-slate-900 transition-shadow flex items-end p-2 pb-2"
          >
            <textarea
              aria-label={t("chat.askAbout", { name: activeLibrary.name })}
              className="w-full max-h-32 min-h-[44px] bg-transparent resize-none outline-none py-2 px-3 text-[15px] placeholder:text-slate-400"
              placeholder={t("chat.askAbout", { name: activeLibrary.name })}
              rows={1}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  submit();
                }
              }}
              disabled={isLoading}
            />
            <button
              type="submit"
              disabled={isLoading || !query.trim()}
              className="flex-shrink-0 w-10 h-10 rounded-lg bg-slate-900 hover:bg-slate-800 disabled:opacity-50 disabled:hover:bg-slate-900 text-white flex items-center justify-center transition-colors mb-0.5 mr-0.5 cursor-pointer"
              title={t("chat.send")}
            >
              <Send size={18} className="ml-1" />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
