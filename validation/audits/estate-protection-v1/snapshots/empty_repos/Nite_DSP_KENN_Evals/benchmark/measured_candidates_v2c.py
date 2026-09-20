"""Pure PCM measurements and evidence-bearing V2-C candidates.

This is evaluation infrastructure; it deliberately has no product imports.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import math
import numpy as np

ANALYSIS_VERSION = "kenn.measured_candidates.v2c.1"

@dataclass(frozen=True)
class MeasuredIssueCandidate:
    issue_type: str; measured_value: float; unit: str; score: float
    severity: str; confidence_kind: str; confidence_bucket: str
    persistence: float; affected_channels: tuple[str, ...]; analysis_scope: str
    evidence: dict; limitations: tuple[str, ...]; analysis_version: str = ANALYSIS_VERSION
    def payload(self) -> dict: return asdict(self)

def _db(value: float) -> float: return 20 * math.log10(max(value, 1e-12))
def _rms(x: np.ndarray) -> float: return float(np.sqrt(np.mean(np.square(x))))
def _sev(score: float) -> str: return "severe" if score >= .85 else "strong" if score >= .65 else "moderate" if score >= .45 else "mild"

def clipping_candidate(audio: np.ndarray, scope: str = "unknown") -> MeasuredIssueCandidate:
    if audio.size == 0:
        return MeasuredIssueCandidate("clipping",0.,"linear_peak",0.,"mild","measured","low",0.,(),scope,{"category":"no_clipping","empty":True},("Empty audio has insufficient evidence.",))
    peak = float(np.max(np.abs(audio))); near = np.abs(audio) >= .999
    # A plateau is two+ adjacent near-FS samples in the same channel. This
    # separates a lone legitimate transient sample from hard flat-topping.
    plateaus = 0; affected=[]
    for c in range(audio.shape[1]):
        runs = np.diff(np.r_[False, near[:,c], False].astype(np.int8)); starts=np.where(runs==1)[0]; ends=np.where(runs==-1)[0]
        events=sum((ends-starts)>=2); plateaus += int(events)
        if events: affected.append("L" if c==0 else "R")
    density=float(np.mean(near)); score=min(1., .15 + min(.45, density*30) + min(.45, plateaus*.12)) if plateaus else max(0., (peak-.999)*120)
    category="likely_hard_clipping" if plateaus>=2 else "likely_sample_clipping" if plateaus else "near_full_scale" if peak>=.98 else "no_clipping"
    return MeasuredIssueCandidate("clipping", peak, "linear_peak", score, _sev(score), "measured", "high" if plateaus else "medium", min(1.,plateaus/4), tuple(affected),scope,{"category":category,"max_sample_peak":peak,"peak_dbfs":_db(peak),"near_full_scale_samples":int(near.sum()),"plateau_events":plateaus,"event_density":density},("Sample-domain detector; it cannot identify all analogue/soft distortion.",))

def headroom_candidate(audio: np.ndarray, scope: str = "unknown") -> MeasuredIssueCandidate:
    if audio.size == 0:
        return MeasuredIssueCandidate("headroom",0.,"dBFS_margin",0.,"mild","derived","low",0.,(),scope,{"empty":True},("Empty audio has insufficient evidence.",))
    per=[float(np.max(np.abs(audio[:,c]))) for c in range(audio.shape[1])]; peak=max(per); margin=-_db(peak)
    # Low margin is only an evidence-derived candidate; scope decides action.
    score=min(1., max(0., (9-margin)/9))
    return MeasuredIssueCandidate("headroom", margin,"dBFS_margin",score,_sev(score),"derived","high",1.,tuple("L" if i==0 else "R" for i,p in enumerate(per) if p==peak),scope,{"max_sample_peak_dbfs":_db(peak),"headroom_db":margin,"channel_peaks_dbfs":[_db(p) for p in per]},("Sample-peak margin is not a universal mastering target; true peak is not estimated.",))

def lr_imbalance_candidate(audio: np.ndarray, sr: int, scope: str = "unknown") -> MeasuredIssueCandidate:
    if audio.size == 0:
        return MeasuredIssueCandidate("lr_imbalance",0.,"dB",0.,"mild","measured","low",0.,(),scope,{"empty":True},("Empty audio has insufficient evidence.",))
    if audio.shape[1] == 1: return MeasuredIssueCandidate("lr_imbalance",0.,"dB",0.,"mild","measured","high",1.,(),scope,{"channel_delta_db":0.,"window_count":0},("Mono material has no L/R balance judgment.",))
    size=max(128,int(sr*.1)); vals=[]
    for start in range(0,len(audio),size):
        frame=audio[start:start+size];
        if len(frame)>=32: vals.append(_db(_rms(frame[:,0]))-_db(_rms(frame[:,1])))
    vals=np.asarray(vals) if vals else np.array([0.]); median=float(np.median(vals)); persistent=float(np.mean(np.sign(vals)==np.sign(median))) if abs(median)>.1 else 1.
    p95=float(np.percentile(np.abs(vals),95)); overall=_db(_rms(audio[:,0]))-_db(_rms(audio[:,1]))
    # Persistent, mix-wide energy difference earns score; alternation is a
    # confounder rather than an automatic pan correction.
    score=min(1., max(0.,(abs(median)-1.5)/6)*persistent + max(0.,(p95-3)/12)*.2)
    return MeasuredIssueCandidate("lr_imbalance",median,"dB",score,_sev(score),"measured","high" if len(vals)>=5 else "medium",persistent,("L","R"),scope,{"channel_delta_db":overall,"median_window_delta_db":median,"p95_abs_window_delta_db":p95,"direction_consistency":persistent,"window_count":len(vals)},("A stereo render cannot distinguish persistent mix imbalance from an intentional arrangement without context.",))
