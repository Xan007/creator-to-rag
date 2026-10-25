import { StrictMode, lazy, Suspense } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
const App =
  import.meta.env.VITE_APP_MODE === "query"
    ? lazy(() => import("./PublicApp.tsx"))
    : lazy(() => import("./App.tsx"));
import { LanguageProvider } from "./lib/LanguageProvider";
import { ErrorBoundary } from "./components/ui/ErrorBoundary";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
      <LanguageProvider>
        <Suspense fallback={null}>
          <App />
        </Suspense>
      </LanguageProvider>
    </ErrorBoundary>
  </StrictMode>,
);
