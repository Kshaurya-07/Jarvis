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

// Event Listeners
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
