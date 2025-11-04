import { useTheme } from "src/utils/hooks/use-theme";
import "./App.css";
import { Coin } from "./Coin";
import { useWidgetState } from "src/utils/hooks/use-widget-state";
import { CoinFlipWidgetState } from "src/utils/types";

function App() {
  const theme = useTheme();
  const [widgetState, setWidgetState] = useWidgetState<CoinFlipWidgetState>();
  const flipResult = widgetState?.flipResult ?? "heads";

  const handleFlipResult = (result: "heads" | "tails") => {
    setWidgetState({ flipResult: result });
    // Whenever the user flips the coin manually, let the model know
    window.openai?.sendFollowUpMessage({
      prompt: "I flipped the coin again and got " + result + ".",
    });
  };

  return (
    <div className={`App ${theme}`} data-theme={theme}>
      <Coin flipResult={flipResult} onFlipResult={handleFlipResult} />
      <p className="instruction-text">Click on the coin to flip it!</p>
    </div>
  );
}

export default App;
