import os
import torch
from diffusers import StableDiffusionPipeline

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

model_path = os.path.join(BASE, "models", "stable-diffusion", "realisticVisionV60B1_v51HyperVAE.safetensors")

device = "cuda" if torch.cuda.is_available() else "cpu"

pipe = StableDiffusionPipeline.from_single_file(
    model_path,
    torch_dtype=torch.float16 if device == "cuda" else torch.float32
).to(device)

pipe.enable_attention_slicing()

points_file = os.path.join(BASE, "static/output/points.txt")

with open("static/output/points.txt","r",encoding="utf-8") as f:
    POINTS = [l.strip() for l in f if l.strip()]

out = os.path.join(BASE,"static/output/scenes")
os.makedirs(out,exist_ok=True)

negative = "anime, cartoon, text, watermark, logo, ugly, blurry"

for idx,p in enumerate(POINTS[:5]):

    prompt = f"""
ultra realistic cinematic photograph of {p},
natural light, depth of field,
DSLR, sharp focus, 4k
"""

    img = pipe(prompt=prompt,negative_prompt=negative,num_inference_steps=30).images[0]
    img.save(os.path.join(out,f"{idx:03d}.png"))
