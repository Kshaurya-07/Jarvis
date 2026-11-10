// Jarvis landing page — interactions only. No tracking, no network calls
// except one same-origin health check that updates the honest status line.
(function () {
  "use strict";
  document.documentElement.classList.add("js");

  var prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---- Scroll reveals: content is visible by default; JS only enhances. ----
  var revealEls = document.querySelectorAll(".reveal");
  if (prefersReducedMotion || !("IntersectionObserver" in window)) {
    revealEls.forEach(function (el) { el.classList.add("is-visible"); });
  } else {
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });
    revealEls.forEach(function (el) { observer.observe(el); });
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

  // ---- Simulated demo: scripted, browser-only, clearly labelled. ----
  var scenarios = {
    file: {
      command: "\u201CLaptop par yeh file kholo aur summarize karo.\u201D",
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

  var chipBtns = Array.prototype.slice.call(document.querySelectorAll(".chip-btn"));
  var commandBubble = document.getElementById("demo-command");
  var runBtn = document.getElementById("demo-run");
  var resetBtn = document.getElementById("demo-reset");
  var logEl = document.getElementById("demo-log");
  var resultEl = document.getElementById("demo-result");
  var noteEl = document.getElementById("demo-note");
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
  function pickScenario(key) {
    if (running) return;
    activeKey = key;
    chipBtns.forEach(function (b) { b.classList.toggle("is-active", b.getAttribute("data-demo") === key); });
    if (commandBubble) commandBubble.textContent = scenarios[key].command;
    resetDemo("Ready. Nothing has been sent anywhere.");
  }
  chipBtns.forEach(function (btn) {
    btn.addEventListener("click", function () { pickScenario(btn.getAttribute("data-demo")); });
  });
  if (resetBtn) resetBtn.addEventListener("click", function () { resetDemo("Reset. Nothing has been sent anywhere."); });

  if (runBtn) {
    runBtn.addEventListener("click", function () {
      if (running) return;
      running = true;
      runBtn.disabled = true;
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
        runBtn.disabled = false;
      }, delay * (scenario.steps.length + 1)));
    });
  }
})();
