import pyaudio
import websocket
import json
import threading
import time
import wave
from urllib.parse import urlencode
from datetime import datetime

# --- Configuration ---
YOUR_API_KEY = "09b245d3b30b4fe5becbad104aaa0204"  # Replace with your actual API key

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

    try:
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)

            with recording_lock:
                wf.writeframes(b''.join(recorded_frames))

        print(f"Audio saved to: {filename}")
    except Exception as e:
        print(f"Error saving WAV file: {e}")


def on_open(ws):
    print("✅ WebSocket connection opened.")

    def stream_audio():
        global stream
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

    global audio_thread
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

    global stream, audio
    stop_event.set()
    if stream:
        stream.stop_stream()
        stream.close()
    if audio:
        audio.terminate()
    if audio_thread and audio_thread.is_alive():
        audio_thread.join(timeout=1.0)


def run():
    global audio, stream, ws_app

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
    run()
import pyaudio
import websocket
import json
import threading
import time
import wave
from urllib.parse import urlencode
from datetime import datetime

# --- Configuration ---
YOUR_API_KEY = "YOUR_ASSEMBLY_AI_API_KEY"  # Replace with your actual API key

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

    try:
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)

            with recording_lock:
                wf.writeframes(b''.join(recorded_frames))

        print(f"Audio saved to: {filename}")
    except Exception as e:
        print(f"Error saving WAV file: {e}")


def on_open(ws):
    print("✅ WebSocket connection opened.")

    def stream_audio():
        global stream
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

    global audio_thread
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

    global stream, audio
    stop_event.set()
    if stream:
        stream.stop_stream()
        stream.close()
    if audio:
        audio.terminate()
    if audio_thread and audio_thread.is_alive():
        audio_thread.join(timeout=1.0)


def run():
    global audio, stream, ws_app

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
    run()