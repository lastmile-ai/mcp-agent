import { useTheme } from "src/utils/hooks/use-theme";
import "./App.css";
import { Timer } from "./Timer";
import { useWidgetState } from "src/utils/hooks/use-widget-state";
import { useOpenAiGlobal } from "src/utils/hooks/use-openai-global";
import { TimerWidgetState } from "src/utils/types";

function App() {
  const theme = useTheme();
  const toolOutput = useOpenAiGlobal("toolOutput") as TimerWidgetState | null;
  const [widgetState, setWidgetState] = useWidgetState<TimerWidgetState>();

  // Prioritize toolOutput (from MCP server) over widgetState for initial values
  // toolOutput contains the parameters passed to the timer tool
  const hours = toolOutput?.hours ?? widgetState?.hours ?? 0;
  const minutes = toolOutput?.minutes ?? widgetState?.minutes ?? 0;
  const seconds = toolOutput?.seconds ?? widgetState?.seconds ?? 0;
  const message = toolOutput?.message ?? widgetState?.message ?? "";

  const handleTimerUpdate = (h: number, m: number, s: number, running: boolean) => {
    setWidgetState({
      hours: h,
      minutes: m,
      seconds: s,
      message: message,
      isRunning: running,
      isPaused: false
    });

    // Notify the model when timer completes
    if (h === 0 && m === 0 && s === 0 && !running) {
      window.openai?.sendFollowUpMessage({
        prompt: "The timer has completed!",
      });
    }
  };

  return (
    <div className={`App ${theme}`} data-theme={theme}>
      <Timer
        initialHours={hours}
        initialMinutes={minutes}
        initialSeconds={seconds}
        message={message}
        onTimerUpdate={handleTimerUpdate}
      />
    </div>
  );
}

export default App;
