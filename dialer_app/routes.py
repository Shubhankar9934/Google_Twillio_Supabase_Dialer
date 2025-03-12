# dialer_app/routes.py
from fastapi import APIRouter, Request, Form, HTTPException, WebSocket, status
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from dialer_app.services.twilio_service import initiate_outbound_call
from dialer_app.services.websocket_service import WebSocketManager
import asyncio

router = APIRouter()
websocket_manager = WebSocketManager()

class EnableTranscriptionRequest(BaseModel):
    call_sid: str

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="dialer_app/templates")
    return templates.TemplateResponse("index.html", {"request": request})

@router.post("/call")
async def start_call(caller: str = Form(...), receiver: str = Form(...)):
    if not caller or not receiver:
        raise HTTPException(status_code=400, detail="Caller or Receiver not specified")
    call_sid = initiate_outbound_call(caller, receiver)
    return JSONResponse({"status": "Call initiated", "call_sid": call_sid})

@router.post("/call_status")
async def call_status(request: Request):
    # Twilio sends form-encoded data for call status updates.
    try:
        form_data = await request.form()
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=400)
    # Try both uppercase and lowercase keys
    call_sid = form_data.get("CallSid") or form_data.get("callsid")
    call_status = (form_data.get("CallStatus") or form_data.get("callstatus") or "").lower()
    if call_sid and call_status:
        if call_sid in websocket_manager.active_calls:
            websocket_manager.active_calls[call_sid]["state"] = call_status
            print(f"[CallStatus] Updated call {call_sid} to state: {call_status}")
            if call_status in ["completed", "voicemail"]:
                asyncio.create_task(websocket_manager.end_call(call_sid))
    return {"status": "ok"}

@router.post("/toggle_transcription", status_code=status.HTTP_200_OK)
async def toggle_transcription(payload: EnableTranscriptionRequest):
    try:
        call_sid = payload.call_sid
        new_state = websocket_manager.toggle_transcription(call_sid)
        print(f"[Toggle Transcription] Call {call_sid} transcription state: {new_state}")
        if new_state is False and new_state != True:
            raise HTTPException(status_code=404, detail="Call not found or not active")
        return {"message": "Transcription toggled", "call_sid": call_sid, "transcription_enabled": new_state}
    except Exception as e:
        print(f"[Toggle Transcription Error] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.websocket("/twilio")
async def twilio_websocket(websocket: WebSocket):
    await websocket.accept()
    await websocket_manager.handle_twilio_media(websocket)

@router.websocket("/ws")
async def client_websocket(websocket: WebSocket):
    await websocket.accept()
    await websocket_manager.handle_client(websocket)
