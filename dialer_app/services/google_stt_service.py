# dialer_app/services/google_stt_service.py
import asyncio
import queue
from google.cloud import speech
from google.cloud.speech import StreamingRecognizeRequest, StreamingRecognitionConfig, RecognitionConfig

class GoogleSTTService:
    def __init__(self, call_id, track, broadcast_callback, loop=None):
        """
        call_id: The Twilio call SID.
        track: "inbound" or "outbound"
        broadcast_callback: async function(call_id, transcript, track)
        loop: The main event loop to schedule coroutine calls.
        """
        self.call_id = call_id
        self.track = track
        self.broadcast_callback = broadcast_callback
        self.active = True
        self.audio_queue = queue.Queue()
        self.client = speech.SpeechClient()
        self.streaming_config = StreamingRecognitionConfig(
            config=RecognitionConfig(
                encoding=RecognitionConfig.AudioEncoding.MULAW,
                sample_rate_hertz=8000,
                language_code="en-US",
                enable_automatic_punctuation=True,
            ),
            interim_results=False,
        )
        self.loop = loop or asyncio.get_event_loop()

    def request_generator(self):
        silent_chunk = bytes([0xFF] * 320)
        while self.active:
            try:
                audio_chunk = self.audio_queue.get(timeout=0.5)
                yield StreamingRecognizeRequest(audio_content=audio_chunk)
            except queue.Empty:
                yield StreamingRecognizeRequest(audio_content=silent_chunk)

    def _streaming_recognize(self):
        try:
            responses = self.client.streaming_recognize(self.streaming_config, self.request_generator())
            for response in responses:
                for result in response.results:
                    if result.alternatives:
                        transcript = result.alternatives[0].transcript.strip()
                        if transcript:
                            print(f"[GoogleSTTService] Transcript found: {transcript}")
                            future = asyncio.run_coroutine_threadsafe(
                                self.broadcast_callback(self.call_id, transcript, self.track),
                                self.loop
                            )
                            try:
                                future.result()
                            except Exception as ex:
                                print(f"[GoogleSTTService] Error broadcasting transcript: {ex}")
        except Exception as e:
            print(f"[GoogleSTTService] Error during streaming recognition for call {self.call_id}, track={self.track}: {e}")

    async def connect(self):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._streaming_recognize)

    async def send_audio(self, audio_chunk):
        if self.active and audio_chunk:
            self.audio_queue.put(audio_chunk)

    async def close(self):
        self.active = False
