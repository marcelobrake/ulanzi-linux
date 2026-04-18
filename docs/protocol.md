# Ulanzi Stream Pad D200 — Wire Protocol

> Reverse-engineered notes. Ground truth comes from our own USB captures and
> cross-checked against [redphx/strmdck](https://github.com/redphx/strmdck) (MIT).

## USB identity

| Field       | Value                                   |
|-------------|-----------------------------------------|
| Vendor ID   | `0x2207` (Rockchip)                     |
| Product ID  | `0x0019`                                |
| Manufacturer| `Zkswe`                                 |
| Product     | `ulanzi`                                |
| Serial      | unit-specific (e.g. `02C37A015U3672742`)|

The device exposes **two HID interfaces**:

| Interface | Role                  | Notes                                                  |
|-----------|------------------------|--------------------------------------------------------|
| `0`       | Custom protocol        | `EP 0x82 IN` + `EP 0x01 OUT`, 1024-byte interrupt @1ms |
| `1`       | Boot-protocol keyboard | Must be suppressed to avoid ghost keys on Linux        |

Our driver talks to Interface 0. Interface 1 is claimed automatically by the
kernel `usbhid` driver; a udev rule is enough to make Interface 0 accessible
without `sudo`.

## Frame layout

Every HID packet is exactly **1024 bytes**.

```
offset  size  field              notes
------  ----  -----------------  --------------------------------------
0x000    2    magic              literal bytes  0x7C 0x7C
0x002    2    command            big-endian uint16 (see tables below)
0x004    4    length             big-endian uint32, BYTE-SWAPPED on wire
0x008   1016  data               command-specific payload, zero-padded
```

The length field is the oddest part of the protocol: logically a big-endian
uint32, but the firmware expects the bytes reversed. We encode this with
`construct.ByteSwapped(Int32ub)`.

## Host → Device commands

| Code     | Name                         | Payload                                  |
|----------|------------------------------|------------------------------------------|
| `0x0001` | `SET_BUTTONS`                | ZIP archive (full button grid)           |
| `0x000D` | `PARTIALLY_UPDATE_BUTTONS`   | ZIP archive (additive update)            |
| `0x0006` | `SET_SMALL_WINDOW_DATA`      | ASCII `mode|cpu|mem|time|gpu`            |
| `0x000A` | `SET_BRIGHTNESS`             | ASCII integer `0..100`                   |
| `0x000B` | `SET_LABEL_STYLE`            | JSON (`Align`, `Color`, `FontName`, ...) |

### ZIP payload schema (`SET_BUTTONS` / `PARTIALLY_UPDATE_BUTTONS`)

```
manifest.json      { "buttons": [ { "index": N, "icon": "icons/X.png", ... } ] }
icons/X.png        RGBA PNG, 85x85, per button
dummy.txt          required — firmware bug workaround, must exist
```

> **Firmware quirk:** the parser on the device discards the last file in
> the ZIP central directory, so we always append an empty `dummy.txt`
> sentinel. Without it, the last declared button silently loses its icon.

### Brightness

`SET_BRIGHTNESS` expects the value as **ASCII digits**, not a byte. `"0"`
turns the backlight off; `"100"` is maximum.

## Device → Host reports

| Code     | Name          | Payload                             |
|----------|---------------|-------------------------------------|
| `0x0101` | `BUTTON`      | `state:1`, `index:1`, `0x01`, `pressed:1` |
| `0x0303` | `DEVICE_INFO` | NUL-terminated ASCII string         |

### `BUTTON` payload

```
offset  size  field     notes
------  ----  --------  -----------------------------------
0x00    1     state     firmware-internal, retained for observability
0x01    1     index     0..12 on the D200 (3x5 layout, 13 active)
0x02    1     const     always 0x01
0x03    1     pressed   0x01 on press, 0x00 on release
```

## Report ID prefix

`hidapi` on Linux requires writes to start with a Report ID byte. The D200
uses Report ID `0x00`, so our outgoing frames are `1 + 1024 = 1025` bytes
at the transport boundary.

## Open questions

- [x] `SET_SMALL_WINDOW_DATA` uses pipe-separated ASCII fields: `mode|cpu|mem|time|gpu`.
- [ ] Whether `BACKGROUND` mode accepts extra fields beyond the standard payload.
- [ ] Whether brightness value is clamped by firmware or silently wraps.
- [ ] Any handshake the official client does before sending `SET_BUTTONS`.
- [ ] Heartbeat / watchdog behaviour when host goes silent.
