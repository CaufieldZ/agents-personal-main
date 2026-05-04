#!/usr/bin/env python3
"""
Voice input daemon: push-to-talk → Whisper ASR → clipboard paste.

Default hotkey: Right Cmd. Hold to record, release to paste.
First run downloads model from HuggingFace — make sure proxy is set if needed.

macOS accessibility permission required:
  System Settings → Privacy & Security → Accessibility → grant to Terminal
"""

import argparse
import os
import re
import sys
import tempfile
import threading

import numpy as np
import sounddevice as sd
import soundfile as sf
import pyperclip
import Quartz
import mlx_whisper

CAPTURE_RATE = 48000
ASR_RATE = 16000
CHANNELS = 1
MODEL_ID = "mlx-community/whisper-large-v3-turbo"

HOTKEY_MAP = {
    "cmd_r": (54, Quartz.kCGEventFlagMaskCommand),
    "alt_l": (58, Quartz.kCGEventFlagMaskAlternate),
    "cmd_l": (55, Quartz.kCGEventFlagMaskCommand),
}


def _find_best_mic():
    devs = sd.query_devices()
    default_in = sd.default.device[0]
    for i, dev in enumerate(devs):
        if dev["max_input_channels"] > 0 and "MacBook" not in dev["name"]:
            return i
    return default_in


class VoiceInput:
    def __init__(self, hotkey_name="cmd_r", language="zh", device=None):
        self.hotkey_keycode, self.hotkey_flag = HOTKEY_MAP[hotkey_name]
        self.language = language
        self.device = device
        self._recording = False
        self._frames = []
        self._stream = None
        self._lock = threading.Lock()
        self._infer_lock = threading.Lock()

    def load_model(self):
        print(f"Loading {MODEL_ID} ...", end=" ", flush=True)
        mlx_whisper.transcribe(
            np.zeros(ASR_RATE, dtype=np.float32),
            path_or_hf_repo=MODEL_ID, language=self.language,
        )
        print("done")

    def _audio_callback(self, indata, frames, time, status):
        if self._recording:
            self._frames.append(indata.copy())

    def _start_rec(self):
        with self._lock:
            if self._recording:
                return
            self._recording = True
            self._frames = []
            self._stream = sd.InputStream(
                samplerate=CAPTURE_RATE, channels=CHANNELS,
                dtype="float32", callback=self._audio_callback,
                device=self.device,
            )
            self._stream.start()
        print("  ● REC", end="", flush=True)

    def _stop_rec(self):
        with self._lock:
            if not self._recording:
                return None
            self._recording = False
            self._stream.stop()
            self._stream.close()
            self._stream = None
            frames = list(self._frames)
            self._frames = []
        return frames

    TECH_PROMPT = (
        "以下是技术对话。常见术语：Claude Opus Sonnet Haiku, DeepSeek, GPT, "
        "GLM, Kimi, Gemini, Llama, Mistral, Python, JavaScript, TypeScript, "
        "React, Next.js, API, token, prompt, embedding, RAG, fine-tuning."
    )

    def _process(self, frames):
        import librosa
        audio = np.concatenate(frames).flatten()
        audio = librosa.resample(audio, orig_sr=CAPTURE_RATE, target_sr=ASR_RATE)
        dur = len(audio) / ASR_RATE
        if dur < 0.3:
            print("\r            \r", end="", flush=True)
            return

        print("\r  ... ", end="", flush=True)

        fd, tmp = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        sf.write(tmp, audio, ASR_RATE)

        try:
            with self._infer_lock:
                result = mlx_whisper.transcribe(
                    tmp, path_or_hf_repo=MODEL_ID, language=self.language,
                    initial_prompt=self.TECH_PROMPT,
                )
            text = result.get("text", "").strip()
            # Filter Whisper hallucination: repetitive output
            if text and len(text) > 8:
                # Single char or short pattern dominating the text
                short = text[:3]
                if short * (len(text) // len(short)) == text[:len(short) * (len(text) // len(short))]:
                    text = ""
                elif len(set(text)) <= 3 and len(text) > 6:
                    text = ""
            # Common Whisper misrecognitions
            text = text.replace("Cloud", "Claude")
            text = text.replace("cloud", "Claude")
            text = text.replace("Deep stick", "DeepSeek")
            text = text.replace("DeepSig", "DeepSeek")
            text = text.replace("Deep Stick", "DeepSeek")
            text = text.replace("OPEX", "Opus")
            text = text.replace("Opex", "Opus")
            text = text.replace("Office", "Opus")
        except Exception as e:
            print(f"\r  err: {e}")
            return
        finally:
            os.unlink(tmp)

        if not text:
            print("\r            \r", end="", flush=True)
            return

        pyperclip.copy(text)
        src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
        down = Quartz.CGEventCreateKeyboardEvent(src, 0x09, True)
        Quartz.CGEventSetFlags(down, Quartz.kCGEventFlagMaskCommand)
        up = Quartz.CGEventCreateKeyboardEvent(src, 0x09, False)
        Quartz.CGEventSetFlags(up, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
        print(f"\r  -> {text}")

    def _tap_callback(self, proxy, event_type, event, refcon):
        if event_type == Quartz.kCGEventFlagsChanged:
            keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
            if keycode != self.hotkey_keycode:
                return event
            flags = Quartz.CGEventGetFlags(event)
            pressed = bool(flags & self.hotkey_flag)
            if pressed and not self._recording:
                self._start_rec()
            elif not pressed and self._recording:
                frames = self._stop_rec()
                if frames:
                    threading.Thread(target=self._process, args=(frames,), daemon=True).start()
        return event

    def run(self):
        self.load_model()
        print(f"\nHold Right Cmd to talk, release to paste.")
        print("Ctrl+C to quit.\n")

        mask = Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged)
        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap, Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionDefault, mask, self._tap_callback, None,
        )
        if tap is None:
            print("ERROR: Cannot create event tap. Grant Accessibility permission and retry.")
            sys.exit(1)

        source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        Quartz.CFRunLoopAddSource(Quartz.CFRunLoopGetCurrent(), source, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(tap, True)
        try:
            Quartz.CFRunLoopRun()
        except KeyboardInterrupt:
            print("\nBye.")


def main():
    p = argparse.ArgumentParser(description="Voice input -> Whisper -> paste")
    p.add_argument("--key", default="cmd_r", choices=HOTKEY_MAP, help="Push-to-talk key (default: cmd_r)")
    p.add_argument("--lang", default="zh", choices=["zh", "en", "ja", "ko", "auto"], help="Language (default: zh)")
    p.add_argument("--device", type=int, default=None, help="Audio input device index (see --list-devices)")
    p.add_argument("--list-devices", action="store_true", help="List audio devices and exit")
    args = p.parse_args()

    if args.list_devices:
        print(sd.query_devices())
        return

    device = args.device if args.device is not None else _find_best_mic()
    print(f"Using mic: {sd.query_devices(device)['name']}")

    vi = VoiceInput(args.key, args.lang, device=device)
    vi.run()


if __name__ == "__main__":
    main()
