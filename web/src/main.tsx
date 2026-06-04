import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { BootstrapErrorBoundary } from "./components/BootstrapErrorBoundary";
import { initTheme, isTauri } from "./theme";
import "./styles/app.css";
import "./styles/chrome.css";
import "./styles/content-surfaces.css";

initTheme();
if (isTauri()) {
  document.body.classList.add("is-tauri");
}

const rootEl = document.getElementById("root");
if (!rootEl) {
  throw new Error("#root not found");
}

ReactDOM.createRoot(rootEl).render(
  <React.StrictMode>
    <BootstrapErrorBoundary>
      <App />
    </BootstrapErrorBoundary>
  </React.StrictMode>,
);
