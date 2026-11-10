// Jarvis landing page — interactions only. No tracking, no network calls
// except one same-origin health check that updates the honest status line.
(function () {
  "use strict";
  document.documentElement.classList.add("js");

  var prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var finePointer = window.matchMedia("(pointer: fine)").matches;
  var motionOK = !prefersReducedMotion;
  document.documentElement.classList.toggle("has-pointer", finePointer && motionOK);

  function clamp(v, a, b) { return Math.min(Math.max(v, a), b); }

  // ---- Count-up: final value is in the HTML, so no-JS still shows it. ----
  function animateCount(el) {
    var target = parseInt(el.getAttribute("data-count"), 10);
    if (isNaN(target)) return;
    if (prefersReducedMotion) { el.textContent = String(target); return; }
    var start = null, duration = 1200;
    function step(ts) {
      if (!start) start = ts;
      var p = Math.min((ts - start) / duration, 1);
      el.textContent = String(Math.round(target * (1 - Math.pow(1 - p, 3))));
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }
  var countEls = document.querySelectorAll(".count-up");
  if ("IntersectionObserver" in window && !prefersReducedMotion) {
    var countObs = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) { animateCount(entry.target); countObs.unobserve(entry.target); }
      });
    }, { threshold: 0.5 });
    countEls.forEach(function (el) { countObs.observe(el); });
  }

  // ---- Honest backend status: real same-origin check, never faked. ----
  var dot = document.getElementById("backend-dot");
  var statusText = document.getElementById("backend-status-text");
  function setStatus(kind, message) {
    if (!dot || !statusText) return;
    dot.className = "status-dot" + (kind ? " " + kind : "");
    statusText.textContent = message;
  }
  try {
    var controller = new AbortController();
    var timer = setTimeout(function () { controller.abort(); }, 1500);
    fetch("/api/health", { signal: controller.signal, cache: "no-store" })
      .then(function (resp) {
        clearTimeout(timer);
        if (resp.ok) {
          setStatus("ok", "Local Jarvis backend detected on this device.");
        } else {
          setStatus("off", "No Jarvis backend detected here — start it on your laptop, then pair your phone.");
        }
      })
      .catch(function () {
        clearTimeout(timer);
        setStatus("off", "No Jarvis backend detected here — start it on your laptop, then pair your phone.");
      });
  } catch (e) {
    setStatus("off", "Backend status unavailable — start Jarvis on your laptop, then pair your phone.");
  }

  // ---- Unified per-pixel scroll + pointer engine (transform/opacity only). ----
  // Every scroll pixel drives something: hero wordmark/core, orbital diagram,
  // manifesto drift, footer parallax, and progressive reveals tied to scroll
  // progress — not just on/off at a threshold. The loop is demand-driven:
  // it runs while scroll/pointer values are still settling, then stops.
  var revealEls = Array.prototype.slice.call(document.querySelectorAll(".reveal"));
  var heroEl = document.querySelector(".hero");
  var heroWordmark = document.getElementById("hero-wordmark");
  var heroVisual = document.getElementById("hero-visual");
  var howSection = document.querySelector(".how-section");
  var orbitDiagram = document.querySelector(".orbit-diagram");
  var manifesto = document.getElementById("manifesto");
  var manifestoQuote = document.getElementById("manifesto-quote");
  var manifestoCore = document.querySelector(".manifesto-core");
  var footerWord = document.querySelector(".footer-wordmark");
  var glowEl = document.getElementById("cursor-glow");
  var ringEl = document.getElementById("cursor-ring");

  var scrollYPos = window.scrollY || 0;
  var pxT = 0, pyT = 0, pxS = 0, pyS = 0; // pointer, viewport-normalised -1..1
  var glowXT = -200, glowYT = -200, glowXS = -200, glowYS = -200;
  var ringXT = -200, ringYT = -200, ringXS = -200, ringYS = -200;
  var rafRunning = false;

  function applyScroll(y) {
    // Hero: wordmark scales, rises and fades; core scales and tilts with the
    // pointer; every pixel of scrolling moves something.
    if (heroEl && heroWordmark && heroVisual) {
      var rect = heroEl.getBoundingClientRect();
      if (rect.bottom >= 0 && rect.top <= window.innerHeight) {
        var p = clamp(-rect.top / window.innerHeight, 0, 1);
        heroWordmark.style.transform = "translate(-50%, calc(-50% + " + (p * 140).toFixed(1) + "px)) scale(" + (1 + p * 0.5).toFixed(3) + ")";
        heroWordmark.style.opacity = String(Math.max(1 - p * 1.4, 0));
        heroVisual.style.transform = "scale(" + (1 + p * 0.12).toFixed(3) + ") rotateX(" + (-pyS * 4).toFixed(2) + "deg) rotateY(" + (pxS * 6).toFixed(2) + "deg)";
        heroVisual.style.setProperty("--px", pxS.toFixed(3));
        heroVisual.style.setProperty("--py", pyS.toFixed(3));
      }
    }
    // Orbital diagram rotates continuously as you scroll through How it works.
    if (howSection && orbitDiagram) {
      var hr = howSection.getBoundingClientRect();
      var hp = clamp((window.innerHeight - hr.top) / (window.innerHeight + hr.height), 0, 1);
      orbitDiagram.style.transform = "rotate(" + (hp * 60).toFixed(1) + "deg)";
    }
    // Manifesto: core drifts across the quote on scroll (subtle, readable).
    if (manifesto && manifestoQuote && manifestoCore) {
      var mr = manifesto.getBoundingClientRect();
      if (mr.bottom >= 0 && mr.top <= window.innerHeight) {
        var mp = clamp((window.innerHeight - mr.top) / (window.innerHeight + mr.height), 0, 1);
        var shift = (mp - 0.5) * 120;
        manifestoCore.style.transform = "translate(calc(-50% + " + shift.toFixed(1) + "px), -50%) rotate(" + (mp * 24 - 12).toFixed(1) + "deg)";
        manifestoQuote.style.transform = "skewX(" + ((mp - 0.5) * 2).toFixed(2) + "deg)";
      }
    }
    // Footer wordmark parallax.
    if (footerWord) {
      var fr = footerWord.getBoundingClientRect();
      if (fr.bottom >= 0 && fr.top <= window.innerHeight) {
        var fp = clamp((window.innerHeight - fr.top) / (window.innerHeight + fr.height), 0, 1);
        footerWord.style.transform = "translateY(" + ((fp - 0.5) * -36).toFixed(1) + "px)";
      }
    }
    // Progressive reveals: opacity / rise / blur tied to scroll progress.
    // Content is visible by default without JS; this only enhances.
    revealEls.forEach(function (el) {
      if (el.classList.contains("how-step")) return; // steps use the active-step observer
      var r = el.getBoundingClientRect();
      if (r.bottom < 0 || r.top > window.innerHeight) return;
      var p = clamp((window.innerHeight * 0.92 - r.top) / (window.innerHeight * 0.7), 0, 1);
      if (p >= 1) {
        el.classList.add("is-visible");
        el.style.opacity = ""; el.style.transform = ""; el.style.filter = "";
      } else {
        el.style.opacity = p.toFixed(3);
        el.style.transform = "translateY(" + ((1 - p) * 16).toFixed(1) + "px)";
        el.style.filter = "blur(" + ((1 - p) * 3).toFixed(2) + "px)";
      }
    });
  }

  function applyPointer() {
    if (glowEl) glowEl.style.transform = "translate3d(" + glowXS.toFixed(1) + "px," + glowYS.toFixed(1) + "px,0)";
    if (ringEl) ringEl.style.transform = "translate3d(" + ringXS.toFixed(1) + "px," + ringYS.toFixed(1) + "px,0)";
  }

  function tick() {
    rafRunning = true;
    pxS += (pxT - pxS) * 0.16;
    pyS += (pyT - pyS) * 0.16;
    glowXS += (glowXT - glowXS) * 0.2;
    glowYS += (glowYT - glowYS) * 0.2;
    ringXS += (ringXT - ringXS) * 0.35;
    ringYS += (ringYT - ringYS) * 0.35;
    applyScroll(scrollYPos);
    applyPointer();
    var settled = Math.abs(pxT - pxS) < 0.002 && Math.abs(pyT - pyS) < 0.002 &&
      Math.abs(glowXT - glowXS) < 0.5 && Math.abs(glowYT - glowYS) < 0.5 &&
      Math.abs(ringXT - ringXS) < 0.5 && Math.abs(ringYT - ringYS) < 0.5;
    if (settled) { rafRunning = false; return; }
    requestAnimationFrame(tick);
  }
  function requestTick() {
    if (!rafRunning && motionOK) requestAnimationFrame(tick);
  }

  if (motionOK) {
    window.addEventListener("scroll", function () {
      scrollYPos = window.scrollY || 0;
      requestTick();
    }, { passive: true });
    applyScroll(scrollYPos); // paint the correct state immediately on load
  } else {
    revealEls.forEach(function (el) { el.classList.add("is-visible"); });
  }

  // ---- Pointer effects (fine pointers only; touch users are unaffected). ----
  // The native cursor stays visible — the glow + ring are an additive layer.
  if (finePointer && motionOK) {
    document.addEventListener("pointermove", function (ev) {
      pxT = clamp((ev.clientX / window.innerWidth) * 2 - 1, -1, 1);
      pyT = clamp((ev.clientY / window.innerHeight) * 2 - 1, -1, 1);
      glowXT = ev.clientX; glowYT = ev.clientY;
      ringXT = ev.clientX; ringYT = ev.clientY;
      requestTick();
    }, { passive: true });
    document.addEventListener("pointerover", function (ev) {
      if (!ringEl) return;
      var t = ev.target && ev.target.closest ?
        ev.target.closest("a, button, input, .tab-btn, [role='switch'], .card") : null;
      ringEl.classList.toggle("is-hover", !!t);
    });

    // Magnetic buttons: primary/ghost CTAs drift a few px toward the pointer.
    Array.prototype.forEach.call(
      document.querySelectorAll(".hero-ctas .btn, .cta-box .btn, .header-actions .btn"),
      function (btn) {
        btn.addEventListener("pointermove", function (ev) {
          var r = btn.getBoundingClientRect();
          var dx = (ev.clientX - (r.left + r.width / 2)) / r.width;
          var dy = (ev.clientY - (r.top + r.height / 2)) / r.height;
          btn.style.transform = "translate(" + (dx * 10).toFixed(1) + "px, " + (dy * 8).toFixed(1) + "px)";
        });
        btn.addEventListener("pointerleave", function () { btn.style.transform = ""; });
      }
    );

    // 3D tilt on cards: perspective rotate following the pointer, max ~6deg.
    Array.prototype.forEach.call(
      document.querySelectorAll(".card, .chart-wrap, .cta-box"),
      function (card) {
        card.addEventListener("pointermove", function (ev) {
          var r = card.getBoundingClientRect();
          var rx = -((ev.clientY - r.top) / r.height - 0.5) * 12;
          var ry = ((ev.clientX - r.left) / r.width - 0.5) * 12;
          card.style.setProperty("--rx", rx.toFixed(2) + "deg");
          card.style.setProperty("--ry", ry.toFixed(2) + "deg");
          card.classList.add("is-tilting");
        });
        card.addEventListener("pointerleave", function () {
          card.classList.remove("is-tilting");
          card.style.setProperty("--rx", "0deg");
          card.style.setProperty("--ry", "0deg");
        });
      }
    );
  }

  // ---- Generic tabs (comparison section). ----
  function initTabs(tablist) {
    if (!tablist) return;
    var btns = Array.prototype.slice.call(tablist.querySelectorAll(".tab-btn[data-tab]"));
    if (!btns.length) return;
    btns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        btns.forEach(function (b) {
          var active = b === btn;
          b.classList.toggle("is-active", active);
          b.setAttribute("aria-selected", active ? "true" : "false");
        });
        btns.forEach(function (b) {
          var panel = document.getElementById(b.getAttribute("data-tab"));
          if (!panel) return;
          var active = b === btn;
          panel.hidden = !active;
          panel.classList.toggle("is-active", active);
          if (active) panel.classList.add("is-visible"); // grows the bars
        });
      });
    });
    var first = document.getElementById(btns[0].getAttribute("data-tab"));
    if (first) first.classList.add("is-visible");
  }
  document.querySelectorAll('[role="tablist"]').forEach(function (tl) {
    if (tl.querySelector(".tab-btn[data-tab]")) initTabs(tl);
  });

  // ---- How it works: highlight the active step + orbital node on scroll. ----
  var howSteps = Array.prototype.slice.call(document.querySelectorAll(".how-step"));
  var howNodes = Array.prototype.slice.call(document.querySelectorAll(".orbit-node"));
  var howCaption = document.getElementById("how-diagram-caption");
  var stepTitles = howSteps.map(function (s) {
    var h = s.querySelector("h3");
    return h ? h.textContent : "";
  });
  function setActiveStep(i) {
    howSteps.forEach(function (s, j) { s.classList.toggle("is-active", j === i); });
    howNodes.forEach(function (n, j) { n.classList.toggle("is-active", j === i); });
    if (howCaption) howCaption.textContent = "Step " + (i + 1) + " of 4 — " + stepTitles[i];
  }
  if (howSteps.length && "IntersectionObserver" in window && !prefersReducedMotion) {
    var stepObs = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) setActiveStep(parseInt(entry.target.getAttribute("data-step"), 10));
      });
    }, { rootMargin: "-40% 0px -40% 0px" });
    howSteps.forEach(function (s) { stepObs.observe(s); });
  } else if (howSteps.length) {
    setActiveStep(0);
  }

  // ---- Simulated demo: scripted, browser-only, clearly labelled. ----
  var scenarios = {
    file: {
      command: "\u201CLaptop par yeh file kholo aur summarize karo.\u201D",
      branchNote: "Branch A — reading a file inside the approved workspace.",
      steps: [
        "Phone sends the command to the paired laptop.",
        "Jarvis checks the file is inside your approved workspace.",
        "Jarvis reads the file and explains the plan before acting.",
        "Summary prepared on the laptop and sent back to your phone."
      ],
      result: "Result (simulated): the file was summarised on your laptop. In the real companion, the summary would appear in your chat with a note of which file was read."
    },
    website: {
      command: "\u201CLaptop par yeh website kholo.\u201D",
      branchNote: "Branch B — the domain is checked against your approved list first.",
      steps: [
        "Phone sends the command to the paired laptop.",
        "Jarvis checks the website's domain against your approved list.",
        "Domain is approved, so Jarvis opens it in the laptop browser.",
        "Jarvis confirms the page opened and offers a summary."
      ],
      result: "Result (simulated): the website opened on your laptop. If the domain were not approved, Jarvis would ask you to approve it first instead of opening it."
    },
    reminder: {
      command: "\u201CMere phone par reminder set karo.\u201D",
      branchNote: "Branch C — phone-side actions are not built yet, so this path stops honestly.",
      steps: [
        "Phone sends the command to the paired laptop.",
        "Jarvis understands the target is your phone, not the laptop.",
        "Phone-side actions are not built yet, so Jarvis cannot set the reminder there.",
        "Jarvis explains this honestly and offers the laptop reminder instead."
      ],
      result: "Result (simulated): not available yet. This is the planned laptop-to-phone direction on the roadmap — Jarvis says so instead of pretending it worked.",
      warn: true
    }
  };

  var demoTabBtns = Array.prototype.slice.call(document.querySelectorAll(".demo-tabs .tab-btn[data-demo]"));
  var commandBubble = document.getElementById("demo-command");
  var runBtn = document.getElementById("demo-run");
  var rerunBtn = document.getElementById("demo-rerun");
  var resetBtn = document.getElementById("demo-reset");
  var logEl = document.getElementById("demo-log");
  var resultEl = document.getElementById("demo-result");
  var noteEl = document.getElementById("demo-note");
  var branchNoteEl = document.getElementById("branch-note");
  var activeKey = "file";
  var timers = [];
  var running = false;

  function clearTimers() {
    timers.forEach(function (t) { clearTimeout(t); });
    timers = [];
  }
  function resetDemo(message) {
    clearTimers();
    running = false;
    if (runBtn) runBtn.disabled = false;
    if (logEl) logEl.innerHTML = '<li class="demo-log-empty">No command yet. Choose one and press \u201CSend to laptop\u201D.</li>';
    if (resultEl) { resultEl.hidden = true; resultEl.textContent = ""; }
    if (noteEl) noteEl.textContent = message || "Ready. Nothing has been sent anywhere.";
  }
  function highlightBranch(key) {
    document.querySelectorAll(".branch").forEach(function (b) {
      b.classList.toggle("is-active", b.getAttribute("data-branch") === key);
    });
    document.querySelectorAll(".branch-check").forEach(function (b) {
      b.classList.toggle("is-active", b.getAttribute("data-branch") === key);
    });
    if (branchNoteEl) branchNoteEl.textContent = scenarios[key].branchNote;
  }
  function pickScenario(key) {
    if (running) return;
    activeKey = key;
    demoTabBtns.forEach(function (b) {
      var active = b.getAttribute("data-demo") === key;
      b.classList.toggle("is-active", active);
      b.setAttribute("aria-selected", active ? "true" : "false");
    });
    if (commandBubble) commandBubble.textContent = scenarios[key].command;
    highlightBranch(key);
    resetDemo("Ready. Nothing has been sent anywhere.");
  }
  demoTabBtns.forEach(function (btn) {
    btn.addEventListener("click", function () { pickScenario(btn.getAttribute("data-demo")); });
  });
  if (resetBtn) resetBtn.addEventListener("click", function () { resetDemo("Reset. Nothing has been sent anywhere."); });

  function runDemo() {
    if (running) return;
    running = true;
    if (runBtn) runBtn.disabled = true;
    var scenario = scenarios[activeKey];
    if (logEl) logEl.innerHTML = "";
    if (resultEl) { resultEl.hidden = true; resultEl.textContent = ""; }
    if (noteEl) noteEl.textContent = "Simulated — running in your browser only. No real device is controlled.";
    var delay = prefersReducedMotion ? 0 : 700;
    scenario.steps.forEach(function (step, i) {
      timers.push(setTimeout(function () {
        var li = document.createElement("li");
        var time = document.createElement("span");
        time.className = "log-time";
        time.textContent = "0" + (i + 1) + ":0" + (i + 1);
        li.appendChild(time);
        li.appendChild(document.createTextNode(step));
        if (logEl) logEl.appendChild(li);
      }, delay * (i + 1)));
    });
    timers.push(setTimeout(function () {
      if (resultEl) {
        resultEl.innerHTML = "";
        var strong = document.createElement("strong");
        strong.textContent = scenario.warn ? "Not available yet — " : "Done (simulated). ";
        resultEl.appendChild(strong);
        resultEl.appendChild(document.createTextNode(scenario.result.replace(/^Result \(simulated\): /, "")));
        resultEl.hidden = false;
      }
      if (noteEl) noteEl.textContent = "Simulated demo finished. Nothing was sent to any device.";
      running = false;
      if (runBtn) runBtn.disabled = false;
    }, delay * (scenario.steps.length + 1)));
  }
  if (runBtn) runBtn.addEventListener("click", runDemo);
  if (rerunBtn) rerunBtn.addEventListener("click", function () { resetDemo(); runDemo(); });
  highlightBranch("file");

  // ---- Chart tooltip: real registry counts, pointer-following. ----
  var chartSvg = document.getElementById("tools-chart-svg");
  var chartTip = document.getElementById("chart-tooltip");
  var chartCursor = document.getElementById("chart-cursor");
  var chartData = [
    { label: "Files & notes", tools: 4, total: 4, x: 60 },
    { label: "Device & screen", tools: 6, total: 10, x: 163.3 },
    { label: "Reminders", tools: 4, total: 14, x: 266.7 },
    { label: "Memory", tools: 3, total: 17, x: 370 },
    { label: "Search & briefing", tools: 2, total: 19, x: 473.3 },
    { label: "Google (read-only)", tools: 4, total: 23, x: 576.7 },
    { label: "Browser", tools: 3, total: 26, x: 680 }
  ];
  function chartY(v) { return 280 - (v / 26) * 240; }
  if (chartSvg && chartTip && chartCursor) {
    chartSvg.addEventListener("pointermove", function (ev) {
      var rect = chartSvg.getBoundingClientRect();
      var svgX = (ev.clientX - rect.left) / rect.width * 720;
      var nearest = chartData[0];
      chartData.forEach(function (d) {
        if (Math.abs(d.x - svgX) < Math.abs(nearest.x - svgX)) nearest = d;
      });
      chartCursor.setAttribute("cx", String(nearest.x));
      chartCursor.setAttribute("cy", String(chartY(nearest.tools)));
      chartCursor.setAttribute("opacity", "1");
      chartTip.hidden = false;
      chartTip.textContent = nearest.label + ": " + nearest.tools + " tools · running total " + nearest.total;
      chartTip.style.left = ((nearest.x / 720) * 100) + "%";
      chartTip.style.top = ((chartY(nearest.tools) / 340) * 100) + "%";
    });
    chartSvg.addEventListener("pointerleave", function () {
      chartCursor.setAttribute("opacity", "0");
      chartTip.hidden = true;
    });
  }

  // ---- Developers: code tabs, typing effect, real copy button. ----
  var codeSamples = {
    curl: "curl http://localhost:8000/api/health\n\n# {\"status\": \"ok\", ...}\n# No key needed — the health check is public on localhost.",
    python: "import httpx\n\nresp = httpx.get(\"http://localhost:8000/api/health\", timeout=5)\nprint(resp.json())  # {\"status\": \"ok\", ...}",
    typescript: "const resp = await fetch(\"http://localhost:8000/api/health\");\nconst health = await resp.json();\nconsole.log(health); // { status: \"ok\", ... }"
  };
  var codeBtns = Array.prototype.slice.call(document.querySelectorAll(".code-tabs .tab-btn[data-code]"));
  var codeText = document.getElementById("code-text");
  var copyBtn = document.getElementById("copy-code");
  var copyNote = document.getElementById("copy-note");
  var activeCode = "curl";
  var typeTimer = null;
  function typeCode(key) {
    if (!codeText) return;
    var full = codeSamples[key];
    if (typeTimer) clearInterval(typeTimer);
    if (prefersReducedMotion) { codeText.textContent = full; return; }
    var i = 0;
    codeText.textContent = "";
    typeTimer = setInterval(function () {
      i += 3;
      codeText.textContent = full.slice(0, i);
      if (i >= full.length) { clearInterval(typeTimer); typeTimer = null; }
    }, 16);
  }
  codeBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      activeCode = btn.getAttribute("data-code");
      codeBtns.forEach(function (b) {
        var active = b === btn;
        b.classList.toggle("is-active", active);
        b.setAttribute("aria-selected", active ? "true" : "false");
      });
      typeCode(activeCode);
      if (copyNote) copyNote.textContent = "Health check against the backend on your own laptop. No key needed for /api/health.";
      if (copyBtn) copyBtn.textContent = "Copy code";
    });
  });
  if (codeText) typeCode("curl");
  if (copyBtn) {
    copyBtn.addEventListener("click", function () {
      var text = codeSamples[activeCode];
      function done(ok) {
        copyBtn.textContent = ok ? "Copied ✓" : "Copy failed — select the code manually";
        if (copyNote) copyNote.textContent = ok ? "Copied to your clipboard." : "Clipboard access was blocked; select the code and copy it manually.";
        setTimeout(function () { copyBtn.textContent = "Copy code"; }, 2500);
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () { done(true); }, function () { done(false); });
      } else {
        var ta = document.createElement("textarea");
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        var ok = false;
        try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
        document.body.removeChild(ta);
        done(ok);
      }
    });
  }

  // ---- Simulated stream feed: plays when visible, replayable. ----
  var streamLines = [
    ["thinking.step", "read the request and work out the target device"],
    ["thinking.step", "check the file is inside the approved workspace"],
    ["tool.call", "list_files · workspace"],
    ["tool.result", "12 files listed · 0 outside the workspace"],
    ["tool.call", "read_text_file · notes/plan.md"],
    ["thinking.check", "confirmation not needed — read-only"],
    ["answer.delta", "Here is the summary of your notes…"],
    ["answer.done", "simulated stream · no backend call was made"]
  ];
  var streamLog = document.getElementById("stream-log");
  var streamReplay = document.getElementById("stream-replay");
  var streamTimers = [];
  var streamPlayed = false;
  function playStream() {
    if (!streamLog) return;
    streamTimers.forEach(function (t) { clearTimeout(t); });
    streamTimers = [];
    streamLog.innerHTML = "";
    var delay = prefersReducedMotion ? 0 : 650;
    streamLines.forEach(function (line, i) {
      streamTimers.push(setTimeout(function () {
        var li = document.createElement("li");
        var kind = document.createElement("span");
        kind.className = "stream-kind";
        kind.textContent = line[0];
        li.appendChild(kind);
        li.appendChild(document.createTextNode(line[1]));
        if (i === streamLines.length - 1) li.classList.add("stream-done");
        streamLog.appendChild(li);
      }, delay * (i + 1)));
    });
  }
  if (streamLog && "IntersectionObserver" in window) {
    var streamObs = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting && !streamPlayed) { streamPlayed = true; playStream(); streamObs.disconnect(); }
      });
    }, { threshold: 0.3 });
    streamObs.observe(streamLog);
  }
  if (streamReplay) streamReplay.addEventListener("click", playStream);

  // ---- Access: spoken-reply preview toggle (controls real content). ----
  var spokenToggle = document.getElementById("spoken-toggle");
  var spokenPreview = document.getElementById("spoken-preview");
  if (spokenToggle && spokenPreview) {
    spokenToggle.addEventListener("click", function () {
      var on = spokenToggle.getAttribute("aria-checked") !== "true";
      spokenToggle.setAttribute("aria-checked", on ? "true" : "false");
      spokenPreview.hidden = !on;
    });
  }

  // ---- Final CTA: preview box sends nothing. ----
  var askForm = document.getElementById("ask-form");
  var askInput = document.getElementById("ask-input");
  var askNote = document.getElementById("ask-note");
  if (askForm && askNote) {
    askForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      askNote.textContent = "Preview only — your question was not sent anywhere. Open the companion to ask Jarvis for real.";
      if (askInput) askInput.value = "";
    });
  }
})();
