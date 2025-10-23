import React from "react";
import ReactDOM from "react-dom/client";
import "./index.css";
import App from "./components/App";
import { setupDevOpenAiGlobal } from "src/utils/dev-openai-global";

// Add openai globals in development mode for easier testing
setupDevOpenAiGlobal();

const root = ReactDOM.createRoot(
  document.getElementById("coinflip-root") as HTMLElement
);
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
