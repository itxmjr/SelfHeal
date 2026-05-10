# SelfHeal

**SelfHeal** is a minimalist, AI-driven personal life orchestrator. It acts as an autonomous digital manager: it interviews you to build a "Life Model," schedules your day dynamically around your existing calendar commitments, and provides a polished Dashboard to track your progress.

## Core Features
*   **🧠 Life Model Intake:** An interactive interview (CLI or Web) maps out your core goals, priorities, and available hours.
*   **🤖 AI-Assisted Scheduling:** Uses Claude 3.5, GPT-4o, or local Ollama to intelligently slot tasks into your daily schedule based on priority, duration, and energy alignment.
*   **⚛️ "Memento Mori" Dashboard:** A stunning, responsive web dashboard that visualizes your life minute-by-minute through an interactive "Life Arc."
*   **🖥️ Desktop Shell (Tauri):** A native desktop application that bundles the dashboard and background daemon into a single experience.
*   **📅 Deep Integrations:** Full two-way synchronization with ClickUp (Tasks), Google Calendar (Schedule), and Obsidian (Journaling).
*   **⚡ Background Intelligence:** A lightweight FastAPI-powered daemon that autonomously syncs calendars, regenerates schedules, and breaking down large tasks into atomic blocks.

---

## 🚀 Installation & Setup

### 1. Prerequisites
- Python 3.11+
- Node.js & npm (for the Dashboard)
- Rust (if building the Desktop App)

### 2. Configure Environment
Copy the example environment file and customize it:
```bash
cp .env.example .env
# Add your API keys for Anthropic, OpenAI, or ClickUp
```

### 3. Build & Run
**Backend (FastAPI Daemon):**
```bash
uv sync
uv run selfheal daemon start
```

**Frontend (Next.js Dashboard):**
```bash
cd dashboard
npm install
npm run dev
```

---

## 💻 Usage

### The Dashboard
Access the "Memento Mori" dashboard at `http://localhost:3000`. This is the primary interface for visualizing your daily arc and productivity score.

### CLI Commands
*   `selfheal today` - View today's schedule and score in the terminal.
*   `selfheal interview` - Start the life-model intake interview.
*   `selfheal sync` - Force an immediate sync across all integrations.

---

## 🛠️ Layered Architecture
SelfHeal v1 follows a professional layered architecture:
*   **`src/selfheal/models/`**: Strict Pydantic schemas for data validation.
*   **`src/selfheal/repositories/`**: Isolated database access layer.
*   **`src/selfheal/services/`**: Modular business logic (Scheduling, Sync, Tasks).
*   **`src/selfheal/api/`**: FastAPI routers for Web/Desktop communication.
*   **`src/selfheal/workers/`**: Autonomous background task orchestration.

---

## 🤝 Memento Mori.
Make every minute count.
