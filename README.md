# 🎨 AI Image Generator (Streamlit)

Text prompt se AI images banayein. Python + Streamlit + Pollinations / Hugging Face.

## Local run
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Cloud deploy
1. Is folder ko GitHub repo mein push karein (`app.py`, `requirements.txt` root mein hon).
2. https://share.streamlit.io par jayein > **New app** > repo, branch, `app.py` select karein.
3. (Optional) Advanced settings > Secrets mein `HF_TOKEN = "hf_..."` add karein.
4. **Deploy** dabayein.

## Providers
- **Hugging Face** (recommended): free token, sab se reliable.
- **Stable Horde**: bina key ke chalta hai, lekin queue ki wajah se slow.
- **Pollinations**: anonymous endpoint aksar 503 deta hai; `POLLINATIONS_API_KEY` se behtar chalta hai.
