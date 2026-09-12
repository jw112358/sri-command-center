const API_BASE = 'https://sri-command-center-api.onrender.com'
const DEVICE_SESSION_KEY = 'citadel.hud.device-session.v1'
const SUMMARY_CACHE_KEY = 'citadel.hud.summary.v3'

export type CodingApproval = { id:string; source:string; sessionId:string; title:string; detail:string; action:string; risk:'low'|'medium'|'high'|'critical'; status:string; createdAt:string; expiresAt:string }
export type LegalApproval = { packetId:string; matterId:string; riskFlags?:string[]; proposedExternalAction?:string|null; createdAt:string }
export type NflHudPick = { rank:number; player:string; team:string; opponent:string; category:string; line:number|null; direction:'OVER'|'UNDER'|'NEUTRAL'|null; projection:number|null; modelProbability:number|null }
export type NflHudCategory = { key:string; label:string; picks:NflHudPick[] }
export type NflOwnerBrief = { schemaVersion:'gtd-nfl-hud-v1'; boardId:string; gameDate:string; briefingDate:string; publishedAt:string; categories:NflHudCategory[]; calibrationStatus:string; visibility:'owner_only' }

export type HudSummary = {
  updatedAt:string
  system:{ status:string; faults:number; latencyMs:number }
  counts:{ codingApprovals:number; legalApprovals:number; builderProposals:number }
  codingApprovals:CodingApproval[]
  legalApprovals:LegalApproval[]
  builderProposals:Array<{ id:string; text:string; project:string; updatedAt:string }>
  recentSessions:Array<{ title:string; project:string; status:string; summary:string; nextStart:string; updatedAt:string }>
  gtd:{ status:string; title:string; summary:string; nextStart:string; updatedAt?:string|null; completionPct?:number|null; source:string; nflOwnerBrief?:NflOwnerBrief }
  eventEdge:{ status?:string; summary?:string; updatedAt?:string|null; completionPct?:number|null; sourceStatus:'live'|'stale'|'offline'|'partial'; detail:string; paperOnly:boolean; mode:'paper'|'shadow'|'live'|'offline'; heartbeatStatus:'healthy'|'stale'|'offline'; activeSignals:number; pendingTrades:number; settled:number; winRate:number; normalizedNet:number; generatedAt?:string|null; source?:string }
}

type DeviceSession = { accessToken:string; deviceId:string; expiresAt:string }
type PersistentStorage = { getLocalStorage:(key:string)=>Promise<string>; setLocalStorage:(key:string,value:string)=>Promise<boolean> }
let persistentStorage:PersistentStorage|null=null
let deviceSession:DeviceSession|null=null
let cachedSummary:HudSummary|null=null

const parseSession=(raw:string|null):DeviceSession|null=>{ if(!raw)return null; try { const value=JSON.parse(raw) as DeviceSession; return value.accessToken&&new Date(value.expiresAt).getTime()>Date.now()?value:null } catch{return null} }
const parseSummary=(raw:string|null):HudSummary|null=>{ if(!raw)return null; try{return JSON.parse(raw) as HudSummary}catch{return null} }
export const initializePersistentStorage=async(storage:PersistentStorage)=>{ persistentStorage=storage; const [session,summary]=await Promise.all([storage.getLocalStorage(DEVICE_SESSION_KEY),storage.getLocalStorage(SUMMARY_CACHE_KEY)]); deviceSession=parseSession(session)??parseSession(localStorage.getItem(DEVICE_SESSION_KEY)); cachedSummary=parseSummary(summary)??parseSummary(localStorage.getItem(SUMMARY_CACHE_KEY)) }
const getSession=()=>{ if(deviceSession&&new Date(deviceSession.expiresAt).getTime()>Date.now())return deviceSession; deviceSession=parseSession(localStorage.getItem(DEVICE_SESSION_KEY)); return deviceSession }
const request=async<T>(path:string,init?:RequestInit):Promise<T>=>{ const headers=new Headers(init?.headers); headers.set('Content-Type','application/json'); const token=getSession()?.accessToken; if(token)headers.set('Authorization',`Bearer ${token}`); const response=await fetch(`${API_BASE}${path}`,{...init,headers}); if(response.status===401)localStorage.removeItem(DEVICE_SESSION_KEY); if(!response.ok){let detail=`Request failed (${response.status})`;try{const body=await response.json() as {detail?:string};if(body.detail)detail=body.detail}catch{}throw new Error(detail)}return response.json() as Promise<T> }
export const isPaired=()=>getSession()!==null
export const pairDevice=async(code:string)=>{const session=await request<DeviceSession>('/api/hud/pair',{method:'POST',body:JSON.stringify({code})});deviceSession=session;localStorage.setItem(DEVICE_SESSION_KEY,JSON.stringify(session));if(persistentStorage)await persistentStorage.setLocalStorage(DEVICE_SESSION_KEY,JSON.stringify(session));return session}
export const loadSummary=async()=>{const value=await request<HudSummary>('/api/hud/summary');cachedSummary=value;localStorage.setItem(SUMMARY_CACHE_KEY,JSON.stringify(value));if(persistentStorage)await persistentStorage.setLocalStorage(SUMMARY_CACHE_KEY,JSON.stringify(value));return value}
export const loadCachedSummary=()=>cachedSummary??parseSummary(localStorage.getItem(SUMMARY_CACHE_KEY))
export const decideCodingApproval=(id:string,decision:'approve'|'deny')=>request<CodingApproval>(`/api/hud/approvals/${encodeURIComponent(id)}/decision`,{method:'POST',body:JSON.stringify({decision})})
export const clearPairing=async()=>{deviceSession=null;localStorage.removeItem(DEVICE_SESSION_KEY);if(persistentStorage)await persistentStorage.setLocalStorage(DEVICE_SESSION_KEY,'')}
