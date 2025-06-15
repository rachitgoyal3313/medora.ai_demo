import pyaudio
import websocket
import json
import threading
import time
import wave
import os
from urllib.parse import urlencode
from datetime import datetime
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
import base64

# --- Configuration ---
YOUR_API_KEY = os.environ.get("ASSEMBLY_AI_API_KEY", "6e61f9fdd89d46168a30ce40d5226400")  # Fallback to default if not set
print(YOUR_API_KEY)
CONNECTION_PARAMS = {
    "sample_rate": 16000,
    "format_turns": True,
}
API_ENDPOINT_BASE_URL = "wss://streaming.assemblyai.com/v3/ws"
API_ENDPOINT = f"{API_ENDPOINT_BASE_URL}?{urlencode(CONNECTION_PARAMS)}"

FRAMES_PER_BUFFER = 800
SAMPLE_RATE = CONNECTION_PARAMS["sample_rate"]
CHANNELS = 1
FORMAT = pyaudio.paInt16

# Ensure prescriptions directory exists
PRESCRIPTIONS_DIR = os.path.join(os.path.dirname(__file__), 'static', 'prescriptions')
os.makedirs(PRESCRIPTIONS_DIR, exist_ok=True)

class VoiceRecognitionService:
    def __init__(self, socketio_instance):
        self.audio = None
        self.stream = None
        self.ws_app = None
        self.audio_thread = None
        self.stop_event = threading.Event()
        self.recorded_frames = []
        self.recording_lock = threading.Lock()
        self.socketio = socketio_instance
        self.is_recording = False
        self.current_transcript = ""

    def save_wav_file(self):
        if not self.recorded_frames:
            print("No audio data recorded.")
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"recorded_audio_{timestamp}.wav"
        filepath = os.path.join(PRESCRIPTIONS_DIR, filename)

        try:
            with wave.open(filepath, 'wb') as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)

                with self.recording_lock:
                    wf.writeframes(b''.join(self.recorded_frames))

            print(f"Audio saved to: {filepath}")
            return filename
        except Exception as e:
            print(f"Error saving WAV file: {e}")
            return None

    def on_open(self, ws):
        print("✅ WebSocket connection opened.")
        self.socketio.emit('voice_status', {'status': 'connected'})

        def stream_audio():
            while not self.stop_event.is_set() and self.is_recording:
                try:
                    audio_data = self.stream.read(FRAMES_PER_BUFFER, exception_on_overflow=False)

                    with self.recording_lock:
                        self.recorded_frames.append(audio_data)

                    ws.send(audio_data, websocket.ABNF.OPCODE_BINARY)
                except Exception as e:
                    print(f"Error streaming audio: {e}")
                    break
            print("🔁 Audio streaming stopped.")

        self.audio_thread = threading.Thread(target=stream_audio)
        self.audio_thread.daemon = True
        self.audio_thread.start()

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            if data.get("type") == "Turn":
                transcript = data.get("transcript", "")
                formatted = data.get("turn_is_formatted", False)
                if formatted and transcript:
                    self.current_transcript = transcript
                    print("🗣", transcript)
                    # Send transcript to frontend
                    self.socketio.emit('transcription_update', {
                        'transcript': transcript,
                        'is_final': formatted
                    })
                elif transcript:
                    # Send partial transcript
                    self.socketio.emit('transcription_partial', {
                        'transcript': transcript
                    })
        except Exception as e:
            print(f"Error handling message: {e}")

    def on_error(self, ws, error):
        print(f"❌ WebSocket Error: {error}")
        self.socketio.emit('voice_error', {'error': str(error)})
        self.stop_recording()

    def on_close(self, ws, close_status_code, close_msg):
        print(f"🔌 WebSocket closed: {close_status_code}, {close_msg}")
        filename = self.save_wav_file()
        
        self.socketio.emit('voice_status', {
            'status': 'disconnected',
            'final_transcript': self.current_transcript,
            'audio_file': filename
        })
        
        self.cleanup()

    def start_recording(self):
        if self.is_recording:
            return False

        self.stop_event.clear()
        self.recorded_frames = []
        self.current_transcript = ""
        self.is_recording = True

        try:
            self.audio = pyaudio.PyAudio()
            self.stream = self.audio.open(
                input=True,
                frames_per_buffer=FRAMES_PER_BUFFER,
                channels=CHANNELS,
                format=FORMAT,
                rate=SAMPLE_RATE,
            )
        except Exception as e:
            print(f"❌ Mic not available: {e}")
            self.socketio.emit('voice_error', {'error': f'Microphone not available: {str(e)}'})
            if self.audio:
                self.audio.terminate()
            return False

        self.ws_app = websocket.WebSocketApp(
            API_ENDPOINT,
            header={"Authorization": YOUR_API_KEY},
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
        )

        ws_thread = threading.Thread(target=self.ws_app.run_forever)
        ws_thread.daemon = True
        ws_thread.start()

        self.socketio.emit('voice_status', {'status': 'recording'})
        return True

    def stop_recording(self):
        if not self.is_recording:
            return False

        self.is_recording = False
        self.stop_event.set()
        
        if self.ws_app and self.ws_app.sock and self.ws_app.sock.connected:
            try:
                self.ws_app.send(json.dumps({"type": "Terminate"}))
                time.sleep(1)
            except:
                pass
            self.ws_app.close()

        self.socketio.emit('voice_status', {'status': 'processing'})
        return self.current_transcript  # Return transcription for app.py

    def cleanup(self):
        self.stop_event.set()
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.audio:
            self.audio.terminate()
        if self.audio_thread and self.audio_thread.is_alive():
            self.audio_thread.join(timeout=1.0)

    def get_current_transcript(self):
        return self.current_transcript

# Global voice prescription instance
voice_prescription = None

def initialize_voice_service(socketio_instance):
    global voice_prescription
    voice_prescription = VoiceRecognitionService(socketio_instance)
    return voice_prescription

def get_voice_service():
    return voice_prescription

# Register Socket.IO event handlers
def register_socketio_handlers(socketio):
    @socketio.on('connect')
    def handle_connect():
        print('Client connected')
        socketio.emit('voice_status', {'status': 'connected'})

    @socketio.on('disconnect')
    def handle_disconnect():
        print('Client disconnected')
        voice_service = get_voice_service()
        if voice_service and voice_service.is_recording:
            voice_service.stop_recording()

    @socketio.on('start_recording')
    def handle_start_recording():
        print('Start recording request received')
        voice_service = get_voice_service()
        if voice_service:
            success = voice_service.start_recording()
            return {'success': success}
        return {'error': 'Voice service not initialized'}

    @socketio.on('stop_recording')
    def handle_stop_recording():
        print('Stop recording request received')
        voice_service = get_voice_service()
        if voice_service:
            transcript = voice_service.stop_recording()
            return {'success': True, 'transcript': transcript}
        return {'error': 'Voice service not initialized'}

# Standalone function for terminal usage (backward compatibility)
def run_terminal_version():
    """Original terminal-based voice recognition function"""
    audio = None
    stream = None
    ws_app = None
    audio_thread = None
    stop_event = threading.Event()
    recorded_frames = []
    recording_lock = threading.Lock()

    def save_wav_file():
        if not recorded_frames:
            print("No audio data recorded.")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"recorded_audio_{timestamp}.wav"
        filepath = os.path.join(PRESCRIPTIONS_DIR, filename)

        try:
            with wave.open(filepath, 'wb') as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)

                with recording_lock:
                    wf.writeframes(b''.join(recorded_frames))

            print(f"Audio saved to: {filepath}")
        except Exception as e:
            print(f"Error saving WAV file: {e}")

    def on_open(ws):
        print("✅ WebSocket connection opened.")

        def stream_audio():
            nonlocal stream
            while not stop_event.is_set():
                try:
                    audio_data = stream.read(FRAMES_PER_BUFFER, exception_on_overflow=False)

                    with recording_lock:
                        recorded_frames.append(audio_data)

                    ws.send(audio_data, websocket.ABNF.OPCODE_BINARY)
                except Exception as e:
                    print(f"Error streaming audio: {e}")
                    break
            print("🔁 Audio streaming stopped.")

        nonlocal audio_thread
        audio_thread = threading.Thread(target=stream_audio)
        audio_thread.daemon = True
        audio_thread.start()

    def on_message(ws, message):
        try:
            data = json.loads(message)
            if data.get("type") == "Turn":
                transcript = data.get("transcript", "")
                formatted = data.get("turn_is_formatted", False)
                if formatted:
                    print('\r' + ' ' * 80 + '\r', end='')  # Clear line
                    print("🗣", transcript)
        except Exception as e:
            print(f"Error handling message: {e}")

    def on_error(ws, error):
        print(f"❌ WebSocket Error: {error}")
        stop_event.set()

    def on_close(ws, close_status_code, close_msg):
        print(f"🔌 WebSocket closed: {close_status_code}, {close_msg}")
        save_wav_file()

        nonlocal stream, audio
        stop_event.set()
        if stream:
            stream.stop_stream()
            stream.close()
        if audio:
            audio.terminate()
        if audio_thread and audio_thread.is_alive():
            audio_thread.join(timeout=1.0)

    audio = pyaudio.PyAudio()
    try:
        stream = audio.open(
            input=True,
            frames_per_buffer=FRAMES_PER_BUFFER,
            channels=CHANNELS,
            format=FORMAT,
            rate=SAMPLE_RATE,
        )
    except Exception as e:
        print(f"❌ Mic not available: {e}")
        audio.terminate()
        return

    print("🎙 Speak into your microphone. Press Ctrl+C to stop.")

    ws_app = websocket.WebSocketApp(
        API_ENDPOINT,
        header={"Authorization": YOUR_API_KEY},
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )

    ws_thread = threading.Thread(target=ws_app.run_forever)
    ws_thread.daemon = True
    ws_thread.start()

    try:
        while ws_thread.is_alive():
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n🛑 Stopping...")
        stop_event.set()
        if ws_app and ws_app.sock and ws_app.sock.connected:
            try:
                ws_app.send(json.dumps({"type": "Terminate"}))
                time.sleep(2)
            except:
                pass
        ws_app.close()
        ws_thread.join()

if __name__ == "__main__":
    run_terminal_version()
