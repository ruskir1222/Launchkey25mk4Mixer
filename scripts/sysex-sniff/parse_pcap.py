"""
parse_pcap.py — extract and decode SysEx messages from a USBPcap capture
of a Novation Launchkey Mini MK4 25.

Usage:
    python parse_pcap.py launchkey_capture.pcap > decoded.txt

Requires:
    pip install pyshark   (which wraps Wireshark's tshark CLI)
OR fallback (no extra dep):
    Uses 'tshark' directly via subprocess if pyshark is missing.

What it does:
    - Reads every USB packet from the .pcap
    - Filters for USB Audio Class MIDI bulk-OUT/IN frames
    - Decodes the 32-bit USB-MIDI event packets into raw MIDI byte streams
    - Reassembles SysEx (F0 .. F7) messages
    - Labels each by manufacturer ID + best-guess opcode meaning
    - Outputs a chronological, human-readable list

Output format:
    [time]  DIR=OUT|IN  MFR=Novation(0020 29)  PROD=mk4mini(0F)  CMD=01  PAYLOAD=00 01 7F 00 00 ...
    > guess: set_pad_color  pad=0  rgb=(127, 0, 0)
"""

import argparse
import os
import shutil
import struct
import subprocess
import sys
from collections import OrderedDict

NOVATION_MFR = b"\x00\x20\x29"

# Best-guess opcode dictionary (will be extended as we decode more)
KNOWN_PRODUCT_IDS = {
    0x0F: "launchkey-mk4-mini-25",
    0x14: "launchkey-mk4",
    0x35: "launchkey-mk3",
    0x36: "launchkey-mk3-mini",
}

KNOWN_OPCODES = {
    # (product, op) -> human label
    (0x0F, 0x01): "MAYBE set_pad_color (carried over from MK3?)",
    (0x0F, 0x02): "MAYBE lcd_text (carried over from full MK4?)",
    (0x0F, 0x0A): "MAYBE knob_ring (carried over from MK3?)",
    (0x0F, 0x11): "MAYBE custom mode bank",
}


def decode_usb_midi_event(packet32: bytes) -> bytes:
    """A USB-MIDI Event Packet is exactly 4 bytes:
       byte0: CIN (low nibble) + cable number (high nibble)
       byte1..3: MIDI bytes (depends on CIN)
    Returns the MIDI bytes in this packet (0..3 bytes).
    """
    if len(packet32) != 4:
        return b""
    cin = packet32[0] & 0x0F
    midi = packet32[1:4]
    # Number of valid bytes per CIN per USB-MIDI spec
    CIN_LEN = {
        0x0: 0, 0x1: 0, 0x2: 2, 0x3: 3,
        0x4: 3,  # SysEx start or continue
        0x5: 1,  # 1-byte SysEx end (or single-byte system msg)
        0x6: 2,  # 2-byte SysEx end
        0x7: 3,  # 3-byte SysEx end
        0x8: 3, 0x9: 3, 0xA: 3, 0xB: 3, 0xC: 2, 0xD: 2, 0xE: 3, 0xF: 1,
    }
    n = CIN_LEN.get(cin, 0)
    return bytes(midi[:n])


def reassemble_sysex(raw_midi_stream: bytes):
    """Yields (start_index, end_index, payload) tuples for each SysEx message
    (excluding the leading F0 / trailing F7)."""
    i = 0
    while i < len(raw_midi_stream):
        if raw_midi_stream[i] == 0xF0:
            start = i
            j = i + 1
            while j < len(raw_midi_stream) and raw_midi_stream[j] != 0xF7:
                j += 1
            if j < len(raw_midi_stream):
                yield (start, j, raw_midi_stream[i + 1 : j])
                i = j + 1
            else:
                break
        else:
            i += 1


def guess_label(product_id: int, opcode: int, payload: bytes) -> str:
    key = (product_id, opcode)
    label = KNOWN_OPCODES.get(key)
    if label:
        # Heuristics on top of label
        if "pad_color" in label and len(payload) >= 4:
            # MK3 format: [opcode] [bank] [pad_id] [colour_index OR r] [g] [b]
            return (
                f"{label}  "
                f"bank=0x{payload[1]:02X} pad=0x{payload[2]:02X} "
                f"rest=({' '.join(f'{b:02X}' for b in payload[3:])})"
            )
        if "lcd_text" in label:
            try:
                txt = bytes(b for b in payload[1:] if 32 <= b < 127).decode("ascii", "replace")
                return f"{label}  text={txt!r}  raw=({' '.join(f'{b:02X}' for b in payload[1:])})"
            except Exception:
                pass
        return label
    return "UNKNOWN"


def run_tshark(pcap_path: str):
    """Yields (timestamp, direction, raw_bytes) for each USB bulk transfer
    that contains MIDI data."""
    tshark = shutil.which("tshark") or "tshark"
    cmd = [
        tshark,
        "-r", pcap_path,
        "-Y", "usb.transfer_type==0x03",  # bulk
        "-T", "fields",
        "-e", "frame.time_relative",
        "-e", "usb.endpoint_address.direction",  # 0=OUT, 1=IN
        "-e", "usb.capdata",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        sys.stderr.write("ERROR: tshark not found. Install Wireshark and re-run.\n")
        sys.exit(2)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr or "tshark failed\n")
        sys.exit(proc.returncode)
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        ts_s, dir_s, hex_s = parts[0], parts[1], parts[2]
        if not hex_s:
            continue
        try:
            ts = float(ts_s)
        except ValueError:
            continue
        try:
            data = bytes.fromhex(hex_s.replace(":", ""))
        except ValueError:
            continue
        direction = "IN" if dir_s.strip() == "1" else "OUT"
        yield (ts, direction, data)


def collect_sysex(pcap_path: str):
    """Stream USB transfers, split into 4-byte USB-MIDI events, decode to raw
    MIDI byte streams per direction, and reassemble SysEx messages."""
    midi_per_dir = {"IN": bytearray(), "OUT": bytearray()}
    timeline = []  # (time, direction, raw_midi_bytes_indices_start)
    last_ts = {"IN": 0.0, "OUT": 0.0}

    sysex_events = []

    for ts, direction, data in run_tshark(pcap_path):
        # Split data into 4-byte USB-MIDI event packets
        for off in range(0, len(data), 4):
            block = data[off : off + 4]
            if len(block) < 4:
                break
            midi = decode_usb_midi_event(block)
            if not midi:
                continue
            stream = midi_per_dir[direction]
            stream.extend(midi)
            # If a SysEx just completed, flush it
            while b"\xF0" in stream and b"\xF7" in stream[stream.index(b"\xF0") :]:
                a = stream.index(b"\xF0")
                b = stream.index(b"\xF7", a)
                payload = bytes(stream[a + 1 : b])
                sysex_events.append((ts, direction, payload))
                del stream[: b + 1]
        last_ts[direction] = ts
    return sysex_events


def format_event(idx: int, ts: float, direction: str, payload: bytes) -> str:
    out = [f"[{idx:04d}] t={ts:8.3f}s  {direction}"]
    if payload.startswith(NOVATION_MFR):
        product = payload[3] if len(payload) > 3 else None
        opcode  = payload[4] if len(payload) > 4 else None
        body    = payload[5:] if len(payload) > 5 else b""
        prod_name = KNOWN_PRODUCT_IDS.get(product, f"unknown(0x{product:02X})") if product is not None else "?"
        if opcode is None:
            return " ".join(out) + f"  MFR=Novation product={prod_name}  (no opcode)"
        out.append(f"MFR=Novation product={prod_name} op=0x{opcode:02X}")
        out.append(f"body=[{' '.join(f'{b:02X}' for b in body)}]")
        guess = guess_label(product, opcode, body)
        out.append(f"\n     > guess: {guess}")
    else:
        out.append("MFR=non-Novation  payload=[" + " ".join(f"{b:02X}" for b in payload) + "]")
    return " ".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pcap", help=".pcap file from USBPcapCMD")
    ap.add_argument("--out", help="output path (default: stdout)")
    args = ap.parse_args()

    if not os.path.exists(args.pcap):
        sys.stderr.write(f"file not found: {args.pcap}\n")
        sys.exit(1)

    events = collect_sysex(args.pcap)
    if args.out:
        sink = open(args.out, "w", encoding="utf-8")
    else:
        sink = sys.stdout

    sink.write(f"# USBPcap-decoded SysEx for Launchkey Mini MK4 25\n")
    sink.write(f"# source: {args.pcap}\n")
    sink.write(f"# total SysEx messages: {len(events)}\n\n")

    by_opcode = OrderedDict()
    for i, (ts, direction, payload) in enumerate(events):
        line = format_event(i, ts, direction, payload)
        sink.write(line + "\n\n")
        if payload.startswith(NOVATION_MFR) and len(payload) > 4:
            opcode = payload[4]
            by_opcode.setdefault(opcode, 0)
            by_opcode[opcode] += 1

    sink.write("\n# OPCODE FREQUENCY (Novation-tagged messages only):\n")
    for op, count in sorted(by_opcode.items(), key=lambda x: -x[1]):
        sink.write(f"  0x{op:02X}  →  {count} messages\n")

    if sink is not sys.stdout:
        sink.close()


if __name__ == "__main__":
    main()
