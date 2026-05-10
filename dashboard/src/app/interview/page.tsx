"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";

interface Message {
  role: "assistant" | "user";
  content: string;
}

export default function InterviewPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const [done, setDone] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ws = new WebSocket("ws://127.0.0.1:8282/interview");
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setMessages((prev) => [...prev, { role: "assistant", content: data.content }]);
      if (data.done) {
        setDone(true);
      }
    };

    setSocket(ws);
    return () => ws.close();
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || !socket || done) return;

    socket.send(input);
    setMessages((prev) => [...prev, { role: "user", content: input }]);
    setInput("");
  };

  return (
    <main className="interview-container">
      <header className="interview-header">
        <div className="nav-back">
          <Link href="/" className="back-link">← DASHBOARD</Link>
          <h1 className="title">Life Interview</h1>
        </div>
        {done && <span className="status-badge">COMPLETE</span>}
      </header>

      <div className="chat-area">
        {messages.map((m, i) => (
          <div key={i} className={`message-wrapper ${m.role}`}>
            <p className="role-label">{m.role}</p>
            <div className="message-content">
              {m.content}
            </div>
          </div>
        ))}
        <div ref={chatEndRef} />
      </div>

      <form onSubmit={sendMessage} className="chat-form">
        <input 
          type="text" 
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={done ? "Interview complete." : "Type your answer..."}
          disabled={done}
          className="chat-input"
        />
        <button 
          type="submit" 
          disabled={done || !input.trim()}
          className="chat-submit"
        >
          SEND
        </button>
      </form>

      <footer className="chat-footer">
        Be honest. This drives your reality.
      </footer>

      <style jsx>{`
        .interview-container {
          max-width: 800px;
          padding: var(--padding-page);
          height: 100vh;
          display: flex;
          flex-direction: column;
          margin: 0 auto;
        }
        
        .interview-header {
          margin-bottom: 2rem;
          display: flex;
          justify-content: space-between;
          align-items: flex-end;
          flex-wrap: wrap;
          gap: 1rem;
        }
        
        .back-link {
          color: var(--muted);
          text-decoration: none;
          font-size: 0.7rem;
          letter-spacing: 0.1em;
        }
        
        .title { margin-top: 0.5rem; }
        
        .status-badge {
          color: var(--success);
          font-size: 0.7rem;
          border: 1px solid var(--success);
          padding: 0.2rem 0.6rem;
          border-radius: 2px;
        }

        .chat-area {
          flex: 1;
          overflow-y: auto;
          margin-bottom: 2rem;
          padding-right: 0.5rem;
        }
        
        .chat-area::-webkit-scrollbar { width: 2px; }
        .chat-area::-webkit-scrollbar-thumb { background: var(--muted); }

        .message-wrapper {
          margin-bottom: 2rem;
          display: flex;
          flex-direction: column;
        }
        
        .message-wrapper.user { align-items: flex-end; }
        .message-wrapper.assistant { align-items: flex-start; }
        
        .role-label {
          color: var(--muted);
          font-size: 0.6rem;
          margin-bottom: 0.4rem;
          text-transform: uppercase;
          letter-spacing: 0.1em;
        }
        
        .message-content {
          max-width: 90%;
          line-height: 1.6;
          font-size: 0.95rem;
          white-space: pre-wrap;
        }
        
        .user .message-content {
          background: var(--dim);
          border: 1px solid var(--muted);
          padding: 1rem;
          border-radius: 4px;
        }

        .chat-form {
          display: flex;
          gap: 0.5rem;
          padding: 1rem 0;
        }
        
        .chat-input {
          flex: 1;
          background: var(--dim);
          border: 1px solid var(--muted);
          color: var(--foreground);
          padding: 1rem;
          font-family: var(--font-mono);
          font-size: 0.9rem;
          outline: none;
          border-radius: 2px;
        }
        
        .chat-input:focus { border-color: var(--foreground); }
        
        .chat-submit {
          background: var(--accent);
          color: var(--background);
          border: none;
          padding: 0 2rem;
          cursor: pointer;
          font-family: var(--font-mono);
          font-weight: bold;
          font-size: 0.8rem;
          border-radius: 2px;
          transition: opacity 0.2s;
        }
        
        .chat-submit:disabled { opacity: 0.3; cursor: not-allowed; }

        .chat-footer {
          padding: 1rem 0;
          color: var(--muted);
          font-size: 0.6rem;
          text-align: center;
          text-transform: uppercase;
          letter-spacing: 0.1em;
        }

        @media (max-width: 640px) {
          .interview-container { padding: 1rem; }
          .chat-form { flex-direction: column; }
          .chat-submit { padding: 1rem; }
          .message-content { max-width: 100%; }
        }
      `}</style>
    </main>
  );
}
