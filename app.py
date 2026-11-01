"""AI Image Generation App - Streamlit
Providers:
  1. Hugging Face Inference API (FLUX / SDXL) - most reliable, free token
  2. Stable Horde  - free, no key, community GPUs (slow)
  3. Pollinations  - free anonymous endpoint (unreliable) or API key
"""
import base64
import io
import random
import time
from urllib.parse import quote

import requests
import streamlit as st
from PIL import Image

st.set_page_config(page_title="AI Image Generator", page_icon="🎨", layout="wide")

# ----------------------------- Config -----------------------------
STYLES = {
    "None": "",
    "Photorealistic": ", ultra realistic, 8k, DSLR photo, sharp focus, natural lighting",
    "Anime": ", anime style, vibrant colors, detailed, studio quality",
    "Digital Art": ", digital art, concept art, highly detailed, trending on artstation",
    "3D Render": ", 3D render, octane render, soft lighting, high detail",
    "Oil Painting": ", oil painting, textured brush strokes, classical art",
    "Cyberpunk": ", cyberpunk, neon lights, futuristic city, cinematic",
    "Pixel Art": ", pixel art, 16-bit, retro game style",
}
SIZES = {
    "Square": (1024, 1024),
    "Portrait": (768, 1024),
    "Landscape": (1024, 768),
    "Wide": (1280, 720),
}
HF_MODELS = {
    "FLUX.1 Schnell (fast)": "black-forest-labs/FLUX.1-schnell",
    "Stable Diffusion XL": "stabilityai/stable-diffusion-xl-base-1.0",
}
POLLI_MODELS = ["flux", "turbo"]
MODELS = {
    "Stable Diffusion - Auto (free)": ("horde", None),
    "Stable Diffusion 1.5 (free)": ("horde", "stable_diffusion"),
    "Deliberate (free)": ("horde", "Deliberate"),
    "Dreamshaper (free)": ("horde", "Dreamshaper"),
    "FLUX (Pollinations, free)": ("polli", "flux"),
}
EXAMPLES = [
    "A majestic lion wearing a golden crown, cinematic lighting",
    "Futuristic Lahore skyline at night with flying cars",
    "A cozy cabin in snowy mountains, warm light from windows",
    "An astronaut riding a horse on Mars",
]
UA = {"User-Agent": "streamlit-ai-image-generator/1.0"}


# ----------------------------- Helpers -----------------------------
def to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def secret(name: str):
    try:
        return st.secrets[name]
    except Exception:
        return None


def gen_huggingface(prompt, negative, width, height, seed, model, token):
    from huggingface_hub import InferenceClient

    client = InferenceClient(token=token, timeout=180)
    kwargs = {"width": width, "height": height, "seed": seed}
    if negative and "FLUX" not in model:  # FLUX negative prompt support nahi karta
        kwargs["negative_prompt"] = negative
    return client.text_to_image(prompt, model=model, **kwargs).convert("RGB")


def gen_pollinations(prompt, width, height, seed, model, api_key=None, status=None):
    params = {"width": width, "height": height, "seed": seed, "model": model, "nologo": "true"}
    if api_key:
        url = f"https://gen.pollinations.ai/image/{quote(prompt)}"
        headers = {**UA, "Authorization": f"Bearer {api_key}"}
    else:
        url = f"https://image.pollinations.ai/prompt/{quote(prompt)}"
        headers = UA

    last_err = None
    for attempt, wait in enumerate([0, 6, 15], start=1):  # 3 tries with backoff
        if wait:
            if status:
                status.write(f"Server busy, {wait}s baad dobara try (attempt {attempt}/3)…")
            time.sleep(wait)
        try:
            r = requests.get(url, params=params, headers=headers, timeout=120)
            if r.status_code in (429, 500, 502, 503, 504):
                last_err = f"HTTP {r.status_code}"
                continue
            r.raise_for_status()
            if "image" not in r.headers.get("content-type", ""):
                last_err = "non-image response"
                continue
            return Image.open(io.BytesIO(r.content)).convert("RGB")
        except requests.RequestException as e:
            last_err = str(e)
    raise RuntimeError(
        f"Pollinations abhi available nahi ({last_err}). "
        "Sidebar se koi Stable Diffusion (free) model select karein."
    )


def gen_horde(prompt, negative, width, height, seed, model=None, status=None, timeout=300):
    # Anonymous users ke liye chhoti sizes safe hain
    scale = min(1.0, 768 / max(width, height))
    w = max(384, int(width * scale) // 64 * 64)
    h = max(384, int(height * scale) // 64 * 64)
    w, h = min(w, 768), min(h, 768)
    body = {
        "prompt": prompt + (f" ### {negative}" if negative else ""),
        "params": {"width": w, "height": h, "steps": 25, "n": 1, "seed": str(seed),
                   "sampler_name": "k_euler_a", "cfg_scale": 7},
        "nsfw": False,
        "r2": True,
    }
    if model:
        body["models"] = [model]
    headers = {**UA, "apikey": secret("HORDE_API_KEY") or "0000000000", "Client-Agent": "streamlit-ai-image-generator:1.0"}
    base = "https://stablehorde.net/api/v2"
    r = requests.post(f"{base}/generate/async", json=body, headers=headers, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"Horde error {r.status_code}: {r.text[:200]}")
    job_id = r.json()["id"]

    start = time.time()
    while time.time() - start < timeout:
        time.sleep(4)
        c = requests.get(f"{base}/generate/check/{job_id}", headers=headers, timeout=30).json()
        if status:
            status.write(f"Queue position: {c.get('queue_position', '?')} · wait ~{c.get('wait_time', '?')}s")
        if c.get("done"):
            break
        if c.get("faulted"):
            raise RuntimeError("Stable Horde job faulted.")
    else:
        requests.delete(f"{base}/generate/status/{job_id}", headers=headers, timeout=15)
        raise RuntimeError("Stable Horde timeout - queue bohat lambi hai, baad mein try karein.")

    res = requests.get(f"{base}/generate/status/{job_id}", headers=headers, timeout=30).json()
    gens = res.get("generations") or []
    if not gens:
        raise RuntimeError("Horde ne koi image return nahi ki.")
    img_data = gens[0]["img"]
    if img_data.startswith("http"):
        raw = requests.get(img_data, headers=UA, timeout=60).content
    else:
        raw = base64.b64decode(img_data)
    return Image.open(io.BytesIO(raw)).convert("RGB")


HF_TOKEN = secret("HF_TOKEN")
POLLI_KEY = secret("POLLINATIONS_API_KEY")
if HF_TOKEN:  # HF models sirf tab dikhte hain jab secrets mein token ho
    MODELS["FLUX.1 Schnell (HF)"] = ("hf", "black-forest-labs/FLUX.1-schnell")
    MODELS["SDXL (HF)"] = ("hf", "stabilityai/stable-diffusion-xl-base-1.0")

# ----------------------------- State -----------------------------
st.session_state.setdefault("history", [])
st.session_state.setdefault("prompt", "")

# ----------------------------- Sidebar -----------------------------
with st.sidebar:
    st.header("⚙️ Settings")
    model_label = st.selectbox("Model", list(MODELS))
    backend, model = MODELS[model_label]

    style = st.selectbox("Style", list(STYLES))
    size_label = st.selectbox("Image size", [f"{k} ({v[0]}x{v[1]})" for k, v in SIZES.items()])
    width, height = SIZES[size_label.split(" ")[0]]
    n_images = st.slider("Number of images", 1, 4, 1)
    negative = st.text_input("Negative prompt", "blurry, low quality, distorted, watermark")
    seed_in = st.number_input("Seed (-1 = random)", min_value=-1, value=-1, step=1)

    if st.button("🗑️ Clear history", use_container_width=True):
        st.session_state.history = []
        st.rerun()

# ----------------------------- Main UI -----------------------------
st.title("🎨 AI Image Generator")
st.caption("Text likhein, AI image bana dega. Built with Python + Streamlit.")

st.write("**Quick examples:**")
for c, ex in zip(st.columns(len(EXAMPLES)), EXAMPLES):
    if c.button(ex[:28] + "…", help=ex, use_container_width=True):
        st.session_state.prompt = ex

prompt = st.text_area("Prompt", key="prompt", height=100,
                      placeholder="e.g. A white cat sitting on a windowsill in the rain")
generate = st.button("✨ Generate", type="primary", use_container_width=True)

if generate:
    if not prompt.strip():
        st.error("Pehle prompt likhein.")
    else:
        full_prompt = prompt.strip() + STYLES[style]
        base_seed = random.randint(0, 2**31 - 1) if seed_in < 0 else int(seed_in)
        slots = st.columns(n_images)
        for i in range(n_images):
            seed = base_seed + i
            with slots[i]:
                status = st.status(f"Image {i + 1}/{n_images} ban rahi hai…", expanded=True)
                try:
                    t0 = time.time()
                    if backend == "hf":
                        img = gen_huggingface(full_prompt, negative, width, height, seed, model, HF_TOKEN)
                    elif backend == "horde":
                        img = gen_horde(full_prompt, negative, width, height, seed, model, status)
                    else:
                        if i > 0 and not POLLI_KEY:
                            status.write("Rate limit ke liye 15s wait…")
                            time.sleep(15)
                        img = gen_pollinations(full_prompt, width, height, seed, model, POLLI_KEY, status)
                    status.update(label="Done ✅", state="complete", expanded=False)
                    png = to_png_bytes(img)
                    st.image(img, use_container_width=True)
                    st.caption(f"Seed {seed} · {time.time() - t0:.1f}s")
                    st.download_button("⬇️ Download", png, f"image_{seed}.png", "image/png",
                                       key=f"dl_{seed}_{i}_{time.time_ns()}")
                    st.session_state.history.insert(0, {"png": png, "prompt": prompt.strip(), "seed": seed})
                except Exception as e:
                    status.update(label="Failed ❌", state="error", expanded=True)
                    if "402" in str(e):
                        st.error("Hugging Face credits khatam. Sidebar se koi free model select karein.")
                    else:
                        st.error(f"Generation fail hui: {e}")

# ----------------------------- History -----------------------------
if st.session_state.history:
    st.divider()
    st.subheader("🖼️ History (is session ki images)")
    hist = st.session_state.history[:12]
    for row in range(0, len(hist), 4):
        for col, item in zip(st.columns(4), hist[row:row + 4]):
            col.image(item["png"], use_container_width=True)
            col.caption(f"{item['prompt'][:60]} · seed {item['seed']}")
