from __future__ import annotations

import os
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ...interview.session import InterviewSession
from ...db import get_connection, get_score

router = APIRouter(tags=["system"])

@router.get("/status")
async def get_status():
    return {
        "status": "running",
        "pid": os.getpid(),
        "timestamp": datetime.now().isoformat()
    }

@router.get("/score")
async def get_current_score():
    conn = get_connection()
    try:
        return get_score(conn)
    finally:
        conn.close()

@router.websocket("/interview")
async def interview_websocket(websocket: WebSocket):
    await websocket.accept()
    session = InterviewSession()
    
    try:
        initial_q = session.get_initial_question()
        await websocket.send_json({"role": "assistant", "content": initial_q})
        
        while not session.is_complete:
            data = await websocket.receive_text()
            resp = session.respond(data)
            
            if resp == "INTERVIEW_COMPLETE":
                await websocket.send_json({
                    "role": "assistant", 
                    "content": "Interview complete! Your Life Model has been updated.",
                    "done": True,
                    "model": session.model
                })
                break
            
            await websocket.send_json({"role": "assistant", "content": resp})
    except WebSocketDisconnect:
        pass
