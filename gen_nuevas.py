#!/usr/bin/env python3
"""Genera imágenes de producto para los artículos nuevos de la wishlist."""
import os, json, urllib.request, time

KEY = open("/opt/data/.fal_key").read().strip()
OUT = "/opt/data/baby-isaac/static/img"
os.makedirs(OUT, exist_ok=True)
ENDPOINT = "https://fal.run/fal-ai/flux-pro/v1.1"

productos = {
  "baby_swing": "Professional product photography of a baby swing rocker seat (baby bouncer chair) standalone, on a pure white background, soft studio lighting, ecommerce product shot, high detail",
  "cesta_ropa": "Professional product photography of a baby nursery laundry hamper basket (woven wicker basket), on a pure white background, soft studio lighting, ecommerce product shot",
  "camara_monitor": "Professional product photography of a baby video monitor camera unit (baby cam), on a pure white background, soft studio lighting, ecommerce product shot",
  "monitoreo_bebe": "Professional product photography of a baby breathing and sleep monitor device (wearable sock vital signs monitor), on a pure white background, soft studio lighting, ecommerce product shot",
  "almohada_lactancia": "Professional product photography of a nursing pillow breastfeeding pillow in soft neutral fabric, on a pure white background, soft studio lighting, ecommerce product shot",
  "organizador_gavetas": "Professional product photography of a baby dresser drawer organizer with fabric storage dividers and bins, on a pure white background, soft studio lighting, ecommerce product shot",
  "esterilizador": "Professional product photography of an electric baby bottle steam sterilizer machine, on a pure white background, soft studio lighting, ecommerce product shot",
  "calentador_leche": "Professional product photography of a baby bottle warmer machine (milk warmer), on a pure white background, soft studio lighting, ecommerce product shot",
  "teteros": "Professional product photography of a set of baby bottles with a bottle cleaning brush, on a pure white background, soft studio lighting, ecommerce product shot",
}


def gen(prompt, outpath):
    body = json.dumps({"prompt": prompt, "image_size": "square_hd", "num_images": 1}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, headers={
        "Content-Type": "application/json", "Authorization": f"Key {KEY}"})
    for attempt in range(3):
        try:
            resp = json.load(urllib.request.urlopen(req, timeout=180))
            url = resp["images"][0]["url"]
            urllib.request.urlretrieve(url, outpath)
            print("OK:", os.path.basename(outpath))
            return True
        except Exception as e:
            print("retry", os.path.basename(outpath), "->", e)
            time.sleep(4)
    return False


for name, prompt in productos.items():
    gen(prompt, os.path.join(OUT, f"{name}.jpg"))

print("DONE")
