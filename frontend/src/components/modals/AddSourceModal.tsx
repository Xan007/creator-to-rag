import { CookieUploadTip } from "./CookieUploadTip";
import React, { useState } from "react";
import { Loader2 } from "lucide-react";
import { Modal } from "../ui/Modal";
import { api } from "../../lib/api";
import { useTranslation } from "../../lib/i18n";

export function AddSourceModal({ isOpen, onClose, activeLibrary }: any) {
  const { t } = useTranslation();
  const [url, setUrl] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
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
    if (!url.trim() || !activeLibrary) return;
    setIsSubmitting(true);
    try {
      await api.addSource(activeLibrary.slug, url.trim());
      alert(t("addSource.ingestStarted"));
      setUrl("");
      onClose();
    } catch (err: any) {
      alert(t("addSource.ingestFailed") + (err.message || "Unknown error"));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={t("addSource.title")}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <p className="text-sm text-gray-500">{t("addSource.desc")}</p>

        {!cookiesUploaded && (
          <CookieUploadTip onUploaded={() => setCookiesUploaded(true)} />
        )}

        {activeLibrary && (
          <div className="bg-slate-50 border border-slate-200 rounded-md px-3 py-2 flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              {t("addSource.destination")}
            </span>
            <span className="text-sm font-medium text-slate-900">
              {activeLibrary.name}
            </span>
          </div>
        )}

        <div>
          <label
            htmlFor="field-addsourcemodal-81"
            className="block text-sm font-medium mb-1"
          >
            {t("addSource.videoUrl")}
          </label>
          <input
            id="field-addsourcemodal-81"
            type="text"
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder={t("addSource.urlPlaceholder")}
          />
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-md cursor-pointer"
          >
            {t("addSource.cancel")}
          </button>
          <button
            type="submit"
            disabled={isSubmitting || !url.trim()}
            className="px-4 py-2 text-sm bg-slate-900 text-white rounded-md hover:bg-slate-800 disabled:opacity-50 flex items-center gap-2 cursor-pointer"
          >
            {isSubmitting && <Loader2 size={14} className="animate-spin" />}
            {t("addSource.ingestUrl")}
          </button>
        </div>
      </form>
    </Modal>
  );
}
