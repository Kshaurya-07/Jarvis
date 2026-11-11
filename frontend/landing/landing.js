/* ==========================================================================
   Jarvis — Scientific Instrument Landing Page
   Raw WebGL Gravitational Lensing Engine + Scroll-Driven Accretion Journey
   ========================================================================== */

(function () {
  "use strict";
  document.documentElement.classList.add("js");

  var prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var finePointer = window.matchMedia("(pointer: fine)").matches;
  var motionOK = !prefersReducedMotion;
  document.documentElement.classList.toggle("has-pointer", finePointer && motionOK);

  function clamp(v, a, b) {
    if (a === undefined) a = 0;
    if (b === undefined) b = 1;
    return Math.min(Math.max(v, a), b);
  }

  function lerp(a, b, t) {
    return a + (b - a) * t;
  }

  // ==========================================================================
  // 1. RAW WEBGL GRAVITATIONAL LENSING & 3D JOURNEY
  // ==========================================================================
  var canvas = document.getElementById("bg-canvas");
  var gl = null;
  if (canvas) {
    try {
      gl = canvas.getContext("webgl", {
        antialias: false,
        alpha: false,
        depth: false,
        powerPreference: "high-performance"
      }) || canvas.getContext("experimental-webgl");
    } catch (e) {
      gl = null;
    }
  }

  if (!gl && canvas) {
    canvas.style.display = "none";
  }

  var uniforms = {};
  var webglProgram = null;
  var textTexture = null;
  var blank = 0;

  // Smoothed animation state
  var sm = {
    z: 1.0,
    e: 0.09,
    a: 1.0,
    ta: 1.0,
    h: 0.0,
    s: 0.0,
    hold: 0.0
  };
  var isHolding = false;

  var VS_SOURCE = [
    "attribute vec2 p;",
    "void main(){",
    "  gl_Position = vec4(p, 0.0, 1.0);",
    "}"
  ].join("\n");

  var FS_SOURCE = [
    "precision highp float;",
    "uniform vec2 R;",
    "uniform float T, E, Z, A, TA, H, S;",
    "uniform sampler2D tx;",
    "",
    "float h(vec2 p){return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);}",
    "float n(vec2 p){",
    "  vec2 i = floor(p), f = fract(p);",
    "  f = f * f * (3.0 - 2.0 * f);",
    "  return mix(mix(h(i), h(i + vec2(1.0, 0.0)), f.x), mix(h(i + vec2(0.0, 1.0)), h(i + vec2(1.0, 1.0)), f.x), f.y);",
    "}",
    "",
    "vec3 disk(vec2 q, float ri, float ro, float d){",
    "  float r = length(q);",
    "  float a = T * 0.45 / (r * sqrt(r) + 0.05);",
    "  vec2 p = mat2(cos(a), -sin(a), sin(a), cos(a)) * q;",
    "  float b = 0.5 + 0.5 * sin(r * 150.0 + n(p * 9.0) * 5.0);",
    "  float g = n(p * 22.0) * 0.6 + 0.4;",
    "  float m = smoothstep(ri, ri + 0.02, r) * (1.0 - smoothstep(ro * 0.55, ro, r));",
    "  return vec3(1.0, 0.93, 0.82) * m * b * g * (0.05 / (r * r + 0.015)) * d;",
    "}",
    "",
    "void main(){",
    "  vec2 u = (gl_FragCoord.xy - 0.5 * R) / R.y;",
    "  u /= Z;",
    "  float R0 = 0.15, r = length(u), s = max(sin(E), 0.04);",
    "  vec2 sp = floor(gl_FragCoord.xy / 2.0);",
    "  vec3 c = vec3(step(0.9985, h(sp)) * (0.4 + 0.6 * sin(T + h(sp) * 40.0)) * 0.7);",
    "  vec2 src = u * (1.0 - 1.8 * R0 * R0 / max(r * r, 0.0001));",
    "  float w = 0.9 * R.x / R.y;",
    "  vec2 tv = vec2(src.x / w + 0.5, src.y / (w * 0.5) + 0.5);",
    "  if (tv.x > 0.0 && tv.x < 1.0 && tv.y > 0.0 && tv.y < 1.0) {",
    "    c += vec3(0.95, 0.92, 0.86) * texture2D(tx, tv).r * TA * 0.9;",
    "  }",
    "  float aw = 1.0 - smoothstep(0.2, 1.4, E);",
    "  c += disk(u, R0 * 1.04, R0 * 2.4, 1.0) * aw * 0.8 + vec3(1.0, 0.93, 0.82) * smoothstep(0.012, 0.0, abs(r - R0 * 1.06)) * 0.9;",
    "  c *= smoothstep(R0 * 0.98, R0, r);",
    "  vec2 q = vec2(u.x, u.y / s);",
    "  float ro = mix(1.5, 0.62, H);",
    "  float dop = 0.6 + 0.8 * (0.5 + 0.5 * clamp(q.x / max(length(q), 0.01), -1.0, 1.0));",
    "  float fm = u.y < 0.0 ? 1.0 : smoothstep(R0 * 0.98, R0 * 1.02, r);",
    "  c += disk(q, 0.2, ro, dop) * fm;",
    "  for (int i = 0; i < 4; i++) {",
    "    float f = float(i), ri = mix(0.62, 0.26, f / 3.0), a = 1.0 - clamp(abs(S - f), 0.0, 1.0);",
    "    float l = smoothstep(0.004, 0.0, abs(length(q) - ri)) * (0.2 + 0.9 * a);",
    "    vec2 dp = ri * vec2(cos(T * 0.8 + f), sin(T * 0.8 + f));",
    "    l += smoothstep(0.014, 0.0, length(q - dp)) * a * 2.0;",
    "    c += vec3(0.3, 0.42, 1.0) * l * H * fm;",
    "  }",
    "  c = 1.0 - exp(-c * 1.6);",
    "  gl_FragColor = vec4(c * A, 1.0);",
    "}"
  ].join("\n");

  function createShader(glCtx, type, source) {
    var sh = glCtx.createShader(type);
    glCtx.shaderSource(sh, source);
    glCtx.compileShader(sh);
    if (!glCtx.getShaderParameter(sh, glCtx.COMPILE_STATUS)) {
      console.warn("Shader error:", glCtx.getShaderInfoLog(sh));
      glCtx.deleteShader(sh);
      return null;
    }
    return sh;
  }

  function initWebGL() {
    if (!gl) return;
    var vs = createShader(gl, gl.VERTEX_SHADER, VS_SOURCE);
    var fs = createShader(gl, gl.FRAGMENT_SHADER, FS_SOURCE);
    if (!vs || !fs) return;

    webglProgram = gl.createProgram();
    gl.attachShader(webglProgram, vs);
    gl.attachShader(webglProgram, fs);
    gl.linkProgram(webglProgram);
    if (!gl.getProgramParameter(webglProgram, gl.LINK_STATUS)) {
      console.warn("WebGL link error:", gl.getProgramInfoLog(webglProgram));
      return;
    }

    gl.useProgram(webglProgram);

    // Full-screen triangle buffer
    var buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);

    var pl = gl.getAttribLocation(webglProgram, "p");
    gl.enableVertexAttribArray(pl);
    gl.vertexAttribPointer(pl, 2, gl.FLOAT, false, 0, 0);

    ["R", "T", "E", "Z", "A", "TA", "H", "S"].forEach(function (k) {
      uniforms[k] = gl.getUniformLocation(webglProgram, k);
    });

    textTexture = gl.createTexture();
    renderTextTexture();

    if (document.fonts) {
      try {
        document.fonts.load('600 280px "Inter Tight"').then(renderTextTexture);
        if (document.fonts.ready) document.fonts.ready.then(renderTextTexture);
      } catch (e) {}
    }
  }

  function renderTextTexture() {
    if (!gl || !textTexture) return;
    var c = document.createElement("canvas");
    c.width = 1024;
    c.height = 512;
    var ctx = c.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, 1024, 512);
    ctx.fillStyle = "#ffffff";
    ctx.font = '600 280px "Inter Tight", system-ui, sans-serif';
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("Jarvis", 512, 265);

    gl.bindTexture(gl.TEXTURE_2D, textTexture);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, c);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  }

  function resizeWebGL() {
    if (!gl || !canvas) return;
    var q = Math.min(window.devicePixelRatio || 1, 1.5) * 0.8;
    var w = Math.round(window.innerWidth * q);
    var h = Math.round(window.innerHeight * q);
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
      gl.viewport(0, 0, w, h);
    }
  }

  // ==========================================================================
  // 2. SCROLL TARGETS COMPUTATION
  // ==========================================================================
  var howSection = document.getElementById("how");
  var heroCentre = document.getElementById("hero-centre");
  var hudDist = document.getElementById("hud-dist");
  var hudInc = document.getElementById("hud-inc");
  var howSteps = Array.prototype.slice.call(document.querySelectorAll(".how-step-card"));
  var railFill = document.getElementById("how-rail-fill");
  var railSteps = Array.prototype.slice.call(document.querySelectorAll(".how-rail-step"));
  var orbitBadges = [
    document.getElementById("orbit-lb-0"),
    document.getElementById("orbit-lb-1"),
    document.getElementById("orbit-lb-2"),
    document.getElementById("orbit-lb-3")
  ].filter(Boolean);

  function getScrollTargets() {
    var y = window.scrollY || window.pageYOffset || 0;
    var vh = window.innerHeight;
    var ht = howSection ? howSection.offsetTop : 99999;
    var hh = howSection ? (howSection.offsetHeight - vh) : 1;
    var hp = clamp((y - ht) / (hh > 0 ? hh : 1), 0, 1);
    var hero = clamp(y / vh, 0, 1);
    var hv = Math.min(
      clamp((y - (ht - vh * 0.8)) / (vh * 0.8), 0, 1),
      1.0 - clamp((y - (ht + hh)) / (vh * 0.6), 0, 1)
    );
    var on = hv > 0;

    var tg = {
      z: on ? (1.0 + 0.25 * hp) : (1.0 + 2.2 * Math.pow(hero, 1.4) + 0.5 * sm.hold * (1.0 - hero)),
      e: on ? lerp(1.45, 0.12, hp) : 0.09,
      a: on ? hv : (1.0 - clamp((hero - 0.55) / 0.45, 0, 1)),
      ta: on ? 0.0 : (1.0 - clamp(hero * 2.5, 0, 1)),
      h: clamp(hv, 0, 1),
      s: hp * 3.0
    };

    return { hero: hero, hp: hp, hv: hv, on: on, tg: tg };
  }

  // ==========================================================================
  // 3. MOUSE / TOUCH HOLD & PARALLAX
  // ==========================================================================
  window.addEventListener("pointerdown", function (e) {
    if (e.target.closest("a, button, input, textarea, select, [role='button'], .tab-btn")) return;
    isHolding = true;
    if (cursorDot) {
      cursorDot.style.width = "64px";
      cursorDot.style.height = "64px";
      cursorDot.style.margin = "-32px 0 0 -32px";
    }
  });

  window.addEventListener("pointerup", function () {
    isHolding = false;
    if (cursorDot) {
      cursorDot.style.width = "34px";
      cursorDot.style.height = "34px";
      cursorDot.style.margin = "-17px 0 0 -17px";
    }
  });

  // ==========================================================================
  // 4. WORD-BY-WORD SCROLL REVEAL (Why Jarvis Exists)
  // ==========================================================================
  var whyStatement = document.getElementById("statement-text");
  var whyWords = [];
  if (whyStatement) {
    var rawText = whyStatement.textContent.trim();
    var words = rawText.split(/\s+/);
    whyStatement.innerHTML = words.map(function (w) {
      return '<span class="rv-word">' + w + "</span>";
    }).join(" ");
    whyWords = Array.prototype.slice.call(whyStatement.querySelectorAll(".rv-word"));
  }

  function updateWordReveal() {
    if (!whyStatement || !whyWords.length) return;
    if (prefersReducedMotion) {
      whyWords.forEach(function (w) { w.style.opacity = "1"; });
      return;
    }
    var r = whyStatement.getBoundingClientRect();
    var vh = window.innerHeight;
    var p = clamp((vh * 0.85 - r.top) / (r.height + vh * 0.35), 0, 1);
    var kWord = p * (whyWords.length + 4);
    whyWords.forEach(function (w, i) {
      w.style.opacity = (0.18 + 0.82 * clamp(kWord - i, 0, 1)).toFixed(2);
    });
  }

  // ==========================================================================
  // 5. CHAPTER NAVIGATION SCROLL-SPY
  // ==========================================================================
  var chapterNavLinks = Array.prototype.slice.call(document.querySelectorAll("#chapter-nav .chapter-link"));
  var chapters = ["companion", "why", "how", "privacy", "access"];

  function updateChapterNav() {
    var vh = window.innerHeight;
    var activeId = "companion";
    for (var i = 0; i < chapters.length; i++) {
      var sec = document.getElementById(chapters[i]);
      if (sec && sec.getBoundingClientRect().top < vh * 0.5) {
        activeId = chapters[i];
      }
    }
    chapterNavLinks.forEach(function (link) {
      link.classList.toggle("is-active", link.getAttribute("data-chapter") === activeId);
    });
  }

  // ==========================================================================
  // 6. CUSTOM DIFFERENCE CURSOR (34px, lerp smoothed)
  // ==========================================================================
  var cursorDot = document.getElementById("cursor-dot");
  var mouseX = -999, mouseY = -999;
  var curX = -999, curY = -999;

  if (finePointer && motionOK && cursorDot) {
    window.addEventListener("pointermove", function (e) {
      mouseX = e.clientX;
      mouseY = e.clientY;
    }, { passive: true });

    document.addEventListener("pointerover", function (e) {
      var isInteractive = e.target && e.target.closest &&
        e.target.closest("a, button, input, .tab-btn, [role='switch'], .card, .chart-svg-wrap");
      cursorDot.classList.toggle("is-active", !!isInteractive);
    });
  }

  // ==========================================================================
  // 7. MAIN RENDER & DOM UPDATE LOOP
  // ==========================================================================
  var currentStepIdx = -1;

  function frame(timestamp) {
    var state = getScrollTargets();
    var k = motionOK ? 0.09 : 1.0;

    // Smooth state interpolation
    for (var prop in state.tg) {
      sm[prop] = lerp(sm[prop], state.tg[prop], k);
    }
    sm.hold = lerp(sm.hold, isHolding ? 1.0 : 0.0, motionOK ? 0.06 : 1.0);

    // Smooth cursor
    if (finePointer && motionOK && cursorDot) {
      curX = lerp(curX, mouseX, 0.25);
      curY = lerp(curY, mouseY, 0.25);
      cursorDot.style.transform = "translate3d(" + curX.toFixed(1) + "px, " + curY.toFixed(1) + "px, 0)";
    }

    // Hero HUD & Blur/Fade on scroll out
    if (hudDist) {
      var dVal = Math.max((26.0 - 22.0 * state.hero) - sm.hold * 4.0, 1.2);
      hudDist.textContent = dVal.toFixed(1);
    }
    if (hudInc) {
      var incDeg = 90.0 - sm.e * 57.2958;
      hudInc.textContent = incDeg.toFixed(1);
    }
    if (heroCentre) {
      var heroOpacity = Math.max(0, 1.0 - state.hero * 1.8);
      var heroBlur = state.hero * 8.0;
      heroCentre.style.opacity = heroOpacity.toFixed(2);
      heroCentre.style.filter = heroBlur > 0.1 ? "blur(" + heroBlur.toFixed(1) + "px)" : "none";
    }

    // How It Works Step Swaps & Rail Fill
    var stepIdx = clamp(Math.floor(state.hp * 4.0), 0, 3);
    if (stepIdx !== currentStepIdx) {
      currentStepIdx = stepIdx;
      howSteps.forEach(function (card, idx) {
        card.classList.toggle("is-active", idx === stepIdx);
      });
      railSteps.forEach(function (rStep, idx) {
        rStep.classList.toggle("is-active", idx === stepIdx);
      });
    }
    if (railFill) {
      railFill.style.height = (state.hp * 100).toFixed(1) + "%";
    }

    // Screen-Projected 3D Orbit Badges
    var winH = window.innerHeight;
    var winW = window.innerWidth;
    orbitBadges.forEach(function (badge, j) {
      var ri = lerp(0.62, 0.26, j / 3.0);
      var ang = 0.35 + j * 0.12;
      var bx = winW / 2.0 + ri * Math.cos(ang) * sm.z * winH;
      var by = winH / 2.0 - ri * Math.sin(ang) * Math.max(Math.sin(sm.e), 0.04) * sm.z * winH;
      badge.style.transform = "translate(" + bx.toFixed(1) + "px, " + by.toFixed(1) + "px)";

      var op = sm.h > 0.15 ? (sm.h * (1.0 - Math.min(1.0, Math.abs(sm.s - j))) * 0.6 + sm.h * 0.4) : 0.0;
      badge.style.opacity = op.toFixed(2);
    });

    // WebGL Draw (Skip when canvas is fully black)
    if (gl && webglProgram) {
      if (sm.a < 0.004) {
        if (!blank) {
          gl.clearColor(0.0, 0.0, 0.0, 1.0);
          gl.clear(gl.COLOR_BUFFER_BIT);
          blank = 1;
        }
      } else {
        blank = 0;
        gl.useProgram(webglProgram);
        gl.uniform2f(uniforms.R, canvas.width, canvas.height);
        gl.uniform1f(uniforms.T, motionOK ? timestamp / 1000.0 : 2.0);
        gl.uniform1f(uniforms.E, sm.e);
        gl.uniform1f(uniforms.Z, sm.z);
        gl.uniform1f(uniforms.A, sm.a);
        gl.uniform1f(uniforms.TA, sm.ta);
        gl.uniform1f(uniforms.H, sm.h);
        gl.uniform1f(uniforms.S, sm.s);

        if (textTexture) {
          gl.activeTexture(gl.TEXTURE0);
          gl.bindTexture(gl.TEXTURE_2D, textTexture);
          gl.uniform1i(gl.getUniformLocation(webglProgram, "tx"), 0);
        }

        gl.drawArrays(gl.TRIANGLES, 0, 3);
      }
    }

    updateWordReveal();
    updateChapterNav();

    requestAnimationFrame(frame);
  }

  // ==========================================================================
  // 8. TABS (Capabilities Comparison)
  // ==========================================================================
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
        });
      });
    });
  }
  document.querySelectorAll('[role="tablist"]').forEach(function (tl) {
    if (tl.querySelector(".tab-btn[data-tab]")) initTabs(tl);
  });

  // ==========================================================================
  // 9. TOOLS CHART WITH SCRUBBER & LIVE TOOLTIP
  // ==========================================================================
  var chartSvg = document.getElementById("tools-chart-svg");
  var chartTip = document.getElementById("chart-tooltip");
  var chartCursor = document.getElementById("chart-cursor");
  var chartScrubber = document.getElementById("chart-scrubber-line");
  var chartActiveCat = document.getElementById("chart-active-cat");
  var chartActiveTools = document.getElementById("chart-active-tools");
  var chartActiveTotal = document.getElementById("chart-active-total");

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
    function updateScrubber(ev) {
      var rect = chartSvg.getBoundingClientRect();
      var clientX = ev.touches ? ev.touches[0].clientX : ev.clientX;
      var svgX = ((clientX - rect.left) / rect.width) * 720;
      var nearest = chartData[0];
      chartData.forEach(function (d) {
        if (Math.abs(d.x - svgX) < Math.abs(nearest.x - svgX)) nearest = d;
      });

      chartCursor.setAttribute("cx", String(nearest.x));
      chartCursor.setAttribute("cy", String(chartY(nearest.tools)));
      chartCursor.setAttribute("opacity", "1");

      if (chartScrubber) {
        chartScrubber.setAttribute("x1", String(nearest.x));
        chartScrubber.setAttribute("x2", String(nearest.x));
        chartScrubber.setAttribute("opacity", "0.75");
      }

      if (chartActiveCat) chartActiveCat.textContent = nearest.label;
      if (chartActiveTools) chartActiveTools.textContent = nearest.tools + " tools";
      if (chartActiveTotal) chartActiveTotal.textContent = nearest.total + " / 26";

      chartTip.hidden = false;
      chartTip.textContent = nearest.label + ": " + nearest.tools + " tools · running total " + nearest.total;
      chartTip.style.left = ((nearest.x / 720) * 100) + "%";
      chartTip.style.top = ((chartY(nearest.tools) / 340) * 100) + "%";
    }

    chartSvg.addEventListener("pointermove", updateScrubber);
    chartSvg.addEventListener("touchmove", updateScrubber, { passive: true });
    chartSvg.addEventListener("pointerleave", function () {
      chartCursor.setAttribute("opacity", "0");
      if (chartScrubber) chartScrubber.setAttribute("opacity", "0");
      chartTip.hidden = true;
    });
  }

  // ==========================================================================
  // 10. DEVELOPERS: CODE TABS, TYPING & CLIPBOARD
  // ==========================================================================
  var codeSamples = {
    curl: "curl https://jarvis-kumar-shaurya.vercel.app/api/health\n\n# {\"status\": \"ok\", ...}\n# No key needed — the health check is public.",
    python: "import httpx\n\nresp = httpx.get(\"https://jarvis-kumar-shaurya.vercel.app/api/health\", timeout=5)\nprint(resp.json())  # {\"status\": \"ok\", ...}",
    typescript: "const resp = await fetch(\"https://jarvis-kumar-shaurya.vercel.app/api/health\");\nconst health = await resp.json();\nconsole.log(health); // { status: \"ok\", ... }"
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
      if (copyNote) copyNote.textContent = "Health check against the cloud backend. No key needed for /api/health.";
      if (copyBtn) copyBtn.textContent = "Copy code";
    });
  });
  if (codeText) typeCode("curl");

  if (copyBtn) {
    copyBtn.addEventListener("click", function () {
      var text = codeSamples[activeCode];
      function done(ok) {
        copyBtn.textContent = ok ? "Copied ✓" : "Copy failed — select code manually";
        if (copyNote) copyNote.textContent = ok ? "Copied to your clipboard." : "Clipboard access was blocked; copy code manually.";
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

  // ==========================================================================
  // 11. DEVELOPERS: STREAMING-LOG PROTOCOL TRACE SIMULATION
  // ==========================================================================
  var streamPanel = document.getElementById("streaming-log-panel");
  var streamCode = document.getElementById("stream-code");
  var streamReplayBtn = document.getElementById("stream-replay-btn");
  var streamLines = [
    "> GET /api/health HTTP/1.1",
    "< 200 OK {\"status\": \"ok\", \"service\": \"jarvis-cloud\", \"tools\": 26, \"tests\": 181}",
    "> POST /api/chat {\"message\": \"Check device status and read latest note\"}",
    "< 200 OK [step 01 · understand] intent=\"status_check\" target=\"laptop\" permitted=true",
    "< 200 OK [step 02 · choose] selected_tool=\"get_device_status\" confirmation_required=false",
    "< 200 OK [step 03 · act] tool=\"get_device_status\" executed=true payload={\"battery\": \"92%\"}",
    "< 200 OK [step 04 · report] result=\"Laptop is online at 92% battery; audit log entry #284 written.\""
  ];
  var streamPlayed = false;
  var streamInterval = null;

  function runStreamingTrace() {
    if (!streamCode) return;
    if (streamInterval) clearInterval(streamInterval);
    streamCode.textContent = "";
    var lineIdx = 0;

    if (prefersReducedMotion) {
      streamCode.textContent = streamLines.join("\n");
      return;
    }

    streamInterval = setInterval(function () {
      if (lineIdx < streamLines.length) {
        streamCode.textContent += (lineIdx > 0 ? "\n" : "") + streamLines[lineIdx];
        lineIdx++;
      } else {
        clearInterval(streamInterval);
        streamInterval = null;
      }
    }, 280);
  }

  if (streamPanel && "IntersectionObserver" in window) {
    var streamObs = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting && !streamPlayed) {
          streamPlayed = true;
          runStreamingTrace();
          streamObs.unobserve(entry.target);
        }
      });
    }, { threshold: 0.2 });
    streamObs.observe(streamPanel);
  }

  if (streamReplayBtn) {
    streamReplayBtn.addEventListener("click", function () {
      runStreamingTrace();
    });
  }

  // ==========================================================================
  // 12. HONEST BACKEND STATUS PROBE
  // ==========================================================================
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
          setStatus("ok", "Cloud backend is up — sign in to start.");
        } else {
          setStatus("off", "Cloud backend not reachable right now — try again in a moment.");
        }
      })
      .catch(function () {
        clearTimeout(timer);
        setStatus("off", "Cloud backend not reachable right now — try again in a moment.");
      });
  } catch (e) {
    setStatus("off", "Backend status unavailable — try again in a moment.");
  }

  // ==========================================================================
  // 13. ACCESS: SPOKEN-REPLY PREVIEW TOGGLE
  // ==========================================================================
  var spokenToggle = document.getElementById("spoken-toggle");
  var spokenPreview = document.getElementById("spoken-preview");
  if (spokenToggle && spokenPreview) {
    spokenToggle.addEventListener("click", function () {
      var on = spokenToggle.getAttribute("aria-checked") !== "true";
      spokenToggle.setAttribute("aria-checked", on ? "true" : "false");
      spokenPreview.hidden = !on;
    });
  }

  // ==========================================================================
  // 14. FINAL CTA PREVIEW FORM
  // ==========================================================================
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

  // ==========================================================================
  // 15. SCROLL ENTRY REVEALS (Subtle blur-plus-offset with stagger)
  // ==========================================================================
  function initReveals() {
    var reveals = document.querySelectorAll(".reveal");
    if (!reveals.length) return;

    if (prefersReducedMotion || !("IntersectionObserver" in window)) {
      reveals.forEach(function (el) { el.classList.add("is-visible"); });
      return;
    }

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    }, {
      rootMargin: "0px 0px -40px 0px",
      threshold: 0.08
    });

    reveals.forEach(function (el) {
      observer.observe(el);
    });
  }

  // ==========================================================================
  // INITIALIZE & BOOTSTRAP
  // ==========================================================================
  initReveals();
  initWebGL();
  resizeWebGL();
  window.addEventListener("resize", function () {
    resizeWebGL();
    renderTextTexture();
  }, { passive: true });

  requestAnimationFrame(frame);

  // ---- Smooth Scrolling (Lenis) with native fallback ----
  window.addEventListener("load", function () {
    if (typeof Lenis !== "undefined" && motionOK) {
      var lenis = new Lenis({
        duration: 1.2,
        easing: function (t) { return Math.min(1, 1.001 - Math.pow(2, -10 * t)); }
      });
      function raf(time) {
        lenis.raf(time);
        requestAnimationFrame(raf);
      }
      requestAnimationFrame(raf);
    }
  });

})();
