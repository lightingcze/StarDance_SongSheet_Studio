"""Small, dependency-free Standard MIDI File reader/writer for SongSheet projects.

Supports SMF format 0/1, PPQ timing, tempo maps, program changes, running
status, and note on/off events. SMPTE-timed and format 2 files are rejected
with actionable errors instead of being silently misread.
"""
from __future__ import annotations

import struct
import uuid
from pathlib import Path
from typing import Any

PPQ = 960

GM_PROGRAMS = [
    "Acoustic Grand Piano", "Bright Acoustic Piano", "Electric Grand Piano", "Honky-tonk Piano",
    "Electric Piano 1", "Electric Piano 2", "Harpsichord", "Clavinet", "Celesta", "Glockenspiel",
    "Music Box", "Vibraphone", "Marimba", "Xylophone", "Tubular Bells", "Dulcimer",
    "Drawbar Organ", "Percussive Organ", "Rock Organ", "Church Organ", "Reed Organ", "Accordion",
    "Harmonica", "Tango Accordion", "Acoustic Guitar (nylon)", "Acoustic Guitar (steel)",
    "Electric Guitar (jazz)", "Electric Guitar (clean)", "Electric Guitar (muted)", "Overdriven Guitar",
    "Distortion Guitar", "Guitar harmonics", "Acoustic Bass", "Electric Bass (finger)",
    "Electric Bass (pick)", "Fretless Bass", "Slap Bass 1", "Slap Bass 2", "Synth Bass 1", "Synth Bass 2",
    "Violin", "Viola", "Cello", "Contrabass", "Tremolo Strings", "Pizzicato Strings", "Orchestral Harp",
    "Timpani", "String Ensemble 1", "String Ensemble 2", "SynthStrings 1", "SynthStrings 2", "Choir Aahs",
    "Voice Oohs", "Synth Voice", "Orchestra Hit", "Trumpet", "Trombone", "Tuba", "Muted Trumpet",
    "French Horn", "Brass Section", "SynthBrass 1", "SynthBrass 2", "Soprano Sax", "Alto Sax",
    "Tenor Sax", "Baritone Sax", "Oboe", "English Horn", "Bassoon", "Clarinet", "Piccolo", "Flute",
    "Recorder", "Pan Flute", "Blown Bottle", "Shakuhachi", "Whistle", "Ocarina", "Lead 1 (square)",
    "Lead 2 (sawtooth)", "Lead 3 (calliope)", "Lead 4 (chiff)", "Lead 5 (charang)", "Lead 6 (voice)",
    "Lead 7 (fifths)", "Lead 8 (bass + lead)", "Pad 1 (new age)", "Pad 2 (warm)", "Pad 3 (polysynth)",
    "Pad 4 (choir)", "Pad 5 (bowed)", "Pad 6 (metallic)", "Pad 7 (halo)", "Pad 8 (sweep)",
    "FX 1 (rain)", "FX 2 (soundtrack)", "FX 3 (crystal)", "FX 4 (atmosphere)", "FX 5 (brightness)",
    "FX 6 (goblins)", "FX 7 (echoes)", "FX 8 (sci-fi)", "Sitar", "Banjo", "Shamisen", "Koto",
    "Kalimba", "Bag pipe", "Fiddle", "Shanai", "Tinkle Bell", "Agogo", "Steel Drums", "Woodblock",
    "Taiko Drum", "Melodic Tom", "Synth Drum", "Reverse Cymbal", "Guitar Fret Noise", "Breath Noise",
    "Seashore", "Bird Tweet", "Telephone Ring", "Helicopter", "Applause", "Gunshot",
]


def _read_vlq(data: bytes, pos: int) -> tuple[int, int]:
    value = 0
    for _ in range(4):
        if pos >= len(data):
            raise ValueError("MIDI soubor končí uprostřed časové hodnoty.")
        byte = data[pos]
        pos += 1
        value = (value << 7) | (byte & 0x7F)
        if byte < 0x80:
            return value, pos
    raise ValueError("Neplatná MIDI časová hodnota (VLQ).")


def _vlq(value: int) -> bytes:
    value = max(0, int(value))
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.insert(0, 0x80 | (value & 0x7F))
        value >>= 7
    return bytes(out)


def _parse_track(chunk: bytes, track_index: int) -> tuple[str, list[dict[str, Any]], list[tuple[int, int]]]:
    pos = 0
    tick = 0
    running = None
    name = f"Track {track_index + 1}"
    events: list[dict[str, Any]] = []
    tempos: list[tuple[int, int]] = []
    while pos < len(chunk):
        delta, pos = _read_vlq(chunk, pos)
        tick += delta
        if pos >= len(chunk):
            break
        status = chunk[pos]
        if status & 0x80:
            pos += 1
            if status < 0xF0:
                running = status
        elif running is not None:
            status = running
        else:
            raise ValueError("MIDI obsahuje událost bez počátečního status byte.")

        if status == 0xFF:
            if pos >= len(chunk):
                break
            meta_type = chunk[pos]
            pos += 1
            size, pos = _read_vlq(chunk, pos)
            payload = chunk[pos:pos + size]
            if len(payload) != size:
                raise ValueError("MIDI obsahuje neúplnou meta událost.")
            pos += size
            if meta_type == 0x03:
                name = payload.decode("utf-8", "replace").strip() or name
            elif meta_type == 0x51 and size == 3:
                tempo = int.from_bytes(payload, "big")
                if tempo:
                    tempos.append((tick, tempo))
            elif meta_type == 0x2F:
                break
            running = None
            continue
        if status in (0xF0, 0xF7):
            size, pos = _read_vlq(chunk, pos)
            pos += size
            running = None
            continue
        if status >= 0xF0:
            # System common/realtime messages are not needed for the note map.
            width = 1 if status in (0xF1, 0xF3) else 2 if status == 0xF2 else 0
            pos += width
            running = None
            continue

        command, channel = status & 0xF0, status & 0x0F
        width = 1 if command in (0xC0, 0xD0) else 2
        if pos + width > len(chunk):
            raise ValueError("MIDI obsahuje neúplnou událost.")
        a = chunk[pos]
        b = chunk[pos + 1] if width == 2 else 0
        pos += width
        if command == 0xC0:
            events.append({"tick": tick, "type": "program", "channel": channel, "program": a})
        elif command == 0x90 and b > 0:
            events.append({"tick": tick, "type": "on", "channel": channel, "pitch": a, "velocity": b})
        elif command == 0x80 or (command == 0x90 and b == 0):
            events.append({"tick": tick, "type": "off", "channel": channel, "pitch": a, "velocity": b})
    return name, events, tempos


def load_midi(path: str | Path) -> dict[str, Any]:
    data = Path(path).read_bytes()
    if len(data) < 14 or data[:4] != b"MThd":
        raise ValueError("Soubor nemá platnou hlavičku Standard MIDI File.")
    header_size = int.from_bytes(data[4:8], "big")
    if header_size < 6 or len(data) < 8 + header_size:
        raise ValueError("MIDI soubor obsahuje neúplnou hlavičku.")
    fmt, track_count, division = struct.unpack(">HHH", data[8:14])
    if fmt == 2:
        raise ValueError("MIDI typu 2 obsahuje nezávislé sekvence; tento import podporuje typy 0 a 1.")
    if fmt not in (0, 1):
        raise ValueError(f"Nepodporovaný typ MIDI souboru: {fmt}.")
    if division & 0x8000:
        raise ValueError("MIDI používá SMPTE časování; očekává se standardní PPQ.")
    if division == 0:
        raise ValueError("MIDI obsahuje nulové PPQ časování.")

    pos = 8 + header_size
    raw_tracks = []
    for index in range(track_count):
        if pos + 8 > len(data) or data[pos:pos + 4] != b"MTrk":
            raise ValueError("MIDI stopa chybí nebo je poškozená.")
        size = int.from_bytes(data[pos + 4:pos + 8], "big")
        pos += 8
        raw_tracks.append(_parse_track(data[pos:pos + size], index))
        pos += size

    tempo_events = [(0, 500000)]
    for _, _, tempos in raw_tracks:
        tempo_events.extend(tempos)
    tempo_events.sort(key=lambda item: item[0])
    # Last tempo event at a tick wins, as specified by MIDI playback ordering.
    compact = []
    for event in tempo_events:
        if compact and compact[-1][0] == event[0]:
            compact[-1] = event
        else:
            compact.append(event)
    tick_points = [0]
    sec_points = [0.0]
    active_tempo = compact[0][1]
    for tick, tempo in compact[1:]:
        sec_points.append(sec_points[-1] + (tick - tick_points[-1]) * active_tempo / (division * 1_000_000))
        tick_points.append(tick)
        active_tempo = tempo

    def to_seconds(tick: int) -> float:
        # Binary search is unnecessary for typical song-sheet event counts.
        i = 0
        for j in range(1, len(tick_points)):
            if tick_points[j] > tick:
                break
            i = j
        return sec_points[i] + (tick - tick_points[i]) * compact[i][1] / (division * 1_000_000)

    parts: dict[tuple[int, int], dict[str, Any]] = {}
    global_program = {channel: 0 for channel in range(16)}
    for track_index, (track_name, events, _) in enumerate(raw_tracks):
        active: dict[tuple[int, int], list[dict[str, Any]]] = {}
        programs: dict[int, int] = {}
        for event in events:
            channel = event["channel"]
            if event["type"] == "program":
                global_program[channel] = event["program"]
                programs[channel] = event["program"]
                existing = parts.get((track_index, channel))
                if existing and not existing["notes"]:
                    existing["program"] = event["program"]
                continue
            key = (track_index, channel)
            part = parts.setdefault(key, {
                "id": uuid.uuid4().hex,
                "name": track_name,
                "program": programs.get(channel, global_program[channel]),
                "channel": channel,
                "notes": [],
            })
            if event["type"] == "on":
                active.setdefault((channel, event["pitch"]), []).append(event)
            else:
                stack = active.get((channel, event["pitch"]), [])
                if stack:
                    start = stack.pop(0)
                    part["notes"].append({
                        "id": uuid.uuid4().hex,
                        "pitch": start["pitch"],
                        "start": to_seconds(start["tick"]),
                        "end": max(to_seconds(event["tick"]), to_seconds(start["tick"]) + 0.03),
                        "velocity": start["velocity"],
                        "manual": False,
                    })
    # MIDI may omit note-offs for a malformed/power-stopped file; close at final event.
    end_tick = max((e["tick"] for _, events, _ in raw_tracks for e in events), default=0)
    for track_index, (track_name, events, _) in enumerate(raw_tracks):
        active: dict[tuple[int, int], list[dict[str, Any]]] = {}
        part_map = {channel: parts[(track_index, channel)] for t, channel in parts if t == track_index}
        for event in events:
            channel = event["channel"]
            if event["type"] == "on":
                active.setdefault((channel, event["pitch"]), []).append(event)
            elif event["type"] == "off":
                stack = active.get((channel, event["pitch"]), [])
                if stack:
                    stack.pop(0)
        for (channel, pitch), stack in active.items():
            part = part_map.get(channel)
            if part:
                for start in stack:
                    part["notes"].append({"id": uuid.uuid4().hex, "pitch": pitch,
                        "start": to_seconds(start["tick"]), "end": max(to_seconds(end_tick), to_seconds(start["tick"]) + 0.03),
                        "velocity": start["velocity"], "manual": False})

    tracks = []
    for part in parts.values():
        program = max(0, min(127, int(part["program"])))
        part["program_name"] = "Drums" if part["channel"] == 9 else GM_PROGRAMS[program]
        part["is_drum"] = part["channel"] == 9
        if part["channel"] == 9:
            part["name"] = "Percussion" if part["name"].startswith("Track ") else part["name"]
        elif part["name"].startswith("Track "):
            part["name"] = GM_PROGRAMS[program]
        part["notes"].sort(key=lambda note: (note["start"], note["pitch"]))
        tracks.append(part)
    tracks.sort(key=lambda part: (part["channel"] == 9, part["channel"], part["program"], part["name"]))
    duration = max((note["end"] for part in tracks for note in part["notes"]), default=0.0)
    return {"schema_version": 1, "engine": "MIDI import", "model": "Standard MIDI File", "tracks": tracks,
            "duration": duration, "source_file": Path(path).name, "ppq": division}


def _track_chunk(name: str, program: int, channel: int, notes: list[dict[str, Any]], bpm: float, ppq: int) -> bytes:
    tempo = round(60_000_000 / max(1.0, min(999.0, float(bpm))))
    events: list[tuple[int, int, bytes]] = [(0, -3, b"\xff\x03" + _vlq(len(name.encode("utf-8"))) + name.encode("utf-8")),
                                                  (0, -2, b"\xff\x51\x03" + tempo.to_bytes(3, "big")),
                                                  (0, -1, bytes([0xC0 | channel, max(0, min(127, int(program)))]))]
    for note in notes:
        start = max(0.0, float(note.get("start", 0) or 0))
        end = max(start + 0.03, float(note.get("end", start + 0.1) or (start + 0.1)))
        start_tick = round(start * ppq * bpm / 60.0)
        end_tick = max(start_tick + 1, round(end * ppq * bpm / 60.0))
        pitch = max(0, min(127, int(note.get("pitch", 60))))
        velocity = max(1, min(127, int(note.get("velocity", 96))))
        events.append((start_tick, 1, bytes([0x90 | channel, pitch, velocity])))
        events.append((end_tick, 0, bytes([0x80 | channel, pitch, 0])))
    events.sort(key=lambda item: (item[0], item[1]))
    data = bytearray()
    last_tick = 0
    for tick, _, message in events:
        data.extend(_vlq(tick - last_tick))
        data.extend(message)
        last_tick = tick
    data.extend(b"\x00\xff\x2f\x00")
    return b"MTrk" + struct.pack(">I", len(data)) + data


def save_midi(path: str | Path, music_analysis: dict[str, Any], bpm: float = 120.0) -> None:
    tracks = music_analysis.get("tracks") or []
    if not tracks:
        raise ValueError("V projektu nejsou žádné noty k exportu do MIDI.")
    clean_tracks = [track for track in tracks if track.get("notes")]
    if not clean_tracks:
        raise ValueError("V projektu nejsou žádné noty k exportu do MIDI.")
    melodic_track_count = sum(not track.get("is_drum") for track in clean_tracks)
    if melodic_track_count > 15:
        raise ValueError("Standardní MIDI má 15 melodických kanálů a jeden bicí kanál; slučte některé stopy před exportem.")
    chunks = []
    used_channels: set[int] = set()
    for index, track in enumerate(clean_tracks):
        if track.get("is_drum"):
            channel = 9
        else:
            preferred = int(track.get("channel", index % 15))
            if preferred == 9 or preferred in used_channels or not 0 <= preferred <= 15:
                preferred = next((ch for ch in list(range(9)) + list(range(10, 16)) if ch not in used_channels), None)
            if preferred is None:
                raise ValueError("Není volný MIDI kanál pro další melodickou stopu.")
            channel = preferred
        used_channels.add(channel)
        name = str(track.get("name") or track.get("program_name") or f"Instrument {index + 1}")
        program = 0 if track.get("is_drum") else min(127, int(track.get("program", 0)))
        chunks.append(_track_chunk(name, program, channel, track["notes"], bpm, PPQ))
    header = b"MThd" + struct.pack(">IHHH", 6, 1, len(chunks), PPQ)
    Path(path).write_bytes(header + b"".join(chunks))


def normalize_music_analysis(value: Any) -> dict[str, Any]:
    """Validate and sanitize project note events while preserving editable metadata."""
    if not isinstance(value, dict):
        return {"schema_version": 1, "engine": "", "model": "", "tracks": []}
    tracks = []
    for index, raw in enumerate(value.get("tracks") or []):
        if not isinstance(raw, dict):
            continue
        notes = []
        for note in raw.get("notes") or []:
            if not isinstance(note, dict):
                continue
            try:
                start = max(0.0, float(note.get("start", 0)))
                end = max(start + 0.03, float(note.get("end", start + 0.1)))
                pitch = max(0, min(127, int(note.get("pitch", 60))))
                velocity = max(1, min(127, int(note.get("velocity", 96))))
            except (TypeError, ValueError, OverflowError):
                continue
            notes.append({"id": str(note.get("id") or uuid.uuid4().hex), "pitch": pitch, "start": start,
                          "end": end, "velocity": velocity, "manual": bool(note.get("manual", False)),
                          "velocity_source": str(note.get("velocity_source", ""))})
        if not notes:
            continue
        program = max(0, min(128, int(raw.get("program", 0) or 0)))
        channel = max(0, min(15, int(raw.get("channel", index % 16) or 0)))
        tracks.append({"id": str(raw.get("id") or uuid.uuid4().hex), "name": str(raw.get("name") or f"Instrument {index + 1}"),
                       "program": program, "program_name": str(raw.get("program_name") or ("Drums" if program == 128 else GM_PROGRAMS[program])),
                       "channel": channel, "is_drum": bool(raw.get("is_drum", channel == 9 or program == 128)),
                       "instrument_key": str(raw.get("instrument_key", "")),
                       "notes": sorted(notes, key=lambda n: (n["start"], n["pitch"]))})
    result = {key: value.get(key) for key in ("engine", "model", "source_file", "source_audio", "ppq", "model_size", "device", "backend", "resume_point", "progress", "duration", "sample_rate") if key in value}
    result.update({"schema_version": 1, "tracks": tracks})
    return result


def note_name(pitch: int) -> str:
    names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
    pitch = max(0, min(127, int(pitch)))
    return f"{names[pitch % 12]}{pitch // 12 - 1}"
