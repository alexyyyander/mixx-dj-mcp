import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  Bot,
  CheckCircle2,
  Clock3,
  FileAudio,
  Loader2,
  LockKeyhole,
  Play,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Tags,
  Waves,
  XCircle,
} from "lucide-react";
import {
  analyzeAiDj,
  applyAiDjMarkers,
  createAiDjPlan,
  executeAiDj,
  fetchAiDjJob,
  fetchAiDjMarkers,
  fetchAiDjProfiles,
  fetchAiDjStatus,
  type AiDjJob,
  type AiDjMarker,
  type AiDjMarkerMap,
  type AiDjPlanResponse,
  type AiDjProfileSummary,
  type AiDjStatusResponse,
} from "../lib/api";

function formatTime(seconds: number) {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60).toString().padStart(2, "0");
  return `${mins}:${secs}`;
}

function markerPosition(marker: AiDjMarker, duration: number) {
  return `${Math.max(0, Math.min(100, (marker.time_seconds / Math.max(duration, 0.1)) * 100))}%`;
}

function statusTone(status: AiDjStatusResponse | null) {
  if (!status) return "text-slate-500";
  if (status.bridge.connected) return "text-emerald-400";
  if (status.bridge.reachable) return "text-amber-400";
  return "text-slate-500";
}

export default function AiDj() {
  const [status, setStatus] = useState<AiDjStatusResponse | null>(null);
  const [profiles, setProfiles] = useState<AiDjProfileSummary[]>([]);
  const [fromTrack, setFromTrack] = useState("");
  const [toTrack, setToTrack] = useState("");
  const [deckOut, setDeckOut] = useState(1);
  const [deckIn, setDeckIn] = useState(2);
  const [durationBeats, setDurationBeats] = useState(32);
  const [markerMap, setMarkerMap] = useState<AiDjMarkerMap | null>(null);
  const [plan, setPlan] = useState<AiDjPlanResponse | null>(null);
  const [job, setJob] = useState<AiDjJob | null>(null);
  const [audioPath, setAudioPath] = useState("");
  const [device, setDevice] = useState<"cpu" | "cuda" | "mps">("cpu");
  const [armed, setArmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedFrom = useMemo(
    () => profiles.find((profile) => profile.track_id === fromTrack),
    [profiles, fromTrack],
  );
  const selectedTo = useMemo(
    () => profiles.find((profile) => profile.track_id === toTrack),
    [profiles, toTrack],
  );

  const load = useCallback(async () => {
    setError(null);
    try {
      const [nextStatus, nextProfiles] = await Promise.all([
        fetchAiDjStatus(),
        fetchAiDjProfiles(),
      ]);
      setStatus(nextStatus);
      setProfiles(nextProfiles.profiles);
      setFromTrack((value) => value || nextProfiles.profiles[0]?.track_id || "");
      setToTrack((value) => value || nextProfiles.profiles[1]?.track_id || nextProfiles.profiles[0]?.track_id || "");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "AI DJ backend unavailable");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!fromTrack) return;
    setMarkerMap(null);
    fetchAiDjMarkers(fromTrack, deckOut)
      .then((result) => setMarkerMap(result.marker_map))
      .catch((cause) => setError(cause instanceof Error ? cause.message : "Unable to load marker map"));
  }, [fromTrack, deckOut]);

  useEffect(() => {
    if (!job || ["complete", "failed", "cancelled"].includes(job.status)) return;
    const timer = window.setInterval(() => {
      fetchAiDjJob(job.job_id)
        .then((nextJob) => {
          setJob(nextJob);
          if (nextJob.kind === "analysis" && nextJob.status === "complete") {
            fetchAiDjProfiles().then((result) => setProfiles(result.profiles)).catch(() => undefined);
          }
        })
        .catch(() => undefined);
    }, 900);
    return () => window.clearInterval(timer);
  }, [job]);

  const runAnalysis = async () => {
    if (!audioPath.trim()) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await analyzeAiDj({ audio_path: audioPath.trim(), device });
      setJob(result.job);
      setNotice("分析任务已排队；完成后刷新 profile 列表即可看到新的节拍、段落、调性和 stems。");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "无法启动分析");
    } finally {
      setBusy(false);
    }
  };

  const createPlan = async () => {
    if (!fromTrack || !toTrack || fromTrack === toTrack) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const nextPlan = await createAiDjPlan({
        from_track_id: fromTrack,
        to_track_id: toTrack,
        duration_beats: durationBeats,
        deck_out: deckOut,
        deck_in: deckIn,
      });
      setPlan(nextPlan);
      setNotice("转场计划已生成。相对 beat 只用于可审计预演，未宣称 HTTP 具备采样级调度能力。");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "无法生成转场计划");
    } finally {
      setBusy(false);
    }
  };

  const applyMarkers = async () => {
    if (!fromTrack || !armed) return;
    setBusy(true);
    setError(null);
    try {
      const result = await applyAiDjMarkers({ track_id: fromTrack, deck: deckOut, confirm: true, wait_ms: 1000 });
      setNotice(result.message || "Hotcue 已提交");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Hotcue 写入失败");
    } finally {
      setBusy(false);
    }
  };

  const executePlan = async () => {
    if (!fromTrack || !toTrack || !armed) return;
    setBusy(true);
    setError(null);
    try {
      const result = await executeAiDj({
        from_track_id: fromTrack,
        to_track_id: toTrack,
        duration_beats: durationBeats,
        deck_out: deckOut,
        deck_in: deckIn,
        confirm: true,
        wait_ms: 1000,
      });
      if (result.job) setJob(result.job);
      setNotice(result.message);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "自动转场未启动");
    } finally {
      setBusy(false);
    }
  };

  const liveReady = Boolean(status?.live_control_enabled && status.bridge.connected);
  const jobProgress = job?.request_count
    ? Math.round(((job.completed_requests || 0) / job.request_count) * 100)
    : 0;

  return (
    <div className="space-y-5" data-testid="ai-dj-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-2">
            <Bot className="text-amber-400" size={22} />
            <h2 className="text-xl font-semibold text-slate-100">AI DJ Control Room</h2>
          </div>
          <p className="text-sm text-slate-500 mt-1 max-w-3xl">
            分析后的 BPM、调性、段落、vocal/stems 和 DJ tag 在这里汇合；Agent 只通过带 ACK 的 API Bridge 触碰 Mixxx。
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-700 text-xs text-slate-300 hover:bg-slate-800"
        >
          <RefreshCw size={14} /> 刷新
        </button>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1.1fr_1fr] gap-5">
        <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
              <Activity size={16} className={statusTone(status)} /> Pipeline status
            </div>
            <span className={`text-xs ${statusTone(status)}`}>
              {status?.bridge.connected ? "Bridge + Mixxx connected" : status?.bridge.reachable ? "Bridge reachable / Mixxx off" : "Bridge offline"}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div className="rounded-lg bg-slate-950/70 p-3">
              <p className="text-slate-500">AI DJ profiles</p>
              <p className="text-lg font-mono text-amber-400 mt-1">{status?.profile_count ?? profiles.length}</p>
              <p className="text-slate-600 truncate mt-1" title={status?.profiles_dir}>{status?.profiles_dir || "not configured"}</p>
            </div>
            <div className="rounded-lg bg-slate-950/70 p-3">
              <p className="text-slate-500">Live guard</p>
              <p className={`text-lg mt-1 ${liveReady ? "text-emerald-400" : "text-amber-400"}`}>{liveReady ? "ARMED" : "LOCKED"}</p>
              <p className="text-slate-600 mt-1">{status?.execution_clock || "best-effort clock"}</p>
            </div>
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3 space-y-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-200"><FileAudio size={15} className="text-sky-400" /> 新文件分析</div>
            <div className="flex gap-2">
              <input value={audioPath} onChange={(event) => setAudioPath(event.target.value)} placeholder="/path/to/track.wav" className="flex-1 min-w-0 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-200 outline-none focus:border-amber-500" />
              <select value={device} onChange={(event) => setDevice(event.target.value as typeof device)} className="rounded-lg border border-slate-700 bg-slate-900 px-2 text-xs text-slate-300">
                <option value="cpu">CPU</option><option value="cuda">CUDA</option><option value="mps">MPS</option>
              </select>
              <button type="button" onClick={() => void runAnalysis()} disabled={busy || !audioPath.trim()} className="px-3 rounded-lg bg-sky-500/15 text-sky-300 text-xs hover:bg-sky-500/25 disabled:opacity-40">分析</button>
            </div>
            <p className="text-[11px] text-slate-600">运行 HTDemucs + All-In-One-Infer + key/energy/tagging；任务在后台执行，不阻塞控制台。</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className="text-xs text-slate-500">Outgoing / 正在播放
              <select value={fromTrack} onChange={(event) => setFromTrack(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-200">
                <option value="">选择 profile</option>{profiles.map((profile) => <option key={profile.track_id} value={profile.track_id}>{profile.track_id}</option>)}
              </select>
            </label>
            <label className="text-xs text-slate-500">Incoming / 下一首
              <select value={toTrack} onChange={(event) => setToTrack(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-200">
                <option value="">选择 profile</option>{profiles.map((profile) => <option key={profile.track_id} value={profile.track_id}>{profile.track_id}</option>)}
              </select>
            </label>
          </div>
          <div className="flex items-end gap-3 flex-wrap">
            <label className="text-xs text-slate-500">Deck out<select value={deckOut} onChange={(event) => setDeckOut(Number(event.target.value))} className="mt-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-200">{[1,2,3,4].map((deck) => <option key={deck}>{deck}</option>)}</select></label>
            <label className="text-xs text-slate-500">Deck in<select value={deckIn} onChange={(event) => setDeckIn(Number(event.target.value))} className="mt-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-200">{[1,2,3,4].map((deck) => <option key={deck}>{deck}</option>)}</select></label>
            <label className="text-xs text-slate-500">转场长度<select value={durationBeats} onChange={(event) => setDurationBeats(Number(event.target.value))} className="mt-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-200"><option value={16}>16 beats</option><option value={32}>32 beats</option><option value={64}>64 beats</option></select></label>
            <button type="button" onClick={() => void createPlan()} disabled={busy || !fromTrack || !toTrack || fromTrack === toTrack} className="ml-auto flex items-center gap-2 px-4 py-2 rounded-lg bg-amber-500 text-slate-950 text-xs font-semibold hover:bg-amber-400 disabled:opacity-40"><Sparkles size={14} /> 生成 AI 转场</button>
          </div>
        </section>

        <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 space-y-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-200"><Waves size={16} className="text-teal-400" /> DJ timeline / 自动打碟 tag</div>
          {markerMap ? <>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-xs">
              <div><span className="text-slate-500">BPM</span><p className="font-mono text-amber-400 text-base mt-1">{markerMap.bpm?.toFixed(1) ?? "—"}</p></div>
              <div><span className="text-slate-500">Key</span><p className="font-mono text-sky-300 text-base mt-1">{markerMap.key_camelot ?? "—"}</p></div>
              <div><span className="text-slate-500">Length</span><p className="font-mono text-slate-200 text-base mt-1">{formatTime(markerMap.duration_seconds)}</p></div>
              <div><span className="text-slate-500">Hotcues</span><p className="font-mono text-teal-300 text-base mt-1">{markerMap.hotcues.length}</p></div>
              <div><span className="text-slate-500">Demucs stems</span><p className="font-mono text-violet-300 text-[11px] mt-2 truncate" title={selectedFrom?.stems.join(", ")}>{selectedFrom?.stems.length ? selectedFrom.stems.join(" · ") : "—"}</p></div>
            </div>
            <div className="flex flex-wrap gap-1.5">{markerMap.semantic_tags.slice(0, 10).map((tag) => <span key={tag} className="inline-flex items-center gap-1 rounded-full bg-teal-500/10 border border-teal-500/20 px-2 py-1 text-[10px] text-teal-300"><Tags size={10} />{tag}</span>)}</div>
            <div className="relative h-28 rounded-lg border border-slate-800 bg-slate-950 overflow-hidden">
              <div className="absolute inset-0 opacity-50" style={{ backgroundImage: "linear-gradient(90deg, transparent 0%, #0f766e22 15%, transparent 31%, #0ea5e933 46%, transparent 63%, #f59e0b22 79%, transparent 100%)" }} />
              {markerMap.markers.map((marker, index) => <div key={`${marker.role}-${marker.time_seconds}-${index}`} className="absolute bottom-3 w-px h-[58%]" style={{ left: markerPosition(marker, markerMap.duration_seconds), backgroundColor: marker.color }} title={`${marker.label} · ${formatTime(marker.time_seconds)}`}><span className="absolute bottom-full left-1 -translate-x-1/2 whitespace-nowrap text-[9px]" style={{ color: marker.color }}>{marker.slot ? `H${marker.slot}` : marker.label}</span></div>)}
              <div className="absolute left-2 right-2 bottom-2 h-px bg-slate-700" />
              <div className="absolute left-2 bottom-0 text-[9px] text-slate-600">0:00</div><div className="absolute right-2 bottom-0 text-[9px] text-slate-600">{formatTime(markerMap.duration_seconds)}</div>
            </div>
            <div className="flex flex-wrap gap-1.5 max-h-20 overflow-y-auto">{markerMap.hotcues.map((marker) => <span key={`${marker.slot}-${marker.time_seconds}`} className="text-[10px] rounded bg-slate-800 px-2 py-1 text-slate-300"><b className="text-amber-400">H{marker.slot}</b> {marker.label} · {formatTime(marker.time_seconds)}</span>)}</div>
            <div className="flex items-center gap-2 pt-1">
              <button type="button" onClick={() => void applyMarkers()} disabled={!liveReady || !armed || busy} className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-40"><Tags size={13} /> 写入 Hotcue</button>
              <span className="text-[10px] text-slate-600">需要暂停 deck，并开启现场 guard</span>
            </div>
          </> : <div className="h-56 flex flex-col items-center justify-center text-center text-slate-600"><Waves size={28} className="mb-2" /><p className="text-sm">选择一个已分析 profile</p><p className="text-xs mt-1">时间线会显示 mix-in / verse / build / drop / break / mix-out 和 8-bar phrase。</p></div>}
        </section>
      </div>

      <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 space-y-4">
        <div className="flex items-center justify-between gap-3 flex-wrap"><div className="flex items-center gap-2 text-sm font-semibold text-slate-200"><ShieldCheck size={16} className={liveReady ? "text-emerald-400" : "text-amber-400"} /> Agent execution gate</div><span className="text-xs text-slate-500">默认只预演，不会让 Agent 直接接管 Mixxx。</span></div>
        {!plan ? <div className="rounded-lg border border-dashed border-slate-800 p-5 text-center text-sm text-slate-600">生成一组 outgoing / incoming profile 后，这里会显示评分、理由和相对 beat 操作。</div> : <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-xs">
            <div><span className="text-slate-500">Style</span><p className="text-amber-300 mt-1">{plan.plan.style}</p></div>
            <div><span className="text-slate-500">Score</span><p className="font-mono text-emerald-300 mt-1">{Number(plan.plan.score || 0).toFixed(3)}</p></div>
            <div><span className="text-slate-500">Target BPM</span><p className="font-mono text-slate-200 mt-1">{plan.plan.target_bpm}</p></div>
            <div><span className="text-slate-500">Mix out</span><p className="font-mono text-slate-200 mt-1">{formatTime(Number(plan.plan.mix_out_time_seconds || 0))}</p></div>
            <div><span className="text-slate-500">Mix in</span><p className="font-mono text-slate-200 mt-1">{formatTime(Number(plan.plan.mix_in_time_seconds || 0))}</p></div>
          </div>
          <div className="flex flex-wrap gap-2">{(plan.plan.rationale || []).map((reason: string) => <span key={reason} className="rounded bg-slate-800 px-2 py-1 text-[10px] text-slate-400">{reason}</span>)}</div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">{plan.rehearsal.requests.map((request, index) => <div key={`${request.relative_beat}-${index}`} className="flex items-center justify-between rounded-lg bg-slate-950/70 px-3 py-2 text-[11px]"><span className="font-mono text-teal-300 w-20">beat {request.relative_beat}</span><span className="text-slate-400 truncate">{request.payload.path}</span><span className="text-slate-600">{request.endpoint.replace("/api/", "")}</span></div>)}</div>
          <div className="flex items-center gap-3 flex-wrap border-t border-slate-800 pt-3">
            <label className="flex items-center gap-2 text-xs text-slate-400"><input type="checkbox" checked={armed} onChange={(event) => setArmed(event.target.checked)} className="accent-amber-500" /> 我已检查 hotcue、deck 和转场序列</label>
            <span className={`flex items-center gap-1 text-[11px] ${liveReady ? "text-emerald-400" : "text-amber-400"}`}>{liveReady ? <CheckCircle2 size={13} /> : <LockKeyhole size={13} />}{liveReady ? "live bridge ready" : "live guard locked"}</span>
            <button type="button" onClick={() => void executePlan()} disabled={!liveReady || !armed || busy} className="ml-auto flex items-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-xs font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-40"><Play size={13} /> 启动自动转场</button>
          </div>
          <p className="text-[10px] text-slate-600 border-l-2 border-slate-700 pl-3">执行前请先在 Mixxx 的 Deck {deckOut}/{deckIn} 手动加载对应音频；API Bridge 当前负责 ACK 控制，不负责传输音频文件。</p>
        </>}
      </section>

      {job && <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-4"><div className="flex items-center justify-between text-xs"><span className="flex items-center gap-2 text-slate-300">{job.status === "complete" ? <CheckCircle2 size={14} className="text-emerald-400" /> : job.status === "failed" ? <XCircle size={14} className="text-red-400" /> : <Loader2 size={14} className="animate-spin text-amber-400" />} {job.kind === "analysis" ? "AI 分析任务" : "自动转场任务"}</span><span className="font-mono text-slate-500">{job.status}</span></div><div className="mt-3 h-1.5 rounded-full bg-slate-800 overflow-hidden"><div className="h-full bg-amber-400 transition-all" style={{ width: `${job.kind === "transition" ? jobProgress : job.status === "complete" ? 100 : 12}%` }} /></div><div className="flex items-center gap-2 mt-2 text-[11px] text-slate-600"><Clock3 size={12} /> {job.kind === "transition" ? `${job.completed_requests || 0}/${job.request_count || 0} bridge requests · beat ${job.current_beat || 0}` : job.audio_path || ""}</div>{job.error && <p className="text-xs text-red-400 mt-2">{job.error}</p>}</section>}

      {(notice || error) && <div className={`rounded-lg border px-3 py-2 text-xs ${error ? "border-red-500/30 bg-red-500/10 text-red-300" : "border-teal-500/20 bg-teal-500/10 text-teal-300"}`}>{error || notice}</div>}
      {(selectedFrom || selectedTo) && <div className="text-[11px] text-slate-700">Loaded profiles: {selectedFrom?.track_id || "—"} → {selectedTo?.track_id || "—"}</div>}
    </div>
  );
}
