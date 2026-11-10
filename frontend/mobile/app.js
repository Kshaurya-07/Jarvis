// Jarvis Mobile Companion Application Logic (Phase 7)
document.addEventListener("DOMContentLoaded", () => {
  // Elements
  const connectionPill = document.getElementById("connection-pill");
  const connectionText = document.getElementById("connection-text");
  const networkNotice = document.getElementById("network-notice");
  const closeNoticeBtn = document.getElementById("close-notice-btn");
  const activeOpBar = document.getElementById("active-operation-bar");
  const stopBtn = document.getElementById("stop-btn");
  const recordingBanner = document.getElementById("recording-banner");
  const cancelVoiceBtn = document.getElementById("cancel-voice-btn");
  const chatStream = document.getElementById("chat-stream");
  const commandInput = document.getElementById("command-input");
  const sendBtn = document.getElementById("send-btn");
  const voiceBtn = document.getElementById("voice-btn");
  const quickChips = document.querySelectorAll(".chip");

  // Drawers & Settings
  const navActionsBtn = document.getElementById("nav-actions-btn");
  const closeActionsBtn = document.getElementById("close-actions-btn");
  const refreshActionsBtn = document.getElementById("refresh-actions-btn");
  const actionsDrawer = document.getElementById("actions-drawer");
  const actionsList = document.getElementById("actions-list");

  const navSettingsBtn = document.getElementById("nav-settings-btn");
  const closeSettingsBtn = document.getElementById("close-settings-btn");
  const settingsDrawer = document.getElementById("settings-drawer");
  const drawerBackdrop = document.getElementById("drawer-backdrop");


  const optInHistoryToggle = document.getElementById("opt-in-history-toggle");
  const clearHistoryBtn = document.getElementById("clear-history-btn");
  const ttsToggle = document.getElementById("tts-toggle");

  // Metadata elements
  const sysVersion = document.getElementById("sys-version");
  const sysPlatform = document.getElementById("sys-platform");
  const sysGemini = document.getElementById("sys-gemini");
  const sysGoogle = document.getElementById("sys-google");
  const sysToolsCount = document.getElementById("sys-tools-count");

  // Phase 11 Remote Pairing Elements
  const noticePairBtn = document.getElementById("notice-pair-btn");
  const remoteGatewayUrlInput = document.getElementById("remote-gateway-url");
  const pairingCodeInput = document.getElementById("pairing-code-input");
  const pairSubmitBtn = document.getElementById("pair-submit-btn");
  const pairControlsContainer = document.getElementById("pair-controls-container");
  const pairedStatusContainer = document.getElementById("paired-status-container");
  const disconnectBtn = document.getElementById("disconnect-btn");
  const localPairHelper = document.getElementById("local-pair-helper");
  const generatePairingCodeBtn = document.getElementById("generate-pairing-code-btn");
  const generatedCodeDisplay = document.getElementById("generated-code-display");
  const displayedCode = document.getElementById("displayed-code");

  // State
  let activeAbortController = null;
  let recognitionInstance = null;
  let isRecording = false;

  // Phase 11: In-Memory Session Token ONLY (Never stored in localStorage, cookies, or logs!)
  let remoteSessionToken = null;
  const GATEWAY_URL_KEY = "jarvis_tailscale_gateway_url";
  const API_BASE_URL_KEY = "jarvis_api_base_url";

  // Cloud-first: the backend is usually same-origin (Vercel hosts the app
  // and the backend together), so the default base URL is "".
  // window.JARVIS_CONFIG.apiBaseUrl (config.js) or the Settings field below
  // overrides it only when the backend lives somewhere else.
  function configuredApiBaseUrl() {
    const fromConfig = (window.JARVIS_CONFIG && window.JARVIS_CONFIG.apiBaseUrl || "").trim();
    if (fromConfig) return fromConfig.replace(/\/+$/, "");
    const fromSettings = (localStorage.getItem(API_BASE_URL_KEY) || "").trim();
    return fromSettings ? fromSettings.replace(/\/+$/, "") : "";
  }

  // Initialize PWA Service Worker
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("./service-worker.js").catch((err) => {
      console.warn("ServiceWorker registration failed:", err);
    });
  }

  // --- Legacy network verification (local mode / Tailscale pairing) ---
  const isLocalhostHost = (
    window.location.hostname === "localhost" ||
    window.location.hostname === "127.0.0.1" ||
    window.location.hostname === "[::1]"
  );

  function getBaseUrl() {
    const configured = configuredApiBaseUrl();
    if (configured) return configured;
    if (isLocalhostHost) {
      return "";
    }
    const custom = (remoteGatewayUrlInput?.value || localStorage.getItem(GATEWAY_URL_KEY) || "").trim();
    return custom ? custom.replace(/\/+$/, "") : "";
  }

  async function apiFetch(endpoint, options = {}) {
    const baseUrl = getBaseUrl();
    const url = baseUrl ? `${baseUrl}${endpoint}` : endpoint;
    options.headers = options.headers || {};
    if (remoteSessionToken) {
      options.headers["Authorization"] = `Bearer ${remoteSessionToken}`;
      options.headers["X-Session-Token"] = remoteSessionToken;
    }
    return fetch(url, options);
  }

  async function checkHealth() {
    try {
      // NOTE: /api/health, not /health. The backend is a Vercel serverless
      // function that only receives /api/* requests (see vercel.json); a
      // bare /health hits the static site, 404s, and the pill wrongly shows
      // "Offline" even though the backend is up. /api/health works locally
      // and on Vercel.
      const resp = await apiFetch("/api/health", { cache: "no-store" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();

      if (isLocalhostHost) {
        connectionPill.className = "connection-pill online";
        connectionText.textContent = "Online (Local)";
      } else if (remoteSessionToken) {
        connectionPill.className = "connection-pill online";
        connectionText.textContent = "Paired (Tailscale)";
        networkNotice.style.display = "none";
      } else {
        connectionPill.className = "connection-pill checking";
        connectionText.textContent = "Reachable (Unpaired)";
        // NOTE: the sign-in notice is owned by refreshMe() (auth state),
        // not by the health check. Showing it here made every signed-in
        // cloud user see "You're not signed in yet" (live bug, 2026-11-11).
      }

      if (sysVersion) sysVersion.textContent = data.version || "1.0.0";
      if (sysPlatform) sysPlatform.textContent = data.platform || "windows";
      if (sysGemini) sysGemini.textContent = data.gemini_configured ? "Ready" : "No API Key";
      if (sysGoogle) sysGoogle.textContent = data.google_connected ? "Connected" : "Not Connected";
      if (sysToolsCount) sysToolsCount.textContent = (data.active_tools || []).length;
    } catch (e) {
      connectionPill.className = "connection-pill offline";
      connectionText.textContent = "Offline";

      if (!isLocalhostHost && !remoteSessionToken) {
        networkNotice.style.display = "flex";
      }
    }
  }

  // --- Cloud account: Google sign-in + your own Gemini key (BYOK) ---
  const signinBtn = document.getElementById("signin-btn");
  const logoutBtn = document.getElementById("logout-btn");
  const accountSignedOut = document.getElementById("account-signed-out");
  const accountSignedIn = document.getElementById("account-signed-in");
  const accountEmailEl = document.getElementById("account-email");
  const onboardBanner = document.getElementById("onboarding-banner");
  const onboardSigninBtn = document.getElementById("onboard-signin-btn");
  const keyStatusEl = document.getElementById("key-status");
  const keyInput = document.getElementById("gemini-key-input");
  const saveKeyBtn = document.getElementById("save-key-btn");
  const deleteKeyBtn = document.getElementById("delete-key-btn");
  const keyMessageEl = document.getElementById("key-message");
  const apiBaseUrlInput = document.getElementById("api-base-url-input");
  let meState = { authenticated: false, has_key: false };
  let historyLoaded = false;

  function goSignIn() {
    window.location.href = (getBaseUrl() || "") + "/api/auth/login";
  }
  if (signinBtn) signinBtn.addEventListener("click", goSignIn);
  if (onboardSigninBtn) onboardSigninBtn.addEventListener("click", goSignIn);
  if (noticePairBtn) noticePairBtn.addEventListener("click", goSignIn);

  async function refreshMe() {
    try {
      const resp = await apiFetch("/api/auth/me", { cache: "no-store" });
      if (!resp.ok) return;
      meState = await resp.json();
      if (accountSignedOut) accountSignedOut.style.display = meState.authenticated ? "none" : "block";
      if (accountSignedIn) accountSignedIn.style.display = meState.authenticated ? "block" : "none";
      if (accountEmailEl && meState.email) accountEmailEl.textContent = meState.email;
      if (keyStatusEl) {
        keyStatusEl.innerHTML = meState.has_key
          ? "Saved — key ending <strong>" + escapeHtml(meState.key_hint || "") + "</strong>. It is encrypted and never shown again."
          : "No key saved yet — add yours below to start chatting.";
      }
      const step1 = document.getElementById("onboard-step-1");
      const step2 = document.getElementById("onboard-step-2");
      if (step1) step1.classList.toggle("done", !!meState.authenticated);
      if (step2) step2.classList.toggle("done", !!meState.has_key);
      // The sign-in notice belongs to auth state: a signed-in user must
      // never see "You're not signed in yet". Local owners need no sign-in,
      // so it stays hidden on localhost too. (Before this, refreshMe only
      // ever SHOWED the notice when unauthenticated and never hid it.)
      if (networkNotice) networkNotice.style.display = (meState.authenticated || isLocalhostHost) ? "none" : "flex";
      updateWizard();
      if (onboardBanner) {
        // The static banner is only the fallback when the wizard is
        // dismissed; never show both at once.
        onboardBanner.style.display = (meState.authenticated && meState.has_key) || wizardVisible ? "none" : "block";
      }
      if (meState.authenticated && !historyLoaded) {
        historyLoaded = true;
        loadChatHistory();
      }
    } catch (e) {
      /* Offline — the health check already shows the state. */
    }
  }

  async function loadChatHistory() {
    try {
      const resp = await apiFetch("/api/chat/history?limit=30", { cache: "no-store" });
      if (!resp.ok) return;
      const data = await resp.json();
      const messages = Array.isArray(data.messages) ? data.messages : [];
      // Only render history into an empty stream (the welcome card counts as empty).
      const existing = chatStream.querySelectorAll(".message:not(.welcome-card)").length;
      if (existing > 0 || messages.length === 0) return;
      const welcome = chatStream.querySelector(".welcome-card");
      if (welcome) welcome.remove();
      messages.forEach((m) => appendMessage(m.role === "user" ? "user" : "assistant", m.content || ""));
    } catch (e) {
      console.debug("Chat history load failed:", e);
    }
  }

  if (logoutBtn) {
    logoutBtn.addEventListener("click", async () => {
      try { await apiFetch("/api/auth/logout", { method: "POST" }); } catch (_) {}
      historyLoaded = false;
      refreshMe();
      checkHealth();
    });
  }

  // Shared Gemini-key save (Settings button and wizard step 2 both use it).
  async function saveGeminiKey(value) {
    const key = (value || "").trim();
    if (!key) throw new Error("Paste your Gemini key first.");
    const resp = await apiFetch("/api/auth/key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: key }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || ("HTTP " + resp.status));
  }

  // --- Guided setup wizard: one popup step at a time. ---
  const wizardOverlay = document.getElementById("setup-wizard");
  const wizardStep1 = document.getElementById("wizard-step-1");
  const wizardStep2 = document.getElementById("wizard-step-2");
  const wizardStepDone = document.getElementById("wizard-step-done");
  const wizardEyebrowNum = document.getElementById("wizard-eyebrow-num");
  const wizardSigninBtn = document.getElementById("wizard-signin-btn");
  const wizardSaveKeyBtn = document.getElementById("wizard-save-key-btn");
  const wizardKeyInput = document.getElementById("wizard-key-input");
  const wizardKeyMessageEl = document.getElementById("wizard-key-message");
  const wizardOkBtn = document.getElementById("wizard-ok-btn");
  const wizardCloseBtn = document.getElementById("wizard-close-btn");
  const WIZARD_DISMISSED_KEY = "jarvis_setup_dismissed";
  let wizardVisible = false;

  function wizardWantedStep() {
    if (meState.authenticated && meState.has_key) return 0; // done: never show
    if (meState.authenticated) return 2;
    return 1;
  }
  function showWizardStep(n) {
    if (wizardStep1) wizardStep1.style.display = n === 1 ? "block" : "none";
    if (wizardStep2) wizardStep2.style.display = n === 2 ? "block" : "none";
    if (wizardStepDone) wizardStepDone.style.display = n === 3 ? "block" : "none";
    if (wizardEyebrowNum) wizardEyebrowNum.textContent = n === 3 ? "03" : ("0" + n);
  }
  function updateWizard() {
    if (!wizardOverlay) return;
    const step = wizardWantedStep();
    let dismissed = false;
    try { dismissed = localStorage.getItem(WIZARD_DISMISSED_KEY) === "1"; } catch (_) {}
    if (step === 0 || dismissed) {
      wizardVisible = false;
      wizardOverlay.style.display = "none";
      return;
    }
    wizardVisible = true;
    wizardOverlay.style.display = "flex";
    showWizardStep(step);
  }
  function dismissWizard() {
    try { localStorage.setItem(WIZARD_DISMISSED_KEY, "1"); } catch (_) {}
    wizardVisible = false;
    if (wizardOverlay) wizardOverlay.style.display = "none";
    if (onboardBanner) onboardBanner.style.display = (meState.authenticated && meState.has_key) ? "none" : "block";
  }
  if (wizardSigninBtn) wizardSigninBtn.addEventListener("click", goSignIn);
  if (wizardCloseBtn) wizardCloseBtn.addEventListener("click", dismissWizard);
  document.querySelectorAll("[data-wizard-dismiss]").forEach(function (btn) {
    btn.addEventListener("click", dismissWizard);
  });
  if (wizardOkBtn) wizardOkBtn.addEventListener("click", function () {
    wizardVisible = false;
    if (wizardOverlay) wizardOverlay.style.display = "none";
    if (commandInput) commandInput.focus();
  });
  if (wizardSaveKeyBtn) wizardSaveKeyBtn.addEventListener("click", async function () {
    if (!wizardKeyInput || !(wizardKeyInput.value || "").trim()) {
      if (wizardKeyMessageEl) wizardKeyMessageEl.textContent = "Paste your Gemini key first.";
      return;
    }
    wizardSaveKeyBtn.disabled = true;
    try {
      await saveGeminiKey(wizardKeyInput.value);
      wizardKeyInput.value = "";
      if (wizardKeyMessageEl) wizardKeyMessageEl.textContent = "";
      await refreshMe();
      // Setup just completed: show the "You're good to start" panel.
      if (meState.authenticated && meState.has_key) {
        wizardVisible = true;
        if (wizardOverlay) wizardOverlay.style.display = "flex";
        showWizardStep(3);
      }
    } catch (err) {
      if (wizardKeyMessageEl) wizardKeyMessageEl.textContent = "Couldn't save that key: " + err.message;
    } finally {
      wizardSaveKeyBtn.disabled = false;
    }
  });
  if (wizardKeyInput) wizardKeyInput.addEventListener("keydown", function (ev) {
    if (ev.key === "Enter" && wizardSaveKeyBtn) wizardSaveKeyBtn.click();
  });

  if (saveKeyBtn) {
    saveKeyBtn.addEventListener("click", async () => {
      if (!keyInput || !(keyInput.value || "").trim()) {
        if (keyMessageEl) keyMessageEl.textContent = "Paste your Gemini key first.";
        return;
      }
      saveKeyBtn.disabled = true;
      try {
        await saveGeminiKey(keyInput.value);
        if (keyInput) keyInput.value = "";
        if (keyMessageEl) keyMessageEl.textContent = "Key saved — you're ready to chat.";
        refreshMe();
      } catch (err) {
        if (keyMessageEl) keyMessageEl.textContent = "Couldn't save that key: " + err.message;
      } finally {
        saveKeyBtn.disabled = false;
      }
    });
  }

  if (deleteKeyBtn) {
    deleteKeyBtn.addEventListener("click", async () => {
      try { await apiFetch("/api/auth/key", { method: "DELETE" }); } catch (_) {}
      if (keyMessageEl) keyMessageEl.textContent = "Key removed. Add a new one to keep chatting.";
      refreshMe();
    });
  }

  if (apiBaseUrlInput) {
    apiBaseUrlInput.value = localStorage.getItem(API_BASE_URL_KEY) || "";
    apiBaseUrlInput.addEventListener("change", () => {
      localStorage.setItem(API_BASE_URL_KEY, apiBaseUrlInput.value.trim());
      checkHealth();
      refreshMe();
    });
  }

  // Login redirect landing: ?login=success / ?login=error on /mobile/.
  (function handleLoginReturn() {
    const params = new URLSearchParams(window.location.search);
    const result = params.get("login");
    if (!result) return;
    if (result === "success") {
      appendMessage("assistant", "Signed in — welcome back. Your chats, notes and reminders are in sync on this device.");
    } else {
      appendMessage("assistant", "Sign-in didn't complete. Please try signing in with Google again from Settings.");
    }
    window.history.replaceState({}, "", window.location.pathname);
  })();

  // Initial health check and periodic ping
  checkHealth();
  refreshMe();
  setInterval(checkHealth, 15000);

  // Load saved gateway URL on initialization (non-sensitive host config)
  if (remoteGatewayUrlInput) {
    const savedGateway = localStorage.getItem(GATEWAY_URL_KEY) || "";
    remoteGatewayUrlInput.value = savedGateway;
    remoteGatewayUrlInput.addEventListener("change", () => {
      localStorage.setItem(GATEWAY_URL_KEY, remoteGatewayUrlInput.value.trim());
      checkHealth();
    });
  }

  // Show local pairing helper only when accessed on localhost
  if (localPairHelper && isLocalhostHost) {
    localPairHelper.style.display = "block";
  }

  // Generate pairing code locally
  if (generatePairingCodeBtn) {
    generatePairingCodeBtn.addEventListener("click", async () => {
      generatePairingCodeBtn.disabled = true;
      try {
        const resp = await apiFetch("/api/remote/pair/generate", { method: "POST" });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          throw new Error(err.detail || `HTTP ${resp.status}`);
        }
        const data = await resp.json();
        displayedCode.textContent = data.pairing_code;
        generatedCodeDisplay.style.display = "block";
        if (pairingCodeInput) pairingCodeInput.value = data.pairing_code;
      } catch (err) {
        alert("Failed to generate code: " + err.message);
      } finally {
        generatePairingCodeBtn.disabled = false;
      }
    });
  }

  // Connect & Pair
  if (pairSubmitBtn) {
    pairSubmitBtn.addEventListener("click", async () => {
      const code = (pairingCodeInput?.value || "").trim();
      const gateway = (remoteGatewayUrlInput?.value || "").trim();

      if (!isLocalhostHost && !gateway) {
        alert("Please enter your laptop's Tailscale address (e.g. https://laptop-name.tailnet-xyz.ts.net).");
        return;
      }
      if (!code) {
        alert("Please enter the 6-digit one-time pairing code from your laptop.");
        return;
      }

      if (gateway) {
        localStorage.setItem(GATEWAY_URL_KEY, gateway);
      }

      pairSubmitBtn.disabled = true;
      pairSubmitBtn.textContent = "Pairing...";

      try {
        const targetUrl = (getBaseUrl() || "") + "/api/remote/pair/exchange";
        const resp = await fetch(targetUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ pairing_code: code }),
        });

        if (!resp.ok) {
          const errData = await resp.json().catch(() => ({}));
          throw new Error(errData.detail || `Server returned HTTP ${resp.status}`);
        }

        const data = await resp.json();
        // Store in volatile memory ONLY!
        remoteSessionToken = data.session_token;

        if (pairingCodeInput) pairingCodeInput.value = "";
        pairControlsContainer.style.display = "none";
        pairedStatusContainer.style.display = "block";

        appendMessage("assistant", "**Secure Tailscale Pairing Active:** Connected to laptop backend. Session token held in volatile memory.");
        closeAllDrawers();
        checkHealth();
      } catch (err) {
        alert("Pairing failed: " + err.message);
      } finally {
        pairSubmitBtn.disabled = false;
        pairSubmitBtn.textContent = "Connect & Pair";
      }
    });
  }

  // Disconnect & Revoke
  if (disconnectBtn) {
    disconnectBtn.addEventListener("click", async () => {
      if (remoteSessionToken) {
        try {
          await apiFetch("/api/remote/session/revoke", { method: "POST" });
        } catch (_) {}
      }
      remoteSessionToken = null;
      pairedStatusContainer.style.display = "none";
      pairControlsContainer.style.display = "block";
      appendMessage("assistant", "Disconnected from laptop. In-memory session token has been revoked.");
      checkHealth();
    });
  }

  if (closeNoticeBtn) {
    closeNoticeBtn.addEventListener("click", () => {
      networkNotice.style.display = "none";
    });
  }

  // --- Command History Privacy Settings ---
  const HISTORY_KEY = "jarvis_command_history";
  const HISTORY_OPT_IN_KEY = "jarvis_history_opt_in";

  // Initialize history toggle state (default: OFF / false)
  const isHistoryOptedIn = localStorage.getItem(HISTORY_OPT_IN_KEY) === "true";
  optInHistoryToggle.checked = isHistoryOptedIn;

  optInHistoryToggle.addEventListener("change", (e) => {
    localStorage.setItem(HISTORY_OPT_IN_KEY, e.target.checked ? "true" : "false");
    if (!e.target.checked) {
      localStorage.removeItem(HISTORY_KEY);
    }
  });

  clearHistoryBtn.addEventListener("click", () => {
    localStorage.removeItem(HISTORY_KEY);
    alert("Local command history has been cleared.");
  });

  function recordHistoryIfAllowed(cmd) {
    if (localStorage.getItem(HISTORY_OPT_IN_KEY) === "true" && cmd) {
      try {
        const hist = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
        hist.unshift(cmd);
        if (hist.length > 50) hist.pop();
        localStorage.setItem(HISTORY_KEY, JSON.stringify(hist));
      } catch (e) {
        console.warn("Could not save history:", e);
      }
    }
  }

  // --- Auto-expanding Textarea ---
  commandInput.addEventListener("input", () => {
    commandInput.style.height = "auto";
    commandInput.style.height = Math.min(commandInput.scrollHeight, 120) + "px";
  });

  commandInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendCommand();
    }
  });

  sendBtn.addEventListener("click", handleSendCommand);

  // --- Quick Command Chips ---
  quickChips.forEach((chip) => {
    chip.addEventListener("click", () => {
      commandInput.value = chip.dataset.cmd;
      commandInput.style.height = "auto";
      commandInput.focus();
    });
  });

  // --- Send Command Workflow ---
  async function handleSendCommand() {
    const text = commandInput.value.trim();
    if (!text || activeAbortController) return;

    recordHistoryIfAllowed(text);

    // Append User Message to Chat
    appendMessage("user", text);
    commandInput.value = "";
    commandInput.style.height = "auto";

    // Setup AbortController for Stop/Pause control
    activeAbortController = new AbortController();
    setOperationActive(true);

    try {
      const response = await apiFetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
        signal: activeAbortController.signal,
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        if (response.status === 401) {
          throw new Error("Please sign in with Google first — tap Settings, then Sign in with Google.");
        }
        if (response.status === 429) {
          throw new Error(errData.detail || "Too many requests — please wait a little and try again.");
        }
        throw new Error(errData.detail || `Server returned HTTP ${response.status}`);
      }

      const data = await response.json();
      appendMessage("assistant", data.reply, data.tools_executed);

      // Optional Text-to-Speech
      if (ttsToggle.checked && "speechSynthesis" in window && data.reply) {
        speakResponse(data.reply);
      }

      // Check if any confirmation was requested
      await checkForPendingConfirmations();
    } catch (err) {
      if (err.name === "AbortError") {
        appendMessage("assistant", "Operation stopped by user.");
      } else {
        appendMessage("assistant", `Error: ${err.message}`);
      }
    } finally {
      activeAbortController = null;
      setOperationActive(false);
    }
  }

  function setOperationActive(active) {
    if (active) {
      activeOpBar.style.display = "flex";
      sendBtn.disabled = true;
    } else {
      activeOpBar.style.display = "none";
      sendBtn.disabled = false;
    }
  }

  // --- Stop / Pause Control ---
  stopBtn.addEventListener("click", async () => {
    if (activeAbortController) {
      activeAbortController.abort();
    }
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    try {
      await apiFetch("/api/remote/stop", { method: "POST" });
    } catch (_) {}
  });

  // --- Chat Message Rendering ---
  function appendMessage(sender, text, toolsExecuted = []) {
    const msgEl = document.createElement("div");
    msgEl.className = `message ${sender}-message`;

    const nowStr = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    const senderName = sender === "user" ? "You" : "Jarvis";

    let toolsHtml = "";
    if (toolsExecuted && toolsExecuted.length > 0) {
      const pills = toolsExecuted.map((t) => {
        const statusClass = t.success ? "tool-success" : "tool-failure";
        return `<span class="tool-pill ${statusClass}">${escapeHtml(t.tool_name)}</span>`;
      }).join("");
      toolsHtml = `<div class="tool-pill-group"><span class="tool-pill-label">Tools:</span> ${pills}</div>`;
    }

    msgEl.innerHTML = `
      <div class="message-header">
        <span class="sender-name">${escapeHtml(senderName)}</span>
        <span class="timestamp">${nowStr}</span>
      </div>
      <div class="message-body">${formatMessageBody(text)}</div>
      ${toolsHtml}
    `;

    chatStream.appendChild(msgEl);
    chatStream.scrollTop = chatStream.scrollHeight;
  }

  function formatMessageBody(raw) {
    if (!raw) return "";
    // Basic escaping and formatting (links and paragraphs)
    const escaped = escapeHtml(raw);
    const withLinks = escaped.replace(
      /\[(.*?)\]\((https?:\/\/[^\s]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
    );
    return `<p>${withLinks.replace(/\n\n/g, "</p><p>").replace(/\n/g, "<br>")}</p>`;
  }

  function escapeHtml(str) {
    if (typeof str !== "string") return "";
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // --- Confirmation Workflow Integration ---
  async function checkForPendingConfirmations() {
    try {
      const resp = await apiFetch("/api/confirm/pending");
      if (!resp.ok) return;
      const pendingList = await resp.json();
      if (!Array.isArray(pendingList) || pendingList.length === 0) return;

      for (const item of pendingList) {
        renderConfirmationCard(item);
      }
    } catch (e) {
      console.debug("Pending confirmation check failed:", e);
    }
  }

  function renderConfirmationCard(action) {
    const existing = document.getElementById(`conf-${action.confirmation_id}`);
    if (existing) return;

    const card = document.createElement("div");
    card.id = `conf-${action.confirmation_id}`;
    card.className = "confirmation-card";
    card.innerHTML = `
      <h4>Action Confirmation Required</h4>
      <p class="confirmation-desc">${escapeHtml(action.description || action.tool_name)}</p>
      <div class="confirmation-buttons">
        <button class="btn-confirm" data-id="${action.confirmation_id}">Approve</button>
        <button class="btn-deny" data-id="${action.confirmation_id}">Deny</button>
      </div>
    `;

    chatStream.appendChild(card);
    chatStream.scrollTop = chatStream.scrollHeight;

    card.querySelector(".btn-confirm").addEventListener("click", () => resolveConfirmation(action.confirmation_id, true, card));
    card.querySelector(".btn-deny").addEventListener("click", () => resolveConfirmation(action.confirmation_id, false, card));
  }

  async function resolveConfirmation(confId, approve, cardEl) {
    try {
      const resp = await apiFetch("/api/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmation_id: confId, approve }),
      });
      const res = await resp.json();
      cardEl.innerHTML = `
        <p class="confirmation-desc"><strong>Action ${approve ? "Approved" : "Denied"}:</strong> ${escapeHtml(res.message || "Completed.")}</p>
      `;
    } catch (e) {
      alert("Failed to submit confirmation: " + e.message);
    }
  }

  // --- Voice Push-to-Talk (Web Speech API) ---
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (SpeechRecognition) {
    voiceBtn.addEventListener("click", toggleVoiceRecording);
    cancelVoiceBtn.addEventListener("click", cancelVoiceRecording);
  } else {
    voiceBtn.title = "Voice recognition not supported in this browser";
    voiceBtn.style.opacity = "0.4";
  }

  function toggleVoiceRecording() {
    if (isRecording) {
      stopVoiceRecording();
    } else {
      startVoiceRecording();
    }
  }

  function startVoiceRecording() {
    if (!SpeechRecognition) return;
    try {
      recognitionInstance = new SpeechRecognition();
      recognitionInstance.lang = "en-US";
      recognitionInstance.interimResults = true;
      recognitionInstance.maxAlternatives = 1;

      recognitionInstance.onstart = () => {
        isRecording = true;
        recordingBanner.style.display = "flex";
        voiceBtn.classList.add("recording");
      };

      recognitionInstance.onresult = (event) => {
        let transcript = "";
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          transcript += event.results[i][0].transcript;
        }
        commandInput.value = transcript;
        commandInput.style.height = "auto";
        commandInput.style.height = Math.min(commandInput.scrollHeight, 120) + "px";
      };

      recognitionInstance.onerror = (event) => {
        console.warn("Speech recognition error:", event.error);
        stopVoiceRecording();
      };

      recognitionInstance.onend = () => {
        stopVoiceRecording();
      };

      recognitionInstance.start();
    } catch (e) {
      console.warn("Speech recognition start failed:", e);
      stopVoiceRecording();
    }
  }

  function stopVoiceRecording() {
    isRecording = false;
    recordingBanner.style.display = "none";
    voiceBtn.classList.remove("recording");
    if (recognitionInstance) {
      try { recognitionInstance.stop(); } catch (e) {}
      recognitionInstance = null;
    }
  }

  function cancelVoiceRecording() {
    stopVoiceRecording();
    commandInput.value = "";
    commandInput.style.height = "auto";
  }

  function speakResponse(text) {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    // Clean text of markdown before speaking
    const cleanText = text.replace(/\[(.*?)\]\(.*?\)/g, "$1").replace(/[*#`_]/g, "").trim();
    if (!cleanText) return;

    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.rate = 1.0;
    utterance.pitch = 1.0;
    window.speechSynthesis.speak(utterance);
  }

  // --- Motion engine: pointer glow + ring, magnetic buttons, 3D tilt,
  // per-pixel scroll (progress bar + wordmark). Same patterns as
  // frontend/landing/landing.js. Fine pointers only; native cursor stays
  // visible; touch and reduced-motion users get none of it.
  (function initMotion() {
    const motionOK = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const finePointer = window.matchMedia("(pointer: fine)").matches;
    if (!motionOK || !finePointer) return;
    document.body.classList.add("has-fine-pointer");
    const glowEl = document.getElementById("cursor-glow");
    const ringEl = document.getElementById("cursor-ring");
    const orbEls = Array.prototype.slice.call(document.querySelectorAll("#ambient-3d .orb i")).map(function (el) {
      const host = el.parentElement;
      return { el: el, depth: parseFloat((host && host.getAttribute("data-depth")) || "20") };
    });
    const wordmarkEl = document.getElementById("chat-wordmark");
    const progressFill = document.getElementById("scroll-progress-fill");
    let gxT = -200, gyT = -200, gx = -200, gy = -200;
    let rxT = -200, ryT = -200, rx = -200, ry = -200;
    let ticking = false;
    function applyFrame() {
      gx += (gxT - gx) * 0.2; gy += (gyT - gy) * 0.2;
      rx += (rxT - rx) * 0.35; ry += (ryT - ry) * 0.35;
      if (glowEl) glowEl.style.transform = "translate3d(" + gx.toFixed(1) + "px," + gy.toFixed(1) + "px,0)";
      if (ringEl) ringEl.style.transform = "translate3d(" + rx.toFixed(1) + "px," + ry.toFixed(1) + "px,0)";
      // Ambient orbs drift with the pointer at different depths (parallax).
      // The CSS drift animation lives on the outer .orb; this moves the
      // inner circle, so the two transforms never fight.
      if (orbEls.length) {
        const nx = (gx / Math.max(1, window.innerWidth) - 0.5) * 2;
        const ny = (gy / Math.max(1, window.innerHeight) - 0.5) * 2;
        orbEls.forEach(function (o) {
          o.el.style.transform = "translate3d(" + (nx * o.depth).toFixed(1) + "px," + (ny * o.depth).toFixed(1) + "px,0)";
        });
      }
      ticking = false;
      if (Math.abs(gxT - gx) > 0.5 || Math.abs(gyT - gy) > 0.5 || Math.abs(rxT - rx) > 0.5 || Math.abs(ryT - ry) > 0.5) {
        requestTick();
      }
    }
    function requestTick() {
      if (!ticking) { ticking = true; requestAnimationFrame(applyFrame); }
    }
    document.addEventListener("pointermove", function (ev) {
      gxT = ev.clientX; gyT = ev.clientY; rxT = ev.clientX; ryT = ev.clientY;
      requestTick();
    }, { passive: true });
    document.addEventListener("pointerover", function (ev) {
      if (!ringEl) return;
      const t = ev.target && ev.target.closest ? ev.target.closest("a, button, input, textarea, .chip") : null;
      ringEl.classList.toggle("is-hover", !!t);
    });
    // Magnetic send / voice buttons drift a few px toward the pointer.
    [sendBtn, voiceBtn].forEach(function (btn) {
      if (!btn) return;
      btn.addEventListener("pointermove", function (ev) {
        const r = btn.getBoundingClientRect();
        const dx = (ev.clientX - (r.left + r.width / 2)) / r.width;
        const dy = (ev.clientY - (r.top + r.height / 2)) / r.height;
        btn.style.transform = "translate(" + (dx * 6).toFixed(1) + "px, " + (dy * 6).toFixed(1) + "px)";
      });
      btn.addEventListener("pointerleave", function () { btn.style.transform = ""; });
    });
    // 3D tilt on message cards (delegated — messages are added dynamically).
    chatStream.addEventListener("pointermove", function (ev) {
      const card = ev.target && ev.target.closest ? ev.target.closest(".message") : null;
      if (!card) return;
      const r = card.getBoundingClientRect();
      const trx = -((ev.clientY - r.top) / r.height - 0.5) * 6;
      const try_ = ((ev.clientX - r.left) / r.width - 0.5) * 6;
      card.style.setProperty("--rx", trx.toFixed(2) + "deg");
      card.style.setProperty("--ry", try_.toFixed(2) + "deg");
      card.classList.add("is-tilting");
    });
    chatStream.addEventListener("pointerleave", function (ev) {
      const card = ev.target && ev.target.closest ? ev.target.closest(".message") : null;
      if (!card) return;
      card.classList.remove("is-tilting");
    }, true);
    // Per-pixel scroll: progress bar + wordmark drift/fade as you scroll.
    chatStream.addEventListener("scroll", function () {
      const max = chatStream.scrollHeight - chatStream.clientHeight;
      const p = max > 0 ? chatStream.scrollTop / max : 0;
      if (progressFill) progressFill.style.width = (p * 100).toFixed(1) + "%";
      if (wordmarkEl) {
        wordmarkEl.style.transform = "translateY(" + (chatStream.scrollTop * -0.08).toFixed(1) + "px)";
        wordmarkEl.style.opacity = Math.max(0.25, 1 - p * 0.6).toFixed(2);
      }
    }, { passive: true });
  })();

  // --- Drawers Management (Actions & Settings) ---
  function openDrawer(drawer) {
    drawer.classList.add("open");
    drawer.setAttribute("aria-hidden", "false");
    drawerBackdrop.style.display = "block";
  }

  function closeAllDrawers() {
    actionsDrawer.classList.remove("open");
    actionsDrawer.setAttribute("aria-hidden", "true");
    settingsDrawer.classList.remove("open");
    settingsDrawer.setAttribute("aria-hidden", "true");
    drawerBackdrop.style.display = "none";
  }

  navActionsBtn.addEventListener("click", () => {
    openDrawer(actionsDrawer);
    loadRecentActions();
  });
  closeActionsBtn.addEventListener("click", closeAllDrawers);
  refreshActionsBtn.addEventListener("click", loadRecentActions);

  navSettingsBtn.addEventListener("click", () => {
    openDrawer(settingsDrawer);
  });
  closeSettingsBtn.addEventListener("click", closeAllDrawers);
  drawerBackdrop.addEventListener("click", closeAllDrawers);

  async function loadRecentActions() {
    actionsList.innerHTML = '<div class="actions-empty">Loading audit actions...</div>';
    try {
      const resp = await apiFetch("/api/actions?limit=25");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const actions = await resp.json();

      if (!Array.isArray(actions) || actions.length === 0) {
        actionsList.innerHTML = '<div class="actions-empty">No recent actions logged yet.</div>';
        return;
      }

      actionsList.innerHTML = "";
      actions.reverse().forEach((act) => {
        const item = document.createElement("div");
        item.className = "action-item";

        const statusClass = act.status === "success" ? "success" : "failure";
        const dateObj = new Date(act.timestamp);
        const timeStr = dateObj.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

        item.innerHTML = `
          <div class="action-header">
            <span class="action-tool">${escapeHtml(act.tool_name)}</span>
            <span class="action-status ${statusClass}">${escapeHtml(act.status)}</span>
          </div>
          <div class="action-time">${timeStr} (${act.execution_time_ms ? act.execution_time_ms.toFixed(1) + "ms" : "N/A"})</div>
        `;
        actionsList.appendChild(item);
      });
    } catch (e) {
      actionsList.innerHTML = `<div class="actions-empty">Failed to load actions: ${escapeHtml(e.message)}</div>`;
    }
  }
});
