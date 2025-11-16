# utils.py
import uuid
import tempfile
import os
from typing import List, Dict

# ----------------------------------------------------------------------
# 1. SYSTEM PROMPT – forces JSON + language
# ----------------------------------------------------------------------
SYSTEM_PROMPT_TEMPLATE = """
You are AgriAssist, an AI agronomist for Indian farmers.
Analyze the crop image and return **only** a valid JSON object.

Fields (use the language requested – Tamil script for "ta", Devanagari for "hi"):
{{
  "diagnosis": "நோய் பெயர்" or "रोग का नाम",
  "english_name": "English name",
  "confidence": 85,
  "symptoms_match": ["இலைகளில் பழுப்பு புள்ளிகள்"],
  "treatment_steps": ["1. 50 கிராம்..."],
  "estimated_cost_inr": 150,
  "precautions": "கையுறை அணியவும்",
  "escalate": false
}}

Language instruction: {lang_instruction}
"""

LANG_INSTRUCTION = {
    "ta": "Respond in **simple rural Tamil** using Tamil script.",
    "hi": "Respond in **simple rural Hindi** using Devanagari script.",
}


def get_structured_prompt(lang: str = "ta") -> List[Dict]:
    """Return the system-prompt list for OpenAI."""
    instruction = LANG_INSTRUCTION.get(lang, LANG_INSTRUCTION["ta"])
    prompt = SYSTEM_PROMPT_TEMPLATE.format(lang_instruction=instruction)
    return [{"role": "system", "content": prompt.strip()}]


# ----------------------------------------------------------------------
# 2. TEXT-TO-SPEECH → MP3 saved in ./public_audio (served by FastAPI)
# ----------------------------------------------------------------------
PUBLIC_AUDIO_DIR = "public_audio"
os.makedirs(PUBLIC_AUDIO_DIR, exist_ok=True)


def text_to_speech(text: str, lang: str = "ta", base_url: str = "") -> str | None:
    """
    Generate MP3 and return **public URL**.
    `base_url` example: "https://abcd1234.ngrok.io"
    """
    from gtts import gTTS

    try:
        tts = gTTS(text=text, lang=lang, slow=False)
        filename = f"{uuid.uuid4()}.mp3"
        filepath = os.path.join(PUBLIC_AUDIO_DIR, filename)
        tts.save(filepath)

        # Return full public URL
        return f"{base_url.rstrip('/')}/{filename}"
    except Exception as e:
        print(f"gTTS failed: {e}")
        return None