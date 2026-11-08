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

  // Phase 10 Demo Drawer
  const navDemoBtn = document.getElementById("nav-demo-btn");
  const closeDemoBtn = document.getElementById("close-demo-btn");
  const demoDrawer = document.getElementById("demo-drawer");
  const seedDemoBtn = document.getElementById("seed-demo-btn");
  const resetDemoBtn = document.getElementById("reset-demo-btn");

  const optInHistoryToggle = document.getElementById("opt-in-history-toggle");
  const clearHistoryBtn = document.getElementById("clear-history-btn");
  const ttsToggle = document.getElementById("tts-toggle");

  // Metadata elements
  const sysVersion = document.getElementById("sys-version");
  const sysPlatform = document.getElementById("sys-platform");
  const sysGemini = document.getElementById("sys-gemini");
  const sysGoogle = document.getElementById("sys-google");
  const sysToolsCount = document.getElementById("sys-tools-count");

  // State
  let activeAbortController = null;
  let recognitionInstance = null;
  let isRecording = false;

  // Initialize PWA Service Worker
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("./service-worker.js").catch((err) => {
      console.warn("ServiceWorker registration failed:", err);
    });
  }

  // --- Network & Option B Verification ---
  const isLocalhostHost = (
    window.location.hostname === "localhost" ||
    window.location.hostname === "127.0.0.1" ||
    window.location.hostname === "[::1]"
  );

  async function checkHealth() {
    try {
      const resp = await fetch("/health", { cache: "no-store" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();

      connectionPill.className = "connection-pill online";
      connectionText.textContent = "Online";

      if (sysVersion) sysVersion.textContent = data.version || "1.0.0";
      if (sysPlatform) sysPlatform.textContent = data.platform || "windows";
      if (sysGemini) sysGemini.textContent = data.gemini_configured ? "Ready" : "No API Key";
      if (sysGoogle) sysGoogle.textContent = data.google_connected ? "Connected" : "Not Connected";
      if (sysToolsCount) sysToolsCount.textContent = (data.active_tools || []).length;

      // In Option B, if accessing from a non-localhost hostname (e.g. phone on LAN)
      if (!isLocalhostHost) {
        networkNotice.style.display = "flex";
      }
    } catch (e) {
      connectionPill.className = "connection-pill offline";
      connectionText.textContent = "Offline";

      if (!isLocalhostHost) {
        networkNotice.style.display = "flex";
      }
    }
  }

  // Initial health check and periodic ping
  checkHealth();
  setInterval(checkHealth, 15000);

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
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
        signal: activeAbortController.signal,
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
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
  stopBtn.addEventListener("click", () => {
    if (activeAbortController) {
      activeAbortController.abort();
    }
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
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
      const resp = await fetch("/api/confirm/pending");
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
      const resp = await fetch("/api/confirm", {
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
    if (demoDrawer) {
      demoDrawer.classList.remove("open");
      demoDrawer.setAttribute("aria-hidden", "true");
    }
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

  // Phase 10 Demo Drawer Events
  if (navDemoBtn && demoDrawer) {
    navDemoBtn.addEventListener("click", () => {
      openDrawer(demoDrawer);
    });
  }
  if (closeDemoBtn) {
    closeDemoBtn.addEventListener("click", closeAllDrawers);
  }

  if (seedDemoBtn) {
    seedDemoBtn.addEventListener("click", async () => {
      seedDemoBtn.disabled = true;
      try {
        const resp = await fetch("/api/demo/seed", { method: "POST" });
        const res = await resp.json();
        if (resp.ok) {
          appendMessage("assistant", `**Demo Data Seeded:** ${res.message || "Fictional mission notes, reminders, and memory created with [DEMO] tag."}`);
          closeAllDrawers();
        } else {
          alert("Error seeding demo data: " + (res.detail || "Unknown error"));
        }
      } catch (err) {
        alert("Network error: " + err.message);
      } finally {
        seedDemoBtn.disabled = false;
      }
    });
  }

  if (resetDemoBtn) {
    resetDemoBtn.addEventListener("click", async () => {
      if (!confirm("Are you sure you want to clear all mock [DEMO] notes, reminders, and memory? Real user data will not be touched.")) {
        return;
      }
      resetDemoBtn.disabled = true;
      try {
        const resp = await fetch("/api/demo/reset", { method: "POST" });
        const res = await resp.json();
        if (resp.ok) {
          appendMessage("assistant", `**Demo Cleanup Complete:** ${res.message || "All [DEMO] records have been removed."}`);
          closeAllDrawers();
        } else {
          alert("Error resetting demo data: " + (res.detail || "Unknown error"));
        }
      } catch (err) {
        alert("Network error: " + err.message);
      } finally {
        resetDemoBtn.disabled = false;
      }
    });
  }

  // --- Audit Feed Loading ---
  async function loadRecentActions() {
    actionsList.innerHTML = '<div class="actions-empty">Loading audit actions...</div>';
    try {
      const resp = await fetch("/api/actions?limit=25");
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
