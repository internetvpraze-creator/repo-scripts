#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import time
import threading

import xbmc
import xbmcaddon
import xbmcvfs

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")


def log(msg: str) -> None:
    xbmc.log(f"[{ADDON_ID}] {msg}", xbmc.LOGDEBUG)


def _get_bool(setting_id: str, default: bool = False) -> bool:
    try:
        return ADDON.getSettingBool(setting_id)
    except Exception:
        v = (ADDON.getSetting(setting_id) or "").strip().lower()
        if v in ("true", "1", "yes", "on"):
            return True
        if v in ("false", "0", "no", "off"):
            return False
        return default


def _get_str(setting_id: str, default: str = "") -> str:
    try:
        v = ADDON.getSettingString(setting_id)
    except Exception:
        v = ADDON.getSetting(setting_id)
    v = (v or "").strip()
    return v if v else default


def _get_int(setting_id: str, default: int = 0) -> int:
    s = _get_str(setting_id, "")
    try:
        return int(float(s))
    except Exception:
        return default


def _norm_dir(p: str) -> str:
    p = p.replace("\\", "/").replace("\", "/")
    if p and not p.endswith("/"):
        p += "/"
    return p


def _join(dir_path: str, name: str) -> str:
    if dir_path.endswith("/"):
        return dir_path + name
    return dir_path + "/" + name


VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".mov", ".wmv", ".m4v", ".ts", ".webm", ".flv")


def list_videos(folder: str) -> list:
    folder = _norm_dir(folder)
    if not xbmcvfs.exists(folder):
        log(f"Folder does not exist: {folder}")
        return []

    try:
        dirs, files = xbmcvfs.listdir(folder)
    except Exception as e:
        log(f"listdir failed: {e}")
        return []

    videos = []
    for f in sorted(files):
        lf = f.lower()
        if any(lf.endswith(ext) for ext in VIDEO_EXTS):
            videos.append(_join(folder, f))

    return videos


def set_repeat_all() -> None:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "Player.SetRepeat", "params": {"playerid": 1, "repeat": "all"}}
    try:
        xbmc.executeJSONRPC(json.dumps(payload))
    except Exception as e:
        log(f"SetRepeat failed: {e}")


def set_shuffle_off() -> None:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "Player.SetShuffle", "params": {"playerid": 1, "shuffle": False}}
    try:
        xbmc.executeJSONRPC(json.dumps(payload))
    except Exception as e:
        log(f"SetShuffle failed: {e}")


def _write_ass_overlay(text: str, seconds: int) -> str:
    # NOTE: This uses subtitles as a lightweight on-screen overlay.
    # The file ends quickly and is then disabled again by the service.
    safe = text.replace("{", "(").replace("}", ")")
    tmp_path = xbmcvfs.translatePath(f"special://temp/{ADDON_ID}_startup.ass")
    ass = f"""[Script Info]
Title: {ADDON_ID} startup overlay
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.601

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default, Arial, 32, &H00FFFFFF, &H000000FF, &H80000000, &H80000000, 0, 0, 0, 0, 100, 100, 0, 0, 1, 2, 1, 3, 10, 20, 40, 0

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:{seconds:02d}.00,Default,,0,0,0,,{{\an3}}{safe}
"""
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(ass)
    return tmp_path


def show_startup_overlay_async() -> None:
    if not _get_bool("show_startup_text", False):
        return

    text = _get_str("startup_text", "").strip()
    if not text:
        return

    seconds = _get_int("startup_text_seconds", 2)
    seconds = max(1, min(10, seconds))

    def worker():
        try:
            # Wait a moment so playback has started
            xbmc.sleep(400)

            player = xbmc.Player()
            if not player.isPlayingVideo():
                return

            ass_path = _write_ass_overlay(text, seconds)
            player.setSubtitles(ass_path)
            player.showSubtitles(True)

            xbmc.sleep(seconds * 1000 + 200)
            # Disable subtitles again to avoid leaving them enabled
            try:
                player.showSubtitles(False)
            except Exception:
                pass
        except Exception as e:
            log(f"Overlay failed: {e}")

    threading.Thread(target=worker, daemon=True).start()


def play_loop(folder: str) -> None:
    vids = list_videos(folder)
    if not vids:
        log("No videos found.")
        return

    pl = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
    pl.clear()
    for v in vids:
        pl.add(v)

    player = xbmc.Player()
    player.play(pl)
    set_shuffle_off()
    set_repeat_all()

    try:
        xbmc.executebuiltin("Action(Fullscreen)")
    except Exception:
        pass

    show_startup_overlay_async()
    log(f"Started loop with {len(vids)} item(s) from {folder}")


def run() -> None:
    folder = _norm_dir(_get_str("video_dir", "/storage/emulated/0/Movies/"))

    # Give Kodi time to initialize UI + storage mounts
    xbmc.sleep(12000)

    play_loop(folder)

    monitor = xbmc.Monitor()
    while not monitor.abortRequested():
        if not xbmc.Player().isPlayingVideo():
            xbmc.sleep(2000)
            play_loop(folder)
        xbmc.sleep(1000)


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        log(f"Fatal: {e}")
