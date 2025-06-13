import pyaudio
import websocket
import json
import threading
import time
import wave
from urllib.parse import urlencode
from datetime import datetime
import os
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class VoicePrescription:
    def __init__(self, socketio=None):
        self.connection_params = {
            "sample_rate": 16000,
            "format_turns": True,
            "utterance_events": True,
        }
        self.api_endpoint = f"wss://streaming.assemblyai.com/v3/ws?{urlencode(self.connection_params)}"
        
        self.frames_per_buffer = 3200
        self.sample_rate = self.connection_params["sample_rate"]
        self.channels = 1
        self.format = pyaudio.paInt16
        
        self.audio = None
        self.stream = None
        self.ws_app = None
        self.ws_thread = None
        self.audio_thread = None
        self.stop_event = threading.Event()
        self.is_recording = False
        
        self.recorded_frames = []
        self.recording_lock = threading.Lock()
        
        self.transcription = ""
        self.final_transcription = ""
        self.transcription_updated = False
        self.api_key = os.getenv("ASSEMBLYAI_API_KEY", "6feb9c809ab14b369e7601462caf811f")
        self.socketio = socketio
        
        # Create audio directory if it doesn't exist
        self.audio_dir = "static/prescriptions"
        os.makedirs(self.audio_dir, exist_ok=True)

    def save_wav_file(self):
        """Save recorded audio frames to a WAV file"""
        if not self.recorded_frames:
            logger.warning("No audio frames to save")
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(self.audio_dir, f"prescription_{timestamp}.wav")

        try:
            with wave.open(filename, 'wb') as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(2)  # 16-bit audio
                wf.setframerate(self.sample_rate)
                
                with self.recording_lock:
                    audio_data = b''.join(self.recorded_frames)
                    wf.writeframes(audio_data)
            
            logger.info(f"Audio file saved: {filename}")
            return filename
        except Exception as e:
            logger.error(f"Error saving WAV file: {e}")
            return None

    def on_open(self, ws):
        """Called when WebSocket connection is opened"""
        logger.info("WebSocket connection opened")
        self.stop_event.clear()
        self.transcription = ""
        self.final_transcription = ""
        self.transcription_updated = False
        
        if self.socketio:
            self.socketio.emit('status', {'message': 'Recording started'}, namespace='/voice')

        def stream_audio():
            """Stream audio data to WebSocket"""
            logger.info("Starting audio streaming thread")
            while not self.stop_event.is_set() and self.is_recording:
                try:
                    if self.stream and self.stream.is_active():
                        audio_data = self.stream.read(self.frames_per_buffer, exception_on_overflow=False)
                        
                        # Store audio data for saving later
                        with self.recording_lock:
                            self.recorded_frames.append(audio_data)
                        
                        # Send to WebSocket for transcription
                        if ws.sock and ws.sock.connected:
                            ws.send(audio_data, websocket.ABNF.OPCODE_BINARY)
                        else:
                            logger.warning("WebSocket not connected, stopping audio stream")
                            break
                    else:
                        logger.warning("Audio stream is not active")
                        break
                        
                except Exception as e:
                    logger.error(f"Error streaming audio: {e}")
                    break
            
            logger.info("Audio streaming thread ended")

        self.audio_thread = threading.Thread(target=stream_audio)
        self.audio_thread.daemon = True
        self.audio_thread.start()

    def on_message(self, ws, message):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(message)
            message_type = data.get("type")
            logger.debug(f"Received message type: {message_type}")

            if message_type == "PartialTranscript":
                partial_text = data.get("text", "")
                if partial_text:
                    self.transcription = self.final_transcription + partial_text
                    if self.socketio:
                        self.socketio.emit('transcription_update', {
                            'transcription': self.transcription,
                            'is_final': False
                        }, namespace='/voice')
            
            elif message_type == "FinalTranscript":
                final_text = data.get("text", "")
                if final_text:
                    self.final_transcription += final_text + " "
                    self.transcription = self.final_transcription
                    if self.socketio:
                        self.socketio.emit('transcription_update', {
                            'transcription': self.transcription,
                            'is_final': True
                        }, namespace='/voice')

        except Exception as e:
            logger.error(f"Error handling message: {e}")

    def on_error(self, ws, error):
        """Handle WebSocket errors"""
        logger.error(f"WebSocket Error: {error}")
        self.stop_event.set()
        if self.socketio:
            self.socketio.emit('error', {'message': f'Connection error: {str(error)}'}, namespace='/voice')

    def on_close(self, ws, close_status_code, close_msg):
        """Called when WebSocket connection is closed"""
        logger.info(f"WebSocket connection closed: {close_status_code} - {close_msg}")
        
        # Save the audio file
        saved_file = self.save_wav_file()
        
        # Clean up resources
        self.stop_event.set()
        self.is_recording = False
        
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception as e:
                logger.error(f"Error closing stream: {e}")
        
        if self.audio:
            try:
                self.audio.terminate()
            except Exception as e:
                logger.error(f"Error terminating audio: {e}")
        
        if self.audio_thread and self.audio_thread.is_alive():
            self.audio_thread.join(timeout=2.0)
        
        if self.socketio:
            self.socketio.emit('status', {
                'message': 'Recording stopped',
                'transcription': self.transcription,
                'audio_file': saved_file
            }, namespace='/voice')

    def start_recording(self):
        """Start voice recording and transcription"""
        try:
            logger.info("Starting voice recording")
            
            # Initialize PyAudio
            self.audio = pyaudio.PyAudio()
            
            # Open audio stream
            self.stream = self.audio.open(
                input=True,
                frames_per_buffer=self.frames_per_buffer,
                channels=self.channels,
                format=self.format,
                rate=self.sample_rate,
                input_device_index=self.audio.get_default_input_device_info()['index']
            )
            
            # Reset recording state
            with self.recording_lock:
                self.recorded_frames = []
            self.transcription = ""
            self.final_transcription = ""
            self.is_recording = True
            
            # Create WebSocket connection
            headers = {"Authorization": self.api_key}
            self.ws_app = websocket.WebSocketApp(
                self.api_endpoint,
                header=headers,
                on_open=self.on_open,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close,
            )

            # Start WebSocket in a separate thread
            self.ws_thread = threading.Thread(target=self.ws_app.run_forever)
            self.ws_thread.daemon = True
            self.ws_thread.start()
            
            logger.info("Voice recording started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error starting recording: {e}")
            self.cleanup()
            if self.socketio:
                self.socketio.emit('error', {'message': f'Failed to start recording: {str(e)}'}, namespace='/voice')
            return False

    def stop_recording(self):
        """Stop voice recording and transcription"""
        try:
            logger.info("Stopping voice recording")
            self.is_recording = False
            self.stop_event.set()
            
            # Send termination message to WebSocket
            if self.ws_app and hasattr(self.ws_app, 'sock') and self.ws_app.sock:
                try:
                    self.ws_app.send(json.dumps({"terminate_session": True}))
                    time.sleep(0.5)  # Wait for graceful termination
                except Exception as e:
                    logger.error(f"Error sending termination message: {e}")
            
            # Close WebSocket connection
            if self.ws_app:
                try:
                    self.ws_app.close()
                except Exception as e:
                    logger.error(f"Error closing WebSocket: {e}")
            
            # Wait for threads to complete
            if self.ws_thread and self.ws_thread.is_alive():
                self.ws_thread.join(timeout=3.0)
            
            if self.audio_thread and self.audio_thread.is_alive():
                self.audio_thread.join(timeout=2.0)
            
            # Save audio file
            saved_file = self.save_wav_file()
            
            # Clean up resources
            self.cleanup()
            
            logger.info(f"Voice recording stopped. Final transcription: {self.transcription}")
            return self.transcription
            
        except Exception as e:
            logger.error(f"Error stopping recording: {e}")
            self.cleanup()
            return self.transcription

    def cleanup(self):
        """Clean up audio resources"""
        try:
            if self.stream:
                if self.stream.is_active():
                    self.stream.stop_stream()
                self.stream.close()
                self.stream = None
            
            if self.audio:
                self.audio.terminate()
                self.audio = None
                
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def get_transcription(self):
        """Get the current transcription"""
        return self.transcription

    def clear_data(self):
        """Clear transcription data and recorded frames"""
        with self.recording_lock:
            self.recorded_frames = []
        self.transcription = ""
        self.final_transcription = ""
        self.transcription_updated = False

# Global instance (will be initialized with socketio)
voice_prescription = None

def initialize_voice_service(socketio):
    """Initialize the voice service with socketio"""
    global voice_prescription
    voice_prescription = VoicePrescription(socketio=socketio)
    logger.info("Voice service initialized")

def start_voice_recognition():
    """Start voice recognition"""
    if voice_prescription:
        return voice_prescription.start_recording()
    return False

def stop_voice_recognition():
    """Stop voice recognition"""
    if voice_prescription:
        return voice_prescription.stop_recording()
    return ""

def get_latest_transcription():
    """Get the latest transcription"""
    if voice_prescription:
        return voice_prescription.get_transcription()
    return ""

def clear_transcription_data():
    """Clear transcription data"""
    if voice_prescription:
        voice_prescription.clear_data()