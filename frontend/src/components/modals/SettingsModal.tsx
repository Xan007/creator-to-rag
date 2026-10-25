import React, { useState, useEffect, useCallback } from "react";
import {
  X,
  Settings,
  Upload,
  Trash2,
  CheckCircle,
  Cookie,
  Languages,
} from "lucide-react";
import { api } from "../../lib/api";
import { cn } from "../../lib/utils";
import { useTranslation } from "../../lib/i18n";

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

function SettingsModalContent({ isOpen, onClose }: SettingsModalProps) {
  const { lang, setLang, t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [cookieStatus, setCookieStatus] = useState<{
    exists: boolean;
    size_bytes: number;
  } | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const status = await api.getCookiesStatus();
      setCookieStatus(status);
    } catch {
      console.error("Failed to fetch cookie status");
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      fetchStatus();
    }
  }, [isOpen, fetchStatus]);

  const handleUpload = async () => {
    if (!selectedFile) return;
    setLoading(true);
    try {
      await api.uploadCookies(selectedFile);
      setSelectedFile(null);
      await fetchStatus();
    } catch {
      alert(t("settings.uploadFailed"));
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm(t("settings.deleteCookiesConfirm"))) return;
    setLoading(true);
    try {
      await api.deleteCookies();
      await fetchStatus();
    } catch {
      alert(t("settings.deleteFailed"));
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4 sm:p-6 animate-in fade-in duration-200">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md overflow-hidden flex flex-col animate-in zoom-in-95 duration-200">
        <div className="h-14 flex items-center justify-between px-6 border-b border-slate-100 bg-slate-50/50">
          <div className="flex items-center gap-2 font-semibold text-slate-900">
            <Settings size={18} className="text-slate-500" />
            {t("settings.title")}
          </div>
          <button
            aria-label={t("modal.cancel")}
            onClick={onClose}
            className="text-slate-400 hover:text-slate-900 hover:bg-slate-200/50 p-1.5 rounded-lg transition-colors cursor-pointer"
          >
            <X size={18} />
          </button>
        </div>

        <div className="p-6 space-y-6">
          <div className="space-y-3 pb-6 border-b border-slate-100">
            <div>
              <h3 className="text-sm font-semibold text-slate-900 mb-1 flex items-center gap-2">
                <Languages size={16} className="text-slate-700" />
                {t("settings.languageSection")}
              </h3>
              <p className="text-xs text-slate-500 leading-relaxed">
                {t("settings.languageDesc")}
              </p>
            </div>
            <div className="grid grid-cols-2 gap-2.5">
              <button
                type="button"
                onClick={() => setLang("es")}
                className={cn(
                  "flex items-center justify-center gap-2 px-3.5 py-2.5 rounded-xl text-sm font-medium border transition-colors cursor-pointer",
                  lang === "es"
                    ? "bg-slate-900 text-white border-slate-900 shadow-xs ring-1 ring-slate-900"
                    : "bg-white text-slate-700 border-slate-200 hover:bg-slate-50 hover:border-slate-300",
                )}
              >
                <span>{t("settings.spanish")}</span>
              </button>
              <button
                type="button"
                onClick={() => setLang("en")}
                className={cn(
                  "flex items-center justify-center gap-2 px-3.5 py-2.5 rounded-xl text-sm font-medium border transition-colors cursor-pointer",
                  lang === "en"
                    ? "bg-slate-900 text-white border-slate-900 shadow-xs ring-1 ring-slate-900"
                    : "bg-white text-slate-700 border-slate-200 hover:bg-slate-50 hover:border-slate-300",
                )}
              >
                <span>{t("settings.english")}</span>
              </button>
            </div>
          </div>

          <div>
            <h3 className="text-sm font-semibold text-slate-900 mb-1 flex items-center gap-2">
              <Cookie size={16} className="text-blue-500" />
              {t("settings.cookiesTitle")}
            </h3>
            <p className="text-sm text-slate-500 leading-relaxed">
              {t("settings.cookiesDesc")}
            </p>
          </div>

          <div className="border border-slate-200 rounded-xl p-5 bg-slate-50/50 space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-slate-700">
                {t("settings.currentStatus")}
              </span>
              {cookieStatus?.exists ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-green-50 text-green-700 text-xs font-medium border border-green-200">
                  <CheckCircle size={14} /> {t("settings.active")} (
                  {(cookieStatus.size_bytes / 1024).toFixed(1)} KB)
                </span>
              ) : (
                <span className="inline-flex items-center px-2.5 py-1 rounded-full bg-slate-100 text-slate-600 text-xs font-medium border border-slate-200">
                  {t("settings.notUploaded")}
                </span>
              )}
            </div>

            <div className="pt-4 border-t border-slate-200/60">
              {cookieStatus?.exists ? (
                <div className="flex justify-end">
                  <button
                    onClick={handleDelete}
                    disabled={loading}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-red-600 bg-white border border-red-200 hover:bg-red-50 hover:border-red-300 transition-colors disabled:opacity-50 cursor-pointer"
                  >
                    <Trash2 size={16} /> {t("settings.deleteCookies")}
                  </button>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="flex items-center justify-center w-full">
                    <label
                      className={cn(
                        "flex flex-col items-center justify-center w-full h-32 border-2 border-dashed rounded-xl cursor-pointer transition-colors",
                        selectedFile
                          ? "border-blue-400 bg-blue-50/50"
                          : "border-slate-300 bg-white hover:bg-slate-50 hover:border-slate-400",
                      )}
                    >
                      <div className="flex flex-col items-center justify-center pt-5 pb-6">
                        <Upload
                          size={24}
                          className={cn(
                            "mb-3",
                            selectedFile ? "text-blue-500" : "text-slate-400",
                          )}
                        />
                        <p className="mb-1 text-sm font-medium text-slate-700">
                          {selectedFile
                            ? selectedFile.name
                            : t("settings.clickToUpload")}
                        </p>
                        <p className="text-xs text-slate-500">
                          {t("settings.netscapeFormat")}
                        </p>
                      </div>
                      <input
                        type="file"
                        className="hidden"
                        accept=".txt"
                        onChange={(e) =>
                          setSelectedFile(e.target.files?.[0] || null)
                        }
                      />
                    </label>
                  </div>
                  {selectedFile && (
                    <button
                      onClick={handleUpload}
                      disabled={loading}
                      className="w-full flex justify-center items-center gap-2 bg-slate-900 text-white px-4 py-2.5 rounded-lg text-sm font-medium hover:bg-slate-800 transition-colors disabled:opacity-50 cursor-pointer"
                    >
                      {loading
                        ? t("settings.uploading")
                        : t("settings.uploadFile")}
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function SettingsModal(
  props: Parameters<typeof SettingsModalContent>[0],
) {
  return props.isOpen ? <SettingsModalContent {...props} /> : null;
}
