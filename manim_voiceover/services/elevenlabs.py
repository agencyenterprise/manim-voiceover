import os
import sys
from pathlib import Path
from typing import List, Optional, Union

from dotenv import find_dotenv, load_dotenv
from manim import logger

from manim_voiceover.helper import create_dotenv_file, remove_bookmarks
from manim_voiceover.services.base import SpeechService

try:
    from elevenlabs.client import ElevenLabs
except ImportError:
    logger.error(
        'Missing packages. Run `pip install "manim-voiceover[elevenlabs]"` '
        "to use ElevenLabs API."
    )

load_dotenv(find_dotenv(usecwd=True))


def create_dotenv_elevenlabs():
    logger.info(
        "Check out https://voiceover.manim.community/en/stable/services.html#elevenlabs"
        " to learn how to create an account and get your subscription key."
    )
    try:
        os.environ["ELEVEN_API_KEY"]
    except KeyError:
        if not create_dotenv_file(["ELEVEN_API_KEY"]):
            raise Exception(
                "The environment variables ELEVEN_API_KEY are not set. "
                "Please set them or create a .env file with the variables."
            )
        logger.info("The .env file has been created. Please run Manim again.")
        sys.exit()


create_dotenv_elevenlabs()


class ElevenLabsService(SpeechService):
    """Speech service for ElevenLabs API."""

    def __init__(
        self,
        voice_name: Optional[str] = None,
        voice_id: Optional[str] = None,
        model: str = "eleven_multilingual_v2",
        voice_settings: Optional[dict] = None,
        output_format: str = "mp3_44100_128",
        transcription_model: str = "base",
        **kwargs,
    ):
        """
        Args:
            voice_name (str, optional): The name of the voice to use.
                See the
                `API page <https://elevenlabs.io/docs/api-reference/text-to-speech>`
                for reference. Defaults to `None`.
                If none of `voice_name` or `voice_id` is be provided,
                it uses default available voice.
            voice_id (str, Optional): The id of the voice to use.
                See the
                `API page <https://elevenlabs.io/docs/api-reference/text-to-speech>`
                for reference. Defaults to `None`. If none of `voice_name`
                or `voice_id` must be provided, it uses default available voice.
            model (str, optional): The name of the model to use. See the `API
                page: <https://elevenlabs.io/docs/api-reference/text-to-speech>`
                for reference. Defaults to `eleven_multilingual_v2`
            voice_settings (dict, optional): The voice settings to use.
                See the
                `Docs: <https://elevenlabs.io/docs/speech-synthesis/voice-settings>`
                for reference.
                It is a dictionary, with keys: `stability`, `similarity_boost`,
                `style`, `use_speaker_boost`, etc.
            output_format (str, optional): The voice output
                format to use. Options are available depending on the Elevenlabs
                subscription. See the `API page:
                <https://elevenlabs.io/docs/api-reference/text-to-speech>`
                for reference. Defaults to `mp3_44100_128`.
        """
        # Initialize ElevenLabs client
        self.client = ElevenLabs()
        
        # Set default model (changed default to eleven_multilingual_v2 which is recommended)
        self.model = model
        
        # Store voice settings for use in text-to-speech conversion
        self.voice_settings = voice_settings
        
        # Set output format
        self.output_format = output_format
        
        # Determine voice to use
        if not voice_name and not voice_id:
            logger.warn(
                "None of `voice_name` or `voice_id` provided. "
                "Will be using default voice."
            )
            # Get the first available voice
            try:
                voices = self.client.voices.get_all()
                self.voice_id = voices[0].voice_id
                logger.info(f"Using default voice: {voices[0].name}")
            except Exception as e:
                logger.error(f"Failed to get voices: {e}")
                self.voice_id = None
        elif voice_id:
            self.voice_id = voice_id
        else:  # voice_name provided
            try:
                voices = self.client.voices.get_all()
                selected_voice = [v for v in voices if v.name == voice_name]
                if selected_voice:
                    self.voice_id = selected_voice[0].voice_id
                else:
                    logger.warn(
                        f"Voice name '{voice_name}' not found. Using default voice."
                    )
                    self.voice_id = voices[0].voice_id
            except Exception as e:
                logger.error(f"Failed to get voices: {e}")
                if voice_id:
                    self.voice_id = voice_id
                else:
                    self.voice_id = None

        SpeechService.__init__(self, transcription_model=transcription_model, **kwargs)

    def generate_from_text(
        self,
        text: str,
        cache_dir: Optional[str] = None,
        path: Optional[str] = None,
        **kwargs,
    ) -> dict:
        if cache_dir is None:
            cache_dir = self.cache_dir  # type: ignore

        input_text = remove_bookmarks(text)
        input_data = {
            "input_text": input_text,
            "service": "elevenlabs",
            "config": {
                "model": self.model,
                "voice_id": self.voice_id,
            },
        }

        # if not config.disable_caching:
        cached_result = self.get_cached_result(input_data, cache_dir)

        if cached_result is not None:
            return cached_result

        if path is None:
            audio_path = self.get_audio_basename(input_data) + ".mp3"
        else:
            audio_path = path

        try:
            # Use the new client-based API
            audio_generator = self.client.text_to_speech.convert(
                text=input_text,
                voice_id=self.voice_id,
                model_id=self.model,
                output_format=self.output_format,
                voice_settings=self.voice_settings,
            )
            
            # Convert generator to bytes
            audio_bytes = b"".join(chunk for chunk in audio_generator)
            
            # Save audio to file
            with open(str(Path(cache_dir) / audio_path), "wb") as f:
                f.write(audio_bytes)
                
        except Exception as e:
            logger.error(f"Error using ElevenLabs API: {e}")
            raise Exception("Failed to generate speech with ElevenLabs.")

        json_dict = {
            "input_text": text,
            "input_data": input_data,
            "original_audio": audio_path,
        }

        return json_dict
