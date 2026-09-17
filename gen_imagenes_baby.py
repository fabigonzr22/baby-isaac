#!/usr/bin/env python3
"""Genera imágenes realistas de producto (bebé) para la wishlist de Isaac con Flux Pro."""
import os, json, urllib.request, time

KEY = open("/opt/data/.fal_key").read().strip()
OUT = "/opt/data/baby-isaac/static/img"
os.makedirs(OUT, exist_ok=True)
ENDPOINT = "https://fal.run/fal-ai/flux-pro/v1.1"

productos = {
  "bodys": "Professional product photography of a set of three white cotton baby bodysuits (onesies) neatly folded, on a pure white background, soft studio lighting, ecommerce product shot, high detail",
  "pijamas": "Professional product photography of baby footed pajamas (sleeper) in soft blue cotton, folded neatly, on a pure white background, soft studio lighting, ecommerce product shot",
  "medias": "Professional product photography of a bundle of baby cotton socks in pastel colors, on a pure white background, soft studio lighting, ecommerce product shot",
  "franelas": "Professional product photography of folded baby cotton short-sleeve t-shirts in neutral colors, on a pure white background, soft studio lighting, ecommerce product shot",
  "camisas": "Professional product photography of a cute baby button-up shirt, folded, on a pure white background, soft studio lighting, ecommerce product shot",
  "pantalones": "Professional product photography of folded baby cotton pants, on a pure white background, soft studio lighting, ecommerce product shot",
  "panales": "Professional product photography of a neat stack of newborn disposable diapers, on a pure white background, soft studio lighting, ecommerce product shot",
  "termometro": "Professional product photography of a digital baby thermometer, on a pure white background, soft studio lighting, ecommerce product shot",
  "aspirador_electrico": "Professional product photography of an electric nasal aspirator device for babies, on a pure white background, soft studio lighting, ecommerce product shot",
  "aspirador_manual": "Professional product photography of a manual rubber bulb nasal aspirator for babies, on a pure white background, soft studio lighting, ecommerce product shot",
  "nebulizador": "Professional product photography of a baby nebulizer machine with face mask, on a pure white background, soft studio lighting, ecommerce product shot",
  "teteros": "Professional product photography of a set of baby bottles with a bottle brush cleaner, on a pure white background, soft studio lighting, ecommerce product shot",
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
