# MicroAlign

MicroAlign is a desktop tool for **manual image alignment** and **batch cropping**.  
It shows your **base image** on the left and the **current image to align** on the right, with a grid overlay, live overlay/alpha blending, and super-fine keyboard controls for translation, rotation, and subtle zoom. When you’re done, save full-resolution aligned images and crop the same region across the entire set — with original quality preserved.

<img src="docs/screenshot.png" alt="MicroAlign UI" width="800"/>

---

## Features

- Side-by-side **Base** (left) and **Moving** (right) panels.
- **Grid overlay** with hover-linked cell highlight on both panels.
- **Micro controls**:
  - Move in preview-pixel units (adjustable step).
  - Rotate in small increments.
  - Zoom (regular and **micro zoom**) to handle slight perspective/distance differences.
- **Overlay mode**: blend moving image over base with adjustable alpha.
- **Outline** of the transformed moving image for quick sanity checks.
- **Recursive source directory** support.
- **Save aligned** full-resolution PNGs.
- **Crop all** to the same box (chosen on the base image) — crops are taken from aligned full-res images (no quality loss).

---

## Install

**Python:** 3.9+ (3.11 recommended)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
