import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Patch ResizeObserver BEFORE anything else to prevent benign
// "ResizeObserver loop completed with undelivered notifications" errors
// (triggered by Radix popper/select) from popping the CRA dev overlay.
if (typeof window !== "undefined" && window.ResizeObserver) {
  const RO = window.ResizeObserver;
  window.ResizeObserver = class extends RO {
    constructor(callback) {
      super((entries, observer) => {
        window.requestAnimationFrame(() => {
          try { callback(entries, observer); } catch (e) { /* swallow */ }
        });
      });
    }
  };
}

window.addEventListener("error", (e) => {
  if (e?.message && e.message.includes("ResizeObserver loop")) {
    e.stopImmediatePropagation();
    e.preventDefault();
  }
});

import "@/index.css";
import App from "@/App";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
    },
  },
});

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
