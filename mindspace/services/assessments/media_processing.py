"""
Media processing helpers for MindSpace assessments.
Contains FFmpeg-based video compression and audio conversion.
"""

import os
import uuid
import tempfile
import subprocess
import shutil

def combine_audio_files_to_wav(input_paths, silence_seconds=0.7):
    """
    Combine multiple audio files into one clean WAV file.

    Output:
      - mono
      - 16000 Hz
      - PCM 16-bit WAV

    Adds short silence between each phonation sound.
    """

    if not input_paths:
        raise RuntimeError("No audio files provided for combining.")

    for path in input_paths:
        if not path or not os.path.exists(path):
            raise RuntimeError(f"Audio file not found: {path}")

    work_dir = tempfile.mkdtemp(prefix="mindspace_voice_combine_")
    normalized_paths = []

    try:
        # Convert every uploaded file to normalized WAV first.
        for index, input_path in enumerate(input_paths, start=1):
            normalized_path = os.path.join(work_dir, f"sound_{index}.wav")

            command = [
                "ffmpeg",
                "-y",
                "-i", input_path,
                "-ac", "1",
                "-ar", "16000",
                "-sample_fmt", "s16",
                normalized_path,
            ]

            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=180,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"Audio normalization failed for {input_path}. "
                    f"FFmpeg error: {result.stderr[-1200:]}"
                )

            normalized_paths.append(normalized_path)

        # Create silence file.
        silence_path = os.path.join(work_dir, "silence.wav")
        silence_cmd = [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", f"anullsrc=r=16000:cl=mono",
            "-t", str(silence_seconds),
            "-sample_fmt", "s16",
            silence_path,
        ]

        result = subprocess.run(
            silence_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Silence generation failed: {result.stderr[-1200:]}")

        # Build concat list with silence between sounds.
        concat_list_path = os.path.join(work_dir, "concat.txt")

        with open(concat_list_path, "w", encoding="utf-8") as file:
            for index, wav_path in enumerate(normalized_paths):
                file.write(f"file '{wav_path}'\n")
                if index < len(normalized_paths) - 1:
                    file.write(f"file '{silence_path}'\n")

        output_path = os.path.join(work_dir, f"combined_phonation_{uuid.uuid4()}.wav")

        concat_cmd = [
            "ffmpeg",
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_path,
            "-c", "copy",
            output_path,
        ]

        result = subprocess.run(
            concat_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Audio combine failed: {result.stderr[-1200:]}")

        if not os.path.exists(output_path) or os.path.getsize(output_path) <= 44:
            raise RuntimeError("Combined audio output is empty or invalid.")

        return output_path

    except FileNotFoundError:
        raise RuntimeError("FFmpeg is not installed. Install it using: sudo apt install ffmpeg")
    

    
def compress_video_for_face_api(input_path):
    if not input_path:
        raise RuntimeError("Input video path missing for compression.")

    input_path = str(input_path)

    if not os.path.exists(input_path):
        raise RuntimeError(f"Input video file not found: {input_path}")

    output_dir = tempfile.mkdtemp(prefix="mindspace_face_compress_")
    output_path = os.path.join(output_dir, f"{uuid.uuid4()}.mp4")

    command = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", "scale='min(480,iw)':-2,fps=12",
        "-an",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "28",
        "-movflags", "+faststart",
        output_path,
    ]

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=900,
        )
    except FileNotFoundError:
        raise RuntimeError("FFmpeg is not installed. Install it using: sudo apt install ffmpeg")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Video compression timed out.")

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg compression failed: {result.stderr[-1200:]}")

    return output_path

def cleanup_temp_file(file_path):
    """
    Safely clean temporary files created by this module.

    For combined audio, FFmpeg creates several temporary WAV files inside the
    same temp directory. Removing only output_path leaves temp files behind.
    If the parent directory is one of our known temp dirs, remove the whole dir.
    """
    if not file_path:
        return

    try:
        if os.path.exists(file_path):
            parent_dir = os.path.dirname(file_path)
            parent_name = os.path.basename(parent_dir)

            os.remove(file_path)

            # Safe recursive cleanup only for directories created by this module.
            if parent_name.startswith(("mindspace_voice_combine_", "mindspace_face_compress_")):
                shutil.rmtree(parent_dir, ignore_errors=True)
            elif parent_dir and os.path.isdir(parent_dir):
                try:
                    os.rmdir(parent_dir)
                except Exception:
                    pass
    except Exception:
        pass

def convert_audio_to_wav(input_file):
    """
    Convert browser-recorded audio/webm or audio/ogg to clean WAV before
    sending to the Voice Feature Extraction API.

    Output:
      - mono
      - 16000 Hz
      - PCM 16-bit WAV

    This fixes API errors like:
      Format not recognised
      Error opening /tmp/tmpxxxx.wav
    """
    input_suffix = ".webm"

    original_name = getattr(input_file, "name", "") or ""
    if "." in original_name:
        input_suffix = "." + original_name.split(".")[-1].lower()

    temp_input = tempfile.NamedTemporaryFile(delete=False, suffix=input_suffix)
    temp_output = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")

    temp_input_path = temp_input.name
    temp_output_path = temp_output.name

    try:
        input_file.seek(0)
        temp_input.write(input_file.read())
        temp_input.flush()
        temp_input.close()
        temp_output.close()

        command = [
            "ffmpeg",
            "-y",
            "-i", temp_input_path,
            "-ac", "1",
            "-ar", "16000",
            "-sample_fmt", "s16",
            temp_output_path,
        ]

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=180,
        )

        if result.returncode != 0:
            raise RuntimeError(
                "Audio WAV conversion failed. "
                f"FFmpeg error: {result.stderr[-1200:]}"
            )

        if not os.path.exists(temp_output_path) or os.path.getsize(temp_output_path) <= 44:
            raise RuntimeError("Audio WAV conversion produced an empty/invalid WAV file.")

        return temp_output_path

    except FileNotFoundError:
        raise RuntimeError("FFmpeg is not installed. Install it using: sudo apt install ffmpeg")

    finally:
        try:
            if os.path.exists(temp_input_path):
                os.remove(temp_input_path)
        except Exception:
            pass