import type { OpenAiGlobals } from "./types";

/**
 * Setup mock window.openai global for development.
 * In production, this global is provided by the OpenAI iframe sandbox.
 */
export function setupDevOpenAiGlobal(): void {
  console.log("Setting up dev OpenAI global...");
  if (window.openai || process.env.NODE_ENV !== "development") {
    return;
  }

  const mockOpenAi: OpenAiGlobals = {
    // visuals
    theme: "light",
    userAgent: {
      device: { type: "desktop" },
      capabilities: {
        hover: true,
        touch: false,
      },
    },
    locale: "en-US",

    // layout
    maxHeight: 800,
    displayMode: "inline",
    safeArea: {
      insets: {
        top: 0,
        bottom: 0,
        left: 0,
        right: 0,
      },
    },

    toolInput: {},
    toolOutput: null,
    toolResponseMetadata: null,
    widgetState: null,
    setWidgetState: async (state: any) => {
      console.log("[Dev] setWidgetState called with:", state);
      mockOpenAi.widgetState = state;
    },
  };

  (window as any).openai = {
    ...mockOpenAi,
    callTool: async (name: string, args: Record<string, unknown>) => {
      console.log("[Dev] callTool called:", name, args);
      return { result: "Mock tool response" };
    },
    sendFollowUpMessage: async (args: { prompt: string }) => {
      console.log("[Dev] sendFollowUpMessage called:", args);
    },
    openExternal: (payload: { href: string }) => {
      console.log("[Dev] openExternal called:", payload);
      window.open(payload.href, "_blank");
    },
    requestDisplayMode: async (args: { mode: any }) => {
      console.log("[Dev] requestDisplayMode called:", args);
      mockOpenAi.displayMode = args.mode;
      return { mode: args.mode };
    },
  };

  console.log("[Dev] Mock window.openai initialized");
}
