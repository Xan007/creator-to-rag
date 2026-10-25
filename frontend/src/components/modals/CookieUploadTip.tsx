import { AlertCircle, Upload } from "lucide-react";
import { api } from "../../lib/api";
import { useTranslation } from "../../lib/i18n";

export function CookieUploadTip({ onUploaded }: { onUploaded: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-lg p-3 text-sm flex gap-3 items-start animate-in fade-in zoom-in-95 duration-300">
      <AlertCircle className="shrink-0 mt-0.5 text-amber-600" size={16} />
      <div className="leading-relaxed flex-1">
        <p>
          <span className="font-semibold">{t("addProfile.tip")}</span>{" "}
          {t("addProfile.cookieTip")}
        </p>
        <label className="mt-2 cursor-pointer inline-flex items-center gap-1.5 px-2.5 py-1.5 bg-amber-100 hover:bg-amber-200 text-amber-900 rounded text-xs font-medium transition-colors">
          <Upload size={14} />
          {t("addProfile.uploadCookies")}
          <input
            type="file"
            accept=".txt"
            className="sr-only"
            onChange={async (event) => {
              const file = event.target.files?.[0];
              if (!file) return;
              try {
                await api.uploadCookies(file);
                onUploaded();
                alert(t("addProfile.cookiesUploaded"));
              } catch {
                alert(t("addProfile.cookiesFailed"));
              }
            }}
          />
        </label>
      </div>
    </div>
  );
}
