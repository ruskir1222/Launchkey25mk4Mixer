"""
parse_pcap.py — extract and decode MIDI messages from a USBPcap capture
of a Novation Launchkey Mini MK4 25.

v2: way more lenient — scans ALL USB packets with payload, looks for
F0..F7 SysEx anywhere, and also dumps non-SysEx MIDI (CC/Note/etc.) for
context. Adds a diagnostic header so we can tell if the capture even
contains USB-MIDI traffic.
"""

import argparse
import os
import shutil
import subprocess
import sys
from collections import Counter

NOVATION_MFR = b"\x00\x20\x29"

KNOWN_PRODUCT_IDS = {
    0x0F: "launchkey-mk4-mini-25?",
    0x14: "launchkey-mk4",
    0x35: "launchkey-mk3",
    0x36: "launchkey-mk3-mini",
}


# ----------------------------------------------------------------------
# USB-MIDI Event Packet decoding (USB Audio Class MIDI 1.0)
# Each USB-MIDI event is exactly 4 bytes:
#   byte0: (cable << 4) | CIN
#   bytes 1..3: actual MIDI bytes, length depends on CIN
# ----------------------------------------------------------------------
CIN_LEN = {
    0x0: 0, 0x1: 0,
    0x2: 2,         # 2-byte system common (Song select etc.)
    0x3: 3,         # 3-byte system common
    0x4: 3,         # SysEx start / continue
    0x5: 1,         # 1-byte SysEx end OR single-byte system message
    0x6: 2,         # 2-byte SysEx end
    0x7: 3,         # 3-byte SysEx end
    0x8: 3, 0x9: 3, 0xA: 3, 0xB: 3, 0xC: 2, 0xD: 2, 0xE: 3, 0xF: 1,
}


def decode_usb_midi_block(block: bytes) -> bytes:
    if len(block) != 4:
        return b""
    cin = block[0] & 0x0F
    n = CIN_LEN.get(cin, 0)
    return bytes(block[1 : 1 + n])


# ----------------------------------------------------------------------
# Naive direct scan: look for 0xF0..0xF7 anywhere in raw USB capdata.
# Some captures don't use the strict USB-MIDI packing; falling back to a
# direct byte scan lets us recover SysEx anyway.
# ----------------------------------------------------------------------
def scan_sysex_direct(buf: bytes):
    i = 0
    while True:
        start = buf.find(b"\xF0", i)
        if start < 0:
            return
        end = buf.find(b"\xF7", start + 1)
        if end < 0:
            return
        yield (start, end, bytes(buf[start + 1 : end]))
        i = end + 1


# ----------------------------------------------------------------------
# tshark wrapper: yield each USB packet as (ts, direction, src_endpoint, raw_bytes)
# ----------------------------------------------------------------------
def run_tshark(pcap_path: str):
    tshark = shutil.which("tshark")
    if not tshark:
        for cand in (
            r"C:\Program Files\Wireshark\tshark.exe",
            r"C:\Program Files (x86)\Wireshark\tshark.exe",
        ):
            if os.path.exists(cand):
                tshark = cand
                break
    if not tshark:
        sys.stderr.write("ERROR: tshark not found. Install Wireshark from "
                         "https://www.wireshark.org/download.html and re-run.\n")
        sys.exit(2)

    cmd = [
        tshark, "-r", pcap_path,
        "-T", "fields",
        "-e", "frame.time_relative",
        "-e", "usb.endpoint_address.direction",
        "-e", "usb.transfer_type",
        "-e", "usb.endpoint_address.number",
        "-e", "usb.capdata",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        sys.stderr.write("ERROR: failed to invoke tshark.\n")
        sys.exit(2)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr or "tshark failed\n")
        sys.exit(proc.returncode)

    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        ts_s, dir_s, tt_s, ep_s, hex_s = parts[:5]
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
        direction = "IN" if (dir_s or "").strip() == "1" else "OUT"
        try:
            tt = int(tt_s, 16) if (tt_s or "").startswith("0x") else int(tt_s or "0")
        except ValueError:
            tt = 0
        try:
            ep = int(ep_s or "0")
        except ValueError:
            ep = 0
        yield (ts, direction, ep, tt, data)


def collect(pcap_path: str):
    packets = list(run_tshark(pcap_path))
    total = len(packets)
    bulk_count = sum(1 for p in packets if p[3] == 0x03)
    int_count  = sum(1 for p in packets if p[3] == 0x01)
    ctrl_count = sum(1 for p in packets if p[3] == 0x02)
    iso_count  = sum(1 for p in packets if p[3] == 0x00)

    # 1) Try strict USB-MIDI decoding on bulk endpoints (Class compliant MIDI)
    midi_stream = {"IN": bytearray(), "OUT": bytearray()}
    sysex_events = []
    midi_events = []  # non-SysEx (CC, Note, etc.) for context

    for ts, direction, ep, tt, data in packets:
        # Try USB-MIDI 4-byte packing first
        decoded = bytearray()
        for off in range(0, len(data), 4):
            block = data[off : off + 4]
            if len(block) < 4:
                break
            decoded.extend(decode_usb_midi_block(block))
        if decoded:
            stream = midi_stream[direction]
            stream.extend(decoded)
            while True:
                a = stream.find(b"\xF0")
                if a < 0:
                    break
                b = stream.find(b"\xF7", a)
                if b < 0:
                    break
                payload = bytes(stream[a + 1 : b])
                sysex_events.append((ts, direction, payload, "usb-midi"))
                del stream[: b + 1]

            # Capture short MIDI events (CC/Note) so we don't lose context
            i = 0
            while i < len(decoded):
                st = decoded[i]
                if st & 0x80 and not (0xF0 <= st <= 0xF7):
                    mtype = st & 0xF0
                    ch = (st & 0x0F) + 1
                    if mtype in (0x80, 0x90, 0xA0, 0xB0, 0xE0):  # 3-byte msgs
                        if i + 2 < len(decoded):
                            midi_events.append((ts, direction, st, decoded[i+1], decoded[i+2]))
                            i += 3; continue
                    if mtype in (0xC0, 0xD0):  # 2-byte
                        if i + 1 < len(decoded):
                            midi_events.append((ts, direction, st, decoded[i+1], None))
                            i += 2; continue
                i += 1

        # 2) Fallback: direct byte scan for SysEx (handles unusual packings)
        for _, _, payload in scan_sysex_direct(data):
            sysex_events.append((ts, direction, payload, "direct-scan"))

    return {
        "total": total,
        "bulk": bulk_count,
        "interrupt": int_count,
        "control": ctrl_count,
        "iso": iso_count,
        "sysex": sysex_events,
        "midi": midi_events,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pcap")
    ap.add_argument("--out")
    args = ap.parse_args()

    if not os.path.exists(args.pcap):
        sys.stderr.write(f"file not found: {args.pcap}\n"); sys.exit(1)

    r = collect(args.pcap)
    sink = open(args.out, "w", encoding="utf-8") if args.out else sys.stdout

    def w(s): sink.write(s + "\n")

    w("# Launchkey Mini MK4 25 — USBPcap decoded output v2")
    w(f"# source: {args.pcap}")
    w("")
    w("## USB PACKET STATS")
    w(f"  total packets with capdata: {r['total']}")
    w(f"  bulk transfers:             {r['bulk']}")
    w(f"  interrupt transfers:        {r['interrupt']}")
    w(f"  control transfers:          {r['control']}")
    w(f"  iso transfers:              {r['iso']}")
    w(f"  SysEx messages found:       {len(r['sysex'])}")
    w(f"  short MIDI events found:    {len(r['midi'])}")
    w("")

    if not r["sysex"] and not r["midi"]:
        w("!! No MIDI data of any kind found in this capture.")
        w("   Likely causes:")
        w("   - Capture bus was wrong (Launchkey is on a different USBPcap bus)")
        w("   - Recording was stopped before any traffic flowed")
        w("   - Novation Components wasn't actually connected to the device")
        sink.close() if args.out else None
        return

    # SysEx dump
    if r["sysex"]:
        w("## SYSEX MESSAGES")
        opcode_counter = Counter()
        for i, (ts, direction, payload, source) in enumerate(r["sysex"]):
            head = f"[{i:04d}] t={ts:8.3f}s  {direction:<3}  src={source}"
            if payload.startswith(NOVATION_MFR):
                product = payload[3] if len(payload) > 3 else None
                opcode  = payload[4] if len(payload) > 4 else None
                body    = payload[5:] if len(payload) > 5 else b""
                pname = KNOWN_PRODUCT_IDS.get(product, f"unknown(0x{product:02X})") if product is not None else "?"
                op_s = f"0x{opcode:02X}" if opcode is not None else "?"
                w(f"{head}  Novation  product={pname}  op={op_s}")
                w(f"     body=[{' '.join(f'{b:02X}' for b in body)}]")
                if opcode is not None:
                    opcode_counter[opcode] += 1
            else:
                w(f"{head}  non-Novation")
                w(f"     full=[{' '.join(f'{b:02X}' for b in payload)}]")
            w("")
        w("## NOVATION OPCODE FREQUENCY")
        for op, n in sorted(opcode_counter.items(), key=lambda x: -x[1]):
            w(f"  0x{op:02X}  ->  {n}")
        w("")

    # Short MIDI dump (CC/Note etc.)
    if r["midi"]:
        w("## SHORT MIDI EVENTS (CC, Note, etc. — for context)")
        for i, (ts, direction, st, d1, d2) in enumerate(r["midi"][:200]):
            mtype = st & 0xF0
            ch = (st & 0x0F) + 1
            name = {
                0x80: "NoteOff", 0x90: "NoteOn",
                0xA0: "PolyAT",  0xB0: "CC",
                0xC0: "PgmChg",  0xD0: "ChanAT",
                0xE0: "PitchBend",
            }.get(mtype, f"0x{st:02X}")
            d2s = f" v={d2}" if d2 is not None else ""
            w(f"  t={ts:8.3f}s {direction:<3} ch{ch:<2} {name:<10} d1={d1}{d2s}")
        if len(r["midi"]) > 200:
            w(f"  ... ({len(r['midi']) - 200} more events truncated)")
        w("")

    if args.out:
        sink.close()


if __name__ == "__main__":
    main()
