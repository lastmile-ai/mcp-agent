import { useState, useEffect, useRef } from "react";
import { Card, CardHeader, CardContent } from "./ui/card";
import { Button } from "./ui/button";
import "./Timer.css";

const totalSecondsFor = (hours: number, minutes: number, seconds: number) =>
  hours * 3600 + minutes * 60 + seconds;

interface TimerProps {
  initialHours: number;
  initialMinutes: number;
  initialSeconds: number;
  message?: string;
  onTimerUpdate?: (hours: number, minutes: number, seconds: number, isRunning: boolean) => void;
}

export function Timer({ initialHours, initialMinutes, initialSeconds, message = "", onTimerUpdate }: TimerProps) {
  const [remainingSeconds, setRemainingSeconds] = useState(() =>
    totalSecondsFor(initialHours, initialMinutes, initialSeconds)
  );
  const [isRunning, setIsRunning] = useState(false);
  const [isCompleted, setIsCompleted] = useState(false);
  const completionNotifiedRef = useRef(false);

  // Store initial values for reset
  const initialTimeRef = useRef({
    hours: initialHours,
    minutes: initialMinutes,
    seconds: initialSeconds
  });

  useEffect(() => {
    // Update initial values when props change
    initialTimeRef.current = {
      hours: initialHours,
      minutes: initialMinutes,
      seconds: initialSeconds
    };
    setRemainingSeconds(
      totalSecondsFor(initialHours, initialMinutes, initialSeconds)
    );
    setIsRunning(false);
    setIsCompleted(false);
    completionNotifiedRef.current = false;
  }, [initialHours, initialMinutes, initialSeconds]);

  useEffect(() => {
    if (!isRunning) return;

    const interval = setInterval(() => {
      setRemainingSeconds((current) => Math.max(current - 1, 0));
    }, 1000);

    return () => {
      clearInterval(interval);
    };
  }, [isRunning]);

  useEffect(() => {
    if (remainingSeconds > 0) {
      completionNotifiedRef.current = false;
      return;
    }

    if (!isRunning || completionNotifiedRef.current) return;

    completionNotifiedRef.current = true;
    setIsRunning(false);
    setIsCompleted(true);
    onTimerUpdate?.(0, 0, 0, false);
  }, [isRunning, onTimerUpdate, remainingSeconds]);

  const hours = Math.floor(remainingSeconds / 3600);
  const minutes = Math.floor((remainingSeconds % 3600) / 60);
  const seconds = remainingSeconds % 60;

  const handleStart = () => {
    if (remainingSeconds === 0) return;
    completionNotifiedRef.current = false;
    setIsRunning(true);
  };

  const handleReset = () => {
    setIsRunning(false);
    setIsCompleted(false);
    completionNotifiedRef.current = false;
    setRemainingSeconds(
      totalSecondsFor(
        initialTimeRef.current.hours,
        initialTimeRef.current.minutes,
        initialTimeRef.current.seconds
      )
    );
    if (onTimerUpdate) {
      onTimerUpdate(
        initialTimeRef.current.hours,
        initialTimeRef.current.minutes,
        initialTimeRef.current.seconds,
        false
      );
    }
  };

  const formatTime = (value: number): string => {
    return value.toString().padStart(2, "0");
  };

  return (
    <Card>
      <div className={`timer-wrapper ${isCompleted ? "timer-completed" : ""}`}>
        <CardHeader className="timer-header">
          <div className="timer-title">
            <ClockIcon className="timer-icon" />
            <div>Timer</div>
          </div>
          <div className="timer-description">
            {isCompleted
              ? "Time's up!"
              : message || "Countdown to zero from the initial duration."}
          </div>
        </CardHeader>
        <CardContent className="timer-content">
          <div className="timer-grid">
            <div className="timer-labels">
              <div className="timer-label">Hours</div>
              <div className="timer-label">Minutes</div>
              <div className="timer-label">Seconds</div>
            </div>
            <div className="timer-values">
              <div className={`timer-value ${isCompleted ? "timer-value-completed" : ""}`}>{formatTime(hours)}</div>
              <div className={`timer-value ${isCompleted ? "timer-value-completed" : ""}`}>{formatTime(minutes)}</div>
              <div className={`timer-value ${isCompleted ? "timer-value-completed" : ""}`}>{formatTime(seconds)}</div>
            </div>
          </div>
          <div className="timer-buttons">
            <Button size="sm" onClick={handleStart} disabled={isRunning || isCompleted}>
              {isRunning ? "Running..." : isCompleted ? "Completed" : "Start"}
            </Button>
            <Button variant="outline" size="sm" onClick={handleReset}>
              Reset
            </Button>
          </div>
        </CardContent>
      </div>
    </Card>
  );
}

function ClockIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      {...props}
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  );
}
