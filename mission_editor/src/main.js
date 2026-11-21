import * as Blockly from "blockly";
import "blockly/blocks";
import * as ru from "blockly/msg/ru";
import fieldMapUrl from "./assets/fll-field-map.png";
import "./styles.css";

Blockly.setLocale(ru);

const FIELD_WIDTH = 2000;
const FIELD_HEIGHT = 1140;
const ROBOT_WIDTH_MM = 183;
const ROBOT_HEIGHT_MM = 120;
const MAX_PATHS = 16;
const MAX_SIMULATION_STEPS = 10000;
const DEFAULT_SETTINGS = {
  speed: 1,
  accel: 900,
  decel: 1100,
  turnAccel: 720,
  turnDecel: 900,
  showPlan: true,
  showTrail: true,
  autosave: false,
};

function loadSettings() {
  try {
    const stored = JSON.parse(window.localStorage.getItem("op.settings") || "{}");
    return { ...DEFAULT_SETTINGS, ...stored };
  } catch (error) {
    return { ...DEFAULT_SETTINGS };
  }
}

const settings = loadSettings();
let autosaveTimer = 0;
const PLAYER_DT = 0.02;
let playerTrail = null;
let playerMarker = null;
let timeline = { duration: 0, frames: [] };
const player = { time: 0, playing: false, raf: 0, last: 0, index: 0 };

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
        { kind: "block", type: "op_turn_to" },
        { kind: "block", type: "op_wheel_turn" },
        { kind: "block", type: "op_arc" },
        { kind: "block", type: "op_wall_square" },
      ],
    },
    {
      kind: "category",
      name: "Навески",
      categorystyle: "attachment_category",
      contents: [
        { kind: "block", type: "op_attachment" },
        { kind: "block", type: "op_att_stalled" },
        { kind: "block", type: "op_att_accel" },
      ],
    },
    {
      kind: "category",
      name: "Действия",
      categorystyle: "action_category",
      contents: [
        { kind: "block", type: "op_wait" },
        { kind: "block", type: "op_beep" },
        { kind: "block", type: "op_log" },
        { kind: "block", type: "op_battery_check" },
      ],
    },
    {
      kind: "category",
      name: "Робот",
      categorystyle: "robot_category",
      contents: [
        { kind: "block", type: "op_set_speed" },
        { kind: "block", type: "op_set_heading" },
        { kind: "block", type: "op_rush" },
        { kind: "block", type: "op_stop" },
        { kind: "block", type: "op_reset_start" },
      ],
    },
    {
      kind: "category",
      name: "Логика",
      categorystyle: "logic_category",
      contents: [
        { kind: "block", type: "op_if" },
        { kind: "block", type: "op_repeat" },
        { kind: "block", type: "op_parallel" },
        { kind: "block", type: "op_sensor_compare" },
      ],
    },
  ],
};

const theme = Blockly.Theme.defineTheme("op", {
  name: "op",
  base: Blockly.Themes.Classic,
  categoryStyles: {
    motion_category: { colour: "#1d9bf0" },
    attachment_category: { colour: "#00ba7c" },
    action_category: { colour: "#c9a227" },
    logic_category: { colour: "#536471" },
    robot_category: { colour: "#f91880" },
  },
  componentStyles: {
    workspaceBackgroundColour: "#000000",
    toolboxBackgroundColour: "#000000",
    toolboxForegroundColour: "#a6adb4",
    flyoutBackgroundColour: "#16181c",
    flyoutForegroundColour: "#e7e9ea",
    flyoutOpacity: 1,
    scrollbarColour: "#3e4348",
    scrollbarOpacity: 0.7,
    insertionMarkerColour: "#1d9bf0",
    insertionMarkerOpacity: 0.32,
    markerColour: "#1d9bf0",
    cursorColour: "#1d9bf0",
  },
  fontStyle: { family: "-apple-system, 'Segoe UI', Roboto, sans-serif", weight: "500", size: 12 },
});

function numberField(value, min, max, precision) {
  return new Blockly.FieldNumber(value, min, max, precision);
}

const THEN_OPTIONS = [
  ["стоп", "hold"],
  ["на проход", "none"],
];

function thenField() {
  return new Blockly.FieldDropdown(THEN_OPTIONS);
}

Blockly.Blocks.op_mission = {
  init() {
    this.appendDummyInput().appendField("Миссия · команды выполняются по порядку");
    this.appendStatementInput("STEPS").appendField("начало");
    this.setColour("#536471");
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
      .appendField("мм/с ·")
      .appendField(thenField(), "THEN");
    this.setPreviousStatement(true);
    this.setNextStatement(true);
    this.setColour("#1d9bf0");
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
      .appendField("°/с ·")
      .appendField(thenField(), "THEN");
    this.setPreviousStatement(true);
    this.setNextStatement(true);
    this.setColour("#1d9bf0");
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
      .appendField("мм/с ·")
      .appendField(thenField(), "THEN");
    this.setPreviousStatement(true);
    this.setNextStatement(true);
    this.setColour("#1d9bf0");
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
    this.setColour("#00ba7c");
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
    this.setColour("#00ba7c");
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
    this.setColour("#00ba7c");
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
    this.setColour("#f91880");
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
    this.setColour("#536471");
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
    this.setColour("#536471");
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
    this.setColour("#536471");
  },
};

Blockly.Blocks.op_turn_to = {
  init() {
    this.appendDummyInput()
      .appendField("Повернуть на курс")
      .appendField(numberField(90, -360, 360, 5), "HEADING")
      .appendField("° · скорость")
      .appendField(numberField(180, 1, 360, 5), "RATE")
      .appendField("°/с ·")
      .appendField(thenField(), "THEN");
    this.setPreviousStatement(true);
    this.setNextStatement(true);
    this.setColour("#1d9bf0");
    this.setInputsInline(true);
  },
};

Blockly.Blocks.op_wheel_turn = {
  init() {
    this.appendDummyInput()
      .appendField("Пивот")
      .appendField(numberField(45, -360, 360, 5), "ANGLE")
      .appendField("° · колесо")
      .appendField(
        new Blockly.FieldDropdown([
          ["правое", "RIGHT"],
          ["левое", "LEFT"],
        ]),
        "LOCKED"
      )
      .appendField("· скорость")
      .appendField(numberField(120, 1, 360, 5), "RATE")
      .appendField("°/с ·")
      .appendField(thenField(), "THEN");
    this.setPreviousStatement(true);
    this.setNextStatement(true);
    this.setColour("#1d9bf0");
    this.setInputsInline(true);
  },
};

Blockly.Blocks.op_wall_square = {
  init() {
    this.appendDummyInput()
      .appendField("Прижаться к стене · курс")
      .appendField(numberField(0, -360, 360, 5), "HEADING")
      .appendField("° · усилие")
      .appendField(numberField(35, 1, 100, 5), "DUTY")
      .appendField("% ·")
      .appendField(numberField(800, 50, 3000, 50), "DURATION")
      .appendField("мс");
    this.setPreviousStatement(true);
    this.setNextStatement(true);
    this.setColour("#1d9bf0");
    this.setInputsInline(true);
  },
};

Blockly.Blocks.op_att_stalled = {
  init() {
    this.appendDummyInput()
      .appendField("Навеска до упора · порт")
      .appendField(new Blockly.FieldDropdown([["E", "E"], ["F", "F"]]), "PORT")
      .appendField("· скорость")
      .appendField(numberField(400, 1, 1000, 10), "SPEED")
      .appendField("°/с · момент")
      .appendField(numberField(80, 1, 100, 5), "DUTY")
      .appendField("%");
    this.setPreviousStatement(true);
    this.setNextStatement(true);
    this.setColour("#00ba7c");
    this.setInputsInline(true);
  },
};

Blockly.Blocks.op_att_accel = {
  init() {
    this.appendDummyInput()
      .appendField("Ускорение навески")
      .appendField(numberField(600, 10, 2000, 10), "ACCEL")
      .appendField("°/с²");
    this.setPreviousStatement(true);
    this.setNextStatement(true);
    this.setColour("#00ba7c");
    this.setInputsInline(true);
  },
};

Blockly.Blocks.op_log = {
  init() {
    this.appendDummyInput()
      .appendField("Лог")
      .appendField(new Blockly.FieldTextInput("точка 1"), "TEXT");
    this.setPreviousStatement(true);
    this.setNextStatement(true);
    this.setColour("#c9a227");
    this.setInputsInline(true);
  },
};

Blockly.Blocks.op_battery_check = {
  init() {
    this.appendDummyInput().appendField("Проверить заряд батареи");
    this.setPreviousStatement(true);
    this.setNextStatement(true);
    this.setColour("#c9a227");
  },
};

Blockly.Blocks.op_set_speed = {
  init() {
    this.appendDummyInput()
      .appendField("Профиль скорости")
      .appendField(
        new Blockly.FieldDropdown([
          ["FAST", "FAST"],
          ["MEDIUM", "MEDIUM"],
          ["SLOW", "SLOW"],
          ["SLOWW", "SLOWW"],
        ]),
        "PROFILE"
      );
    this.setPreviousStatement(true);
    this.setNextStatement(true);
    this.setColour("#f91880");
    this.setInputsInline(true);
  },
};

Blockly.Blocks.op_set_heading = {
  init() {
    this.appendDummyInput()
      .appendField("Считать курс за")
      .appendField(numberField(0, -360, 360, 5), "HEADING")
      .appendField("°");
    this.setPreviousStatement(true);
    this.setNextStatement(true);
    this.setColour("#f91880");
    this.setInputsInline(true);
  },
};

Blockly.Blocks.op_rush = {
  init() {
    this.appendDummyInput()
      .appendField("Быстрый режим")
      .appendField(
        new Blockly.FieldDropdown([
          ["включить", "true"],
          ["выключить", "false"],
        ]),
        "ENABLED"
      );
    this.setPreviousStatement(true);
    this.setNextStatement(true);
    this.setColour("#f91880");
    this.setInputsInline(true);
  },
};

Blockly.Blocks.op_stop = {
  init() {
    this.appendDummyInput()
      .appendField("Стоп")
      .appendField(
        new Blockly.FieldDropdown([
          ["привод", "drive"],
          ["всё", "all"],
          ["отпустить привод", "release"],
        ]),
        "SCOPE"
      );
    this.setPreviousStatement(true);
    this.setNextStatement(true);
    this.setColour("#f91880");
    this.setInputsInline(true);
  },
};

Blockly.Blocks.op_reset_start = {
  init() {
    this.appendDummyInput().appendField("Сбросить к стартовому состоянию");
    this.setPreviousStatement(true);
    this.setNextStatement(true);
    this.setColour("#f91880");
  },
};

const workspace = Blockly.inject("blockly", {
  toolbox,
  theme,
  media: "./",
  renderer: "zelos",
  trashcan: false,
  // Blockly v12 forces move.drag = false when scrollbars are off,
  // so scrollbars stay logically enabled and are hidden in CSS.
  grid: { spacing: 26, length: 0, snap: false },
  move: { scrollbars: true, drag: true, wheel: false },
  zoom: { controls: false, wheel: true, pinch: true, startScale: 1, maxScale: 1.6, minScale: 0.4 },
  sounds: false,
});

const elements = {
  layout: document.querySelector("#workspace-layout"),
  editorPanel: document.querySelector("#editor-panel"),
  toolboxToggle: document.querySelector("#toolbox-toggle"),
  mapPanel: document.querySelector(".map-panel"),
  mapToggle: document.querySelector("#map-toggle"),
  fileButton: document.querySelector("#file-button"),
  fileMenu: document.querySelector("#file-menu"),
  undoButton: document.querySelector("#undo-button"),
  redoButton: document.querySelector("#redo-button"),
  viewButton: document.querySelector("#view-button"),
  viewMenu: document.querySelector("#view-menu"),
  settingsButton: document.querySelector("#settings-button"),
  settingsDialog: document.querySelector("#settings-dialog"),
  settingsConfirm: document.querySelector("#settings-confirm"),
  settingsReset: document.querySelector("#settings-reset"),
  setSpeed: document.querySelector("#set-speed"),
  setAccel: document.querySelector("#set-accel"),
  setDecel: document.querySelector("#set-decel"),
  setTurnAccel: document.querySelector("#set-turn-accel"),
  setTurnDecel: document.querySelector("#set-turn-decel"),
  setPlan: document.querySelector("#set-plan"),
  setTrail: document.querySelector("#set-trail"),
  setAutosave: document.querySelector("#set-autosave"),
  pathLayer: document.querySelector("#path-layer"),
  status: document.querySelector("#status"),
  startX: document.querySelector("#start-x"),
  startY: document.querySelector("#start-y"),
  startHeading: document.querySelector("#start-heading"),
  fieldWrap: document.querySelector("#field-wrap"),
  fieldMap: document.querySelector("#field-map-image"),
  pathLayer: document.querySelector("#path-layer"),
  robotLayer: document.querySelector("#robot-layer"),
  fullscreenButton: document.querySelector("#fullscreen-button"),
  playButton: document.querySelector("#play-button"),
  seek: document.querySelector("#player-seek"),
  time: document.querySelector("#player-time"),
  openDialog: document.querySelector("#open-dialog"),
  missionList: document.querySelector("#mission-list"),
  saveDialog: document.querySelector("#save-dialog"),
  saveTitle: document.querySelector("#save-title"),
  saveNumber: document.querySelector("#save-number"),
  saveHint: document.querySelector("#save-hint"),
  saveConfirm: document.querySelector("#save-confirm"),
  editDialog: document.querySelector("#edit-dialog"),
  editName: document.querySelector("#edit-name"),
  editNumber: document.querySelector("#edit-number"),
  editColor: document.querySelector("#edit-color"),
  editConfirm: document.querySelector("#edit-confirm"),
};

elements.fieldMap.setAttribute("href", fieldMapUrl);

function blockNumber(block, field) {
  return Number(block.getFieldValue(field));
}

function stepWithThrough(block, step) {
  if (block.getFieldValue("THEN") === "none") step.through = true;
  return step;
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
      return stepWithThrough(block, {
        type: "straight",
        distance_mm: blockNumber(block, "DISTANCE"),
        speed_mm_s: blockNumber(block, "SPEED"),
      });
    case "op_turn":
      return stepWithThrough(block, {
        type: "turn",
        angle_deg: blockNumber(block, "ANGLE"),
        rate_deg_s: blockNumber(block, "RATE"),
      });
    case "op_arc":
      return stepWithThrough(block, {
        type: "arc",
        radius_mm: blockNumber(block, "RADIUS"),
        angle_deg: blockNumber(block, "ANGLE"),
        speed_mm_s: blockNumber(block, "SPEED"),
      });
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
    case "op_turn_to":
      return stepWithThrough(block, {
        type: "turn_to",
        heading_deg: blockNumber(block, "HEADING"),
        rate_deg_s: blockNumber(block, "RATE"),
      });
    case "op_wheel_turn":
      return stepWithThrough(block, {
        type: "wheel_turn",
        angle_deg: blockNumber(block, "ANGLE"),
        locked: block.getFieldValue("LOCKED"),
        rate_deg_s: blockNumber(block, "RATE"),
      });
    case "op_wall_square":
      return {
        type: "wall_square",
        heading_deg: blockNumber(block, "HEADING"),
        duty: blockNumber(block, "DUTY"),
        duration_ms: blockNumber(block, "DURATION"),
      };
    case "op_att_stalled":
      return {
        type: "att_until_stalled",
        port: block.getFieldValue("PORT"),
        speed_deg_s: blockNumber(block, "SPEED"),
        duty_limit: blockNumber(block, "DUTY"),
      };
    case "op_att_accel":
      return { type: "set_att_accel", accel_deg_s2: blockNumber(block, "ACCEL") };
    case "op_log":
      return { type: "log", message: (block.getFieldValue("TEXT") || "").trim() };
    case "op_battery_check":
      return { type: "battery_check" };
    case "op_set_speed":
      return { type: "set_speed", profile: block.getFieldValue("PROFILE") };
    case "op_set_heading":
      return { type: "set_heading", heading_deg: blockNumber(block, "HEADING") };
    case "op_rush":
      return { type: "rush", enabled: block.getFieldValue("ENABLED") === "true" };
    case "op_stop":
      return { type: "stop", scope: block.getFieldValue("SCOPE") };
    case "op_reset_start":
      return { type: "reset_start" };
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
  const name = (missionMeta.name || "").trim();
  if (!name) throw new Error("У миссии должно быть название.");
  return {
    version: 1,
    name,
    color: missionMeta.color,
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
  } else if (step.type === "turn_to") {
    state.heading = step.heading_deg;
  } else if (step.type === "wheel_turn") {
    const delta = step.angle_deg;
    const offset = step.locked === "RIGHT" ? -82.5 : 82.5;
    const start = (state.heading * Math.PI) / 180;
    const ox = offset * Math.cos(start);
    const oy = -offset * Math.sin(start);
    const turned = (delta * Math.PI) / 180;
    const nx = ox * Math.cos(turned) + oy * Math.sin(turned);
    const ny = -ox * Math.sin(turned) + oy * Math.cos(turned);
    state.x += nx - ox;
    state.y += ny - oy;
    state.heading += delta;
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
      state.points.push([
        currentX,
        currentY,
        state.heading + change * (index / segments),
      ]);
    }
    const end = (state.heading + change) * Math.PI / 180;
    state.x += radius * (Math.cos(start) - Math.cos(end));
    state.y += radius * (Math.sin(end) - Math.sin(start));
    state.heading += change;
  }
  if (step.type !== "arc") state.points.push([state.x, state.y, state.heading]);
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

function robotOutsideField(x, y, heading) {
  const radians = (heading * Math.PI) / 180;
  const halfWidth = ROBOT_WIDTH_MM / 2;
  const halfHeight = ROBOT_HEIGHT_MM / 2;
  const extentX =
    Math.abs(Math.cos(radians)) * halfWidth +
    Math.abs(Math.sin(radians)) * halfHeight;
  const extentY =
    Math.abs(Math.sin(radians)) * halfWidth +
    Math.abs(Math.cos(radians)) * halfHeight;
  return (
    x - extentX < 0 ||
    x + extentX > FIELD_WIDTH ||
    y - extentY < 0 ||
    y + extentY > FIELD_HEIGHT
  );
}

function appendRobotMarker(layer, state, markerClass) {
  const robot = document.createElementNS("http://www.w3.org/2000/svg", "g");
  robot.setAttribute("class", "robot-footprint " + markerClass);
  robot.setAttribute(
    "transform",
    "translate(" + mapX(state.x) + " " + mapY(state.y) + ") rotate(" + state.heading + ")"
  );

  const body = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  body.setAttribute("x", -ROBOT_WIDTH_MM / 2);
  body.setAttribute("y", -ROBOT_HEIGHT_MM / 2);
  body.setAttribute("width", ROBOT_WIDTH_MM);
  body.setAttribute("height", ROBOT_HEIGHT_MM);
  body.setAttribute("rx", "10");
  body.setAttribute("class", "robot-body");

  const front = document.createElementNS("http://www.w3.org/2000/svg", "path");
  front.setAttribute(
    "d",
    "M -24 " + -ROBOT_HEIGHT_MM / 2 + " L 0 -42 L 24 " + -ROBOT_HEIGHT_MM / 2 + " Z"
  );
  front.setAttribute("class", "robot-front");
  robot.append(body, front);
  layer.appendChild(robot);
  return robot;
}

function renderMap(mission) {
  const x = mission.start_pose.x_mm;
  const y = mission.start_pose.y_mm;
  const heading = mission.start_pose.heading_deg;
  const start = { x, y, heading, points: [[x, y, heading]], alternate: false };
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

  playerTrail = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  playerTrail.setAttribute("class", "trajectory progress");
  elements.pathLayer.appendChild(playerTrail);

  appendRobotMarker(elements.robotLayer, { x, y, heading }, "start-footprint");
  const startMark = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  startMark.setAttribute("cx", mapX(x));
  startMark.setAttribute("cy", mapY(y));
  startMark.setAttribute("r", "9");
  startMark.setAttribute("class", "start-mark");
  elements.robotLayer.appendChild(startMark);

  playerMarker = appendRobotMarker(
    elements.robotLayer,
    { x, y, heading },
    "player-footprint"
  );

  const outside = endStates.some((state) =>
    state.points.some((point) => robotOutsideField(point[0], point[1], point[2]))
  );
  return { outside, truncated: budget.truncated, endStates };
}

function setStatus(message, error) {
  elements.status.textContent = message;
  elements.status.classList.toggle("error", Boolean(error));
}

function updatePreview() {
  try {
    const mission = currentMission();
    const result = renderMap(mission);
    loadTimeline(buildTimeline(mission));
    if (result.truncated) {
      setStatus("Предпросмотр обрезан после " + MAX_SIMULATION_STEPS + " команд.", true);
    } else if (result.outside) {
      setStatus("Траектория выходит за границы поля.", true);
    } else {
      setStatus("");
    }
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
        THEN: step.through ? "none" : "hold",
      });
      break;
    case "turn":
      block = createBlock("op_turn", {
        ANGLE: step.angle_deg,
        RATE: step.rate_deg_s === undefined ? 180 : step.rate_deg_s,
        THEN: step.through ? "none" : "hold",
      });
      break;
    case "arc":
      block = createBlock("op_arc", {
        RADIUS: step.radius_mm,
        ANGLE: step.angle_deg,
        SPEED: step.speed_mm_s === undefined ? 300 : step.speed_mm_s,
        THEN: step.through ? "none" : "hold",
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
    case "turn_to":
      block = createBlock("op_turn_to", {
        HEADING: step.heading_deg,
        RATE: step.rate_deg_s === undefined ? 180 : step.rate_deg_s,
        THEN: step.through ? "none" : "hold",
      });
      break;
    case "wheel_turn":
      block = createBlock("op_wheel_turn", {
        ANGLE: step.angle_deg,
        LOCKED: step.locked,
        RATE: step.rate_deg_s === undefined ? 120 : step.rate_deg_s,
        THEN: step.through ? "none" : "hold",
      });
      break;
    case "wall_square":
      block = createBlock("op_wall_square", {
        HEADING: step.heading_deg,
        DUTY: step.duty === undefined ? 35 : Math.abs(step.duty),
        DURATION: step.duration_ms === undefined ? 800 : step.duration_ms,
      });
      break;
    case "att_until_stalled":
      block = createBlock("op_att_stalled", {
        PORT: step.port,
        SPEED: step.speed_deg_s,
        DUTY: step.duty_limit === undefined ? 80 : step.duty_limit,
      });
      break;
    case "set_att_accel":
      block = createBlock("op_att_accel", { ACCEL: step.accel_deg_s2 });
      break;
    case "log":
      block = createBlock("op_log", { TEXT: step.message });
      break;
    case "battery_check":
      block = createBlock("op_battery_check", {});
      break;
    case "set_speed":
      block = createBlock("op_set_speed", { PROFILE: step.profile });
      break;
    case "set_heading":
      block = createBlock("op_set_heading", { HEADING: step.heading_deg });
      break;
    case "rush":
      block = createBlock("op_rush", { ENABLED: step.enabled ? "true" : "false" });
      break;
    case "stop":
      block = createBlock("op_stop", { SCOPE: step.scope });
      break;
    case "reset_start":
      block = createBlock("op_reset_start", {});
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

let currentFilename = null;
let missionMeta = { name: "Новая миссия", color: "WHITE" };

function replaceWorkspace(mission, filename) {
  currentFilename = filename || null;
  missionMeta = {
    name: mission.name || "Новая миссия",
    color: mission.color || "WHITE",
  };
  workspace.clear();
  const pose = mission.start_pose || { x_mm: 1000, y_mm: 570, heading_deg: 0 };
  elements.startX.value = pose.x_mm;
  elements.startY.value = pose.y_mm;
  elements.startHeading.value = pose.heading_deg;
  const root = createBlock("op_mission", {});
  connectSequence(root, "STEPS", mission.steps || []);
  Blockly.svgResize(workspace);
  window.requestAnimationFrame(() => workspace.scrollCenter());
  updatePreview();
}

async function fetchMissions() {
  const response = await fetch("/api/missions", { cache: "no-store" });
  if (!response.ok) throw new Error("Не удалось получить список миссий.");
  const data = await response.json();
  return data.missions || [];
}

async function saveMission(filename, mission, previous) {
  const response = await fetch("/api/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename, mission, previous }),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Не удалось сохранить миссию.");
  return result;
}

async function buildArchive() {
  const response = await fetch("/api/build", { method: "POST" });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Не удалось собрать архив.");
  return result;
}

function filenameFor(number) {
  return "mission_" + String(number) + ".json";
}

function nextMissionNumber(missions) {
  return missions.reduce((max, item) => Math.max(max, item.number || 0), 0) + 1;
}


function openDialog(dialog) {
  if (typeof dialog.showModal === "function") dialog.showModal();
  else dialog.setAttribute("open", "");
}

function closeDialog(dialog) {
  if (typeof dialog.close === "function") dialog.close();
  else dialog.removeAttribute("open");
}

function closeFileMenu() {
  elements.fileMenu.hidden = true;
  elements.fileButton.setAttribute("aria-expanded", "false");
}

function toggleFileMenu() {
  const open = elements.fileMenu.hidden;
  elements.fileMenu.hidden = !open;
  elements.fileButton.setAttribute("aria-expanded", String(open));
}

function renderMissionList(missions) {
  elements.missionList.replaceChildren();
  const valid = missions.filter((item) => item.mission);
  if (!valid.length) {
    const empty = document.createElement("p");
    empty.className = "dialog-hint";
    empty.textContent = "В папке missions пока нет миссий.";
    elements.missionList.appendChild(empty);
    return;
  }
  for (const item of valid) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "mission-row";
    if (item.filename === currentFilename) row.classList.add("current");
    const number = document.createElement("span");
    number.className = "mission-number";
    number.textContent = String(item.number).padStart(2, "0");
    const label = document.createElement("span");
    label.className = "mission-name";
    label.textContent = item.mission.name;
    const color = document.createElement("span");
    color.className = "mission-color";
    color.textContent = item.mission.color;
    row.append(number, label, color);
    row.addEventListener("click", () => {
      closeDialog(elements.openDialog);
      replaceWorkspace(item.mission, item.filename);
      setStatus("Открыта " + item.filename);
    });
    elements.missionList.appendChild(row);
  }
}

async function openMissionDialog() {
  closeFileMenu();
  try {
    renderMissionList(await fetchMissions());
    openDialog(elements.openDialog);
  } catch (error) {
    setStatus(error.message, true);
  }
}

function askSaveNumber({ title, defaultNumber, onConfirm }) {
  elements.saveTitle.textContent = title;
  elements.saveNumber.value = String(defaultNumber);
  const sync = () => {
    const number = Number(elements.saveNumber.value);
    elements.saveHint.textContent = Number.isFinite(number) && number > 0
      ? "missions/" + filenameFor(number)
      : "Введи номер от 1 до 999.";
  };
  sync();
  elements.saveNumber.oninput = sync;
  elements.saveConfirm.onclick = async () => {
    const number = Number(elements.saveNumber.value);
    if (!Number.isFinite(number) || number < 1 || number > 999) {
      setStatus("Номер миссии должен быть от 1 до 999.", true);
      return;
    }
    elements.saveConfirm.disabled = true;
    try {
      await onConfirm(number);
      closeDialog(elements.saveDialog);
    } catch (error) {
      setStatus(error.message, true);
    } finally {
      elements.saveConfirm.disabled = false;
    }
  };
  openDialog(elements.saveDialog);
}

async function saveCurrentMission() {
  const mission = currentMission();
  if (currentFilename) {
    const result = await saveMission(currentFilename, mission);
    setStatus("Сохранено: " + result.filename);
    return;
  }
  const missions = await fetchMissions();
  askSaveNumber({
    title: "Сохранить миссию",
    defaultNumber: nextMissionNumber(missions),
    onConfirm: async (number) => {
      const filename = filenameFor(number);
      const result = await saveMission(filename, mission);
      currentFilename = result.filename;
      setStatus("Сохранено: " + result.filename);
    },
  });
}

async function handleBuild() {
  closeFileMenu();
  try {
    setStatus("Собираю архив…");
    const result = await buildArchive();
    setStatus("missions/" + result.archive + " · миссий: " + result.missions);
  } catch (error) {
    setStatus(error.message, true);
  }
}

function createMission() {
  closeFileMenu();
  replaceWorkspace(
    {
      version: 1,
      name: "Новая миссия",
      color: "WHITE",
      start_pose: { x_mm: 1000, y_mm: 570, heading_deg: 0 },
      steps: [{ type: "straight", distance_mm: 200, speed_mm_s: 300 }],
    },
    null
  );
  setStatus("Новая миссия. Сохрани, чтобы выбрать номер.");
}

async function editMission() {
  closeFileMenu();
  const mission = currentMission();
  const missions = await fetchMissions();
  elements.editNumber.value = String(
    currentFilename ? missionNumberFromFilename(currentFilename) : nextMissionNumber(missions)
  );
  elements.editName.value = mission.name;
  elements.editColor.value = mission.color;
  elements.editConfirm.onclick = async () => {
    const number = Number(elements.editNumber.value);
    if (!Number.isFinite(number) || number < 1 || number > 999) {
      setStatus("Номер миссии должен быть от 1 до 999.", true);
      return;
    }
    const name = elements.editName.value.trim();
    if (!name) {
      setStatus("У миссии должно быть название.", true);
      return;
    }
    elements.editConfirm.disabled = true;
    try {
      missionMeta = { name, color: elements.editColor.value };
      const updated = currentMission();
      const filename = filenameFor(number);
      const result = await saveMission(
        filename,
        updated,
        currentFilename && currentFilename !== filename ? currentFilename : null
      );
      currentFilename = result.filename;
      closeDialog(elements.editDialog);
      setStatus("Сохранено: " + result.filename + " · " + updated.color);
    } catch (error) {
      setStatus(error.message, true);
    } finally {
      elements.editConfirm.disabled = false;
    }
  };
  openDialog(elements.editDialog);
}

function missionNumberFromFilename(filename) {
  const match = /^mission_([0-9]{1,3})\.json$/.exec(filename || "");
  return match ? Number(match[1]) : 1;
}


function expandDrive(steps, out = []) {
  for (const step of steps || []) {
    if (step.type === "if") {
      expandDrive(step.then || [], out);
    } else if (step.type === "repeat") {
      for (let index = 0; index < step.times; index += 1) {
        expandDrive(step.steps || [], out);
      }
    } else if (step.type === "parallel") {
      const drive = (step.branches || []).find((branch) => branch.resource === "drive");
      if (drive) expandDrive(drive.steps || [], out);
    } else {
      out.push(step);
    }
  }
  return out;
}

function trapezoid(total, vmax, accel, decel) {
  const accelDistance = (vmax * vmax) / (2 * accel);
  const decelDistance = (vmax * vmax) / (2 * decel);
  let peak = vmax;
  let accelTime = vmax / accel;
  let decelTime = vmax / decel;
  let cruiseTime = 0;
  if (accelDistance + decelDistance >= total) {
    peak = Math.sqrt((2 * total * accel * decel) / (accel + decel));
    accelTime = peak / accel;
    decelTime = peak / decel;
  } else {
    cruiseTime = (total - accelDistance - decelDistance) / vmax;
  }
  const accelLength = 0.5 * accel * accelTime * accelTime;
  const cruiseLength = peak * cruiseTime;
  const duration = accelTime + cruiseTime + decelTime;
  const positionAt = (time) => {
    if (time <= accelTime) return 0.5 * accel * time * time;
    if (time <= accelTime + cruiseTime) {
      return accelLength + peak * (time - accelTime);
    }
    const td = time - accelTime - cruiseTime;
    return accelLength + cruiseLength + peak * td - 0.5 * decel * td * td;
  };
  return { duration: Math.max(duration, PLAYER_DT), positionAt };
}

function buildTimeline(mission) {
  const pose = {
    x: mission.start_pose.x_mm,
    y: mission.start_pose.y_mm,
    h: mission.start_pose.heading_deg,
  };
  const frames = [{ t: 0, x: pose.x, y: pose.y, h: pose.h }];
  let clock = 0;

  for (const step of expandDrive(mission.steps)) {
    if (step.type === "straight") {
      const total = Math.abs(step.distance_mm);
      if (total < 1e-6) continue;
      const direction = Math.sign(step.distance_mm) || 1;
      const speed = Math.max(1, step.speed_mm_s ?? 300);
      const profile = trapezoid(total, speed, settings.accel, settings.decel);
      const radians = (pose.h * Math.PI) / 180;
      const count = Math.max(1, Math.ceil(profile.duration / PLAYER_DT));
      for (let index = 1; index <= count; index += 1) {
        const local = (profile.duration * index) / count;
        const travelled = profile.positionAt(local) * direction;
        frames.push({
          t: clock + local,
          x: pose.x + travelled * Math.sin(radians),
          y: pose.y + travelled * Math.cos(radians),
          h: pose.h,
        });
      }
      const travelled = total * direction;
      pose.x += travelled * Math.sin(radians);
      pose.y += travelled * Math.cos(radians);
      clock += profile.duration;
      frames.push({ t: clock, x: pose.x, y: pose.y, h: pose.h });
    } else if (step.type === "turn") {
      const total = Math.abs(step.angle_deg);
      if (total < 1e-6) continue;
      const direction = Math.sign(step.angle_deg) || 1;
      const rate = Math.max(1, step.rate_deg_s ?? 180);
      const profile = trapezoid(total, rate, settings.turnAccel, settings.turnDecel);
      const count = Math.max(1, Math.ceil(profile.duration / PLAYER_DT));
      for (let index = 1; index <= count; index += 1) {
        const local = (profile.duration * index) / count;
        frames.push({
          t: clock + local,
          x: pose.x,
          y: pose.y,
          h: pose.h + profile.positionAt(local) * direction,
        });
      }
      pose.h += total * direction;
      clock += profile.duration;
      frames.push({ t: clock, x: pose.x, y: pose.y, h: pose.h });
    } else if (step.type === "turn_to") {
      const delta = step.heading_deg - pose.h;
      const total = Math.abs(delta);
      if (total < 1e-6) continue;
      const direction = Math.sign(delta) || 1;
      const rate = Math.max(1, step.rate_deg_s ?? 180);
      const profile = trapezoid(total, rate, settings.turnAccel, settings.turnDecel);
      const count = Math.max(1, Math.ceil(profile.duration / PLAYER_DT));
      for (let index = 1; index <= count; index += 1) {
        const local = (profile.duration * index) / count;
        frames.push({
          t: clock + local,
          x: pose.x,
          y: pose.y,
          h: pose.h + profile.positionAt(local) * direction,
        });
      }
      pose.h = step.heading_deg;
      clock += profile.duration;
      frames.push({ t: clock, x: pose.x, y: pose.y, h: pose.h });
    } else if (step.type === "wheel_turn") {
      const delta = step.angle_deg;
      if (Math.abs(delta) < 1e-6) continue;
      const rate = Math.max(1, step.rate_deg_s ?? 120);
      const profile = trapezoid(Math.abs(delta), rate, settings.turnAccel, settings.turnDecel);
      const offset = step.locked === "RIGHT" ? -82.5 : 82.5;
      const start = (pose.h * Math.PI) / 180;
      const ox = offset * Math.cos(start);
      const oy = -offset * Math.sin(start);
      const count = Math.max(1, Math.ceil(profile.duration / PLAYER_DT));
      for (let index = 1; index <= count; index += 1) {
        const local = (profile.duration * index) / count;
        const turned = ((profile.positionAt(local) * Math.sign(delta)) * Math.PI) / 180;
        const nx = ox * Math.cos(turned) + oy * Math.sin(turned);
        const ny = -ox * Math.sin(turned) + oy * Math.cos(turned);
        frames.push({
          t: clock + local,
          x: pose.x + nx - ox,
          y: pose.y + ny - oy,
          h: pose.h + (turned * 180) / Math.PI,
        });
      }
      const turned = (delta * Math.PI) / 180;
      const nx = ox * Math.cos(turned) + oy * Math.sin(turned);
      const ny = -ox * Math.sin(turned) + oy * Math.cos(turned);
      pose.x += nx - ox;
      pose.y += ny - oy;
      pose.h += delta;
      clock += profile.duration;
      frames.push({ t: clock, x: pose.x, y: pose.y, h: pose.h });
    } else if (step.type === "wall_square") {
      clock += (step.duration_ms ?? 800) / 1000;
      frames.push({ t: clock, x: pose.x, y: pose.y, h: pose.h });
    } else if (step.type === "att_until_stalled") {
      clock += 0.6;
      frames.push({ t: clock, x: pose.x, y: pose.y, h: pose.h });
    } else if (step.type === "arc") {
      const radius = step.radius_mm;
      const change = step.angle_deg * (radius > 0 ? 1 : -1);
      const total = Math.abs((radius * change * Math.PI) / 180);
      if (total < 1e-6) continue;
      const speed = Math.max(1, step.speed_mm_s ?? 300);
      const profile = trapezoid(total, speed, settings.accel, settings.decel);
      const startAngle = (pose.h * Math.PI) / 180;
      const changeRad = (change * Math.PI) / 180;
      const count = Math.max(1, Math.ceil(profile.duration / PLAYER_DT));
      for (let index = 1; index <= count; index += 1) {
        const local = (profile.duration * index) / count;
        const fraction = profile.positionAt(local) / total;
        const angle = startAngle + changeRad * fraction;
        frames.push({
          t: clock + local,
          x: pose.x + radius * (Math.cos(startAngle) - Math.cos(angle)),
          y: pose.y + radius * (Math.sin(angle) - Math.sin(startAngle)),
          h: pose.h + change * fraction,
        });
      }
      pose.x += radius * (Math.cos(startAngle) - Math.cos(startAngle + changeRad));
      pose.y += radius * (Math.sin(startAngle + changeRad) - Math.sin(startAngle));
      pose.h += change;
      clock += profile.duration;
      frames.push({ t: clock, x: pose.x, y: pose.y, h: pose.h });
    } else if (step.type === "wait") {
      clock += step.duration_ms / 1000;
      frames.push({ t: clock, x: pose.x, y: pose.y, h: pose.h });
    } else if (step.type === "attachment") {
      clock += Math.abs(step.angle_deg) / Math.max(1, step.speed_deg_s || 1);
      frames.push({ t: clock, x: pose.x, y: pose.y, h: pose.h });
    } else if (step.type === "beep") {
      clock += step.duration_ms / 1000;
      frames.push({ t: clock, x: pose.x, y: pose.y, h: pose.h });
    }
  }

  return { duration: clock, frames };
}


function frameAt(time) {
  const frames = timeline.frames;
  if (!frames.length) return null;
  let low = 0;
  let high = frames.length - 1;
  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    if (frames[middle].t <= time) low = middle;
    else high = middle - 1;
  }
  return { frame: frames[low], index: low };
}

function renderPlayerState() {
  const found = frameAt(player.time);
  if (!found) return;
  const { frame, index } = found;
  player.index = index;
  if (playerMarker) {
    playerMarker.setAttribute(
      "transform",
      "translate(" + mapX(frame.x) + " " + mapY(frame.y) + ") rotate(" + frame.h + ")"
    );
  }
  if (playerTrail) {
    const points = timeline.frames
      .slice(0, index + 1)
      .map((item) => mapX(item.x) + "," + mapY(item.y));
    playerTrail.setAttribute("points", points.join(" "));
  }
  elements.seek.value = String(
    timeline.duration > 0 ? Math.round((player.time / timeline.duration) * 1000) : 0
  );
  elements.time.textContent =
    player.time.toFixed(1) + " / " + timeline.duration.toFixed(1) + " с";
}

function stopPlayer() {
  player.playing = false;
  window.cancelAnimationFrame(player.raf);
  player.raf = 0;
  elements.fieldWrap.classList.remove("is-playing");
  elements.playButton.classList.remove("is-playing");
  elements.playButton.setAttribute("aria-label", "Воспроизвести предпросмотр");
}

function tickPlayer(now) {
  if (!player.playing) return;
  const delta = Math.min(0.25, (now - player.last) / 1000) * settings.speed;
  player.last = now;
  player.time = Math.min(timeline.duration, player.time + delta);
  renderPlayerState();
  if (player.time >= timeline.duration) {
    stopPlayer();
    return;
  }
  player.raf = window.requestAnimationFrame(tickPlayer);
}

function playPlayer() {
  if (timeline.duration <= 0) return;
  if (player.time >= timeline.duration) player.time = 0;
  player.playing = true;
  player.last = performance.now();
  elements.fieldWrap.classList.add("is-playing");
  elements.playButton.classList.add("is-playing");
  elements.playButton.setAttribute("aria-label", "Пауза");
  player.raf = window.requestAnimationFrame(tickPlayer);
}

function loadTimeline(next) {
  stopPlayer();
  timeline = next;
  player.time = 0;
  player.index = 0;
  elements.fieldWrap.classList.toggle("no-timeline", timeline.duration <= 0);
  renderPlayerState();
}

function setToolboxCollapsed(collapsed) {
  elements.editorPanel.classList.toggle("toolbox-collapsed", collapsed);
  elements.toolboxToggle.setAttribute("aria-expanded", String(!collapsed));
  elements.toolboxToggle.title = collapsed
    ? "Развернуть панель блоков"
    : "Свернуть панель блоков";
  window.localStorage.setItem("op.toolbox", collapsed ? "1" : "0");
  Blockly.svgResize(workspace);
}

function setMapCollapsed(collapsed) {
  elements.layout.classList.toggle("map-collapsed", collapsed);
  elements.mapToggle.setAttribute("aria-expanded", String(!collapsed));
  elements.mapToggle.title = collapsed ? "Развернуть карту" : "Свернуть карту";
  window.localStorage.setItem("op.map", collapsed ? "1" : "0");
  window.requestAnimationFrame(() => Blockly.svgResize(workspace));
}

async function openInitialMission() {
  try {
    const missions = await fetchMissions();
    const valid = missions.filter((item) => item.mission);
    const selected =
      valid.find((item) => item.filename === "mission_1.json") || valid[0];
    if (selected) {
      replaceWorkspace(selected.mission, selected.filename);
    } else {
      createMission();
    }
  } catch (error) {
    createMission();
    setStatus(error.message, true);
  }
}


function decorateToolbox() {
  for (const category of document.querySelectorAll(".blocklyToolboxCategory")) {
    const color = category.style.borderLeftColor;
    if (color) category.style.setProperty("--cat", color);
    const label = category.querySelector(".blocklyToolboxCategoryLabel");
    const container = category.closest(".blocklyToolboxCategoryContainer");
    if (label && container) container.title = label.textContent;
  }
}

function applySettings() {
  elements.pathLayer.classList.toggle("hide-plan", !settings.showPlan);
  elements.pathLayer.classList.toggle("hide-trail", !settings.showTrail);
  if (timeline.duration > 0) updatePreview();
}

function fillSettingsForm() {
  elements.setSpeed.value = String(settings.speed);
  elements.setAccel.value = String(settings.accel);
  elements.setDecel.value = String(settings.decel);
  elements.setTurnAccel.value = String(settings.turnAccel);
  elements.setTurnDecel.value = String(settings.turnDecel);
  elements.setPlan.checked = settings.showPlan;
  elements.setTrail.checked = settings.showTrail;
  elements.setAutosave.checked = settings.autosave;
}

function persistSettings() {
  window.localStorage.setItem("op.settings", JSON.stringify(settings));
  applySettings();
}

function readSettingsForm() {
  const number = (input, fallback) =>
    Number.isFinite(input.valueAsNumber) ? input.valueAsNumber : fallback;
  settings.speed = Number(elements.setSpeed.value) || 1;
  settings.accel = Math.max(100, number(elements.setAccel, 900));
  settings.decel = Math.max(100, number(elements.setDecel, 1100));
  settings.turnAccel = Math.max(60, number(elements.setTurnAccel, 720));
  settings.turnDecel = Math.max(60, number(elements.setTurnDecel, 900));
  settings.showPlan = elements.setPlan.checked;
  settings.showTrail = elements.setTrail.checked;
  settings.autosave = elements.setAutosave.checked;
  persistSettings();
}

function scheduleAutosave() {
  if (!settings.autosave || !currentFilename) return;
  window.clearTimeout(autosaveTimer);
  autosaveTimer = window.setTimeout(async () => {
    try {
      const result = await saveMission(currentFilename, currentMission());
      setStatus("Автосохранение: " + result.filename);
    } catch (error) {
      setStatus(error.message, true);
    }
  }, 1200);
}

function syncViewMenu() {
  const toolboxItem = elements.viewMenu.querySelector('[data-view="toolbox"]');
  const mapItem = elements.viewMenu.querySelector('[data-view="map"]');
  toolboxItem.textContent = elements.editorPanel.classList.contains("toolbox-collapsed")
    ? "Развернуть панель блоков"
    : "Свернуть панель блоков";
  mapItem.textContent = elements.layout.classList.contains("map-collapsed")
    ? "Развернуть карту"
    : "Свернуть карту";
}

function closeViewMenu() {
  elements.viewMenu.hidden = true;
  elements.viewButton.setAttribute("aria-expanded", "false");
}

function toggleViewMenu() {
  const open = elements.viewMenu.hidden;
  elements.viewMenu.hidden = !open;
  elements.viewButton.setAttribute("aria-expanded", String(open));
  if (open) syncViewMenu();
}

elements.fileButton.addEventListener("click", (event) => {
  event.stopPropagation();
  toggleFileMenu();
});

elements.fileMenu.addEventListener("click", (event) => {
  const action = event.target.closest("button[data-action]")?.dataset.action;
  if (!action) return;
  if (action === "open") openMissionDialog();
  else if (action === "save") {
    closeFileMenu();
    saveCurrentMission().catch((error) => setStatus(error.message, true));
  } else if (action === "build") handleBuild();
  else if (action === "create") createMission();
  else if (action === "edit") editMission().catch((error) => setStatus(error.message, true));
});

document.addEventListener("click", (event) => {
  if (!event.target.closest(".file-menu")) closeFileMenu();
  if (!event.target.closest(".view-menu")) closeViewMenu();
});

for (const button of document.querySelectorAll("dialog [data-close]")) {
  button.addEventListener("click", () => closeDialog(button.closest("dialog")));
}

for (const dialog of document.querySelectorAll("dialog")) {
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) closeDialog(dialog);
  });
}

elements.toolboxToggle.addEventListener("click", () => {
  setToolboxCollapsed(!elements.editorPanel.classList.contains("toolbox-collapsed"));
});

elements.mapToggle.addEventListener("click", () => {
  setMapCollapsed(!elements.layout.classList.contains("map-collapsed"));
});

elements.playButton.addEventListener("click", () => {
  if (player.playing) stopPlayer();
  else playPlayer();
});

elements.seek.addEventListener("input", () => {
  const fraction = Number(elements.seek.value) / 1000;
  player.time = Math.max(0, Math.min(1, fraction)) * timeline.duration;
  player.last = performance.now();
  renderPlayerState();
});

elements.fullscreenButton.addEventListener("click", async () => {
  try {
    if (document.fullscreenElement === elements.fieldWrap) {
      await document.exitFullscreen();
    } else {
      await elements.fieldWrap.requestFullscreen();
    }
  } catch (error) {
    setStatus("Не удалось включить полный экран: " + error.message, true);
  }
});

document.addEventListener("fullscreenchange", () => {
  const active = document.fullscreenElement === elements.fieldWrap;
  elements.fullscreenButton.classList.toggle("is-fullscreen", active);
  elements.fullscreenButton.title = active ? "Выйти из полного экрана" : "Полный экран";
  elements.fullscreenButton.setAttribute(
    "aria-label",
    active ? "Выйти из полного экрана" : "Полный экран"
  );
  window.requestAnimationFrame(() => renderPlayerState());
});

for (const input of [elements.startX, elements.startY, elements.startHeading]) {
  input.addEventListener("input", updatePreview);
  input.addEventListener("input", scheduleAutosave);
}

window.addEventListener("resize", () => Blockly.svgResize(workspace));

workspace.addChangeListener((event) => {
  if (event.isUiEvent) return;
  window.clearTimeout(updatePreview.timer);
  updatePreview.timer = window.setTimeout(updatePreview, 120);
  scheduleAutosave();
});

elements.undoButton.addEventListener("click", () => workspace.undo(false));

elements.redoButton.addEventListener("click", () => workspace.undo(true));

elements.viewButton.addEventListener("click", (event) => {
  event.stopPropagation();
  toggleViewMenu();
});

elements.viewMenu.addEventListener("click", (event) => {
  const view = event.target.closest("button[data-view]")?.dataset.view;
  if (!view) return;
  closeViewMenu();
  if (view === "toolbox") {
    setToolboxCollapsed(!elements.editorPanel.classList.contains("toolbox-collapsed"));
  } else if (view === "map") {
    setMapCollapsed(!elements.layout.classList.contains("map-collapsed"));
  } else if (view === "fullscreen") {
    elements.fullscreenButton.click();
  } else if (view === "play") {
    if (player.playing) stopPlayer();
    else playPlayer();
  }
});

elements.settingsButton.addEventListener("click", () => {
  fillSettingsForm();
  openDialog(elements.settingsDialog);
});

elements.settingsConfirm.addEventListener("click", () => {
  readSettingsForm();
  closeDialog(elements.settingsDialog);
  setStatus("Настройки сохранены");
});

elements.settingsReset.addEventListener("click", () => {
  Object.assign(settings, DEFAULT_SETTINGS);
  fillSettingsForm();
  window.localStorage.setItem("op.settings", JSON.stringify(settings));
  applySettings();
});

document.addEventListener("keydown", (event) => {
  if (!event.ctrlKey && !event.metaKey) return;
  const key = event.key.toLowerCase();
  if (key === "s") {
    event.preventDefault();
    saveCurrentMission().catch((error) => setStatus(error.message, true));
  } else if (key === "b") {
    event.preventDefault();
    handleBuild();
  } else if (key === "p") {
    event.preventDefault();
    if (player.playing) stopPlayer();
    else playPlayer();
  }
});

setToolboxCollapsed(window.localStorage.getItem("op.toolbox") === "1");
setMapCollapsed(window.localStorage.getItem("op.map") === "1");
decorateToolbox();
applySettings();
openInitialMission();

