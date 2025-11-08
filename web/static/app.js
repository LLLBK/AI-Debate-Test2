const tabButtons = document.querySelectorAll(".tab-button");
const viewPanels = document.querySelectorAll(".view-panel");
const trainerResetButtons = document.querySelectorAll("[data-reset-trainer]");

const form = document.querySelector("#debate-form");
const judgeGrid = document.querySelector(".judges-grid");
const judgeTemplate = document.querySelector("#judge-template");
const addJudgeButton = document.querySelector("#add-judge");
const saveButton = document.querySelector("#save-debate");
const statusBar = document.querySelector("#status-bar");
const statusIcon = document.querySelector(".status-icon");
const statusText = document.querySelector("#status-text");
const output = document.querySelector("#debate-output");
const summaryGrid = document.querySelector("#summary-grid");
const timeline = document.querySelector("#timeline");
const judgeTable = document.querySelector("#judge-table");
const toast = document.querySelector("#toast");

const hostNameInput = document.querySelector("#host-name");
const hostEndpointInput = document.querySelector("#host-endpoint");
const debater1NameInput = document.querySelector("#debater1-name");
const debater1EndpointInput = document.querySelector("#debater1-endpoint");
const debater2NameInput = document.querySelector("#debater2-name");
const debater2EndpointInput = document.querySelector("#debater2-endpoint");

const LLM_PRESETS = {
  openai: {
    api_url: "https://api.openai.com/v1/chat/completions",
    model: "gpt-4o-mini",
    temperature: 0.7,
    max_tokens: null,
    timeout_seconds: 30,
    force_json: false,
  },
  deepseek_chat: {
    api_url: "https://api.deepseek.com/v1/chat/completions",
    model: "deepseek-chat",
    temperature: 0.6,
    max_tokens: null,
    timeout_seconds: 30,
    force_json: false,
  },
  deepseek_reasoner: {
    api_url: "https://api.deepseek.com/v1/chat/completions",
    model: "deepseek-reasoner",
    temperature: 0.2,
    max_tokens: null,
    timeout_seconds: 45,
    force_json: true,
  },
  custom: {},
};

const personaCatalog = {
  hosts: [],
  debaters: [],
  judges: [],
};

function buildTrainer(type, defaults) {
  return {
    type,
    defaults,
    selector: document.querySelector(`#${type}-persona-select`),
    fields: {
      name: document.querySelector(`#${type}-name-input`),
      prompt: document.querySelector(`#${type}-prompt`),
      preset: document.querySelector(`#${type}-llm-preset`),
      apiUrl: document.querySelector(`#${type}-api-url`),
      model: document.querySelector(`#${type}-model`),
      apiKey: document.querySelector(`#${type}-api-key`),
      temperature: document.querySelector(`#${type}-temperature`),
      maxTokens: document.querySelector(`#${type}-max-tokens`),
      timeout: document.querySelector(`#${type}-timeout`),
      forceJson: document.querySelector(`#${type}-force-json`),
      extraHeaders: document.querySelector(`#${type}-extra-headers`),
      notes: document.querySelector(`#${type}-notes`),
    },
    endpointField: document.querySelector(`#${type}-endpoint-value`),
    copyButton: document.querySelector(`#${type}-copy-endpoint`),
    applyButton: document.querySelector(`#${type}-apply-btn`),
    saveButton: document.querySelector(`#${type}-save-btn`),
    deleteButton: document.querySelector(`#${type}-delete-btn`),
    slotSelect: document.querySelector(`#${type}-slot-select`) || null,
    currentDetail: null,
    currentId: null,
    suppressPresetChange: false,
  };
}

const personaTrainers = {
  host: buildTrainer("host", { preset: "deepseek_chat", forceJson: false }),
  debater: buildTrainer("debater", { preset: "openai", forceJson: false }),
  judge: buildTrainer("judge", { preset: "deepseek_reasoner", forceJson: true }),
};

const TRAINER_LABELS = {
  host: "主持人",
  debater: "辩手",
  judge: "评委",
};

const HOST_STAGE_LABELS = {
  introduction: "主持人开场",
  pre_cross_examination: "串场：交叉质询前",
  mid_cross_examination: "串场：交叉质询中场",
  pre_free_debate: "串场：自由辩论前",
  pre_closing: "串场：总结前",
  pre_judging: "串场：请评委投票",
  wrap_up: "串场：赛果公布",
};

let currentDebate = null;
let isRequestInFlight = false;
let judgePresets = [];
let judgePresetCursor = 0;
let streamAbortController = null;

const MIN_JUDGES = Number((judgeGrid && judgeGrid.dataset && judgeGrid.dataset.min) || 5);
const MAX_JUDGES = 12;

tabButtons.forEach((button) => {
  button.addEventListener("click", (event) => {
    event.preventDefault();
    const target = button.dataset.viewTarget;
    switchView(target);
  });
});

trainerResetButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const type = button.dataset.resetTrainer;
    resetTrainerForm(type);
  });
});

Object.values(personaTrainers).forEach((trainer) => {
  if (trainer.selector) {
    trainer.selector.addEventListener("change", () => handleTrainerSelection(trainer));
  }
  if (trainer.fields.preset) {
    trainer.fields.preset.addEventListener("change", () => handlePresetChange(trainer));
  }
  if (trainer.saveButton) {
    trainer.saveButton.addEventListener("click", () => persistTrainer(trainer));
  }
  if (trainer.deleteButton) {
    trainer.deleteButton.addEventListener("click", () => deleteTrainer(trainer));
  }
  if (trainer.copyButton) {
    trainer.copyButton.addEventListener("click", () => {
      if (!trainer.currentDetail || !trainer.currentDetail.endpoint) {
        showToast("请先保存角色以生成 Endpoint。", "info");
        return;
      }
      copyToClipboard(trainer.currentDetail.endpoint);
    });
  }
  if (trainer.applyButton) {
    trainer.applyButton.addEventListener("click", () => applyPersonaToDebate(trainer));
  }
});

function switchView(target) {
  if (!target) return;
  tabButtons.forEach((button) => {
    const isActive = button.dataset.viewTarget === target;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", String(isActive));
  });
  viewPanels.forEach((panel) => {
    const isActive = panel.dataset.viewPanel === target;
    panel.classList.toggle("active", isActive);
    panel.hidden = !isActive;
  });
}

function resetTrainerForm(type) {
  const trainer = personaTrainers[type];
  if (!trainer) return;
  trainer.currentDetail = null;
  trainer.currentId = null;
  if (trainer.selector) {
    trainer.selector.value = "";
  }
  trainer.fields.name.value = "";
  trainer.fields.prompt.value = "";
  trainer.fields.apiUrl.value = "";
  trainer.fields.model.value = "";
  trainer.fields.apiKey.value = "";
  const presetDefaults = LLM_PRESETS[trainer.defaults.preset] || {};
  const resolvedTemperature =
    typeof trainer.defaults.temperature !== "undefined"
      ? trainer.defaults.temperature
      : presetDefaults.temperature;
  trainer.fields.temperature.value =
    typeof resolvedTemperature === "number" ? resolvedTemperature : 0.7;
  trainer.fields.maxTokens.value = "";
  const resolvedTimeout =
    typeof trainer.defaults.timeout !== "undefined"
      ? trainer.defaults.timeout
      : presetDefaults.timeout_seconds;
  trainer.fields.timeout.value =
    typeof resolvedTimeout === "number" ? resolvedTimeout : 30;
  trainer.fields.forceJson.checked = Boolean(trainer.defaults.forceJson);
  trainer.fields.extraHeaders.value = "";
  trainer.fields.notes.value = "";
  trainer.suppressPresetChange = true;
  trainer.fields.preset.value = trainer.defaults.preset || "custom";
  trainer.suppressPresetChange = false;
  applyPresetValues(trainer, trainer.fields.preset.value);
  setTrainerEndpoint(trainer, null);
  toggleTrainerButtons(trainer, false);
}

function handleTrainerSelection(trainer) {
  const personaId = trainer.selector ? trainer.selector.value : "";
  if (!personaId) {
    resetTrainerForm(trainer.type);
    return;
  }
  fetch(`/api/personas/${trainer.type}/${personaId}`)
    .then((response) => {
      if (!response.ok) throw new Error("加载角色失败。");
      return response.json();
    })
    .then((detail) => {
      trainer.currentDetail = detail;
      trainer.currentId = detail.id;
      fillTrainerFromDetail(trainer, detail);
      toggleTrainerButtons(trainer, true);
    })
    .catch((error) => {
      showToast(error.message, "error");
    });
}

function fillTrainerFromDetail(trainer, detail) {
  trainer.fields.name.value = detail.name || "";
  trainer.fields.prompt.value = detail.system_prompt || "";
  const llm = detail.llm || {};
  trainer.fields.apiUrl.value = llm.api_url || "";
  trainer.fields.model.value = llm.model || "";
  trainer.fields.apiKey.value = llm.api_key || "";
  trainer.fields.temperature.value =
    typeof llm.temperature !== "undefined" ? llm.temperature : trainer.fields.temperature.value;
  trainer.fields.maxTokens.value =
    typeof llm.max_tokens !== "undefined" && llm.max_tokens !== null ? llm.max_tokens : "";
  trainer.fields.timeout.value =
    typeof llm.timeout_seconds !== "undefined" ? llm.timeout_seconds : trainer.fields.timeout.value;
  trainer.fields.forceJson.checked = Boolean(llm.force_json);
  trainer.fields.extraHeaders.value =
    llm.extra_headers && Object.keys(llm.extra_headers).length > 0
      ? JSON.stringify(llm.extra_headers, null, 2)
      : "";
  trainer.fields.notes.value = detail.notes || "";
  const presetKey = detectPresetKey(detail.llm);
  trainer.suppressPresetChange = true;
  trainer.fields.preset.value = presetKey;
  trainer.suppressPresetChange = false;
  setTrainerEndpoint(trainer, detail.endpoint);
  toggleTrainerButtons(trainer, true);
}

function detectPresetKey(llmConfig) {
  if (!llmConfig) return "custom";
  const entries = Object.entries(LLM_PRESETS);
  for (let index = 0; index < entries.length; index += 1) {
    const [key, preset] = entries[index];
    if (key === "custom") continue;
    if (preset.api_url === llmConfig.api_url && preset.model === llmConfig.model) {
      return key;
    }
  }
  return "custom";
}

function handlePresetChange(trainer) {
  if (trainer.suppressPresetChange) return;
  applyPresetValues(trainer, trainer.fields.preset.value);
}

function applyPresetValues(trainer, presetKey) {
  const preset = LLM_PRESETS[presetKey];
  if (!preset || presetKey === "custom") return;
  trainer.fields.apiUrl.value = preset.api_url || trainer.fields.apiUrl.value;
  trainer.fields.model.value = preset.model || trainer.fields.model.value;
  if (typeof preset.temperature !== "undefined") {
    trainer.fields.temperature.value = preset.temperature;
  }
  if (typeof preset.timeout_seconds !== "undefined") {
    trainer.fields.timeout.value = preset.timeout_seconds;
  }
  if (typeof preset.force_json === "boolean") {
    trainer.fields.forceJson.checked = preset.force_json;
  }
  if (preset.max_tokens) {
    trainer.fields.maxTokens.value = preset.max_tokens;
  }
}

function setTrainerEndpoint(trainer, endpoint) {
  trainer.endpointField.textContent = endpoint || "保存后自动生成";
}

function toggleTrainerButtons(trainer, hasPersona) {
  if (trainer.applyButton) {
    trainer.applyButton.disabled = !hasPersona;
  }
  if (trainer.deleteButton) {
    trainer.deleteButton.disabled = !hasPersona;
  }
}

function parseHeadersInput(value) {
  if (!value) return {};
  try {
    const parsed = JSON.parse(value);
    if (parsed === null || Array.isArray(parsed) || typeof parsed !== "object") {
      throw new Error("额外 Header 需要为 JSON 对象。");
    }
    return parsed;
  } catch (error) {
    throw new Error("额外 Header 需要为合法的 JSON 对象。");
  }
}

function collectTrainerPayload(trainer) {
  const name = trainer.fields.name.value.trim();
  const systemPrompt = trainer.fields.prompt.value.trim();
  const apiUrl = trainer.fields.apiUrl.value.trim();
  const model = trainer.fields.model.value.trim();
  const apiKey = trainer.fields.apiKey.value.trim();
  const temperature = Number(trainer.fields.temperature.value);
  const timeout = Number(trainer.fields.timeout.value);
  const maxTokensRaw = trainer.fields.maxTokens.value.trim();
  const notes = trainer.fields.notes.value.trim();

  if (!name) throw new Error("请填写名称。");
  if (!systemPrompt) throw new Error("请填写提示词。");
  if (!apiUrl) throw new Error("请填写 LLM API URL。");
  if (!model) throw new Error("请填写模型名称。");
  if (Number.isNaN(temperature)) throw new Error("温度值不合法。");
  if (Number.isNaN(timeout) || timeout < 5) throw new Error("超时需要为数字，且至少 5 秒。");

  const llmConfig = {
    api_url: apiUrl,
    model,
    api_key: apiKey || null,
    temperature,
    timeout_seconds: timeout,
    force_json: Boolean(trainer.fields.forceJson.checked),
    max_tokens: maxTokensRaw ? Number(maxTokensRaw) : null,
    extra_headers: parseHeadersInput(trainer.fields.extraHeaders.value.trim()),
  };

  if (llmConfig.max_tokens !== null && Number.isNaN(llmConfig.max_tokens)) {
    throw new Error("最大 Token 需为数字。");
  }

  return {
    name,
    system_prompt: systemPrompt,
    llm: llmConfig,
    notes: notes || null,
  };
}

async function persistTrainer(trainer) {
  try {
    const payload = collectTrainerPayload(trainer);
    const method = trainer.currentId ? "PUT" : "POST";
    const url = trainer.currentId
      ? `/api/personas/${trainer.type}/${trainer.currentId}`
      : `/api/personas/${trainer.type}`;
    const response = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || "保存失败。");
    }
    const detail = await response.json();
    trainer.currentDetail = detail;
    trainer.currentId = detail.id;
    fillTrainerFromDetail(trainer, detail);
    toggleTrainerButtons(trainer, true);
    await loadPersonas();
    if (trainer.selector) {
      trainer.selector.value = detail.id;
    }
    showToast("已生成 Endpoint，可直接填入辩论表单。", "success");
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function deleteTrainer(trainer) {
  if (!trainer.currentId) {
    showToast("请选择需要删除的角色。", "info");
    return;
  }
  const confirmed = window.confirm("确定要删除该角色吗？此操作不可恢复。");
  if (!confirmed) return;
  try {
    const response = await fetch(`/api/personas/${trainer.type}/${trainer.currentId}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      throw new Error("删除失败。");
    }
    await loadPersonas();
    resetTrainerForm(trainer.type);
    showToast("已删除该角色。", "success");
  } catch (error) {
    showToast(error.message, "error");
  }
}

function applyPersonaToDebate(trainer) {
  if (!trainer.currentDetail) {
    showToast("请先保存该角色。", "info");
    return;
  }
  const { name, endpoint } = trainer.currentDetail;
  if (trainer.type === "host") {
    hostNameInput.value = name;
    hostEndpointInput.value = endpoint;
  } else if (trainer.type === "debater") {
    const slot = trainer.slotSelect ? trainer.slotSelect.value : "debater1";
    const targetMap = {
      debater1: {
        name: debater1NameInput,
        endpoint: debater1EndpointInput,
      },
      debater2: {
        name: debater2NameInput,
        endpoint: debater2EndpointInput,
      },
    };
    const target = targetMap[slot] || targetMap.debater1;
    target.name.value = name;
    target.endpoint.value = endpoint;
  } else if (trainer.type === "judge") {
    injectJudgeFromPersona(name, endpoint);
  }
  showToast("已填入辩论表单。", "success");
  switchView("debate");
}

function injectJudgeFromPersona(name, endpoint) {
  let targetCard = Array.from(judgeGrid.querySelectorAll(".judge-card")).find((card) => {
    const nameInput = card.querySelector('input[data-field="name"]');
    const endpointInput = card.querySelector('input[data-field="endpoint"]');
    return nameInput && endpointInput && !nameInput.value && !endpointInput.value;
  });
  if (!targetCard) {
    targetCard = addJudge(true);
    if (!targetCard) {
      showToast(`评委数量已达上限（${MAX_JUDGES}）。`, "info");
      return;
    }
  }
  const nameInput = targetCard.querySelector('input[data-field="name"]');
  const endpointInput = targetCard.querySelector('input[data-field="endpoint"]');
  if (nameInput && endpointInput) {
    nameInput.value = name;
    endpointInput.value = endpoint;
  }
}

async function copyToClipboard(text) {
  if (!text) {
    showToast("暂无可复制的 Endpoint。", "info");
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    showToast("已复制到剪贴板。", "success");
  } catch {
    window.prompt("复制以下链接：", text);
  }
}

function refreshJudgeRemoveButtons() {
  const cards = judgeGrid.querySelectorAll(".judge-card");
  cards.forEach((card) => {
    const removeBtn = card.querySelector(".remove-judge");
    if (!removeBtn) return;
    if (cards.length > MIN_JUDGES) {
      removeBtn.classList.remove("hidden");
    } else {
      removeBtn.classList.add("hidden");
    }
  });
}

function removeJudgeCard(card) {
  const total = judgeGrid.querySelectorAll(".judge-card").length;
  if (total <= MIN_JUDGES) {
    showToast(`至少需要 ${MIN_JUDGES} 位评委。`, "info");
    return;
  }
  judgeGrid.removeChild(card);
  refreshJudgeRemoveButtons();
}

function createJudgeCard(preset = {}, options = {}) {
  const clone = judgeTemplate.content.cloneNode(true);
  const card = clone.querySelector(".judge-card");
  const nameInput = card.querySelector('input[data-field="name"]');
  const endpointInput = card.querySelector('input[data-field="endpoint"]');
  const removeBtn = card.querySelector(".remove-judge");

  nameInput.value = preset.name || "";
  endpointInput.value = preset.endpoint || "";

  if (preset.placeholderName) {
    nameInput.placeholder = preset.placeholderName;
  }
  if (preset.placeholderEndpoint) {
    endpointInput.placeholder = preset.placeholderEndpoint;
  }

  if (removeBtn) {
    removeBtn.addEventListener("click", () => removeJudgeCard(card));
  }

  judgeGrid.appendChild(card);
  if (options.focus && nameInput) {
    nameInput.focus();
  }
  refreshJudgeRemoveButtons();
  return card;
}

function initJudges(presets = []) {
  judgeGrid.innerHTML = "";

  const seeds = presets.slice(0, MAX_JUDGES);
  while (seeds.length < MIN_JUDGES) {
    const index = seeds.length;
    seeds.push({
      name: "",
      endpoint: "",
      placeholderName: `评委 ${index + 1}`,
      placeholderEndpoint: `http://localhost:${8111 + index}/respond`,
    });
  }

  seeds.forEach((seed) => createJudgeCard(seed));
  judgePresetCursor = Math.min(presets.length, MAX_JUDGES);
}

function addJudge(focusNew = false) {
  const existing = judgeGrid.querySelectorAll(".judge-card").length;
  if (existing >= MAX_JUDGES) {
    showToast(`暂不支持超过 ${MAX_JUDGES} 位评委。`, "info");
    return null;
  }

  const preset = judgePresets[judgePresetCursor] || {
    name: "",
    endpoint: "",
    placeholderName: `评委 ${existing + 1}`,
    placeholderEndpoint: `http://localhost:${8111 + existing}/respond`,
  };
  const card = createJudgeCard(preset, { focus: focusNew });
  judgePresetCursor = Math.min(judgePresetCursor + 1, judgePresets.length);
  return card;
}

async function fetchJudgePresets() {
  try {
    const response = await fetch("/api/judges");
    if (!response.ok) return [];
    return response.json();
  } catch (error) {
    console.warn("Failed to load judge presets:", error);
    return [];
  }
}

function showToast(message, type = "info") {
  if (!toast) return;
  toast.textContent = message;
  toast.classList.remove("hidden");
  toast.classList.remove("show");
  toast.dataset.type = type;
  requestAnimationFrame(() => {
    toast.classList.add("show");
  });
  clearTimeout(showToast.timeout);
  showToast.timeout = setTimeout(() => {
    toast.classList.remove("show");
  }, 3200);
}

function setLoadingState(isLoading, message = "正在请求辩论结果...") {
  isRequestInFlight = isLoading;
  const submitBtn = form.querySelector('button[type="submit"]');
  submitBtn.disabled = isLoading;
  saveButton.disabled = isLoading || !currentDebate;

  if (isLoading) {
    statusBar.classList.remove("hidden");
    statusIcon.textContent = "⏳";
    statusText.textContent = message;
    output.classList.remove("hidden");
  } else if (!currentDebate) {
    statusBar.classList.add("hidden");
    statusIcon.textContent = "";
    statusText.textContent = "";
  } else {
    statusIcon.textContent = "✅";
    statusText.textContent = "辩论完成，以下为完整战况。";
    statusBar.classList.remove("hidden");
  }
}

function setErrorState(message) {
  isRequestInFlight = false;
  const submitBtn = form.querySelector('button[type="submit"]');
  submitBtn.disabled = false;
  saveButton.disabled = true;
  statusBar.classList.remove("hidden");
  statusIcon.textContent = "⚠️";
  statusText.textContent = message;
}

function updateProgressStatus(message) {
  if (!message) return;
  statusBar.classList.remove("hidden");
  statusIcon.textContent = "⏳";
  statusText.textContent = message;
}

function bootstrapLiveDebate(payload) {
  currentDebate = {
    topic: payload.topic,
    host: payload.host,
    debaters: payload.debaters,
    judges: payload.judges,
    transcript: [],
    interludes: [],
    judge_votes: [],
    assignments: {},
    metadata: payload.metadata || null,
  };
  output.classList.remove("hidden");
  renderSummary(currentDebate);
  renderTimeline(currentDebate);
  renderJudgeVotes(currentDebate);
}

function collectFormData() {
  const formData = new FormData(form);

  const topic = (formData.get("topic") || "").trim();
  const hostName = (formData.get("hostName") || "").trim();
  const hostEndpoint = (formData.get("hostEndpoint") || "").trim();

  const debaters = [
    {
      name: (formData.get("debater1Name") || "").trim(),
      endpoint: (formData.get("debater1Endpoint") || "").trim(),
    },
    {
      name: (formData.get("debater2Name") || "").trim(),
      endpoint: (formData.get("debater2Endpoint") || "").trim(),
    },
  ];

  const judges = Array.from(judgeGrid.querySelectorAll(".judge-card")).map(
    (card) => {
      const nameInput = card.querySelector('input[data-field="name"]');
      const endpointInput = card.querySelector('input[data-field="endpoint"]');
      const name = nameInput ? nameInput.value.trim() : "";
      const endpoint = endpointInput ? endpointInput.value.trim() : "";
      return { name, endpoint };
    },
  );

  const options = {
    max_cross_questions: Number(formData.get("maxQuestions")) || 5,
    max_freeform_rounds: Number(formData.get("maxRounds")) || 10,
    request_timeout_seconds: Number(formData.get("timeout")) || 45,
  };

  return {
    topic,
    host: { name: hostName, endpoint: hostEndpoint },
    debaters,
    judges,
    options,
  };
}

function slugValue(value) {
  if (!value) return "";
  return value.toLowerCase().replace(/[_\s]+/g, "-");
}

function formatStage(stage) {
  if (!stage) return "未知环节";
  if (stage.startsWith("opening_")) {
    return stage.includes("affirmative") ? "正方开篇陈词" : "反方开篇陈词";
  }
  if (stage.startsWith("affirmative_cross_q")) {
    const index = stage.replace("affirmative_cross_q", "");
    return `正方质询第 ${index} 问`;
  }
  if (stage.startsWith("affirmative_cross_a")) {
    const index = stage.replace("affirmative_cross_a", "");
    return `反方回答第 ${index} 问`;
  }
  if (stage.startsWith("negative_cross_q")) {
    const index = stage.replace("negative_cross_q", "");
    return `反方质询第 ${index} 问`;
  }
  if (stage.startsWith("negative_cross_a")) {
    const index = stage.replace("negative_cross_a", "");
    return `正方回答第 ${index} 问`;
  }
  if (stage.startsWith("free_debate")) {
    const [, info] = stage.split("round");
    const [roundPart, side] = info.split("_");
    const sideInfo = side || "";
    const sideMatch = sideInfo.match(/\d+/);
    const round = Number((sideMatch && sideMatch[0]) || roundPart.replace("_", ""));
    const formattedSide = sideInfo.indexOf("affirmative") >= 0 ? "正方" : "反方";
    return `自由辩论 第 ${round} 回合 · ${formattedSide}`;
  }
  if (stage === "closing_affirmative") return "正方结辩陈词";
  if (stage === "closing_negative") return "反方结辩陈词";
  if (stage === "judging") return "评委投票";
  return stage.replace(/_/g, " ");
}

function renderSummary(debate) {
  summaryGrid.innerHTML = "";

  const assignments = debate.assignments || {};
  const affirmative =
    assignments.affirmative ||
    assignments.AFFIRMATIVE ||
    "（系统分配中）";
  const negative =
    assignments.negative ||
    assignments.NEGATIVE ||
    "（系统分配中）";
  const host =
    assignments.host ||
    assignments.HOST ||
    (debate.host ? debate.host.name : undefined);
  const judges =
    assignments.judge ||
    assignments.JUDGE ||
    (Array.isArray(debate.judges) ? debate.judges.map((judge) => judge.name) : []) ||
    [];

  const { judge_votes: judgeVotes = [] } = debate;
  const affirmativeVotes = judgeVotes.filter(
    (vote) => vote.vote === "affirmative",
  ).length;
  const negativeVotes = judgeVotes.filter(
    (vote) => vote.vote === "negative",
  ).length;
  const tieVotes = judgeVotes.filter((vote) => vote.vote === "tie").length;
  let winnerLabel = "评委仍在讨论";
  if (judgeVotes.length > 0) {
    if (affirmativeVotes > negativeVotes) {
      winnerLabel = `正方领先 ${affirmativeVotes}-${negativeVotes}`;
    } else if (negativeVotes > affirmativeVotes) {
      winnerLabel = `反方领先 ${negativeVotes}-${affirmativeVotes}`;
    } else {
      winnerLabel = "平局";
    }
    if (tieVotes) {
      winnerLabel += `（平票 ${tieVotes}）`;
    }
  }

  const cards = [
    { title: "辩题", value: debate.topic },
    { title: "正方辩手", value: affirmative },
    { title: "反方辩手", value: negative },
    { title: "主持人", value: host },
    {
      title: "评委阵容",
      value: Array.isArray(judges) ? judges.join("、") : judges,
    },
    { title: "评判结果", value: winnerLabel },
  ];

  cards.forEach((card) => {
    const div = document.createElement("div");
    div.className = "summary-card";
    const title = document.createElement("h4");
    title.textContent = card.title;
    const value = document.createElement("p");
    value.textContent = card.value || "—";
    div.appendChild(title);
    div.appendChild(value);
    summaryGrid.appendChild(div);
  });
}

function buildTimeline(debate) {
  const hostMap = new Map();
  (debate.interludes || []).forEach((interlude) => {
    hostMap.set(interlude.stage, interlude);
  });

  const items = [];

  const pushHost = (stage) => {
    if (hostMap.has(stage)) {
      items.push({ type: "host", data: hostMap.get(stage) });
      hostMap.delete(stage);
    }
  };

  pushHost("introduction");

  let insertedMidCross = false;
  let insertedPreFree = false;
  let insertedPreClosing = false;
  let insertedPreJudging = false;

  (debate.transcript || []).forEach((turn) => {
    if (turn.stage === "opening_negative") {
      items.push({ type: "turn", data: turn });
      pushHost("pre_cross_examination");
      return;
    }

    if (
      turn.stage.startsWith("negative_cross_q") &&
      !insertedMidCross
    ) {
      pushHost("mid_cross_examination");
      insertedMidCross = true;
    }

    if (
      turn.stage.startsWith("free_debate_round1_affirmative") &&
      !insertedPreFree
    ) {
      pushHost("pre_free_debate");
      insertedPreFree = true;
    }

    if (turn.stage === "closing_negative" && !insertedPreClosing) {
      pushHost("pre_closing");
      insertedPreClosing = true;
    }

    items.push({ type: "turn", data: turn });

    if (turn.stage === "closing_affirmative" && !insertedPreJudging) {
      pushHost("pre_judging");
      insertedPreJudging = true;
    }
  });

  pushHost("wrap_up");

  return items;
}

function renderTimeline(debate) {
  timeline.innerHTML = "";
  const items = buildTimeline(debate);
  items.forEach((item, index) => {
    const container = document.createElement("article");
    container.className = "timeline-item";

    if (item.type === "host") {
      container.classList.add("host");
      const title = document.createElement("h4");
      title.textContent =
        HOST_STAGE_LABELS[item.data.stage] || "主持人串场";
      const meta = document.createElement("div");
      meta.className = "timeline-meta";
      meta.textContent = `环节 ${index + 1} · 主持人`;
      const content = document.createElement("p");
      content.className = "timeline-content";
      content.textContent = item.data.content;
      container.append(meta, title, content);
    } else {
      const { data } = item;
      const speaker =
        data.speaker_role === "affirmative" ? "正方" : "反方";
      container.classList.add(data.speaker_role);
      const title = document.createElement("h4");
      title.textContent = `${speaker} · ${data.speaker_name}`;
      const meta = document.createElement("div");
      meta.className = "timeline-meta";
      meta.textContent = `环节 ${index + 1} · ${formatStage(data.stage)}`;
      const content = document.createElement("p");
      content.className = "timeline-content";
      content.textContent = data.content;
      container.append(meta, title, content);
    }

    timeline.appendChild(container);
  });
  timeline.scrollTop = timeline.scrollHeight;
}

function renderJudgeVotes(debate) {
  judgeTable.innerHTML = "";
  (debate.judge_votes || []).forEach((vote) => {
    const tr = document.createElement("tr");
    const judgeTd = document.createElement("td");
    const personaName = vote.metadata && vote.metadata.persona_name;
    judgeTd.textContent =
      personaName && personaName !== vote.judge_name
        ? `${vote.judge_name}（${personaName}）`
        : vote.judge_name;

    const voteTd = document.createElement("td");
    if (vote.vote === "affirmative") {
      voteTd.textContent = "正方";
    } else if (vote.vote === "negative") {
      voteTd.textContent = "反方";
    } else {
      voteTd.textContent = "平局";
    }

    const rationaleTd = document.createElement("td");
    rationaleTd.textContent = vote.rationale;

    tr.append(judgeTd, voteTd, rationaleTd);
    judgeTable.appendChild(tr);
  });
}

function renderDebate(debate) {
  currentDebate = debate;
  renderSummary(debate);
  renderTimeline(debate);
  renderJudgeVotes(debate);
  output.classList.remove("hidden");
  saveButton.disabled = false;
}

async function readEventStream(stream, onEvent) {
  const reader = stream.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  async function processBuffer(forceFlush = false) {
    let boundaryIndex = buffer.indexOf("\n\n");
    while (boundaryIndex >= 0) {
      const rawEvent = buffer.slice(0, boundaryIndex).trim();
      buffer = buffer.slice(boundaryIndex + 2);
      if (rawEvent) {
        const dataLine = rawEvent
          .split("\n")
          .find((line) => line.startsWith("data:"));
        if (dataLine) {
          const jsonText = dataLine.replace(/^data:\s*/, "");
          if (jsonText) {
            const parsed = JSON.parse(jsonText);
            // eslint-disable-next-line no-await-in-loop
            await onEvent(parsed);
          }
        }
      }
      boundaryIndex = buffer.indexOf("\n\n");
    }

    if (forceFlush && buffer.trim()) {
      const remaining = buffer.trim();
      buffer = "";
      const dataLine = remaining
        .split("\n")
        .find((line) => line.startsWith("data:"));
      if (dataLine) {
        const jsonText = dataLine.replace(/^data:\s*/, "");
        if (jsonText) {
          await onEvent(JSON.parse(jsonText));
        }
      }
    }
  }

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // eslint-disable-next-line no-await-in-loop
    await processBuffer(false);
  }
  buffer += decoder.decode();
  await processBuffer(true);
}

async function handleStreamingEvent(event) {
  if (!event || !event.type) return;
  const { type } = event;
  const payload = event.payload || {};

  if (type === "host_interlude") {
    if (!currentDebate) return;
    currentDebate.interludes = currentDebate.interludes || [];
    currentDebate.interludes.push(payload);
    renderSummary(currentDebate);
    renderTimeline(currentDebate);
    updateProgressStatus(
      HOST_STAGE_LABELS[payload.stage] ||
        `主持人串场 · ${payload.stage || "进行中"}`,
    );
    return;
  }

  if (type === "debate_turn") {
    if (!currentDebate) return;
    currentDebate.transcript = currentDebate.transcript || [];
    currentDebate.transcript.push(payload);
    renderTimeline(currentDebate);
    renderSummary(currentDebate);
    updateProgressStatus(`当前环节：${formatStage(payload.stage)}`);
    return;
  }

  if (type === "judge_vote") {
    if (!currentDebate) return;
    currentDebate.judge_votes = currentDebate.judge_votes || [];
    currentDebate.judge_votes.push(payload);
    renderJudgeVotes(currentDebate);
    renderSummary(currentDebate);
    updateProgressStatus(`评委 ${payload.judge_name} 已完成投票`);
    return;
  }

  if (type === "complete") {
    renderDebate(payload);
    setLoadingState(false);
    showToast("辩论完成，可在下方查看详情。", "success");
    return;
  }

  if (type === "assignments") {
    if (!currentDebate) {
      currentDebate = { assignments: {} };
    }
    currentDebate.assignments = payload || {};
    renderSummary(currentDebate);
    return;
  }

  if (type === "error") {
    throw new Error(
      (payload && payload.message) || "服务端返回未知错误，辩论中止。",
    );
  }
}

async function startDebate(event) {
  event.preventDefault();
  if (isRequestInFlight) return;

  const payload = collectFormData();
  const filledJudges = payload.judges.filter(
    (judge) => judge.name || judge.endpoint,
  );
  payload.judges = filledJudges;

  if (!payload.topic) {
    showToast("请填写辩题。", "error");
    return;
  }

  if (!payload.host.name || !payload.host.endpoint) {
    showToast("请填写主持人信息。", "error");
    return;
  }

  const invalidDebater = payload.debaters.find(
    (debater) => !debater.name || !debater.endpoint,
  );
  if (invalidDebater) {
    showToast("请填写两位辩手的姓名与 API。", "error");
    return;
  }

  if (payload.judges.length < MIN_JUDGES) {
    showToast(`请至少填写 ${MIN_JUDGES} 位评委。`, "error");
    return;
  }

  const incompleteJudge = payload.judges.find(
    (judge) => !judge.name || !judge.endpoint,
  );
  if (incompleteJudge) {
    showToast("部分评委信息不完整，请填写姓名和 API。", "error");
    return;
  }

  bootstrapLiveDebate(payload);
  setLoadingState(true, "辩论开始，正在实时更新...");
  showToast("辩论开始，正在调度各方发言...", "info");

  const controller = new AbortController();
  streamAbortController = controller;
  let receivedCompletion = false;

  try {
    const response = await fetch("/api/debate/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });

    if (!response.ok || !response.body) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || "服务端返回错误。");
    }

    await readEventStream(response.body, async (evt) => {
      if (evt.type === "complete") {
        receivedCompletion = true;
      }
      await handleStreamingEvent(evt);
    });

    if (!receivedCompletion) {
      throw new Error("辩论尚未完成即断开连接。");
    }
  } catch (error) {
    if (error.name === "AbortError") {
      return;
    }
    console.error(error);
    saveButton.disabled = true;
    setErrorState(`辩论失败：${error.message}`);
    showToast(`辩论失败：${error.message}`, "error");
  } finally {
    streamAbortController = null;
  }
}

async function saveCurrentDebate() {
  if (!currentDebate) {
    showToast("尚未生成辩论内容。", "info");
    return;
  }
  const defaultLabel = slugValue(currentDebate.topic).slice(0, 32);
  // eslint-disable-next-line no-alert
  const filename = window.prompt(
    "可选：输入保存文件名（无需扩展名，默认自动生成）",
    defaultLabel,
  );

  try {
    const response = await fetch("/api/debate/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        debate: currentDebate,
        filename: filename ? filename.trim() : null,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || "保存失败。");
    }

    const result = await response.json();
    showToast(`已保存：${result.path}`, "success");
  } catch (error) {
    showToast(`保存失败：${error.message}`, "error");
  }
}

function resetView() {
  if (streamAbortController) {
    streamAbortController.abort();
    streamAbortController = null;
  }
  currentDebate = null;
  isRequestInFlight = false;
  const submitBtn = form.querySelector('button[type="submit"]');
  if (submitBtn) submitBtn.disabled = false;
  output.classList.add("hidden");
  summaryGrid.innerHTML = "";
  timeline.innerHTML = "";
  judgeTable.innerHTML = "";
  saveButton.disabled = true;
  statusBar.classList.add("hidden");
  statusIcon.textContent = "";
  statusText.textContent = "";
  showToast("表单已重置。", "info");
}

async function loadPersonas() {
  try {
    const response = await fetch("/api/personas");
    if (!response.ok) throw new Error();
    const data = await response.json();
    personaCatalog.hosts = data.hosts || [];
    personaCatalog.debaters = data.debaters || [];
    personaCatalog.judges = data.judges || [];
    updateTrainerSelectors();
  } catch (error) {
    console.warn("无法加载已有角色。", error);
  }
}

function updateTrainerSelectors() {
  const mapping = {
    host: "hosts",
    debater: "debaters",
    judge: "judges",
  };
  Object.entries(personaTrainers).forEach(([type, trainer]) => {
    const listKey = mapping[type];
    const list = personaCatalog[listKey] || [];
    if (!trainer.selector) return;
    const previous = trainer.selector.value;
    const label = TRAINER_LABELS[type] || "";
    trainer.selector.innerHTML = `<option value="">新建${label}</option>`;
    list.forEach((item) => {
      const option = document.createElement("option");
      option.value = item.id;
      option.textContent = `${item.name} · ${item.model}`;
      trainer.selector.appendChild(option);
    });
    if (trainer.currentId && list.some((item) => item.id === trainer.currentId)) {
      trainer.selector.value = trainer.currentId;
    } else if (previous && list.some((item) => item.id === previous)) {
      trainer.selector.value = previous;
    } else {
      trainer.selector.value = "";
    }
  });
}

async function bootstrap() {
  Object.keys(personaTrainers).forEach((type) => resetTrainerForm(type));
  const initialButton = document.querySelector(".tab-button.active");
  const initialTarget =
    initialButton && initialButton.dataset ? initialButton.dataset.viewTarget : "host";
  switchView(initialTarget || "host");
  await loadPersonas();
  judgePresets = await fetchJudgePresets();
  initJudges(judgePresets);
  refreshJudgeRemoveButtons();
}

bootstrap();

form.addEventListener("submit", startDebate);
form.addEventListener("reset", () => {
  initJudges(judgePresets);
  refreshJudgeRemoveButtons();
  resetView();
});

if (addJudgeButton) {
  addJudgeButton.addEventListener("click", () => addJudge(true));
}

saveButton.addEventListener("click", saveCurrentDebate);
