interface MeshNode {
  u: number; v: number; x: number; y: number;
  ox: number; oy: number; vx: number; vy: number;
  phase: number; heat: number; quiet: number; accent: boolean;
}
interface QuietZone { left: number; top: number; right: number; bottom: number }
interface MeshEdge { a: number; b: number }

const TAU = Math.PI * 2;
const MAX_LINKS = 3;

/** Isolated mutable renderer. React participates only in mounting and cleanup. */
export function createForgeMesh(canvas: HTMLCanvasElement, hero: HTMLElement): () => void {
  const ctx = canvas.getContext('2d');
  if (!ctx) return () => {};
  const context = ctx;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const coarse = matchMedia('(pointer: coarse)');
  const sprite = document.createElement('canvas');
  sprite.width = sprite.height = 64;
  const glow = sprite.getContext('2d');
  if (glow) {
    const gradient = glow.createRadialGradient(32, 32, 0, 32, 32, 32);
    gradient.addColorStop(0, 'rgba(209,42,42,0.6)');
    gradient.addColorStop(0.2, 'rgba(161,18,18,0.25)');
    gradient.addColorStop(1, 'rgba(122,0,0,0)');
    glow.fillStyle = gradient;
    glow.fillRect(0, 0, 64, 64);
  }

  let nodes: MeshNode[] = [];
  let edges: MeshEdge[] = [];
  let zones: QuietZone[] = [];
  let width = 0, height = 0, link = 200;
  let mobile = false, visible = false, disposed = false;
  let raf = 0, timer = 0, last = 0, time = 0, lastPointerTime = 0;
  let resizeTimer = 0;
  const pointer = { x: -10000, y: -10000, active: false };
  const scan = { x: 0, y: 0, age: 10 };

  function quietAt(x: number, y: number): number {
    let amount = 1;
    for (let i = 0; i < zones.length; i++) {
      const zone = zones[i];
      const dx = Math.max(zone.left - x, 0, x - zone.right);
      const dy = Math.max(zone.top - y, 0, y - zone.bottom);
      amount = Math.min(amount, 0.06 + Math.min(1, Math.max(dx, dy) / 42) * 0.94);
    }
    return amount;
  }

  function measure() {
    if (disposed) return;
    const rect = hero.getBoundingClientRect();
    width = rect.width;
    height = rect.height;
    mobile = coarse.matches || width < 640;
    const dpr = Math.min(devicePixelRatio || 1, mobile ? 1 : 1.25);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    zones = Array.from(hero.querySelectorAll<HTMLElement>('[data-mesh-quiet]')).map(element => {
      const box = element.getBoundingClientRect();
      return { left: box.left - rect.left - 10, right: box.right - rect.left + 10,
        top: box.top - rect.top - 18, bottom: box.bottom - rect.top + 20 };
    });
    const count = mobile ? Math.min(28, Math.max(20, Math.round(width * height / 18000)))
      : Math.min(58, Math.max(44, Math.round(width * height / 22000)));
    if (nodes.length !== count) {
      // Stratified, seeded placement keeps the mesh sparse and resize-stable.
      let seed = 7419;
      const random = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296; };
      const across = Math.ceil(Math.sqrt(count * width / height));
      const down = Math.ceil(count / across);
      nodes = Array.from({ length: count }, (_, i) => ({
        u: ((i % across) + 0.2 + random() * 0.65) / across,
        v: (Math.floor(i / across) + 0.15 + random() * 0.7) / down,
        x: 0, y: 0, ox: 0, oy: 0, vx: 0, vy: 0,
        phase: random() * TAU, heat: 0, quiet: 1,
        accent: i % 11 === 3,
      }));
    }
    link = Math.min(mobile ? 160 : 270, Math.sqrt(width * height / count) * 1.45);
    // Connect nearest anchors once. Stable topology avoids per-frame searches
    // and keeps the constellation from flickering as nodes respond to input.
    const candidates: Array<MeshEdge & { distance: number }> = [];
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const dx = (nodes[i].u - nodes[j].u) * width;
        const dy = (nodes[i].v - nodes[j].v) * height;
        const distance = dx * dx + dy * dy;
        if (distance < link * link) candidates.push({ a: i, b: j, distance });
      }
    }
    candidates.sort((a, b) => a.distance - b.distance);
    const degree = new Uint8Array(nodes.length);
    edges = [];
    for (const edge of candidates) {
      if (degree[edge.a] >= MAX_LINKS || degree[edge.b] >= MAX_LINKS) continue;
      degree[edge.a]++;
      degree[edge.b]++;
      edges.push({ a: edge.a, b: edge.b });
    }
    update(0);
    sync();
  }

  function update(dt: number) {
    const radius = mobile ? 130 : 220;
    const radius2 = radius * radius;
    const damping = Math.exp(-9 * dt);
    for (let i = 0; i < nodes.length; i++) {
      const node = nodes[i];
      const baseX = node.u * width + (reduced.matches ? 0 : Math.sin(time * 0.17 + node.phase) * 9);
      const baseY = node.v * height + (reduced.matches ? 0 : Math.cos(time * 0.13 + node.phase) * 7);
      const dx = baseX + node.ox - pointer.x, dy = baseY + node.oy - pointer.y;
      const distance2 = dx * dx + dy * dy;
      let heat = 0, forceX = 0, forceY = 0;
      if (pointer.active && distance2 < radius2 && !reduced.matches) {
        const distance = Math.sqrt(distance2);
        heat = 1 - distance / radius;
        const force = heat * heat * 1050 / Math.max(distance, 1);
        forceX = dx * force;
        forceY = dy * force;
      }
      if (scan.age < 1.2 && !reduced.matches) {
        const sx = baseX - scan.x, sy = baseY - scan.y;
        const distance = Math.sqrt(sx * sx + sy * sy);
        const wave = Math.max(0, 1 - Math.abs(distance - scan.age * 230) / 42) * (1 - scan.age / 1.2);
        heat = Math.max(heat, wave);
        forceX += sx / Math.max(distance, 1) * wave * 180;
        forceY += sy / Math.max(distance, 1) * wave * 180;
      }
      node.vx = (node.vx + (forceX - node.ox * 32) * dt) * damping;
      node.vy = (node.vy + (forceY - node.oy * 32) * dt) * damping;
      node.ox += node.vx * dt;
      node.oy += node.vy * dt;
      node.x = baseX + node.ox;
      node.y = baseY + node.oy;
      node.quiet = quietAt(node.x, node.y);
      node.heat += (heat - node.heat) * Math.min(1, dt * 8);
    }
  }

  function draw() {
    context.clearRect(0, 0, width, height);
    const entrance = reduced.matches ? 1 : Math.min(1, time / 0.65);
    context.lineWidth = 0.75;
    const link2 = link * link;
    for (let i = 0; i < edges.length; i++) {
      const a = nodes[edges[i].a];
      const b = nodes[edges[i].b];
      const dx = a.x - b.x, dy = a.y - b.y;
      const distance2 = dx * dx + dy * dy;
      const heat = Math.max(a.heat, b.heat);
      const quiet = Math.min(a.quiet, b.quiet, quietAt((a.x + b.x) / 2, (a.y + b.y) / 2));
      const strength = Math.max(0, 1 - distance2 / link2) * quiet * entrance;
      context.strokeStyle = heat > 0.1 ? '#A11212' : '#6E6258';
      context.globalAlpha = strength * (0.43 + heat * 0.55);
      context.beginPath(); context.moveTo(a.x, a.y); context.lineTo(b.x, b.y); context.stroke();
      // A few short signal hops, never a growing list of particles.
      const phase = (time * 0.16 + a.phase) % 1;
      if (!reduced.matches && i % 13 === 0 && phase < 0.22 && quiet > 0.4) {
        const progress = phase / 0.22;
        const px = a.x + (b.x - a.x) * progress, py = a.y + (b.y - a.y) * progress;
        context.globalAlpha = Math.sin(progress * Math.PI) * entrance * 0.5;
        context.fillStyle = '#A11212';
        context.beginPath(); context.arc(px, py, 1.6, 0, TAU); context.fill();
      }
    }
    for (let i = 0; i < nodes.length; i++) {
      const node = nodes[i];
      const accent = node.accent ? 0.3 : 0;
      const intensity = Math.max(accent, node.heat);
      if (intensity > 0.05) {
        context.globalAlpha = intensity * node.quiet * entrance * 0.7;
        context.drawImage(sprite, node.x - 18, node.y - 18, 36, 36);
      }
      context.globalAlpha = node.quiet * entrance * (node.accent ? 0.76 : 0.56 + node.heat * 0.35);
      context.fillStyle = intensity > 0.15 ? '#A11212' : '#6E6258';
      context.beginPath(); context.arc(node.x, node.y, node.accent ? 2.2 : 1.4, 0, TAU); context.fill();
    }
    if (pointer.active && !reduced.matches) {
      const quiet = quietAt(pointer.x, pointer.y);
      if (quiet > 0.35) {
        const reach = mobile ? 130 : 200;
        let connected = 0;
        context.strokeStyle = '#A11212';
        context.lineWidth = 0.9;
        for (const node of nodes) {
          const dx = pointer.x - node.x, dy = pointer.y - node.y;
          const distance = Math.sqrt(dx * dx + dy * dy);
          if (distance > reach || node.quiet < 0.4) continue;
          context.globalAlpha = (1 - distance / reach) * quiet * entrance * 0.48;
          context.beginPath(); context.moveTo(pointer.x, pointer.y); context.lineTo(node.x, node.y); context.stroke();
          if (++connected === 5) break;
        }
        context.globalAlpha = quiet * entrance * 0.22;
        context.drawImage(sprite, pointer.x - 32, pointer.y - 32);
        context.globalAlpha = quiet * entrance * 0.55;
        context.beginPath(); context.arc(pointer.x, pointer.y, 2, 0, TAU); context.fillStyle = '#A11212'; context.fill();
      }
    }
    if (scan.age < 1.2 && !reduced.matches) {
      context.strokeStyle = '#A11212';
      context.lineWidth = 1;
      context.globalAlpha = (1 - scan.age / 1.2) * quietAt(scan.x, scan.y) * 0.38;
      context.beginPath(); context.arc(scan.x, scan.y, scan.age * 230, 0, TAU); context.stroke();
    }
    context.globalAlpha = 1;
  }

  function frame(now: number) {
    raf = 0;
    if (!visible || document.hidden || reduced.matches || disposed) return;
    const dt = last ? Math.min((now - last) / 1000, 0.08) : 1 / 60;
    last = now;
    time += dt;
    scan.age += dt;
    update(dt);
    draw();
    schedule();
  }

  function schedule(immediate = false) {
    if (!visible || document.hidden || reduced.matches || disposed) return;
    if (immediate) {
      clearTimeout(timer);
      timer = 0;
      if (!raf) raf = requestAnimationFrame(frame);
      return;
    }
    const responsive = performance.now() - lastPointerTime < 900 || scan.age < 1.2;
    if (responsive) raf = requestAnimationFrame(frame);
    else timer = window.setTimeout(() => {
      timer = 0;
      raf = requestAnimationFrame(frame);
    }, mobile ? 70 : 38);
  }

  function sync() {
    cancelAnimationFrame(raf);
    clearTimeout(timer);
    raf = 0;
    timer = 0;
    last = 0;
    if (document.hidden) pointer.active = false;
    if (!visible || document.hidden || disposed) return;
    if (reduced.matches) {
      pointer.active = false;
      for (const node of nodes) { node.ox = node.oy = node.vx = node.vy = node.heat = 0; }
      update(0); draw();
    } else schedule(true);
  }
  function position(event: PointerEvent) {
    const rect = hero.getBoundingClientRect();
    pointer.x = event.clientX - rect.left;
    pointer.y = event.clientY - rect.top;
    pointer.active = true;
    lastPointerTime = performance.now();
    schedule(true);
  }
  function leave() {
    if (!pointer.active) return;
    pointer.active = false;
    schedule(true);
  }
  function down(event: PointerEvent) {
    if (reduced.matches || event.button !== 0 || (event.target instanceof Element && event.target.closest('a, button, input'))) return;
    position(event);
    scan.x = pointer.x; scan.y = pointer.y; scan.age = 0;
    schedule(true);
  }
  function up(event: PointerEvent) { if (event.pointerType !== 'mouse') leave(); }
  function queueMeasure() { clearTimeout(resizeTimer); resizeTimer = window.setTimeout(measure, 80); }
  function revealed(event: TransitionEvent) {
    if (event.propertyName === 'transform' && event.target instanceof Element && event.target.matches('[data-mesh-quiet]')) queueMeasure();
  }
  const observer = new IntersectionObserver(([entry]) => {
    visible = entry.isIntersecting;
    sync();
  }, { threshold: 0.05 });
  const resizer = new ResizeObserver(queueMeasure);
  observer.observe(hero);
  resizer.observe(hero);
  hero.addEventListener('pointermove', position, { passive: true });
  hero.addEventListener('pointerleave', leave);
  hero.addEventListener('pointerdown', down, { passive: true });
  hero.addEventListener('pointerup', up);
  hero.addEventListener('pointercancel', leave);
  hero.addEventListener('transitionend', revealed);
  window.addEventListener('scroll', leave, { passive: true });
  window.addEventListener('resize', queueMeasure);
  document.addEventListener('visibilitychange', sync);
  reduced.addEventListener('change', sync);
  coarse.addEventListener('change', measure);
  document.fonts.ready.then(() => { if (!disposed) measure(); });
  measure();

  return () => {
    disposed = true;
    cancelAnimationFrame(raf);
    clearTimeout(timer);
    clearTimeout(resizeTimer);
    observer.disconnect(); resizer.disconnect();
    hero.removeEventListener('pointermove', position);
    hero.removeEventListener('pointerleave', leave);
    hero.removeEventListener('pointerdown', down);
    hero.removeEventListener('pointerup', up);
    hero.removeEventListener('pointercancel', leave);
    hero.removeEventListener('transitionend', revealed);
    window.removeEventListener('scroll', leave);
    window.removeEventListener('resize', queueMeasure);
    document.removeEventListener('visibilitychange', sync);
    reduced.removeEventListener('change', sync);
    coarse.removeEventListener('change', measure);
  };
}
