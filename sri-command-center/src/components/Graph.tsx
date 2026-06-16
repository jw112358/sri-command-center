import { useRef, useEffect, useState } from 'react';
import * as THREE from 'three';
import type { GraphData, GraphNode, Tweaks } from '../types';
import { OS_BY_ID } from '../mock/data';

const STATUS_COLOR: Record<string, { core: number; glow: number }> = {
  ACTIVE:   { core: 0xfff3b0, glow: 0xffd700 },
  BLOCKED:  { core: 0xffb060, glow: 0xff6a4d },
  COMPLETE: { core: 0xb9a23a, glow: 0x7a6a1e },
};
const KIND_SIZE: Record<string, number> = { hub: 1.25, project: 0.62, agent: 0.48, skill: 0.32 };

const _texCache: Record<number, THREE.Texture> = {};
function glowTexture(hex: number): THREE.Texture {
  if (_texCache[hex]) return _texCache[hex];
  const c = document.createElement('canvas'); c.width = c.height = 128;
  const ctx = c.getContext('2d')!;
  const r = `${(hex >> 16) & 255},${(hex >> 8) & 255},${hex & 255}`;
  const g = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
  g.addColorStop(0, 'rgba(255,255,255,0.95)');
  g.addColorStop(0.25, `rgba(${r},0.9)`);
  g.addColorStop(0.55, `rgba(${r},0.35)`);
  g.addColorStop(1, `rgba(${r},0)`);
  ctx.fillStyle = g; ctx.fillRect(0, 0, 128, 128);
  const t = new THREE.Texture(c); t.needsUpdate = true;
  _texCache[hex] = t; return t;
}

function fibSphere(i: number, n: number, radius: number): THREE.Vector3 {
  const off = 2 / n, y = i * off - 1 + off / 2;
  const r = Math.sqrt(Math.max(0, 1 - y * y));
  const phi = i * Math.PI * (3 - Math.sqrt(5));
  return new THREE.Vector3(Math.cos(phi) * r, y, Math.sin(phi) * r).multiplyScalar(radius);
}

interface GraphProps {
  data: GraphData;
  selectedId: string | null;
  onSelect: (node: GraphNode | null) => void;
  fullscreen: boolean;
  onToggleFs: () => void;
  tweaks: Tweaks;
  pulseSet: Set<string>;
  onMarkComplete?: (nodeId: string) => void;
  onViewLog?: (node: GraphNode) => void;
}

export function ProjectGraph({ data, selectedId, onSelect, fullscreen, onToggleFs, tweaks, pulseSet, onMarkComplete, onViewLog }: GraphProps) {
  const mountRef = useRef<HTMLDivElement>(null);
  const stateRef = useRef<Record<string, any>>({});
  const [tooltip, setTooltip] = useState<{ node: GraphNode } | null>(null);
  const [ctx, setCtx] = useState<{ x: number; y: number; node: GraphNode } | null>(null);
  const [failed, setFailed] = useState(false);

  const propsRef = useRef({ selectedId, tweaks, pulseSet, onSelect, onToggleFs });
  propsRef.current = { selectedId, tweaks, pulseSet, onSelect, onToggleFs };

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;
    const W = () => mount.clientWidth, H = () => mount.clientHeight;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    } catch {
      setFailed(true); return;
    }

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(55, W() / H(), 0.1, 2000);
    camera.position.set(0, 0, 64);

    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x060f1e, 1);
    renderer.setSize(W(), H());
    mount.appendChild(renderer.domElement);

    const world = new THREE.Group(); scene.add(world);

    // Star field
    const starGeo = new THREE.BufferGeometry();
    const starN = 900, sp = new Float32Array(starN * 3);
    for (let i = 0; i < starN; i++) {
      const v = fibSphere(i, starN, 320 + Math.random() * 260);
      sp[i*3] = v.x; sp[i*3+1] = v.y; sp[i*3+2] = v.z;
    }
    starGeo.setAttribute('position', new THREE.BufferAttribute(sp, 3));
    const stars = new THREE.Points(starGeo, new THREE.PointsMaterial({
      color: 0xffe9a8, size: 1.1, transparent: true, opacity: 0.55, sizeAttenuation: true,
    }));
    scene.add(stars);

    // Layout
    const hubs = data.nodes.filter((n) => n.kind === 'hub');
    const hubPos: Record<string, THREE.Vector3> = {};
    hubs.forEach((h, i) => { hubPos[h.id] = fibSphere(i, hubs.length, 30); });

    const pos: Record<string, THREE.Vector3> = {};
    const nodeObjs: THREE.Sprite[] = [];

    data.nodes.forEach((n) => {
      let p: THREE.Vector3;
      if (n.kind === 'hub') {
        p = hubPos[n.id].clone();
      } else {
        const hp = hubPos['os:' + n.os] || new THREE.Vector3();
        const spread = n.kind === 'project' ? 11 : n.kind === 'agent' ? 8 : 6.5;
        const out = n.status === 'COMPLETE' ? 1.35 : 1;
        const jitter = new THREE.Vector3(
          Math.random() - 0.5, Math.random() - 0.5, Math.random() - 0.5
        ).normalize().multiplyScalar(spread * out * (0.6 + Math.random() * 0.5));
        p = hp.clone().add(jitter).add(hp.clone().normalize().multiplyScalar(3.5 * out));
      }
      pos[n.id] = p;

      const sc = STATUS_COLOR[n.status] || STATUS_COLOR.COMPLETE;
      const mat = new THREE.SpriteMaterial({
        map: glowTexture(sc.glow), color: 0xffffff, transparent: true,
        blending: THREE.AdditiveBlending, depthWrite: false, opacity: 0.95,
      });
      const sprite = new THREE.Sprite(mat);
      sprite.position.copy(p);
      // Project nodes scale with completionPct (0-100): 100% → ~2.8× a 0% project.
      // Other node kinds use val-based sizing unchanged.
      let completionScale = 1.0;
      if (n.kind === 'project' && n.completionPct != null) {
        const pct = Math.max(0, Math.min(100, n.completionPct));
        completionScale = 0.55 + (pct / 100) * 1.7; // range 0.55 → 2.25
      }
      const base = (KIND_SIZE[n.kind] || 0.4) * completionScale * (1 + (n.val || 1) * 0.04) * 7.4;
      (sprite as any).userData = { node: n, base, phase: Math.random() * Math.PI * 2, sc };
      sprite.scale.setScalar(0.001);
      world.add(sprite);
      nodeObjs.push(sprite);
    });

    // Links
    const linkPairs: { a: THREE.Vector3; b: THREE.Vector3; active: boolean }[] = [];
    const lv: number[] = [];
    data.links.forEach((l) => {
      const a = pos[l.source], b = pos[l.target];
      if (!a || !b) return;
      lv.push(a.x, a.y, a.z, b.x, b.y, b.z);
      const tn = data.nodes.find((n) => n.id === l.target);
      linkPairs.push({ a, b, active: !!(tn && tn.status === 'ACTIVE') });
    });
    const linkGeo = new THREE.BufferGeometry();
    linkGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(lv), 3));
    const linksMesh = new THREE.LineSegments(linkGeo, new THREE.LineBasicMaterial({
      color: 0x1a3a7a, transparent: true, opacity: 0.5,
    }));
    world.add(linksMesh);

    // Pulse sprites
    const pulseTex = glowTexture(0xfff3b0);
    const pulses = linkPairs.filter((l) => l.active).slice(0, 40).map((l) => {
      const m = new THREE.SpriteMaterial({ map: pulseTex, transparent: true,
        blending: THREE.AdditiveBlending, depthWrite: false, opacity: 0.9 });
      const s = new THREE.Sprite(m); s.scale.setScalar(2.4);
      (s as any).userData = { link: l, t: Math.random() };
      world.add(s); return s;
    });

    // Label DOM overlay
    const labelLayer = document.createElement('div');
    Object.assign(labelLayer.style, { position: 'absolute', inset: '0', pointerEvents: 'none', zIndex: '10', overflow: 'hidden' });
    mount.appendChild(labelLayer);
    const labelEls: Record<string, HTMLDivElement> = {};
    nodeObjs.forEach((s) => {
      const n = (s as any).userData.node as GraphNode;
      const el = document.createElement('div');
      el.textContent = n.label;
      Object.assign(el.style, {
        position: 'absolute', transform: 'translate(-50%,-50%)', whiteSpace: 'nowrap',
        fontFamily: 'var(--font-ui)', letterSpacing: '1px', pointerEvents: 'none',
        color: n.kind === 'hub' ? '#FFD700' : '#cfe0ff',
        fontSize: n.kind === 'hub' ? '11px' : '9.5px',
        textShadow: '0 0 6px rgba(0,0,0,.9), 0 0 10px rgba(255,215,0,.3)',
        opacity: n.kind === 'hub' ? '1' : '0', transition: 'opacity .15s',
      });
      labelLayer.appendChild(el);
      labelEls[n.id] = el;
    });

    // Interaction state
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();
    const st = stateRef.current;
    st.rotX = 0.2; st.rotY = 0; st.velY = 0; st.dragging = false; st.lastUser = 0;
    st.zoom = 64; st.hoverId = null; st.intro = 0; st.mx = null; st.my = null;

    let lastX = 0, lastY = 0;
    const onDown = (e: PointerEvent) => {
      st.dragging = true; st.lastUser = performance.now();
      lastX = e.clientX; lastY = e.clientY;
      mount.classList.add('dragging');
      setCtx(null);
    };
    const onMove = (e: PointerEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
      st.mx = e.clientX - rect.left; st.my = e.clientY - rect.top;
      if (st.dragging) {
        const dx = e.clientX - lastX, dy = e.clientY - lastY;
        lastX = e.clientX; lastY = e.clientY;
        st.rotY += dx * 0.006; st.rotX += dy * 0.006;
        st.rotX = Math.max(-1.3, Math.min(1.3, st.rotX));
        st.velY = dx * 0.006; st.lastUser = performance.now();
      }
    };
    const onUp = () => { st.dragging = false; mount.classList.remove('dragging'); };
    const onWheel = (e: WheelEvent) => {
      e.preventDefault(); st.lastUser = performance.now();
      st.zoom = Math.max(34, Math.min(150, st.zoom + e.deltaY * 0.05));
    };
    let downX = 0, downY = 0;
    mount.addEventListener('pointerdown', (e) => { downX = e.clientX; downY = e.clientY; st.movedSinceDown = false; onDown(e); });
    window.addEventListener('pointermove', (e) => {
      if (Math.abs(e.clientX - downX) + Math.abs(e.clientY - downY) > 5) st.movedSinceDown = true;
      onMove(e);
    });
    window.addEventListener('pointerup', onUp);
    renderer.domElement.addEventListener('click', (e) => {
      if (st.movedSinceDown) return;
      raycaster.setFromCamera(mouse, camera);
      const hit = raycaster.intersectObjects(nodeObjs, false)[0];
      propsRef.current.onSelect(hit ? (hit.object as any).userData.node : null);
      setCtx(null);
    });
    renderer.domElement.addEventListener('contextmenu', (e) => {
      e.preventDefault();
      raycaster.setFromCamera(mouse, camera);
      const hit = raycaster.intersectObjects(nodeObjs, false)[0];
      if (hit) {
        const node = (hit.object as any).userData.node as GraphNode;
        propsRef.current.onSelect(node);
        setCtx({ x: e.clientX, y: e.clientY, node });
      }
    });
    renderer.domElement.addEventListener('wheel', onWheel, { passive: false });

    const tmp = new THREE.Vector3();
    const project = (p: THREE.Vector3) => {
      tmp.copy(p).applyMatrix4(world.matrixWorld).project(camera);
      return { x: (tmp.x * 0.5 + 0.5) * W(), y: (-tmp.y * 0.5 + 0.5) * H(), z: tmp.z };
    };

    // Render loop
    let raf: number, prev = performance.now();
    const loop = () => {
      raf = requestAnimationFrame(loop);
      const now = performance.now(), dt = Math.min(0.05, (now - prev) / 1000); prev = now;
      const P = propsRef.current;
      const glow = P.tweaks?.glowNodes ? 1 : 0.4;
      const rotSpeed = P.tweaks?.animGraph ? 0.05 : 0;
      st.intro = Math.min(1, st.intro + dt * 0.8);

      const idle = now - st.lastUser > 1200;
      if (idle && !st.dragging) st.rotY += rotSpeed * dt;
      else { st.rotY += st.velY; st.velY *= 0.9; }

      world.rotation.y = st.rotY;
      world.rotation.x = st.rotX;
      stars.rotation.y += rotSpeed * dt * 0.3;
      camera.position.z += (st.zoom - camera.position.z) * Math.min(1, dt * 8);
      world.updateMatrixWorld();

      raycaster.setFromCamera(mouse, camera);
      const hits = st.mx != null ? raycaster.intersectObjects(nodeObjs, false) : [];
      const hoverNode = hits[0] ? (hits[0].object as any).userData.node as GraphNode : null;
      if ((hoverNode?.id ?? null) !== st.hoverId) {
        st.hoverId = hoverNode?.id ?? null;
        setTooltip(hoverNode ? { node: hoverNode } : null);
      }

      const sel = P.selectedId;
      const ps = P.pulseSet || new Set<string>();
      nodeObjs.forEach((s, i) => {
        const u = (s as any).userData, n = u.node as GraphNode;
        const t = now / 1000 + u.phase;
        let k = 1;
        if (n.status === 'ACTIVE') k = 1 + Math.sin(t * 3.2) * 0.12;
        if (ps.has(n.agentId ?? '')) k = 1 + Math.sin(t * 9) * 0.28;
        if (n.status === 'BLOCKED') k = 1 + Math.sin(t * 2) * 0.08;
        if (n.id === sel) k *= 1.5;
        const introK = Math.min(1, st.intro * 1.4 - i * 0.004);
        s.scale.setScalar(u.base * k * Math.max(0, introK) * (0.85 + glow * 0.25));
        s.material.opacity = (n.status === 'COMPLETE' ? 0.6 : 0.95) * Math.max(0, introK);
        if (n.id === sel) s.material.opacity = 1;
      });

      pulses.forEach((pl) => {
        (pl as any).userData.t += dt * 0.6;
        if ((pl as any).userData.t > 1) (pl as any).userData.t -= 1;
        const { a, b } = (pl as any).userData.link;
        pl.position.lerpVectors(a, b, (pl as any).userData.t);
        const f = Math.sin((pl as any).userData.t * Math.PI);
        pl.material.opacity = 0.15 + f * 0.7 * glow;
        pl.scale.setScalar(1.4 + f * 1.6);
      });
      (linksMesh.material as THREE.LineBasicMaterial).opacity = 0.35 + 0.2 * glow;

      nodeObjs.forEach((s) => {
        const n = (s as any).userData.node as GraphNode, el = labelEls[n.id];
        if (!el) return;
        const pr = project(s.position);
        const behind = pr.z > 1;
        const show = n.kind === 'hub' || n.id === st.hoverId || n.id === sel;
        if (behind || !show) { el.style.opacity = '0'; return; }
        el.style.left = pr.x + 'px'; el.style.top = (pr.y - s.scale.x * 3.2) + 'px';
        el.style.opacity = n.kind === 'hub' ? '0.95' : '1';
        el.style.color = n.id === sel ? '#fff7cc' : (n.kind === 'hub' ? '#FFD700' : '#cfe0ff');
      });

      renderer.render(scene, camera);
    };
    loop();

    const ro = new ResizeObserver(() => {
      camera.aspect = W() / H(); camera.updateProjectionMatrix(); renderer.setSize(W(), H());
    });
    ro.observe(mount);

    return () => {
      cancelAnimationFrame(raf); ro.disconnect();
      window.removeEventListener('pointermove', onMove as any);
      window.removeEventListener('pointerup', onUp as any);
      if (mount.contains(renderer.domElement)) mount.removeChild(renderer.domElement);
      if (mount.contains(labelLayer)) mount.removeChild(labelLayer);
      renderer.dispose();
    };
  }, [data]);

  const tip = tooltip?.node;
  const tipPos = tip ? { left: stateRef.current.mx, top: stateRef.current.my } : null;

  if (failed) return (
    <div className="panel-body" style={{ display: 'grid', placeItems: 'center', color: 'var(--muted)' }}>
      3D engine unavailable — check connection.
    </div>
  );

  return (
    <>
      <div className="graph-canvas" ref={mountRef}></div>
      {tip && tipPos && (
        <div className="graph-tooltip" style={{ left: tipPos.left, top: tipPos.top }}>
          <div className="tt-name">{tip.label}</div>
          <div className="tt-meta">
            {tip.kind.toUpperCase()} · {OS_BY_ID[tip.os]?.name.replace(/ \(.*\)/, '') ?? tip.os}<br />
            STATUS {tip.status}
            {tip.kind === 'project' && tip.completionPct != null && (
              <><br />COMPLETION {Math.round(tip.completionPct)}%</>
            )}
          </div>
        </div>
      )}
      <div className="graph-legend">
        <div className="lg"><span className="sw" style={{ background: '#fff3b0', boxShadow: '0 0 8px #ffd700' }}></span>ACTIVE</div>
        <div className="lg"><span className="sw" style={{ background: '#ff8a5a', boxShadow: '0 0 8px #ff6a4d' }}></span>BLOCKED</div>
        <div className="lg"><span className="sw" style={{ background: '#7a6a1e' }}></span>COMPLETE</div>
      </div>
      <div className="graph-controls">
        <button className="btn sm icon" title="Reset view" onClick={() => {
          const s = stateRef.current; s.rotX = 0.2; s.rotY = 0; s.zoom = 64; s.lastUser = 0;
        }}>⟲</button>
        <button className="btn sm icon" title={fullscreen ? 'Exit full screen' : 'Full screen'} onClick={onToggleFs}>
          {fullscreen ? '⤡' : '⤢'}
        </button>
      </div>
      <div className="graph-hint">DRAG rotate · SCROLL zoom · CLICK inspect · RIGHT-CLICK menu</div>
      {ctx && (
        <>
          <div style={{ position: 'fixed', inset: 0, zIndex: 9400 }} onClick={() => setCtx(null)} onContextMenu={(e) => { e.preventDefault(); setCtx(null); }} />
          <div className="ctx-menu" style={{ left: ctx.x, top: ctx.y }}>
            <div className="ci" onClick={() => { onSelect(ctx.node); setCtx(null); }}><span className="ic">▣</span> Inspect Node</div>
            <div className="ci" onClick={() => { onViewLog?.(ctx.node); setCtx(null); }}><span className="ic">≣</span> View Log</div>
            <div className="ci" onClick={() => {
              onMarkComplete?.(ctx.node.id);
              setCtx(null);
            }}><span className="ic">✓</span> Mark Complete</div>
          </div>
        </>
      )}
    </>
  );
}
