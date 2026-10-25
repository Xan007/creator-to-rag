import i18n from "i18next";
import {
  initReactI18next,
  useTranslation as useI18nextTranslation,
} from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import esTranslation from "../locales/es.json";
import enTranslation from "../locales/en.json";

export const defaultNS = "translation";
export const resources = {
  es: { translation: esTranslation },
  en: { translation: enTranslation },
} as const;

export type Language = "es" | "en";

const STORAGE_KEY = "creators_rag_language";

function initialLanguage() {
  try {
    return localStorage.getItem(STORAGE_KEY) || 'es';
  } catch {
    return 'es';
  }
}

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: "es",
    lng: initialLanguage(),
    debug: false,
    interpolation: {
      escapeValue: false,
    },
    detection: {
      order: ["localStorage", "navigator"],
      lookupLocalStorage: STORAGE_KEY,
      caches: ["localStorage"],
    },
  });

export function useTranslation() {
  const { t, i18n: instance } = useI18nextTranslation();
  const currentLang = (
    instance.language?.startsWith("en") ? "en" : "es"
  ) as Language;

  const setLang = (lang: Language) => {
    instance.changeLanguage(lang);
    try {
      localStorage.setItem(STORAGE_KEY, lang);
    } catch {
      // ignore
    }
  };

  const toggleLang = () => {
    setLang(currentLang === "es" ? "en" : "es");
  };

  return {
    t,
    i18n: instance,
    lang: currentLang,
    setLang,
    toggleLang,
  };
}

export default i18n;
