/**
 * Jarvis Local Companion - Chrome Extension Popup Script
 * Connects exclusively to the local Jarvis backend on http://127.0.0.1:8000
 * Supports Push-to-Talk speech recognition, local TTS, and active tab inspection.
 */

const BACKEND_URL = "http://127.0.0.1:8000";
let activeAbortController = null;
let speechRecognitionInstance = null;
let currentRecordedTranscript = "";

// DOM Elements
const statusBadge = document.getElementById("backend-status");
const statusText = document.getElementById("status-text");
const readBtn = document.getElementById("read-btn");
const stopBtn = document.getElementById("stop-btn");
const questionInput = document.getElementById("question-input");
const progressContainer = document.getElementById("progress-container");
const progressText = document.getElementById("progress-text");
const resultContainer = document.getElementById("result-container");
const resultText = document.getElementById("result-text");
const resultModeTag = document.getElementById("result-mode-tag");
const charCount = document.getElementById("char-count");
const apiNotice = document.getElementById("api-notice");
const errorContainer = document.getElementById("error-container");
const errorMessage = document.getElementById("error-message");
const tabInfo = document.getElementById("tab-info");
const tabTitle = document.getElementById("tab-title");

// Voice Elements
const voiceRecordBtn = document.getElementById("voice-record-btn");
const recordingBanner = document.getElementById("recording-banner");
const voiceDoneBtn = document.getElementById("voice-done-btn");
const voiceCancelBtn = document.getElementById("voice-cancel-btn");
const ttsToggle = document.getElementById("tts-toggle");
const ttsControlBar = document.getElementById("tts-control-bar");
const stopSpeakingBtn = document.getElementById("stop-speaking-btn");

// 1. Check local Jarvis backend health on startup
async function checkBackendHealth() {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2000);

    const res = await fetch(`${BACKEND_URL}/health`, {
      method: "GET",
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    if (res.ok) {
      const data = await res.json();
      statusBadge.className = "status-badge online";
      statusText.textContent = "Jarvis Online";
      statusBadge.title = `Connected to Jarvis v${data.version} on ${BACKEND_URL}`;
      readBtn.disabled = false;
    } else {
      setBackendOffline();
    }
  } catch (err) {
    setBackendOffline();
  }
}

function setBackendOffline() {
  statusBadge.className = "status-badge offline";
  statusText.textContent = "Backend Offline";
  statusBadge.title = `Cannot reach ${BACKEND_URL}. Please ensure 'uvicorn app.main:app' is running.`;
}

// 2. Safe DOM extractor injected into user-selected active tab
function extractVisiblePageText() {
  const clone = document.body.cloneNode(true);

  // Strip sensitive or non-content tags completely
  const tagsToRemove = [
    "script", "style", "noscript", "template", "iframe", "svg", "canvas",
    "input[type='password']", "input[type='hidden']"
  ];

  tagsToRemove.forEach(selector => {
    clone.querySelectorAll(selector).forEach(el => el.remove());
  });

  const rawText = clone.innerText || clone.textContent || "";
  const cleanedText = rawText
    .split("\n")
    .map(line => line.trim())
    .filter(line => line.length > 0)
    .join("\n")
    .replace(/[ \t]+/g, " ");

  const maxChars = 50000;
  const truncatedText = cleanedText.slice(0, maxChars);

  return {
    url: window.location.href,
    title: document.title || "Untitled Tab",
    text: truncatedText,
    totalLength: cleanedText.length,
  };
}

// 3. Voice: Push-to-Talk Speech Recognition
function startPushToTalk() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    showError("Speech recognition is not supported in this browser version.");
    return;
  }

  currentRecordedTranscript = "";
  speechRecognitionInstance = new SpeechRecognition();
  speechRecognitionInstance.continuous = false; // Strictly push-to-talk, not continuous
  speechRecognitionInstance.interimResults = true;
  speechRecognitionInstance.lang = "en-US";

  speechRecognitionInstance.onstart = () => {
    hideError();
    recordingBanner.classList.remove("hidden");
    voiceRecordBtn.disabled = true;
  };

  speechRecognitionInstance.onresult = (event) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; ++i) {
      if (event.results[i].isFinal) {
        currentRecordedTranscript += event.results[i][0].transcript + " ";
      } else {
        interim += event.results[i][0].transcript;
      }
    }
    const displayTranscript = (currentRecordedTranscript + interim).trim();
    if (displayTranscript) {
      questionInput.value = displayTranscript;
    }
  };

  speechRecognitionInstance.onerror = (event) => {
    if (event.error !== "no-speech" && event.error !== "aborted") {
      showError(`Voice recognition error: ${event.error}`);
    }
    stopRecordingUI();
  };

  speechRecognitionInstance.onend = () => {
    stopRecordingUI();
  };

  try {
    speechRecognitionInstance.start();
  } catch (err) {
    showError(`Failed to start microphone: ${err.message}`);
    stopRecordingUI();
  }
}

function stopRecordingUI() {
  recordingBanner.classList.add("hidden");
  voiceRecordBtn.disabled = false;
  if (speechRecognitionInstance) {
    speechRecognitionInstance = null;
  }
}

function handleVoiceDone() {
  if (speechRecognitionInstance) {
    speechRecognitionInstance.stop();
  }
  stopRecordingUI();
}

function handleVoiceCancel() {
  if (speechRecognitionInstance) {
    speechRecognitionInstance.abort();
  }
  stopRecordingUI();
}

// 4. Voice: Optional Spoken Responses (TTS)
function speakResponseIfEnabled(text) {
  if (!ttsToggle.checked || !("speechSynthesis" in window)) {
    return;
  }

  window.speechSynthesis.cancel(); // Stop any active speech

  const cleanText = text.replace(/[*#_`>]/g, "").slice(0, 500); // Safe clean text snippet
  const utterance = new SpeechSynthesisUtterance(cleanText);
  utterance.lang = "en-US";
  utterance.rate = 1.0;

  ttsControlBar.classList.remove("hidden");

  utterance.onend = () => {
    ttsControlBar.classList.add("hidden");
  };

  utterance.onerror = () => {
    ttsControlBar.classList.add("hidden");
  };

  window.speechSynthesis.speak(utterance);
}

function stopSpeaking() {
  if ("speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }
  ttsControlBar.classList.add("hidden");
}

// 5. Handle "Read this page" action
async function handleReadPage() {
  hideError();
  resultContainer.classList.add("hidden");
  stopSpeaking();

  const mode = document.querySelector('input[name="mode"]:checked').value;
  const question = questionInput.value.trim();

  readBtn.disabled = true;
  stopBtn.disabled = false;
  progressContainer.classList.remove("hidden");
  progressText.textContent = "Extracting visible page text...";

  activeAbortController = new AbortController();

  try {
    const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });

    if (!activeTab || !activeTab.id) {
      throw new Error("No active tab found. Please click the extension while viewing a webpage.");
    }

    if (activeTab.url.startsWith("chrome://") || activeTab.url.startsWith("edge://") || activeTab.url.startsWith("about:")) {
      throw new Error("Browser internal pages cannot be inspected due to browser security restrictions.");
    }

    tabInfo.classList.remove("hidden");
    tabTitle.textContent = activeTab.title || activeTab.url;

    const injectionResults = await chrome.scripting.executeScript({
      target: { tabId: activeTab.id },
      func: extractVisiblePageText,
    });

    if (!injectionResults || !injectionResults[0] || !injectionResults[0].result) {
      throw new Error("Failed to extract text from the active tab.");
    }

    const pageData = injectionResults[0].result;

    if (!pageData.text || pageData.text.trim().length === 0) {
      throw new Error("No readable visible text was found on this webpage.");
    }

    progressText.textContent = "Sending visible text to Jarvis for study analysis...";

    const response = await fetch(`${BACKEND_URL}/api/extension/read-page`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        url: pageData.url,
        title: pageData.title,
        page_text: pageData.text,
        question: question || null,
        mode: mode,
      }),
      signal: activeAbortController.signal,
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.detail || `Server returned error status ${response.status}`);
    }

    const result = await response.json();

    resultContainer.classList.remove("hidden");
    resultModeTag.textContent = mode === "quiz_help" ? "Practice Quiz Help" : "Page Summary";
    resultModeTag.style.backgroundColor = mode === "quiz_help" ? "#8b5cf6" : "#3b82f6";
    charCount.textContent = `${result.chars_processed.toLocaleString()} chars analyzed`;
    resultText.textContent = result.reply;
    apiNotice.textContent = result.disclosure;

    // Trigger local spoken response if user enabled it
    speakResponseIfEnabled(result.reply);

  } catch (err) {
    if (err.name === "AbortError") {
      showError("Analysis stopped by user.");
    } else {
      showError(err.message || "An unexpected error occurred.");
    }
  } finally {
    readBtn.disabled = false;
    stopBtn.disabled = true;
    progressContainer.classList.add("hidden");
    activeAbortController = null;
  }
}

// 6. Stop button
function handleStop() {
  if (activeAbortController) {
    activeAbortController.abort();
    activeAbortController = null;
  }
}

function showError(msg) {
  errorContainer.classList.remove("hidden");
  errorMessage.textContent = msg;
}

function hideError() {
  errorContainer.classList.add("hidden");
  errorMessage.textContent = "";
}

// Phase 8: Automation DOM Elements
const automationPanel = document.getElementById("automation-panel");
const approvedDomainSelect = document.getElementById("approved-domain-select");
const approveCurrentTabBtn = document.getElementById("approve-current-tab-btn");
const autoActionRadios = document.querySelectorAll("input[name='auto_action']");
const fillFieldInputs = document.getElementById("fill-field-inputs");
const autoSelectorInput = document.getElementById("auto-selector");
const autoValueInput = document.getElementById("auto-value");
const autoDescInput = document.getElementById("auto-desc");
const autoConfirmationBox = document.getElementById("automation-confirmation-box");
const confirmationDescText = document.getElementById("confirmation-desc-text");
const autoConfirmBtn = document.getElementById("auto-confirm-btn");
const autoDenyBtn = document.getElementById("auto-deny-btn");
const activityLogList = document.getElementById("activity-log-list");
const clearActivityLogBtn = document.getElementById("clear-activity-log-btn");

let pendingAutomationAction = null;

// Handle Mode Change
document.querySelectorAll("input[name='mode']").forEach(radio => {
  radio.addEventListener("change", (e) => {
    if (e.target.value === "automation") {
      automationPanel.classList.remove("hidden");
      readBtn.innerHTML = '<span class="btn-icon">&#9658;</span> Execute Action';
      loadApprovedDomains();
    } else {
      automationPanel.classList.add("hidden");
      readBtn.innerHTML = '<span class="btn-icon">&#128214;</span> Read This Page';
    }
  });
});

// Handle Automation Action Sub-mode (read vs fill)
autoActionRadios.forEach(radio => {
  radio.addEventListener("change", (e) => {
    if (e.target.value === "fill") {
      fillFieldInputs.classList.remove("hidden");
    } else {
      fillFieldInputs.classList.add("hidden");
    }
  });
});

// Load Approved Domains from Backend
async function loadApprovedDomains() {
  try {
    const res = await fetch(`${BACKEND_URL}/api/browser/approved-domains`);
    if (res.ok) {
      const data = await res.json();
      approvedDomainSelect.innerHTML = "";
      data.approved_domains.forEach(d => {
        const opt = document.createElement("option");
        opt.value = d;
        opt.textContent = d;
        approvedDomainSelect.appendChild(opt);
      });
    }
  } catch (e) {
    console.debug("Could not load approved domains:", e);
  }
}

// Approve Current Active Tab Domain
if (approveCurrentTabBtn) {
  approveCurrentTabBtn.addEventListener("click", async () => {
    try {
      const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tabs || !tabs[0] || !tabs[0].url) return;
      const url = new URL(tabs[0].url);
      const domain = url.hostname;

      const res = await fetch(`${BACKEND_URL}/api/browser/approve-domain`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domain }),
      });
      if (res.ok) {
        await loadApprovedDomains();
        approvedDomainSelect.value = domain;
        logActivity("APPROVE_DOMAIN", domain, "success");
      }
    } catch (e) {
      showError("Failed to approve domain: " + e.message);
    }
  });
}

// Activity Log helpers
function logActivity(action, domain, status) {
  const emptyMsg = activityLogList.querySelector(".log-empty");
  if (emptyMsg) emptyMsg.remove();

  const item = document.createElement("div");
  item.className = `activity-log-item ${status}`;
  const now = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  item.innerHTML = `<span><strong>${action}</strong>: ${domain}</span> <span>${now}</span>`;
  activityLogList.prepend(item);
}

if (clearActivityLogBtn) {
  clearActivityLogBtn.addEventListener("click", () => {
    activityLogList.innerHTML = '<div class="log-empty">No browser actions executed yet.</div>';
  });
}

// Safe Injected Field Filler (Runs in tab context via chrome.scripting.executeScript)
function injectSafeFieldFill(selector, value) {
  const el = document.querySelector(selector);
  if (!el) return { success: false, error: `Element with selector '${selector}' not found.` };

  // Strict sensitive check
  const type = (el.type || "").toLowerCase();
  const name = (el.name || "").toLowerCase();
  const id = (el.id || "").toLowerCase();
  const ac = (el.autocomplete || "").toLowerCase();

  const sensitive = ["password", "card", "cvv", "secret", "token", "otp", "ssn", "pin"];
  if (type === "password" || type === "hidden" || type === "file") {
    return { success: false, error: "Security Refusal: Cannot fill password, hidden, or file inputs." };
  }
  for (const s of sensitive) {
    if (name.includes(s) || id.includes(s) || ac.includes(s)) {
      return { success: false, error: `Security Refusal: Field appears sensitive ('${s}'). Cannot automate.` };
    }
  }

  // Set value and dispatch events
  el.value = value;
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));

  return { success: true };
}

// Phase 8: Automation Execution Handler
async function handleAutomationAction(activeTab) {
  const approvedDomain = approvedDomainSelect.value;
  if (!approvedDomain) {
    showError("Please select or approve a domain first.");
    return;
  }

  // Validate active tab domain
  try {
    const tabUrl = new URL(activeTab.url);
    if (tabUrl.hostname !== approvedDomain && !tabUrl.hostname.endsWith("." + approvedDomain)) {
      showError(`Domain mismatch: Active tab '${tabUrl.hostname}' does not match approved domain '${approvedDomain}'.`);
      logActivity("DOMAIN_MISMATCH", tabUrl.hostname, "failure");
      return;
    }
  } catch (e) {
    showError("Invalid tab URL: " + e.message);
    return;
  }

  const selectedAutoAction = document.querySelector("input[name='auto_action']:checked")?.value || "read";

  if (selectedAutoAction === "fill") {
    const selector = autoSelectorInput.value.trim();
    const value = autoValueInput.value;
    const desc = autoDescInput.value.trim();

    if (!selector) {
      showError("Please enter a CSS selector for the field to fill.");
      return;
    }

    // Call backend to plan and validate action
    try {
      progressContainer.classList.remove("hidden");
      progressText.textContent = "Validating field and planning action...";

      const planResp = await fetch(`${BACKEND_URL}/api/browser/plan-action`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action_type: "fill_field",
          approved_domain: approvedDomain,
          selector: selector,
          value: value,
          field_description: desc || null,
        }),
      });

      if (!planResp.ok) {
        const errJson = await planResp.json().catch(() => ({}));
        throw new Error(errJson.detail || `HTTP ${planResp.status}`);
      }

      const planData = await planResp.json();
      pendingAutomationAction = {
        action_type: "fill_field",
        selector,
        value,
        approvedDomain,
        confirmation_id: planData.confirmation_id,
        tabId: activeTab.id,
      };

      // Show confirmation box
      confirmationDescText.textContent = planData.description;
      autoConfirmationBox.classList.remove("hidden");
      progressContainer.classList.add("hidden");
    } catch (err) {
      progressContainer.classList.add("hidden");
      showError(`Action planning rejected: ${err.message}`);
      logActivity("PLAN_FILL_REJECTED", approvedDomain, "failure");
    }
  } else {
    // Read page action within approved domain
    logActivity("READ_PAGE", approvedDomain, "success");
    // Delegates to normal read flow
    originalHandleReadPage();
  }
}

// Confirmation Buttons Listeners
if (autoConfirmBtn) {
  autoConfirmBtn.addEventListener("click", async () => {
    if (!pendingAutomationAction) return;

    try {
      // 1. Confirm with backend
      await fetch(`${BACKEND_URL}/api/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          confirmation_id: pendingAutomationAction.confirmation_id,
          approve: true,
        }),
      });

      // 2. Injected execution in tab
      const execResults = await chrome.scripting.executeScript({
        target: { tabId: pendingAutomationAction.tabId },
        func: injectSafeFieldFill,
        args: [pendingAutomationAction.selector, pendingAutomationAction.value],
      });

      const res = execResults?.[0]?.result;
      if (res && res.success) {
        autoConfirmationBox.classList.add("hidden");
        logActivity("FILL_FIELD", pendingAutomationAction.approvedDomain, "success");
        alert("Field successfully filled! Reminder: Click the submit button manually when ready.");
      } else {
        throw new Error(res?.error || "Injected script execution failed.");
      }
    } catch (err) {
      showError(`Execution failed: ${err.message}`);
      logActivity("FILL_FIELD_ERROR", pendingAutomationAction.approvedDomain, "failure");
    } finally {
      pendingAutomationAction = null;
    }
  });
}

if (autoDenyBtn) {
  autoDenyBtn.addEventListener("click", async () => {
    if (pendingAutomationAction) {
      logActivity("FILL_FIELD_DENIED", pendingAutomationAction.approvedDomain, "cancelled");
      pendingAutomationAction = null;
    }
    autoConfirmationBox.classList.add("hidden");
  });
}

// Update handleReadPage to branch into automation when mode is 'automation'
const originalHandleReadPage = handleReadPage;
handleReadPage = async function() {
  const mode = document.querySelector("input[name='mode']:checked")?.value || "summary";
  if (mode === "automation") {
    hideError();
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab) {
      showError("No active tab found.");
      return;
    }
    await handleAutomationAction(tab);
  } else {
    await originalHandleReadPage();
  }
};

// Main DOMContentLoaded Init
document.addEventListener("DOMContentLoaded", () => {
  checkBackendHealth();
  readBtn.addEventListener("click", handleReadPage);
  stopBtn.addEventListener("click", handleStop);

  // Voice Event Listeners
  voiceRecordBtn.addEventListener("click", startPushToTalk);
  voiceDoneBtn.addEventListener("click", handleVoiceDone);
  voiceCancelBtn.addEventListener("click", handleVoiceCancel);
  stopSpeakingBtn.addEventListener("click", stopSpeaking);
});


