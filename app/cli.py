"""
Jarvis Command Line Interface (CLI).
Provides local laptop management utilities such as generating secure remote pairing codes.
"""

import sys
from app.core.config import settings
from app.core.remote_auth import remote_session_manager


def print_pairing_code():
    code = remote_session_manager.generate_pairing_code()
    print("=" * 70)
    print("  JARVIS SECURE REMOTE PAIRING (Tailscale Phone-to-Laptop Control)")
    print("=" * 70)
    print(f"  ONE-TIME PAIRING CODE:   {code}")
    print(f"  VALIDITY:                {settings.REMOTE_PAIRING_CODE_TIMEOUT_SECONDS} seconds (5 minutes)")
    print("  STORAGE:                 In-memory only (Never stored on disk or logs)")
    print("-" * 70)
    print("  INSTRUCTIONS:")
    print("  1. Ensure Tailscale is running on both your laptop and phone.")
    print("  2. Run Tailscale Serve on this laptop (if not already running):")
    print("     tailscale serve --https=443 http://127.0.0.1:8000")
    print("  3. On your phone, open the hosted Jarvis PWA:")
    print("     https://jarvis-kumar-shaurya.vercel.app")
    print("  4. Open Settings -> Remote Pairing (Tailscale).")
    print("  5. Enter your laptop's Tailscale domain:")
    print("     https://<your-machine-name>.<your-tailnet>.ts.net")
    print(f"  6. Enter the 6-digit code '{code}' and tap 'Connect & Pair'.")
    print("=" * 70)


def main():
    if len(sys.argv) > 1 and sys.argv[1].lower() in ("pair", "code", "generate-code"):
        print_pairing_code()
    else:
        print("Usage:")
        print("  python -m app.cli pair        - Generate a 5-minute one-time remote pairing code")


if __name__ == "__main__":
    main()
