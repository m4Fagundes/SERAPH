import platform
import subprocess

def detect_dark_mode_mac():
    """Detects if macOS is in dark mode"""
    if platform.system() != "Darwin":
        return False
    try:
        result = subprocess.run(
            ["defaults", "read", "-g", "AppleInterfaceStyle"],
            capture_output=True, text=True
        )
        return result.stdout.strip().lower() == "dark"
    except:
        return False
