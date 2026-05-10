from __future__ import annotations

import datetime
import os
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import read_wallpaper_data


def generate_wallpaper() -> Path | None:
    data = read_wallpaper_data()
    if not data:
        return None

    width = 1920
    height = 1080
    bg_color = (15, 15, 20)
    text_color = (220, 220, 220)
    
    mood = data.get("mood", "")
    if mood == "Needs Focus":
        accent_color = (200, 50, 50)
    elif mood == "On Track":
        accent_color = (50, 200, 100)
    else:
        accent_color = (200, 150, 50)
        
    dim_color = (60, 60, 70)

    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    try:
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 120)
        font_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
    except IOError:
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_small = ImageFont.load_default()

    now = datetime.datetime.now()
    current_hour = now.hour
    
    # 1. Draw Hour Dots (24 dots)
    dot_radius = 8
    dot_spacing = 35
    total_dots = 24
    grid_width = (total_dots - 1) * dot_spacing
    start_x = (width - grid_width) // 2
    start_y = height // 2 - 50

    for h in range(total_dots):
        x = start_x + h * dot_spacing
        y = start_y
        
        if h < current_hour:
            # Past
            draw.ellipse([x - dot_radius, y - dot_radius, x + dot_radius, y + dot_radius], fill=dim_color)
        elif h == current_hour:
            # Current
            draw.ellipse([x - dot_radius, y - dot_radius, x + dot_radius, y + dot_radius], fill=accent_color)
        else:
            # Future
            draw.ellipse([x - dot_radius, y - dot_radius, x + dot_radius, y + dot_radius], outline=dim_color, width=2)


    # 2. Current Time
    now_str = now.strftime("%H:%M")
    try:
        bbox = draw.textbbox((0, 0), now_str, font=font_large)
        tw = bbox[2] - bbox[0]
    except AttributeError:
        tw = 400
    draw.text(((width - tw) // 2, start_y - 180), now_str, font=font_large, fill=text_color)

    # 3. Next Action
    next_action = data.get("next", {})
    start_time = next_action.get('start', '')
    end_time = next_action.get('end', '')
    time_str = f"[{start_time}-{end_time}] " if start_time else ""
    action_text = f"{time_str}{next_action.get('name', 'All clear')}"
    
    try:
        bbox = draw.textbbox((0, 0), action_text, font=font_medium)
        aw = bbox[2] - bbox[0]
    except AttributeError:
        aw = 600
    draw.text(((width - aw) // 2, start_y + 80), action_text, font=font_medium, fill=text_color)

    # 4. Score
    score = data.get("score", 0)
    score_text = f"SCORE: {score:.0f}/100  |  MOOD: {mood.upper()}"
    
    try:
        bbox = draw.textbbox((0, 0), score_text, font=font_small)
        sw = bbox[2] - bbox[0]
    except AttributeError:
        sw = 300
    draw.text(((width - sw) // 2, start_y + 160), score_text, font=font_small, fill=dim_color)

    out_path = Path("~/.local/share/selfheal/wallpaper.png").expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path


def apply_wallpaper(path: Path) -> None:
    path_str = str(path.absolute())
    
    # Hyprland
    if "HYPRLAND_INSTANCE_SIGNATURE" in os.environ:
        subprocess.run(["hyprctl", "hyprpaper", "preload", path_str], capture_output=True)
        subprocess.run(["hyprctl", "hyprpaper", "wallpaper", f",{path_str}"], capture_output=True)
        return

    # KDE Plasma
    if "KDE_FULL_SESSION" in os.environ:
        script = f"""
        var allDesktops = desktops();
        for (i=0;i<allDesktops.length;i++) {{
            d = allDesktops[i];
            d.wallpaperPlugin = "org.kde.image";
            d.currentConfigGroup = Array("Wallpaper", "org.kde.image", "General");
            d.writeConfig("Image", "file://{path_str}");
        }}
        """
        subprocess.run(["qdbus", "org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell.evaluateScript", script], capture_output=True)
        return

    # macOS
    try:
        if os.uname().sysname == "Darwin":
            script = f'tell application "Finder" to set desktop picture to POSIX file "{path_str}"'
            subprocess.run(["osascript", "-e", script], capture_output=True)
            return
    except AttributeError:
        pass

    # Windows
    if os.name == "nt":
        import ctypes
        ctypes.windll.user32.SystemParametersInfoW(20, 0, path_str, 0)
        return
