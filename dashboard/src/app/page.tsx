"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

interface Task {
  id: number;
  name: string;
  emoji: string;
  status: string;
  scheduled_start?: string;
  scheduled_end?: string;
}

interface Score {
  score: number;
  task_completion: number;
  time_utilization: number;
  mood: string;
}

export default function Dashboard() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [score, setScore] = useState<Score | null>(null);
  const [loading, setLoading] = useState(true);
  const [currentTime, setCurrentTime] = useState(new Date());

  useEffect(() => {
    async function fetchData() {
      try {
        const [tasksRes, scoreRes] = await Promise.all([
          fetch("http://127.0.0.1:8282/tasks"),
          fetch("http://127.0.0.1:8282/score"),
        ]);
        
        if (tasksRes.ok) setTasks(await tasksRes.json());
        if (scoreRes.ok) setScore(await scoreRes.json());
      } catch (err) {
        console.error("Failed to fetch dashboard data:", err);
      } finally {
        setLoading(false);
      }
    }
    
    fetchData();
    const interval = setInterval(() => {
        fetchData();
        setCurrentTime(new Date());
    }, 60000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <main className="loading">
        <header>
          <h1>SelfHeal</h1>
          <p className="status-text">Initializing life engine...</p>
        </header>
      </main>
    );
  }

  return (
    <main>
      <header className="dashboard-header">
        <div className="brand">
          <h1>SelfHeal</h1>
          <p className="subtitle">Minute-Level Life Orchestrator</p>
          <div className="actions">
            <Link href="/interview" className="btn-minimal">
              START INTERVIEW
            </Link>
          </div>
        </div>
        <div className="score-hero">
          <h2 className="score-value">{Math.round(score?.score || 0)}%</h2>
          <p className="score-label">Productivity Score</p>
        </div>
      </header>

      <section className="card arc-section">
        <div className="section-header">
          <h3>Today's Arc</h3>
          <span className="current-time">{currentTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
        </div>
        <div className="dot-grid-container">
          <div className="dot-grid">
            {Array.from({ length: 24 }).map((_, h) => (
              Array.from({ length: 60 }).map((_, m) => {
                const isPast = h < currentTime.getHours() || (h === currentTime.getHours() && m < currentTime.getMinutes());
                const isCurrent = h === currentTime.getHours() && m === currentTime.getMinutes();
                return (
                  <div 
                    key={`${h}-${m}`} 
                    className={`dot ${isCurrent ? 'active' : isPast ? 'done' : ''}`}
                    title={`${h}:${m}`}
                  />
                );
              })
            ))}
          </div>
        </div>
      </section>

      <section className="timeline-section">
        <div className="section-header">
          <h3>Timeline</h3>
          <span className="badge">{tasks.length} Active Blocks</span>
        </div>
        <ul className="task-list">
          {tasks.map((task) => (
            <li key={task.id} className="task-item">
              <span className="task-time">
                {task.scheduled_start || "--:--"}
              </span>
              <span className="task-name">
                {task.emoji} {task.name}
              </span>
              <span className={`task-status ${task.status === 'done' ? 'success' : ''}`}>
                {task.status.toUpperCase()}
              </span>
            </li>
          ))}
          {tasks.length === 0 && <p className="empty-state">No tasks scheduled for today.</p>}
        </ul>
      </section>

      <footer className="dashboard-footer">
        Memento Mori. Make it count.
      </footer>

      <style jsx>{`
        .dashboard-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-end;
          margin-bottom: 4rem;
          gap: 2rem;
          flex-wrap: wrap;
        }
        .subtitle { color: var(--muted); font-size: 0.8rem; margin-top: 0.2rem; }
        .actions { margin-top: 1.5rem; }
        .btn-minimal {
          color: var(--foreground);
          font-size: 0.7rem;
          text-decoration: none;
          border: 1px solid var(--muted);
          padding: 0.5rem 1rem;
          border-radius: 2px;
          transition: all 0.2s ease;
        }
        .btn-minimal:hover {
          background: var(--foreground);
          color: var(--background);
        }
        .score-hero { text-align: right; }
        .score-label { color: var(--muted); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.1em; }
        
        .section-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 1rem;
        }
        .current-time { font-size: 0.8rem; color: var(--muted); }
        .badge { background: var(--muted); padding: 0.2rem 0.5rem; border-radius: 2px; font-size: 0.6rem; }
        
        .dot-grid-container {
          width: 100%;
          overflow-x: auto;
          cursor: crosshair;
        }
        
        .arc-section { margin-bottom: 4rem; }
        .empty-state { color: var(--muted); margin-top: 2rem; font-size: 0.8rem; }
        .dashboard-footer {
          margin-top: 8rem;
          color: var(--muted);
          font-size: 0.7rem;
          text-align: center;
          padding-bottom: 4rem;
          letter-spacing: 0.2em;
          text-transform: uppercase;
        }

        @media (max-width: 640px) {
          .dashboard-header {
            flex-direction: column;
            align-items: flex-start;
            margin-bottom: 2rem;
          }
          .score-hero { text-align: left; }
          .score-value { font-size: 3rem; }
          .arc-section { margin-bottom: 2rem; }
        }
      `}</style>
    </main>
  );
}
