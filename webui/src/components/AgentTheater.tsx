import { useEffect, useRef } from "react";
import type { WSEvent } from "../hooks/useWebSocket";

interface Props {
  runEvents: WSEvent[];
  onCancel: () => void;
}

export default function AgentTheater({ runEvents, onCancel }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [runEvents.length]);

  return (
    <div className="theater">
      <div className="theater-header">
        <h2>Live Agent Theater</h2>
        <button onClick={onCancel} className="btn-danger">Cancel</button>
      </div>

      <div className="theater-stream">
        {runEvents.length === 0 && (
          <div className="waiting">
            <div className="spinner" />
            <p>Agents preparing to work...</p>
          </div>
        )}

        {[...runEvents].reverse().map((e, i) => {
          const event = e.event as string || e.type as string || "";
          const data = e.data as Record<string, string> || {};
          const isStart = event.includes("start") || event.includes("running");
          const isDone = event.includes("complete") || event.includes("done");
          const isError = event.includes("error");

          return (
            <div key={i} className={`event ${isDone ? "done" : ""} ${isError ? "error" : ""}`}>
              <span className={`dot ${isStart ? "running" : ""} ${isDone ? "done" : ""} ${isError ? "error" : ""}`} />
              <div>
                <strong>{data.agent || event}</strong>
                <span className="dim"> {data.phase || ""} {data.model ? `(${data.model})` : ""}</span>
              </div>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
