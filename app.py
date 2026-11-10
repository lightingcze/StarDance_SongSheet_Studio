"""StarDance SongSheet Studio - local desktop editor for printable song sheets."""
from __future__ import annotations

import json
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
import uuid
import wave
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageTk
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas as pdf_canvas


APP_NAME = "StarDance SongSheet Studio"
PAGE_W, PAGE_H = 2480, 1754  # A4 landscape at approximately 210 dpi
FPS = 25
FONT_DIR = "assets/fonts"
PRODUCTION_FIELDS = [
    ("choreography", "Poznámky choreografů"),
    ("theme", "Téma a charakter čísla"),
    ("costumes", "Kostýmy"),
    ("props", "Rekvizity"),
    ("lighting", "Požadavky na světla"),
    ("led", "LED obsah a videoprojekce"),
    ("effects", "Speciální efekty"),
    ("other", "Další produkční poznámky"),
]
DEFAULTS: dict[str, Any] = {
    "metadata": {"title": "", "episode": "", "artist": "", "performer": "", "dance": ""},
    "production": {key: "" for key, _ in PRODUCTION_FIELDS},
    "duration": "", "bpm": "", "bpm_confidence": "Neurčeno", "audio_path": "",
    "waveform": [], "cues": "", "sections": "", "ld_proposals": "",
    "markers": [],
    "instrument_summary": "", "instrument_summary_short": "", "instrument_events": [],
    "references": [], "accent": "#16A9A0", "dark": False,
    "show_waveform": True, "show_references": True,
}

INSTRUMENT_FILTERS = ["Všechny", "Bicí/perkuse", "Bas/kopák", "Tónová vrstva", "Bez přiřazení"]


def app_resource(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative


def ffmpeg_executable() -> str | None:
    try:
        import imageio_ffmpeg  # type: ignore
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError, FileNotFoundError):
        return shutil.which("ffmpeg")


def tc25(seconds: float) -> str:
    """Format seconds as HH:MM:SS:FF (25 fps, rounded to nearest frame)."""
    frames = max(0, int(round(float(seconds) * FPS)))
    hh, rem = divmod(frames, 3600 * FPS)
    mm, rem = divmod(rem, 60 * FPS)
    ss, ff = divmod(rem, FPS)
    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"


def display_time(seconds: float) -> str:
    frames = max(0, int(round(seconds * FPS)))
    hh, rem = divmod(frames, 3600 * FPS)
    mm, rem = divmod(rem, 60 * FPS)
    ss, ff = divmod(rem, FPS)
    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"


def estimate_audio(path: str) -> dict[str, Any]:
    executable = ffmpeg_executable()
    if not executable:
        raise RuntimeError("Dekodér ffmpeg není dostupný. Nainstalujte ffmpeg nebo použijte sestavenou aplikaci.")
    command = [executable, "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", "22050", "-f", "f32le", "-"]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0 or not result.stdout:
        detail = result.stderr.decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError("Nahrávku se nepodařilo přečíst: " + (detail[-1] if detail else "neznámá chyba ffmpeg"))
    samples = np.frombuffer(result.stdout, dtype="<f4")
    if samples.size < 2205:
        raise RuntimeError("Nahrávka je příliš krátká nebo prázdná.")
    samples = np.nan_to_num(samples, copy=False)
    sr = 22050
    duration = float(samples.size / sr)

    # Compact peak envelope for the printable waveform and the editable project.
    bucket = max(1, int(math.ceil(samples.size / 2400)))
    padded = np.pad(samples, (0, (-len(samples)) % bucket))
    envelope = np.max(np.abs(padded.reshape(-1, bucket)), axis=1)
    maxamp = float(envelope.max()) or 1.0
    envelope = np.clip(envelope / maxamp, 0, 1).astype(float).tolist()

    # Estimate pulse from positive changes in a short RMS envelope. This is a
    # suggestion only: half/double-time and downbeat remain listening checks.
    hop = 1102  # approximately 50 ms, for tempo resolution
    hop_seconds = hop / sr
    frames = np.pad(samples, (0, (-len(samples)) % hop)).reshape(-1, hop)
    rms = np.sqrt(np.mean(frames * frames, axis=1))
    novelty = np.maximum(0, np.diff(rms, prepend=rms[0]))
    novelty -= float(novelty.mean())
    if novelty.size > 2 and float(np.max(np.abs(novelty))) > 1e-9:
        corr = np.correlate(novelty, novelty, mode="full")[novelty.size - 1:]
        # 60..180 BPM corresponds to 1.0..0.333 seconds.
        lo = max(1, int(math.ceil(60 / (180 * hop_seconds))))
        hi = min(len(corr) - 1, int(math.floor(60 / (60 * hop_seconds))))
        candidate = corr[lo:hi + 1]
        bpm = 0
        confidence = "Nízká"
        if candidate.size:
            lag = int(np.argmax(candidate)) + lo
            bpm = int(round(60 / (lag * hop_seconds)))
            baseline = float(np.median(candidate)) + 1e-9
            strength = float(candidate[lag - lo]) / baseline
            confidence = "Vyšší" if strength >= 2.8 else "Střední" if strength >= 1.65 else "Nízká"
    else:
        bpm, confidence = 0, "Nízká"

    # Ten-second loudness windows describe energy only, not musical phrasing.
    section_lines: list[str] = []
    window = 10.0
    energies = []
    for start in np.arange(0, duration, window):
        a, b = int(start * sr), min(samples.size, int((start + window) * sr))
        if b > a:
            energies.append((float(start), float(np.sqrt(np.mean(samples[a:b] ** 2)))) )
    if energies:
        vals = [e for _, e in energies]
        mid = float(np.median(vals))
        for i, (start, energy) in enumerate(energies):
            end = min(duration, start + window)
            label = "vyšší energie" if energy > mid * 1.22 else "nižší energie" if energy < mid * 0.78 else "střední energie"
            section_lines.append(f"{tc25(start)}–{tc25(end)}  {label} — automatický odhad, ověřit poslechem")

    # Prominent energy changes are candidate accents, never GO cues.
    peak_indices: list[int] = []
    if novelty.size > 5 and float(novelty.max()) > 0:
        threshold = float(np.quantile(novelty[novelty > 0], 0.92)) if np.any(novelty > 0) else float("inf")
        for idx in range(1, len(novelty) - 1):
            if novelty[idx] >= threshold and novelty[idx] >= novelty[idx - 1] and novelty[idx] > novelty[idx + 1]:
                if not peak_indices or idx - peak_indices[-1] >= 15:
                    peak_indices.append(idx)
        peak_indices = sorted(peak_indices, key=lambda i: novelty[i], reverse=True)[:8]
        peak_indices.sort()
    markers = [{"id": uuid.uuid4().hex, "label": "Možný hudební akcent", "time": round(i * hop_seconds * FPS) / FPS, "kind": "Akcent"} for i in peak_indices]
    cue_lines = [f"{tc25(item['time'])}  {item['label']} — návrh, ověřit poslechem" for item in markers]
    instrument_result = estimate_instrument_layers(samples, sr, duration)
    return {
        "duration": duration, "bpm": bpm, "bpm_confidence": confidence,
        "waveform": envelope, "sections": "\n".join(section_lines), "cues": "\n".join(cue_lines), "markers": markers,
        **instrument_result,
    }


def estimate_instrument_layers(samples: np.ndarray, sample_rate: int, duration: float) -> dict[str, Any]:
    """Estimate broad sound families from spectral bands; never claims exact source separation."""
    fft_size, hop = 2048, 2205
    if samples.size < fft_size:
        note = "Nahrávka je příliš krátká pro odhad nástrojových vrstev."
        return {"instrument_summary": note, "instrument_summary_short": "nedostatek dat", "instrument_events": []}
    starts = range(0, samples.size - fft_size + 1, hop)
    frames = np.stack([samples[start:start + fft_size] for start in starts])
    spectrum = np.abs(np.fft.rfft(frames * np.hanning(fft_size), axis=1))
    power = spectrum * spectrum
    frequencies = np.fft.rfftfreq(fft_size, 1 / sample_rate)
    band_masks = {
        "low": (frequencies >= 35) & (frequencies < 180),
        "mid": (frequencies >= 180) & (frequencies < 2200),
        "high": (frequencies >= 2200) & (frequencies < 9000),
    }
    band_power = {name: power[:, mask].sum(axis=1) for name, mask in band_masks.items()}
    total_power = power.sum(axis=1) + 1e-12
    low_share = band_power["low"] / total_power
    harmonic_share = (band_power["mid"] + band_power["high"]) / total_power
    flatness = np.exp(np.mean(np.log(power + 1e-12), axis=1)) / (np.mean(power + 1e-12, axis=1) + 1e-12)

    normalized = spectrum / (spectrum.sum(axis=1, keepdims=True) + 1e-12)
    flux = np.maximum(0, np.diff(normalized, axis=0)).sum(axis=1)
    transient_threshold = float(np.quantile(flux, 0.985)) if flux.size else float("inf")
    peak_candidates: list[int] = []
    for index in range(1, max(1, len(flux) - 1)):
        if flux[index] >= transient_threshold and flux[index] >= flux[index - 1] and flux[index] > flux[index + 1]:
            peak_candidates.append(index)
    transient_indices: list[int] = []
    for index in sorted(peak_candidates, key=lambda item: float(flux[item]), reverse=True):
        if all(abs(index - previous) >= 5 for previous in transient_indices):
            transient_indices.append(index)
        if len(transient_indices) >= 20:
            break
    transient_indices.sort()

    def run_starts(active: np.ndarray, minimum_gap_seconds: float, max_count: int) -> list[int]:
        starts_found: list[int] = []
        previous = -10**9
        index = 0
        min_gap = int(minimum_gap_seconds * sample_rate / hop)
        while index < len(active):
            if active[index]:
                if index == 0 or not active[index - 1]:
                    if index - previous >= min_gap:
                        starts_found.append(index)
                        previous = index
                index += 1
            else:
                index += 1
        return starts_found[:max_count]

    low_threshold = max(0.08, float(np.quantile(low_share, 0.60)) * 0.8)
    low_active = (low_share > low_threshold) & (band_power["low"] > float(np.quantile(band_power["low"], 0.35)))
    tonal_active = (flatness < 0.16) & (harmonic_share > 0.30) & (total_power > float(np.quantile(total_power, 0.35)))
    low_starts = run_starts(low_active, 4.0, 6)
    tonal_starts = run_starts(tonal_active, 4.0, 6)

    events: list[dict[str, Any]] = []
    for index in transient_indices:
        events.append({
            "time": round((index + 1) * hop / sample_rate * FPS) / FPS,
            "label": "Možný perkusní akcent",
            "instrument": "Bicí/perkuse",
        })
    for index in low_starts:
        events.append({
            "time": round(index * hop / sample_rate * FPS) / FPS,
            "label": "Možný nástup nízké vrstvy",
            "instrument": "Bas/kopák",
        })
    for index in tonal_starts:
        events.append({
            "time": round(index * hop / sample_rate * FPS) / FPS,
            "label": "Možný nástup tónové vrstvy",
            "instrument": "Tónová vrstva",
        })
    events.sort(key=lambda item: item["time"])

    mean_low = float(np.mean(low_share))
    median_flatness = float(np.median(flatness))
    transient_rate = len(peak_candidates) * 60 / max(duration, 1)
    percussion = "zřetelné transienty" if transient_rate >= 20 else "slabší transienty" if transient_rate >= 5 else "málo průkazných transientů"
    bass = "výraznější" if mean_low >= 0.24 else "možná přítomná" if mean_low >= 0.10 else "slabá / nerozpoznaná"
    tonal = "pravděpodobná" if median_flatness < 0.10 else "možná" if median_flatness < 0.24 else "neurčitá"
    summary = (
        f"• Bicí/perkuse: {percussion} ({transient_rate:.0f}/min), kandidátní transienty.\n"
        f"• Bas/kopák (35–180 Hz): {bass}; spektrum nerozliší kopák od basového nástroje.\n"
        f"• Tónová vrstva: {tonal}; může zahrnovat klávesy, piano, smyčce, kytaru či synth, které se zde nedají spolehlivě rozdělit.\n"
        "Heuristický odhad z frekvenčních pásem a transientů, nikoli rozpoznání jednotlivých stop. Potvrďte poslechem."
    )
    present = []
    if transient_rate >= 5:
        present.append(f"bicí/perkuse: {percussion}")
    if mean_low >= 0.10:
        present.append(f"bas/kopák: {bass}")
    if median_flatness < 0.24:
        present.append(f"tónová vrstva: {tonal}")
    short = " · ".join(present) if present else "jednotlivé nástroje nejsou zřetelně rozlišitelné"
    return {"instrument_summary": summary, "instrument_summary_short": short, "instrument_events": events}


class PageRenderer:
    def __init__(self, state: dict[str, Any], quality: str = "preview"):
        self.state = state
        self.scale = 1.0 if quality == "print" else 0.56
        self.w, self.h = int(PAGE_W * self.scale), int(PAGE_H * self.scale)
        self.fonts: dict[tuple[int, bool], ImageFont.FreeTypeFont] = {}
        self.dark = bool(state.get("dark"))
        self.accent = state.get("accent", "#16A9A0")
        self.bg = "#101820" if self.dark else "#F4F6F6"
        self.paper = "#17232B" if self.dark else "#FFFFFF"
        self.ink = "#F4F7F8" if self.dark else "#18252D"
        self.muted = "#A6B4BB" if self.dark else "#5F7078"
        self.line = "#35444C" if self.dark else "#D8E0E2"
        self.gold = "#F1B84B"

    def px(self, n: int | float) -> int:
        return int(n * self.scale)

    def font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        key = (size, bold)
        if key not in self.fonts:
            name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
            fp = app_resource(f"{FONT_DIR}/{name}")
            if not fp.exists():
                fp = Path("/usr/share/fonts/truetype/dejavu") / name
                self.fonts[key] = ImageFont.truetype(str(fp), self.px(size)) if fp.exists() else ImageFont.load_default()
        return self.fonts[key]

    def wrap(self, draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
        lines: list[str] = []
        for paragraph in (text or "").splitlines() or [""]:
            if not paragraph:
                lines.append("")
                continue
            words = paragraph.split()
            line = ""
            for word in words:
                trial = word if not line else f"{line} {word}"
                if draw.textbbox((0, 0), trial, font=font)[2] <= max_width or not line:
                    line = trial
                else:
                    lines.append(line)
                    line = word
            lines.append(line)
        return lines

    def draw_lines(self, draw: ImageDraw.ImageDraw, text: str, x: int, y: int, max_width: int,
                   font: ImageFont.FreeTypeFont, fill: str, line_gap: int = 10, max_lines: int | None = None) -> int:
        lines = self.wrap(draw, text, font, max_width)
        if max_lines is not None and len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = lines[-1].rstrip(" .") + " …"
        line_height = font.getbbox("Ag")[3] - font.getbbox("Ag")[1] + self.px(line_gap)
        for line in lines:
            draw.text((x, y), line, font=font, fill=fill)
            y += line_height
        return y

    def base(self, page_num: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
        img = Image.new("RGB", (self.w, self.h), self.bg)
        d = ImageDraw.Draw(img)
        m = self.px(70)
        d.rounded_rectangle((m, m, self.w - m, self.h - m), radius=self.px(24), fill=self.paper)
        d.rectangle((m, m, self.w - m, m + self.px(13)), fill=self.accent)
        d.text((m + self.px(36), m + self.px(32)), "STARDANCE 2026  /  SONG SHEET", font=self.font(25, True), fill=self.accent)
        d.text((self.w - m - self.px(220), m + self.px(32)), f"STRANA {page_num} / 2", font=self.font(21, True), fill=self.muted)
        footer_y = self.h - m - self.px(34)
        d.line((m + self.px(34), footer_y - self.px(19), self.w - m - self.px(34), footer_y - self.px(19)), fill=self.line, width=self.px(2))
        d.text((m + self.px(34), footer_y), "ČASOVÁNÍ 25 FPS  •  Automatické analýzy ověřit poslechem", font=self.font(18), fill=self.muted)
        return img, d

    def metadata_line(self) -> str:
        meta = self.state["metadata"]
        vals = [meta.get("episode", ""), meta.get("artist", ""), meta.get("performer", ""), meta.get("dance", "")]
        return "   •   ".join(x for x in vals if x) or "Doplňte díl, interpreta, účinkující nebo tanec v editoru"

    def page_one(self) -> Image.Image:
        img, d = self.base(1)
        m, inner = self.px(104), self.w - self.px(208)
        title = self.state["metadata"].get("title") or "Název skladby není vyplněn"
        d.text((m, self.px(150)), title[:90], font=self.font(52, True), fill=self.ink)
        d.text((m, self.px(226)), self.metadata_line(), font=self.font(24), fill=self.muted)
        instrument_short = self.state.get("instrument_summary_short", "")
        if instrument_short:
            self.draw_lines(d, f"NÁSTROJOVÉ VRSTVY (ODHAD): {instrument_short}", m, self.px(254), inner,
                            self.font(18, True), self.muted, line_gap=0, max_lines=1)

        # Duration and tempo cards.
        card_y, card_h, gap = self.px(282), self.px(118), self.px(20)
        card_w = (inner - gap) // 2
        duration = self.state.get("duration", "") or "—"
        try:
            duration = display_time(float(duration)) if isinstance(duration, (int, float)) else duration
        except ValueError:
            pass
        bpm = self.state.get("bpm") or "—"
        d.rounded_rectangle((m, card_y, m + card_w, card_y + card_h), radius=self.px(18), fill=self.bg, outline=self.line, width=self.px(2))
        d.text((m + self.px(24), card_y + self.px(15)), "DÉLKA SKLADBY", font=self.font(19, True), fill=self.muted)
        d.text((m + self.px(24), card_y + self.px(48)), str(duration), font=self.font(34, True), fill=self.ink)
        x2 = m + card_w + gap
        d.rounded_rectangle((x2, card_y, x2 + card_w, card_y + card_h), radius=self.px(18), fill=self.bg, outline=self.line, width=self.px(2))
        d.text((x2 + self.px(24), card_y + self.px(15)), "TEMPO", font=self.font(19, True), fill=self.muted)
        bpm_text = f"{bpm} BPM  ·  {self.state.get('bpm_confidence', 'Neurčeno')} jistota · odhad"
        d.text((x2 + self.px(24), card_y + self.px(48)), bpm_text[:70], font=self.font(28, True), fill=self.ink)

        # Waveform or explicit empty state.
        wave_y, wave_h = self.px(435), self.px(320)
        d.text((m, wave_y), "VLNOVÁ FORMA SKUTEČNÉ NAHRÁVKY", font=self.font(22, True), fill=self.ink)
        wx, wy, ww, wh = m, wave_y + self.px(42), inner, wave_h - self.px(48)
        d.rounded_rectangle((wx, wy, wx + ww, wy + wh), radius=self.px(12), fill=self.bg, outline=self.line, width=self.px(2))
        if self.state.get("show_waveform", True) and self.state.get("waveform"):
            values = np.asarray(self.state["waveform"], dtype=float)
            mid = wy + wh // 2
            d.line((wx + self.px(18), mid, wx + ww - self.px(18), mid), fill=self.line, width=self.px(1))
            x0 = wx + self.px(18)
            span = max(1, ww - self.px(36))
            for i, val in enumerate(values):
                x = x0 + int(round(i * span / max(1, len(values) - 1)))
                amp = max(self.px(2), int(val * wh * 0.43))
                d.line((x, mid - amp, x, mid + amp), fill=self.accent, width=max(1, self.px(2)))
            try:
                audio_duration = float(self.state.get("duration") or 0)
            except (ValueError, TypeError):
                audio_duration = 0
            if audio_duration > 0:
                for i, marker in enumerate(self.state.get("markers", [])):
                    try:
                        marker_time = max(0.0, min(audio_duration, float(marker.get("time", 0))))
                    except (TypeError, ValueError):
                        continue
                    marker_x = x0 + int(round(span * marker_time / audio_duration))
                    d.line((marker_x, wy + self.px(10), marker_x, wy + wh - self.px(8)), fill=self.gold, width=self.px(3))
                    label_y = wy + self.px(9 + (i % 3) * 22)
                    label = str(marker.get("label", "Značka"))[:18]
                    d.text((min(max(wx + self.px(12), marker_x + self.px(5)), wx + ww - self.px(180)), label_y), label, font=self.font(14, True), fill=self.gold)
        else:
            msg = "Waveform se zobrazí po načtení zvukového souboru." if self.state.get("show_waveform", True) else "Zobrazení waveformu je vypnuté v nastavení stránky."
            d.text((wx + self.px(28), wy + wh // 2 - self.px(14)), msg, font=self.font(22), fill=self.muted)

        # Time ruler with explicit 25 fps marks.
        ruler_y = wy + wh + self.px(17)
        d.text((m, ruler_y), "ČASOVÁ OSA  ·  HH:MM:SS:FF  ·  25 FPS", font=self.font(20, True), fill=self.muted)
        try:
            total = float(self.state.get("duration") or 0)
        except (ValueError, TypeError):
            total = 0
        line_y = ruler_y + self.px(44)
        d.line((m, line_y, m + inner, line_y), fill=self.line, width=self.px(3))
        if total > 0:
            count = min(8, max(2, int(total / 15) + 1))
            for i in range(count + 1):
                x = m + int(inner * i / count)
                t = total * i / count
                d.line((x, line_y - self.px(10), x, line_y + self.px(11)), fill=self.accent, width=self.px(3))
                label = tc25(t)
                d.text((x - self.px(42), line_y + self.px(17)), label, font=self.font(17), fill=self.muted)
        else:
            d.text((m, line_y + self.px(14)), "Načtěte audio a zadejte ověřenou délku pro časové značky.", font=self.font(18), fill=self.muted)

        # Editable cue/section text is represented verbatim with compact, readable cards.
        col_gap, col_w = self.px(28), (inner - self.px(28)) // 2
        box_y = line_y + self.px(70)
        box_h = self.h - self.px(170) - box_y
        self.draw_list_box(d, m, box_y, col_w, box_h, "RYTMICKÉ AKCENTY / CUE NÁVRHY", self.state.get("cues", ""), True)
        self.draw_list_box(d, m + col_w + col_gap, box_y, col_w, box_h, "ENERGETICKÉ ÚSEKY", self.state.get("sections", ""), False)
        return img

    def draw_list_box(self, d: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, title: str, content: str, gold: bool) -> None:
        d.rounded_rectangle((x, y, x + w, y + h), radius=self.px(14), fill=self.bg, outline=self.line, width=self.px(2))
        d.text((x + self.px(18), y + self.px(15)), title, font=self.font(18, True), fill=self.gold if gold else self.accent)
        text = content.strip() or ("Po analýze se zde zobrazí kandidátní akcenty. Všechny časy a GO body ověřte poslechem." if gold else "Po analýze se zde zobrazí 10sekundová energetická okna, nikoli hudební fráze.")
        self.draw_lines(d, text, x + self.px(18), y + self.px(48), w - self.px(36), self.font(21), self.ink, line_gap=5, max_lines=max(3, int(h / self.px(36))))

    def page_two(self) -> Image.Image:
        img, d = self.base(2)
        m = self.px(104)
        title = self.state["metadata"].get("title") or "Název skladby není vyplněn"
        d.text((m, self.px(150)), title[:90], font=self.font(42, True), fill=self.ink)
        d.text((m, self.px(213)), self.metadata_line(), font=self.font(22), fill=self.muted)
        top, bottom = self.px(266), self.h - self.px(137)
        left_x, left_w = m, self.px(1500)
        gap = self.px(30)
        right_x, right_w = left_x + left_w + gap, self.w - self.px(104) - (left_x + left_w + gap)

        d.rounded_rectangle((left_x, top, left_x + left_w, bottom), radius=self.px(16), fill=self.bg, outline=self.line, width=self.px(2))
        d.text((left_x + self.px(22), top + self.px(18)), "PRODUKČNÍ ZADÁNÍ  ·  PODLE PODKLADŮ", font=self.font(21, True), fill=self.accent)
        inner_x = left_x + self.px(22)
        content_y = top + self.px(62)
        col_gap = self.px(22)
        field_w = (left_w - self.px(66)) // 2
        groups = [PRODUCTION_FIELDS[:4], PRODUCTION_FIELDS[4:]]
        for col, fields in enumerate(groups):
            x = inner_x + col * (field_w + col_gap)
            y = content_y
            available = bottom - self.px(22) - content_y
            # Fit every source note without silently truncating; font scales down
            # only when the supplied notes require it.
            body_size = 23
            for candidate in (23, 21, 19, 17, 15):
                f = self.font(candidate)
                line_step = f.getbbox("Ag")[3] - f.getbbox("Ag")[1] + self.px(4)
                needed = 0
                for key, _label in fields:
                    value = self.state["production"].get(key, "").strip() or "Není vyplněno."
                    lines = self.wrap(d, value, f, field_w - self.px(34))
                    needed += self.px(48) + len(lines) * line_step + self.px(18)
                if needed <= available:
                    body_size = candidate
                    break
            body_font = self.font(body_size)
            for key, label in fields:
                value = self.state["production"].get(key, "").strip() or "Není vyplněno."
                lines = self.wrap(d, value, body_font, field_w - self.px(34))
                font_line = body_font.getbbox("Ag")[3] - body_font.getbbox("Ag")[1] + self.px(4)
                box_h = max(self.px(88), self.px(48) + len(lines) * font_line + self.px(14))
                d.rounded_rectangle((x, y, x + field_w, y + box_h), radius=self.px(10), fill=self.paper, outline=self.line, width=self.px(2))
                d.text((x + self.px(14), y + self.px(10)), label.upper(), font=self.font(17, True), fill=self.muted)
                text_y = y + self.px(34)
                for line in lines:
                    d.text((x + self.px(14), text_y), line, font=body_font, fill=self.ink)
                    text_y += font_line
                y += box_h + self.px(12)

        # Assistant proposals are separated visually and labeled as non-source material.
        proposal_h = self.px(790)
        d.rounded_rectangle((right_x, top, right_x + right_w, top + proposal_h), radius=self.px(16), fill="#2C261B" if self.dark else "#FFF7E6", outline=self.gold, width=self.px(3))
        d.text((right_x + self.px(20), top + self.px(18)), "NÁVRHY LD  ·  AUTOMATICKÉ / ASISTENT", font=self.font(20, True), fill=self.gold)
        ld = self.state.get("ld_proposals", "").strip()
        if not ld:
            ld = "Doplňte vlastní návrhy LD. Automatické hudební odhady se zobrazí po načtení audia a zůstávají neověřené. Produkční zadání je uvedeno samostatně vlevo."
        proposal_width = right_w - self.px(40)
        proposal_available = proposal_h - self.px(83)
        proposal_size = 23
        for candidate in (23, 21, 19, 17, 15):
            proposal_font = self.font(candidate)
            lines = self.wrap(d, ld, proposal_font, proposal_width)
            line_step = proposal_font.getbbox("Ag")[3] - proposal_font.getbbox("Ag")[1] + self.px(8)
            if len(lines) * line_step <= proposal_available:
                proposal_size = candidate
                break
        self.draw_lines(d, ld, right_x + self.px(20), top + self.px(64), proposal_width, self.font(proposal_size), self.ink, line_gap=8)

        ref_y = top + proposal_h + self.px(20)
        ref_h = bottom - ref_y
        d.rounded_rectangle((right_x, ref_y, right_x + right_w, bottom), radius=self.px(16), fill=self.bg, outline=self.line, width=self.px(2))
        d.text((right_x + self.px(20), ref_y + self.px(15)), "VIZUÁLNÍ REFERENCE", font=self.font(19, True), fill=self.accent)
        paths = self.state.get("references", []) if self.state.get("show_references", True) else []
        if not paths:
            msg = "Bez vložených obrázků" if self.state.get("show_references", True) else "Zobrazení referencí vypnuto"
            d.text((right_x + self.px(20), ref_y + self.px(56)), msg, font=self.font(17), fill=self.muted)
        else:
            thumb_w = (right_w - self.px(60)) // 2
            thumb_h = max(self.px(70), (ref_h - self.px(90)) // 2)
            for i, path in enumerate(paths[:4]):
                try:
                    image = Image.open(path).convert("RGB")
                    thumb = ImageOps.contain(image, (thumb_w, thumb_h))
                    tx = right_x + self.px(20) + (i % 2) * (thumb_w + self.px(16))
                    ty = ref_y + self.px(52) + (i // 2) * (thumb_h + self.px(10))
                    img.paste(thumb, (tx + (thumb_w - thumb.width) // 2, ty))
                except (OSError, ValueError):
                    continue
        return img

    def render(self, page: int) -> Image.Image:
        return self.page_one() if page == 1 else self.page_two()


class SongSheetApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("1510x970")
        self.root.minsize(1100, 720)
        self.state = json.loads(json.dumps(DEFAULTS))
        self.project_path: Path | None = None
        self.vars: dict[str, tk.StringVar] = {}
        self.text_widgets: dict[str, tk.Text] = {}
        self.page = 1
        self.preview_image: ImageTk.PhotoImage | None = None
        self.rendered: dict[int, Image.Image] = {}
        self.pending_render: str | None = None
        self.analysis_queue: queue.Queue[tuple[bool, Any]] = queue.Queue()
        self.playback_queue: queue.Queue[tuple[bool, Any]] = queue.Queue()
        self.playback_path: str | None = None
        self.playback_temp_path: str | None = None
        self.playback_wave: Any = None
        self.playback_stream: Any = None
        self.playback_rate = 44100
        self.playback_channels = 2
        self.playback_frames = 0
        self.playing = False
        self.current_position = 0.0
        self.playback_lock = threading.RLock()
        self.playhead_item: int | None = None
        self.playhead_label_item: int | None = None
        self.marker_drag_id: str | None = None
        self.selected_marker_id: str | None = None
        self._updating_slider = False
        self.audio_status = tk.StringVar(value="Načtěte zvukový soubor pro waveform a analýzu.")
        self._build_ui()
        self.root.after(200, self._poll_analysis)
        self.root.after(50, self._poll_transport)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.schedule_preview()

    def _build_ui(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        toolbar = ttk.Frame(self.root, padding=(8, 7))
        toolbar.pack(side="top", fill="x")
        buttons = [
            ("Nový", self.new_project), ("Otevřít", self.open_project), ("Uložit", self.save_project),
            ("Načíst audio", self.import_audio), ("Přidat referenci", self.add_reference),
            ("Export PDF", self.export_pdf), ("Export PNG", self.export_png),
        ]
        for label, command in buttons:
            ttk.Button(toolbar, text=label, command=command).pack(side="left", padx=(0, 6))
        ttk.Label(toolbar, textvariable=self.audio_status, anchor="e").pack(side="right", fill="x", expand=True, padx=8)

        split = ttk.Panedwindow(self.root, orient="horizontal")
        split.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        editor = ttk.Frame(split, width=485)
        preview = ttk.Frame(split)
        split.add(editor, weight=0)
        split.add(preview, weight=1)

        self.notebook = ttk.Notebook(editor)
        self.notebook.pack(fill="both", expand=True)
        self._build_metadata_tab()
        self._build_music_tab()
        self._build_production_tab()
        self._build_ld_tab()
        self._build_layout_tab()

        self.right_notebook = ttk.Notebook(preview)
        self.right_notebook.pack(fill="both", expand=True)
        print_tab = ttk.Frame(self.right_notebook)
        timeline_tab = ttk.Frame(self.right_notebook)
        self.right_notebook.add(print_tab, text="Tiskový náhled")
        self.right_notebook.add(timeline_tab, text="Audio a značky")

        preview_head = ttk.Frame(print_tab, padding=(8, 4))
        preview_head.pack(fill="x")
        ttk.Label(preview_head, text="NÁHLED TISKOVÉ STRÁNKY", font=("TkDefaultFont", 10, "bold")).pack(side="left")
        self.page_button = tk.IntVar(value=1)
        ttk.Radiobutton(preview_head, text="1 · Hudba", variable=self.page_button, value=1, command=self.change_page).pack(side="right", padx=4)
        ttk.Radiobutton(preview_head, text="2 · Produkce", variable=self.page_button, value=2, command=self.change_page).pack(side="right", padx=4)
        self.preview_canvas = tk.Canvas(print_tab, background="#DCE3E5", highlightthickness=0)
        self.preview_canvas.pack(fill="both", expand=True)
        self.preview_canvas.bind("<Configure>", lambda _e: self.show_preview())
        self._build_timeline_ui(timeline_tab)

    def _build_timeline_ui(self, parent: ttk.Frame) -> None:
        transport = ttk.Frame(parent, padding=(10, 9))
        transport.pack(fill="x")
        self.play_button = ttk.Button(transport, text="▶ Přehrát", command=self.toggle_playback)
        self.play_button.pack(side="left", padx=(0, 6))
        ttk.Button(transport, text="■ Stop", command=self.stop_playback).pack(side="left", padx=(0, 12))
        self.position_text = tk.StringVar(value="00:00:00:00 / 00:00:00:00")
        ttk.Label(transport, textvariable=self.position_text, width=27, anchor="w").pack(side="left")
        self.position_scale = ttk.Scale(transport, from_=0, to=1, orient="horizontal", command=self._on_position_scale)
        self.position_scale.pack(side="left", fill="x", expand=True, padx=(8, 0))
        self.position_scale.bind("<ButtonRelease-1>", self._on_position_release)
        self.instrument_summary_var = tk.StringVar(value="Nástrojové vrstvy se analyzují heuristicky; přesný instrument ověřte poslechem.")
        ttk.Label(parent, textvariable=self.instrument_summary_var, wraplength=820, justify="left", foreground="#6B5A32").pack(fill="x", padx=13, pady=(0, 7))

        self.timeline_canvas = tk.Canvas(parent, height=320, background="#16222A", highlightthickness=0)
        self.timeline_canvas.pack(fill="x", padx=12, pady=(0, 6))
        self.timeline_canvas.bind("<Configure>", lambda _e: self.draw_timeline())
        self.timeline_canvas.bind("<Button-1>", self._timeline_press)
        self.timeline_canvas.bind("<B1-Motion>", self._timeline_drag)
        self.timeline_canvas.bind("<ButtonRelease-1>", self._timeline_release)
        ttk.Label(parent, text="Klik waveformem pro posun playheadu. Přetáhněte svislou značku nebo dvojklikem upravte její buňku v tabulce.", foreground="#5F7078").pack(anchor="w", padx=14, pady=(0, 5))

        marker_bar = ttk.Frame(parent, padding=(10, 3))
        marker_bar.pack(fill="x")
        ttk.Label(marker_bar, text="EDITOVATELNÉ ZNAČKY", font=("TkDefaultFont", 9, "bold")).pack(side="left")
        self.instrument_filter_var = tk.StringVar(value="Všechny")
        ttk.Label(marker_bar, text="Filtr vrstvy:").pack(side="right", padx=(10, 4))
        self.instrument_filter = ttk.Combobox(marker_bar, textvariable=self.instrument_filter_var, state="readonly", width=21, values=INSTRUMENT_FILTERS)
        self.instrument_filter.pack(side="right")
        self.instrument_filter.bind("<<ComboboxSelected>>", self._instrument_filter_changed)
        ttk.Button(marker_bar, text="＋ Přidat značku", command=self.add_marker).pack(side="right", padx=(5, 0))
        ttk.Button(marker_bar, text="⚙ Značky z odhadu", command=self.generate_instrument_markers).pack(side="right", padx=(5, 0))
        ttk.Button(marker_bar, text="− Odebrat vybranou", command=self.remove_marker).pack(side="right")

        table_frame = ttk.Frame(parent, padding=(10, 0, 10, 10))
        table_frame.pack(fill="both", expand=True)
        columns = ("label", "time", "kind", "instrument")
        self.marker_tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=10, selectmode="browse")
        self.marker_tree.heading("label", text="Název značky")
        self.marker_tree.heading("time", text="Čas (HH:MM:SS:FF)")
        self.marker_tree.heading("kind", text="Typ")
        self.marker_tree.heading("instrument", text="Nástroj / vrstva")
        self.marker_tree.column("label", width=420, minwidth=160, anchor="w")
        self.marker_tree.column("time", width=180, minwidth=140, anchor="center")
        self.marker_tree.column("kind", width=130, minwidth=100, anchor="center")
        self.marker_tree.column("instrument", width=220, minwidth=150, anchor="center")
        tree_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.marker_tree.yview)
        self.marker_tree.configure(yscrollcommand=tree_scroll.set)
        self.marker_tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        self.marker_tree.bind("<<TreeviewSelect>>", self._marker_selected)
        self.marker_tree.bind("<Double-1>", self._edit_marker_cell)

    def _entry_row(self, parent: ttk.Frame, key: str, label: str, default: str = "") -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", padx=9, pady=4)
        ttk.Label(row, text=label, width=16, anchor="w").pack(side="left")
        var = tk.StringVar(value=default)
        self.vars[key] = var
        entry = ttk.Entry(row, textvariable=var)
        entry.pack(side="left", fill="x", expand=True)
        var.trace_add("write", lambda *_: self._entry_changed(key))

    def _entry_changed(self, key: str) -> None:
        self.schedule_preview()
        if key == "duration" and hasattr(self, "timeline_canvas"):
            self._update_scale_range()
            self.draw_timeline()

    def _text_panel(self, parent: ttk.Frame, key: str, label: str, height: int = 7) -> tk.Text:
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=8, pady=5)
        ttk.Label(frame, text=label, font=("TkDefaultFont", 9, "bold")).pack(anchor="w", pady=(0, 3))
        text = tk.Text(frame, height=height, wrap="word", undo=True, font=("TkDefaultFont", 9))
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        text.bind("<KeyRelease>", lambda _e: self.schedule_preview())
        self.text_widgets[key] = text
        return text

    def _build_metadata_tab(self) -> None:
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Skladba")
        for key, label in [("title", "Název skladby"), ("episode", "Díl"), ("artist", "Interpret"), ("performer", "Účinkující"), ("dance", "Tanec")]:
            self._entry_row(tab, f"meta_{key}", label)
        self._entry_row(tab, "duration", "Délka (HH:MM:SS:FF)")
        self._entry_row(tab, "bpm", "Tempo BPM (odhad)")
        ttk.Label(tab, text="BPM, takt a první doba vyžadují poslechovou kontrolu.", wraplength=430, foreground="#945F00").pack(fill="x", padx=12, pady=7)
        ttk.Label(tab, text="Projekt se zpracovává lokálně; audio se nikam neodesílá.", wraplength=430).pack(fill="x", padx=12, pady=(2, 9))

    def _build_music_tab(self) -> None:
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Hudební mapa")
        cue_text = self._text_panel(tab, "cues", "Kandidátní akcenty — synchronizováno s editovatelnou tabulkou značek", 12)
        cue_text.configure(state="disabled")
        self._text_panel(tab, "sections", "Energetická okna (10 s), nikoli ověřené hudební fráze", 10)
        ttk.Label(tab, text="Časové značky se tisknou v HH:MM:SS:FF při 25 fps.", foreground="#5F7078").pack(anchor="w", padx=10, pady=5)

    def _build_production_tab(self) -> None:
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Produkce")
        ttk.Label(tab, text="Zapište nebo vložte poznámky z produkčního zdroje. Text se tiskne samostatně od návrhů LD.", wraplength=440, justify="left").pack(fill="x", padx=9, pady=8)
        canvas = tk.Canvas(tab, highlightthickness=0)
        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw", width=435)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        for key, label in PRODUCTION_FIELDS:
            self._text_panel(inner, f"prod_{key}", label, 4)

    def _build_ld_tab(self) -> None:
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Návrhy LD")
        ttk.Label(tab, text="Vlastní doporučení asistenta / LD. Tato část je v PDF barevně oddělena od produkčního zadání.", wraplength=440, justify="left").pack(fill="x", padx=9, pady=8)
        self._text_panel(tab, "ld_proposals", "Návrhy, přechody a body k ověření na zkoušce", 20)

    def _build_layout_tab(self) -> None:
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Vzhled")
        self.accent_label = tk.StringVar(value="Tyrkysová")
        ttk.Label(tab, text="Barva zvýraznění").pack(anchor="w", padx=12, pady=(16, 4))
        self.accent_combo = ttk.Combobox(tab, textvariable=self.accent_label, state="readonly", values=["Tyrkysová", "Modrá", "Fialová", "Červená", "Zlatá"])
        self.accent_combo.pack(fill="x", padx=12)
        self.accent_combo.bind("<<ComboboxSelected>>", self.change_accent)
        self.dark_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(tab, text="Tmavé tiskové pozadí", variable=self.dark_var, command=self.schedule_preview).pack(anchor="w", padx=12, pady=12)
        self.wave_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(tab, text="Zobrazit waveform", variable=self.wave_var, command=self.schedule_preview).pack(anchor="w", padx=12, pady=3)
        self.refs_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(tab, text="Zobrazit vizuální reference", variable=self.refs_var, command=self.schedule_preview).pack(anchor="w", padx=12, pady=3)
        ttk.Button(tab, text="Vlastní barva…", command=self.pick_color).pack(anchor="w", padx=12, pady=10)
        ttk.Button(tab, text="Odebrat poslední referenci", command=self.remove_reference).pack(anchor="w", padx=12, pady=2)
        ttk.Label(tab, text="Náhled se obnoví automaticky. Export používá stránku A4 na šířku.", wraplength=430, justify="left").pack(fill="x", padx=12, pady=10)

    def change_accent(self, _event: Any = None) -> None:
        colors = {"Tyrkysová": "#16A9A0", "Modrá": "#3A78C2", "Fialová": "#8056B3", "Červená": "#C74645", "Zlatá": "#C48A21"}
        self.state["accent"] = colors.get(self.accent_label.get(), "#16A9A0")
        self.schedule_preview()

    def pick_color(self) -> None:
        color = colorchooser.askcolor(self.state.get("accent", "#16A9A0"), title="Barva zvýraznění")[1]
        if color:
            self.state["accent"] = color
            self.accent_label.set("Vlastní barva")
            self.schedule_preview()

    def collect_state(self) -> dict[str, Any]:
        state = json.loads(json.dumps(self.state))
        for key in ["title", "episode", "artist", "performer", "dance"]:
            state["metadata"][key] = self.vars[f"meta_{key}"].get().strip()
        duration = self.vars["duration"].get().strip()
        # Accept display timecode or raw seconds.
        if duration.count(":") == 3:
            try:
                hh, mm, ss, ff = map(int, duration.split(":"))
                state["duration"] = hh * 3600 + mm * 60 + ss + ff / FPS
            except ValueError:
                state["duration"] = duration
        else:
            try:
                state["duration"] = float(duration)
            except ValueError:
                state["duration"] = duration
        state["bpm"] = self.vars["bpm"].get().strip()
        for key, _label in PRODUCTION_FIELDS:
            state["production"][key] = self.text_widgets[f"prod_{key}"].get("1.0", "end-1c").strip()
        for key in ["cues", "sections", "ld_proposals"]:
            state[key] = self.text_widgets[key].get("1.0", "end-1c").strip()
        state["dark"] = self.dark_var.get()
        state["show_waveform"] = self.wave_var.get()
        state["show_references"] = self.refs_var.get()
        return state

    def schedule_preview(self) -> None:
        if not hasattr(self, "preview_canvas"):
            return
        if self.pending_render:
            self.root.after_cancel(self.pending_render)
        self.pending_render = self.root.after(650, self.render_preview)

    def render_preview(self) -> None:
        self.pending_render = None
        try:
            self.state = self.collect_state()
            self.rendered = {1: PageRenderer(self.state).render(1), 2: PageRenderer(self.state).render(2)}
            self.show_preview()
        except (tk.TclError, OSError, ValueError) as exc:
            self.audio_status.set(f"Náhled nelze vykreslit: {exc}")

    def show_preview(self) -> None:
        if not self.rendered:
            return
        page = self.page_button.get() if hasattr(self, "page_button") else 1
        image = self.rendered.get(page)
        if image is None:
            return
        cw, ch = max(200, self.preview_canvas.winfo_width() - 20), max(200, self.preview_canvas.winfo_height() - 20)
        ratio = min(cw / image.width, ch / image.height)
        resized = image.resize((int(image.width * ratio), int(image.height * ratio)), Image.Resampling.LANCZOS)
        self.preview_image = ImageTk.PhotoImage(resized)
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(cw // 2 + 10, ch // 2 + 10, image=self.preview_image, anchor="center")

    def change_page(self) -> None:
        self.page = self.page_button.get()
        self.show_preview()

    def import_audio(self) -> None:
        path = filedialog.askopenfilename(title="Vyberte zvukový soubor", filetypes=[
            ("Zvuk", "*.wav *.mp3 *.flac *.m4a *.aac *.ogg *.aiff *.aif"), ("Všechny soubory", "*.*")])
        if not path:
            return
        self._close_playback()
        self.state["audio_path"] = path
        self.state["waveform"] = []
        self.state["markers"] = []
        self.state["duration"] = ""
        self.state["bpm"] = ""
        self.state["cues"] = ""
        self.state["sections"] = ""
        self.state["instrument_summary"] = ""
        self.state["instrument_summary_short"] = ""
        self.state["instrument_events"] = []
        self.current_position = 0.0
        self.selected_marker_id = None
        self.instrument_summary_var.set("Analyzuji možné nástrojové vrstvy…")
        self.instrument_filter_var.set("Všechny")
        self.vars["duration"].set("")
        self.vars["bpm"].set("")
        self._refresh_marker_table()
        self._refresh_cue_text()
        self.text_widgets["sections"].delete("1.0", "end")
        if not self.vars["title"].get().strip():
            self.vars["title"].set(Path(path).stem)
        self.audio_status.set(f"Analyzuji {Path(path).name}…")
        self.draw_timeline()
        threading.Thread(target=self._analyze_worker, args=(path,), daemon=True).start()

    def duration_seconds(self) -> float:
        raw = self.vars["duration"].get().strip() if "duration" in self.vars else ""
        try:
            return self.parse_time_value(raw)
        except (ValueError, TypeError):
            try:
                return max(0.0, float(self.state.get("duration", 0) or 0))
            except (ValueError, TypeError):
                return 0.0

    @staticmethod
    def parse_time_value(value: str) -> float:
        value = value.strip()
        if value.count(":") == 3:
            hh, mm, ss, ff = (int(part) for part in value.split(":"))
            if hh < 0 or not 0 <= mm < 60 or not 0 <= ss < 60 or not 0 <= ff < FPS:
                raise ValueError("Použijte HH:MM:SS:FF a snímek 00 až 24.")
            return hh * 3600 + mm * 60 + ss + ff / FPS
        seconds = float(value)
        if seconds < 0:
            raise ValueError("Čas nesmí být záporný.")
        return round(seconds * FPS) / FPS

    def toggle_playback(self) -> None:
        if self.playing:
            self.playing = False
            self.play_button.configure(text="▶ Přehrát")
            return
        path = self.state.get("audio_path", "")
        if not path or not Path(path).exists():
            messagebox.showinfo("Přehrávání", "Nejprve načtěte audio nebo otevřete projekt, který ho obsahuje.")
            return
        if self.playback_wave is not None and self.playback_path == path and self.playback_stream is not None:
            if self.current_position >= self.playback_frames / self.playback_rate:
                self._seek_to(0.0)
            self.playing = True
            self.play_button.configure(text="❚❚ Pozastavit")
            return
        if self.playback_path == path:
            self.audio_status.set("Připravuji audio pro přehrávání…")
            return
        self._close_playback()
        self.playback_path = path
        self.play_button.configure(state="disabled")
        self.audio_status.set("Připravuji audio pro přehrávání…")
        threading.Thread(target=self._prepare_playback, args=(path,), daemon=True).start()

    def _prepare_playback(self, path: str) -> None:
        executable = ffmpeg_executable()
        if not executable:
            self.playback_queue.put((False, (path, "Dekodér ffmpeg není dostupný.")))
            return
        temp = tempfile.NamedTemporaryFile(prefix="stardance_", suffix=".wav", delete=False)
        temp_path = temp.name
        temp.close()
        command = [executable, "-y", "-v", "error", "-i", path, "-vn", "-ac", str(self.playback_channels), "-ar", str(self.playback_rate), "-c:a", "pcm_s16le", "-f", "wav", temp_path]
        try:
            result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False)
        except OSError as exc:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            self.playback_queue.put((False, (path, str(exc))))
            return
        if result.returncode != 0:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            lines = result.stderr.decode("utf-8", "replace").strip().splitlines()
            self.playback_queue.put((False, (path, lines[-1] if lines else "Audio se nepodařilo dekódovat.")))
            return
        self.playback_queue.put((True, (path, temp_path)))

    def _audio_callback(self, outdata: np.ndarray, frames: int, _time_info: Any, _status: Any) -> None:
        outdata.fill(0)
        if not self.playing or self.playback_wave is None:
            return
        try:
            with self.playback_lock:
                data = self.playback_wave.readframes(frames)
                count = len(data) // (2 * self.playback_channels)
                if count:
                    outdata[:count, :] = np.frombuffer(data, dtype="<i2").reshape(-1, self.playback_channels)
                self.current_position = self.playback_wave.tell() / self.playback_rate
                if count < frames:
                    self.playing = False
                    self.current_position = self.playback_frames / self.playback_rate
        except (OSError, ValueError):
            self.playing = False

    def _poll_analysis(self) -> None:
        try:
            while True:
                ok, payload = self.analysis_queue.get_nowait()
                path, result = payload
                if path != self.state.get("audio_path"):
                    continue
                if ok:
                    self.state.update(result)
                    self.vars["duration"].set(display_time(result["duration"]))
                    self.vars["bpm"].set(str(result["bpm"]) if result["bpm"] else "")
                    self.state["bpm_confidence"] = result["bpm_confidence"]
                    self.instrument_summary_var.set(result.get("instrument_summary", "Odhad nástrojových vrstev není k dispozici."))
                    self._refresh_marker_table()
                    self._refresh_cue_text()
                    self.text_widgets["sections"].delete("1.0", "end")
                    self.text_widgets["sections"].insert("1.0", result["sections"])
                    self.audio_status.set(f"Načteno: {Path(path).name} · {display_time(result['duration'])} · BPM {result['bpm'] or '—'} ({result['bpm_confidence']} jistota, odhad)")
                    self._update_scale_range()
                    self.draw_timeline()
                    self.schedule_preview()
                else:
                    self.audio_status.set("Analýza se nezdařila")
                    messagebox.showerror("Audio analýza", result)
        except queue.Empty:
            pass
        self._poll_playback_ready()
        self.root.after(200, self._poll_analysis)

    def _poll_playback_ready(self) -> None:
        try:
            while True:
                ok, payload = self.playback_queue.get_nowait()
                path, result = payload
                if path != self.state.get("audio_path"):
                    if ok:
                        try:
                            os.unlink(result)
                        except OSError:
                            pass
                    continue
                if not ok:
                    self.playback_path = None
                    self.play_button.configure(state="normal")
                    self.audio_status.set("Přehrávání se nezdařilo")
                    messagebox.showerror("Přehrávání", result)
                    continue
                temp_path = result
                try:
                    import sounddevice as sd  # type: ignore
                    self.playback_temp_path = temp_path
                    with self.playback_lock:
                        self.playback_wave = wave.open(temp_path, "rb")
                        self.playback_frames = self.playback_wave.getnframes()
                    self.playback_path = path
                    self.playback_stream = sd.OutputStream(
                        samplerate=self.playback_rate, channels=self.playback_channels, dtype="int16", blocksize=1024, callback=self._audio_callback
                    )
                    self.playback_stream.start()
                    self._update_scale_range()
                    self._seek_to(min(self.current_position, self.playback_frames / self.playback_rate))
                    self.playing = True
                    self.play_button.configure(state="normal", text="❚❚ Pozastavit")
                    self.audio_status.set(f"Přehrávání: {Path(path).name}")
                except Exception as exc:
                    self._close_playback()
                    self.play_button.configure(state="normal", text="▶ Přehrát")
                    messagebox.showerror("Přehrávání", f"Audio výstup nelze otevřít: {exc}")
        except queue.Empty:
            pass

    def _poll_transport(self) -> None:
        duration = self.duration_seconds()
        self.position_text.set(f"{tc25(self.current_position)} / {tc25(duration)}")
        self._updating_slider = True
        self.position_scale.set(self.current_position)
        self._updating_slider = False
        self._move_playhead()
        if not self.playing and self.play_button.winfo_exists():
            self.play_button.configure(text="▶ Přehrát")
        self.root.after(50, self._poll_transport)

    def _close_playback(self) -> None:
        self.playing = False
        stream, self.playback_stream = self.playback_stream, None
        if stream is not None:
            try:
                stream.stop()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass
        with self.playback_lock:
            if self.playback_wave is not None:
                try:
                    self.playback_wave.close()
                except Exception:
                    pass
                self.playback_wave = None
        temp, self.playback_temp_path = self.playback_temp_path, None
        if temp:
            try:
                os.unlink(temp)
            except OSError:
                pass
        self.playback_path = None
        self.playback_frames = 0
        if hasattr(self, "play_button") and self.play_button.winfo_exists():
            self.play_button.configure(state="normal", text="▶ Přehrát")

    def stop_playback(self) -> None:
        self.playing = False
        self._seek_to(0.0)
        self.play_button.configure(text="▶ Přehrát")

    def _seek_to(self, seconds: float) -> None:
        duration = self.playback_frames / self.playback_rate if self.playback_frames else self.duration_seconds()
        self.current_position = max(0.0, min(float(seconds), duration))
        if self.playback_wave is not None:
            with self.playback_lock:
                self.playback_wave.setpos(min(self.playback_frames, int(round(self.current_position * self.playback_rate))))
        self._move_playhead()
        self.position_text.set(f"{tc25(self.current_position)} / {tc25(duration)}")

    def _update_scale_range(self) -> None:
        duration = self.playback_frames / self.playback_rate if self.playback_frames else self.duration_seconds()
        self.position_scale.configure(to=max(1.0, duration))

    def _on_position_scale(self, value: str) -> None:
        if self._updating_slider:
            return
        self.current_position = float(value)
        self.position_text.set(f"{tc25(self.current_position)} / {tc25(self.duration_seconds())}")
        self._move_playhead()

    def _on_position_release(self, _event: Any = None) -> None:
        self._seek_to(float(self.position_scale.get()))

    def draw_timeline(self) -> None:
        if not hasattr(self, "timeline_canvas"):
            return
        canvas = self.timeline_canvas
        canvas.delete("all")
        self.playhead_item = None
        self.playhead_label_item = None
        width = max(300, canvas.winfo_width())
        height = max(220, canvas.winfo_height())
        left, right = 42, width - 28
        top, bottom = 38, height - 44
        self.timeline_plot = (left, right, top, bottom)
        center = (top + bottom) // 2
        duration = self.duration_seconds()
        canvas.create_rectangle(left, top, right, bottom, fill="#1D2C35", outline="#52636C")
        values = self.state.get("waveform", [])
        if values:
            span = max(1, right - left)
            upper: list[float] = []
            lower: list[float] = []
            values_array = np.asarray(values, dtype=float)
            for column in range(span + 1):
                i0 = int(column * len(values_array) / (span + 1))
                i1 = max(i0 + 1, int((column + 1) * len(values_array) / (span + 1)))
                peak = float(values_array[i0:min(len(values_array), i1)].max()) if len(values_array) else 0.0
                x = left + column
                amp = max(1, int(peak * (bottom - top) * 0.44))
                upper.extend((x, center - amp))
                lower.extend((x, center + amp))
            canvas.create_polygon(*(upper + list(reversed(lower))), fill="#23B8AA", outline="")
        else:
            canvas.create_text((left + right) // 2, center, text="Po načtení audia se zde zobrazí waveform", fill="#A6B4BB", font=("TkDefaultFont", 12))

        if duration > 0:
            tick_count = min(12, max(4, int(duration / 10) + 1))
            for i in range(tick_count + 1):
                x = left + int((right - left) * i / tick_count)
                second = duration * i / tick_count
                canvas.create_line(x, bottom + 1, x, bottom + 8, fill="#91A1A8")
                canvas.create_text(x, bottom + 22, text=tc25(second), fill="#A6B4BB", font=("TkDefaultFont", 8))

        self.marker_canvas_items: dict[str, tuple[int, int]] = {}
        marker_colors = {"Akcent": "#F0B94B", "Cue": "#E26D5A", "Sekce": "#7EA6F8", "Nástroj": "#C38CE4", "Jiné": "#C38CE4"}
        for i, marker in enumerate(self._visible_markers()):
            if duration <= 0:
                continue
            marker_time = max(0.0, min(duration, float(marker.get("time", 0))))
            x = left + int((right - left) * marker_time / duration)
            color = marker_colors.get(marker.get("kind", "Cue"), "#F0B94B")
            line = canvas.create_line(x, top, x, bottom, fill=color, width=3 if marker.get("id") == self.selected_marker_id else 2)
            text = canvas.create_text(min(right - 5, max(left + 5, x + 5)), top + 10 + (i % 4) * 17,
                                      text=str(marker.get("label", "Značka"))[:24], anchor="nw", fill=color, font=("TkDefaultFont", 8, "bold"))
            self.marker_canvas_items[str(marker.get("id"))] = (line, text)
        self.playhead_item = canvas.create_line(left, top, left, bottom, fill="#FF5D6C", width=2)
        self.playhead_label_item = canvas.create_text(left + 4, bottom - 4, text=tc25(self.current_position), anchor="sw", fill="#FF8791", font=("TkDefaultFont", 8, "bold"))
        self._move_playhead()

    def _time_at_canvas_x(self, x: int) -> float:
        duration = self.duration_seconds()
        if duration <= 0:
            return 0.0
        left, right, _top, _bottom = self.timeline_plot
        ratio = max(0.0, min(1.0, (x - left) / max(1, right - left)))
        return duration * ratio

    def _move_playhead(self) -> None:
        if not getattr(self, "playhead_item", None):
            return
        left, right, top, bottom = self.timeline_plot
        duration = self.duration_seconds()
        ratio = 0.0 if duration <= 0 else max(0.0, min(1.0, self.current_position / duration))
        x = left + int((right - left) * ratio)
        self.timeline_canvas.coords(self.playhead_item, x, top, x, bottom)
        if self.playhead_label_item:
            self.timeline_canvas.coords(self.playhead_label_item, min(right - 2, x + 4), bottom - 4)
            self.timeline_canvas.itemconfigure(self.playhead_label_item, text=tc25(self.current_position))

    def _timeline_press(self, event: Any) -> None:
        time = self._time_at_canvas_x(event.x)
        duration = self.duration_seconds()
        if duration > 0:
            left, right, _top, _bottom = self.timeline_plot
            for marker in self._visible_markers():
                marker_x = left + int((right - left) * float(marker.get("time", 0)) / duration)
                marker_id = str(marker["id"])
                line_id, text_id = self.marker_canvas_items.get(marker_id, (None, None))
                label_box = self.timeline_canvas.bbox(text_id) if text_id else None
                on_label = bool(label_box and label_box[0] <= event.x <= label_box[2] and label_box[1] <= event.y <= label_box[3])
                if abs(marker_x - event.x) <= 8 or on_label:
                    self.marker_drag_id = marker_id
                    self.selected_marker_id = self.marker_drag_id
                    self.current_position = float(marker.get("time", 0))
                    self._refresh_marker_table()
                    self._seek_to(self.current_position)
                    self.draw_timeline()
                    return
        self.marker_drag_id = None
        self._seek_to(time)

    def _timeline_drag(self, event: Any) -> None:
        if self.marker_drag_id:
            marker = next((m for m in self.state.get("markers", []) if str(m.get("id")) == self.marker_drag_id), None)
            if marker is not None:
                marker["time"] = round(self._time_at_canvas_x(event.x) * FPS) / FPS
                self.current_position = float(marker["time"])
                self._refresh_marker_table()
                self._refresh_cue_text()
                self.draw_timeline()
                self.schedule_preview()
        else:
            self._seek_to(self._time_at_canvas_x(event.x))

    def _timeline_release(self, _event: Any) -> None:
        self.marker_drag_id = None
        self._seek_to(self.current_position)

    def add_marker(self) -> None:
        instrument = self.instrument_filter_var.get()
        if instrument in {"Všechny", "Bez přiřazení"}:
            instrument = ""
        marker = {"id": uuid.uuid4().hex, "label": "Nová značka", "time": round(self.current_position * FPS) / FPS, "kind": "Cue", "instrument": instrument}
        self.state.setdefault("markers", []).append(marker)
        self.selected_marker_id = marker["id"]
        self._refresh_marker_table()
        self._refresh_cue_text()
        self.draw_timeline()
        self.schedule_preview()

    def _visible_markers(self) -> list[dict[str, Any]]:
        selected_filter = self.instrument_filter_var.get() if hasattr(self, "instrument_filter_var") else "Všechny"
        markers = self.state.get("markers", [])
        if selected_filter == "Všechny":
            return markers
        if selected_filter == "Bez přiřazení":
            return [marker for marker in markers if not marker.get("instrument")]
        return [marker for marker in markers if marker.get("instrument") == selected_filter]

    def _instrument_filter_changed(self, _event: Any = None) -> None:
        visible_ids = {str(marker.get("id")) for marker in self._visible_markers()}
        if self.selected_marker_id not in visible_ids:
            self.selected_marker_id = None
        self._refresh_marker_table()
        self.draw_timeline()

    def generate_instrument_markers(self) -> None:
        events = list(self.state.get("instrument_events", []))
        if not events:
            messagebox.showinfo("Značky z nástrojů", "Nejprve načtěte audio a nechte proběhnout analýzu nástrojových vrstev.")
            return
        selected_filter = self.instrument_filter_var.get()
        if selected_filter == "Bez přiřazení":
            events = []
        elif selected_filter != "Všechny":
            events = [event for event in events if event.get("instrument") == selected_filter]
        existing = self.state.setdefault("markers", [])
        added = 0
        for event in events:
            event_time = round(float(event.get("time", 0)) * FPS) / FPS
            instrument = str(event.get("instrument", ""))
            duplicate = any(
                marker.get("instrument") == instrument and abs(float(marker.get("time", 0)) - event_time) < 0.25
                for marker in existing
            )
            if duplicate:
                continue
            existing.append({
                "id": uuid.uuid4().hex,
                "label": str(event.get("label", "Možná nástrojová událost")),
                "time": event_time,
                "kind": "Nástroj",
                "instrument": instrument,
            })
            added += 1
        self._refresh_marker_table()
        self._refresh_cue_text()
        self.draw_timeline()
        self.schedule_preview()
        self.audio_status.set(f"Přidáno {added} možných značek nástrojových vrstev; ověřte je poslechem.")

    def remove_marker(self) -> None:
        selected = self.marker_tree.selection()
        marker_id = selected[0] if selected else self.selected_marker_id
        if not marker_id:
            return
        self.state["markers"] = [m for m in self.state.get("markers", []) if str(m.get("id")) != marker_id]
        self.selected_marker_id = None
        self._refresh_marker_table()
        self._refresh_cue_text()
        self.draw_timeline()
        self.schedule_preview()

    def _refresh_marker_table(self) -> None:
        if not hasattr(self, "marker_tree"):
            return
        selected = self.selected_marker_id
        visible = sorted(self._visible_markers(), key=lambda item: float(item.get("time", 0)))
        visible_ids = {str(marker.get("id", "")) for marker in visible}
        if selected and selected not in visible_ids:
            selected = None
            self.selected_marker_id = None
        self._updating_marker_tree = True
        self.marker_tree.delete(*self.marker_tree.get_children())
        for marker in visible:
            marker_id = str(marker.setdefault("id", uuid.uuid4().hex))
            self.marker_tree.insert("", "end", iid=marker_id, values=(marker.get("label", ""), tc25(float(marker.get("time", 0))), marker.get("kind", "Cue"), marker.get("instrument", "") or "Bez přiřazení"))
        if selected and self.marker_tree.exists(selected):
            self.marker_tree.selection_set(selected)
            self.marker_tree.see(selected)
        self._updating_marker_tree = False

    def _refresh_cue_text(self) -> None:
        lines = [f"{tc25(float(marker.get('time', 0)))}  [{marker.get('kind', 'Cue')} · {marker.get('instrument') or 'bez přiřazení'}] {marker.get('label', '')}" for marker in sorted(self.state.get("markers", []), key=lambda item: float(item.get("time", 0)))]
        self.state["cues"] = "\n".join(lines)
        if hasattr(self, "text_widgets") and "cues" in self.text_widgets:
            self._replace_text("cues", self.state["cues"])

    def _marker_selected(self, _event: Any = None) -> None:
        if getattr(self, "_updating_marker_tree", False):
            return
        selected = self.marker_tree.selection()
        if not selected:
            return
        marker_id = selected[0]
        self.selected_marker_id = marker_id
        marker = next((m for m in self.state.get("markers", []) if str(m.get("id")) == marker_id), None)
        if marker:
            self._seek_to(float(marker.get("time", 0)))
            self.draw_timeline()

    def _edit_marker_cell(self, event: Any) -> None:
        item = self.marker_tree.identify_row(event.y)
        column = self.marker_tree.identify_column(event.x)
        if not item or column not in {"#1", "#2", "#3", "#4"}:
            return
        box = self.marker_tree.bbox(item, column)
        if not box:
            return
        marker = next((m for m in self.state.get("markers", []) if str(m.get("id")) == item), None)
        if marker is None:
            return
        x, y, width, height = box
        if column in {"#3", "#4"}:
            editor: Any = ttk.Combobox(self.marker_tree, state="readonly")
            value_key = "kind" if column == "#3" else "instrument"
            values = ("Cue", "Akcent", "Sekce", "Nástroj", "Jiné") if column == "#3" else INSTRUMENT_FILTERS[1:]
            editor.configure(values=values)
            current_value = marker.get(value_key, "Cue")
            editor.set(current_value or ("Bez přiřazení" if column == "#4" else "Cue"))
        else:
            editor = ttk.Entry(self.marker_tree)
            editor.insert(0, tc25(float(marker.get("time", 0))) if column == "#2" else str(marker.get("label", "")))
        editor.place(x=x, y=y, width=width, height=height)
        editor.focus_set()
        done = {"value": False}

        def commit(_event: Any = None) -> None:
            if done["value"]:
                return
            done["value"] = True
            value = editor.get()
            try:
                if column == "#1":
                    marker["label"] = value
                elif column == "#2":
                    marker_time = self.parse_time_value(value)
                    duration = self.duration_seconds()
                    if duration and marker_time > duration:
                        raise ValueError("Značka musí být uvnitř délky skladby.")
                    marker["time"] = marker_time
                elif column == "#3":
                    marker["kind"] = value
                else:
                    marker["instrument"] = "" if value == "Bez přiřazení" else value
            except ValueError as exc:
                done["value"] = False
                messagebox.showerror("Značka", str(exc))
                editor.focus_set()
                return
            editor.destroy()
            self.selected_marker_id = item
            self._refresh_marker_table()
            self._refresh_cue_text()
            self.draw_timeline()
            self.schedule_preview()

        editor.bind("<Return>", commit)
        editor.bind("<FocusOut>", commit)

        def cancel(_event: Any = None) -> None:
            done["value"] = True
            editor.destroy()

        editor.bind("<Escape>", cancel)

    def _analyze_worker(self, path: str) -> None:
        try:
            self.analysis_queue.put((True, (path, estimate_audio(path))))
        except Exception as exc:
            self.analysis_queue.put((False, (path, str(exc))))

    def add_reference(self) -> None:
        paths = filedialog.askopenfilenames(title="Vyberte obrázky pro vizuální reference", filetypes=[("Obrázky", "*.png *.jpg *.jpeg *.webp *.bmp"), ("Všechny soubory", "*.*")])
        if paths:
            self.state["references"] = list(self.state.get("references", [])) + list(paths)
            self.schedule_preview()

    def remove_reference(self) -> None:
        references = list(self.state.get("references", []))
        if references:
            references.pop()
            self.state["references"] = references
            self.schedule_preview()

    def _project_payload(self, destination: Path) -> dict[str, Any]:
        state = self.collect_state()
        assets_dir = destination.with_suffix("").with_name(destination.stem + "_assets")
        refs_dir = assets_dir / "references"
        audio_dir = assets_dir / "audio"
        refs_dir.mkdir(parents=True, exist_ok=True)
        if state.get("audio_path") and Path(state["audio_path"]).exists():
            audio_dir.mkdir(parents=True, exist_ok=True)
            src = Path(state["audio_path"])
            dest = audio_dir / src.name
            if src.resolve() != dest.resolve():
                shutil.copy2(src, dest)
            state["audio_path"] = str(Path(destination.stem + "_assets") / "audio" / src.name)
        refs_relative = []
        for index, raw in enumerate(state.get("references", []), start=1):
            src = Path(raw)
            if not src.exists():
                continue
            base_name = src.name
            while len(base_name) > 3 and base_name[:2].isdigit() and base_name[2] == "_":
                base_name = base_name[3:]
            target = refs_dir / f"{index:02d}_{base_name}"
            if src.resolve() != target.resolve():
                shutil.copy2(src, target)
            refs_relative.append(str(Path(destination.stem + "_assets") / "references" / target.name))
        state["references"] = refs_relative
        return {"format": "stardance-songsheet", "version": 1, "state": state}

    def save_project(self) -> None:
        if self.project_path is None:
            path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("SongSheet projekt", "*.json")], title="Uložit projekt jako")
            if not path:
                return
            self.project_path = Path(path)
        try:
            payload = self._project_payload(self.project_path)
            self.project_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self.audio_status.set(f"Uloženo: {self.project_path.name}")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Uložení projektu", str(exc))

    def open_project(self) -> None:
        path = filedialog.askopenfilename(title="Otevřít SongSheet projekt", filetypes=[("SongSheet projekt", "*.json"), ("JSON", "*.json")])
        if not path:
            return
        try:
            document = json.loads(Path(path).read_text(encoding="utf-8"))
            state = document.get("state", document)
            state = {**json.loads(json.dumps(DEFAULTS)), **state}
            state["metadata"] = {**DEFAULTS["metadata"], **state.get("metadata", {})}
            state["production"] = {**DEFAULTS["production"], **state.get("production", {})}
            normalized = []
            for item in state.get("markers", []) or []:
                try:
                    marker_time = self.parse_time_value(str(item.get("time", 0))) if isinstance(item.get("time"), str) else float(item.get("time", 0))
                except (ValueError, TypeError):
                    continue
                normalized.append({
                    "id": str(item.get("id") or uuid.uuid4().hex),
                    "label": str(item.get("label", "Značka")),
                    "time": round(max(0.0, marker_time) * FPS) / FPS,
                    "kind": str(item.get("kind", "Cue")),
                    "instrument": str(item.get("instrument", "") or ""),
                })
            if not normalized and state.get("cues"):
                for line in state["cues"].splitlines():
                    match = re.match(r"^\s*(\d{2}:\d{2}:\d{2}:\d{2})\s+(.*)$", line)
                    if match:
                        try:
                            marker_time = self.parse_time_value(match.group(1))
                        except ValueError:
                            continue
                        label = match.group(2).split(" — ", 1)[0]
                        normalized.append({"id": uuid.uuid4().hex, "label": label or "Dřívější značka", "time": marker_time, "kind": "Akcent"})
            state["markers"] = normalized
            base = Path(path).parent
            for key in ["audio_path"]:
                p = Path(state.get(key, "")) if state.get(key) else None
                if p and not p.is_absolute():
                    state[key] = str((base / p).resolve())
            state["references"] = [str((base / p).resolve()) if not Path(p).is_absolute() else p for p in state.get("references", [])]
            self._close_playback()
            self.current_position = 0.0
            self.state = state
            self.project_path = Path(path)
            for key, var in self.vars.items():
                if key.startswith("meta_"):
                    var.set(state["metadata"].get(key[5:], ""))
                elif key == "duration":
                    dur = state.get("duration", "")
                    var.set(display_time(dur) if isinstance(dur, (int, float)) else str(dur))
                elif key == "bpm":
                    var.set(str(state.get("bpm", "")))
            for key, _label in PRODUCTION_FIELDS:
                self._replace_text(f"prod_{key}", state["production"].get(key, ""))
            for key in ["cues", "sections", "ld_proposals"]:
                self._replace_text(key, state.get(key, ""))
            self.selected_marker_id = None
            self.instrument_filter_var.set("Všechny")
            self.instrument_summary_var.set(state.get("instrument_summary", ""))
            self._refresh_marker_table()
            self._refresh_cue_text()
            self.dark_var.set(bool(state.get("dark")))
            self.wave_var.set(bool(state.get("show_waveform", True)))
            self.refs_var.set(bool(state.get("show_references", True)))
            color_names = {"#16A9A0": "Tyrkysová", "#3A78C2": "Modrá", "#8056B3": "Fialová", "#C74645": "Červená", "#C48A21": "Zlatá"}
            self.accent_label.set(color_names.get(str(state.get("accent", "")).upper(), "Vlastní barva"))
            audio_path = state.get("audio_path", "")
            self.audio_status.set(f"Otevřeno: {Path(path).name}" + (f" · audio {Path(audio_path).name}" if audio_path else ""))
            self._update_scale_range()
            self.draw_timeline()
            self.schedule_preview()
        except (OSError, ValueError, TypeError) as exc:
            messagebox.showerror("Otevření projektu", str(exc))

    def _replace_text(self, key: str, value: str) -> None:
        widget = self.text_widgets[key]
        if key == "cues":
            widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        if key == "cues":
            widget.configure(state="disabled")

    def _export_images(self, path: Path) -> tuple[Image.Image, Image.Image]:
        state = self.collect_state()
        if isinstance(state.get("duration"), str) and not state["duration"].strip():
            state["duration"] = ""
        renderer = PageRenderer(state, quality="print")
        return renderer.render(1), renderer.render(2)

    def export_pdf(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")], title="Exportovat PDF")
        if not path:
            return
        try:
            pages = self._export_images(Path(path))
            c = pdf_canvas.Canvas(path, pagesize=landscape(A4), pageCompression=1)
            width, height = landscape(A4)
            for image in pages:
                c.drawImage(ImageReaderCompat(image), 0, 0, width=width, height=height)
                c.showPage()
            c.save()
            self.audio_status.set(f"PDF exportováno: {Path(path).name}")
        except Exception as exc:
            messagebox.showerror("Export PDF", str(exc))

    def export_png(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png")], title="Exportovat stránku 1 jako PNG")
        if not path:
            return
        try:
            pages = self._export_images(Path(path))
            target = Path(path)
            pages[0].save(target, dpi=(210, 210))
            second = target.with_name(target.stem + "_strana_2.png")
            pages[1].save(second, dpi=(210, 210))
            self.audio_status.set(f"PNG exportováno: {target.name} a {second.name}")
        except Exception as exc:
            messagebox.showerror("Export PNG", str(exc))

    def new_project(self) -> None:
        if not messagebox.askyesno("Nový projekt", "Začít nový song sheet? Neuložené změny budou ztraceny."):
            return
        self.state = json.loads(json.dumps(DEFAULTS))
        self._close_playback()
        self.current_position = 0.0
        self.instrument_summary_var.set("Nástrojové vrstvy se analyzují heuristicky; přesný instrument ověřte poslechem.")
        self.instrument_filter_var.set("Všechny")
        self.project_path = None
        for key in ["title", "episode", "artist", "performer", "dance"]:
            self.vars[f"meta_{key}"].set("")
        self.vars["duration"].set("")
        self.vars["bpm"].set("")
        for key, _label in PRODUCTION_FIELDS:
            self._replace_text(f"prod_{key}", "")
        for key in ["cues", "sections", "ld_proposals"]:
            self._replace_text(key, "")
        self.selected_marker_id = None
        self._refresh_marker_table()
        self._refresh_cue_text()
        self.dark_var.set(False)
        self.wave_var.set(True)
        self.refs_var.set(True)
        self.state["accent"] = "#16A9A0"
        self.accent_label.set("Tyrkysová")
        self.audio_status.set("Nový projekt")
        self._update_scale_range()
        self.draw_timeline()
        self.schedule_preview()

    def _on_close(self) -> None:
        self._close_playback()
        self.root.destroy()


def ImageReaderCompat(image: Image.Image):
    """ReportLab image reader wrapper kept local to avoid extra temp files."""
    from reportlab.lib.utils import ImageReader
    return ImageReader(image)


def main() -> None:
    root = tk.Tk()
    SongSheetApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
