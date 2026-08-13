"""X11 keysym names mapped to Linux evdev key codes.

``xdotool`` speaks X11 keysym names; ``ydotool`` speaks raw evdev codes
(``<code>:<pressed>``) because it injects below the display server via
``/dev/uinput``. This table bridges the two so a single ``keys:`` value in
``deck.yaml`` works on both X11 and Wayland.

Generated from ``/usr/include/linux/input-event-codes.h``; the numeric
codes are kernel ABI and therefore stable across distributions.
"""

from __future__ import annotations

__all__ = [
    "KEYSYM_TO_EVDEV",
    "MODIFIER_ALIASES",
    "keysym_to_evdev",
    "translate_shortcut",
]

KEYSYM_TO_EVDEV: dict[str, int] = {
    "0": 11,
    "1": 2,
    "2": 3,
    "3": 4,
    "4": 5,
    "5": 6,
    "6": 7,
    "7": 8,
    "8": 9,
    "9": 10,
    "a": 30,
    "Alt_L": 56,
    "Alt_R": 100,
    "apostrophe": 40,
    "b": 48,
    "backslash": 43,
    "BackSpace": 14,
    "bracketleft": 26,
    "bracketright": 27,
    "c": 46,
    "Caps_Lock": 58,
    "comma": 51,
    "Control_L": 29,
    "Control_R": 97,
    "d": 32,
    "Delete": 111,
    "Down": 108,
    "e": 18,
    "End": 107,
    "equal": 13,
    "Escape": 1,
    "f": 33,
    "F1": 59,
    "F10": 68,
    "F11": 87,
    "F12": 88,
    "F13": 183,
    "F14": 184,
    "F15": 185,
    "F16": 186,
    "F17": 187,
    "F18": 188,
    "F19": 189,
    "F2": 60,
    "F20": 190,
    "F21": 191,
    "F22": 192,
    "F23": 193,
    "F24": 194,
    "F3": 61,
    "F4": 62,
    "F5": 63,
    "F6": 64,
    "F7": 65,
    "F8": 66,
    "F9": 67,
    "g": 34,
    "grave": 41,
    "h": 35,
    "Home": 102,
    "i": 23,
    "Insert": 110,
    "j": 36,
    "k": 37,
    "KP_Enter": 96,
    "l": 38,
    "Left": 105,
    "m": 50,
    "Menu": 127,
    "Meta_L": 125,
    "Meta_R": 126,
    "minus": 12,
    "n": 49,
    "Next": 109,
    "Num_Lock": 69,
    "o": 24,
    "p": 25,
    "Page_Down": 109,
    "Page_Up": 104,
    "Pause": 119,
    "period": 52,
    "Print": 99,
    "Prior": 104,
    "q": 16,
    "r": 19,
    "Return": 28,
    "Right": 106,
    "s": 31,
    "Scroll_Lock": 70,
    "semicolon": 39,
    "Shift_L": 42,
    "Shift_R": 54,
    "slash": 53,
    "space": 57,
    "Super_L": 125,
    "Super_R": 126,
    "t": 20,
    "Tab": 15,
    "u": 22,
    "Up": 103,
    "v": 47,
    "w": 17,
    "x": 45,
    "y": 21,
    "z": 44,
    "XF86AudioForward": 208,
    "XF86AudioLowerVolume": 114,
    "XF86AudioMedia": 226,
    "XF86AudioMicMute": 248,
    "XF86AudioMute": 113,
    "XF86AudioNext": 163,
    "XF86AudioPause": 164,
    "XF86AudioPlay": 164,
    "XF86AudioPrev": 165,
    "XF86AudioRaiseVolume": 115,
    "XF86AudioRecord": 167,
    "XF86AudioRewind": 168,
    "XF86AudioStop": 166,
    "XF86Back": 158,
    "XF86Bluetooth": 237,
    "XF86Calculator": 140,
    "XF86Close": 206,
    "XF86Copy": 133,
    "XF86Cut": 137,
    "XF86Display": 227,
    "XF86Documents": 235,
    "XF86Eject": 161,
    "XF86Explorer": 144,
    "XF86Favorites": 156,
    "XF86Forward": 159,
    "XF86HomePage": 172,
    "XF86KbdBrightnessDown": 229,
    "XF86KbdBrightnessUp": 230,
    "XF86KbdLightOnOff": 228,
    "XF86Launch1": 148,
    "XF86Launch2": 149,
    "XF86Launch3": 202,
    "XF86Launch4": 203,
    "XF86Mail": 155,
    "XF86MonBrightnessDown": 224,
    "XF86MonBrightnessUp": 225,
    "XF86MyComputer": 157,
    "XF86New": 181,
    "XF86Open": 134,
    "XF86Paste": 135,
    "XF86PowerOff": 116,
    "XF86Reload": 173,
    "XF86RFKill": 247,
    "XF86Save": 234,
    "XF86ScreenSaver": 152,
    "XF86Search": 217,
    "XF86Sleep": 142,
    "XF86Tools": 171,
    "XF86TouchpadOff": 532,
    "XF86TouchpadOn": 531,
    "XF86TouchpadToggle": 530,
    "XF86WakeUp": 143,
    "XF86WLAN": 238,
    "XF86WWW": 150,
}

# Shorthand accepted by xdotool's grammar, mapped onto canonical keysyms.
MODIFIER_ALIASES: dict[str, str] = {
    "ctrl": "Control_L",
    "control": "Control_L",
    "ctl": "Control_L",
    "shift": "Shift_L",
    "alt": "Alt_L",
    "meta": "Meta_L",
    "super": "Super_L",
    "win": "Super_L",
    "cmd": "Super_L",
    "altgr": "Alt_R",
}

# Keysym spellings that differ only by case from what users tend to type.
_CASE_INSENSITIVE_FALLBACK = {name.lower(): name for name in KEYSYM_TO_EVDEV}


def keysym_to_evdev(name: str) -> int | None:
    """Resolve a single keysym name to its evdev code, or ``None``."""
    canonical = MODIFIER_ALIASES.get(name.lower(), name)
    code = KEYSYM_TO_EVDEV.get(canonical)
    if code is not None:
        return code
    fallback = _CASE_INSENSITIVE_FALLBACK.get(canonical.lower())
    return KEYSYM_TO_EVDEV.get(fallback) if fallback else None


def translate_shortcut(keys: str) -> list[str] | None:
    """Translate an xdotool-style chord into ydotool ``<code>:<pressed>`` args.

    ``"ctrl+alt+t"`` becomes press-ctrl, press-alt, press-t, then the releases
    in reverse order. Returns ``None`` if any component is unknown, so callers
    can fall back to a keysym-native tool rather than emitting a wrong chord.
    """
    parts = [part for part in keys.split("+") if part]
    if not parts:
        return None
    # A trailing literal "+" (e.g. "ctrl++") collapses to the plus keysym.
    if keys.endswith("+") and len(parts) >= 1:
        parts.append("equal")

    codes: list[int] = []
    for part in parts:
        code = keysym_to_evdev(part)
        if code is None:
            return None
        codes.append(code)

    argv = [f"{code}:1" for code in codes]
    argv.extend(f"{code}:0" for code in reversed(codes))
    return argv
