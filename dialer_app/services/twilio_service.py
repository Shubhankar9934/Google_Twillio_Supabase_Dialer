# dialer_app/services/twilio_service.py
import os
from twilio.rest import Client
from dialer_app.config import Config

def initiate_outbound_call(caller_number, receiver_number):
    account_sid = Config.TWILIO_ACCOUNT_SID
    auth_token = Config.TWILIO_AUTH_TOKEN
    twilio_number = Config.TWILIO_PHONE_NUMBER

    ngrok_url = os.environ.get("NGROK_URL")
    if not ngrok_url:
        raise RuntimeError("Ngrok URL not found. Ensure ngrok is running and NGROK_ENABLED is True.")

    domain = ngrok_url.replace('https://', '').replace('http://', '').strip('/')
    stream_url = f"wss://{domain}/twilio"
    print(f"[Twilio Service] Using Media Stream URL: {stream_url}")

    # Automatically configure the callback URL using current NGROK_URL
    callback_url = f"{ngrok_url}/call_status"

    # Include AMD settings for detecting answering machine and using answerOnBridge.
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Start>
        <Stream url="{stream_url}" track="both_tracks" />
    </Start>
    <Dial machineDetection="DetectMessageEnd" answerOnBridge="true">{receiver_number}</Dial>
</Response>"""

    client = Client(account_sid, auth_token)
    call = client.calls.create(
        twiml=twiml,
        to=caller_number,
        from_=twilio_number,
        status_callback=callback_url,
        status_callback_event=["initiated", "ringing", "answered", "completed"],
        status_callback_method="POST"
    )
    print("Outbound call initiated. SID:", call.sid)
    return call.sid
