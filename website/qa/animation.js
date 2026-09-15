const output = document.querySelector('#results');
const button = document.querySelector('#run');
const fixture = document.querySelector('#fixture');
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
const until = async check => {
  for (let i = 0; i < 160; i++) { if (check()) return; await wait(100); }
  throw new Error('Timed out waiting for the app');
};

function instrument(options) {
  const stats = window.animationQA = { draws: 0, times: [], stamps: [], preferences: {}, nodes: 0, lines: 0, positions: [] };
  const nativeMedia = window.matchMedia.bind(window);
  window.matchMedia = query => {
    if (query !== '(prefers-reduced-motion: reduce)' && query !== '(pointer: coarse)') return nativeMedia(query);
    if (!stats.preferences[query]) {
      const preference = new EventTarget();
      preference.media = query;
      preference.matches = query.includes('reduced-motion') ? !!options.reduced : !!options.coarse;
      preference.set = value => { preference.matches = value; preference.dispatchEvent(new Event('change')); };
      stats.preferences[query] = preference;
    }
    return stats.preferences[query];
  };
  const clear = CanvasRenderingContext2D.prototype.clearRect;
  const arc = CanvasRenderingContext2D.prototype.arc;
  const stroke = CanvasRenderingContext2D.prototype.stroke;
  CanvasRenderingContext2D.prototype.clearRect = function (...args) {
    if (this.canvas.classList.contains('forge-mesh')) { stats.draws++; stats.nodes = 0; stats.lines = 0; stats.positions.length = 0; }
    return clear.apply(this, args);
  };
  CanvasRenderingContext2D.prototype.arc = function (...args) {
    if (this.canvas.classList.contains('forge-mesh') && (args[2] === 1.25 || args[2] === 2)) {
      stats.nodes++;
      stats.positions.push({ x: args[0], y: args[1] });
    }
    return arc.apply(this, args);
  };
  CanvasRenderingContext2D.prototype.stroke = function (...args) {
    if (this.canvas.classList.contains('forge-mesh')) stats.lines++;
    return stroke.apply(this, args);
  };
  const nativeFrame = window.requestAnimationFrame.bind(window);
  window.requestAnimationFrame = callback => nativeFrame(now => {
    const before = stats.draws;
    const start = performance.now();
    callback(now);
    if (stats.draws > before) {
      stats.times.push(performance.now() - start);
      stats.stamps.push(now);
    }
  });
}

button.addEventListener('click', async () => {
  button.disabled = true;
  const results = [];
  const report = () => { output.textContent = JSON.stringify(results, null, 2); };
  try {
    const source = await (await fetch('/')).text();
    const cases = [
      { width: 1920, height: 1080 },
      { width: 1366, height: 768 },
      { width: 390, height: 844, coarse: true },
      { width: 390, height: 844, reduced: true, coarse: true },
      { width: 1366, height: 768, resizeDuringIntro: true },
      { width: 1366, height: 768, skip: true },
    ];
    for (const options of cases) {
      const row = { options, status: 'running', checks: {} };
      results.push(row); report();
      const iframe = document.createElement('iframe');
      iframe.style.width = options.width + 'px';
      iframe.style.height = options.height + 'px';
      fixture.replaceChildren(iframe);
      iframe.srcdoc = source.replace('</head>', `<script>(${instrument.toString()})(${JSON.stringify(options)})<\/script></head>`);
      await until(() => iframe.contentDocument.querySelector('.forge-nav-logo'));
      const win = iframe.contentWindow;
      const doc = iframe.contentDocument;
      const stats = win.animationQA;
      const originalLogo = doc.querySelector('.forge-nav-logo');
      if (options.resizeDuringIntro) {
        await wait(600);
        iframe.style.width = '390px'; iframe.style.height = '844px';
      }
      if (options.skip) doc.querySelector('.forge-entry-skip')?.click();
      await until(() => doc.querySelector('.is-ready'));
      await doc.fonts.ready;
      await wait(1200);
      const rect = element => element.getBoundingClientRect();
      const logo = doc.querySelector('.forge-nav-logo');
      const home = doc.querySelector('[data-forge-home]');
      const hero = doc.querySelector('#top');
      const canvas = doc.querySelector('.forge-mesh');
      row.checks.sameLogo = logo === originalLogo;
      row.checks.docked = Math.abs(rect(logo).left - rect(home).left) < 1 && Math.abs(rect(logo).top - rect(home).top) < 1;
      row.checks.noOverflow = doc.documentElement.scrollWidth <= win.innerWidth;
      row.checks.canvasDpr = canvas.width / rect(canvas).width <= 1.501;
      row.checks.decorative = canvas.getAttribute('aria-hidden') === 'true' && win.getComputedStyle(canvas).pointerEvents === 'none';
      row.checks.linksAccessible = !!doc.querySelector('a[href="#download"]') && !doc.querySelector('.forge-entry');
      const before = stats.draws;
      stats.times.length = 0; stats.stamps.length = 0;
      await wait(2200);
      // A static redraw after fonts or layout settle is valid; animation-frame draws are not.
      row.checks.motionPreference = options.reduced ? stats.stamps.length === 0 : stats.draws > before + 10;
      const ordered = [...stats.times].sort((a, b) => a - b);
      row.frameWorkMs = { median: ordered[Math.floor(ordered.length * 0.5)] ?? 0, p95: ordered[Math.floor(ordered.length * 0.95)] ?? 0 };
      const stamps = stats.stamps;
      row.observedDrawsPerSecond = stamps.length > 1 ? Math.round((stamps.length - 1) * 1000 / (stamps.at(-1) - stamps[0])) : 0;
      row.nodes = stats.nodes; row.links = stats.lines;
      if (!options.reduced) {
        const targetIndex = stats.positions.findIndex(node => node.x > win.innerWidth * 0.6 && node.y > 150 && node.y < win.innerHeight * 0.8);
        const target = { ...stats.positions[targetIndex] };
        hero.dispatchEvent(new win.PointerEvent('pointermove', { clientX: target.x - 30, clientY: target.y, pointerType: options.coarse ? 'touch' : 'mouse', bubbles: true }));
        await wait(350);
        // Ambient drift travels less than 0.6 px in this interval; displacement must exceed it.
        row.checks.pointerSpringResponse = stats.positions[targetIndex].x - target.x > 1;
        hero.dispatchEvent(new win.PointerEvent('pointerdown', { clientX: target.x - 30, clientY: target.y, button: 0, bubbles: true }));
        await wait(120);
        hero.dispatchEvent(new win.PointerEvent('pointerup', { pointerType: 'touch', bubbles: true }));
        doc.documentElement.style.scrollBehavior = 'auto';
        win.scrollTo(0, hero.offsetHeight + 200);
        await wait(400);
        const paused = stats.draws;
        await wait(400);
        row.checks.offscreenPaused = stats.draws === paused;
        win.scrollTo(0, 0);
        await wait(400);
        row.checks.returns = stats.draws > paused;
        const preference = stats.preferences['(prefers-reduced-motion: reduce)'];
        preference.set(true);
        await wait(100);
        const staticDraw = stats.draws;
        await wait(300);
        row.checks.liveReducedMotion = stats.draws === staticDraw;
        preference.set(false);
        await wait(200);
        row.checks.liveMotionResume = stats.draws > staticDraw;
        // The visibility event path is exercised without changing OS settings.
        Object.defineProperty(doc, 'hidden', { configurable: true, value: true });
        doc.dispatchEvent(new win.Event('visibilitychange'));
        const hiddenDraw = stats.draws;
        await wait(300);
        row.checks.hiddenPaused = stats.draws === hiddenDraw;
        delete doc.hidden;
        doc.dispatchEvent(new win.Event('visibilitychange'));
        await wait(200);
        row.checks.visibleResumed = stats.draws > hiddenDraw;
      }
      row.status = Object.values(row.checks).every(Boolean) ? 'passed' : 'FAILED';
      report();
    }
  } catch (error) {
    results.push({ error: String(error) }); report();
  } finally {
    button.disabled = false;
    document.title = results.every(row => row.status === 'passed') ? 'QA passed' : 'QA needs review';
  }
});
