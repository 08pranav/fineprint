/* FinePrint web client. Plain JavaScript, no build step.
   HMI rules applied throughout: every action gives feedback, every wait shows progress in words,
   errors sit next to their cause and keep the user's input, the back button works, and
   destructive actions can be undone. */
(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const MIN_CHARS = 120;
  const MAX_CHARS = 60000;
  const MAX_MB = 5;
  const SEVERITY = {
    high: { label: "High risk", icon: "i-high" },
    medium: { label: "Medium risk", icon: "i-medium" },
    low: { label: "Low risk", icon: "i-low" },
  };
  const METHOD_LABEL = { rules: "rules", llm: "the language model", hybrid: "rules and the language model" };
  const LANG_LABEL = { en: "English", hi: "Hindi", mr: "Marathi", hinglish: "Hinglish" };
  const SUGGESTIONS = {
    loan: ["What happens if an EMI bounces?", "Can I close this loan early, and what does it cost?", "mera EMI late hua toh kitna lagega?", "व्याज दर बदलू शकतो का?"],
    credit_card: ["What if I pay only the minimum amount due?", "What is the annual fee?", "late payment pe kitna charge lagega?", "क्या बैंक मेरी लिमिट घटा सकता है?"],
    bnpl: ["Is this EMI really interest-free?", "What happens if I miss one EMI?", "processing fee kitni hai?"],
    insurance: ["How long before I can claim for an existing illness?", "Is there a co-payment?", "policy apne aap renew hogi kya?"],
    subscription: ["How do I cancel?", "Can the price go up?", "mera data kisko share hota hai?"],
  };

  const state = {
    health: null,
    source: "paste",
    file: null,
    sampleId: null,
    samples: [],
    masked: null,          // document text after personal data was hidden
    pii: {},               // how many personal details were hidden, by kind
    analysis: null,        // last /api/analyze response
    docContext: null,      // numbers as found in the document (for reset)
    filters: { high: true, medium: true, low: true },
    level: "standard",
    language: "en",
    chat: [],
    controller: null,
    undo: null,
  };

  // ------------------------------------------------------------------ helpers
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const icon = (id, cls = "icon") => `<svg class="${cls}" aria-hidden="true"><use href="#${id}"/></svg>`;
  // Use the document's own numbering ("Clause 8", "Clause iv"); unnumbered parts get FinePrint's running number.
  const clauseName = (c) => (c ? (c.label ? `Clause ${c.label}` : `Part ${c.number}`) : "this clause");
  const multiPage = () => (state.analysis?.clauses || []).some((c) => (c.page || 1) > 1);
  const plural = (n, one, many) => `${n.toLocaleString("en-IN")} ${n === 1 ? one : many}`;
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* storage blocked: preferences just aren't remembered */ } },
  };

  async function api(path, { method = "GET", json, form, signal, timeout = 90000 } = {}) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort("timeout"), timeout);
    if (signal) signal.addEventListener("abort", () => ctrl.abort("cancelled"), { once: true });
    let res;
    try {
      res = await fetch(path, {
        method,
        headers: json ? { "Content-Type": "application/json" } : undefined,
        body: json ? JSON.stringify(json) : form,
        signal: ctrl.signal,
      });
    } catch (err) {
      if (ctrl.signal.aborted && ctrl.signal.reason === "cancelled") throw Object.assign(new Error("Cancelled."), { cancelled: true });
      if (ctrl.signal.aborted) throw new Error("This is taking too long. Try a shorter document, or try again in a minute.");
      throw new Error("Can't reach FinePrint. Check your internet connection and try again.");
    } finally {
      clearTimeout(timer);
    }
    let body = null;
    try { body = await res.json(); } catch { /* not JSON */ }
    if (!res.ok) {
      const detail = body && typeof body.detail === "string" ? body.detail : null;
      throw new Error(detail || `The server could not do this (error ${res.status}). Try again.`);
    }
    return body;
  }

  function setError(el, message, field) {
    const box = typeof el === "string" ? $(el) : el;
    if (!box) return;
    if (message) {
      box.textContent = message;
      box.hidden = false;
      if (field) field.setAttribute("aria-invalid", "true");
    } else {
      box.textContent = "";
      box.hidden = true;
      if (field) field.removeAttribute("aria-invalid");
    }
  }

  // ------------------------------------------------------------------ navigation (back button works)
  const VIEWS = ["add", "review", "ask"];
  const TITLES = { add: "Add your document", review: "Review risks", ask: "Ask about this document" };

  function show(view, { push = true, focus = true } = {}) {
    if (view !== "add" && !state.analysis) view = "add";
    VIEWS.forEach((v) => { $(`#view-${v}`).hidden = v !== view; });
    $$(".step").forEach((btn) => {
      const v = btn.dataset.step;
      const idx = VIEWS.indexOf(v);
      btn.disabled = v !== "add" && !state.analysis;
      btn.classList.toggle("done", idx < VIEWS.indexOf(view) && !btn.disabled);
      if (v === view) btn.setAttribute("aria-current", "step"); else btn.removeAttribute("aria-current");
    });
    document.title = `${TITLES[view]} · FinePrint`;
    if (push && location.hash !== `#${view}`) history.pushState({ view }, "", `#${view}`);
    if (focus) {
      window.scrollTo({ top: 0 });
      $(`#h-${view}`).focus({ preventScroll: true });
    }
    if (view === "ask") renderSuggestions();
  }

  window.addEventListener("popstate", () => show((location.hash || "#add").slice(1), { push: false }));
  document.addEventListener("click", (e) => {
    const nav = e.target.closest("[data-nav]");
    if (nav) { e.preventDefault(); show(nav.dataset.nav); }
    const step = e.target.closest(".step");
    if (step && !step.disabled) show(step.dataset.step);
  });

  // ------------------------------------------------------------------ step 1: add document
  function setSource(value) {
    state.source = value;
    ["paste", "upload", "sample"].forEach((s) => { $(`#panel-${s}`).hidden = s !== value; });
    setError("#analyse-error-text", null);
    $("#analyse-error").hidden = true;
  }
  $$('input[name="source"]').forEach((r) => r.addEventListener("change", () => setSource(r.value)));

  const docText = $("#doc-text");
  function updateCount() {
    const n = docText.value.trim().length;
    const count = $("#doc-text-count");
    count.textContent = n < MIN_CHARS && n > 0
      ? `${n.toLocaleString("en-IN")} characters · needs at least ${MIN_CHARS}`
      : `${n.toLocaleString("en-IN")} characters`;
    count.classList.toggle("ok", n >= MIN_CHARS && n <= MAX_CHARS);
    $("#clear-text").hidden = n === 0;
    if (!$("#doc-text-error").hidden && n >= MIN_CHARS && n <= MAX_CHARS) setError("#doc-text-error", null, docText);
  }
  docText.addEventListener("input", updateCount);
  docText.addEventListener("blur", () => {
    const n = docText.value.trim().length;
    if (n > 0 && n < MIN_CHARS) setError("#doc-text-error", `This is ${n} characters. Paste the full terms, at least ${MIN_CHARS} characters.`, docText);
  });
  $("#clear-text").addEventListener("click", () => {
    const old = docText.value;
    docText.value = "";
    updateCount();
    docText.focus();
    showUndo("Text cleared.", () => { docText.value = old; updateCount(); docText.focus(); });
  });

  // file upload with checks before anything is sent
  const fileInput = $("#file-input");
  function chooseFile(file) {
    setError("#file-error", null);
    if (!file) return;
    const okType = /\.(pdf|txt)$/i.test(file.name) || ["application/pdf", "text/plain"].includes(file.type);
    if (!okType) return setError("#file-error", `"${file.name}" is not a PDF or .txt file. Choose a PDF or text file, or paste the text instead.`);
    if (file.size > MAX_MB * 1048576) return setError("#file-error", `"${file.name}" is ${(file.size / 1048576).toFixed(1)} MB. The limit is ${MAX_MB} MB.`);
    state.file = file;
    $("#file-name").textContent = file.name;
    $("#file-size").textContent = file.size > 1048576 ? `${(file.size / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(file.size / 1024))} KB`;
    $("#file-chosen").hidden = false;
    $("#drop").hidden = true;
    $("#file-remove").focus();
  }
  fileInput.addEventListener("change", () => chooseFile(fileInput.files[0]));
  $("#file-remove").addEventListener("click", () => {
    state.file = null;
    fileInput.value = "";
    $("#file-chosen").hidden = true;
    $("#drop").hidden = false;
    fileInput.focus();
  });
  const drop = $("#drop");
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("dragging"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, () => drop.classList.remove("dragging")));
  drop.addEventListener("drop", (e) => { e.preventDefault(); chooseFile(e.dataTransfer.files[0]); });

  async function loadSamples() {
    const list = $("#sample-list");
    try {
      state.samples = await api("/api/samples");
      list.innerHTML = state.samples.map((s) => `
        <label class="sample">
          <input type="radio" name="sample" value="${esc(s.id)}">
          <span class="sample-title">${esc(s.title)}</span>
          <span class="sample-desc">${esc(s.description)}</span>
        </label>`).join("");
      $$('input[name="sample"]', list).forEach((r) => r.addEventListener("change", () => {
        state.sampleId = r.value;
        setError("#sample-error", null);
      }));
    } catch (err) {
      list.innerHTML = `<p class="field-error">Samples could not be loaded. ${esc(err.message)}</p>`;
    }
  }

  function validateSource() {
    if (state.source === "paste") {
      const n = docText.value.trim().length;
      if (n === 0) return { el: "#doc-text-error", field: docText, msg: "Paste the document text first." };
      if (n < MIN_CHARS) return { el: "#doc-text-error", field: docText, msg: `This is ${n} characters. Paste the full terms, at least ${MIN_CHARS} characters.` };
      if (n > MAX_CHARS) return { el: "#doc-text-error", field: docText, msg: `This is ${n.toLocaleString("en-IN")} characters; the limit is ${MAX_CHARS.toLocaleString("en-IN")}. Paste the fees and charges section first.` };
    }
    if (state.source === "upload" && !state.file) return { el: "#file-error", field: fileInput, msg: "Choose a PDF or text file first." };
    if (state.source === "sample" && !state.sampleId) {
      return { el: "#sample-error", field: $('input[name="sample"]'), msg: "Pick one of the samples first." };
    }
    return null;
  }

  function setAnalysing(on, text = "") {
    const btn = $("#analyse-btn");
    btn.disabled = on;
    btn.setAttribute("aria-busy", String(on));
    btn.textContent = on ? "Analysing…" : "Analyse document";
    $("#cancel-btn").hidden = !on;
    $("#analyse-status").hidden = !on;
    $(".spinner", $("#analyse-status")).hidden = !on;
    $("#analyse-status-text").textContent = text;
    $$('input[name="source"]').forEach((r) => { r.disabled = on; });
  }

  async function analyse() {
    $("#analyse-error").hidden = true;
    const problem = validateSource();
    if (problem) {
      setError(problem.el, problem.msg, problem.field);
      (problem.field || $(problem.el)).focus();
      return;
    }
    state.controller = new AbortController();
    const signal = state.controller.signal;
    try {
      setAnalysing(true, "Reading the document…");
      let extracted;
      if (state.source === "upload") {
        const form = new FormData();
        form.append("file", state.file);
        setAnalysing(true, `Uploading ${state.file.name}…`);
        extracted = await api("/api/extract", { method: "POST", form, signal });
      } else {
        let text = docText.value;
        if (state.source === "sample") {
          text = (await api(`/api/samples/${encodeURIComponent(state.sampleId)}`, { signal })).text;
        }
        const form = new FormData();
        form.append("text", text);
        extracted = await api("/api/extract", { method: "POST", form, signal });
      }
      const hidden = Object.values(extracted.pii_masked || {}).reduce((a, b) => a + b, 0);
      setAnalysing(true, `Found ${plural(extracted.clause_count, "clause", "clauses")}${hidden ? ` and hid ${plural(hidden, "personal detail", "personal details")}` : ""}. Checking each clause for risks…`);
      const analysis = await api("/api/analyze", {
        method: "POST", signal, timeout: 180000,
        json: { text: extracted.text, level: state.level, language: state.language },
      });
      state.masked = extracted.text;
      state.pii = extracted.pii_masked || {};
      state.analysis = analysis;
      state.docContext = { ...analysis.context };
      state.chat = [];
      state.undo = null;
      $("#undo-notice").hidden = true;
      $("#chat").innerHTML = "";
      setAnalysing(false);
      renderReview();
      show("review");
    } catch (err) {
      setAnalysing(false);
      if (err.cancelled) {
        $("#analyse-status").hidden = false;
        $("#analyse-status-text").textContent = "Cancelled. Your document is still here.";
        return;
      }
      $("#analyse-error-text").textContent = err.message;
      $("#analyse-error").hidden = false;
      $("#analyse-btn").focus();
    } finally {
      state.controller = null;
    }
  }
  $("#analyse-btn").addEventListener("click", analyse);
  $("#cancel-btn").addEventListener("click", () => state.controller && state.controller.abort());

  // ------------------------------------------------------------------ step 2: review
  function docLabel(type) {
    return { loan: "loan agreement", credit_card: "credit card terms", bnpl: "EMI offer", insurance: "insurance policy", subscription: "subscription terms" }[type] || "document";
  }

  function renderReview() {
    const a = state.analysis;
    const n = a.flags.length;
    const these = { credit_card: "these credit card terms", subscription: "these subscription terms" }[a.doc_type] || `this ${docLabel(a.doc_type)}`;
    $("#h-review").textContent = n ? `${plural(n, "thing", "things")} to check in ${these}` : `No risky clauses found in ${these}`;
    const hidden = Object.values(state.pii || {}).reduce((x, y) => x + y, 0);
    $("#review-meta").textContent = [
      `${plural(a.summary.clauses, "clause", "clauses")} read`,
      hidden ? `${plural(hidden, "personal detail", "personal details")} hidden` : "no personal details found",
      `checked by ${METHOD_LABEL[a.method]}`,
    ].join(" · ");
    renderWarnings(a.warnings);
    renderFilters();
    renderFlags();
    renderClauses();
    renderNumbers();
    applyLanguageAvailability();
  }

  function renderWarnings(list) {
    $("#review-warnings").innerHTML = (list || []).map((w) => `
      <div class="notice notice-info">${icon("i-info")}<p>${esc(w)}</p></div>`).join("");
  }

  function renderFilters() {
    const s = state.analysis.summary;
    $("#filters").innerHTML = ["high", "medium", "low"].map((sev) => `
      <button type="button" class="chip chip-${sev}" data-sev="${sev}" aria-pressed="${state.filters[sev]}">
        ${icon("i-check", "icon tick")}${icon(SEVERITY[sev].icon)}${esc(SEVERITY[sev].label.replace(" risk", ""))} (${s[sev]})
      </button>`).join("");
    $$("#filters .chip").forEach((chip) => chip.addEventListener("click", () => {
      const sev = chip.dataset.sev;
      state.filters[sev] = !state.filters[sev];
      chip.setAttribute("aria-pressed", String(state.filters[sev]));
      applyFilters();
    }));
  }

  function applyFilters() {
    let visible = 0;
    $$("#flags > li[data-sev]").forEach((li) => {
      li.hidden = !state.filters[li.dataset.sev];
      if (!li.hidden) visible += 1;
    });
    const none = $("#flags-none");
    if (none) none.hidden = visible > 0 || !state.analysis.flags.length;
  }

  function impactHTML(f) {
    if (!f.impact) return "";
    const fig = f.impact.amount !== null && f.impact.amount !== undefined;
    return `<p class="impact${fig ? "" : " no-figure"}" data-impact="${esc(f.id)}">${esc(f.impact.headline)}</p>`;
  }

  function howHTML(f) {
    if (!f.impact || f.impact.amount === null || f.impact.amount === undefined) return "";
    const items = [f.impact.basis, ...(f.impact.assumptions || [])].filter(Boolean);
    return `<details><summary>How this was worked out</summary>
      <div class="detail-body"><ul>${items.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
      <p class="muted">Calculated by FinePrint's formulas, not by the language model.</p></div></details>`;
  }

  function flagHTML(f) {
    const clause = state.analysis.clauses.find((c) => c.id === f.clause_id);
    const sev = SEVERITY[f.severity];
    const foundBy = f.found_by.length === 2 ? "Found by rules and the language model" : f.found_by[0] === "rules" ? "Found by rules" : "Found by the language model; quote checked against the document";
    const kb = f.kb ? `<details><summary>Why this matters</summary><div class="detail-body">
        <p><strong>${esc(f.kb.title)}.</strong> ${esc(f.kb.body)}</p>
        <p class="muted">Source: <a href="${esc(f.kb.source_url)}" target="_blank" rel="noopener">${esc(f.kb.source_name)}<span class="sr-only"> (opens in a new tab)</span>${icon("i-external", "icon icon-xs")}</a></p>
      </div></details>` : "";
    return `
      <li data-sev="${esc(f.severity)}" id="flag-${esc(f.id)}">
        <article class="flag" aria-labelledby="flag-title-${esc(f.id)}">
          <div class="flag-head">
            <span class="badge badge-${esc(f.severity)}">${icon(sev.icon)}${esc(sev.label)}</span>
            <h3 id="flag-title-${esc(f.id)}">${esc(f.category_label)}</h3>
          </div>
          ${impactHTML(f)}
          <p class="explanation" data-expl="${esc(f.id)}">${esc(f.explanation)}</p>
          <blockquote class="quote">
            ${esc(f.quote)}
            <div class="quote-meta">
              <span>${esc(clauseName(clause))}${clause && multiPage() ? `, page ${clause.page}` : ""}</span>
              <span aria-hidden="true">·</span>
              <button type="button" class="btn-text btn" data-goto="${esc(f.clause_id)}">Show in document</button>
            </div>
          </blockquote>
          ${howHTML(f)}
          ${kb}
          <div class="flag-actions">
            <button type="button" class="btn btn-text" data-askabout="${esc(f.clause_id)}">${icon("i-chat")}Ask about this clause</button>
            <span class="found-by">${esc(foundBy)}</span>
          </div>
        </article>
      </li>`;
  }

  function renderFlags() {
    const a = state.analysis;
    const list = $("#flags");
    if (!a.flags.length) {
      list.innerHTML = `<li class="empty">
        <h2>Nothing risky found in ${plural(a.summary.clauses, "clause", "clauses")}</h2>
        <p>That does not guarantee there are no risks: unusual wording can be missed. Read the whole document below, or ask a question about anything you are unsure of.</p>
      </li>`;
      return;
    }
    list.innerHTML = a.flags.map(flagHTML).join("") +
      `<li class="empty" id="flags-none" hidden><p>All risk levels are hidden. Turn one back on under "Show".</p></li>`;
    applyFilters();
  }

  function renderClauses() {
    const a = state.analysis;
    const flagsBy = {};
    a.flags.forEach((f) => { (flagsBy[f.clause_id] = flagsBy[f.clause_id] || []).push(f); });
    $("#full-doc-count").textContent = `(${plural(a.clauses.length, "clause", "clauses")})`;
    let lastHead = null;
    $("#clauses").innerHTML = a.clauses.map((c) => {
      const fl = flagsBy[c.id] || [];
      const head = c.heading && c.heading !== lastHead ? `<li class="clause-head" aria-hidden="false">${esc(c.heading)}</li>` : "";
      lastHead = c.heading || lastHead;
      const tags = fl.length ? `<div class="clause-tags">${fl.map((f) => `<span class="badge badge-${esc(f.severity)}">${icon(SEVERITY[f.severity].icon)}${esc(f.category_label)}</span>`).join("")}</div>` : "";
      return `${head}<li class="clause${fl.length ? " flagged" : ""}" id="clause-${esc(c.id)}" tabindex="-1">
        <span class="clause-num">${esc(clauseName(c).replace("Clause ", ""))}</span><div>${esc(c.text)}${tags}</div></li>`;
    }).join("");
  }

  function goToClause(cid) {
    if ($("#view-review").hidden) show("review", { focus: false });
    const details = $("#full-doc");
    details.open = true;
    $$(".clause.target").forEach((el) => el.classList.remove("target"));
    const el = $(`#clause-${CSS.escape(cid)}`);
    if (!el) return;
    el.classList.add("target");
    el.scrollIntoView({ block: "center", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    el.focus({ preventScroll: true });
  }

  $("#flags").addEventListener("click", (e) => {
    const go = e.target.closest("[data-goto]");
    if (go) goToClause(go.dataset.goto);
    const ask = e.target.closest("[data-askabout]");
    if (ask) {
      const c = state.analysis.clauses.find((x) => x.id === ask.dataset.askabout);
      show("ask");
      const q = $("#question");
      q.value = `What does ${clauseName(c).toLowerCase()} mean for me?`;
      q.focus();
      q.setSelectionRange(q.value.length, q.value.length);
    }
  });

  // level and language
  function applyLanguageAvailability() {
    const noModel = !state.analysis?.model_used && state.health?.mode !== "hybrid";
    $$("#language option").forEach((o) => {
      if (o.value !== "en") {
        o.disabled = noModel;
        o.textContent = o.textContent.replace(" — needs language model", "") + (noModel ? " — needs language model" : "");
      }
    });
    $("#language-note").hidden = !noModel;
    if (noModel && state.language !== "en") { state.language = "en"; $("#language").value = "en"; }
  }

  async function reExplain(prev) {
    const status = $("#explain-status");
    const list = $("#flags");
    status.hidden = false;
    $("#explain-status-text").textContent = `Rewriting explanations: ${state.level} level, ${LANG_LABEL[state.language]}…`;
    list.setAttribute("aria-busy", "true");
    try {
      const r = await api("/api/explain", { method: "POST", json: { flags: state.analysis.flags, context: state.analysis.context, level: state.level, language: state.language } });
      state.analysis.flags = r.flags;
      state.analysis.warnings = r.warnings;
      r.flags.forEach((f) => { const p = $(`[data-expl="${CSS.escape(f.id)}"]`); if (p) p.textContent = f.explanation; });
      renderWarnings(r.warnings);
      $("#explain-status-text").textContent = "Explanations updated.";
      store.set("fp-level", state.level);
      store.set("fp-language", state.language);
      setTimeout(() => { status.hidden = true; }, 2500);
    } catch (err) {
      Object.assign(state, prev);
      $(`input[name="level"][value="${prev.level}"]`).checked = true;
      $("#language").value = prev.language;
      status.hidden = true;
      renderWarnings([...(state.analysis.warnings || []), `Explanations were not changed: ${err.message}`]);
    } finally {
      list.removeAttribute("aria-busy");
    }
  }
  $$('input[name="level"]').forEach((r) => r.addEventListener("change", () => {
    const prev = { level: state.level, language: state.language };
    state.level = r.value;
    if (state.analysis) reExplain(prev);
  }));
  $("#language").addEventListener("change", (e) => {
    const prev = { level: state.level, language: state.language };
    state.language = e.target.value;
    if (state.analysis) reExplain(prev);
  });

  // your numbers -> live recalculation (deterministic, fast)
  const NUM_FIELDS = [
    { key: "principal", input: "#n-principal", src: "#s-principal", err: "#e-principal", min: 0, max: 1e9, name: "Amount" },
    { key: "annual_rate", input: "#n-rate", src: "#s-rate", err: "#e-rate", min: 0, max: 100, name: "Interest rate" },
    { key: "tenure_months", input: "#n-tenure", src: "#s-tenure", err: "#e-tenure", min: 1, max: 480, name: "Tenure", integer: true },
    { key: "emi", input: "#n-emi", src: "#s-emi", err: "#e-emi", min: 0, max: 1e8, name: "EMI" },
  ];

  function renderNumbers() {
    const ctx = state.analysis.context;
    $("#principal-name").textContent = { credit_card: "Credit limit", bnpl: "Purchase amount", insurance: "Sum insured", subscription: "Amount" }[state.analysis.doc_type] || "Loan amount";
    const sources = state.docContext.sources || {};
    NUM_FIELDS.forEach((f) => {
      const input = $(f.input);
      input.value = ctx[f.key] ?? "";
      setError(f.err, null, input);
      const clauseId = sources[f.key];
      const clause = clauseId && state.analysis.clauses.find((c) => c.id === clauseId);
      $(f.src).textContent = ctx[f.key] == null
        ? "Not in the document. Add it to see more rupee figures."
        : clause && state.docContext[f.key] === ctx[f.key] ? `From ${clauseName(clause).toLowerCase()}` : "Changed by you";
    });
    $("#numbers-status").textContent = "";
  }

  function readNumbers() {
    const ctx = { ...state.analysis.context };
    let ok = true;
    NUM_FIELDS.forEach((f) => {
      const input = $(f.input);
      const raw = input.value.trim();
      if (raw === "") { ctx[f.key] = null; setError(f.err, null, input); return; }
      const v = Number(raw);
      let msg = null;
      if (!Number.isFinite(v)) msg = `${f.name} must be a number.`;
      else if (v < f.min || v > f.max) msg = `${f.name} must be between ${f.min.toLocaleString("en-IN")} and ${f.max.toLocaleString("en-IN")}.`;
      else if (f.integer && !Number.isInteger(v)) msg = `${f.name} must be a whole number of months.`;
      setError(f.err, msg, input);
      if (msg) ok = false; else ctx[f.key] = f.integer ? Math.round(v) : v;
    });
    return ok ? ctx : null;
  }

  let recalcTimer = null;
  async function recalc(message = "Rupee figures updated.") {
    const ctx = readNumbers();
    const status = $("#numbers-status");
    status.classList.remove("error");
    if (!ctx) { status.textContent = "Fix the highlighted number to update the figures."; status.classList.add("error"); return; }
    status.textContent = "Updating rupee figures…";
    try {
      const before = Object.fromEntries(state.analysis.flags.map((f) => [f.id, f.impact && f.impact.headline]));
      const r = await api("/api/recalculate", { method: "POST", json: { text: state.masked, context: ctx, flags: state.analysis.flags, level: state.level } });
      state.analysis.flags = r.flags;
      state.analysis.context = ctx;
      let changed = 0;
      r.flags.forEach((f) => {
        const p = $(`[data-impact="${CSS.escape(f.id)}"]`);
        if (p && f.impact && before[f.id] !== f.impact.headline) {
          p.textContent = f.impact.headline;
          p.classList.toggle("no-figure", f.impact.amount == null);
          p.classList.add("changed");
          changed += 1;
        }
        const e = $(`[data-expl="${CSS.escape(f.id)}"]`);
        if (e) e.textContent = f.explanation;
      });
      renderNumbers();
      status.textContent = changed ? `${message} ${plural(changed, "figure", "figures")} changed.` : "No figures depend on that number.";
      if (r.warnings.length) renderWarnings([...(state.analysis.warnings || []), ...r.warnings]);
    } catch (err) {
      status.textContent = `Could not update: ${err.message}`;
      status.classList.add("error");
    }
  }
  NUM_FIELDS.forEach((f) => $(f.input).addEventListener("input", () => {
    clearTimeout(recalcTimer);
    $$(".impact.changed").forEach((el) => el.classList.remove("changed"));
    recalcTimer = setTimeout(() => recalc(), 600);
  }));
  $("#numbers-jump").addEventListener("click", (e) => {
    e.preventDefault();
    $("#numbers").scrollIntoView({ block: "start" });
    $("#n-principal").focus({ preventScroll: true });
  });
  $("#numbers").addEventListener("submit", (e) => { e.preventDefault(); recalc(); });
  $("#numbers-reset").addEventListener("click", () => {
    NUM_FIELDS.forEach((f) => { $(f.input).value = state.docContext[f.key] ?? ""; });
    recalc("Back to the document's numbers.");
  });

  // report download
  $("#download-btn").addEventListener("click", () => {
    const a = state.analysis;
    const date = new Date().toISOString().slice(0, 10);
    const lines = [
      `# FinePrint report: ${docLabel(a.doc_type)}`, "",
      `Date: ${date}. ${a.summary.clauses} clauses read; checked by ${METHOD_LABEL[a.method]}.`,
      `High risk: ${a.summary.high}. Medium: ${a.summary.medium}. Low: ${a.summary.low}.`, "",
      "## Numbers used",
      `Amount: ${a.context.principal ?? "not given"} · Rate: ${a.context.annual_rate ?? "not given"}% a year · Tenure: ${a.context.tenure_months ?? "not given"} months · EMI: ${a.context.emi ?? "not given"}`, "",
      "## What to check", "",
    ];
    a.flags.forEach((f, i) => {
      const c = a.clauses.find((x) => x.id === f.clause_id);
      lines.push(`### ${i + 1}. ${f.category_label} (${SEVERITY[f.severity].label})`, "");
      if (f.impact) lines.push(`**${f.impact.headline}**`, "");
      lines.push(f.explanation, "", `> ${f.quote}`, `> (${clauseName(c)})`, "");
    });
    lines.push("---", "FinePrint explains documents. It is not financial advice. Confirm important terms with the lender in writing.");
    const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
    const link = document.createElement("a");
    const name = `fineprint-report-${date}.md`;
    link.href = URL.createObjectURL(blob);
    link.download = name;
    document.body.appendChild(link);
    link.click();
    setTimeout(() => { URL.revokeObjectURL(link.href); link.remove(); }, 1000);
    $("#download-status").textContent = `Report downloaded as ${name}.`;
  });

  // start over, with undo instead of a confirmation dialog
  function showUndo(text, restore) {
    state.undo = restore;
    $("#undo-notice p").textContent = text;
    $("#undo-notice").hidden = false;
  }
  $("#undo-btn").addEventListener("click", () => {
    const restore = state.undo;
    state.undo = null;
    $("#undo-notice").hidden = true;
    if (restore) restore();
  });
  $("#start-over").addEventListener("click", () => {
    const snapshot = { masked: state.masked, pii: state.pii, analysis: state.analysis, docContext: state.docContext, chat: $("#chat").innerHTML };
    state.masked = null;
    state.analysis = null;
    state.docContext = null;
    $("#chat").innerHTML = "";
    $("#question").value = "";
    show("add");
    showUndo("The previous document and its results were cleared.", () => {
      Object.assign(state, { masked: snapshot.masked, pii: snapshot.pii, analysis: snapshot.analysis, docContext: snapshot.docContext });
      $("#chat").innerHTML = snapshot.chat;
      renderReview();
      show("review");
    });
  });

  // ------------------------------------------------------------------ step 3: ask
  function renderSuggestions() {
    const type = state.analysis?.doc_type || "loan";
    const qs = SUGGESTIONS[type] || SUGGESTIONS.loan;
    $("#suggestions").innerHTML = qs.map((q) => `<button type="button" class="chip" data-q="${esc(q)}">${esc(q)}</button>`).join("");
    $("#suggestions-wrap").hidden = $("#chat").children.length > 2;
  }
  $("#suggestions").addEventListener("click", (e) => {
    const chip = e.target.closest("[data-q]");
    if (!chip) return;
    $("#question").value = chip.dataset.q;
    ask();
  });

  function citeHTML(text, cited) {
    const byId = Object.fromEntries((state.analysis?.clauses || []).map((c) => [c.id, c]));
    return esc(text).replace(/\[(C\d+)\]/g, (m, id) => byId[id] ? `<button type="button" class="cite" data-goto="${id}">${esc(clauseName(byId[id]))}</button>` : "");
  }

  function addMessage(html, cls) {
    const li = document.createElement("li");
    li.className = `msg ${cls}`;
    li.innerHTML = html;
    $("#chat").appendChild(li);
    return li;
  }

  let asking = false;
  async function ask(retryText) {
    if (asking) return;
    const q = $("#question");
    const question = (retryText ?? q.value).trim();
    if (question.length < 3) {
      setError("#question-error", "Type a question of at least a few words.", q);
      q.focus();
      return;
    }
    if (question.length > 500) {
      setError("#question-error", `Keep the question under 500 characters (it is ${question.length}).`, q);
      q.focus();
      return;
    }
    setError("#question-error", null, q);
    asking = true;
    const btn = $("#ask-btn");
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
    if (!retryText) addMessage(`<p class="msg-who">You</p><p class="msg-text">${esc(question)}</p>`, "msg-user");
    q.value = "";
    const pending = addMessage(`<p class="msg-who">FinePrint</p><p class="progress"><span class="spinner" aria-hidden="true"></span>Looking through the document…</p>`, "msg-bot");
    pending.setAttribute("aria-busy", "true");
    pending.scrollIntoView({ block: "nearest" });
    try {
      const r = await api("/api/ask", { method: "POST", json: { question, text: state.masked } });
      const meta = [`Asked in ${LANG_LABEL[r.detected_language] || r.detected_language}`];
      if (r.cited_clauses.length) meta.push(`quotes ${plural(r.cited_clauses.length, "clause", "clauses")}`);
      if (r.abstained) meta.push("not found in the document");
      pending.innerHTML = `<p class="msg-who">FinePrint <span class="muted">· ${esc(meta.join(" · "))}</span></p>
        <p class="msg-text">${citeHTML(r.answer, r.cited_clauses)}</p>
        ${(r.warnings || []).map((w) => `<p class="msg-note">${esc(w)}</p>`).join("")}`;
    } catch (err) {
      pending.classList.add("msg-error");
      pending.innerHTML = `<p class="msg-who">FinePrint</p><p class="msg-text">${icon("i-error")} Your question was not answered. ${esc(err.message)}</p>
        <div><button type="button" class="btn btn-secondary" data-retry>Try again</button></div>`;
      $("[data-retry]", pending).addEventListener("click", () => { pending.remove(); ask(question); });
      if (!q.value) q.value = question;
    } finally {
      pending.removeAttribute("aria-busy");
      btn.disabled = false;
      btn.removeAttribute("aria-busy");
      asking = false;
      $("#suggestions-wrap").hidden = $("#chat").children.length > 2;
    }
  }
  $("#ask-form").addEventListener("submit", (e) => { e.preventDefault(); ask(); });
  $("#question").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); ask(); }
  });
  $("#question").addEventListener("input", () => { if (!$("#question-error").hidden) setError("#question-error", null, $("#question")); });
  $("#chat").addEventListener("click", (e) => {
    const go = e.target.closest("[data-goto]");
    if (go) goToClause(go.dataset.goto);
  });

  // ------------------------------------------------------------------ start
  async function init() {
    const savedLevel = store.get("fp-level");
    const savedLang = store.get("fp-language");
    if (["simple", "standard", "expert"].includes(savedLevel)) { state.level = savedLevel; $(`input[name="level"][value="${savedLevel}"]`).checked = true; }
    if (["en", "hi", "mr", "hinglish"].includes(savedLang)) { state.language = savedLang; $("#language").value = savedLang; }
    updateCount();
    show((location.hash || "#add").slice(1), { push: false, focus: false });
    if (location.hash && location.hash !== "#add" && !state.analysis) history.replaceState({ view: "add" }, "", "#add");
    loadSamples();
    try {
      state.health = await api("/api/health", { timeout: 15000 });
      $("#mode").textContent = state.health.mode === "hybrid" ? "Rules + language model" : "Rules only (no language model)";
      $("#mode").title = state.health.model ? `Model: ${state.health.model}` : "Set LLM_API_KEY and LLM_MODEL on the server to enable the language model.";
    } catch {
      $("#mode").textContent = "Server not reachable";
    }
    if (state.health?.mode !== "hybrid" && state.language !== "en") { state.language = "en"; $("#language").value = "en"; }
  }
  init();
})();
