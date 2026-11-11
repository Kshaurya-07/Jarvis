/* ==========================================================================
   Jarvis — Visual Layer & WebGL Engine
   Raw WebGL Gravitational Lensing Black Hole + Interactive Scroll Experience
   ========================================================================== */

(function () {
  "use strict";
  document.documentElement.classList.add("js");

  var prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var finePointer = window.matchMedia("(pointer: fine)").matches;
  var motionOK = !prefersReducedMotion;
  document.documentElement.classList.toggle("has-pointer", finePointer && motionOK);

  function clamp(v, a, b) { return Math.min(Math.max(v, a), b); }

  // ==========================================================================
  // 1. RAW WEBGL GRAVITATIONAL LENSING ENGINE
  // ==========================================================================
  var canvas = document.getElementById("bg-canvas");
  var gl = null;
  if (canvas) {
    try {
      gl = canvas.getContext("webgl", { alpha: false, depth: false, antialias: false, powerPreference: "high-performance" }) ||
           canvas.getContext("experimental-webgl");
    } catch (e) {
      gl = null;
    }
  }

  // Fallback if WebGL unavailable
  if (!gl && canvas) {
    canvas.style.display = "none";
  }

  var webglProgram = null;
  var textTexture = null;
  var uniforms = {};
  var canvasWidth = 0, canvasHeight = 0;
  var heroDistance = 26.0;
  var holdZoom = 0.0;
  var isHolding = false;
  var currentMode = 0; // 0 = Hero, 1 = How it works, 2 = Black
  var currentInclination = 1.48; // ~84.8 deg
  var blackFade = 0.0;
  var activeRingIndex = 0.0;
  var howScrollProgress = 0.0;
  var pointerX = 0.0, pointerY = 0.0;

  var VS_SOURCE = [
    "attribute vec2 a_pos;",
    "void main() {",
    "  gl_Position = vec4(a_pos, 0.0, 1.0);",
    "}"
  ].join("\n");

  var FS_SOURCE = [
    "precision highp float;",
    "uniform vec2 u_res;",
    "uniform float u_time;",
    "uniform float u_dist;",
    "uniform float u_inc;",
    "uniform float u_hold;",
    "uniform float u_fade;",
    "uniform int u_mode;",
    "uniform float u_active_ring;",
    "uniform sampler2D u_text_tex;",
    "uniform vec2 u_mouse;",

    "float hash(vec2 p) {",
    "  p = fract(p * vec2(123.34, 456.21));",
    "  p += dot(p, p + 45.32);",
    "  return fract(p.x * p.y);",
    "}",

    "void main() {",
    "  if (u_fade >= 0.99) {",
    "    gl_FragColor = vec4(0.0, 0.0, 0.0, 1.0);",
    "    return;",
    "  }",

    "  vec2 uv = (gl_FragCoord.xy - 0.5 * u_res) / min(u_res.x, u_res.y);",
    "  float effDist = max(u_dist - u_hold * 14.0, 2.6);",
    "  float effInc = u_inc;",

    "  // Camera setup",
    "  vec3 ro = vec3(0.0, effDist * sin(effInc), effDist * cos(effInc));",
    "  ro.x += u_mouse.x * 0.4;",
    "  ro.y += u_mouse.y * 0.4;",
    "  vec3 ta = vec3(0.0, 0.0, 0.0);",
    "  vec3 ww = normalize(ta - ro);",
    "  vec3 uu = normalize(cross(ww, vec3(0.0, 1.0, 0.0)));",
    "  vec3 vv = cross(uu, ww);",
    "  vec3 rd = normalize(uv.x * uu + uv.y * vv + 1.4 * ww);",

    "  // Gravitational Raymarching",
    "  vec3 p = ro;",
    "  vec3 v = rd;",
    "  vec3 col = vec3(0.0);",
    "  float rs = 1.0;",
    "  float dt = 0.26;",
    "  bool hitHole = false;",
    "  float diskAcc = 0.0;",
    "  vec3 diskCol = vec3(0.0);",

    "  // Cream/white accretion disk palette",
    "  vec3 cCreamCore = vec3(1.0, 0.98, 0.94);",
    "  vec3 cCreamBody = vec3(0.92, 0.89, 0.84);",
    "  vec3 cCreamDim  = vec3(0.68, 0.65, 0.60);",
    "  vec3 cElectricBlue = vec3(0.30, 0.42, 1.0);",

    "  for (int i = 0; i < 44; i++) {",
    "    float r = length(p);",
    "    if (r < rs * 1.05) {",
    "      hitHole = true;",
    "      break;",
    "    }",
    "    if (r > 34.0) break;",

    "    // Gravitational deflection force: a = -1.5 * rs / r^5 * p",
    "    vec3 accel = -1.5 * rs * p / (r * r * r * r * r);",
    "    v += accel * dt * 1.8;",
    "    vec3 pNext = p + v * dt;",

    "    // Equator intersection (y crosses 0)",
    "    if ((p.y > 0.0 && pNext.y <= 0.0) || (p.y < 0.0 && pNext.y >= 0.0)) {",
    "      float tCross = -p.y / (pNext.y - p.y);",
    "      vec3 pCross = mix(p, pNext, tCross);",
    "      float rDisk = length(pCross.xz);",

    "      // Mode 0: Hero Black Hole Accretion Disk",
    "      if (u_mode == 0) {",
    "        if (rDisk >= 1.6 * rs && rDisk <= 8.5 * rs) {",
    "          float dNorm = (rDisk - 1.6 * rs) / (6.9 * rs);",
    "          float ang = atan(pCross.z, pCross.x);",
    "          float swirl = sin(ang * 4.0 + 2.8 * log(rDisk) - u_time * 1.8);",
    "          float density = smoothstep(0.0, 0.25, dNorm) * (1.0 - smoothstep(0.6, 1.0, dNorm));",
    "          density *= (0.75 + 0.25 * swirl);",

    "          // Relativistic Doppler beaming (left side approaches, brighter cream)",
    "          float dop = 1.0 - 0.45 * (pCross.x / rDisk);",
    "          vec3 localC = mix(cCreamCore, cCreamBody, dNorm) * dop * density * 1.4;",
    "          diskCol += localC * (1.0 - diskAcc);",
    "          diskAcc += density * 0.42;",
    "        }",
    "      }",
    "      // Mode 1: How it works (4 Electric Blue Orbit Rings)",
    "      else if (u_mode == 1) {",
    "        float ringR[4];",
    "        ringR[0] = 2.4;",
    "        ringR[1] = 4.2;",
    "        ringR[2] = 6.0;",
    "        ringR[3] = 7.8;",

    "        for (int k = 0; k < 4; k++) {",
    "          float distRing = abs(rDisk - ringR[k]);",
    "          float ringW = 0.08;",
    "          float ringGlow = exp(-distRing * 18.0);",
    "          bool isActive = (abs(float(k) - u_active_ring) < 0.5);",
    "          if (isActive) {",
    "            // Orbiting beacon dot",
    "            float dotAng = u_time * 2.2;",
    "            vec2 dotPos = vec2(cos(dotAng), sin(dotAng)) * ringR[k];",
    "            float distDot = length(pCross.xz - dotPos);",
    "            float dotGlow = exp(-distDot * 12.0) * 3.5;",
    "            diskCol += (cElectricBlue * ringGlow * 2.5 + vec3(1.0) * dotGlow);",
    "            diskAcc += ringGlow * 0.8 + dotGlow * 0.5;",
    "          } else {",
    "            diskCol += cElectricBlue * ringGlow * 0.55;",
    "            diskAcc += ringGlow * 0.25;",
    "          }",
    "        }",
    "      }",
    "    }",

    "    p = pNext;",
    "  }",

    "  // Photon Ring (thin high-energy arc around horizon)",
    "  float impactParam = length(uv);",
    "  float photonArc = exp(-abs(impactParam - (1.52 / effDist * 14.0)) * 40.0) * (1.0 - float(hitHole));",
    "  col += cCreamCore * photonArc * 0.85;",

    "  // Add Accretion Disk / Orbit contribution",
    "  col += diskCol;",

    "  // Background Lensed Sky & Jarvis Text (only if ray escaped black hole)",
    "  if (!hitHole) {",
    "    // Sample background text billboard behind black hole",
    "    vec3 escapeDir = normalize(v);",
    "    if (escapeDir.z < -0.15) {",
    "      float tPlane = (-18.0 - ro.z) / escapeDir.z;",
    "      if (tPlane > 0.0) {",
    "        vec3 hitPlane = ro + escapeDir * tPlane;",
    "        vec2 textUV = hitPlane.xy / vec2(22.0, 11.0) + vec2(0.5, 0.5);",
    "        if (textUV.x >= 0.0 && textUV.x <= 1.0 && textUV.y >= 0.0 && textUV.y <= 1.0) {",
    "          vec4 txtSample = texture2D(u_text_tex, textUV);",
    "          // Gravitationally warped off-white wordmark",
    "          col += txtSample.rgb * vec3(0.95, 0.93, 0.89) * txtSample.a * 0.85;",
    "        }",
    "      }",
    "    }",

    "    // Sparse twinkling background stars",
    "    vec2 starUV = floor(escapeDir.xy * 240.0);",
    "    float starH = hash(starUV);",
    "    if (starH > 0.988) {",
    "      float twinkle = sin(u_time * 2.0 + starH * 30.0) * 0.5 + 0.5;",
    "      col += vec3(0.9, 0.9, 1.0) * twinkle * (starH - 0.988) * 45.0;",
    "    }",
    "  }",

    "  // Fade out when scrolling",
    "  col = mix(col, vec3(0.0), u_fade);",

    "  gl_FragColor = vec4(col, 1.0);",
    "}"
  ].join("\n");

  function createShader(glCtx, type, source) {
    var sh = glCtx.createShader(type);
    glCtx.shaderSource(sh, source);
    glCtx.compileShader(sh);
    if (!glCtx.getShaderParameter(sh, glCtx.COMPILE_STATUS)) {
      console.warn("WebGL Shader error:", glCtx.getShaderInfoLog(sh));
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
      console.warn("WebGL Link error:", gl.getProgramInfoLog(webglProgram));
      return;
    }

    gl.useProgram(webglProgram);

    // Quad geometry
    var posBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, posBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([
      -1, -1,
       1, -1,
      -1,  1,
      -1,  1,
       1, -1,
       1,  1
    ]), gl.STATIC_DRAW);

    var aPos = gl.getAttribLocation(webglProgram, "a_pos");
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

    // Uniforms
    uniforms.res = gl.getUniformLocation(webglProgram, "u_res");
    uniforms.time = gl.getUniformLocation(webglProgram, "u_time");
    uniforms.dist = gl.getUniformLocation(webglProgram, "u_dist");
    uniforms.inc = gl.getUniformLocation(webglProgram, "u_inc");
    uniforms.hold = gl.getUniformLocation(webglProgram, "u_hold");
    uniforms.fade = gl.getUniformLocation(webglProgram, "u_fade");
    uniforms.mode = gl.getUniformLocation(webglProgram, "u_mode");
    uniforms.active_ring = gl.getUniformLocation(webglProgram, "u_active_ring");
    uniforms.text_tex = gl.getUniformLocation(webglProgram, "u_text_tex");
    uniforms.mouse = gl.getUniformLocation(webglProgram, "u_mouse");

    createTextTexture();
  }

  // Generate 2D Texture containing "Jarvis" wordmark for gravitational lensing
  function createTextTexture() {
    if (!gl) return;
    var textCanvas = document.createElement("canvas");
    textCanvas.width = 1024;
    textCanvas.height = 512;
    var ctx = textCanvas.getContext("2d");
    if (!ctx) return;

    ctx.clearRect(0, 0, textCanvas.width, textCanvas.height);
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 220px 'Inter Tight', sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.letterSpacing = "-0.05em";
    ctx.fillText("Jarvis", textCanvas.width / 2, textCanvas.height / 2);

    textTexture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, textTexture);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, textCanvas);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  }

  function resizeWebGL() {
    if (!canvas || !gl) return;
    var dpr = clamp((window.devicePixelRatio || 1) * 0.8, 0.75, 1.5);
    var w = Math.round(window.innerWidth * dpr);
    var h = Math.round(window.innerHeight * dpr);
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
      canvasWidth = w;
      canvasHeight = h;
      gl.viewport(0, 0, w, h);
    }
  }

  // ==========================================================================
  // 2. HUD & INTERACTIVE SCROLL PROJECTIONS
  // ==========================================================================
  var hudDist = document.getElementById("hud-dist");
  var hudInc = document.getElementById("hud-inc");
  var orbitBadge = document.getElementById("orbit-projected-label");
  var heroSection = document.getElementById("companion");
  var howSection = document.getElementById("how");
  var howSteps = Array.prototype.slice.call(document.querySelectorAll(".how-step-card"));
  var railFill = document.getElementById("how-rail-fill");
  var railSteps = Array.prototype.slice.call(document.querySelectorAll(".how-rail-step"));

  var stepLabels = [
    "01 Understand · r2.4",
    "02 Choose · r4.2",
    "03 Act · r6.0",
    "04 Report · r7.8"
  ];

  // Mouse / Touch hold to deepen
  window.addEventListener("mousedown", function (e) {
    if (e.target.closest("a, button, input, textarea, [role='button']")) return;
    isHolding = true;
  });
  window.addEventListener("mouseup", function () { isHolding = false; });
  window.addEventListener("touchstart", function (e) {
    if (e.target.closest("a, button, input, textarea, [role='button']")) return;
    isHolding = true;
  }, { passive: true });
  window.addEventListener("touchend", function () { isHolding = false; });

  // Pointer position for subtle parallax
  window.addEventListener("mousemove", function (e) {
    pointerX = (e.clientX / window.innerWidth) * 2 - 1;
    pointerY = (e.clientY / window.innerHeight) * 2 - 1;
  }, { passive: true });

  // ==========================================================================
  // 3. WORD-BY-WORD SCROLL REVEAL (Why Jarvis Exists)
  // ==========================================================================
  var statementEl = document.querySelector(".statement-text");
  var statementWords = [];
  if (statementEl) {
    var rawText = statementEl.textContent.trim();
    var words = rawText.split(/\s+/);
    statementEl.innerHTML = words.map(function (w) {
      return '<span class="word">' + w + '</span>';
    }).join(" ");
    statementWords = Array.prototype.slice.call(statementEl.querySelectorAll(".word"));
  }

  function updateWordReveal() {
    if (!statementEl || !statementWords.length) return;
    var rect = statementEl.getBoundingClientRect();
    var viewH = window.innerHeight;
    var start = viewH * 0.85;
    var end = viewH * 0.25;
    var progress = clamp((start - rect.top) / (start - end), 0, 1);

    var revealCount = Math.floor(progress * statementWords.length);
    statementWords.forEach(function (word, idx) {
      word.classList.toggle("is-revealed", idx <= revealCount || prefersReducedMotion);
    });
  }

  // ==========================================================================
  // 4. CHAPTER NAVIGATION SCROLL-SPY
  // ==========================================================================
  var chapterLinks = Array.prototype.slice.call(document.querySelectorAll(".chapter-link"));
  var chapters = [
    { id: "companion", link: document.querySelector('.chapter-link[data-chapter="companion"]') },
    { id: "why", link: document.querySelector('.chapter-link[data-chapter="why"]') },
    { id: "how", link: document.querySelector('.chapter-link[data-chapter="how"]') },
    { id: "privacy", link: document.querySelector('.chapter-link[data-chapter="privacy"]') },
    { id: "access", link: document.querySelector('.chapter-link[data-chapter="access"]') }
  ];

  function updateChapterNav() {
    var scrollY = window.scrollY || window.pageYOffset;
    var currentActive = null;
    for (var i = 0; i < chapters.length; i++) {
      var el = document.getElementById(chapters[i].id);
      if (el) {
        var top = el.offsetTop - 180;
        if (scrollY >= top) {
          currentActive = chapters[i].link;
        }
      }
    }
    if (!currentActive && chapters.length) currentActive = chapters[0].link;
    chapterLinks.forEach(function (link) {
      link.classList.toggle("is-active", link === currentActive);
    });
  }

  // ==========================================================================
  // 5. RENDER LOOP
  // ==========================================================================
  var startTime = performance.now();

  function render(now) {
    requestAnimationFrame(render);

    var timeSec = motionOK ? (now - startTime) * 0.001 : 0.0;
    var scrollY = window.scrollY || window.pageYOffset;
    var winH = window.innerHeight;

    // Smooth hold zoom
    if (isHolding && motionOK) {
      holdZoom += (1.0 - holdZoom) * 0.06;
    } else {
      holdZoom += (0.0 - holdZoom) * 0.08;
    }

    // Hero Section Calculations
    var heroRect = heroSection ? heroSection.getBoundingClientRect() : { top: 0, height: winH };
    var heroProgress = clamp(-heroRect.top / winH, 0, 1);

    // How Section Calculations (400vh scroll container)
    var howRect = howSection ? howSection.getBoundingClientRect() : { top: 99999, height: 1 };
    var howTotalScroll = howRect.height - winH;
    howScrollProgress = clamp(-howRect.top / (howTotalScroll > 0 ? howTotalScroll : 1), 0, 1);

    // State machine for 3D modes
    if (howRect.top <= 0 && howRect.bottom >= winH) {
      // In 4-step How It Works 3D Journey
      currentMode = 1;
      blackFade = 0.0;
      // Tilt from face-on (0.2 rad ~11 deg) towards edge-on (1.48 rad ~84.8 deg)
      currentInclination = 0.35 + howScrollProgress * 1.1;
      heroDistance = 16.0;

      // Active step (0, 1, 2, 3)
      var stepIdx = Math.min(Math.floor(howScrollProgress * 4), 3);
      activeRingIndex = stepIdx;

      // Update text swaps
      howSteps.forEach(function (card, idx) {
        card.classList.toggle("is-active", idx === stepIdx);
      });

      // Update rail
      if (railFill) railFill.style.height = (howScrollProgress * 100) + "%";
      railSteps.forEach(function (stepEl, idx) {
        stepEl.classList.toggle("is-active", idx === stepIdx);
      });

      // Update Screen-Projected DOM Badge
      if (orbitBadge) {
        orbitBadge.style.opacity = "1";
        orbitBadge.textContent = stepLabels[stepIdx];
        // Calculate projected screen position from 3D ring
        var ringRadii = [2.4, 4.2, 6.0, 7.8];
        var curR = ringRadii[stepIdx];
        var orbAngle = timeSec * 2.2;
        var orbX = Math.cos(orbAngle) * curR;
        var orbZ = Math.sin(orbAngle) * curR;

        // Project 3D (orbX, 0, orbZ) to 2D screen coordinates
        var camY = heroDistance * Math.sin(currentInclination);
        var camZ = heroDistance * Math.cos(currentInclination);
        var screenX = (window.innerWidth / 2) + (orbX * 42);
        var screenY = (window.innerHeight / 2) + (camY * 12) + (orbZ * Math.cos(currentInclination) * 32);
        orbitBadge.style.left = screenX + "px";
        orbitBadge.style.top = screenY + "px";
      }
    } else if (heroRect.bottom > 0) {
      // In Hero Section
      currentMode = 0;
      currentInclination = 1.48; // Edge-on ~84.8 deg
      heroDistance = Math.max(26.0 - heroProgress * 18.0, 4.0);
      blackFade = heroProgress * 1.2; // Zoom in and fade to black when leaving hero

      if (orbitBadge) orbitBadge.style.opacity = "0";
    } else {
      // Other standard content sections — fade out canvas for fast performance
      currentMode = 2;
      blackFade = 1.0;
      if (orbitBadge) orbitBadge.style.opacity = "0";
    }

    // Update HUD metrics
    if (hudDist) {
      var displayDist = Math.max(26.0 - heroProgress * 21.0 - holdZoom * 12.0, 1.2).toFixed(1);
      hudDist.textContent = displayDist;
    }
    if (hudInc) {
      var displayInc = ((currentInclination * 180) / Math.PI).toFixed(1);
      hudInc.textContent = displayInc;
    }

    // Render WebGL
    if (gl && webglProgram && blackFade < 0.99) {
      gl.useProgram(webglProgram);
      gl.uniform2f(uniforms.res, canvasWidth, canvasHeight);
      gl.uniform1f(uniforms.time, timeSec);
      gl.uniform1f(uniforms.dist, heroDistance);
      gl.uniform1f(uniforms.inc, currentInclination);
      gl.uniform1f(uniforms.hold, holdZoom);
      gl.uniform1f(uniforms.fade, clamp(blackFade, 0.0, 1.0));
      gl.uniform1i(uniforms.mode, currentMode);
      gl.uniform1f(uniforms.active_ring, activeRingIndex);
      gl.uniform2f(uniforms.mouse, pointerX, pointerY);

      if (textTexture) {
        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, textTexture);
        gl.uniform1i(uniforms.text_tex, 0);
      }

      gl.drawArrays(gl.TRIANGLES, 0, 6);
    }

    updateWordReveal();
    updateChapterNav();
  }

  // ==========================================================================
  // 6. CUSTOM DIFFERENCE CURSOR (Lerp Smoothed)
  // ==========================================================================
  var cursorDot = document.getElementById("cursor-dot");
  var cursorX = -100, cursorY = -100;
  var targetCursorX = -100, targetCursorY = -100;

  if (finePointer && motionOK && cursorDot) {
    window.addEventListener("pointermove", function (e) {
      targetCursorX = e.clientX;
      targetCursorY = e.clientY;
    }, { passive: true });

    document.addEventListener("pointerover", function (e) {
      var isInteractive = e.target && e.target.closest &&
        e.target.closest("a, button, input, .tab-btn, [role='switch'], .card, .chart-svg-wrap");
      cursorDot.classList.toggle("is-active", !!isInteractive);
    });

    function updateCursor() {
      cursorX += (targetCursorX - cursorX) * 0.22;
      cursorY += (targetCursorY - cursorY) * 0.22;
      cursorDot.style.transform = "translate3d(" + (cursorX - 17).toFixed(1) + "px," + (cursorY - 17).toFixed(1) + "px, 0)";
      requestAnimationFrame(updateCursor);
    }
    requestAnimationFrame(updateCursor);
  }

  // ==========================================================================
  // 7. HONEST BACKEND STATUS PROBE
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
  // 9. TOOLS CHART WITH SCRUBBER & TOOLTIP
  // ==========================================================================
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
  var chartScrubber = document.getElementById("chart-scrubber-line");
  var chartActiveCat = document.getElementById("chart-active-cat");
  var chartActiveTools = document.getElementById("chart-active-tools");
  var chartActiveTotal = document.getElementById("chart-active-total");

  if (chartSvg && chartTip && chartCursor) {
    function updateScrubber(ev) {
      var rect = chartSvg.getBoundingClientRect();
      var clientX = ev.touches ? ev.touches[0].clientX : ev.clientX;
      var svgX = ((clientX - rect.left) / rect.width) * 720;
      var nearest = chartData[0];
      chartData.forEach(function (d) {
        if (Math.abs(d.x - svgX) < Math.abs(nearest.x - svgX)) nearest = d;
      });

      // Update dot cursor
      chartCursor.setAttribute("cx", String(nearest.x));
      chartCursor.setAttribute("cy", String(chartY(nearest.tools)));
      chartCursor.setAttribute("opacity", "1");

      // Update vertical scrubber line
      if (chartScrubber) {
        chartScrubber.setAttribute("x1", String(nearest.x));
        chartScrubber.setAttribute("x2", String(nearest.x));
        chartScrubber.setAttribute("opacity", "0.75");
      }

      // Update live numbers beside chart
      if (chartActiveCat) chartActiveCat.textContent = nearest.label;
      if (chartActiveTools) chartActiveTools.textContent = nearest.tools + " tools";
      if (chartActiveTotal) chartActiveTotal.textContent = nearest.total + " / 26";

      // Update tooltip
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
  // 11. DEVELOPERS: CODE TABS, TYPING & CLIPBOARD
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
  // INITIALIZE
  // ==========================================================================
  
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
      rootMargin: "0px 0px -50px 0px",
      threshold: 0.08
    });

    reveals.forEach(function (el) {
      observer.observe(el);
    });
  }

  initReveals();
  initWebGL();
  resizeWebGL();
  window.addEventListener("resize", function () {
    resizeWebGL();
    createTextTexture();
  }, { passive: true });

  requestAnimationFrame(render);


  // ---- Smooth Scrolling (Lenis) with native fallback ----
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

})();