import * as Blockly from "blockly";
import "blockly/blocks";
import * as ru from "blockly/msg/ru";
import "./styles.css";

Blockly.setLocale(ru);

const FIELD_WIDTH = 1100;
const FIELD_HEIGHT = 2300;
const MAX_PATHS = 16;
const MAX_SIMULATION_STEPS = 10000;

const toolbox = {
  kind: "categoryToolbox",
  contents: [
    {
      kind: "category",
      name: "Движение",
      categorystyle: "motion_category",
      contents: [
        { kind: "block", type: "op_straight" },
        { kind: "block", type: "op_turn" },
        { kind: "block", type: "op_arc" },
      ],
    },
    {
      kind: "category",
      name: "Навески и действия",
      categorystyle: "action_category",
      contents: [
        { kind: "block", type: "op_attachment" },
        { kind: "block", type: "op_wait" },
        { kind: "block", type: "op_beep" },
      ],
    },
    {
      kind: "category",
      name: "Управление",
      categorystyle: "logic_category",
      contents: [
        { kind: "block", type: "op_if" },
        { kind: "block", type: "op_repeat" },
        { kind: "block", type: "op_parallel" },
      ],
    },
    {
      kind: "category",
      name: "Условия и датчики",
      categorystyle: "sensor_category",
      contents: [{ kind: "block", type: "op_sensor_compare" }],
    },
  ],
};

const theme = Blockly.Theme.defineTheme("op", {
  name: "op",
  base: Blockly.Themes.Classic,
  categoryStyles: {
    motion_category: { colour: "#2b8a83" },
    action_category: { colour: "#b56c43" },
    logic_category: { colour: "#8a70be" },
    sensor_category: { colour: "#8a70be" },
  },
  componentStyles: {
    workspaceBackgroundColour: "#151e1a",
    toolboxBackgroundColour: "#1b2822",
    toolboxForegroundColour: "#dce8e1",
    flyoutBackgroundColour: "#202d27",
    flyoutForegroundColour: "#dce8e1",
    flyoutOpacity: 1,
    scrollbarColour: "#52665a",
    scrollbarOpacity: 0.65,
    insertionMarkerColour: "#c6f36b",
    insertionMarkerOpacity: 0.3,
    markerColour: "#c6f36b",
    cursorColour: "#c6f36b",
  },
  fontStyle: { family: "Segoe UI", weight: "600", size: 12 },
});

function numberField(value, min, max, precision) {
  return new Blockly.FieldNumber(value, min, max, precision);
}

Blockly.Blocks.op_mission = {
  init() {
    this.appendDummyInput().appendField("Миссия · команды выполняются по порядку");
    this.appendStatementInput("STEPS").appendField("начало");
    this.setColour("#75836f");
    this.setDeletable(false);
    this.setMovable(false);
  },
};

Blockly.Blocks.op_straight = {
  init() {
    this.appendDummyInput()
      .appendField("Ехать прямо")
      .appendField(numberField(300, -5000, 5000, 10), "DISTANCE")
      .appendField("мм · скорость")
      .appendField(numberField(300, 1, 800, 10), "SPEED")
      .appendField("мм/с");
    this.setPreviousStatement(true);
    this.setNextStatement(true);
    this.setColour("#2b8a83");
    this.setInputsInline(true);
  },
};

Blockly.Blocks.op_turn = {
  init() {
    this.appendDummyInput()
      .appendField("Повернуть")
      .appendField(numberField(90, -360, 360, 5), "ANGLE")
      .appendField("° · скорость")
      .appendField(numberField(180, 1, 360, 5), "RATE")
      .appendField("°/с");
    this.setPreviousStatement(true);
    this.setNextStatement(true);
    this.setColour("#2b8a83");
    this.setInputsInline(true);
  },
};

Blockly.Blocks.op_arc = {
  init() {
    this.appendDummyInput()
      .appendField("Дуга · радиус")
      .appendField(numberField(200, -5000, 5000, 10), "RADIUS")
      .appendField("мм · угол")
      .appendField(numberField(90, -360, 360, 5), "ANGLE")
      .appendField("° · скорость")
      .appendField(numberField(300, 1, 800, 10), "SPEED")
      .appendField("мм/с");
    this.setPreviousStatement(true);
    this.setNextStatement(true);
    this.setColour("#2b8a83");
    this.setInputsInline(true);
  },
};

Blockly.Blocks.op_attachment = {
  init() {
    this.appendDummyInput()
      .appendField("Навеска порт")
      .appendField(new Blockly.FieldDropdown([["E", "E"], ["F", "F"]]), "PORT")
      .appendField("угол")
      .appendField(numberField(90, -360, 360, 5), "ANGLE")
      .appendField("° · скорость")
      .appendField(numberField(300, 1, 800, 10), "SPEED")
      .appendField("°/с");
    this.setPreviousStatement(true);
    this.setNextStatement(true);
    this.setColour("#b56c43");
    this.setInputsInline(true);
  },
};

Blockly.Blocks.op_wait = {
  init() {
    this.appendDummyInput()
      .appendField("Ждать")
      .appendField(numberField(500, 0, 30000, 100), "DURATION")
      .appendField("мс");
    this.setPreviousStatement(true);
    this.setNextStatement(true);
    this.setColour("#b56c43");
    this.setInputsInline(true);
  },
};

Blockly.Blocks.op_beep = {
  init() {
    this.appendDummyInput()
      .appendField("Сигнал")
      .appendField(numberField(880, 50, 4000, 10), "FREQUENCY")
      .appendField("Гц · длительность")
      .appendField(numberField(150, 1, 1000, 10), "DURATION")
      .appendField("мс");
    this.setPreviousStatement(true);
    this.setNextStatement(true);
    this.setColour("#b56c43");
    this.setInputsInline(true);
  },
};

Blockly.Blocks.op_sensor_compare = {
  init() {
    this.appendDummyInput()
      .appendField(new Blockly.FieldDropdown([
        ["курс, °", "heading_deg"],
        ["заряд, мВ", "battery_mv"],
        ["угол мотора E, °", "attachment_E"],
        ["угол мотора F, °", "attachment_F"],
      ]), "SENSOR")
      .appendField(new Blockly.FieldDropdown([
        ["меньше", "<"],
        ["≤", "<="],
        ["равно", "=="],
        ["не равно", "!="],
        ["≥", ">="],
        ["больше", ">"],
      ]), "OPERATOR")
      .appendField(numberField(45, -1000000, 1000000, 1), "VALUE");
    this.setOutput(true, "Boolean");
    this.setColour("#8a70be");
    this.setInputsInline(true);
  },
};

Blockly.Blocks.op_if = {
  init() {
    this.appendValueInput("CONDITION")
      .setCheck("Boolean")
      .appendField("Если");
    this.appendStatementInput("THEN").appendField("то");
    this.appendStatementInput("ELSE").appendField("иначе");
    this.setPreviousStatement(true);
    this.setNextStatement(true);
    this.setColour("#8a70be");
  },
};

Blockly.Blocks.op_repeat = {
  init() {
    this.appendDummyInput()
      .appendField("Повторить")
      .appendField(numberField(2, 1, 100, 1), "TIMES")
      .appendField("раз");
    this.appendStatementInput("DO");
    this.setPreviousStatement(true);
    this.setNextStatement(true);
    this.setColour("#8a70be");
  },
};

Blockly.Blocks.op_parallel = {
  init() {
    this.appendDummyInput().appendField("Одновременно · независимые каналы");
    this.appendStatementInput("DRIVE").appendField("Привод");
    this.appendStatementInput("E").appendField("Навеска E");
    this.appendStatementInput("F").appendField("Навеска F");
    this.setPreviousStatement(true);
    this.setNextStatement(true);
    this.setColour("#d0913e");
  },
};

const workspace = Blockly.inject("blockly", {
  toolbox,
  theme,
  media: "./",
  renderer: "zelos",
  trashcan: true,
  move: { scrollbars: true, drag: true, wheel: true },
  zoom: { controls: true, wheel: true, startScale: 0.9, maxScale: 1.4, minScale: 0.55 },
  sounds: false,
});

const elements = {
  filename: document.querySelector("#filename"),
  missionName: document.querySelector("#mission-name"),
  missionColor: document.querySelector("#mission-color"),
  missionSelect: document.querySelector("#mission-select"),
  startX: document.querySelector("#start-x"),
  startY: document.querySelector("#start-y"),
  startHeading: document.querySelector("#start-heading"),
  pathLayer: document.querySelector("#path-layer"),
  robotLayer: document.querySelector("#robot-layer"),
  status: document.querySelector("#status"),
};

function blockNumber(block, field) {
  return Number(block.getFieldValue(field));
}

function stepChain(first, inputName) {
  const steps = [];
  let block = first.getInputTargetBlock(inputName);
  while (block) {
    steps.push(blockToStep(block));
    block = block.getNextBlock();
  }
  return steps;
}

function blockToStep(block) {
  switch (block.type) {
    case "op_straight":
      return {
        type: "straight",
        distance_mm: blockNumber(block, "DISTANCE"),
        speed_mm_s: blockNumber(block, "SPEED"),
      };
    case "op_turn":
      return {
        type: "turn",
        angle_deg: blockNumber(block, "ANGLE"),
        rate_deg_s: blockNumber(block, "RATE"),
      };
    case "op_arc":
      return {
        type: "arc",
        radius_mm: blockNumber(block, "RADIUS"),
        angle_deg: blockNumber(block, "ANGLE"),
        speed_mm_s: blockNumber(block, "SPEED"),
      };
    case "op_attachment":
      return {
        type: "attachment",
        port: block.getFieldValue("PORT"),
        angle_deg: blockNumber(block, "ANGLE"),
        speed_deg_s: blockNumber(block, "SPEED"),
      };
    case "op_wait":
      return { type: "wait", duration_ms: blockNumber(block, "DURATION") };
    case "op_beep":
      return {
        type: "beep",
        frequency_hz: blockNumber(block, "FREQUENCY"),
        duration_ms: blockNumber(block, "DURATION"),
      };
    case "op_if":
      {
        const step = {
        type: "if",
        condition: conditionToData(block.getInputTargetBlock("CONDITION")),
        then: stepChain(block, "THEN"),
        };
        const otherwise = stepChain(block, "ELSE");
        if (otherwise.length) step.else = otherwise;
        return step;
      }
    case "op_repeat":
      return {
        type: "repeat",
        times: blockNumber(block, "TIMES"),
        steps: stepChain(block, "DO"),
      };
    case "op_parallel": {
      const branches = [];
      for (const resource of ["drive", "E", "F"]) {
        const input = resource === "drive" ? "DRIVE" : resource;
        const steps = stepChain(block, input);
        if (steps.length) branches.push({ resource, steps });
      }
      return { type: "parallel", branches };
    }
    default:
      throw new Error("Неизвестный блок: " + block.type);
  }
}

function conditionToData(block) {
  if (!block || block.type !== "op_sensor_compare") {
    throw new Error("В условие нужно вставить блок сравнения датчика.");
  }
  const sensor = block.getFieldValue("SENSOR");
  const condition = {
    sensor: sensor.indexOf("attachment_") === 0 ? "attachment_angle_deg" : sensor,
    operator: block.getFieldValue("OPERATOR"),
    value: blockNumber(block, "VALUE"),
  };
  if (sensor === "attachment_E") condition.port = "E";
  if (sensor === "attachment_F") condition.port = "F";
  return condition;
}

function currentMission() {
  const root = workspace.getTopBlocks(false).find((block) => block.type === "op_mission");
  if (!root) throw new Error("На рабочем поле нет корневого блока «Миссия».");
  const startPose = {
    x_mm: elements.startX.valueAsNumber,
    y_mm: elements.startY.valueAsNumber,
    heading_deg: elements.startHeading.valueAsNumber,
  };
  if (
    !Number.isFinite(startPose.x_mm) || startPose.x_mm < 0 || startPose.x_mm > FIELD_WIDTH ||
    !Number.isFinite(startPose.y_mm) || startPose.y_mm < 0 || startPose.y_mm > FIELD_HEIGHT ||
    !Number.isFinite(startPose.heading_deg) || startPose.heading_deg < -360 || startPose.heading_deg > 360
  ) {
    throw new Error("Стартовая позиция должна быть внутри поля, курс — от -360° до 360°.");
  }
  return {
    version: 1,
    name: elements.missionName.value.trim(),
    color: elements.missionColor.value,
    start_pose: startPose,
    steps: stepChain(root, "STEPS"),
  };
}

function poseAfter(state, step) {
  if (step.type === "straight") {
    const heading = (state.heading * Math.PI) / 180;
    state.x += step.distance_mm * Math.sin(heading);
    state.y += step.distance_mm * Math.cos(heading);
  } else if (step.type === "turn") {
    state.heading += step.angle_deg;
  } else if (step.type === "arc") {
    const radius = step.radius_mm;
    const start = (state.heading * Math.PI) / 180;
    const change = step.angle_deg * (radius > 0 ? 1 : -1);
    const segments = Math.max(8, Math.ceil(Math.abs(change) / 4));
    for (let index = 1; index <= segments; index += 1) {
      const angle = start + (change * Math.PI / 180) * (index / segments);
      const startAngle = state.heading * Math.PI / 180;
      const currentX = state.x + radius * (Math.cos(startAngle) - Math.cos(angle));
      const currentY = state.y + radius * (Math.sin(angle) - Math.sin(startAngle));
      state.points.push([currentX, currentY]);
    }
    const end = (state.heading + change) * Math.PI / 180;
    state.x += radius * (Math.cos(start) - Math.cos(end));
    state.y += radius * (Math.sin(end) - Math.sin(start));
    state.heading += change;
  }
  if (step.type !== "arc") state.points.push([state.x, state.y]);
  return state;
}

function copyState(state, alternate) {
  return {
    x: state.x,
    y: state.y,
    heading: state.heading,
    points: state.points.map((point) => point.slice()),
    alternate: state.alternate || alternate,
  };
}

function simulateSteps(states, steps, budget) {
  let current = states;
  for (const step of steps) {
    if (budget.remaining <= 0) {
      budget.truncated = true;
      break;
    }
    budget.remaining -= 1;
    if (step.type === "if") {
      const alternatives = [];
      for (const state of current) {
        alternatives.push(...simulateSteps([copyState(state, false)], step.then, budget));
        alternatives.push(...simulateSteps([copyState(state, true)], step.else || [], budget));
      }
      current = alternatives.slice(0, MAX_PATHS);
    } else if (step.type === "repeat") {
      for (let count = 0; count < step.times; count += 1) {
        current = simulateSteps(current, step.steps, budget).slice(0, MAX_PATHS);
        if (budget.remaining <= 0) break;
      }
    } else if (step.type === "parallel") {
      const drive = step.branches.find((branch) => branch.resource === "drive");
      if (drive) current = simulateSteps(current, drive.steps, budget);
    } else {
      current = current.map((state) => poseAfter(state, step));
    }
  }
  return current.slice(0, MAX_PATHS);
}

function mapX(x) {
  return x;
}

function mapY(y) {
  return FIELD_HEIGHT - y;
}

function renderMap(mission) {
  const x = mission.start_pose.x_mm;
  const y = mission.start_pose.y_mm;
  const heading = mission.start_pose.heading_deg;
  const start = { x, y, heading, points: [[x, y]], alternate: false };
  const budget = { remaining: MAX_SIMULATION_STEPS, truncated: false };
  const endStates = simulateSteps([start], mission.steps, budget);

  elements.pathLayer.replaceChildren();
  elements.robotLayer.replaceChildren();
  for (const state of endStates) {
    const path = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    path.setAttribute(
      "points",
      state.points.map((point) => mapX(point[0]) + "," + mapY(point[1])).join(" ")
    );
    path.setAttribute("class", state.alternate ? "trajectory alt" : "trajectory");
    elements.pathLayer.appendChild(path);
  }

  const startMark = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  startMark.setAttribute("cx", mapX(x));
  startMark.setAttribute("cy", mapY(y));
  startMark.setAttribute("r", "18");
  startMark.setAttribute("class", "start-mark");
  elements.robotLayer.appendChild(startMark);

  const finalState = endStates[0] || start;
  const robot = document.createElementNS("http://www.w3.org/2000/svg", "g");
  robot.setAttribute(
    "transform",
    "translate(" + mapX(finalState.x) + " " + mapY(finalState.y) + ") rotate(" + finalState.heading + ")"
  );
  const body = document.createElementNS("http://www.w3.org/2000/svg", "path");
  body.setAttribute("d", "M 0 -35 L 24 24 L 0 15 L -24 24 Z");
  body.setAttribute("class", "robot-mark");
  const nose = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  nose.setAttribute("cx", "0");
  nose.setAttribute("cy", "-16");
  nose.setAttribute("r", "5");
  nose.setAttribute("class", "robot-direction");
  robot.append(body, nose);
  elements.robotLayer.appendChild(robot);

  const outside = endStates.some((state) =>
    state.points.some((point) =>
      point[0] < 0 || point[0] > FIELD_WIDTH || point[1] < 0 || point[1] > FIELD_HEIGHT
    )
  );
  return { outside, truncated: budget.truncated };
}

function setStatus(message, error) {
  elements.status.textContent = message;
  elements.status.classList.toggle("error", Boolean(error));
}

function updatePreview() {
  try {
    const mission = currentMission();
    const result = renderMap(mission);
    setStatus(
      result.outside
        ? "Траектория выходит за границы поля 110 × 230 см."
        : result.truncated
          ? "Предпросмотр обрезан после " + MAX_SIMULATION_STEPS + " команд."
          : "Предпросмотр обновлён · " + mission.steps.length + " команд.",
      result.outside
    );
  } catch (error) {
    setStatus(error.message, true);
  }
}

function createBlock(type, fields) {
  const block = workspace.newBlock(type);
  for (const [field, value] of Object.entries(fields || {})) {
    block.setFieldValue(String(value), field);
  }
  block.initSvg();
  block.render();
  return block;
}

function connectSequence(parent, inputName, steps) {
  let previous = null;
  for (const step of steps || []) {
    const block = createStepBlock(step);
    if (previous) previous.nextConnection.connect(block.previousConnection);
    else parent.getInput(inputName).connection.connect(block.previousConnection);
    previous = block;
  }
}

function createStepBlock(step) {
  let block;
  switch (step.type) {
    case "straight":
      block = createBlock("op_straight", {
        DISTANCE: step.distance_mm,
        SPEED: step.speed_mm_s === undefined ? 300 : step.speed_mm_s,
      });
      break;
    case "turn":
      block = createBlock("op_turn", {
        ANGLE: step.angle_deg,
        RATE: step.rate_deg_s === undefined ? 180 : step.rate_deg_s,
      });
      break;
    case "arc":
      block = createBlock("op_arc", {
        RADIUS: step.radius_mm,
        ANGLE: step.angle_deg,
        SPEED: step.speed_mm_s === undefined ? 300 : step.speed_mm_s,
      });
      break;
    case "attachment":
      block = createBlock("op_attachment", {
        PORT: step.port,
        ANGLE: step.angle_deg,
        SPEED: step.speed_deg_s,
      });
      break;
    case "wait":
      block = createBlock("op_wait", { DURATION: step.duration_ms });
      break;
    case "beep":
      block = createBlock("op_beep", {
        FREQUENCY: step.frequency_hz,
        DURATION: step.duration_ms,
      });
      break;
    case "if": {
      block = createBlock("op_if", {});
      const condition = step.condition;
      let sensor = condition.sensor;
      if (sensor === "attachment_angle_deg") sensor = "attachment_" + condition.port;
      const conditionBlock = createBlock("op_sensor_compare", {
        SENSOR: sensor,
        OPERATOR: condition.operator,
        VALUE: condition.value,
      });
      block.getInput("CONDITION").connection.connect(conditionBlock.outputConnection);
      connectSequence(block, "THEN", step.then);
      connectSequence(block, "ELSE", step.else || []);
      break;
    }
    case "repeat":
      block = createBlock("op_repeat", { TIMES: step.times });
      connectSequence(block, "DO", step.steps);
      break;
    case "parallel":
      block = createBlock("op_parallel", {});
      for (const branch of step.branches) {
        const input = branch.resource === "drive" ? "DRIVE" : branch.resource;
        connectSequence(block, input, branch.steps);
      }
      break;
    default:
      throw new Error("Неизвестная команда миссии: " + step.type);
  }
  return block;
}

function replaceWorkspace(mission) {
  workspace.clear();
  elements.missionName.value = mission.name || "Новая миссия";
  elements.missionColor.value = mission.color || "CYAN";
  const pose = mission.start_pose || { x_mm: 550, y_mm: 120, heading_deg: 0 };
  elements.startX.value = pose.x_mm;
  elements.startY.value = pose.y_mm;
  elements.startHeading.value = pose.heading_deg;
  const root = createBlock("op_mission", {});
  connectSequence(root, "STEPS", mission.steps || []);
  Blockly.svgResize(workspace);
  updatePreview();
}

async function loadMissionList(preferredFilename) {
  const selection = preferredFilename || elements.missionSelect.value;
  const response = await fetch("/api/missions");
  if (!response.ok) throw new Error("Не удалось получить список миссий.");
  const data = await response.json();
  const valid = data.missions.filter((item) => item.mission);
  elements.missionSelect.replaceChildren();
  for (const item of valid) {
    const option = document.createElement("option");
    option.value = item.filename;
    option.textContent = item.filename;
    elements.missionSelect.appendChild(option);
  }
  if (valid.some((item) => item.filename === selection)) {
    elements.missionSelect.value = selection;
  }
  return valid;
}

async function openSelectedMission() {
  try {
    const requestedFilename = elements.missionSelect.value;
    const list = await loadMissionList(requestedFilename);
    const selected = list.find((item) => item.filename === requestedFilename)
      || list.find((item) => item.filename === "mission_3.json")
      || list[0];
    if (selected) {
      elements.missionSelect.value = selected.filename;
      elements.filename.value = selected.filename;
      replaceWorkspace(selected.mission);
      setStatus("Загружена " + selected.filename + ".");
    } else {
      replaceWorkspace({
        version: 1,
        name: "Новая миссия",
        color: "CYAN",
        steps: [{ type: "straight", distance_mm: 100, speed_mm_s: 200 }],
      });
      setStatus("Создана новая миссия. Добавь команды из панели блоков.");
    }
  } catch (error) {
    setStatus(error.message, true);
  }
}

function downloadMission(mission) {
  const blob = new Blob([JSON.stringify(mission, null, 2) + "\n"], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = elements.filename.value;
  link.click();
  URL.revokeObjectURL(url);
}

async function saveAndBuild() {
  try {
    const mission = currentMission();
    const filename = elements.filename.value.trim();
    if (!/^mission_[0-9]+\.json$/.test(filename)) {
      throw new Error("Имя файла должно быть в формате mission_4.json.");
    }
    const response = await fetch("/api/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename, mission }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Не удалось собрать архив.");
    await loadMissionList();
    elements.missionSelect.value = filename;
    setStatus(filename + " сохранена. Архив " + result.archive + " готов.");
  } catch (error) {
    setStatus(error.message, true);
  }
}

document.querySelector("#load-button").addEventListener("click", openSelectedMission);
document.querySelector("#save-button").addEventListener("click", saveAndBuild);
document.querySelector("#export-button").addEventListener("click", () => {
  try {
    downloadMission(currentMission());
    setStatus("JSON скачан: " + elements.filename.value);
  } catch (error) {
    setStatus(error.message, true);
  }
});
document.querySelector("#fit-button").addEventListener("click", () => Blockly.svgResize(workspace));
elements.missionSelect.addEventListener("change", () => {
  const filename = elements.missionSelect.value;
  if (filename) elements.filename.value = filename;
});

workspace.addChangeListener((event) => {
  if (event.isUiEvent) return;
  window.clearTimeout(updatePreview.timer);
  updatePreview.timer = window.setTimeout(updatePreview, 100);
});
for (const input of [elements.startX, elements.startY, elements.startHeading]) {
  input.addEventListener("input", updatePreview);
}
window.addEventListener("resize", () => Blockly.svgResize(workspace));

openSelectedMission();
