import { Theme } from "../types";
import { useOpenAiGlobal } from "./use-openai-global";

export function useTheme(): Theme {
  return useOpenAiGlobal("theme") ?? "light";
}
