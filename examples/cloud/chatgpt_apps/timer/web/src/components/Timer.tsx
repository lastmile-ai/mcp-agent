import { useState, useEffect, useRef } from "react";
import { Card, CardHeader, CardContent } from "./ui/card";
import { Button } from "./ui/button";
import "./Timer.css";

interface TimerProps {
  initialHours: number;
  initialMinutes: number;
  initialSeconds: number;
  message?: string;
  onTimerUpdate?: (hours: number, minutes: number, seconds: number, isRunning: boolean) => void;
}

export function Timer({ initialHours, initialMinutes, initialSeconds, message = "", onTimerUpdate }: TimerProps) {
  const [hours, setHours] = useState(initialHours);
  const [minutes, setMinutes] = useState(initialMinutes);
  const [seconds, setSeconds] = useState(initialSeconds);
  const [isRunning, setIsRunning] = useState(false);
  const [isCompleted, setIsCompleted] = useState(false);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

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
    setHours(initialHours);
    setMinutes(initialMinutes);
    setSeconds(initialSeconds);
    setIsCompleted(false);
  }, [initialHours, initialMinutes, initialSeconds]);

  useEffect(() => {
    if (isRunning) {
      intervalRef.current = setInterval(() => {
        // Use a ref to get current values and calculate new time atomically
        setHours((h) => {
          setMinutes((m) => {
            setSeconds((s) => {
              // Calculate total seconds and decrement
              let totalSeconds = h * 3600 + m * 60 + s - 1;

              // Check if timer completed
              if (totalSeconds <= 0) {
                setIsRunning(false);
                setIsCompleted(true);
                setHours(0);
                setMinutes(0);
                if (onTimerUpdate) {
                  onTimerUpdate(0, 0, 0, false);
                }
                return 0;
              }

              // Calculate new time components
              const newHours = Math.floor(totalSeconds / 3600);
              const newMinutes = Math.floor((totalSeconds % 3600) / 60);
              const newSeconds = totalSeconds % 60;

              // Update states
              setHours(newHours);
              setMinutes(newMinutes);

              return newSeconds;
            });
            return m;
          });
          return h;
        });
      }, 1000);
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [isRunning, onTimerUpdate]);

  const handleStart = () => {
    if (hours === 0 && minutes === 0 && seconds === 0) {
      return;
    }
    setIsRunning(true);
  };

  const handleReset = () => {
    setIsRunning(false);
    setIsCompleted(false);
    setHours(initialTimeRef.current.hours);
    setMinutes(initialTimeRef.current.minutes);
    setSeconds(initialTimeRef.current.seconds);
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
