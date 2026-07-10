import { useState, useEffect, useRef } from "react";
import { useWebSocket } from "../hooks/useWebSocket";

interface Message {
  agent: string;
  role: string;
  content: string;
  metadata: Record<string, any>;
  timestamp: string;
}

export default function ConversationView() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [filterAgent, setFilterAgent] = useState<string>("all");
  const [autoScroll, setAutoScroll] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { connected, on } = useWebSocket();

  useEffect(() => {
    return on((event) => {
      if (event.type === "message") {
        const msg = event.data as Message;
        setMessages(prev => [...prev, msg]);
      }
    });
  }, [on]);

  useEffect(() => {
    if (autoScroll && messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, autoScroll]);

  const filteredMessages = filterAgent === "all" 
    ? messages 
    : messages.filter(m => m.agent === filterAgent);

  const agents = Array.from(new Set(messages.map(m => m.agent)));

  const getRoleColor = (role: string) => {
    switch (role) {
      case "user": return "#58a6ff";
      case "assistant": return "#3fb950";
      case "tool_call": return "#d29922";
      case "tool_result": return "#8b949e";
      default: return "#c9d1d9";
    }
  };

  const getRoleIcon = (role: string) => {
    switch (role) {
      case "user": return "👤";
      case "assistant": return "🤖";
      case "tool_call": return "🔧";
      case "tool_result": return "📋";
      default: return "💬";
    }
  };

  return (
    <div className="conversation-view">
      <div className="conversation-header">
        <h2>Agent Conversations</h2>
        <div className="conversation-controls">
          <select 
            value={filterAgent} 
            onChange={(e) => setFilterAgent(e.target.value)}
            className="agent-filter"
          >
            <option value="all">All Agents</option>
            {agents.map(a => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>
          <label className="auto-scroll-toggle">
            <input 
              type="checkbox" 
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
            />
            Auto-scroll
          </label>
          <button onClick={() => setMessages([])} className="btn-secondary">
            Clear
          </button>
        </div>
      </div>

      <div className="conversation-status">
        <span className={connected ? "status-connected" : "status-disconnected"}>
          {connected ? "● Connected" : "○ Disconnected"}
        </span>
        <span className="message-count">{filteredMessages.length} messages</span>
      </div>

      <div className="conversation-messages">
        {filteredMessages.map((msg, idx) => (
          <div key={idx} className={`message message-${msg.role}`}>
            <div className="message-header">
              <span className="message-icon">{getRoleIcon(msg.role)}</span>
              <span className="message-agent">{msg.agent}</span>
              <span className="message-role" style={{ color: getRoleColor(msg.role) }}>
                {msg.role}
              </span>
              <span className="message-time">
                {new Date(msg.timestamp).toLocaleTimeString()}
              </span>
            </div>
            <div className="message-content">
              {msg.content || "(empty)"}
            </div>
            {msg.metadata && Object.keys(msg.metadata).length > 0 && (
              <div className="message-metadata">
                {msg.metadata.tool && <span className="metadata-tag">🔧 {msg.metadata.tool}</span>}
                {msg.metadata.turn && <span className="metadata-tag">Turn {msg.metadata.turn}</span>}
                {msg.metadata.model && <span className="metadata-tag">🤖 {msg.metadata.model}</span>}
                {msg.metadata.usage && (
                  <span className="metadata-tag">
                    📊 {msg.metadata.usage.total_tokens || 0} tokens
                  </span>
                )}
              </div>
            )}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>
    </div>
  );
}
