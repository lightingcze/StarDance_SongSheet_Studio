"use strict";

(() => {
  const FPS = 25;
  const ANALYSIS_RATE = 22050;
  const WAVE_BINS = 2400;
  const INSTRUMENTS = ["Bicí/perkuse", "Bas/kopák", "Tónová vrstva"];
  const MARK_KINDS = ["Akcent", "Cue", "Sekce", "Nástroj", "Jiné"];
  const PRODUCTION_FIELDS = [
    ["choreography", "Poznámky choreografů"], ["theme", "Téma a charakter čísla"],
    ["costumes", "Kostýmy"], ["props", "Rekvizity"], ["lighting", "Požadavky na světla"],
    ["led", "LED obsah a videoprojekce"], ["effects", "Speciální efekty"],
    ["other", "Další produkční poznámky"]
  ];
  const DEFAULT_ACCENT = "#16a9a0";
  const DRAFT_KEY = "stardance-songsheet-web-draft-v1";
  const $ = (selector, root) => (root || document).querySelector(selector);
  const $$ = (selector, root) => Array.from((root || document).querySelectorAll(selector));
  let state = createDefaults();
  let audioContext = null;
  let audioBuffer = null;
  let audioFile = null;
  let audioObjectUrl = "";
  let selectedMarkerId = "";
  let currentPage = 1;
  let currentView = "preview";
  let waveformZoom = 1;
  let timelineWidth = 900;
  let dragMarkerId = "";
  let toastTimer = 0;
  let draftTimer = 0;
  let analysisBusy = false;
  const audioPlayer = $("#audioPlayer");
  const waveformCanvas = $("#waveformCanvas");
  const waveformScroller = $("#waveformScroller");

  function createDefaults() {
    const production = {};
    PRODUCTION_FIELDS.forEach((field) => { production[field[0]] = ""; });
    return {
      metadata: { title: "", episode: "", artist: "", performer: "", dance: "" },
      production: production, duration: "", durationSeconds: 0, bpm: "",
      bpm_confidence: "Neurčeno", audioName: "", audioDataUrl: "", waveform: [],
      cues: "", sections: "", ld_proposals: "", markers: [], instrument_summary: "",
      instrument_summary_short: "", instrument_events: [], references: [],
      accent: DEFAULT_ACCENT, dark: false, show_waveform: true, show_references: true
    };
  }

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"
    })[char]);
  }
  function clamp(value, min, max) { return Math.max(min, Math.min(max, value)); }
  function formatTimecode(seconds) {
    const frames = Math.max(0, Math.round((Number(seconds) || 0) * FPS));
    const hh = Math.floor(frames / (3600 * FPS));
    const remHour = frames % (3600 * FPS);
    const mm = Math.floor(remHour / (60 * FPS));
    const remMinute = remHour % (60 * FPS);
    return [hh, mm, Math.floor(remMinute / FPS), remMinute % FPS]
      .map((part) => String(part).padStart(2, "0")).join(":");
  }
  function parseTimecode(value) {
    const text = String(value || "").trim();
    const match = text.match(/^(\d{1,3}):([0-5]?\d):([0-5]?\d):(\d{1,2})$/);
    if (match) return Number(match[1]) * 3600 + Number(match[2]) * 60 +
      Number(match[3]) + clamp(Number(match[4]), 0, FPS - 1) / FPS;
    const numeric = Number(text.replace(",", "."));
    return Number.isFinite(numeric) && numeric >= 0 ? numeric : null;
  }
  function currentDuration() { return audioBuffer ? audioBuffer.duration : (Number(state.durationSeconds) || 0); }
  function newId() { return Math.random().toString(36).slice(2, 10) + Date.now().toString(36); }
  function readAsDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(reader.error || new Error("Soubor se nepodařilo načíst."));
      reader.readAsDataURL(file);
    });
  }
  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url; link.download = filename; document.body.appendChild(link);
    link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1500);
  }
  function safeFilename(value) {
    return (String(value || "StarDance_SongSheet").normalize("NFKD").replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-zA-Z0-9_-]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 70)) || "StarDance_SongSheet";
  }
  function showToast(message, duration) {
    const toast = $("#toast");
    toast.textContent = message; toast.classList.add("visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("visible"), duration || 3000);
  }
  function setStatus(message) { $("#audioStatus").textContent = message; }
  function setSaveStatus(message) { $("#saveStatus").textContent = message; }
  function persistDraft() {
    clearTimeout(draftTimer);
    setSaveStatus("Ukládám změny…");
    draftTimer = setTimeout(() => {
      try {
        const draft = Object.assign({}, state, { audioDataUrl: "", references: [] });
        localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
        setSaveStatus("Změny se ukládají lokálně");
      } catch (error) {
        setSaveStatus("Pracovní stav je příliš velký");
      }
    }, 250);
  }
  function restoreDraft() {
    try {
      const raw = localStorage.getItem(DRAFT_KEY);
      if (!raw) return;
      const saved = JSON.parse(raw);
      if (!saved || !saved.metadata) return;
      state = Object.assign(createDefaults(), saved);
      state.metadata = Object.assign(createDefaults().metadata, saved.metadata || {});
      state.production = Object.assign(createDefaults().production, saved.production || {});
      state.audioDataUrl = "";
      state.references = [];
      state.markers = Array.isArray(saved.markers) ? saved.markers : [];
    } catch (_) { state = createDefaults(); }
  }
  function changed() {
    renderPreview();
    renderReferenceList();
    renderWaveform();
    persistDraft();
  }
  function updateMetadata(event) {
    state.metadata[event.currentTarget.dataset.meta] = event.currentTarget.value;
    changed();
  }
  function updateProduction(event) {
    state.production[event.currentTarget.dataset.production] = event.currentTarget.value;
    changed();
  }
  function updateAnalysisText(event) {
    state[event.currentTarget.dataset.state] = event.currentTarget.value;
    changed();
  }
  function bindControls() {
    $$("[data-editor-tab]").forEach((button) => button.addEventListener("click", () => {
      $$("[data-editor-tab]").forEach((item) => item.classList.toggle("active", item === button));
      $$("[data-editor-panel]").forEach((panel) => panel.classList.toggle("active", panel.dataset.editorPanel === button.dataset.editorTab));
    }));
    $$("[data-view-tab]").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.viewTab)));
    $$("[data-page]").forEach((button) => button.addEventListener("click", () => {
      currentPage = Number(button.dataset.page); renderPreview();
    }));
    $$("[data-meta]").forEach((input) => input.addEventListener("input", updateMetadata));
    $$("[data-production]").forEach((input) => input.addEventListener("input", updateProduction));
    $$("[data-state]").forEach((input) => input.addEventListener("input", updateAnalysisText));
    $("#durationField").addEventListener("change", () => {
      const value = parseTimecode($("#durationField").value);
      if (value == null) { $("#durationField").value = state.duration || ""; showToast("Zadejte čas jako HH:MM:SS:FF nebo sekundy."); return; }
      state.durationSeconds = value; state.duration = formatTimecode(value);
      $("#durationField").value = state.duration; changed();
    });
    $("#bpmField").addEventListener("change", () => {
      const value = Number($("#bpmField").value.replace(",", "."));
      if (Number.isFinite(value) && value > 0 && value < 400) { state.bpm = String(Math.round(value)); changed(); }
      else { $("#bpmField").value = state.bpm || ""; }
    });
    $("#accentSelect").addEventListener("change", () => {
      state.accent = $("#accentSelect").value; document.documentElement.style.setProperty("--accent", state.accent); changed();
    });
    $("#darkToggle").addEventListener("change", () => { state.dark = $("#darkToggle").checked; changed(); });
    $("#waveToggle").addEventListener("change", () => { state.show_waveform = $("#waveToggle").checked; changed(); });
    $("#refsToggle").addEventListener("change", () => { state.show_references = $("#refsToggle").checked; changed(); });
    $("#zoomRange").addEventListener("input", () => {
      waveformZoom = Number($("#zoomRange").value) || 1;
      $("#zoomValue").value = waveformZoom + "×"; renderWaveform();
    });
    $("#instrumentFilter").addEventListener("change", renderMarkers);
    $("#newProjectButton").addEventListener("click", newProject);
    $("#openProjectButton").addEventListener("click", () => $("#projectInput").click());
    $("#saveProjectButton").addEventListener("click", saveProject);
    $("#loadAudioButton").addEventListener("click", () => $("#audioInput").click());
    $("#loadAudioInline").addEventListener("click", () => $("#audioInput").click());
    $("#addReferenceButton").addEventListener("click", () => $("#referenceInput").click());
    $("#addReferenceInline").addEventListener("click", () => $("#referenceInput").click());
    $("#exportPdfButton").addEventListener("click", exportPdf);
    $("#exportPngButton").addEventListener("click", exportPng);
    $("#generateMarkersButton").addEventListener("click", generateInstrumentMarkers);
    $("#addMarkerButton").addEventListener("click", addMarker);
    $("#removeMarkerButton").addEventListener("click", removeSelectedMarker);
    $("#audioInput").addEventListener("change", (event) => {
      const file = event.target.files && event.target.files[0];
      if (file) loadAudio(file);
      event.target.value = "";
    });
    $("#referenceInput").addEventListener("change", (event) => {
      const files = Array.from(event.target.files || []);
      if (files.length) addReferenceFiles(files);
      event.target.value = "";
    });
    $("#projectInput").addEventListener("change", (event) => {
      const file = event.target.files && event.target.files[0];
      if (file) openProject(file);
      event.target.value = "";
    });
    $("#playButton").addEventListener("click", togglePlayback);
    $("#stopButton").addEventListener("click", stopPlayback);
    $("#seekRange").addEventListener("input", () => {
      const duration = currentDuration();
      if (duration) seekTo(Number($("#seekRange").value) / 1000 * duration);
    });
    audioPlayer.addEventListener("timeupdate", updateTransport);
    audioPlayer.addEventListener("loadedmetadata", updateTransport);
    audioPlayer.addEventListener("play", () => { $("#playButton").textContent = "Ⅱ"; });
    audioPlayer.addEventListener("pause", () => { $("#playButton").textContent = "▶"; });
    audioPlayer.addEventListener("ended", () => { $("#playButton").textContent = "▶"; updateTransport(); });
    audioPlayer.addEventListener("error", () => {
      if (audioPlayer.src) setStatus("Prohlížeč tento zvukový formát nepřehrál. Zkuste WAV nebo MP3.");
    });
    waveformCanvas.addEventListener("pointerdown", waveformPointerDown);
    waveformCanvas.addEventListener("pointermove", waveformPointerMove);
    waveformCanvas.addEventListener("pointerup", waveformPointerUp);
    waveformCanvas.addEventListener("pointercancel", waveformPointerUp);
    window.addEventListener("resize", renderWaveform);
    window.addEventListener("beforeprint", renderPrintPages);
    const dropArea = waveformScroller;
    ["dragenter", "dragover"].forEach((name) => dropArea.addEventListener(name, (event) => {
      event.preventDefault(); dropArea.classList.add("drag-over");
    }));
    ["dragleave", "drop"].forEach((name) => dropArea.addEventListener(name, (event) => {
      event.preventDefault(); dropArea.classList.remove("drag-over");
    }));
    dropArea.addEventListener("drop", (event) => {
      const file = Array.from(event.dataTransfer.files || []).find((item) =>
        item.type.startsWith("audio/") || /\.(wav|mp3|flac|m4a|aac|ogg|aiff?)$/i.test(item.name));
      if (file) loadAudio(file);
    });
    $("#markerTableBody").addEventListener("change", markerTableChange);
    $("#markerTableBody").addEventListener("click", markerTableClick);
  }

  async function loadAudio(file, keepProjectData) {
    const name = file.name || "audio";
    if (audioObjectUrl) URL.revokeObjectURL(audioObjectUrl);
    audioFile = file;
    audioObjectUrl = URL.createObjectURL(file);
    audioPlayer.src = audioObjectUrl;
    $("#audioFileName").textContent = name;
    $("#audioFileMeta").textContent = (file.size / 1048576).toFixed(1) + " MB · načítá se";
    waveformScroller.classList.add("has-audio");
    state.audioName = name;
    try {
      state.audioDataUrl = await readAsDataUrl(file);
      setStatus("Dekóduji audio a vytvářím waveform…");
      const bytes = await file.arrayBuffer();
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) throw new Error("Tento prohlížeč nepodporuje Web Audio API.");
      if (!audioContext) audioContext = new Ctx();
      if (audioContext.state === "suspended") await audioContext.resume();
      audioBuffer = await audioContext.decodeAudioData(bytes.slice(0));
      state.durationSeconds = audioBuffer.duration;
      state.duration = formatTimecode(audioBuffer.duration);
      $("#durationField").value = state.duration;
      $("#audioFileMeta").textContent = (file.size / 1048576).toFixed(1) + " MB · " + formatTimecode(audioBuffer.duration);
      await analyzeAudioBuffer(audioBuffer);
      updateTransport();
      changed();
      setStatus("Audio analyzováno v tomto prohlížeči · " + formatTimecode(audioBuffer.duration));
      showToast("Waveform a hudební odhady jsou připravené.");
    } catch (error) {
      audioBuffer = null;
      state.durationSeconds = 0;
      state.waveform = [];
      state.audioDataUrl = keepProjectData ? state.audioDataUrl : "";
      waveformScroller.classList.remove("has-audio");
      setStatus("Audio nelze analyzovat: " + error.message);
      showToast("Nepodařilo se načíst audio. Zkuste WAV nebo MP3.");
    }
  }

  async function resampleAudio(buffer) {
    const length = Math.ceil(buffer.duration * ANALYSIS_RATE);
    const mono = new Float32Array(length);
    const channels = [];
    for (let c = 0; c < buffer.numberOfChannels; c++) channels.push(buffer.getChannelData(c));
    const ratio = buffer.sampleRate / ANALYSIS_RATE;
    for (let start = 0; start < length; start += 250000) {
      const end = Math.min(length, start + 250000);
      for (let i = start; i < end; i++) {
        const position = i * ratio, left = Math.floor(position), fraction = position - left;
        let value = 0;
        for (let c = 0; c < channels.length; c++) {
          const data = channels[c];
          value += (data[left] || 0) * (1 - fraction) + (data[Math.min(left + 1, data.length - 1)] || 0) * fraction;
        }
        mono[i] = value / channels.length;
      }
      if (end < length) { setStatus("Příprava analýzy… " + Math.round(end / length * 100) + "%"); await new Promise((resolve) => requestAnimationFrame(resolve)); }
    }
    return mono;
  }

  function makeWaveform(buffer) {
    const channel = buffer.getChannelData(0);
    const bins = Math.min(WAVE_BINS, Math.max(1, Math.floor(channel.length / 32)));
    const values = new Array(bins);
    for (let b = 0; b < bins; b++) {
      const start = Math.floor(b * channel.length / bins);
      const end = Math.max(start + 1, Math.floor((b + 1) * channel.length / bins));
      let peak = 0;
      for (let i = start; i < end; i++) peak = Math.max(peak, Math.abs(channel[i]));
      values[b] = Math.round(peak * 10000) / 10000;
    }
    return values;
  }

  function fftMagnitudes(signal, start, size, sampleRate) {
    const real = new Float32Array(size), imag = new Float32Array(size);
    for (let i = 0; i < size; i++) {
      const sample = signal[Math.min(start + i, signal.length - 1)] || 0;
      real[i] = sample * (0.5 - 0.5 * Math.cos(2 * Math.PI * i / (size - 1)));
    }
    let j = 0;
    for (let i = 1; i < size; i++) {
      let bit = size >> 1;
      for (; j & bit; bit >>= 1) j ^= bit;
      j ^= bit;
      if (i < j) { const temp = real[i]; real[i] = real[j]; real[j] = temp; }
    }
    for (let width = 2; width <= size; width <<= 1) {
      const angle = -2 * Math.PI / width, stepR = Math.cos(angle), stepI = Math.sin(angle);
      for (let base = 0; base < size; base += width) {
        let wr = 1, wi = 0, half = width >> 1;
        for (let k = 0; k < half; k++) {
          const even = base + k, odd = even + half;
          const tr = wr * real[odd] - wi * imag[odd], ti = wr * imag[odd] + wi * real[odd];
          real[odd] = real[even] - tr; imag[odd] = imag[even] - ti;
          real[even] += tr; imag[even] += ti;
          const next = wr * stepR - wi * stepI;
          wi = wr * stepI + wi * stepR; wr = next;
        }
      }
    }
    const bands = [0, 0, 0], resolution = sampleRate / size;
    for (let i = 1; i < size / 2; i++) {
      const magnitude = Math.sqrt(real[i] * real[i] + imag[i] * imag[i]);
      const hz = i * resolution;
      if (hz < 180) bands[0] += magnitude;
      else if (hz < 2200) bands[1] += magnitude;
      else bands[2] += magnitude;
    }
    return bands;
  }

  function estimateTempo(envelope) {
    if (envelope.length < 40) return { bpm: "", confidence: "Neurčeno" };
    const novelty = new Float32Array(envelope.length);
    for (let i = 1; i < envelope.length; i++) novelty[i] = Math.max(0, envelope[i] - envelope[i - 1]);
    let mean = 0;
    for (let i = 0; i < novelty.length; i++) mean += novelty[i];
    mean /= novelty.length;
    for (let i = 0; i < novelty.length; i++) novelty[i] = Math.max(0, novelty[i] - mean * 0.25);
    const hopSeconds = 0.05, minLag = Math.floor(60 / 190 / hopSeconds), maxLag = Math.ceil(60 / 55 / hopSeconds);
    let bestLag = 0, bestScore = 0, second = 0;
    for (let lag = minLag; lag <= maxLag; lag++) {
      let score = 0, norm = 0;
      for (let i = lag; i < novelty.length; i++) { score += novelty[i] * novelty[i - lag]; norm += novelty[i] * novelty[i]; }
      score = norm ? score / norm : 0;
      if (score > bestScore) { second = bestScore; bestScore = score; bestLag = lag; }
      else if (score > second && Math.abs(lag - bestLag) > 1) second = score;
    }
    if (!bestLag || bestScore < 0.03) return { bpm: "", confidence: "Nízká jistota" };
    let bpm = 60 / (bestLag * hopSeconds);
    if (bpm < 70) bpm *= 2;
    if (bpm > 165) bpm /= 2;
    const confidence = bestScore > 0.25 && bestScore - second > 0.04 ? "Střední" : "Nízká jistota";
    return { bpm: String(Math.round(bpm)), confidence: confidence };
  }

  function findAccentCandidates(envelope) {
    if (envelope.length < 2) return [];
    const delta = new Float32Array(envelope.length);
    const sorted = [];
    for (let i = 1; i < envelope.length; i++) { delta[i] = Math.max(0, envelope[i] - envelope[i - 1]); sorted.push(delta[i]); }
    sorted.sort((a, b) => a - b);
    const median = sorted[Math.floor(sorted.length * 0.5)] || 0;
    const threshold = median * 2.7;
    const candidates = [];
    for (let i = 2; i < delta.length - 2; i++) {
      if (delta[i] > threshold && delta[i] >= delta[i - 1] && delta[i] > delta[i + 1]) {
        if (!candidates.length || i * 0.05 - candidates[candidates.length - 1] > 1.3) candidates.push(i * 0.05);
      }
      if (candidates.length >= 32) break;
    }
    if (!candidates.length) {
      const step = Math.max(1, Math.round(60 / (Number(state.bpm) || 120) / 0.05));
      for (let i = step; i < envelope.length && candidates.length < 24; i += step * 4) candidates.push(i * 0.05);
    }
    return candidates;
  }

  function makeEnergyText(envelope) {
    const windows = Math.ceil(envelope.length / 200), levels = [];
    for (let w = 0; w < windows; w++) {
      const start = w * 200, end = Math.min(envelope.length, start + 200);
      let sum = 0;
      for (let i = start; i < end; i++) sum += envelope[i] * envelope[i];
      levels.push(Math.sqrt(sum / Math.max(1, end - start)));
    }
    const max = Math.max.apply(null, levels.concat([0.000001]));
    return levels.map((level, i) => {
      const label = level / max > 0.72 ? "vysoká" : level / max > 0.38 ? "střední" : "klidnější";
      return formatTimecode(i * 10) + " · " + label + " energie (" + Math.round(level / max * 100) + "%)";
    }).join("\n");
  }

  async function analyzeAudioBuffer(buffer) {
    if (analysisBusy) return;
    analysisBusy = true;
    try {
      const mono = await resampleAudio(buffer);
      state.waveform = makeWaveform(buffer);
      const hop = Math.round(ANALYSIS_RATE * 0.05);
      const envelope = new Float32Array(Math.ceil(mono.length / hop));
      for (let w = 0; w < envelope.length; w++) {
        const start = w * hop, end = Math.min(mono.length, start + hop);
        let sum = 0;
        for (let i = start; i < end; i++) sum += mono[i] * mono[i];
        envelope[w] = Math.sqrt(sum / Math.max(1, end - start));
      }
      const tempo = estimateTempo(envelope);
      state.bpm = tempo.bpm;
      state.bpm_confidence = tempo.confidence;
      const accents = findAccentCandidates(envelope);
      state.cues = accents.map((time) => formatTimecode(time) + " · možný akcent").join("\n");
      state.sections = makeEnergyText(envelope);
      state.instrument_events = [];
      const frameSize = 512, frameHop = Math.round(ANALYSIS_RATE * 0.5);
      const aggregate = { low: [], mid: [], high: [] };
      const samples = Math.max(1, Math.floor(mono.length / frameHop));
      const stride = Math.max(1, Math.ceil(samples / 1200));
      for (let n = 0; n < samples; n += stride) {
        const bands = fftMagnitudes(mono, n * frameHop, frameSize, ANALYSIS_RATE);
        aggregate.low.push(bands[0]); aggregate.mid.push(bands[1]); aggregate.high.push(bands[2]);
        if (n > 0 && n % 120 === 0) {
          setStatus("Odhad nástrojových vrstev… " + Math.round(n / samples * 100) + "%");
          await new Promise((resolve) => requestAnimationFrame(resolve));
        }
      }
      const averages = [aggregate.low, aggregate.mid, aggregate.high].map((list) =>
        list.reduce((sum, value) => sum + value, 0) / Math.max(1, list.length));
      const maxBand = Math.max.apply(null, averages.concat([1]));
      const names = ["Bas/kopák", "Tónová vrstva", "Bicí/perkuse"];
      const detail = names.map((name, i) => name + ": " + Math.round(averages[i] / maxBand * 100) + "% relativní aktivity");
      state.instrument_summary = "Frekvenční odhad (nikoli rozpoznání samostatných stop):\n" + detail.join("\n");
      state.instrument_summary_short = detail.join(" · ");
      const layerLists = [
        { name: "Bas/kopák", values: aggregate.low, gate: 1.18 },
        { name: "Tónová vrstva", values: aggregate.mid, gate: 1.22 },
        { name: "Bicí/perkuse", values: aggregate.high, gate: 1.3 }
      ];
      for (let layer = 0; layer < layerLists.length; layer++) {
        const item = layerLists[layer], mean = item.values.reduce((sum, value) => sum + value, 0) / Math.max(1, item.values.length);
        const windowed = Math.max(1, Math.floor(10 / (0.5 * stride)));
        for (let i = 0; i < item.values.length; i += windowed) {
          const end = Math.min(item.values.length, i + windowed);
          const level = item.values.slice(i, end).reduce((sum, value) => sum + value, 0) / (end - i);
          if (level > mean * item.gate) state.instrument_events.push({
            time: i * 0.5 * stride, layer: item.name, label: item.name + " · vyšší aktivita"
          });
        }
      }
      state.instrument_events.sort((a, b) => a.time - b.time);
      $("#instrumentSummary").value = state.instrument_summary;
      $("#cueText").value = state.cues;
      $("#sectionText").value = state.sections;
      $("#bpmReadout").textContent = state.bpm || "—";
      $("#confidenceValue").textContent = state.bpm_confidence;
      $("#bpmField").value = state.bpm || "";
      changed();
    } finally {
      analysisBusy = false;
    }
  }

  function switchView(view) {
    currentView = view;
    $$("[data-view-tab]").forEach((button) => button.classList.toggle("active", button.dataset.viewTab === view));
    $$("[data-view-panel]").forEach((panel) => panel.classList.toggle("active", panel.dataset.viewPanel === view));
    if (view === "audio") requestAnimationFrame(renderWaveform);
  }
  function syncControls() {
    $$("[data-meta]").forEach((input) => { input.value = state.metadata[input.dataset.meta] || ""; });
    $$("[data-production]").forEach((input) => { input.value = state.production[input.dataset.production] || ""; });
    $("[data-state='ld_proposals']").value = state.ld_proposals || "";
    $("#durationField").value = state.duration || "";
    $("#bpmField").value = state.bpm || "";
    $("#accentSelect").value = state.accent || DEFAULT_ACCENT;
    $("#darkToggle").checked = Boolean(state.dark);
    $("#waveToggle").checked = state.show_waveform !== false;
    $("#refsToggle").checked = state.show_references !== false;
    $("#instrumentSummary").value = state.instrument_summary || "";
    $("#cueText").value = state.cues || "";
    $("#sectionText").value = state.sections || "";
    $("#bpmReadout").textContent = state.bpm || "—";
    $("#confidenceValue").textContent = state.bpm_confidence || "Neurčeno";
    document.documentElement.style.setProperty("--accent", state.accent || DEFAULT_ACCENT);
  }
  function addMarker() {
    const time = audioPlayer.currentTime || 0;
    const marker = { id: newId(), name: "Nová značka", time: time, kind: "Cue", instrument: "" };
    state.markers.push(marker); selectedMarkerId = marker.id;
    switchView("audio"); renderMarkers(); renderWaveform(); changed();
  }
  function removeSelectedMarker() {
    if (!selectedMarkerId && state.markers.length) selectedMarkerId = state.markers[state.markers.length - 1].id;
    if (!selectedMarkerId) return showToast("Nejprve vyberte značku v tabulce nebo na waveformu.");
    state.markers = state.markers.filter((marker) => marker.id !== selectedMarkerId);
    selectedMarkerId = ""; renderMarkers(); renderWaveform(); changed();
  }
  function markerTableChange(event) {
    const field = event.target.dataset.markerField;
    if (!field) return;
    const index = Number(event.target.dataset.markerIndex);
    const marker = state.markers[index];
    if (!marker) return;
    let value = event.target.value;
    if (field === "time") {
      const parsed = parseTimecode(value);
      if (parsed == null) { event.target.value = formatTimecode(marker.time); showToast("Čas zadejte jako HH:MM:SS:FF nebo sekundy."); return; }
      marker.time = Math.min(parsed, currentDuration() || parsed);
    } else marker[field] = value;
    selectedMarkerId = marker.id;
    renderMarkers(); renderWaveform(); changed();
  }
  function markerTableClick(event) {
    const deleteButton = event.target.closest(".row-delete");
    if (deleteButton) {
      const marker = state.markers[Number(deleteButton.dataset.markerIndex)];
      if (marker) { selectedMarkerId = marker.id; removeSelectedMarker(); }
      return;
    }
    const row = event.target.closest("tr[data-marker-id]");
    if (row) { selectedMarkerId = row.dataset.markerId; renderMarkers(); renderWaveform(); }
  }
  function renderMarkers() {
    const body = $("#markerTableBody"), filter = $("#instrumentFilter").value;
    const visible = state.markers.map((marker, index) => ({ marker: marker, index: index })).filter((entry) => {
      if (filter === "Všechny") return true;
      if (filter === "Bez přiřazení") return !entry.marker.instrument;
      return entry.marker.instrument === filter;
    });
    if (!visible.length) {
      body.innerHTML = '<tr><td colspan="5" class="empty-row">' +
        (state.markers.length ? "Pro zvolenou vrstvu tu nejsou žádné značky." : "Načtěte audio nebo přidejte značku.") + "</td></tr>";
      return;
    }
    body.innerHTML = visible.map((entry) => {
      const marker = entry.marker, index = entry.index;
      return '<tr data-marker-id="' + esc(marker.id) + '" class="' + (marker.id === selectedMarkerId ? "selected" : "") + '">' +
        '<td><span class="marker-color"></span><input data-marker-index="' + index + '" data-marker-field="name" aria-label="Název značky" value="' + esc(marker.name) + '"></td>' +
        '<td><input data-marker-index="' + index + '" data-marker-field="time" aria-label="Čas značky" value="' + esc(formatTimecode(marker.time)) + '"></td>' +
        '<td><select data-marker-index="' + index + '" data-marker-field="kind" aria-label="Typ značky">' +
        MARK_KINDS.map((kind) => '<option' + (marker.kind === kind ? " selected" : "") + '>' + esc(kind) + "</option>").join("") + "</select></td>" +
        '<td><select data-marker-index="' + index + '" data-marker-field="instrument" aria-label="Nástrojová vrstva"><option value="">—</option>' +
        INSTRUMENTS.map((layer) => '<option' + (marker.instrument === layer ? " selected" : "") + '>' + esc(layer) + "</option>").join("") + "</select></td>" +
        '<td><button class="row-delete" type="button" data-marker-index="' + index + '" aria-label="Odebrat značku">×</button></td></tr>';
    }).join("");
  }
  function generateInstrumentMarkers() {
    if (!state.instrument_events.length) {
      showToast("Nejsou připravené návrhy vrstev. Nejdřív načtěte audio."); return;
    }
    const known = new Set(state.markers.map((marker) => marker.instrument + ":" + Math.round(marker.time)));
    let added = 0;
    state.instrument_events.slice(0, 60).forEach((item) => {
      const key = item.layer + ":" + Math.round(item.time);
      if (known.has(key)) return;
      known.add(key);
      state.markers.push({ id: newId(), name: item.label, time: item.time, kind: "Nástroj", instrument: item.layer });
      added++;
    });
    renderMarkers(); renderWaveform(); changed(); switchView("audio");
    showToast(added ? "Přidáno " + added + " kandidátních značek." : "Všechny návrhy už mají značku.");
  }

  function timelineTimeFromEvent(event) {
    const rect = waveformCanvas.getBoundingClientRect();
    const x = clamp(event.clientX - rect.left + waveformScroller.scrollLeft, 0, timelineWidth);
    return currentDuration() * x / Math.max(1, timelineWidth);
  }
  function waveformPointerDown(event) {
    if (!state.waveform.length) return;
    const time = timelineTimeFromEvent(event);
    const tolerance = currentDuration() * 14 / Math.max(1, timelineWidth);
    const nearest = state.markers.reduce((best, marker) => {
      const distance = Math.abs(marker.time - time);
      return distance < tolerance && (!best || distance < best.distance) ? { marker: marker, distance: distance } : best;
    }, null);
    waveformCanvas.setPointerCapture(event.pointerId);
    if (nearest) {
      dragMarkerId = nearest.marker.id; selectedMarkerId = dragMarkerId;
      waveformCanvas.classList.add("dragging-marker"); renderMarkers();
    } else if (audioBuffer) seekTo(time);
  }
  function waveformPointerMove(event) {
    if (!dragMarkerId) return;
    const marker = state.markers.find((item) => item.id === dragMarkerId);
    if (!marker) return;
    marker.time = clamp(timelineTimeFromEvent(event), 0, currentDuration());
    updateTransport(); renderWaveform();
  }
  function waveformPointerUp() {
    if (!dragMarkerId) return;
    dragMarkerId = ""; waveformCanvas.classList.remove("dragging-marker");
    renderMarkers(); renderWaveform(); changed();
  }
  function drawWaveform(canvas, width, height, withMarkers, mini) {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * dpr); canvas.height = Math.round(height * dpr);
    canvas.style.width = width + "px"; canvas.style.height = height + "px";
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, width, height);
    const dark = mini ? Boolean(state.dark) : true;
    ctx.fillStyle = dark ? "#192930" : "#f4f8f8"; ctx.fillRect(0, 0, width, height);
    const center = height * 0.52, maxAmplitude = height * 0.37;
    ctx.strokeStyle = dark ? "rgba(202,225,225,.18)" : "rgba(70,101,104,.16)";
    ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(0, center); ctx.lineTo(width, center); ctx.stroke();
    if (state.waveform.length) {
      const step = width / state.waveform.length;
      ctx.fillStyle = state.accent || DEFAULT_ACCENT;
      for (let i = 0; i < state.waveform.length; i++) {
        const amp = Math.max(1, state.waveform[i] * maxAmplitude);
        ctx.fillRect(i * step, center - amp, Math.max(1, step * 0.78), amp * 2);
      }
    }
    const duration = currentDuration();
    if (!mini && duration) {
      ctx.font = "10px DejaVu Web, Segoe UI, sans-serif";
      ctx.fillStyle = "rgba(224,238,238,.64)";
      const interval = duration > 1800 ? 300 : duration > 600 ? 60 : duration > 180 ? 30 : 10;
      for (let second = 0; second <= duration; second += interval) {
        const x = second / duration * width;
        ctx.strokeStyle = "rgba(211,230,230,.2)"; ctx.beginPath(); ctx.moveTo(x, 12); ctx.lineTo(x, height - 18); ctx.stroke();
        ctx.fillText(formatTimecode(second).slice(0, 8), x + 4, height - 5);
      }
      const colors = { "Akcent": "#e7b54a", "Cue": "#52d1c4", "Sekce": "#9a8be8", "Nástroj": "#ef8c69", "Jiné": "#d2d9d9" };
      state.markers.forEach((marker) => {
        const x = marker.time / duration * width;
        ctx.strokeStyle = colors[marker.kind] || colors.Cue; ctx.lineWidth = marker.id === selectedMarkerId ? 2.5 : 1.4;
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke();
        ctx.fillStyle = ctx.strokeStyle; ctx.beginPath(); ctx.moveTo(x - 4, 1); ctx.lineTo(x + 4, 1); ctx.lineTo(x, 8); ctx.closePath(); ctx.fill();
        if (x >= waveformScroller.scrollLeft && x <= waveformScroller.scrollLeft + waveformScroller.clientWidth) {
          ctx.save(); ctx.translate(x + 5, 20); ctx.rotate(Math.PI / 2); ctx.font = "9px DejaVu Web, Segoe UI, sans-serif";
          ctx.fillText(String(marker.name || "").slice(0, 32), 0, 0); ctx.restore();
        }
      });
      const playX = audioPlayer.currentTime / duration * width;
      ctx.strokeStyle = "#fff"; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.moveTo(playX, 0); ctx.lineTo(playX, height); ctx.stroke();
    }
  }
  function renderWaveform() {
    if (!waveformCanvas || !waveformScroller) return;
    const available = waveformScroller.clientWidth || 900;
    timelineWidth = Math.max(available, available * waveformZoom);
    waveformCanvas.style.width = timelineWidth + "px";
    if (state.waveform.length) {
      waveformScroller.classList.add("has-audio"); drawWaveform(waveformCanvas, timelineWidth, 246, true, false);
    } else {
      waveformScroller.classList.remove("has-audio"); drawWaveform(waveformCanvas, timelineWidth, 246, false, false);
    }
    renderMarkers();
    if ($("#sheetPreview")) drawMiniWaveform();
  }
  function seekTo(time) {
    const duration = currentDuration();
    if (!duration) return;
    audioPlayer.currentTime = clamp(time, 0, duration);
    updateTransport(); renderWaveform();
  }
  function togglePlayback() {
    if (!audioPlayer.src) { $("#audioInput").click(); return; }
    if (audioPlayer.paused) audioPlayer.play().catch(() => showToast("Přehrávání nebylo možné spustit."));
    else audioPlayer.pause();
  }
  function stopPlayback() { audioPlayer.pause(); seekTo(0); }
  function updateTransport() {
    const duration = currentDuration(), current = audioPlayer.currentTime || 0;
    $("#currentTimecode").textContent = formatTimecode(current);
    $("#totalTimecode").textContent = formatTimecode(duration);
    $("#seekRange").value = duration ? String(Math.round(current / duration * 1000)) : "0";
    if (audioBuffer && !dragMarkerId) drawWaveform(waveformCanvas, timelineWidth, 246, true, false);
  }
  function drawMiniWaveform() {
    const canvas = $("#previewWaveform");
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    drawWaveform(canvas, Math.max(220, Math.floor(rect.width || 600)), 92, false, true);
  }
  function renderReferenceList() {
    const list = $("#referenceList");
    if (!state.references.length) { list.innerHTML = '<p class="empty-state">Zatím bez obrázků.</p>'; return; }
    list.innerHTML = state.references.map((ref, index) =>
      '<div class="reference-thumb"><img src="' + esc(ref.dataUrl) + '" alt="' + esc(ref.name) + '">' +
      '<span>' + esc(ref.name) + '</span><button type="button" data-ref-index="' + index + '" aria-label="Odebrat referenci">×</button></div>'
    ).join("");
    list.querySelectorAll("button[data-ref-index]").forEach((button) => button.addEventListener("click", () => {
      state.references.splice(Number(button.dataset.refIndex), 1); renderReferenceList(); changed();
    }));
  }
  async function addReferenceFiles(files) {
    const remaining = Math.max(0, 4 - state.references.length);
    if (!remaining) return showToast("Lze vložit nejvýše čtyři reference.");
    for (const file of files.slice(0, remaining)) {
      if (!file.type.startsWith("image/")) continue;
      try { state.references.push({ name: file.name, dataUrl: await readAsDataUrl(file) }); }
      catch (_) { showToast("Obrázek se nepodařilo načíst."); }
    }
    renderReferenceList(); changed();
    if (files.length > remaining) showToast("Přidány nejvýše čtyři obrázky.");
  }

  function metaItem(label, value) {
    return '<div class="sheet-meta-item"><span>' + esc(label) + '</span><strong>' + esc(value || "—") + '</strong></div>';
  }
  function sectionTitle(text) { return '<div class="sheet-section-title">' + esc(text) + "</div>"; }
  function listBox(title, text) {
    return '<div class="sheet-list-box"><h4>' + esc(title) + '</h4><p>' + esc(text || "—") + "</p></div>";
  }
  function buildSheetMarkup(page) {
    const title = state.metadata.title || "Název skladby";
    const accentBar = '<div class="sheet-accent-bar"></div>';
    const topline = '<div class="sheet-topline"><span>STARDANCE · SONGSHEET STUDIO</span><span class="sheet-page-tag">PRACOVNÍ LIST · ' +
      (page === 1 ? "01 / HUDBA" : "02 / PRODUKCE") + "</span></div>";
    const footer = '<div class="sheet-footer"><span>' + esc(title) + " · " + esc(state.metadata.dance || "Tanec neuveden") +
      '</span><span>25 FPS · ' + (page === 1 ? "01" : "02") + "</span></div>";
    if (page === 1) {
      const markers = state.markers.length ? state.markers.slice(0, 10).map((m) =>
        formatTimecode(m.time) + " · " + m.name + (m.instrument ? " [" + m.instrument + "]" : "")
      ).join("\n") : "Zatím bez ručně potvrzených značek.";
      const candidates = state.cues || "Návrhy se zobrazí po načtení audia.";
      const sections = state.sections || "Energetická okna se zobrazí po analýze audia.";
      const layers = state.instrument_summary || "Nástrojové vrstvy se zobrazí po analýze audia.";
      const wave = state.show_waveform ?
        '<canvas id="previewWaveform" class="preview-waveform"></canvas>' :
        '<div class="waveform-off-note">Waveform je skrytý v nastavení vzhledu.</div>';
      return accentBar + topline +
        '<div class="sheet-title-row"><h2 class="sheet-title">' + esc(title) + '</h2><div class="sheet-bpm-card"><strong>' +
        esc(state.bpm || "—") + '</strong><span>BPM · ' + esc(state.bpm_confidence || "ODHAD") + "</span></div></div>" +
        '<div class="sheet-meta">' + metaItem("Díl", state.metadata.episode) + metaItem("Interpret", state.metadata.artist) +
        metaItem("Účinkující", state.metadata.performer) + metaItem("Tanec", state.metadata.dance) +
        metaItem("Délka", state.duration || (currentDuration() ? formatTimecode(currentDuration()) : "")) + "</div>" +
        sectionTitle("HUDEBNÍ PRŮBĚH") + '<div class="sheet-wave-area">' + wave + "</div>" +
        '<div class="sheet-bottom-grid">' + listBox("Ruční značky · HH:MM:SS:FF", markers) +
        listBox("Kandidátní akcenty · ověřit poslechem", candidates) + listBox("Energetická okna · 10 s", sections) + listBox("Odhad nástrojových vrstev", layers) + "</div>" + footer;
    }
    const blocks = PRODUCTION_FIELDS.map((field, index) =>
      '<div class="production-preview-block' + (index === 7 ? " wide" : "") + '"><h4>' +
      esc(field[1]) + '</h4><p>' + esc(state.production[field[0]] || "—") + "</p></div>"
    ).join("");
    const refs = state.show_references && state.references.length ?
      '<div class="refs-preview">' + state.references.slice(0, 4).map((ref) =>
        '<figure><img src="' + esc(ref.dataUrl) + '" alt="' + esc(ref.name) + '"><figcaption>' + esc(ref.name) + "</figcaption></figure>"
      ).join("") + "</div>" :
      '<div class="refs-empty">' + (state.show_references ? "Bez obrazových referencí." : "Reference jsou skryté.") + "</div>";
    const ld = state.ld_proposals || "Vlastní návrhy LD zatím nejsou doplněné.";
    return accentBar + topline + '<div class="sheet-page-two"><div class="sheet-title-row"><h2 class="sheet-title">' +
      esc(title) + '</h2><div class="sheet-bpm-card"><strong>' + esc(state.duration || "—") +
      '</strong><span>DÉLKA · HH:MM:SS:FF</span></div></div>' +
      '<div class="sheet-meta">' + metaItem("Interpret", state.metadata.artist) + metaItem("Účinkující", state.metadata.performer) +
      metaItem("Díl", state.metadata.episode) + metaItem("Tanec", state.metadata.dance) + metaItem("Tempo", state.bpm ? state.bpm + " BPM" : "") + "</div>" +
      '<div class="production-page-grid"><div class="production-blocks">' + blocks + '</div><aside class="ld-preview-block"><h3>NÁVRHY LD · VLASTNÍ POZNÁMKY</h3><p>' +
      esc(ld) + "</p>" + refs + "</aside></div>" + footer + "</div>";
  }
  function renderPreview() {
    const preview = $("#sheetPreview");
    if (!preview) return;
    preview.classList.toggle("dark", Boolean(state.dark));
    preview.style.setProperty("--accent", state.accent || DEFAULT_ACCENT);
    preview.innerHTML = buildSheetMarkup(currentPage);
    $$("[data-page]").forEach((button) => button.classList.toggle("active", Number(button.dataset.page) === currentPage));
    requestAnimationFrame(drawMiniWaveform);
  }
  function renderPrintPages() {
    const pages = $("#printPages");
    if (!pages) return;
    const dark = state.dark ? " dark" : "";
    pages.innerHTML = [1, 2].map((page) =>
      '<div class="print-page' + dark + '" style="--accent:' + esc(state.accent || DEFAULT_ACCENT) + '">' +
      buildSheetMarkup(page) + "</div>"
    ).join("");
    pages.querySelectorAll("canvas.preview-waveform").forEach((canvas) => drawWaveform(canvas, 980, 118, false, true));
  }
  function renderAll() {
    syncControls();
    $("#audioFileName").textContent = state.audioName || "Žádné audio";
    $("#audioFileMeta").textContent = state.audioName ? "Projekt otevřen · audio znovu načtěte pro přehrávání a analýzu" : "WAV · MP3 · FLAC · M4A · AAC · OGG · AIFF";
    if (state.audioName) setStatus("Projekt obnoven. Pro poslech znovu načtěte jeho audio soubor.");
    renderMarkers(); renderReferenceList(); renderPreview(); renderWaveform();
  }
  function saveProject() {
    state.audioDataUrl = state.audioDataUrl || "";
    const project = Object.assign({ format: "stardance-songsheet-web", version: 1, savedAt: new Date().toISOString() }, state);
    const blob = new Blob([JSON.stringify(project, null, 2)], { type: "application/json;charset=utf-8" });
    downloadBlob(blob, safeFilename(state.metadata.title) + ".stardance.json");
    showToast("Projekt uložen jako přenosný JSON soubor.");
  }
  async function openProject(file) {
    try {
      const project = JSON.parse(await file.text());
      const source = project && (project.state || project);
      if (!source || !source.metadata) throw new Error("Soubor neobsahuje platný projekt SongSheet.");
      const next = Object.assign(createDefaults(), source);
      next.metadata = Object.assign(createDefaults().metadata, source.metadata || {});
      next.production = Object.assign(createDefaults().production, source.production || {});
      next.markers = Array.isArray(source.markers) ? source.markers.map((marker) => ({
        id: marker.id || newId(), name: marker.name || marker.label || "Značka",
        time: typeof marker.time === "string" ? (parseTimecode(marker.time) || 0) : (Number(marker.time) || 0),
        kind: marker.kind || "Cue", instrument: marker.instrument || ""
      })) : [];
      next.references = Array.isArray(source.references) ? source.references.filter((ref) => ref && typeof ref === "object" && typeof ref.dataUrl === "string" && ref.dataUrl.startsWith("data:image/")).slice(0, 4) : [];
      next.audioDataUrl = typeof source.audioDataUrl === "string" && source.audioDataUrl.startsWith("data:audio/") ? source.audioDataUrl : "";
      next.audioName = source.audioName || (source.audio_path ? String(source.audio_path).split(/[\\/]/).pop() : "");
      next.durationSeconds = Number(source.durationSeconds) || parseTimecode(source.duration) || 0;
      next.accent = String(source.accent || DEFAULT_ACCENT).toLowerCase();
      state = next;
      selectedMarkerId = "";
      syncControls(); renderAll(); persistDraft();
      if (state.audioDataUrl) {
        const response = await fetch(state.audioDataUrl);
        const blob = await response.blob();
        const audio = new File([blob], state.audioName || "project-audio.wav", { type: blob.type || "audio/wav" });
        await loadAudio(audio, true);

      }
      showToast("Projekt otevřen.");
    } catch (error) {
      showToast("Projekt se nepodařilo otevřít: " + error.message, 5000);
    }
  }
  function exportPdf() {
    renderPrintPages();
    window.print();
  }
  function newProject() {
    const hasContent = state.metadata.title || state.markers.length || state.audioName;
    if (hasContent && !window.confirm("Začít nový projekt? Neuložené změny se nahradí.")) return;
    audioPlayer.pause(); audioPlayer.removeAttribute("src"); audioPlayer.load();
    if (audioObjectUrl) URL.revokeObjectURL(audioObjectUrl);
    audioObjectUrl = ""; audioBuffer = null; audioFile = null;
    state = createDefaults(); selectedMarkerId = ""; currentPage = 1;
    localStorage.removeItem(DRAFT_KEY); syncControls(); renderAll();
    setStatus("Načtěte audio pro waveform a analýzu.");
  }

  function pngText(ctx, text, x, y, maxWidth, lineHeight, maxLines) {
    const words = String(text || "—").split(/\s+/), lines = [];
    let line = "";
    words.forEach((word) => {
      const attempt = line ? line + " " + word : word;
      if (ctx.measureText(attempt).width > maxWidth && line) { lines.push(line); line = word; }
      else line = attempt;
    });
    if (line) lines.push(line);
    lines.slice(0, maxLines || 5).forEach((item, index) => ctx.fillText(item, x, y + index * lineHeight));
  }
  function drawPngHeader(ctx, canvas, page) {
    const accent = state.accent || DEFAULT_ACCENT, dark = Boolean(state.dark);
    ctx.fillStyle = dark ? "#19272e" : "#ffffff"; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = accent; ctx.fillRect(0, 0, canvas.width, 18);
    ctx.fillStyle = accent; ctx.font = "bold 22px DejaVu Web, sans-serif";
    ctx.fillText("STARDANCE · SONGSHEET STUDIO", 150, 118);
    ctx.fillStyle = dark ? "#9eacad" : "#8e9a9c"; ctx.font = "bold 18px DejaVu Web, sans-serif";
    ctx.textAlign = "right"; ctx.fillText("PRACOVNÍ LIST · " + (page === 1 ? "01 / HUDBA" : "02 / PRODUKCE"), canvas.width - 150, 118); ctx.textAlign = "left";
    ctx.fillStyle = dark ? "#eef2f1" : "#27343a"; ctx.font = "bold 72px DejaVu Web, sans-serif";
    pngText(ctx, state.metadata.title || "Název skladby", 150, 225, 2400, 78, 1);
    ctx.fillStyle = accent; ctx.font = "bold 46px DejaVu Web, sans-serif";
    ctx.textAlign = "right"; ctx.fillText(page === 1 ? (state.bpm || "—") + " BPM" : (state.duration || "—"), canvas.width - 150, 228); ctx.textAlign = "left";
  }
  function drawPngWave(ctx, x, y, width, height) {
    ctx.fillStyle = state.dark ? "#202f36" : "#f5f8f8";
    ctx.fillRect(x, y, width, height);
    ctx.strokeStyle = state.dark ? "#45565c" : "#dce6e5";
    ctx.beginPath(); ctx.moveTo(x, y + height / 2); ctx.lineTo(x + width, y + height / 2); ctx.stroke();
    if (!state.show_waveform) return;
    ctx.fillStyle = state.accent || DEFAULT_ACCENT;
    const step = width / Math.max(1, state.waveform.length);
    state.waveform.forEach((value, index) => {
      const amp = Math.max(1, value * height * 0.43);
      ctx.fillRect(x + index * step, y + height / 2 - amp, Math.max(1, step * 0.75), amp * 2);
    });
  }
  function drawPngPageOne(ctx, canvas) {
    const ink = state.dark ? "#e6eeee" : "#27343a", muted = state.dark ? "#c2cdce" : "#667579", accent = state.accent || DEFAULT_ACCENT;
    drawPngHeader(ctx, canvas, 1);
    ctx.strokeStyle = state.dark ? "#394951" : "#e1e7e7"; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(150, 285); ctx.lineTo(canvas.width - 150, 285); ctx.stroke();
    const meta = [["DÍL", state.metadata.episode], ["INTERPRET", state.metadata.artist], ["ÚČINKUJÍCÍ", state.metadata.performer], ["TANEC", state.metadata.dance], ["DÉLKA", state.duration]];
    const col = (canvas.width - 300) / meta.length;
    meta.forEach((item, index) => {
      ctx.fillStyle = "#91a0a1"; ctx.font = "bold 16px DejaVu Web, sans-serif"; ctx.fillText(item[0], 150 + index * col, 326);
      ctx.fillStyle = ink; ctx.font = "22px DejaVu Web, sans-serif"; pngText(ctx, item[1] || "—", 150 + index * col, 364, col - 18, 26, 1);
    });
    ctx.fillStyle = accent; ctx.font = "bold 21px DejaVu Web, sans-serif"; ctx.fillText("HUDEBNÍ PRŮBĚH", 150, 435);
    drawPngWave(ctx, 150, 460, canvas.width - 300, 365);
    const boxY = 875, boxW = (canvas.width - 330) / 2;
    const boxH = 600, boxGap = 24;
    const boxes = [
      ["RUČNÍ ZNAČKY · HH:MM:SS:FF", state.markers.slice(0, 10).map((m) => formatTimecode(m.time) + " · " + m.name).join("\n") || "Zatím bez ručně potvrzených značek."],
      ["KANDIDÁTNÍ AKCENTY · OVĚŘIT POSLECHEM", state.cues || "Návrhy se zobrazí po načtení audia."],
      ["ENERGETICKÁ OKNA · 10 S", state.sections || "Okna se zobrazí po analýze audia."],
      ["ODHAD NÁSTROJOVÝCH VRSTEV", state.instrument_summary || "Vrstvy se zobrazí po analýze audia."]
    ];
    boxes.forEach((item, i) => {
      const colIndex = i % 2, rowIndex = Math.floor(i / 2);
      const x = 150 + colIndex * (boxW + 30), y = boxY + rowIndex * (boxH + boxGap);
      ctx.strokeStyle = state.dark ? "#3c4b52" : "#e2e8e7"; ctx.strokeRect(x, y, boxW, boxH);
      ctx.fillStyle = accent; ctx.font = "bold 18px DejaVu Web, sans-serif"; ctx.fillText(item[0], x + 20, y + 38);
      ctx.fillStyle = muted; ctx.font = "17px DejaVu Web, sans-serif"; pngText(ctx, item[1], x + 20, y + 76, boxW - 40, 27, 18);
    });
    drawPngFooter(ctx, canvas, 1);
  }
  function drawPngFooter(ctx, canvas, page) {
    ctx.fillStyle = state.dark ? "#98a3a4" : "#98a3a4"; ctx.font = "16px DejaVu Web, sans-serif";
    ctx.fillText((state.metadata.title || "Název skladby") + " · " + (state.metadata.dance || "Tanec neuveden"), 150, canvas.height - 85);
    ctx.textAlign = "right"; ctx.fillText("25 FPS · 0" + page, canvas.width - 150, canvas.height - 85); ctx.textAlign = "left";
  }
  async function drawPngPageTwo(ctx, canvas) {
    drawPngHeader(ctx, canvas, 2);
    const accent = state.accent || DEFAULT_ACCENT, ink = state.dark ? "#e6eeee" : "#27343a", muted = state.dark ? "#c2cdce" : "#667579";
    const leftX = 150, top = 330, gap = 18, blockW = 1110, blockH = 430;
    for (let i = 0; i < PRODUCTION_FIELDS.length; i++) {
      const column = i % 2, row = Math.floor(i / 2), x = leftX + column * (blockW + gap), y = top + row * (blockH + gap);
      ctx.strokeStyle = state.dark ? "#3c4b52" : "#e3e9e8"; ctx.strokeRect(x, y, blockW, blockH);
      ctx.fillStyle = accent; ctx.font = "bold 17px DejaVu Web, sans-serif"; ctx.fillText(PRODUCTION_FIELDS[i][1].toUpperCase(), x + 18, y + 32);
      ctx.fillStyle = muted; ctx.font = "16px DejaVu Web, sans-serif";
      pngText(ctx, state.production[PRODUCTION_FIELDS[i][0]] || "—", x + 18, y + 65, blockW - 36, 24, 8);
    }
    const asideX = 2440, asideW = canvas.width - asideX - 150;
    ctx.strokeStyle = "rgba(217,166,56,.6)"; ctx.strokeRect(asideX, top, asideW, 1774);
    ctx.fillStyle = "#ad8123"; ctx.font = "bold 19px DejaVu Web, sans-serif"; ctx.fillText("NÁVRHY LD · VLASTNÍ POZNÁMKY", asideX + 20, top + 38);
    ctx.fillStyle = muted; ctx.font = "17px DejaVu Web, sans-serif";
    pngText(ctx, state.ld_proposals || "Vlastní návrhy LD zatím nejsou doplněné.", asideX + 20, top + 75, asideW - 40, 27, 12);
    if (state.show_references && state.references.length) {
      for (let i = 0; i < state.references.length; i++) {
        const ref = state.references[i], image = new Image();
        image.src = ref.dataUrl;
        await new Promise((resolve) => { image.onload = resolve; image.onerror = resolve; });
        if (!image.naturalWidth) continue;
        const x = asideX + 20 + (i % 2) * (asideW / 2), y = top + 440 + Math.floor(i / 2) * 310;
        const w = asideW / 2 - 30, h = 280, scale = Math.min(w / image.width, h / image.height);
        ctx.drawImage(image, x, y, image.width * scale, image.height * scale);
        ctx.fillStyle = ink; ctx.font = "14px DejaVu Web, sans-serif"; ctx.fillText(ref.name.slice(0, 30), x, y + h + 20);
      }
    }
    drawPngFooter(ctx, canvas, 2);
  }
  async function exportPng() {
    const canvas = document.createElement("canvas");
    canvas.width = 3508; canvas.height = 2480;
    const ctx = canvas.getContext("2d");
    try {
      drawPngPageOne(ctx, canvas);
      const first = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
      if (!first) throw new Error("Stránku se nepodařilo vykreslit.");
      downloadBlob(first, safeFilename(state.metadata.title) + "_01_hudba.png");
      await drawPngPageTwo(ctx, canvas);
      const second = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
      if (!second) throw new Error("Stránku se nepodařilo vykreslit.");
      downloadBlob(second, safeFilename(state.metadata.title) + "_02_produkce.png");
      showToast("Exportovány dvě tiskové PNG stránky v rozlišení 300 dpi.");
    } catch (error) { showToast("PNG export selhal: " + error.message, 5000); }
  }

  function initialize() {
    restoreDraft();
    bindControls();
    renderAll();
    if (state.audioName) {
      $("#audioFileName").textContent = state.audioName;
      $("#audioFileMeta").textContent = "Waveform obnoven z lokálního pracovního stavu";
      waveformScroller.classList.add("has-audio");
    }
  }
  initialize();
})();
