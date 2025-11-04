import { useState } from "react";
import "./Coin.css";

interface CoinProps {
  flipResult: "heads" | "tails";
  onFlipResult: (result: "heads" | "tails") => void;
}

export function Coin({ flipResult, onFlipResult }: CoinProps) {
  const [isFlipping, setIsFlipping] = useState(false);

  const handleCoinFlip = () => {
    if (isFlipping) return;

    setIsFlipping(true);

    setTimeout(() => {
      const flipResult = Math.random() < 0.5 ? "heads" : "tails";
      setIsFlipping(false);

      onFlipResult(flipResult);
    }, 600);
  };

  return (
    <div className="coin-container">
      <div
        className={`coin ${isFlipping ? "flipping" : ""} ${flipResult}`}
        onClick={handleCoinFlip}
      >
        <div className="coin-face heads">H</div>
        <div className="coin-face tails">T</div>
      </div>
    </div>
  );
}
