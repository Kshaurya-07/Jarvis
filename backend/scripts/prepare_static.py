#!/usr/bin/env python3
"""
Populates the dedicated static output directory (`frontend/public/`) for
Vercel deployment. Copies only the intended public client-side static assets:
- `frontend/mobile/` -> `frontend/public/` (Mobile Companion PWA)
- `frontend/demo/`   -> `frontend/public/demo/` (Local Fictional Science Demo Page)
- `frontend/landing/` -> `frontend/public/landing/` (Jarvis vision landing page)

Zero backend source code, zero python runtimes, zero data folders, and zero secrets
are ever copied into the public output.
"""

import shutil
from pathlib import Path


def prepare_static():
    root = Path(__file__).resolve().parent.parent.parent
    frontend_dir = root / "frontend"
    mobile_dir = frontend_dir / "mobile"
    demo_dir = frontend_dir / "demo"
    landing_dir = frontend_dir / "landing"
    public_dir = frontend_dir / "public"

    assert mobile_dir.exists(), f"Source mobile directory not found: {mobile_dir}"
    assert demo_dir.exists(), f"Source demo directory not found: {demo_dir}"
    assert landing_dir.exists(), f"Source landing directory not found: {landing_dir}"

    print(f"Preparing dedicated public output directory: {public_dir}")

    # Create public directory structure
    public_dir.mkdir(parents=True, exist_ok=True)
    (public_dir / "icons").mkdir(parents=True, exist_ok=True)
    (public_dir / "demo").mkdir(parents=True, exist_ok=True)
    (public_dir / "landing").mkdir(parents=True, exist_ok=True)

    # 1. Copy mobile PWA assets to public root
    mobile_files = [
        "index.html",
        "style.css",
        "app.js",
        "manifest.webmanifest",
        "service-worker.js",
    ]
    for filename in mobile_files:
        src = mobile_dir / filename
        dest = public_dir / filename
        shutil.copy2(src, dest)
        print(f"  Copied mobile asset: {dest.name}")

    # Copy icons. The mobile PWA manifest, index.html and service worker all
    # reference icons/icon-192.png and icons/icon-512.png, and the service
    # worker precaches them — if they are missing here the PWA install fails
    # and the icons 404, so fail loudly instead of silently copying nothing.
    icons_src = mobile_dir / "icons"
    icons_dest = public_dir / "icons"
    icons = sorted(icons_src.glob("*.png")) if icons_src.exists() else []
    assert icons, (
        f"Mobile PWA icons not found in {icons_src}: "
        "expected icons/icon-192.png and icons/icon-512.png"
    )
    for icon in icons:
        shutil.copy2(icon, icons_dest / icon.name)
        print(f"  Copied icon: icons/{icon.name}")

    # 2. Copy demo page to public/demo/
    demo_src = demo_dir / "index.html"
    demo_dest = public_dir / "demo" / "index.html"
    shutil.copy2(demo_src, demo_dest)
    print(f"  Copied demo page: demo/index.html")

    # 3. Copy landing page to public/landing/
    for filename in ["index.html", "landing.css", "landing.js"]:
        src = landing_dir / filename
        dest = public_dir / "landing" / filename
        shutil.copy2(src, dest)
        print(f"  Copied landing asset: landing/{filename}")

    print("\nSUCCESS: Dedicated public directory populated successfully.")
    print("Files in public output directory:")
    for f in sorted(public_dir.rglob("*")):
        if f.is_file():
            print(f"  - {f.relative_to(public_dir).as_posix()} ({f.stat().st_size:,} bytes)")


if __name__ == "__main__":
    prepare_static()
