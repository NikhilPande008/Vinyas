import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  AudioLines,
  BarChart3,
  CheckCircle2,
  ClipboardList,
  Cpu,
  Eye,
  FileCheck2,
  Gauge,
  Mic,
  MicOff,
  Play,
  RefreshCw,
  Send,
  ShieldAlert,
  Shuffle,
  Upload,
  Volume2,
  X,
} from 'lucide-react';
import { I18N } from './i18n';

const LINE_OPTIONS = [
  { id: 'PCB', short: 'Line A — PCB SMT', machine: 'SMT-REFLOW-CHAKAN-A1' },
  { id: 'CNC', short: 'Line B — CNC Spindle', machine: 'CNC-SPINDLE-CHAKAN-B2' },
  { id: 'WELD', short: 'Line C — MIG Weld', machine: 'MIG-ARC-BHOSARI-C3' },
];

const fmtMs = (val) => (typeof val === 'number' && !Number.isNaN(val) ? `${val} ms` : '—');

export default function App() {
  const [viewMode, setViewMode] = useState(() =>
    typeof window !== 'undefined' && window.innerWidth < 1024 ? 'operator' : 'engineer'
  );
  const [language, setLanguage] = useState('en-IN');
  const t = I18N[language] || I18N['en-IN'];

  const [selectedLine, setSelectedLine] = useState('CNC');
  const [drawnPart, setDrawnPart] = useState(null);
  const [uploadedPreview, setUploadedPreview] = useState(null);
  const [uploadTelemetryPreset, setUploadTelemetryPreset] = useState('nominal');

  const [inspection, setInspection] = useState(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [isInspecting, setIsInspecting] = useState(false);
  const [inspectError, setInspectError] = useState('');

  // Blind reveal & session tally
  const [revealed, setRevealed] = useState(null);
  const [sessionStats, setSessionStats] = useState({ correct: 0, total: 0 });
  const scoredSamplesRef = useRef(new Set());

  // Human disposition + Work Order
  const [dispRole, setDispRole] = useState('QE');
  const [dispNote, setDispNote] = useState('');
  const [disposition, setDisposition] = useState(null);
  const [isSavingDisp, setIsSavingDisp] = useState(false);

  const [woNotes, setWoNotes] = useState('');
  const [isLoggingWo, setIsLoggingWo] = useState(false);
  const [woError, setWoError] = useState('');
  const [workOrders, setWorkOrders] = useState([]);
  const [totalAvoidableLoss, setTotalAvoidableLoss] = useState(0);

  // Co-pilot (WebSocket primary -> REST fallback)
  const [copilotInput, setCopilotInput] = useState('');
  const [copilotMessages, setCopilotMessages] = useState([]);
  const [copilotTransport, setCopilotTransport] = useState('ws');
  const [isCopilotBusy, setIsCopilotBusy] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [voiceMessage, setVoiceMessage] = useState('');
  const wsRef = useRef(null);

  // Line Run batch & Metrics modal
  const [lineRunResult, setLineRunResult] = useState(null);
  const [isRunningBatch, setIsRunningBatch] = useState(false);
  const [metricsModalOpen, setMetricsModalOpen] = useState(false);
  const [metricsData, setMetricsData] = useState(null);

  const fileInputRef = useRef(null);

  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  const fetchWorkOrders = async () => {
    try {
      const res = await fetch('/api/work-orders');
      if (res.ok) {
        const data = await res.json();
        setWorkOrders(data.work_orders || []);
        setTotalAvoidableLoss(data.total_avoidable_loss_inr || 0);
      }
    } catch {
      // ignore transient startup errors
    }
  };

  const fetchMetrics = async () => {
    try {
      const res = await fetch('/api/metrics');
      if (res.ok) {
        setMetricsData(await res.json());
      }
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    fetchWorkOrders();
    fetchMetrics();
  }, []);

  // Draw random simulated part (no auto-inspection on load)
  const handleDrawRandom = async (lineOverride) => {
    const line = lineOverride || selectedLine;
    setSelectedLine(line);
    setIsDrawing(true);
    setInspectError('');
    setUploadedPreview(null);
    setInspection(null);
    setRevealed(null);
    setDisposition(null);
    setWoError('');
    try {
      const res = await fetch('/api/rig/draw', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ line }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setDrawnPart(data);
    } catch (err) {
      setInspectError(`Could not draw simulated part: ${err.message}`);
    } finally {
      setIsDrawing(false);
    }
  };

  const buildUploadTelemetry = (line, preset) => {
    if (preset === 'anomalous') {
      if (line === 'CNC') {
        return { vibration_khz: 0.793, vibration_rms_mms: 5.1, temperature_c: 62.0, line_speed_rpm: 5400 };
      }
      if (line === 'WELD') {
        return { vibration_khz: 0.9, vibration_rms_mms: 1.6, temperature_c: 320.0, line_speed_rpm: 1850, shielding_gas_lpm: 7.5, arc_voltage_v: 26.0, wire_feed_m_per_min: 8.4 };
      }
      return { vibration_khz: 0.4, vibration_rms_mms: 0.8, temperature_c: 254.0, line_speed_rpm: 1200, reflow_ramp_c_per_s: 3.6, reflow_peak_c: 254.0, reflow_tal_s: 72.0 };
    }
    if (line === 'CNC') {
      return { vibration_khz: 0.09, vibration_rms_mms: 0.9, temperature_c: 41.0, line_speed_rpm: 5400 };
    }
    if (line === 'WELD') {
      return { vibration_khz: 0.8, vibration_rms_mms: 1.3, temperature_c: 270.0, line_speed_rpm: 1850, shielding_gas_lpm: 17.0, arc_voltage_v: 22.0, wire_feed_m_per_min: 8.5 };
    }
    return { vibration_khz: 0.35, vibration_rms_mms: 0.7, temperature_c: 242.0, line_speed_rpm: 1200, reflow_ramp_c_per_s: 2.0, reflow_peak_c: 242.0, reflow_tal_s: 65.0 };
  };

  const handleInspect = async () => {
    setIsInspecting(true);
    setInspectError('');
    setRevealed(null);
    setDisposition(null);
    setWoError('');
    try {
      let body;
      if (uploadedPreview) {
        body = {
          line: selectedLine,
          custom_image_base64: uploadedPreview,
          sensor_telemetry: buildUploadTelemetry(selectedLine, uploadTelemetryPreset),
          language,
        };
      } else if (drawnPart) {
        body = { sample_id: drawnPart.sample_id, language };
      } else {
        body = { line: selectedLine, language };
      }
      const res = await fetch('/api/inspect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
      setInspection(data);
      fetchMetrics();
    } catch (err) {
      setInspectError(err.message || 'Inspection failed');
    } finally {
      setIsInspecting(false);
    }
  };

  const handleRevealTruth = async () => {
    const sid = inspection?.sample_id || drawnPart?.sample_id;
    if (!sid) return;
    try {
      const res = await fetch(`/api/rig/reveal/${sid}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
      setRevealed(data);
      if (inspection && !scoredSamplesRef.current.has(sid)) {
        scoredSamplesRef.current.add(sid);
        const sysEscalated = inspection.tier1_triage?.pass_status === 'ESCALATE';
        const isCorrect = Boolean(data.is_defect) === Boolean(sysEscalated);
        setSessionStats((prev) => ({
          correct: prev.correct + (isCorrect ? 1 : 0),
          total: prev.total + 1,
        }));
      }
    } catch (err) {
      setInspectError(err.message);
    }
  };

  const handlePhotoUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      setUploadedPreview(String(reader.result));
      setDrawnPart(null);
      setInspection(null);
      setRevealed(null);
      setDisposition(null);
    };
    reader.readAsDataURL(file);
  };

  const handleRecordDisposition = async (decision) => {
    if (!inspection?.incident_id) return;
    setIsSavingDisp(true);
    setWoError('');
    try {
      const res = await fetch(`/api/incidents/${inspection.incident_id}/disposition`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision, role: dispRole, note: dispNote }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
      setDisposition(data);
    } catch (err) {
      setWoError(err.message);
    } finally {
      setIsSavingDisp(false);
    }
  };

  const handleLogWorkOrder = async (e) => {
    e.preventDefault();
    if (!inspection?.incident_id || !woNotes.trim()) return;
    setIsLoggingWo(true);
    setWoError('');
    try {
      const lineObj = LINE_OPTIONS.find((l) => l.id === inspection.line) || LINE_OPTIONS[0];
      const res = await fetch('/api/work-orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          incident_id: inspection.incident_id,
          machine_id: lineObj.machine,
          operator_notes: woNotes.trim(),
          line: inspection.line,
          avoidable_loss_inr: inspection.tier2_diagnosis?.estimated_avoidable_loss_inr || 0,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
      setWoNotes('');
      await fetchWorkOrders();
    } catch (err) {
      setWoError(err.message);
    } finally {
      setIsLoggingWo(false);
    }
  };

  const playAudioOrTts = (resp) => {
    if (resp.audio_wav_base64) {
      try {
        const audio = new Audio(`data:audio/wav;base64,${resp.audio_wav_base64}`);
        audio.play().catch(() => {});
        return 'live-audio';
      } catch {
        // fallback below
      }
    }
    if (typeof window !== 'undefined' && 'speechSynthesis' in window && resp.answer) {
      try {
        const utter = new SpeechSynthesisUtterance(resp.answer);
        utter.lang = language;
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(utter);
        return 'device-tts';
      } catch {
        // ignore
      }
    }
    return 'text-only';
  };

  const sendCopilotQuestion = async (questionText) => {
    const q = (questionText || copilotInput).trim();
    if (!q) return;
    setCopilotInput('');
    setIsCopilotBusy(true);
    setCopilotMessages((prev) => [...prev, { role: 'user', text: q }]);

    const payload = {
      question: q,
      line: inspection?.line || selectedLine,
      incident_id: inspection?.incident_id || null,
      matched_sop_id: inspection?.tier2_diagnosis?.matched_sop_id || null,
      language,
    };

    const handleReply = (resp, transportUsed) => {
      const audioMode = playAudioOrTts(resp);
      setCopilotMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: resp.answer,
          model: resp.model_used || resp.producer,
          producer: resp.producer,
          sop: resp.grounded_sop_id,
          latency_ms: resp.latency_ms,
          unverified: resp.unverified_values || [],
          audioMode,
          transport: transportUsed,
        },
      ]);
      setIsCopilotBusy(false);
      fetchMetrics();
    };

    // Primary transport: WebSocket /api/live-copilot; automatic labelled fallback: REST /api/copilot/chat
    const tryRestFallback = async () => {
      setCopilotTransport('rest-fallback');
      try {
        const res = await fetch('/api/copilot/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
        handleReply(data, 'REST fallback');
      } catch (err) {
        setCopilotMessages((prev) => [
          ...prev,
          { role: 'assistant', text: `Co-pilot error: ${err.message}`, producer: 'FALLBACK_RULES' },
        ]);
        setIsCopilotBusy(false);
      }
    };

    try {
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${proto}//${window.location.host}/api/live-copilot`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      const timer = setTimeout(() => {
        if (ws.readyState !== WebSocket.OPEN) {
          ws.close();
          tryRestFallback();
        }
      }, 3000);

      ws.onopen = () => {
        clearTimeout(timer);
        setCopilotTransport('ws');
        ws.send(JSON.stringify(payload));
      };
      ws.onmessage = (evt) => {
        try {
          const data = JSON.parse(evt.data);
          handleReply(data, 'WebSocket');
        } finally {
          ws.close();
        }
      };
      ws.onerror = () => {
        clearTimeout(timer);
        ws.close();
        tryRestFallback();
      };
    } catch {
      tryRestFallback();
    }
  };

  const handleVoicePushToTalk = () => {
    setVoiceMessage('');
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRec) {
      setVoiceMessage(t.voiceUnsupported);
      return;
    }
    const rec = new SpeechRec();
    rec.lang = language;
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    setIsListening(true);
    rec.onresult = (e) => {
      const transcript = e.results?.[0]?.[0]?.transcript || '';
      setIsListening(false);
      if (transcript.trim()) {
        sendCopilotQuestion(transcript.trim());
      }
    };
    rec.onerror = () => {
      setIsListening(false);
      setVoiceMessage(t.voiceUnsupported);
    };
    rec.onend = () => setIsListening(false);
    rec.start();
  };

  const handleLineRun = async () => {
    setIsRunningBatch(true);
    setLineRunResult(null);
    setInspectError('');
    try {
      const res = await fetch('/api/line-run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ line: selectedLine, n: 10 }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
      setLineRunResult(data);
      fetchMetrics();
    } catch (err) {
      setInspectError(err.message);
    } finally {
      setIsRunningBatch(false);
    }
  };

  const diag = inspection?.tier2_diagnosis || null;
  const lossNotEstimated = Boolean(diag?.economics_basis?.startsWith('Not estimated'));
  const t1 = inspection?.tier1_triage || null;
  const tel = inspection?.telemetry || null;

  const verdictStyle = useMemo(() => {
    if (!t1) return null;
    if (t1.pass_status === 'HEALTHY') {
      return {
        label: t.passVerdict,
        bg: 'bg-emerald-950/80 border-emerald-500 text-emerald-100',
        icon: <CheckCircle2 className="w-8 h-8 text-emerald-400 shrink-0" />,
      };
    }
    if (diag?.severity === 'CRITICAL') {
      return {
        label: t.stopVerdict,
        bg: 'bg-rose-950/85 border-rose-500 text-rose-100',
        icon: <ShieldAlert className="w-8 h-8 text-rose-400 shrink-0" />,
      };
    }
    return {
      label: t.holdVerdict,
      bg: 'bg-amber-950/85 border-amber-500 text-amber-100',
      icon: <AlertTriangle className="w-8 h-8 text-amber-400 shrink-0" />,
    };
  }, [t1, diag, t]);

  const canLogWorkOrder =
    disposition && ['HOLD', 'REWORK', 'SCRAP'].includes(disposition.decision);

  const activeFrameUrl = inspection?.raw_image_url || drawnPart?.frame_url || uploadedPreview;
  const activeIsSimulated = inspection ? inspection.input_simulated : Boolean(drawnPart);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Header Bar */}
      <header className="border-b border-slate-800 bg-slate-900/95 px-4 py-3 sticky top-0 z-30">
        <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-sky-500/20 border border-sky-400/40 flex items-center justify-center">
              <Cpu className="w-6 h-6 text-sky-300" />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight text-white">{t.appTitle}</h1>
              <p className="text-xs text-slate-300">{t.appSubtitle}</p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* Session Tally */}
            {sessionStats.total > 0 && (
              <span className="px-3 py-1.5 rounded-full bg-indigo-950 border border-indigo-500/50 text-xs font-semibold text-indigo-200">
                {t.sessionTally(sessionStats.correct, sessionStats.total)}
              </span>
            )}

            {/* Language Switcher */}
            <div className="inline-flex rounded-lg border border-slate-700 bg-slate-950 p-0.5" role="group" aria-label="Language">
              {[
                { code: 'en-IN', label: 'EN' },
                { code: 'hi-IN', label: 'हिन्दी' },
                { code: 'mr-IN', label: 'मराठी' },
              ].map((lng) => (
                <button
                  key={lng.code}
                  type="button"
                  onClick={() => setLanguage(lng.code)}
                  className={`px-3 py-1.5 min-h-[36px] text-xs font-semibold rounded-md transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 ${
                    language === lng.code
                      ? 'bg-sky-500 text-slate-950'
                      : 'text-slate-300 hover:text-white'
                  }`}
                >
                  {lng.label}
                </button>
              ))}
            </div>

            {/* Operator / Engineer View Toggle */}
            <div className="inline-flex rounded-lg border border-slate-700 bg-slate-950 p-0.5" role="group" aria-label="View mode">
              <button
                type="button"
                onClick={() => setViewMode('operator')}
                className={`px-3 py-1.5 min-h-[36px] text-xs font-semibold rounded-md transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 ${
                  viewMode === 'operator' ? 'bg-emerald-500 text-slate-950' : 'text-slate-300 hover:text-white'
                }`}
              >
                {t.operatorView}
              </button>
              <button
                type="button"
                onClick={() => setViewMode('engineer')}
                className={`px-3 py-1.5 min-h-[36px] text-xs font-semibold rounded-md transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 ${
                  viewMode === 'engineer' ? 'bg-sky-500 text-slate-950' : 'text-slate-300 hover:text-white'
                }`}
              >
                {t.engineerView}
              </button>
            </div>

            {viewMode === 'engineer' && (
              <button
                type="button"
                onClick={() => {
                  fetchMetrics();
                  setMetricsModalOpen(true);
                }}
                className="px-3 py-1.5 min-h-[36px] rounded-lg border border-slate-700 bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-100 flex items-center gap-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400"
              >
                <BarChart3 className="w-4 h-4 text-sky-300" />
                Metrics
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 py-5 space-y-5">
        {/* Line Selector + Blind Draw / Upload Controls */}
        <section className="rounded-xl border border-slate-800 bg-slate-900/80 p-4 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {LINE_OPTIONS.map((lineObj) => {
              const active = selectedLine === lineObj.id;
              return (
                <button
                  key={lineObj.id}
                  type="button"
                  onClick={() => {
                    setSelectedLine(lineObj.id);
                    setDrawnPart(null);
                    setInspection(null);
                    setRevealed(null);
                    setDisposition(null);
                  }}
                  className={`text-left p-4 min-h-[56px] rounded-lg border transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 ${
                    active
                      ? 'border-sky-400 bg-sky-950/50 text-white'
                      : 'border-slate-700 bg-slate-950/60 text-slate-300 hover:border-slate-500'
                  }`}
                >
                  <div className="text-sm font-bold">{lineObj.short}</div>
                  <div className="text-xs text-slate-400 mt-0.5">{lineObj.machine}</div>
                </button>
              );
            })}
          </div>

          {selectedLine === 'CNC' && (
            <p className="text-xs text-sky-200 bg-sky-950/40 border border-sky-800/60 rounded-lg px-3 py-2">
              {t.cncNote}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => handleDrawRandom(selectedLine)}
              disabled={isDrawing}
              className="px-5 py-3 min-h-[48px] rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-950 font-bold text-sm flex items-center gap-2 transition disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
            >
              <Shuffle className="w-5 h-5" />
              {t.drawRandom}
            </button>

            <button
              type="button"
              onClick={handleInspect}
              disabled={isInspecting || (!drawnPart && !uploadedPreview)}
              className="px-5 py-3 min-h-[48px] rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-sm flex items-center gap-2 transition disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
            >
              {isInspecting ? <RefreshCw className="w-5 h-5 animate-spin" /> : <Play className="w-5 h-5" />}
              {t.inspectPart}
            </button>

            {inspection?.sample_id && (
              <button
                type="button"
                onClick={handleRevealTruth}
                className="px-4 py-3 min-h-[48px] rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-sm flex items-center gap-2 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
              >
                <Eye className="w-5 h-5" />
                {t.revealTruth}
              </button>
            )}

            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={handlePhotoUpload}
              className="hidden"
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="px-4 py-3 min-h-[48px] rounded-lg border border-slate-700 bg-slate-800 hover:bg-slate-700 text-slate-100 font-semibold text-sm flex items-center gap-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400"
            >
              <Upload className="w-4 h-4" />
              {t.uploadPhoto}
            </button>

            {uploadedPreview && (
              <label className="flex items-center gap-2 text-xs text-slate-300">
                Telemetry preset:
                <select
                  value={uploadTelemetryPreset}
                  onChange={(e) => setUploadTelemetryPreset(e.target.value)}
                  className="bg-slate-950 border border-slate-700 rounded-md px-2 py-1.5 text-xs text-slate-100"
                >
                  <option value="nominal">Nominal (default)</option>
                  <option value="anomalous">Anomalous</option>
                </select>
              </label>
            )}

            {viewMode === 'engineer' && (
              <button
                type="button"
                onClick={handleLineRun}
                disabled={isRunningBatch}
                className="ml-auto px-4 py-3 min-h-[48px] rounded-lg border border-amber-500/60 bg-amber-950/50 hover:bg-amber-900/60 text-amber-100 font-semibold text-sm flex items-center gap-2 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400"
              >
                <Gauge className="w-4 h-4" />
                {isRunningBatch ? 'Running batch...' : t.lineRunBtn}
              </button>
            )}
          </div>

          {inspectError && (
            <div className="p-3 rounded-lg bg-rose-950/80 border border-rose-500 text-rose-100 text-sm">
              {inspectError}
            </div>
          )}
        </section>

        {/* Empty State on First Visit */}
        {!drawnPart && !uploadedPreview && !inspection && (
          <section className="rounded-xl border border-dashed border-slate-700 bg-slate-900/50 p-10 text-center space-y-4">
            <h2 className="text-xl font-bold text-white">{t.emptyTitle}</h2>
            <p className="text-base text-slate-300 max-w-xl mx-auto">{t.emptyDesc}</p>
            <button
              type="button"
              onClick={() => handleDrawRandom(selectedLine)}
              className="px-6 py-3.5 min-h-[52px] rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-950 font-bold text-base inline-flex items-center gap-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
            >
              <Shuffle className="w-5 h-5" />
              {t.drawRandom}
            </button>
          </section>
        )}

        {/* Ground Truth Reveal Banner */}
        {revealed && (
          <section className="rounded-xl border border-indigo-500/60 bg-indigo-950/60 p-4 flex flex-wrap items-center justify-between gap-3">
            <div className="space-y-1">
              <div className="text-xs font-bold uppercase tracking-wider text-indigo-300">
                Ground Truth Revealed — {revealed.sample_id}
              </div>
              <div className="text-base font-bold text-white">
                {revealed.label} ({revealed.defect_type}) {revealed.severity !== 'none' ? `• severity: ${revealed.severity}` : ''}
              </div>
            </div>
            <span className="px-3 py-1 rounded-full text-xs font-bold bg-slate-900 border border-indigo-400/50 text-indigo-200">
              {Boolean(revealed.is_defect) === (t1?.pass_status === 'ESCALATE')
                ? '✔ Gate verdict matched ground truth'
                : '✘ Gate verdict differed from ground truth'}
            </span>
          </section>
        )}

        {/* ==================== OPERATOR VIEW ==================== */}
        {viewMode === 'operator' && (drawnPart || uploadedPreview || inspection) && (
          <div className="space-y-5 text-base">
            {/* Giant Verdict Card */}
            {verdictStyle && (
              <section
                aria-live="polite"
                className={`rounded-2xl border-2 p-6 flex items-center gap-4 ${verdictStyle.bg}`}
              >
                {verdictStyle.icon}
                <div className="space-y-1">
                  <div className="text-2xl font-extrabold tracking-tight">{verdictStyle.label}</div>
                  <div className="text-sm opacity-90">
                    {diag ? diag.root_cause_analysis : t1?.escalation_reason}
                  </div>
                  <div className="flex flex-wrap gap-2 pt-1">
                    <span className="px-2.5 py-1 rounded-full bg-slate-950/60 text-xs font-semibold">
                      {tel?.inference_mode === 'LIVE_MODEL' ? 'AI' : 'Rules'}
                    </span>
                    {activeIsSimulated && (
                      <span className="px-2.5 py-1 rounded-full bg-slate-950/60 text-xs font-semibold">
                        {t.simulatedChip}
                      </span>
                    )}
                  </div>
                </div>
              </section>
            )}

            {/* Frame Preview */}
            {activeFrameUrl && (
              <section className="rounded-xl border border-slate-800 bg-slate-900 p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-slate-200">
                    {drawnPart?.sample_id || inspection?.sample_id || 'Uploaded frame'}
                  </span>
                  {activeIsSimulated && (
                    <span className="px-2.5 py-1 rounded bg-amber-950 border border-amber-500/50 text-xs font-bold text-amber-200">
                      {t.simulatedChip}
                    </span>
                  )}
                </div>
                <img
                  src={inspection?.tier3_visual_sop_data_url || activeFrameUrl}
                  alt="Inspection part frame"
                  className="w-full max-h-80 object-contain rounded-lg bg-slate-950 border border-slate-800"
                />
                {inspection?.verdict_note && (
                  <p className="text-xs text-slate-300">{inspection.verdict_note}</p>
                )}
              </section>
            )}

            {/* SOP Repair Steps */}
            {diag && (
              <section className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-3">
                <h2 className="text-lg font-bold text-white flex items-center gap-2">
                  <ClipboardList className="w-5 h-5 text-sky-400" />
                  {t.sopSteps} ({diag.matched_sop_id})
                </h2>
                <ol className="list-decimal list-inside space-y-2.5 text-base text-slate-100">
                  {(diag.repair_steps_checked?.length
                    ? diag.repair_steps_checked
                    : diag.repair_steps.map((s) => ({ text: s, unverified: false, unverified_values: [] }))
                  ).map((step, idx) => (
                    <li key={idx} className="leading-relaxed">
                      <span>{step.text}</span>
                      {step.unverified && (
                        <span className="ml-2 inline-block px-2 py-0.5 rounded bg-amber-950 border border-amber-500 text-xs font-bold text-amber-200">
                          ⚠ {t.unverifiedWarn} ({step.unverified_values.join(', ')})
                        </span>
                      )}
                    </li>
                  ))}
                </ol>
              </section>
            )}

            {/* Push-to-Talk Co-Pilot (Operator View) */}
            <section className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-bold text-white flex items-center gap-2">
                  <Volume2 className="w-5 h-5 text-sky-400" />
                  {t.copilotTitle}
                </h2>
                <button
                  type="button"
                  onClick={handleVoicePushToTalk}
                  aria-label={t.pushToTalk}
                  className={`min-h-[64px] min-w-[64px] px-5 rounded-full font-bold text-base flex items-center gap-2 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white ${
                    isListening
                      ? 'bg-rose-500 text-white animate-pulse'
                      : 'bg-sky-500 hover:bg-sky-400 text-slate-950'
                  }`}
                >
                  {isListening ? <MicOff className="w-6 h-6" /> : <Mic className="w-6 h-6" />}
                  {isListening ? t.listening : t.pushToTalk}
                </button>
              </div>
              {voiceMessage && <p className="text-sm text-amber-300">{voiceMessage}</p>}
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  sendCopilotQuestion();
                }}
                className="flex gap-2"
              >
                <input
                  type="text"
                  value={copilotInput}
                  onChange={(e) => setCopilotInput(e.target.value)}
                  placeholder={t.askPlaceholder}
                  className="flex-1 min-h-[48px] px-4 rounded-lg bg-slate-950 border border-slate-700 text-base text-white"
                />
                <button
                  type="submit"
                  disabled={isCopilotBusy}
                  aria-label={t.send}
                  className="px-5 min-h-[48px] rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-950 font-bold text-sm"
                >
                  <Send className="w-5 h-5" />
                </button>
              </form>
              {copilotMessages.slice(-2).map((m, i) => (
                <div
                  key={i}
                  className={`p-3 rounded-lg text-base ${
                    m.role === 'user' ? 'bg-slate-800 text-slate-100' : 'bg-sky-950/60 border border-sky-700/60 text-sky-100'
                  }`}
                >
                  {m.text}
                </div>
              ))}
            </section>
          </div>
        )}

        {/* ==================== ENGINEER VIEW (3-COLUMN) ==================== */}
        {viewMode === 'engineer' && (drawnPart || uploadedPreview || inspection) && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
            {/* Column 1: Simulated Frame, Signal, Envelope Spectrum & Gate Votes */}
            <div className="lg:col-span-4 space-y-4">
              <section className="rounded-xl border border-slate-800 bg-slate-900 p-4 space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <h2 className="text-sm font-bold text-white">1. Input Frame &amp; Telemetry</h2>
                  {activeIsSimulated ? (
                    <span className="px-2.5 py-0.5 rounded bg-amber-950 border border-amber-500/60 text-xs font-bold text-amber-200">
                      {t.simulatedChip}
                    </span>
                  ) : (
                    <span className="px-2.5 py-0.5 rounded bg-sky-950 border border-sky-500/60 text-xs font-bold text-sky-200">
                      USER UPLOAD
                    </span>
                  )}
                </div>

                {activeFrameUrl && (
                  <img
                    src={activeFrameUrl}
                    alt="Raw inspection frame"
                    className="w-full rounded-lg border border-slate-800 bg-slate-950"
                  />
                )}

                {inspection?.verdict_note && (
                  <p className="text-xs text-sky-200 bg-sky-950/40 p-2 rounded border border-sky-800/50">
                    {inspection.verdict_note}
                  </p>
                )}

                {(inspection?.audio_url || drawnPart?.wav_url) && (
                  <div className="space-y-1">
                    <div className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                      <AudioLines className="w-4 h-4 text-sky-400" />
                      48 kHz Vibration Signal (Simulated)
                    </div>
                    <audio
                      controls
                      src={inspection?.audio_url || drawnPart?.wav_url}
                      className="w-full h-9"
                    />
                  </div>
                )}

                {inspection?.envelope_spectrum_data_url && (
                  <div className="space-y-1">
                    <div className="text-xs font-semibold text-slate-300">
                      Tier-1A Hilbert Envelope Spectrum (2–8 kHz bandpass)
                    </div>
                    <img
                      src={inspection.envelope_spectrum_data_url}
                      alt="Hilbert envelope spectrum"
                      className="w-full rounded-lg border border-slate-800"
                    />
                  </div>
                )}

                {/* Sensor Telemetry Readout */}
                <div className="grid grid-cols-2 gap-2 text-xs">
                  {Object.entries(inspection?.sensor_telemetry || drawnPart?.telemetry || {})
                    .filter(([, v]) => v !== null && v !== undefined)
                    .map(([k, v]) => (
                      <div key={k} className="p-2 rounded bg-slate-950 border border-slate-800">
                        <div className="text-slate-400">{k}</div>
                        <div className="font-mono font-bold text-slate-100">{String(v)}</div>
                      </div>
                    ))}
                </div>
              </section>

              {/* Tier-1 Combined Gate Card */}
              {t1 && (
                <section className="rounded-xl border border-slate-800 bg-slate-900 p-4 space-y-2.5" aria-live="polite">
                  <div className="flex items-center justify-between">
                    <h2 className="text-sm font-bold text-white">Tier-1 Gate Verdict</h2>
                    <span
                      className={`px-2.5 py-1 rounded-full text-xs font-bold ${
                        t1.pass_status === 'HEALTHY'
                          ? 'bg-emerald-950 text-emerald-300 border border-emerald-500/60'
                          : 'bg-amber-950 text-amber-200 border border-amber-500/60'
                      }`}
                    >
                      {t1.pass_status}
                    </span>
                  </div>
                  <div className="text-xs space-y-1.5 text-slate-200">
                    <div>
                      <strong>Signal gate (DSP):</strong>{' '}
                      {t1.t1a_flags?.length ? `⚠ ${t1.t1a_flags.join(', ')}` : '✓ nominal'} ({fmtMs(tel?.t1a_ms)})
                    </div>
                    <div>
                      <strong>Visual gate ({t1.provenance_t1b?.model_id || t1.provenance_t1b?.producer}):</strong>{' '}
                      {t1.t1b_vote === 'NOMINAL' ? '✓ NOMINAL' : `⚠ ${t1.t1b_vote}`} ({fmtMs(tel?.t1b_ms)})
                    </div>
                    <p className="text-slate-300 pt-1">{t1.escalation_reason}</p>
                  </div>
                </section>
              )}
            </div>

            {/* Column 2: Tier-2 Root Cause, SOP Guard, Tier-3 Overlay & Provenance */}
            <div className="lg:col-span-4 space-y-4">
              {diag ? (
                <>
                  <section className="rounded-xl border border-slate-800 bg-slate-900 p-4 space-y-3">
                    <div className="flex items-center justify-between gap-2">
                      <h2 className="text-sm font-bold text-white">2. Tier-2 Root-Cause Diagnosis</h2>
                      <span className="px-2 py-0.5 rounded bg-sky-950 border border-sky-500/50 text-xs font-mono text-sky-200">
                        {tel?.tier2_model_used || 'RULE-BASED'}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-2 text-xs">
                      <span className="px-2.5 py-1 rounded bg-slate-950 border border-slate-700 font-bold text-white">
                        {diag.defect_type}
                      </span>
                      <span className="px-2.5 py-1 rounded bg-rose-950/70 border border-rose-500/50 font-bold text-rose-200">
                        {diag.severity}
                      </span>
                      <span className="px-2.5 py-1 rounded bg-slate-950 border border-slate-700 text-slate-300">
                        SOP: {diag.matched_sop_id}
                      </span>
                    </div>
                    <p className="text-sm text-slate-200 leading-relaxed">{diag.root_cause_analysis}</p>

                    {/* Evidence */}
                    {diag.evidence?.length > 0 && (
                      <div className="space-y-1">
                        <div className="text-xs font-bold text-slate-300">Evidence</div>
                        <ul className="space-y-1 text-xs text-slate-300">
                          {diag.evidence.map((ev, i) => (
                            <li key={i} className="bg-slate-950 p-2 rounded border border-slate-800">
                              <span className="font-mono text-sky-300">[{ev.source}]</span> {ev.observation}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* SOP-Guarded Repair Steps */}
                    <div className="space-y-1.5">
                      <div className="text-xs font-bold text-slate-300 flex items-center justify-between">
                        <span>Repair Steps (SOP-Guarded)</span>
                        {diag.unverified_value_count > 0 && (
                          <span className="text-amber-300">
                            ⚠ {diag.unverified_value_count} unverified value(s)
                          </span>
                        )}
                      </div>
                      <ol className="list-decimal list-inside space-y-1.5 text-xs text-slate-200">
                        {(diag.repair_steps_checked?.length
                          ? diag.repair_steps_checked
                          : diag.repair_steps.map((s) => ({ text: s, unverified: false, unverified_values: [] }))
                        ).map((step, i) => (
                          <li key={i} className="leading-relaxed">
                            {step.text}
                            {step.unverified && (
                              <span className="ml-1.5 px-1.5 py-0.5 rounded bg-amber-950 border border-amber-500 text-amber-200 font-semibold">
                                ⚠ {t.unverifiedWarn} ({step.unverified_values.join(', ')})
                              </span>
                            )}
                          </li>
                        ))}
                      </ol>
                    </div>

                    {/* Deterministic Assumption-Based Economics */}
                    <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 flex items-center justify-between">
                      <div>
                        <div className="text-xs text-slate-400">{t.avoidableLossLabel}</div>
                        {!lossNotEstimated && (
                          <div className="text-xs text-slate-500">
                            {diag.estimated_downtime_prevented_mins} min est. downtime avoided
                          </div>
                        )}
                      </div>
                      {lossNotEstimated ? (
                        <div className="text-sm font-semibold text-slate-300">{t.lossNotEstimated}</div>
                      ) : (
                        <div className="text-lg font-extrabold font-mono text-emerald-300">
                          ₹{Number(diag.estimated_avoidable_loss_inr || 0).toLocaleString('en-IN')}
                        </div>
                      )}
                    </div>
                  </section>

                  {/* Tier-3 Deterministic Visual Repair Overlay */}
                  {inspection?.tier3_visual_sop_data_url && (
                    <section className="rounded-xl border border-slate-800 bg-slate-900 p-4 space-y-2">
                      <div className="flex items-center justify-between gap-2">
                        <h2 className="text-sm font-bold text-white">3. Tier-3 Visual Repair Card</h2>
                        <span className="text-xs text-slate-300 font-mono">
                          {inspection.tier3_render_mode}
                        </span>
                      </div>
                      <img
                        src={inspection.tier3_visual_sop_data_url}
                        alt="Visual repair overlay"
                        className="w-full rounded-lg border border-slate-800"
                      />
                    </section>
                  )}
                </>
              ) : (
                t1 && (
                  <section className="rounded-xl border border-emerald-700/50 bg-emerald-950/30 p-5 space-y-2">
                    <h2 className="text-base font-bold text-emerald-200">
                      Short-circuited at Tier-1 (HEALTHY)
                    </h2>
                    <p className="text-sm text-slate-300">
                      Tier-2 root-cause diagnosis and Tier-3 overlay were skipped (0 Tier-2 tokens used).
                    </p>
                  </section>
                )
              )}

              {/* Retrieved SOPs + Provenance Attempts Trace */}
              {inspection && (
                <section className="rounded-xl border border-slate-800 bg-slate-900 p-4 space-y-3">
                  <h2 className="text-sm font-bold text-white">Stage Latencies &amp; Provenance</h2>
                  <div className="grid grid-cols-3 gap-2 text-xs">
                    <div className="p-2 rounded bg-slate-950 border border-slate-800">
                      <div className="text-slate-400">T1-A DSP</div>
                      <div className="font-mono font-bold text-white">{fmtMs(tel?.t1a_ms)}</div>
                    </div>
                    <div className="p-2 rounded bg-slate-950 border border-slate-800">
                      <div className="text-slate-400">T1-B Gate</div>
                      <div className="font-mono font-bold text-white">{fmtMs(tel?.t1b_ms)}</div>
                    </div>
                    <div className="p-2 rounded bg-slate-950 border border-slate-800">
                      <div className="text-slate-400">Retrieval</div>
                      <div className="font-mono font-bold text-white">{fmtMs(tel?.retrieval_ms)}</div>
                    </div>
                    <div className="p-2 rounded bg-slate-950 border border-slate-800">
                      <div className="text-slate-400">T2 Diag</div>
                      <div className="font-mono font-bold text-white">{fmtMs(tel?.tier2_ms)}</div>
                    </div>
                    <div className="p-2 rounded bg-slate-950 border border-slate-800">
                      <div className="text-slate-400">T3 Overlay</div>
                      <div className="font-mono font-bold text-white">{fmtMs(tel?.tier3_ms)}</div>
                    </div>
                    <div className="p-2 rounded bg-slate-950 border border-slate-800">
                      <div className="text-slate-400">Total</div>
                      <div className="font-mono font-bold text-sky-300">{fmtMs(tel?.total_ms)}</div>
                    </div>
                  </div>

                  {inspection.matched_sops?.length > 0 && (
                    <div className="space-y-1">
                      <div className="text-xs font-bold text-slate-300">
                        Retrieved SOPs ({tel?.retrieval_mode})
                      </div>
                      {inspection.matched_sops.map((s) => (
                        <div key={s.id} className="text-xs p-2 rounded bg-slate-950 border border-slate-800 flex justify-between gap-2">
                          <span className="font-mono text-sky-300">{s.id}</span>
                          <span className="text-slate-300 truncate">{s.title}</span>
                          <span className="font-mono text-emerald-300 shrink-0">{s.similarity_score}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  <details className="text-xs">
                    <summary className="cursor-pointer text-sky-300 font-semibold">
                      Attempts trace ({inspection.provenance?.length || 0} stages)
                    </summary>
                    <div className="mt-2 space-y-1.5">
                      {(inspection.provenance || []).map((p, idx) => (
                        <div key={idx} className="p-2 rounded bg-slate-950 border border-slate-800 space-y-1">
                          <div className="flex justify-between font-mono">
                            <span className="text-white">{p.stage}</span>
                            <span className="text-slate-300">
                              {p.model_id || p.producer} • {p.latency_ms} ms
                            </span>
                          </div>
                          {p.attempts?.length > 0 && (
                            <div className="text-slate-400 font-mono">
                              {p.attempts
                                .map((a) => `${a.model_id} → ${a.status} (${a.latency_ms} ms)`)
                                .join(' · ')}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </details>
                </section>
              )}
            </div>

            {/* Column 3: Co-Pilot, Line Run & Work Order Ledger */}
            <div className="lg:col-span-4 space-y-4">
              {/* Tier-4 Co-Pilot */}
              <section className="rounded-xl border border-slate-800 bg-slate-900 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-bold text-white flex items-center gap-1.5">
                    <Volume2 className="w-4 h-4 text-sky-400" />
                    4. {t.copilotTitle}
                  </h2>
                  <span className="text-xs font-mono text-slate-400">
                    {copilotTransport === 'ws' ? 'WS /api/live-copilot' : 'REST fallback'}
                  </span>
                </div>

                <div className="h-52 overflow-y-auto space-y-2 p-2 rounded-lg bg-slate-950 border border-slate-800">
                  {copilotMessages.length === 0 && (
                    <p className="text-xs text-slate-400 p-2">
                      Ask a question in EN, हिन्दी, or मराठी grounded in the retrieved SOP.
                    </p>
                  )}
                  {copilotMessages.map((m, idx) => (
                    <div
                      key={idx}
                      className={`p-2.5 rounded-lg text-xs space-y-1 ${
                        m.role === 'user'
                          ? 'bg-slate-800 text-slate-100 ml-6'
                          : 'bg-sky-950/60 border border-sky-800/60 text-sky-100 mr-4'
                      }`}
                    >
                      <div>{m.text}</div>
                      {m.role === 'assistant' && (
                        <div className="text-slate-400 font-mono flex flex-wrap gap-2 pt-1">
                          <span>{m.model}</span>
                          {m.latency_ms !== undefined && <span>• {m.latency_ms} ms</span>}
                          {m.audioMode === 'live-audio' && <span>• Live audio</span>}
                          {m.audioMode === 'device-tts' && <span>• Text fallback + device TTS</span>}
                        </div>
                      )}
                      {m.unverified?.length > 0 && (
                        <div className="text-amber-300 font-semibold">
                          ⚠ {t.unverifiedWarn}: {m.unverified.join(', ')}
                        </div>
                      )}
                    </div>
                  ))}
                </div>

                {voiceMessage && <p className="text-xs text-amber-300">{voiceMessage}</p>}

                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    sendCopilotQuestion();
                  }}
                  className="flex gap-2"
                >
                  <button
                    type="button"
                    onClick={handleVoicePushToTalk}
                    aria-label={t.pushToTalk}
                    className={`min-h-[44px] min-w-[44px] rounded-lg flex items-center justify-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 ${
                      isListening ? 'bg-rose-500 text-white' : 'bg-slate-800 hover:bg-slate-700 text-sky-300'
                    }`}
                  >
                    {isListening ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
                  </button>
                  <input
                    type="text"
                    value={copilotInput}
                    onChange={(e) => setCopilotInput(e.target.value)}
                    placeholder={t.askPlaceholder}
                    className="flex-1 min-h-[44px] px-3 rounded-lg bg-slate-950 border border-slate-700 text-xs text-white"
                  />
                  <button
                    type="submit"
                    disabled={isCopilotBusy}
                    aria-label={t.send}
                    className="px-3.5 min-h-[44px] rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-950 font-bold text-xs"
                  >
                    <Send className="w-4 h-4" />
                  </button>
                </form>
              </section>

              {/* Line Run Measured Token Accounting */}
              {lineRunResult && (
                <section className="rounded-xl border border-amber-500/50 bg-amber-950/30 p-4 space-y-2 text-xs">
                  <div className="font-bold text-amber-200 flex items-center justify-between">
                    <span>Batch Line Run ({lineRunResult.line}, N={lineRunResult.parts_inspected})</span>
                    <span className="font-mono">{fmtMs(lineRunResult.elapsed_ms)}</span>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="p-2 rounded bg-slate-950 border border-slate-800">
                      <div className="text-slate-400">Escalated</div>
                      <div className="font-mono font-bold text-white">
                        {lineRunResult.escalated_count} / {lineRunResult.parts_inspected} ({lineRunResult.escalation_rate_pct}%)
                      </div>
                    </div>
                    <div className="p-2 rounded bg-slate-950 border border-slate-800">
                      <div className="text-slate-400">Token effect of the gate</div>
                      <div
                        className={`font-mono font-bold ${
                          lineRunResult.measured_token_saving_pct !== null && lineRunResult.measured_token_saving_pct < 0 ? 'text-amber-300' : 'text-emerald-300'
                        }`}
                      >
                        {lineRunResult.measured_token_saving_pct !== null
                          ? `${lineRunResult.measured_token_saving_pct > 0 ? '−' : '+'}${Math.abs(lineRunResult.measured_token_saving_pct)}% tokens`
                          : '—'}
                      </div>
                    </div>
                    <div className="p-2 rounded bg-slate-950 border border-slate-800">
                      <div className="text-slate-400">Gated Tokens</div>
                      <div className="font-mono text-white">{lineRunResult.gated_tokens.toLocaleString()}</div>
                    </div>
                    <div className="p-2 rounded bg-slate-950 border border-slate-800">
                      <div className="text-slate-400">Est. Cloud-Only</div>
                      <div className="font-mono text-white">
                        {lineRunResult.cloud_only_estimated_tokens.toLocaleString()}
                      </div>
                    </div>
                  </div>
                  <p className="text-slate-300">{lineRunResult.note}</p>
                </section>
              )}
            </div>
          </div>
        )}

        {/* ==================== HUMAN DISPOSITION + WORK ORDER (BOTH VIEWS) ==================== */}
        {inspection && (
          <section className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <FileCheck2 className="w-5 h-5 text-emerald-400" />
                {t.dispositionTitle} — <span className="font-mono text-sky-300">{inspection.incident_id}</span>
              </h2>
              <span className="text-xs text-slate-300">
                {t.aiRecommends}:{' '}
                <strong className="text-amber-300">
                  {diag?.recommended_disposition || (t1?.pass_status === 'HEALTHY' ? 'RELEASE' : 'HOLD')}
                </strong>
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <label className="text-xs text-slate-300 flex items-center gap-2">
                {t.roleLabel}:
                <select
                  value={dispRole}
                  onChange={(e) => setDispRole(e.target.value)}
                  className="bg-slate-950 border border-slate-700 rounded-md px-3 py-2 text-xs text-white"
                >
                  <option value="QE">QE</option>
                  <option value="Supervisor">Supervisor</option>
                </select>
              </label>

              <input
                type="text"
                value={dispNote}
                onChange={(e) => setDispNote(e.target.value)}
                placeholder="Optional disposition note..."
                className="flex-1 min-w-[200px] min-h-[44px] px-3 rounded-lg bg-slate-950 border border-slate-700 text-xs text-white"
              />

              <div className="flex flex-wrap gap-2">
                {['RELEASE', 'HOLD', 'REWORK', 'SCRAP'].map((dec) => (
                  <button
                    key={dec}
                    type="button"
                    disabled={isSavingDisp}
                    onClick={() => handleRecordDisposition(dec)}
                    className={`px-4 py-2.5 min-h-[44px] rounded-lg font-bold text-xs border transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white ${
                      disposition?.decision === dec
                        ? 'bg-emerald-500 text-slate-950 border-emerald-400'
                        : 'bg-slate-800 hover:bg-slate-700 text-white border-slate-600'
                    }`}
                  >
                    {dec}
                  </button>
                ))}
              </div>
            </div>

            {disposition && (
              <div className="text-xs text-emerald-300 bg-emerald-950/40 border border-emerald-700/50 rounded-lg px-3 py-2">
                Recorded: <strong>{disposition.decision}</strong> by <strong>{disposition.role}</strong> at{' '}
                {disposition.recorded_at}
              </div>
            )}

            {/* Work Order Form (unlocked ONLY after HOLD/REWORK/SCRAP) */}
            {canLogWorkOrder ? (
              <form onSubmit={handleLogWorkOrder} className="space-y-3 pt-2 border-t border-slate-800">
                <textarea
                  rows={2}
                  value={woNotes}
                  onChange={(e) => setWoNotes(e.target.value)}
                  placeholder="Enter operator note in English, Hindi, or Marathi (Gemini extracts part_code, priority, spares & SLA risk)..."
                  className="w-full p-3 rounded-lg bg-slate-950 border border-slate-700 text-sm text-white"
                />
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs text-slate-400">{t.demoStoreNote}</span>
                  <button
                    type="submit"
                    disabled={isLoggingWo || !woNotes.trim()}
                    className="px-5 py-2.5 min-h-[44px] rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-sm disabled:opacity-50"
                  >
                    {isLoggingWo ? 'Logging...' : t.logWorkOrder}
                  </button>
                </div>
              </form>
            ) : (
              <p className="text-xs text-slate-400 pt-1">{t.unlockHint}</p>
            )}

            {woError && <p className="text-xs text-rose-300">{woError}</p>}
          </section>
        )}

        {/* Work Order Ledger */}
        <section className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-base font-bold text-white">{t.ledgerTitle}</h2>
              <p className="text-xs text-slate-400">{t.demoStoreNote}</p>
            </div>
            <div className="text-right">
              <div className="text-xs text-slate-400">Estimated avoidable loss logged (assumptions)</div>
              <div className="text-lg font-extrabold font-mono text-emerald-300">
                ₹{Number(totalAvoidableLoss).toLocaleString('en-IN')}
              </div>
            </div>
          </div>

          {workOrders.length === 0 ? (
            <p className="text-xs text-slate-400">No work orders logged yet in this demo session.</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {workOrders.slice(0, 6).map((wo) => (
                <div key={wo.id} className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-xs space-y-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono font-bold text-sky-300">{wo.id}</span>
                    <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-200 font-mono">
                      {wo.extraction_model_id || wo.extraction_producer}
                    </span>
                  </div>
                  <p className="text-slate-200">{wo.operator_notes}</p>
                  <div className="flex flex-wrap gap-2 text-slate-300">
                    <span>SKU: <strong>{wo.extracted_tags_json?.part_code}</strong></span>
                    <span>Priority: <strong>{wo.extracted_tags_json?.shift_priority}</strong></span>
                    {wo.sla_critical_flag && (
                      <span className="text-rose-300 font-bold">SLA RISK</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </main>

      {/* Metrics Modal */}
      {metricsModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-2xl w-full p-5 space-y-4 max-h-[85vh] overflow-y-auto">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <Activity className="w-5 h-5 text-sky-400" />
                Live Model Health &amp; Routing Config (/api/metrics)
              </h2>
              <button
                type="button"
                onClick={() => setMetricsModalOpen(false)}
                aria-label="Close metrics modal"
                className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {metricsData?.routing_config && (
              <div className="text-xs space-y-1">
                <div className="font-bold text-slate-300">Active Routing Config</div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                  {Object.entries(metricsData.routing_config).map(([k, v]) => (
                    <div key={k} className="p-2 rounded bg-slate-950 border border-slate-800 font-mono">
                      <span className="text-slate-400">{k}:</span>{' '}
                      <span className="text-sky-300">{String(v)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="text-xs space-y-1">
              <div className="font-bold text-slate-300">Per-Model Counters Since Startup</div>
              {metricsData?.models && Object.keys(metricsData.models).length > 0 ? (
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-slate-700 text-slate-400">
                      <th className="py-1.5">Model / Stage</th>
                      <th className="py-1.5">OK</th>
                      <th className="py-1.5">Fallback</th>
                      <th className="py-1.5">Errors</th>
                      <th className="py-1.5">p50</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(metricsData.models).map(([m, st]) => (
                      <tr key={m} className="border-b border-slate-800 font-mono">
                        <td className="py-1.5 text-sky-300">{m}</td>
                        <td className="py-1.5 text-emerald-300">{st.ok}</td>
                        <td className="py-1.5 text-amber-300">{st.fallback}</td>
                        <td className="py-1.5 text-rose-300">{st.errors}</td>
                        <td className="py-1.5 text-slate-200">{fmtMs(st.p50_ms)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="text-slate-400">No model calls recorded yet since server startup.</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
