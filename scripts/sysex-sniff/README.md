# 🔬 Launchkey MK4 Mini — SysEx Sniffing Toolkit

> Capture and decode the SysEx commands Novation Components sends to your
> Launchkey Mini MK4 25 so we can drive the **RGB pads** and **LCD screen**
> from our own helper script.

---

## Why this is needed

Novation doesn't publish the SysEx protocol for the MK4 Mini's pad LEDs or LCD.
The old Launchkey MK3 SysEx commands don't work on the MK4 Mini firmware
(rejected silently).

To unlock LED + LCD control, we need to:
1. Watch what Novation Components sends over USB when it changes a pad colour or LCD text.
2. Decode those SysEx packets.
3. Replicate them from our Python helper.

This folder contains everything needed to do that capture and decode.

---

## What you'll need

| Tool | Purpose | Free? |
|---|---|---|
| **USBPcap** | Windows USB packet capture (driver-level) | ✅ Yes |
| **Wireshark** | UI to view captured packets | ✅ Yes |
| **Novation Components** | The official Novation editor that talks to your Launchkey | ✅ Yes |
| `parse_pcap.py` (in this folder) | Extracts SysEx messages from USBPcap captures | ✅ Yes |

Time: ~30 minutes total.

---

## Step-by-step procedure

### 1. Install the tools

Run from an Administrator PowerShell:

```powershell
winget install -e --id WiresharkFoundation.Wireshark
winget install -e --id USBPcap.USBPcap
```

Or download manually:
- USBPcap: https://desowin.org/usbpcap/
- Wireshark: https://www.wireshark.org/download.html
- Novation Components: https://components.novationmusic.com/

**Reboot after USBPcap installs** (it installs a kernel driver).

### 2. Identify the USB bus your Launchkey is on

1. Plug in your Launchkey Mini MK4 25
2. Open Device Manager → Universal Serial Bus controllers
3. Right-click each USB Root Hub → Properties → Details → look for one connected to "Launchkey Mini MK4 25"
4. Note the bus number (USBPcap shows it as `\\.\USBPcap1`, `\\.\USBPcap2`, etc.)

### 3. Start a USBPcap capture

Open a terminal and run (replace `USBPcap1` with your bus from step 2):

```cmd
"C:\Program Files\USBPcap\USBPcapCMD.exe" -d \\.\USBPcap1 -o launchkey_capture.pcap
```

Leave this running. You'll stop it with `Ctrl+C` after step 4.

### 4. Drive Novation Components through every state we care about

Open **Novation Components**. Connect your Launchkey. For each of the following,
**count to 2 seconds between actions** so it's easy to find them in the capture:

**A. Pad LEDs — Custom mode**

1. Switch the device to Custom 1
2. Set Pad 1 to **bright red** (`Components → click pad → pick color`)
3. Set Pad 2 to **bright green**
4. Set Pad 3 to **bright blue**
5. Set Pad 4 to **bright yellow**
6. Set Pad 5 to **bright cyan**
7. Set Pad 6 to **bright magenta**
8. Set Pad 7 to **white**
9. Set Pad 8 to **off/black**
10. Click **Send to Launchkey** (the upload button)

This gives us a clean palette of color commands across the 16 pads.

**B. LCD text**

1. In Components, change the Custom 1 name to something distinctive, e.g. `HELLO`
2. Send to device
3. Repeat with names of different lengths: `A`, `AB`, `ABC`, `ABCD`, `LONGNAME12345`
4. Try sending with various special characters: `Hi!`, `123`, `🎵` (might be ignored, that's fine to record)

**C. Knob ring / value display**

1. Switch to **Volume** mode on the Launchkey
2. Turn knob 1 slowly from 0 → 100 → 0
3. Move on to knob 2, do the same
4. This lets us see if there's a "set knob LED ring position" SysEx

### 5. Stop the capture

`Ctrl+C` in the USBPcapCMD window. A file `launchkey_capture.pcap` is created
in the current directory.

### 6. Decode the capture

From this folder, run:

```cmd
python parse_pcap.py launchkey_capture.pcap > decoded.txt
```

`decoded.txt` will contain a human-readable list of every SysEx message with:
- Timestamp
- Direction (PC → device or device → PC)
- Manufacturer ID
- Hex payload
- Best-guess interpretation

### 7. Share the file

Either:
- Paste the contents of `decoded.txt` into the chat, OR
- Upload it to a gist / paste service and share the link

I'll analyze the patterns and add the matching commands to `launchkey_helper.py`
so the LEDs and LCD light up from our own dashboard.

---

## What we're looking for (so you know what's important)

Each SysEx message starts with `F0` and ends with `F7`. Novation's
manufacturer ID is `00 20 29`. So every interesting message looks like:

```
F0 00 20 29 02 0F [opcode] [data ...] F7
                  ↑       ↑
                  product device ID
```

Some known opcodes for OTHER Launchkey models:
- `01 00`  set pad color (MK3) — *we'll be confirming if MK4 Mini uses this or something new*
- `02 ..`  LCD text on Launchkey 49/61
- `0A ..`  knob ring position (MK3)

What we'll discover for the MK4 Mini:
- The exact opcode + format for pad colors (probably similar to MK3 but
  potentially with a new sub-channel or device ID)
- The opcode + character encoding for the LCD text
- Whether the LCD accepts arbitrary text or only enum values

---

## After we have the protocol

Once decoded, the work in `launchkey_helper.py` is small:

1. Add `set_pad_color(channel, note, r, g, b)` that emits the discovered SysEx
2. Add `set_lcd_text(text)` that emits the LCD SysEx
3. Wire them into the existing dispatcher so:
   - Mapped pad → LED takes its color from the mapping
   - Active knob → LCD shows "Spotify  73%" while the knob is being turned

Estimated time once protocol is captured: **~1 hour of coding**.
