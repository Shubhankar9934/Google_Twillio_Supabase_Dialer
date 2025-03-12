# dialer_app/services/websocket_service.py
import base64
import asyncio
import json
import datetime
from dialer_app.services.google_stt_service import GoogleSTTService
from dialer_app.services.database_service import DatabaseService
from dialer_app.services.summarization_service import generate_summary
from dialer_app.config import Config

class WebSocketManager:
    def __init__(self):
        self.active_calls = {}
        self.database_service = DatabaseService()

    def toggle_transcription(self, call_id: str) -> bool:
        call_data = self.active_calls.get(call_id)
        if not call_data:
            return False
        call_data["transcribe_enabled"] = not call_data["transcribe_enabled"]
        print(f"[WebSocketManager] Transcription toggled for call {call_id}: {call_data['transcribe_enabled']}")
        return call_data["transcribe_enabled"]

    async def handle_twilio_media(self, websocket):
        call_id = None
        try:
            print("[WebSocketManager] Twilio WebSocket connection established")
            handshake = await websocket.receive_text()
            print(f"[WebSocketManager] Received handshake: {handshake}")

            async for message in websocket.iter_text():
                data = json.loads(message)
                event = data.get("event", "")
                if event == "start":
                    call_id = data["start"]["callSid"]
                    print(f"[WebSocketManager] Twilio stream START for call {call_id}")
                    if call_id not in self.active_calls:
                        current_loop = asyncio.get_running_loop()
                        inbound_service = GoogleSTTService(call_id, "inbound", self.broadcast_transcript, loop=current_loop)
                        outbound_service = GoogleSTTService(call_id, "outbound", self.broadcast_transcript, loop=current_loop)
                        inbound_task = asyncio.create_task(inbound_service.connect())
                        outbound_task = asyncio.create_task(outbound_service.connect())
                        self.active_calls[call_id] = {
                            "inbound_service": inbound_service,
                            "outbound_service": outbound_service,
                            "inbound_task": inbound_task,
                            "outbound_task": outbound_task,
                            "clients": set(),
                            "transcribe_enabled": True,
                            "inbound_connected": False,
                            "outbound_connected": False,
                            "state": "initiated",  # initial state
                            "start_time": datetime.datetime.utcnow(),
                            "verified_caller": Config.VERIFIED_CALLER_NUMBER,
                            "verified_receiver": Config.DEFAULT_RECEIVER_NUMBER,
                            "transcript": []
                        }
                elif event == "media":
                    if call_id in self.active_calls:
                        call_data = self.active_calls[call_id]
                        track = data["media"]["track"]
                        payload = data["media"]["payload"]
                        audio_data = base64.b64decode(payload)

                        # Mark connection as connected for each track if not already set.
                        if track == "inbound" and not call_data["inbound_connected"]:
                            call_data["inbound_connected"] = True
                            print(f"[WebSocketManager] Agent connected for call {call_id}")
                        if track == "outbound" and not call_data["outbound_connected"]:
                            call_data["outbound_connected"] = True
                            print(f"[WebSocketManager] Customer connected for call {call_id}")

                        # If both sides are connected and transcription is enabled, force state to "in-progress"
                        if call_data["transcribe_enabled"] and call_data["inbound_connected"] and call_data["outbound_connected"]:
                            if call_data.get("state") != "in-progress":
                                call_data["state"] = "in-progress"
                                print(f"[WebSocketManager] Call {call_id} state updated to in-progress")
                                # Send update to all subscribed clients
                                status_update = {"callStatus": "Call in-progress"}
                                for client_ws in call_data["clients"]:
                                    try:
                                        await client_ws.send_json(status_update)
                                    except Exception as e:
                                        print(f"[WebSocketManager] Error sending call status update: {e}")
                            # Process audio from each track
                            if track == "inbound":
                                await call_data["inbound_service"].send_audio(audio_data)
                            elif track == "outbound":
                                await call_data["outbound_service"].send_audio(audio_data)
                        else:
                            print(f"[WebSocketManager] Skipping audio for call {call_id} - current state: {call_data.get('state')}")
                elif event == "stop":
                    print(f"[WebSocketManager] Twilio stream STOP for call {call_id}")
                    await self.end_call(call_id)
        except Exception as e:
            print(f"[WebSocketManager] Error handling Twilio media: {e}")
        finally:
            if call_id:
                await self.end_call(call_id)

    async def broadcast_transcript(self, call_id, transcript, track):
        await self._broadcast_transcript_async(call_id, transcript, track)

    async def _broadcast_transcript_async(self, call_id, transcript, track):
        call_data = self.active_calls.get(call_id)
        if not call_data:
            return
        label = "Agent:" if track == "inbound" else "Customer:"
        message = {"transcript": transcript, "track": track}
        call_data.setdefault("transcript", []).append(f"{label} {transcript}")
        for client_ws in call_data["clients"]:
            try:
                await client_ws.send_json(message)
            except Exception as e:
                print(f"[WebSocketManager] Error sending transcript to client: {e}")

    async def end_call(self, call_id):
        call_data = self.active_calls.pop(call_id, None)
        if call_data:
            try:
                await call_data["inbound_service"].close()
                await call_data["outbound_service"].close()
                if not call_data["inbound_task"].done():
                    call_data["inbound_task"].cancel()
                    try:
                        await call_data["inbound_task"]
                    except asyncio.CancelledError:
                        pass
                if not call_data["outbound_task"].done():
                    call_data["outbound_task"].cancel()
                    try:
                        await call_data["outbound_task"]
                    except asyncio.CancelledError:
                        pass

                # Notify all clients that the call has ended and update call status
                status_update = {"callStatus": "Call Ended", "callEnded": True}
                for client_ws in call_data["clients"]:
                    try:
                        await client_ws.send_json(status_update)
                    except Exception as e:
                        print(f"[WebSocketManager] Error sending call status update: {e}")
                print(f"[WebSocketManager] Call {call_id} ended and cleaned up.")

                # Only log calls that reached a connected state.
                if call_data.get("state") not in ["in-progress", "answered", "completed"]:
                    print(f"[WebSocketManager] Call {call_id} did not reach connected state; skipping logging.")
                    return

                end_time = datetime.datetime.utcnow()
                total_seconds = int((end_time - call_data["start_time"]).total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

                transcript_text = "\n".join(call_data.get("transcript", []))
                metadata = {
                    "verified_caller": call_data.get("verified_caller"),
                    "verified_receiver": call_data.get("verified_receiver")
                }
                summary = generate_summary(transcript_text, metadata)

                call_record = {
                    "datetime": call_data["start_time"].isoformat(),
                    "call_status": "Ended",
                    "verified_caller": call_data.get("verified_caller"),
                    "verified_receiver": call_data.get("verified_receiver"),
                    "call_sid": call_id,
                    "duration": duration_str,
                    "transcript_enable": call_data["transcribe_enabled"],
                    "transcript": transcript_text,
                    "summary": summary
                }
                self.database_service.insert_call_record(call_record)

                # Also send the summary to all clients.
                for client_ws in call_data["clients"]:
                    try:
                        await client_ws.send_json({"summary": summary})
                    except Exception as e:
                        print(f"[WebSocketManager] Error sending summary to client: {e}")
            except Exception as e:
                print(f"[WebSocketManager] Error during call cleanup: {e}")

    async def handle_client(self, websocket):
        try:
            print("[WebSocketManager] Client WebSocket connection established")
            async for msg in websocket.iter_json():
                if "subscribe" in msg:
                    call_id = msg["subscribe"]
                    call_data = self.active_calls.get(call_id)
                    if call_data:
                        call_data["clients"].add(websocket)
                        # Send initial state and any existing transcripts
                        state_message = {
                            "transcript": f"Connected to call {call_id}",
                            "callStatus": call_data.get("state"),
                            "transcription_enabled": call_data.get("transcribe_enabled", True)
                        }
                        await websocket.send_json(state_message)
                        
                        # Send existing transcripts if any
                        if call_data.get("transcript"):
                            for transcript_line in call_data["transcript"]:
                                track = "inbound" if transcript_line.startswith("Agent:") else "outbound"
                                text = transcript_line.split(": ", 1)[1] if ": " in transcript_line else transcript_line
                                await websocket.send_json({
                                    "transcript": text,
                                    "track": track
                                })
                        print(f"[WebSocketManager] Client subscribed to call {call_id}")
                    else:
                        print(f"[WebSocketManager] Call {call_id} not found for subscription")
        except Exception as e:
            print(f"[WebSocketManager] handle_client error: {e}")
            try:
                await websocket.send_json({"error": str(e)})
            except:
                pass
