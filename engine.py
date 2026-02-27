import os
import glob
from PIL import Image, ImageDraw, ImageFont
import pytesseract
import numpy as np
import pyttsx3
import textwrap 
import torch
import spacy
import google.generativeai as genai
from diffusers import StableDiffusionPipeline
from dotenv import load_dotenv
from moviepy.editor import AudioFileClip, ImageClip, concatenate_videoclips, CompositeVideoClip

load_dotenv()
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_KEY:
    raise Exception("GEMINI_API_KEY missing")
genai.configure(api_key=GEMINI_KEY)

voice_model = genai.GenerativeModel("gemini-flash-latest")

device = "cuda" if torch.cuda.is_available() else "cpu"
print("[INFO] Device:", device)

if os.name == "nt":
    tesseract_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(tesseract_path):
        pytesseract.pytesseract.tesseract_cmd = tesseract_path

nlp = spacy.load("en_core_web_sm")

BASE = os.path.dirname(os.path.abspath(__file__))
model_path = os.path.join(BASE, "models", "stable-diffusion", "realisticVisionV60B1_v51HyperVAE.safetensors")

pipe = StableDiffusionPipeline.from_single_file(
    model_path,
    torch_dtype=torch.float16 if device == "cuda" else torch.float32
).to(device)
pipe.enable_attention_slicing()

POINTS = []

def run_ocr(path):
    return pytesseract.image_to_string(Image.open(path))

def run_nlp(text):
    global POINTS
    doc = nlp(text)
    POINTS = [s.text.strip() for s in doc.sents][:10]

    os.makedirs("static/output", exist_ok=True)
    with open("static/output/points.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(POINTS))

def process_file(path):
    run_nlp(run_ocr(path))

def summarize_points():
    joined = ". ".join(POINTS)
    prompt = f"""
You are a friendly teacher.
Explain this topic naturally in spoken English.
Do NOT repeat sentences.
Teach clearly like storytelling in one minute.

{joined}
"""
    return voice_model.generate_content(prompt).text

def generate_voice(output_path="static/output/voice.wav"):

    summary = summarize_points()

    # Save caption
    with open("static/output/caption.txt","w",encoding="utf-8") as f:
        f.write(summary)

    engine = pyttsx3.init()
    engine.setProperty("rate", 175)
    engine.save_to_file(summary, output_path)
    engine.runAndWait()

    print("[INFO] Voice + caption generated")

# ---------------- VISUALS ----------------

def generate_visual_prompts(max_images=5):
    prompts = []
    topics_map = {
        "pollution": "polluted rivers, factories, smoke",
        "ecosystem": "forests, animals, plants, rivers",
        "climate": "storms, drought, nature effects",
        "industry": "factories, smokestacks, industrial sites"
    }

    for point in POINTS[:max_images]:
        lower = point.lower()
        prompt = None
        for k, v in topics_map.items():
            if k in lower:
                prompt = v
                break
        if not prompt:
            prompt = point
        prompts.append(prompt)
    return prompts

def generate_images():
    os.makedirs("static/output/scenes", exist_ok=True)
    for f in os.listdir("static/output/scenes"):
        os.remove(os.path.join("static/output/scenes", f))

    prompts = generate_visual_prompts()
    negative = "realistic photo, portrait, face, people, human face, text, logo, watermark, blurry, low quality"

    for i, scene in enumerate(prompts):
        prompt = f"""
colorful storybook illustration of {scene},
soft cartoon style characters,
educational animation look,
friendly environment,
rounded shapes,
clean outlines,
simple expressive characters,
bright colors,
high detail,
children story illustration,
no text,
masterpiece
"""
        image = pipe(
            prompt=prompt,
            negative_prompt=negative,
            guidance_scale=7,
            num_inference_steps=35,
        ).images[0]

        image.save(f"static/output/scenes/{i:03d}.png")
        print(f"[INFO] Image saved: {i:03d}.png")

# ---------------- VIDEO ----------------

def build_video(output_path):
    image_files = sorted(glob.glob("static/output/scenes/*.png"))
    audio = AudioFileClip("static/output/voice.wav")
    audio = audio.set_start(0)
    duration = audio.duration
    per = duration / len(image_files)
    clips = [ImageClip(img).set_duration(per) for img in image_files]
    video = concatenate_videoclips(clips).set_audio(audio)

    with open("static/output/caption.txt","r",encoding="utf-8") as f:
        text = f.read()
    import textwrap
    chunks = textwrap.wrap(text, 120)
    W, H = video.size
    segment = duration / len(chunks)
    caption_clips = []
    for i, chunk in enumerate(chunks):
        wrapped = "\n".join(textwrap.wrap(chunk, 45))
        box = Image.new("RGBA", (W,160), (0,0,0,180))
        draw = ImageDraw.Draw(box)
        font = ImageFont.load_default()
        draw.multiline_text((20,20), wrapped, font=font, fill="white")
        clip = ImageClip(np.array(box)).set_duration(segment).set_start(i*segment).set_position(("center","bottom"))
        caption_clips.append(clip)

    final = CompositeVideoClip([video.set_position("center")] + caption_clips)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    final.write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac")
    print("[INFO] Final video saved:", output_path)

def run_animation(output_path):
    generate_images()
    generate_voice()
    build_video(output_path)

# ---------------- COMIC ----------------

def run_comic():
    os.makedirs("static/comic", exist_ok=True)
    with open("static/output/points.txt", "r", encoding="utf-8") as f:
        points = [l.strip() for l in f if l.strip()]

    joined_points = ". ".join(points)

    prompt = f"""
You are a FRIENDLY EDUCATIONAL STORYTELLER.
Create TWELVE comic panels explaining:
{joined_points}
"""
    story_text = voice_model.generate_content(prompt).text.strip()
    panels = [p for p in story_text.split("\n") if p][:12]

    comic_paths = []
    negative_prompt = "anime, cartoon, illustration, painting, text, logo, watermark, blurry, human face, person, people, portrait, face"

    for idx, panel_text in enumerate(panels):
        sd_prompt = f"""
ultra realistic colorful comic illustration of {panel_text},
storybook style,
soft lighting,
clean outlines,
high detail,
no text,no human body or face
"""
        img = pipe(
            prompt=sd_prompt,
            negative_prompt=negative_prompt,
            guidance_scale=7,
            num_inference_steps=30
        ).images[0]

        draw = ImageDraw.Draw(img)
        W, H = img.size
        try:
            font = ImageFont.truetype("arial.ttf", 17)
        except:
            font = ImageFont.load_default()
        wrapped = "\n".join(textwrap.wrap(panel_text, 42)[:5])
        box_height = 40 + len(wrapped.split("\n")) * font.getbbox("Ay")[3] + 20
        box = Image.new("RGBA", (W, box_height), (255,255,255,170))
        img.paste(box, (0, H-box_height-40), box)
        draw.multiline_text((20, H-box_height-40+20), wrapped, fill="black", font=font)
        out = f"static/comic/panel_{idx}.png"
        img.save(out)
        comic_paths.append(out)

    imgs = [Image.open(p) for p in comic_paths]
    w, h = imgs[0].size
    cols, rows = 3, 4
    canvas = Image.new("RGB", (w*cols, h*rows), "white")
    for i, im in enumerate(imgs):
        x, y = (i%cols)*w, (i//cols)*h
        canvas.paste(im, (x, y))

    existing = glob.glob("static/comic/comic_*.png")
    idx = len(existing)+1
    final_path = f"static/comic/comic_{idx}.png"
    canvas.save(final_path)
    print("[INFO] Comic saved:", final_path)
    return final_path

# ---------------- FLOWCHART ----------------

def run_flowchart():

    import os
    import textwrap
    from PIL import Image, ImageDraw, ImageFont

    os.makedirs("static/flowchart", exist_ok=True)

    # Read points from SpaCy output
    with open("static/output/points.txt", "r", encoding="utf-8") as f:
        points = [l.strip() for l in f if l.strip()]

    width = 900
    img_height = 300 * len(points)

    img = Image.new("RGB", (width, img_height), "white")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except:
        font = ImageFont.load_default()

    x_center = width // 2
    y = 80

    centers = []

    # ---------- DRAW NODES ----------
    for p in points:

        wrapped = textwrap.wrap(p, 25)

        line_widths = []
        line_heights = []

        for line in wrapped:
            bbox = font.getbbox(line)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            line_widths.append(w)
            line_heights.append(h)

        text_w = max(line_widths)
        text_h = sum(line_heights) + (len(wrapped)-1)*5

        radius = max(text_w, text_h)//2 + 30

        # Circle
        draw.ellipse(
            (x_center-radius, y-radius, x_center+radius, y+radius),
            outline="black",
            width=2
        )

        # Text (manual centering)
        current_y = y - text_h//2

        for line in wrapped:
            bbox = font.getbbox(line)
            lw = bbox[2] - bbox[0]
            lh = bbox[3] - bbox[1]

            draw.text(
                (x_center-lw//2, current_y),
                line,
                fill="black",
                font=font
            )

            current_y += lh + 5

        centers.append((x_center, y, radius))
        y += radius*2 + 60

    # ---------- DRAW ARROWS ----------
    for i in range(len(centers)-1):

        x1, y1, r1 = centers[i]
        x2, y2, r2 = centers[i+1]

        draw.line((x1, y1+r1, x2, y2-r2), fill="black", width=2)

        draw.polygon([
            (x2-6, y2-r2-10),
            (x2+6, y2-r2-10),
            (x2, y2-r2)
        ], fill="black")

    # ---------- SAVE ----------
    existing = os.listdir("static/flowchart")
    idx = len(existing) + 1
    path = f"static/flowchart/flowchart_{idx}.png"

    img.save(path)

    print("[INFO] Flowchart saved:", path)

    return path
# ---------------- QUIZ ----------------


# Load API key from environment (kept secret)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is not set!")

# Configure the SDK globally — no need to pass api_key anywhere else
genai.configure(api_key=GEMINI_API_KEY)

def generate_quiz():
    import json
    try:
        with open("static/output/points.txt", "r", encoding="utf-8") as f:
            points = [l.strip() for l in f if l.strip()]

        if not points:
            print("No study material found!")
            return []

        joined_points = ". ".join(points)

        prompt = f"""
Generate 4 multiple choice questions from the following study material.

Strictly return ONLY valid JSON in this format:

[
  {{
    "question": "Question text",
    "options": ["Option1", "Option2", "Option3", "Option4"],
    "answer": "Correct Option"
  }}
]

Study Material:
{joined_points}
"""

        response = voice_model.generate_content(prompt)

        text = response.text.strip()

        print("RAW GEMINI RESPONSE:\n", text)

        # Extract JSON safely
        start = text.find("[")
        end = text.rfind("]") + 1

        if start != -1 and end != -1:
            text = text[start:end]

        quiz_data = json.loads(text)

        print("Generated Quiz:", quiz_data)
        return quiz_data

    except Exception as e:
        print("Quiz generation error:", e)
        return []