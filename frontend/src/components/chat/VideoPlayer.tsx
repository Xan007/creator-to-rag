import { useState, useEffect, useCallback, useEffectEvent } from "react";
import {
  PanelRightClose,
  ExternalLink,
  Loader2,
  PlayCircle,
  BookOpen,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "../../lib/utils";
import { useTranslation } from "../../lib/i18n";
import type { SourceInfo } from "../../lib/api-types";

interface VideoPlayerProps {
  isOpen?: boolean;
  playingSource: SourceInfo | null;
  setPlayingSource: (source: SourceInfo | null) => void;
  iframeLoaded: boolean;
  setIframeLoaded: (loaded: boolean) => void;
  onClose?: () => void;
}

function useVideoPlayerModel({
  isOpen = true,
  playingSource,
  setPlayingSource,
  iframeLoaded,
  setIframeLoaded,
  onClose,
}: VideoPlayerProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<"video" | "knowledge">("video");

  const handleDismiss = useCallback(() => {
    if (onClose) {
      onClose();
    } else {
      setPlayingSource(null);
    }
  }, [onClose, setPlayingSource]);

  const dismissFromEvent = useEffectEvent(handleDismiss);
  useEffect(() => {
    if (!isOpen || !playingSource) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        dismissFromEvent();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [playingSource, isOpen]);

  if (!playingSource) return null;

  const creatorName = playingSource.creator || "creador";
  const displayTitle =
    playingSource.title || t("player.postBy", { creator: creatorName });
  const hasKnowledge = Boolean(
    playingSource.knowledge || playingSource.summary || playingSource.caption,
  );

  const panelWidth = "min(460px, 100vw)";

  return {
    isOpen,
    playingSource,
    iframeLoaded,
    setIframeLoaded,
    t,
    activeTab,
    setActiveTab,
    handleDismiss,
    creatorName,
    displayTitle,
    hasKnowledge,
    panelWidth,
  };
}

export function VideoPlayer(props: Parameters<typeof useVideoPlayerModel>[0]) {
  const model = useVideoPlayerModel(props);
  if (!model) return null;
  return <PlayerPanel model={model} />;
}

function PlayerPanel({
  model,
}: {
  model: NonNullable<ReturnType<typeof useVideoPlayerModel>>;
}) {
  const { isOpen, panelWidth } = model;
  return (
    <aside
      style={{ width: isOpen ? panelWidth : 0 }}
      className={cn(
        "fixed inset-y-16 right-0 lg:static shrink-0 h-[calc(100dvh-4rem)] lg:h-full bg-white text-slate-900 flex flex-col z-20",
        "transition-[width] duration-300 ease-in-out overflow-hidden group",
        isOpen ? "border-l border-slate-200" : "border-l-0",
      )}
    >
      <PlayerContent model={model} />
    </aside>
  );
}

function PlayerVideoTab({
  model,
}: {
  model: NonNullable<ReturnType<typeof useVideoPlayerModel>>;
}) {
  const { activeTab, isOpen, iframeLoaded, t } = model;
  return (
    <div
      className={cn(
        "flex-1 bg-slate-50 relative flex flex-col items-center justify-center overflow-hidden transition-colors duration-200",
        activeTab === "video" ? "flex opacity-100" : "hidden opacity-0",
      )}
    >
      {isOpen && !iframeLoaded && (
        <div className="absolute inset-0 bg-slate-50 flex items-center justify-center z-20 transition-opacity duration-300">
          <div className="flex flex-col items-center gap-2.5 text-slate-500">
            <Loader2 size={26} className="animate-spin text-slate-700" />
            <span className="text-xs font-medium">{t("player.loading")}</span>
          </div>
        </div>
      )}

      <SourceEmbed model={model} />
    </div>
  );
}

function PlayerKnowledgeTab({
  model,
}: {
  model: NonNullable<ReturnType<typeof useVideoPlayerModel>>;
}) {
  const { activeTab } = model;
  return (
    <div
      className={cn(
        "flex-1 overflow-y-auto p-5 space-y-4 bg-slate-50/60 transition-colors duration-200",
        activeTab === "knowledge"
          ? "block opacity-100 animate-in fade-in-50 duration-200"
          : "hidden opacity-0",
      )}
    >
      <SourceKnowledge model={model} />
    </div>
  );
}

function PlayerContent({
  model,
}: {
  model: NonNullable<ReturnType<typeof useVideoPlayerModel>>;
}) {
  const {
    panelWidth,
    isOpen,
    playingSource,
    t,
    displayTitle,
    handleDismiss,
    setActiveTab,
    activeTab,
  } = model;
  return (
    <div
      style={{ width: panelWidth }}
      className={cn(
        "flex flex-col h-full bg-white relative transition-opacity duration-200",
        isOpen ? "opacity-100" : "opacity-0 pointer-events-none",
      )}
    >
      <div className="h-16 flex items-center px-5 justify-between border-b border-slate-200 shrink-0 bg-white">
        <div className="flex items-center min-w-0 pr-3 gap-2 flex-1">
          {playingSource.source_index && (
            <span className="font-semibold text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-800 shrink-0">
              {t("player.source", { index: playingSource.source_index })}
            </span>
          )}
          <span
            className="text-sm font-semibold text-slate-900 truncate"
            title={displayTitle}
          >
            {displayTitle}
          </span>
        </div>

        <div className="flex items-center gap-1 shrink-0">
          {playingSource.url && (
            <a
              href={playingSource.url}
              target="_blank"
              rel="noreferrer"
              className="p-2 text-slate-400 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors cursor-pointer"
              title={t("player.openInstagram")}
            >
              <ExternalLink size={16} />
            </a>
          )}
          <button
            type="button"
            onClick={handleDismiss}
            className="p-2 text-slate-400 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors cursor-pointer"
            title={t("player.hidePanel")}
          >
            <PanelRightClose size={18} />
          </button>
        </div>
      </div>

      <div className="flex border-b border-slate-200 px-5 bg-white text-xs font-medium gap-4 shrink-0">
        <button
          type="button"
          onClick={() => setActiveTab("video")}
          className={cn(
            "py-2.5 border-b-2 flex items-center gap-1.5 transition-colors duration-200 cursor-pointer",
            activeTab === "video"
              ? "border-slate-900 text-slate-900 font-semibold"
              : "border-transparent text-slate-500 hover:text-slate-800",
          )}
        >
          <PlayCircle size={14} />
          <span>{t("player.tabPost")}</span>
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("knowledge")}
          className={cn(
            "py-2.5 border-b-2 flex items-center gap-1.5 transition-colors duration-200 cursor-pointer",
            activeTab === "knowledge"
              ? "border-slate-900 text-slate-900 font-semibold"
              : "border-transparent text-slate-500 hover:text-slate-800",
          )}
        >
          <BookOpen size={14} />
          <span>{t("player.tabKnowledge")}</span>
        </button>
      </div>

      <PlayerVideoTab model={model} />

      <PlayerKnowledgeTab model={model} />
    </div>
  );
}

function SourceEmbed({
  model,
}: {
  model: NonNullable<ReturnType<typeof useVideoPlayerModel>>;
}) {
  const {
    isOpen,
    playingSource,
    setIframeLoaded,
    displayTitle,
    iframeLoaded,
    t,
  } = model;
  return (
    <>
      {" "}
      {isOpen &&
        (playingSource.url?.includes("instagram.com") ? (
          <iframe
            sandbox="allow-scripts allow-popups allow-presentation"
            key={playingSource.url}
            onLoad={() => setIframeLoaded(true)}
            loading="lazy"
            referrerPolicy="strict-origin-when-cross-origin"
            title={displayTitle}
            src={(() => {
              try {
                const u = new URL(playingSource.url);
                return u.origin + u.pathname + "/embed/captioned";
              } catch {
                return playingSource.url + "/embed/captioned";
              }
            })().replace("//embed", "/embed")}
            className={cn(
              "w-full h-full border-0 transition-opacity duration-300 bg-white",
              iframeLoaded ? "opacity-100" : "opacity-0",
            )}
            allowFullScreen={true}
            scrolling="no"
          />
        ) : playingSource.url?.includes("tiktok.com") ? (
          <iframe
            sandbox="allow-scripts allow-popups allow-presentation"
            key={playingSource.url}
            onLoad={() => setIframeLoaded(true)}
            loading="lazy"
            referrerPolicy="strict-origin-when-cross-origin"
            title={displayTitle}
            src={`https://www.tiktok.com/embed/v2/${playingSource.url.split("/").pop()?.split("?")[0] || ""}`}
            className={cn(
              "w-full h-full border-0 transition-opacity duration-300 bg-white",
              iframeLoaded ? "opacity-100" : "opacity-0",
            )}
            allow="encrypted-media;"
            allowFullScreen={true}
          />
        ) : (
          <div className="p-8 text-center space-y-3">
            <p className="text-slate-500 text-sm">{t("player.cannotEmbed")}</p>
            <a
              href={playingSource.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 text-xs font-medium text-slate-900 bg-white border border-slate-200 px-3.5 py-2 rounded-lg hover:bg-slate-50 transition-colors"
            >
              <ExternalLink size={14} /> {t("player.openNewTab")}
            </a>
          </div>
        ))}{" "}
    </>
  );
}

function SourceKnowledge({
  model,
}: {
  model: NonNullable<ReturnType<typeof useVideoPlayerModel>>;
}) {
  const { activeTab, playingSource, t, creatorName, hasKnowledge } = model;
  return (
    <>
      {" "}
      {activeTab === "knowledge" && (
        <>
          {playingSource.title && (
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs space-y-1">
              <h3 className="font-semibold text-slate-900 text-sm leading-snug">
                {playingSource.title}
              </h3>
              <p className="text-xs text-slate-500">
                {t("player.byCreator", { creator: creatorName })}
              </p>
            </div>
          )}

          {hasKnowledge ? (
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs space-y-3">
              <div className="flex items-center gap-1.5 pb-2 border-b border-slate-100">
                <BookOpen size={14} className="text-slate-600" />
                <h4 className="text-xs font-semibold text-slate-800 uppercase tracking-wider">
                  {t("player.extractedKnowledge")}
                </h4>
              </div>
              <div className="prose prose-sm max-w-none text-slate-700 text-xs leading-relaxed">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {playingSource.knowledge ||
                    playingSource.summary ||
                    playingSource.caption ||
                    ""}
                </ReactMarkdown>
              </div>
            </div>
          ) : (
            <div className="bg-white p-6 rounded-xl border border-dashed border-slate-200 text-center text-xs text-slate-500">
              {t("player.noNotes")}
            </div>
          )}

          {playingSource.url && (
            <a
              href={playingSource.url}
              target="_blank"
              rel="noopener noreferrer"
              className="w-full flex items-center justify-center gap-2 text-xs font-medium text-slate-700 bg-white border border-slate-200 hover:bg-slate-50 p-2.5 rounded-lg transition-colors cursor-pointer"
            >
              <ExternalLink size={14} /> {t("player.viewOriginal")}
            </a>
          )}
        </>
      )}{" "}
    </>
  );
}
