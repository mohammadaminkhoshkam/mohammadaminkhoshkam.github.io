// Shared behaviour: theme toggle, mobile menu, signal-wave background, reveal-on-scroll, project filters.
(function () {
  const root = document.documentElement;

  // ----- Theme -----
  function readTheme() { try { return localStorage.getItem("theme"); } catch (e) { return null; } }
  function saveTheme(t) { try { localStorage.setItem("theme", t); } catch (e) { /* ignore */ } }
  const saved = readTheme();
  if (saved === "light" || saved === "dark") root.setAttribute("data-theme", saved);

  function currentTheme() {
    const t = root.getAttribute("data-theme");
    if (t) return t;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  document.addEventListener("DOMContentLoaded", function () {
    const toggle = document.getElementById("theme-toggle");
    if (toggle) {
      toggle.addEventListener("click", function () {
        const next = currentTheme() === "dark" ? "light" : "dark";
        root.setAttribute("data-theme", next);
        saveTheme(next);
      });
    }

    // ----- Mobile menu -----
    const menuBtn = document.getElementById("menu-btn");
    const links = document.querySelector(".nav-links");
    if (menuBtn && links) {
      menuBtn.addEventListener("click", function () {
        const open = links.classList.toggle("open");
        menuBtn.setAttribute("aria-expanded", String(open));
      });
      links.querySelectorAll("a").forEach(function (a) {
        a.addEventListener("click", function () { links.classList.remove("open"); });
      });
    }

    // ----- Footer year -----
    document.querySelectorAll("[data-year]").forEach(function (el) { el.textContent = new Date().getFullYear(); });

    // ----- Reveal on scroll -----
    const revealEls = document.querySelectorAll(".reveal");
    if ("IntersectionObserver" in window) {
      const io = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
        });
      }, { threshold: 0.12 });
      revealEls.forEach(function (el) { io.observe(el); });
    } else {
      revealEls.forEach(function (el) { el.classList.add("in"); });
    }

    // ----- Project filters -----
    const chips = document.querySelectorAll(".chip[data-filter]");
    const projects = document.querySelectorAll(".project[data-cat]");
    chips.forEach(function (chip) {
      chip.addEventListener("click", function () {
        const f = chip.dataset.filter;
        chips.forEach(function (c) { c.setAttribute("aria-pressed", String(c === chip)); });
        projects.forEach(function (p) {
          p.hidden = !(f === "all" || p.dataset.cat.split(" ").indexOf(f) !== -1);
        });
      });
    });

    // ----- Signal-wave background -----
    document.querySelectorAll("canvas[data-waves]").forEach(startWaves);
  });

  function startWaves(canvas) {
    const ctx = canvas.getContext("2d");
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let w = 0, h = 0, dpr = 1, t = 0, visible = true;

    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = canvas.clientWidth; h = canvas.clientHeight;
      canvas.width = w * dpr; canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function color(name) { return getComputedStyle(root).getPropertyValue(name).trim(); }

    // A carrier, a modulated signal and a faint noise floor — like a scope trace.
    const traces = [
      { amp: 0.16, freq: 1.6, speed: 0.6, off: 0.55, varName: "--accent", width: 1.6, mod: 0.35 },
      { amp: 0.10, freq: 3.1, speed: -0.9, off: 0.62, varName: "--accent-2", width: 1.2, mod: 0.0 },
      { amp: 0.06, freq: 6.5, speed: 1.4, off: 0.70, varName: "--border", width: 1, mod: 0.6 }
    ];

    function draw() {
      ctx.clearRect(0, 0, w, h);
      traces.forEach(function (tr) {
        ctx.beginPath();
        ctx.strokeStyle = color(tr.varName);
        ctx.lineWidth = tr.width;
        ctx.globalAlpha = 0.9;
        for (let x = 0; x <= w; x += 3) {
          const u = x / w;
          const env = 1 + tr.mod * Math.sin(u * Math.PI * 2 * 0.7 + t * 0.4);
          const y = h * tr.off + Math.sin(u * Math.PI * 2 * tr.freq + t * tr.speed) * h * tr.amp * env;
          if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.stroke();
      });
      ctx.globalAlpha = 1;
    }

    function loop() {
      if (visible) { t += 0.016; draw(); }
      requestAnimationFrame(loop);
    }

    resize();
    window.addEventListener("resize", resize);
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (e) { visible = e[0].isIntersecting; }).observe(canvas);
    }
    if (reduce) { draw(); } else { loop(); }
  }
})();
