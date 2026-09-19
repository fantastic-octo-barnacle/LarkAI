import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { PreferencesProvider } from "./preferences";
import App from "./App";
import "./style.css";
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <PreferencesProvider>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </PreferencesProvider>
  </StrictMode>,
);
