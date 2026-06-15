import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { BootstrapErrorBoundary } from "./components/BootstrapErrorBoundary";
import { TweaksDemoProvider } from "./context/TweaksDemoContext";
import { initTheme, isTauri } from "./theme";
import { initDesktopZoom } from "./utils/desktopZoom";
import { getLocale } from "./i18n/locale";

// Design system (SSOT: ~/Downloads/Agent lab/styles/) — order matters
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/layout.css";
import "./styles/surfaces.css";
import "./styles/plan-execute.css";
import "./styles/overlays.css";
import "./styles/tweaks.css";
import "./styles/prototype-panels.css";

initTheme();
document.documentElement.lang = getLocale();
if (isTauri()) {
  document.body.classList.add("is-tauri");
  initDesktopZoom();
}

const rootEl = document.getElementById("root");
if (!rootEl) {
  throw new Error("#root not found");
}

ReactDOM.createRoot(rootEl).render(
  <React.StrictMode>
    <TweaksDemoProvider>
      <BootstrapErrorBoundary>
        <App />
      </BootstrapErrorBoundary>
    </TweaksDemoProvider>
  </React.StrictMode>,
);
