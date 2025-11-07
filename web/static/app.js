const judgeGrid = document.querySelector(".judges-grid");
const judgeTemplate = document.querySelector("#judge-template");
const addJudgeButton = document.querySelector("#add-judge");
const saveButton = document.querySelector("#save-debate");
const form = document.querySelector("#debate-form");
const statusBar = document.querySelector("#status-bar");
const statusIcon = document.querySelector(".status-icon");
const statusText = document.querySelector("#status-text");
const output = document.querySelector("#debate-output");
const summaryGrid = document.querySelector("#summary-grid");
const timeline = document.querySelector("#timeline");
const judgeTable = document.querySelector("#judge-table");
const toast = document.querySelector("#toast");

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

const MIN_JUDGES = Number(judgeGrid?.dataset.min || 5);
const MAX_JUDGES = 12;

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

function createJudgeCard(preset = {}) {
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
  refreshJudgeRemoveButtons();
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

function addJudge() {
  const existing = judgeGrid.querySelectorAll(".judge-card").length;
  if (existing >= MAX_JUDGES) {
    showToast(`暂不支持超过 ${MAX_JUDGES} 位评委。`, "info");
    return;
  }

  const preset = judgePresets[judgePresetCursor] || {
    name: "",
    endpoint: "",
    placeholderName: `评委 ${existing + 1}`,
    placeholderEndpoint: `http://localhost:${8111 + existing}/respond`,
  };
  createJudgeCard(preset);
  judgePresetCursor = Math.min(judgePresetCursor + 1, judgePresets.length);
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
    output.classList.add("hidden");
  } else if (!currentDebate) {
    statusBar.classList.add("hidden");
  } else {
    statusIcon.textContent = "✅";
    statusText.textContent = "辩论完成，以下为完整战况。";
    statusBar.classList.remove("hidden");
  }
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
      const name = (card.querySelector('input[data-field="name"]')?.value || "").trim();
      const endpoint = (card.querySelector('input[data-field="endpoint"]')?.value || "").trim();
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
    const round = Number(side?.match(/\d+/)?.[0] || roundPart.replace("_", ""));
    const formattedSide = side?.includes("affirmative") ? "正方" : "反方";
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
  const host = assignments.host || assignments.HOST || debate.host?.name;
  const judges =
    assignments.judge ||
    assignments.JUDGE ||
    debate.judges?.map((judge) => judge.name) ||
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
}

function renderJudgeVotes(debate) {
  judgeTable.innerHTML = "";
  (debate.judge_votes || []).forEach((vote) => {
    const tr = document.createElement("tr");
    const judgeTd = document.createElement("td");
    const personaName = vote.metadata?.persona_name;
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
  setLoadingState(false, "");
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

  setLoadingState(true);
  showToast("辩论开始，正在调度各方发言...", "info");

  try {
    const response = await fetch("/api/debate/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || "服务端返回错误。");
    }

    const debate = await response.json();
    renderDebate(debate);
    showToast("辩论完成，可在下方查看详情。", "success");
  } catch (error) {
    currentDebate = null;
    saveButton.disabled = true;
    setLoadingState(false);
    showToast(`辩论失败：${error.message}`, "error");
    console.error(error);
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
  currentDebate = null;
  output.classList.add("hidden");
  saveButton.disabled = true;
  statusBar.classList.add("hidden");
  showToast("表单已重置。", "info");
}

async function bootstrap() {
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
  addJudgeButton.addEventListener("click", addJudge);
}

saveButton.addEventListener("click", saveCurrentDebate);
