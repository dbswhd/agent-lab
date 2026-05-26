import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { initTheme, isTauri } from "./theme";
import "./styles/app.css";

initTheme();
if (isTauri()) {
  document.body.classList.add("is-tauri");
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
