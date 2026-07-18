/**
 * Advanced RAG Chatbot - Embeddable Widget
 * -----------------------------------------
 * Drop this into any website with:
 *
 *   <script src="https://YOUR_DEPLOYED_DOMAIN/widget.js"
 *           data-bot-id="YOUR_BOT_ID"
 *           data-api-key="YOUR_BOT_API_KEY"
 *           data-api-base="https://YOUR_DEPLOYED_BACKEND_URL"></script>
 *
 * No build step, no framework required, no dependencies. Pure vanilla JS
 * that self-injects its own DOM + CSS, so it can never conflict with the
 * host site's styles or scripts.
 */
(function () {
  "use strict";

  var scriptTag = document.currentScript;
  var BOT_ID = scriptTag.getAttribute("data-bot-id");
  var API_KEY = scriptTag.getAttribute("data-api-key");
  var API_BASE = (scriptTag.getAttribute("data-api-base") || "").replace(/\/$/, "");

  if (!BOT_ID || !API_KEY || !API_BASE) {
    console.error("[RAG Widget] Missing required data-bot-id, data-api-key, or data-api-base attributes.");
    return;
  }

  var SESSION_KEY = "rag_widget_session_" + BOT_ID;
  var sessionId = getOrCreateSessionId();

  var state = {
    open: false,
    loading: false,
    connecting: true,
    slowNotice: false,
    config: { name: "Assistant", welcome_message: "Hi! How can I help?", primary_color: "#4F46E5" },
    messages: [], // { role: 'user'|'assistant', text }
  };

  function getOrCreateSessionId() {
    try {
      var existing = window.localStorage.getItem(SESSION_KEY);
      if (existing) return existing;
      var id = "sess_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
      window.localStorage.setItem(SESSION_KEY, id);
      return id;
    } catch (e) {
      // localStorage unavailable (private browsing, etc.) -- fall back to in-memory id.
      return "sess_" + Math.random().toString(36).slice(2);
    }
  }

  // ---------- DOM construction ----------
  var root = document.createElement("div");
  root.id = "rag-widget-root";
  document.addEventListener("DOMContentLoaded", mount);
  if (document.readyState === "complete" || document.readyState === "interactive") {
    mount();
  }

  function mount() {
    if (document.getElementById("rag-widget-root")) return;
    document.body.appendChild(root);
    injectStyles();
    render();
    fetchConfig();
    // Little entrance pop for the launcher bubble itself, once, on first load.
    requestAnimationFrame(function () {
      var fab = document.getElementById("rag-fab");
      if (fab) fab.classList.add("rag-fab-in");
    });
  }

  function injectStyles() {
    var style = document.createElement("style");
    style.textContent =
      "#rag-widget-root *{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;}" +
      "#rag-fab{position:fixed;bottom:20px;right:20px;width:60px;height:60px;border-radius:50%;" +
      "box-shadow:0 4px 16px rgba(0,0,0,0.25);cursor:pointer;display:flex;align-items:center;justify-content:center;" +
      "z-index:2147483000;border:none;transform:scale(0);opacity:0;" +
      "transition:transform .25s cubic-bezier(.34,1.56,.64,1),opacity .2s ease,box-shadow .15s ease;}" +
      "#rag-fab.rag-fab-in{transform:scale(1);opacity:1;}" +
      "#rag-fab:hover{transform:scale(1.08);box-shadow:0 6px 20px rgba(0,0,0,0.3);}" +
      "#rag-fab:active{transform:scale(0.94);}" +
      "#rag-fab svg{transition:transform .2s ease;}" +
      "#rag-fab.rag-fab-open svg{transform:rotate(90deg);}" +
      "#rag-panel{position:fixed;bottom:92px;right:20px;width:360px;max-width:92vw;height:520px;max-height:75vh;" +
      "background:#fff;border-radius:16px;box-shadow:0 10px 40px rgba(0,0,0,0.25);display:flex;flex-direction:column;" +
      "overflow:hidden;z-index:2147483000;transform-origin:bottom right;" +
      "transform:translateY(16px) scale(0.92);opacity:0;visibility:hidden;pointer-events:none;" +
      "transition:transform .22s cubic-bezier(.34,1.56,.64,1),opacity .18s ease,visibility 0s linear .22s;}" +
      "#rag-panel.rag-open{transform:translateY(0) scale(1);opacity:1;visibility:visible;pointer-events:auto;" +
      "transition:transform .22s cubic-bezier(.34,1.56,.64,1),opacity .18s ease,visibility 0s linear 0s;}" +
      "#rag-header{padding:14px 16px;color:#fff;display:flex;justify-content:space-between;align-items:center;}" +
      "#rag-header .header-text{display:flex;flex-direction:column;gap:2px;}" +
      "#rag-header .title{font-weight:600;font-size:15px;}" +
      ".rag-status{display:flex;align-items:center;gap:5px;font-size:11px;opacity:.85;font-weight:500;}" +
      ".rag-status-dot{width:6px;height:6px;border-radius:50%;background:#fff;}" +
      ".rag-status-online{background:#4ADE80;}" +
      ".rag-status-connecting{background:#FBBF24;animation:ragPulse 1.2s ease-in-out infinite;}" +
      "@keyframes ragPulse{0%,100%{opacity:.4;}50%{opacity:1;}}" +
      ".rag-slow-notice{align-self:flex-start;font-size:11.5px;color:#8b93a7;padding:2px 4px 0;max-width:82%;animation:ragMsgIn .2s ease both;}" +
      "#rag-close{background:none;border:none;color:#fff;font-size:20px;cursor:pointer;line-height:1;opacity:.9;" +
      "border-radius:50%;width:26px;height:26px;display:flex;align-items:center;justify-content:center;" +
      "transition:background .15s ease,transform .15s ease;}" +
      "#rag-close:hover{background:rgba(255,255,255,0.18);}" +
      "#rag-close:active{transform:scale(0.85);}" +
      "#rag-messages{flex:1;overflow-y:auto;padding:14px;background:#f7f7fb;display:flex;flex-direction:column;gap:10px;}" +
      ".rag-msg{max-width:82%;padding:9px 12px;border-radius:14px;font-size:13.5px;line-height:1.45;white-space:pre-wrap;word-wrap:break-word;}" +
      ".rag-msg.user{align-self:flex-end;background:#4F46E5;color:#fff;border-bottom-right-radius:4px;}" +
      ".rag-msg.assistant{align-self:flex-start;background:#fff;color:#222;border:1px solid #e6e6ef;border-bottom-left-radius:4px;}" +
      ".rag-msg-enter{animation:ragMsgIn .25s cubic-bezier(.2,.7,.3,1) both;}" +
      "@keyframes ragMsgIn{from{opacity:0;transform:translateY(8px) scale(0.98);}to{opacity:1;transform:translateY(0) scale(1);}}" +
      ".rag-typing{align-self:flex-start;background:#fff;border:1px solid #e6e6ef;border-radius:14px;" +
      "border-bottom-left-radius:4px;padding:11px 14px;display:flex;gap:4px;align-items:center;animation:ragMsgIn .2s ease both;}" +
      ".rag-typing span{width:6px;height:6px;border-radius:50%;background:#bbb;animation:ragBounce 1.1s ease-in-out infinite;}" +
      ".rag-typing span:nth-child(2){animation-delay:.15s;}" +
      ".rag-typing span:nth-child(3){animation-delay:.3s;}" +
      "@keyframes ragBounce{0%,60%,100%{transform:translateY(0);opacity:.5;}30%{transform:translateY(-4px);opacity:1;}}" +
      ".rag-msg ul,.rag-msg ol{margin:6px 0 10px;padding-left:20px;}" +
      ".rag-msg li{margin-bottom:5px;line-height:1.5;}" +
      ".rag-msg h1,.rag-msg h2,.rag-msg h3,.rag-msg h4,.rag-msg h5,.rag-msg h6{" +
      "font-weight:700;line-height:1.35;color:var(--rag-accent,#4F46E5);letter-spacing:-0.01em;}" +
      ".rag-msg h3{font-size:14.5px;margin-top:12px;padding-bottom:5px;border-bottom:1px solid rgba(0,0,0,0.08);}" +
      ".rag-msg h4{font-size:13.5px;margin-top:10px;}" +
      ".rag-msg h5,.rag-msg h6{font-size:13px;margin-top:8px;}" +
      ".rag-msg.assistant h1,.rag-msg.assistant h2,.rag-msg.assistant h3,.rag-msg.assistant h4,.rag-msg.assistant h5,.rag-msg.assistant h6{margin-top:0;}" +
      ".rag-msg strong{font-weight:700;color:inherit;}" +
      ".rag-msg.assistant strong{color:var(--rag-accent,#4F46E5);}" +
      ".rag-msg p,.rag-msg > div{margin-bottom:6px;}" +
      ".rag-msg code{background:rgba(0,0,0,0.06);padding:1.5px 6px;border-radius:4px;font-family:'SF Mono',Consolas,Monaco,monospace;font-size:12.5px;}" +
      ".rag-msg.user code{background:rgba(255,255,255,0.2);}" +
      ".rag-code-block{background:#161821;color:#e2e4ee;border-radius:8px;padding:11px 13px;" +
      "margin:8px 0;overflow-x:auto;font-family:'SF Mono',Consolas,Monaco,monospace;" +
      "font-size:12px;line-height:1.55;white-space:pre;}" +
      ".rag-code-block code{background:none;padding:0;color:inherit;}" +
      ".rag-code-lang{display:block;font-size:10px;letter-spacing:.05em;text-transform:uppercase;" +
      "color:#8b93a7;margin-bottom:6px;font-family:'SF Mono',Consolas,Monaco,monospace;}" +
      "#rag-input-row{display:flex;border-top:1px solid #eee;padding:10px;gap:8px;background:#fff;}" +
      "#rag-input{flex:1;border:1px solid #ddd;border-radius:20px;padding:9px 14px;font-size:13.5px;outline:none;" +
      "transition:border-color .15s ease,box-shadow .15s ease;}" +
      "#rag-input:focus{border-color:#4F46E5;box-shadow:0 0 0 3px rgba(79,70,229,0.12);}" +
      "#rag-send{border:none;color:#fff;border-radius:20px;padding:0 16px;font-size:13.5px;cursor:pointer;font-weight:600;" +
      "transition:transform .12s ease,filter .12s ease;}" +
      "#rag-send:hover{filter:brightness(1.08);}" +
      "#rag-send:active{transform:scale(0.94);}" +
      "#rag-send:disabled{opacity:.6;cursor:default;transform:none;filter:none;}" +
      "#rag-footer-note{font-size:10.5px;color:#aaa;text-align:center;padding:4px 0 8px;}" +
      "#rag-messages{scroll-behavior:smooth;}" +
      "@media(max-width:480px){#rag-panel{right:10px;left:10px;width:auto;bottom:80px;}#rag-fab{right:16px;bottom:16px;}}" +
      "@media(prefers-reduced-motion:reduce){#rag-fab,#rag-panel,.rag-msg-enter,.rag-typing,.rag-typing span{animation:none!important;transition:none!important;}}";
    document.head.appendChild(style);
  }

  function render() {
    var color = state.config.primary_color || "#4F46E5";
    root.style.setProperty("--rag-accent", color);
    var fabWasOpen = root.querySelector && root.querySelector("#rag-fab.rag-fab-in");

    root.innerHTML =
      '<button id="rag-fab" style="background:' + color + '" aria-label="Open chat">' + chatIconSvg() + "</button>" +
      panelHtml(color);

    var fab = document.getElementById("rag-fab");
    if (fabWasOpen) fab.classList.add("rag-fab-in"); // preserve entrance state across re-renders
    if (state.open) fab.classList.add("rag-fab-open");

    fab.onclick = function () {
      if (state.open) {
        closePanel();
      } else {
        openPanel();
      }
    };

    var panel = document.getElementById("rag-panel");
    var form = document.getElementById("rag-form");
    var input = document.getElementById("rag-input");

    document.getElementById("rag-close").onclick = function () {
      closePanel();
    };
    form.onsubmit = function (e) {
      e.preventDefault();
      sendMessage(input.value);
    };

    if (state.open) {
      panel.classList.add("rag-open");
      scrollToBottom();
      input.focus();
    }
  }

  function openPanel() {
    state.open = true;
    if (state.messages.length === 0) {
      state.messages.push({ role: "assistant", text: state.config.welcome_message });
    }
    render();
  }

  function closePanel() {
    var panel = document.getElementById("rag-panel");
    var fab = document.getElementById("rag-fab");
    if (panel) panel.classList.remove("rag-open"); // triggers the CSS close transition
    if (fab) fab.classList.remove("rag-fab-open");
    state.open = false;
    // Delay the actual re-render (which would otherwise instantly rebuild
    // the panel in its closed state with no transition) until the CSS
    // transition has had time to play.
    setTimeout(function () {
      if (!state.open) render();
    }, 220);
  }

  function panelHtml(color) {
    var msgsHtml = state.messages
      .map(function (m, idx) {
        var content = m.role === "assistant" ? renderMarkdown(m.text) : escapeHtml(m.text);
        var isNewest = idx === state.messages.length - 1;
        var cls = "rag-msg " + m.role + (isNewest ? " rag-msg-enter" : "");
        return '<div class="' + cls + '">' + content + "</div>";
      })
      .join("");
    if (state.loading) {
      msgsHtml += '<div class="rag-typing"><span></span><span></span><span></span></div>';
      if (state.slowNotice) {
        msgsHtml += '<div class="rag-slow-notice">Waking up the assistant — first reply can take a few extra seconds.</div>';
      }
    }
    var statusHtml = state.connecting
      ? '<span class="rag-status"><span class="rag-status-dot rag-status-connecting"></span>Connecting…</span>'
      : '<span class="rag-status"><span class="rag-status-dot rag-status-online"></span>Online</span>';
    return (
      '<div id="rag-panel">' +
      '<div id="rag-header" style="background:' + color + '">' +
      '<span class="header-text">' +
      '<span class="title">' + escapeHtml(state.config.name || "Assistant") + "</span>" +
      statusHtml +
      "</span>" +
      '<button id="rag-close" aria-label="Close chat">&times;</button>' +
      "</div>" +
      '<div id="rag-messages">' + msgsHtml + "</div>" +
      '<form id="rag-form">' +
      '<div id="rag-input-row">' +
      '<input id="rag-input" type="text" placeholder="Type your message…" autocomplete="off" ' +
      (state.loading ? "disabled" : "") + " />" +
      '<button id="rag-send" type="submit" style="background:' + color + '" ' +
      (state.loading ? "disabled" : "") + ">Send</button>" +
      "</div>" +
      '<div id="rag-footer-note">Powered by Advanced RAG Chatbot</div>' +
      "</form>" +
      "</div>"
    );
  }

  function chatIconSvg() {
    return (
      '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">' +
      '<path d="M4 4H20V16H7L4 19V4Z" stroke="white" stroke-width="2" stroke-linejoin="round"/>' +
      "</svg>"
    );
  }

  function escapeHtml(str) {
    var div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // Lightweight, safe markdown renderer: escapes HTML first (so the LLM
  // can never inject real tags/scripts), then converts a small, common
  // subset of markdown syntax into HTML. Good enough for headings, bold,
  // italics, inline code, and bullet/numbered lists coming back from the LLM.
  function renderMarkdown(raw) {
    var escaped = escapeHtml(raw || "");
    var lines = escaped.split("\n");
    var htmlParts = [];
    var listBuffer = [];
    var listType = null; // "ul" | "ol"

    function flushList() {
      if (listBuffer.length) {
        htmlParts.push("<" + listType + ">" + listBuffer.join("") + "</" + listType + ">");
        listBuffer = [];
        listType = null;
      }
    }

    function inline(text) {
      text = text.replace(/`([^`]+)`/g, "<code>$1</code>");
      text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
      text = text.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
      text = text.replace(/(^|[^_])_([^_\n]+)_(?!_)/g, "$1<em>$2</em>");
      return text;
    }

    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];

      // Fenced code block: ```lang ... ``` (escaped, so check the escaped form).
      var fenceMatch = line.match(/^```(\w*)\s*$/);
      if (fenceMatch) {
        flushList();
        var lang = fenceMatch[1];
        var codeLines = [];
        i++;
        while (i < lines.length && !/^```\s*$/.test(lines[i])) {
          codeLines.push(lines[i]);
          i++;
        }
        // i now points at the closing ``` line (or end of message if unterminated).
        var langLabel = lang ? '<span class="rag-code-lang">' + lang + "</span>" : "";
        htmlParts.push('<div class="rag-code-block">' + langLabel + codeLines.join("\n") + "</div>");
        continue;
      }

      var headingMatch = line.match(/^(#{1,4})\s+(.*)$/);
      var bulletMatch = line.match(/^\s*[-*]\s+(.*)$/);
      var numberedMatch = line.match(/^\s*\d+\.\s+(.*)$/);

      if (headingMatch) {
        flushList();
        var level = Math.min(headingMatch[1].length + 2, 6); // ### -> h5, keeps bubble text small
        htmlParts.push("<h" + level + ">" + inline(headingMatch[2]) + "</h" + level + ">");
      } else if (bulletMatch) {
        if (listType !== "ul") { flushList(); listType = "ul"; }
        listBuffer.push("<li>" + inline(bulletMatch[1]) + "</li>");
      } else if (numberedMatch) {
        if (listType !== "ol") { flushList(); listType = "ol"; }
        listBuffer.push("<li>" + inline(numberedMatch[1]) + "</li>");
      } else if (line.trim() === "") {
        flushList();
        htmlParts.push('<div style="height:6px"></div>');
      } else {
        flushList();
        htmlParts.push("<div>" + inline(line) + "</div>");
      }
    }
    flushList();
    return htmlParts.join("");
  }

  function scrollToBottom() {
    var el = document.getElementById("rag-messages");
    if (el) el.scrollTop = el.scrollHeight;
  }

  // ---------- API calls with basic retry/error recovery ----------
  function fetchConfig() {
    fetchWithRetry(API_BASE + "/bots/" + BOT_ID + "/config", { method: "GET" }, 2)
      .then(function (data) {
        state.config = Object.assign(state.config, data);
        state.connecting = false;
        render();
      })
      .catch(function (err) {
        console.warn("[RAG Widget] Could not load bot config, using defaults.", err);
        state.connecting = false;
        render();
      });
  }

  function sendMessage(text) {
    text = (text || "").trim();
    if (!text || state.loading) return;

    state.messages.push({ role: "user", text: text });
    state.loading = true;
    state.slowNotice = false;
    render();

    // If the backend is cold (Railway free tier, first request after idle),
    // the reply can take several seconds. Rather than leave the typing
    // indicator looking stuck, surface a reassuring note after a delay.
    var slowTimer = setTimeout(function () {
      if (state.loading) {
        state.slowNotice = true;
        render();
      }
    }, 4000);

    fetchWithRetry(
      API_BASE + "/chat",
      {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-api-key": API_KEY },
        body: JSON.stringify({ bot_id: BOT_ID, session_id: sessionId, message: text }),
      },
      2
    )
      .then(function (data) {
        state.messages.push({ role: "assistant", text: data.reply || "Sorry, I couldn't generate a response." });
      })
      .catch(function (err) {
        console.error("[RAG Widget] Chat request failed:", err);
        state.messages.push({
          role: "assistant",
          text: "Sorry, something went wrong reaching the assistant. Please try again in a moment.",
        });
      })
      .finally(function () {
        clearTimeout(slowTimer);
        state.loading = false;
        state.slowNotice = false;
        render();
      });
  }

  function fetchWithRetry(url, options, retries) {
    return fetch(url, options)
      .then(function (res) {
        if (!res.ok) {
          return res
            .json()
            .catch(function () {
              return {};
            })
            .then(function (body) {
              throw new Error((body && body.error) || "Request failed with status " + res.status);
            });
        }
        return res.json();
      })
      .catch(function (err) {
        if (retries > 0) {
          return new Promise(function (resolve) {
            setTimeout(resolve, 600);
          }).then(function () {
            return fetchWithRetry(url, options, retries - 1);
          });
        }
        throw err;
      });
  }
})();