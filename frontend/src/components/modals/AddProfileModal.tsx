import { CookieUploadTip } from "./CookieUploadTip";
import React, { useState } from "react";
import { Loader2 } from "lucide-react";
import { Modal } from "../ui/Modal";
import { api } from "../../lib/api";
import { useTranslation } from "../../lib/i18n";

export function AddProfileModal({ isOpen, onClose, activeLibrary }: any) {
  const { t } = useTranslation();
  const [input, setInput] = useState("");
  const [platform, setPlatform] = useState("auto");
  const [maxPosts, setMaxPosts] = useState(50);
  const [captionOnly, setCaptionOnly] = useState(false);
  const [keepMedia, setKeepMedia] = useState(false);
  const [interests, setInterests] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [isChecking, setIsChecking] = useState(false);
  const [cookiesUploaded, setCookiesUploaded] = useState(true);

  React.useEffect(() => {
    if (isOpen) {
      api
        .getCookiesStatus()
        .then((res) => setCookiesUploaded(res.exists))
        .catch(() => setCookiesUploaded(true));
    }
  }, [isOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || !activeLibrary) return;

    // Auto detect if platform is auto
    let detectedPlatform = platform;
    if (platform === "auto") {
      if (input.includes("tiktok.com")) detectedPlatform = "tiktok";
      else if (input.includes("instagram.com")) detectedPlatform = "instagram";
      else detectedPlatform = "instagram"; // default to IG if just username
    }

    // Extract username
    let username = input.trim();
    const match = username.match(
      /(?:instagram\.com\/|tiktok\.com\/@)([^/?]+)/i,
    );
    if (match) {
      username = match[1];
    } else {
      username = username.replace(/^@/, "");
    }

    setIsChecking(true);
    setIsChecking(false);

    setIsSubmitting(true);
    try {
      if (detectedPlatform === "tiktok") {
        const fullUrl = input.includes("tiktok.com")
          ? input
          : `https://www.tiktok.com/@${username}`;
        await api.addSource(activeLibrary.slug, fullUrl, {
          caption_only: captionOnly,
          keep_media: keepMedia,
          interests: interests.trim() ? interests.trim() : undefined,
          max_posts: maxPosts,
        });
      } else {
        await api.addProfile(activeLibrary.slug, username, {
          max_posts: maxPosts,
          caption_only: captionOnly,
          keep_media: keepMedia,
          interests: interests.trim() ? interests.trim() : undefined,
        });
      }
      alert(t("addProfile.ingestStarted"));
      setInput("");
      onClose();
    } catch (err: any) {
      alert(t("addProfile.ingestFailed") + (err.message || "Unknown error"));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={t("addProfile.title")}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <p className="text-sm text-gray-500">{t("addProfile.desc")}</p>

        {!cookiesUploaded && (
          <CookieUploadTip onUploaded={() => setCookiesUploaded(true)} />
        )}

        {activeLibrary && (
          <div className="bg-slate-50 border border-slate-200 rounded-md px-3 py-2 flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              {t("addProfile.destination")}
            </span>
            <span className="text-sm font-medium text-slate-900">
              {activeLibrary.name}
            </span>
          </div>
        )}

        <div>
          <label
            htmlFor="field-addprofilemodal-124"
            className="block text-sm font-medium mb-1"
          >
            {t("addProfile.platform")}
          </label>
          <select
            id="field-addprofilemodal-124"
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 cursor-pointer"
          >
            <option value="auto">{t("addProfile.platformAuto")}</option>
            <option value="instagram">{t("addProfile.platformIg")}</option>
            <option value="tiktok">{t("addProfile.platformTiktok")}</option>
          </select>
        </div>

        <div>
          <label
            htmlFor="field-addprofilemodal-136"
            className="block text-sm font-medium mb-1"
          >
            {t("addProfile.urlOrUser")}
          </label>
          <input
            id="field-addprofilemodal-136"
            type="text"
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={t("addProfile.urlOrUserPlaceholder")}
          />
        </div>

        <div>
          <label
            htmlFor="field-addprofilemodal-146"
            className="block text-sm font-medium mb-1"
          >
            {t("addProfile.interests")}
          </label>
          <input
            id="field-addprofilemodal-146"
            type="text"
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900"
            value={interests}
            onChange={(e) => setInterests(e.target.value)}
            placeholder={t("addProfile.interestsPlaceholder")}
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label
              htmlFor="field-addprofilemodal-157"
              className="block text-sm font-medium mb-1"
            >
              {t("addProfile.maxPosts")}
            </label>
            <input
              id="field-addprofilemodal-157"
              type="number"
              min="1"
              max="200"
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900"
              value={maxPosts}
              onChange={(e) => setMaxPosts(parseInt(e.target.value) || 50)}
            />
          </div>
        </div>

        <div className="space-y-2 pt-2 border-t border-gray-100">
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={captionOnly}
              onChange={(e) => setCaptionOnly(e.target.checked)}
              className="rounded text-slate-900 focus:ring-slate-900"
            />
            {t("addProfile.captionOnly")}
          </label>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={keepMedia}
              onChange={(e) => setKeepMedia(e.target.checked)}
              className="rounded text-slate-900 focus:ring-slate-900"
            />
            {t("addProfile.keepMedia")}
          </label>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-md cursor-pointer"
          >
            {t("addProfile.cancel")}
          </button>
          <button
            type="submit"
            disabled={isSubmitting || isChecking || !input.trim()}
            className="px-4 py-2 text-sm bg-slate-900 text-white rounded-md hover:bg-slate-800 disabled:opacity-50 flex items-center gap-2 cursor-pointer"
          >
            {(isSubmitting || isChecking) && (
              <Loader2 size={14} className="animate-spin" />
            )}
            {isChecking
              ? t("addProfile.verifying")
              : t("addProfile.startIngest")}
          </button>
        </div>
      </form>
    </Modal>
  );
}
