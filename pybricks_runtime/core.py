"""
core.py — соревновательная основа робота: константы настройки, устройства,
точные движения с гироскопом, моторы навесного оборудования.

Измерено и проверено на роботе (PybricksLQR, 28.09–02.10.2026, профиль скорости MEDIUM):
  straight(mm)            — LQR: держит не только курс, но и ЛИНИЮ (в конце ≈0,2 мм от линии)
  turn(°), turn_to(°)     — LQR-поворот на месте (средняя ошибка 0,2°, на 22% быстрее PI)
  wheel_turn(°, locked=…) — LQR-поворот вокруг стоящего колеса (тот же цикл, что у turn(); 6 прогонов
                            wheel_turn_test, средняя ошибка ≈0,3°)
  arc(r, °)               — DriveBase.arc с гироскопом (на роботе курс в конце 0,33° в среднем)
  rush()                  — быстрый режим до конца миссии (возвращение в базу), см. RUSH_*; на роботе не измерялся
Отдельно на роботе не измерялось: wall_square(°), профили FAST / SLOW / SLOWW.
У каждого движения есть таймаут, оно возвращает True (успех) / False (таймаут, упор).
then=Stop.NONE — только если следующая команда тоже движение: иначе робот продолжит ехать (straight,
arc) или вращаться (turn, wheel_turn), пока его не остановит следующее движение.

Отладочные флаги (раздел 1): DEBUG_LOG — журнал движений, DEBUG_BEEP — служебные писки,
DEBUG_RAISE — пробрасывать исключения из миссии в меню с полным traceback.
На соревнованиях DEBUG_LOG = DEBUG_BEEP = False: каждый print и beep стоит времени.
Калибровка под железо — в разделе 1 (WHEEL_DIAMETER, AXLE_TRACK, GYRO_HEADING_CORRECTION,
SPEED_PROFILES, RUSH_*); сводка значений — calibration_report().

Частоты beep — под прошивку 4.1.0+: до 4.0.1 хаб пищал вдвое выше заданного, поэтому значения
удвоены (звучат так же, как раньше). На прошивке 4.0.1 они прозвучат на октаву выше.

Режимов PI, трасс и тестовых инструментов в этом файле нет — они в PybricksLQR/hub/core.py.
Если робот изменится (шины, вес, мат), перемерьте по PybricksLQR/README.md и
перенесите константы LQR_* и STRAIGHT_LQR_* в этот файл (имена совпадают).
"""

from pybricks.hubs import PrimeHub
from pybricks.pupdevices import Motor
from pybricks.parameters import Port, Direction, Button, Color, Icon, Stop, Axis
from pybricks.robotics import DriveBase
from pybricks.tools import wait, StopWatch

from config import REVERSE_DRIVE_MOTORS


# =====================================================================
# 1. КОНСТАНТЫ НАСТРОЙКИ — калибровка под поле и робота только здесь
# =====================================================================

# --- Порты ---
LEFT_DRIVE_PORT = Port.B
RIGHT_DRIVE_PORT = Port.A
ATT_LEFT_PORT = Port.E
ATT_RIGHT_PORT = Port.F

# --- Геометрия, мм ---
WHEEL_DIAMETER = 62.4             # измерьте, проехав 1 м прямо, и поправьте
AXLE_TRACK = 165                  # расстояние между точками касания колёс с полом

# --- Профили скорости ---
# speed: мм/с, accel: мм/с², turn: °/с (поворот на месте), turn_accel: °/с².
# Большой мотор SPIKE ≈1000 °/с → с колесом 62.4 мм предел ≈540 мм/с.
# Если мотор упрётся в свой предел, на гиро-коррекцию не останется запаса, поэтому
# при запуске профили ограничиваются долей SPEED_HEADROOM от максимума.
FAST = "FAST"
MEDIUM = "MEDIUM"
SLOW = "SLOW"
SLOWW = "SLOWW"
SPEED_PROFILES = {
    FAST:   {"speed": 450, "accel": 1000, "turn": 250, "turn_accel": 1000},
    MEDIUM: {"speed": 350, "accel": 700,  "turn": 180, "turn_accel": 700},
    SLOW:   {"speed": 160, "accel": 320,  "turn": 100, "turn_accel": 300},
    SLOWW:  {"speed": 110, "accel": 220,  "turn": 70,  "turn_accel": 200},
}
DEFAULT_PROFILE = MEDIUM
SPEED_HEADROOM = 0.85

# --- Езда прямо (LQR: удержание линии) ---
# Линия — точка, где начался straight(), и целевой курс. Боковое смещение от линии y
# считается по одометрии (пройденное за цикл Δs × ошибка курса ψ), коррекция:
#     u = k_ψ·ψ − σ·(k_y·y + k_z·∫y) − k_ω·ω
# Если робот проехал несколько мм с неверным курсом, он не только исправляет курс, но и возвращается на линию.
# Коэффициенты зависят от скорости (таблица pc/design_straight.py, интерполяция).
# Ограничение: если колесо проскальзывает вбок, ни одометрия, ни гироскоп этого не видят.
STRAIGHT_LQR_V = (50, 100, 200, 300, 400, 500,)
STRAIGHT_LQR_K = (                # (k_y, k_ψ, k_ω, k_z) для каждой скорости
    (3.399, 3.674, 0.2607, 0.09825,),
    (3.341, 4.616, 0.3154, 0.09789,),
    (3.297, 6.174, 0.4012, 0.09732,),
    (3.271, 7.492, 0.4699, 0.09686,),
    (3.253, 8.668, 0.5285, 0.09647,),
    (3.237, 9.743, 0.5803, 0.09612,),
)
STRAIGHT_MAX_CORRECTION = 40      # °/с, предел коррекции
STRAIGHT_MIN_SPEED = 40           # мм/с, скорость на старте и финише
STRAIGHT_PREALIGN = 3.0           # °, если ошибка на старте больше — сначала доворачиваем
STRAIGHT_LINE_PSI = 3.0           # °, предел угла возврата на линию (чтобы и при большом смещении не уходил вкось)
STRAIGHT_Z_LIMIT = 60.0           # мм·с, предел накопленного смещения
STRAIGHT_OMEGA_TAU = 0.03         # с, фильтр ω: курс робота дрожит с частотой ≈10 Гц на ±4 °/с
                                  # (straight_test 2026-09-29) — это не должно попадать в команду
STRAIGHT_LINE_CARRY_MS = 300      # мс, следующий straight после then=Stop.NONE сохраняет линию

# --- Дуга (arc) ---
# arc() — DriveBase.arc с гироскопом. LQR-дуга (держит саму дугу, как straight() линию) осталась только в
# PybricksLQR/hub/core.py (ARC_MODE = "LQR"): на роботе (arc_test 2026-10-02, 6 дуг R 150–300 мм) DriveBase.arc
# не хуже по курсу (0,33° в среднем / 0,53° наибольшая против 0,30° / 0,50° у LQR после доводки) и быстрее
# (10,8 с против 12,0 с).

# --- Поворот (общее) ---
TURN_SETTLE_RATE = 3              # °/с, медленнее этого робот считается остановившимся

# --- LQR-поворот ---
# Поворотом управляем сами — run() напрямую на моторы, каждые 10 мс.
# Измерено на роботе: внутренняя цель мотора (reference) идёт впереди робота, а
# при повороте на месте шины сильно трутся. Поворот состоит из трёх этапов:
#   0) преднатяг — чтобы стронуть стоящего робота, выводим цель вперёд; профиль начинается
#      с фактической скорости робота (ни задержки, ни рывка);
#   1) весь поворот — один непрерывный профиль (разгон → постоянная → торможение до LQR_V_END),
#      LQR отслеживает: угол, скорость, опережение цели, накопленную ошибку;
#      «потолок» по оставшемуся углу не даёт роботу подойти к цели слишком быстро;
#   2) когда до цели остаётся ω·STOP_T — brake, робот останавливается за счёт трения. STOP_T подстраивается сам.
# Модель (pc/servo_model.py, sysid на роботе 2026-09-28; полностью — PybricksLQR/data/servo.json):
LQR_GAIN = 1.090                  # робот поворачивается во столько раз быстрее команды
LQR_SERVO_KP = 2427               # 1/с², жёсткость сервопривода мотора (в пересчёте на робота)
LQR_FRICTION = 6923               # °/с², трение при движении
# Обратная связь (pc/design_lqr.py): ошибка угла, ошибка скорости, ошибка опережения, накопленная ошибка
LQR_K = (13.23, 0.404, 22.24, 17.09,)
LQR_ACCEL_MAX = 1000              # °/с², предел ускорения профиля
LQR_MOTOR_ACCEL = 5000            # °/с², ускорение run() приводных моторов (по умолчанию в Pybricks 2000 — медленно)
LQR_PRELOAD_V = 60                # °/с, преднатяг: пока робот не тронулся, выводим цель вперёд с этой скоростью
LQR_PRELOAD_GO = 8                # °/с, если робот вращается быстрее — профиль начинается
LQR_PRELOAD_MS = 250              # мс, максимальная длительность преднатяга
LQR_V_END = 50                    # °/с, подходим к цели с этой скоростью: на роботе при 35–70 °/с
                                  # остановка самая стабильная (на малой скорости робот едет рывками, остановка случайна)
LQR_CAP_MARGIN = 1.15             # «потолок»: команда ≤ это × √(v_end² + 2·a·остаток)
LQR_SLEW = 2500                   # °/с², команда за один цикл меняется не более чем на это × LOOP_MS
LQR_LEAD_TAU = 0.04               # с, сглаживание упреждающего значения опережения (чтобы не было скачка при смене ускорения)
LQR_STOP_T = 0.042                # с, brake, когда до цели остаётся ω·STOP_T (значение, выученное на роботе, 2026-09-29)
LQR_STOP_ADAPT = 0.3              # после каждого поворота приближаем STOP_T к измеренному значению на эту долю
LQR_STOP_MIN_W = 35               # °/с, STOP_T обучается только на остановках быстрее этого
LQR_SETTLE_MS = 30                # мс, если после brake робот стоит неподвижно столько — измеряем ошибку
LQR_FIX_TOL = 0.6                 # °, если ошибка больше — медленная коррекция
LQR_FIX_V = 20                    # °/с, скорость коррекции
LQR_FIX_TRIES = 1                 # число попыток коррекции
GYRO_RATE_SIGN = -1               # ω = GYRO_RATE_SIGN · angular_velocity(Axis.Z); проверено sysid
LQR_INT_ZONE = 5.0                # °, интеграл накапливается, только когда ошибка меньше этого
LQR_INT_LIMIT = 1.0               # °·с, предел интеграла

# --- LQR-поворот вокруг колеса (wheel_turn) ---
# Тот же цикл, что у turn(): преднатяг, профиль, LQR по 4 величинам, brake за ω·STOP_T до цели.
# Опорное колесо весь поворот стоит в hold, второе колесо крутит один мотор (передача WHEEL_TURN_K).
# Модель снята на роботе по трассе 90° вокруг правого колеса (wheel_turn_test 2026-10-02,
# PybricksLQR/data/pivot.json): инерция ×1,46 и трение ×0,40 от поворота на месте. Прежняя оценка
# (×2,3 и ×1,2) почти вдвое переоценивала трение: при торможении регулятор подталкивал мотор вперёд,
# робот держал скорость дольше профиля и в конце резко тормозил. Новые значения — из
# PybricksLQR/hub/core.py (там же, как их обновить по следующему тесту).
LQR_PIVOT_GAIN = 1.050            # как LQR_GAIN, по трассе
LQR_PIVOT_KP = 3331               # 1/с², жёсткость серво в градусах робота
LQR_PIVOT_FRICTION = 1920         # °/с², трение в движении
LQR_PIVOT_K = (15.09, 0.5694, 41.24, 19.46,)
LQR_PIVOT_PRELOAD_V = 40          # °/с, преднатяг: вокруг колеса робот трогается легче, при 60 на малых углах
                                  # он срывается рывком и перелетает (3° вокруг левого: перелёт 1,2–2,1°)
LQR_PIVOT_PRELOAD_MOVE = 0.4      # °, преднатяг идёт, пока движущийся мотор реально не повернёт робота на столько.
                                  # Одного гироскопа мало: опорное колесо в hold пружинит, корпус качается на
                                  # 45–56 °/с, а колесо ещё стоит (трасса −90° вокруг правого, wheel_turn_test
                                  # 2026-10-02) — профиль стартовал рано, команда срезалась, робот замирал на 80 мс
LQR_PIVOT_ACCEL_MAX = 700         # °/с², предел ускорения профиля: один мотор разгоняет цель вдвое медленнее
LQR_PIVOT_DECEL_MAX = 400         # °/с², торможение профиля. При 700 робот в конце не успевал: трассы (wheel_turn_test
                                  # 2026-10-02) — робот тормозит на 250–500 °/с² вокруг левого колеса и 470–1000
                                  # вокруг правого, к brake подходил на 80–160 °/с вместо 50, доезд гулял на ±1–2°
# с, начальные значения по направлениям: опора правое колесо угол > 0, < 0; опора левое > 0, < 0.
# Доезд после brake на роботе разный — с общим STOP_T одни направления недоезжали, другие перелетали;
# вокруг левого колеса при угле > 0 робот доезжает почти вдвое дольше. На медленном подходе (торможение 400 °/с²)
# доезд длиннее, чем на быстром: значения — по поворотам на 45–90° с подходом 35–100 °/с (wheel_turn_test
# 2026-10-02, прогоны 3–5) и по тому, что выучилось в пятом прогоне. Каждое учится отдельно.
LQR_PIVOT_STOP_T = (0.030, 0.034, 0.057, 0.040,)

# --- Быстрый режим rush() (возвращение в базу) ---
# После rush() и до конца миссии точность меняется на время:
#   - после поворота нет LQR-коррекции, даже если ошибка больше LQR_FIX_TOL;
#   - straight() и arc() доворачивают на месте только при ошибке курса больше RUSH_PREALIGN, меньшую
#     исправляют на ходу;
#   - turn()/wheel_turn() с then=Stop.NONE не сбрасывают скорость до LQR_V_END, а отдают робота следующему
#     движению на скорости до RUSH_V_END — заранее, за ω²/(2·turn_accel профиля) до цели: столько робот
#     докрутит, пока DriveBase в следующем straight() гасит вращение. Следующим лучше ставить straight():
#     DriveBase.arc считает дугу от фактического курса и закончит её на эти градусы раньше;
#   - arc() с then=Stop.NONE так же отдаёт робота следующему straight() заранее (дуга вращается со скоростью
#     speed/radius: чтобы остаток вращения уложился в RUSH_LEAD_MAX, радиус на FAST — от ≈180 мм).
# Без остановок идут только переходы с then=Stop.NONE. Поворот на месте (turn) всё равно требует остановки
# движения вперёд — на ходу угол проходят дугой arc().
# На роботе не измерялось: если после такого поворота робот перекручивает — уменьшите RUSH_V_END.
RUSH_V_END = 120                  # °/с
RUSH_LEAD_MAX = 10.0              # °, не отдаём робота раньше, чем за столько градусов до цели
RUSH_PREALIGN = 15.0              # °, должно быть больше RUSH_LEAD_MAX

# --- Цикл и таймауты ---
LOOP_MS = 10
TIMEOUT_FACTOR = 2.0              # таймаут = ожидаемое время × этот коэффициент
TIMEOUT_EXTRA_MS = 1000           # + постоянный запас
STALL_GRACE_MS = 300              # в начале движения упор не проверяем
ABORT_ON_FAIL = False             # True: при таймауте/упоре миссия прерывается; False: продолжается

# --- Моторы навесного оборудования ---
ATT_MAX_SPEED = 1000              # °/с
ATT_DEFAULT_ACCEL = 3000          # °/с²
ATT_STALL_TIMEOUT_MS = 3000

# --- Батарея и гироскоп ---
BATTERY_WARN_MV = 7800
BATTERY_LOW_MV = 7400
BATTERY_BEEP_PERIOD_MS = 25000
IMU_READY_TIMEOUT_MS = 4000
GYRO_HEADING_CORRECTION = 361.35  # сколько градусов хаб насчитывает за полный оборот (инструмент «G»; в хабе
                                  # с 02.10.2026 — 361.3488). В коде — чтобы не потерять при перепрошивке хаба;
                                  # при смене хаба перемерьте. None — значение, сохранённое в хабе.
                                  # Прошивка принимает только 345–375, иначе программа упадёт при старте
GYRO_CAL_TURNS = 3

# --- Отладка и звук ---
DEBUG_RAISE = False               # True: полный traceback ошибки в миссии (для тренировок)
DEBUG_LOG = True                  # True: журнал движений; на соревнованиях False — каждый print стоит времени
DEBUG_BEEP = True                 # True: служебные писки; на соревнованиях False — ни одного лишнего сигнала

LEFT = "left"
RIGHT = "right"


# =====================================================================
# 2. УСТРОЙСТВА
# =====================================================================

hub = PrimeHub(top_side=Axis.Z, front_side=-Axis.Y)

if REVERSE_DRIVE_MOTORS:
    left_motor = Motor(LEFT_DRIVE_PORT, Direction.CLOCKWISE)
    right_motor = Motor(RIGHT_DRIVE_PORT, Direction.COUNTERCLOCKWISE)
else:
    left_motor = Motor(LEFT_DRIVE_PORT, Direction.COUNTERCLOCKWISE)
    right_motor = Motor(RIGHT_DRIVE_PORT)
att_left = Motor(ATT_LEFT_PORT)
att_right = Motor(ATT_RIGHT_PORT)

robot = DriveBase(left_motor, right_motor, WHEEL_DIAMETER, AXLE_TRACK)
robot.use_gyro(True)

# LQR-повороту нужно, чтобы внутренняя цель моторов могла быстро уходить вперёд. DriveBase
# использует свои настройки, это влияет только на прямые команды моторам (run/hold).
try:
    for _m in (left_motor, right_motor):
        _lim = _m.control.limits()
        _m.control.limits(_lim[0], LQR_MOTOR_ACCEL, _lim[2])
except Exception as _e:
    print("LQR: не удалось изменить ускорение моторов:", _e)

PI = 3.14159265
# Пределы считаются от фактического максимума мотора (с запасом на гиро-коррекцию).
_MOTOR_MAX = min(left_motor.control.limits()[0], right_motor.control.limits()[0])
MAX_DRIVE_SPEED = _MOTOR_MAX * PI * WHEEL_DIAMETER / 360 * SPEED_HEADROOM  # мм/с
MAX_TURN_RATE = MAX_DRIVE_SPEED * 360 / (PI * AXLE_TRACK)                  # °/с, на месте
MAX_WHEEL_TURN_RATE = MAX_TURN_RATE / 2                                    # °/с, одним колесом
WHEEL_TURN_K = 2 * AXLE_TRACK / WHEEL_DIAMETER  # °/с робота → °/с движущегося мотора
SPIN_K = AXLE_TRACK / WHEEL_DIAMETER            # °/с робота → °/с каждого мотора (поворот на месте)
LQR_U_MAX = MAX_TURN_RATE / SPEED_HEADROOM      # °/с, полный предел моторов

_clock = StopWatch()              # общие часы для журнала и таймаутов
_target_heading = 0.0             # абсолютный целевой курс на поле, °
_profile = SPEED_PROFILES[DEFAULT_PROFILE]
_att_accel = ATT_DEFAULT_ACCEL
_att_deadline = {}                # id(мотор) → время таймаута (для att_wait)
_att_start = {}                   # id(мотор) → угол в начале последнего att_run (для att_wait с angle)
_att_pending = set()              # id(мотор): новое ускорение ещё не применено (мотор был занят)
_arc_v = None                     # straight_speed, которая сейчас стоит в DriveBase (для DriveBase.arc)
_stop_t = LQR_STOP_T              # обучаемый STOP_T (пока программа работает)
_pivot_stop_t = LQR_PIVOT_STOP_T  # то же для поворота вокруг колеса, по 4 направлениям (см. LQR_PIVOT_STOP_T)
_line_carry = None                # при then=Stop.NONE: (курс, y, ∫y, время) — для следующего straight
_rush = False                     # быстрый режим rush(): до конца миссии


class MoveError(Exception):
    pass


# =====================================================================
# 3. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =====================================================================

def log(*parts):
    if DEBUG_LOG:
        print("{:>7}".format(_clock.time()), *parts)


def beep(frequency_hz=880, duration_ms=80):
    """
    Служебный сигнал миссии. При DEBUG_BEEP = False молчит: на соревнованиях
    каждый beep — это ~0,1 с ожидания, а отладочные метки там не нужны.
    """
    if DEBUG_BEEP:
        hub.speaker.beep(frequency_hz, duration_ms)


def _clamp(x, low, high):
    return low if x < low else high if x > high else x


def _auto_timeout(amount, speed, accel):
    """Верхняя оценка времени трапециевидного профиля × запас, мс."""
    speed = max(abs(speed), 1)
    seconds = abs(amount) / speed + speed / max(accel, 1)
    return int(seconds * 1000 * TIMEOUT_FACTOR) + TIMEOUT_EXTRA_MS


def _fail(reason):
    """Движение не завершено: журнал + звук, при необходимости — прервать миссию."""
    log("!!", reason)
    beep(600, 60)
    if ABORT_ON_FAIL:
        raise MoveError(reason)
    return False


def _wait_done(is_done, timeout, name, on_timeout):
    """Ждать, пока is_done() не вернёт True; при таймауте вызывается on_timeout()."""
    timer = StopWatch()
    while not is_done():
        if timer.time() > timeout:
            on_timeout()
            return _fail("таймаут " + name)
        wait(5)
    return True


def _hold_robot():
    # В Pybricks hold() — это «проехать 0 мм». Пока активен drive(), он считается не от
    # фактического состояния, а от внутренней траектории прошивки (reference), а она
    # может быть впереди робота — тогда робот проезжает лишнее, стремясь дойти до той точки.
    # Сначала stop(): контроллер выключается, и hold начинается от реально измеренного состояния.
    # hold_test (2026-09-29): из 4 способов остановки этот самый точный.
    robot.stop()
    if hasattr(robot, "hold"):    # Pybricks v4+
        robot.hold()
    else:                         # v3.x
        robot.straight(0)


def _hold_motor(motor):
    """Удерживать мотор там, где он реально стоит (причина — в _hold_robot)."""
    motor.stop()
    motor.hold()


def _finish_drive(then):
    if then == Stop.HOLD:
        _hold_robot()
    elif then == Stop.BRAKE:
        robot.brake()
    elif then == Stop.COAST:
        robot.stop()
    # Stop.NONE: не останавливаемся — следующее движение плавно продолжит


def limit_profiles():
    for name in SPEED_PROFILES:
        p = SPEED_PROFILES[name]
        if p["speed"] > MAX_DRIVE_SPEED:
            log("Профиль", name, "speed", p["speed"], "->", int(MAX_DRIVE_SPEED))
            p["speed"] = int(MAX_DRIVE_SPEED)
        if p["turn"] > MAX_TURN_RATE:
            log("Профиль", name, "turn", p["turn"], "->", int(MAX_TURN_RATE))
            p["turn"] = int(MAX_TURN_RATE)


def calibration_report():
    """
    Что перемерять при смене робота, колёс или мата. Вызывается вручную из консоли
    (или из миссии-теста); в обычных миссиях не используется и время не тратит.
    """
    log("== КАЛИБРОВКА ==")
    log("колесо", WHEEL_DIAMETER, "мм · колея", AXLE_TRACK, "мм")
    log("гироскоп", GYRO_HEADING_CORRECTION, "°/оборот · проверка", GYRO_CAL_TURNS, "оборота")
    log("мотор", int(_MOTOR_MAX), "°/с →", int(MAX_DRIVE_SPEED), "мм/с · поворот", int(MAX_TURN_RATE), "°/с")
    for name in (FAST, MEDIUM, SLOW, SLOWW):
        p = SPEED_PROFILES[name]
        log(" ", name, p["speed"], "мм/с ·", p["accel"], "мм/с² ·", p["turn"], "°/с ·",
            p["turn_accel"], "°/с²")
    log("rush", RUSH_V_END, "°/с выход ·", RUSH_LEAD_MAX, "° ранний выход ·",
        RUSH_PREALIGN, "° доворот")
    log("стык", STRAIGHT_LINE_CARRY_MS, "мс перенос линии ·", LOOP_MS, "мс цикл ·",
        STALL_GRACE_MS, "мс до проверки упора")


def _drive_settings():
    """Настройки DriveBase из профиля: нужны для arc() и для ограничения ускорения drive()."""
    global _arc_v
    robot.settings(
        straight_speed=int(_profile["speed"]),
        straight_acceleration=int(_profile["accel"]),
        turn_rate=int(_profile["turn"]),
        turn_acceleration=int(_profile["turn_accel"]),
    )
    _arc_v = int(_profile["speed"])


def set_speed(name):
    """Профиль скорости: FAST / MEDIUM / SLOW / SLOWW."""
    global _profile
    _profile = SPEED_PROFILES[name]
    try:
        _drive_settings()
    except OSError:
        # Прошивка может не менять настройки, пока DriveBase активен (после движения робот удерживает
        # позицию): на миг отпускаем, меняем и снова удерживаем робота там, где он стоит.
        # Если робот ехал (предыдущее движение с then=Stop.NONE), он остановится.
        robot.stop()
        _drive_settings()
        _hold_robot()


def set_heading(heading=0):
    """Принять текущий курс робота за `heading` градусов на поле."""
    global _target_heading, _line_carry
    heading = round(heading)
    robot.reset(0, heading)       # при use_gyro(True) гироскоп тоже устанавливается в это значение
    _target_heading = heading
    _line_carry = None            # линия привязана к прежнему курсу — после сброса она не годится


def rush(on=True):
    """
    Быстрый режим до конца миссии (возвращение в базу): точность меняется на время, подробно — у RUSH_*.
    rush(False) — снова точный режим. reset_start() выключает его перед каждой миссией.
    """
    global _rush
    _rush = on


# =====================================================================
# 4. ЕЗДА ПРЯМО (гироскоп + одометрия)
#
# Основная идея — АБСОЛЮТНЫЙ курс. _target_heading — курс на поле
# (курс на старте = 0°, положительный — по часовой стрелке). turn(90) прибавляет 90°
# не к фактическому курсу, а к целевому, поэтому ошибка 0.5° одного поворота
# не переходит на следующий поворот — ошибки не накапливаются.
# =====================================================================

def straight(distance, speed=None, heading=None, then=Stop.HOLD, timeout=None, until=None):
    """
    Езда прямо с гироскопом, distance мм (отрицательное — назад).
    speed — мм/с (только для этого движения); если не задано — скорость профиля.
    heading — абсолютный курс, °; если не задан — сохраняется текущий целевой курс.
    until — функция; если она вернёт True, движение завершается досрочно.
    Результат: True — успех, False — таймаут или упор.
    """
    global _target_heading, _line_carry
    if heading is not None:
        _target_heading = heading
    target = _target_heading
    carry = _line_carry
    _line_carry = None

    # Если робота сильно развернуло (столкновение), сначала выравниваемся на месте,
    # иначе он будет уходить вбок на протяжении всего пути.
    if abs(target - hub.imu.heading()) > (RUSH_PREALIGN if _rush else STRAIGHT_PREALIGN):
        turn_to(target)
        carry = None

    v_max = min(abs(speed), MAX_DRIVE_SPEED) if speed else _profile["speed"]
    accel = _profile["accel"]
    direction = 1 if distance >= 0 else -1
    total = abs(distance)
    v_end = v_max if then == Stop.NONE else STRAIGHT_MIN_SPEED
    v_start = max(STRAIGHT_MIN_SPEED, abs(robot.state()[1]))
    if timeout is None:
        timeout = _auto_timeout(total, v_max, accel)

    # Линия: эта точка + курс target. Если предыдущий straight(then=Stop.NONE) продолжается
    # без остановки тем же курсом — его линия и смещение сохраняются.
    y = 0.0                       # боковое смещение от линии, мм (положительное — по часовой стрелке от курса)
    y_int = 0.0                   # ∫y dt, мм·с
    # Перенос линии — только в том же направлении: при езде назад знак y уже учтён
    # множителем direction, поэтому чужое смещение увело бы робота не в ту сторону.
    if (carry is not None and carry[0] == target and carry[3] == direction
            and _clock.time() - carry[4] <= STRAIGHT_LINE_CARRY_MS):
        y, y_int = carry[1], carry[2]
    omega_f = None                # отфильтрованная ω

    start = robot.distance()
    last_d = start
    timer = StopWatch()
    last_time = 0
    ok = True

    while True:
        d = robot.distance()
        traveled = abs(d - start)
        remaining = total - traveled
        if remaining <= 0:
            break
        if until is not None and until():
            break
        now = timer.time()
        if now > timeout:
            ok = _fail("таймаут straight({})".format(distance))
            break
        if now > STALL_GRACE_MS and robot.stalled():
            ok = _fail("упор straight({})".format(distance))
            break

        # 1) Профиль скорости (v² = v0² + 2·a·s): в начале равномерный разгон,
        #    в конце торможение — колёса не проскальзывают, робот точно останавливается.
        v = min(v_max,
                (v_start * v_start + 2 * accel * traveled) ** 0.5,
                (v_end * v_end + 2 * accel * remaining) ** 0.5)

        # 2) Состояние: ошибка курса ψ (гироскоп), смещение от линии y (одометрия), ω (гироскоп).
        #    ошибка = целевой курс − гироскоп (положительная ошибка → нужно повернуть вправо).
        #    y: пройденное Δs (назад — отрицательное) × ошибка курса (малый угол: sin ψ ≈ ψ).
        error = target - hub.imu.heading()
        dt = (now - last_time) / 1000
        last_time = now
        y -= (d - last_d) * error * 0.0174533
        last_d = d
        omega = GYRO_RATE_SIGN * hub.imu.angular_velocity(Axis.Z)
        if omega_f is None:
            omega_f = omega
        else:
            omega_f += (omega - omega_f) * dt / (STRAIGHT_OMEGA_TAU + dt)

        # 3) LQR-коррекция. σ·y — смещение с учётом направления движения (при езде назад
        #    направление возврата на линию меняется). Член линии ограничен: даже при большом
        #    смещении робот не поворачивает к линии на угол больше STRAIGHT_LINE_PSI.
        #    Коррекция передаётся в drive() как скорость поворота, а DriveBase превращает её
        #    в разницу скоростей левого/правого колеса. Знак поворота одинаков и при езде
        #    вперёд, и назад (положительный = по часовой стрелке).
        k = _straight_gains(v)
        line = _clamp(direction * (k[0] * y + k[3] * y_int),
                      -k[1] * STRAIGHT_LINE_PSI, k[1] * STRAIGHT_LINE_PSI)
        u = k[1] * error - line - k[2] * omega_f
        correction = _clamp(u, -STRAIGHT_MAX_CORRECTION, STRAIGHT_MAX_CORRECTION)
        if correction == u:       # если упёрлись в предел — интеграл не накапливается
            y_int = _clamp(y_int + y * dt, -STRAIGHT_Z_LIMIT, STRAIGHT_Z_LIMIT)

        robot.drive(direction * v, correction)
        wait(LOOP_MS)

    if ok or then != Stop.NONE:
        _finish_drive(then)
    else:
        _hold_robot()             # таймаут/упор при Stop.NONE: стоим (иначе drive() едет дальше, как в arc())
    psi_end = hub.imu.heading() - target
    if then == Stop.NONE and ok:
        _line_carry = (target, y, y_int, direction, _clock.time())
    log("straight {} -> {:.1f} мм, ошибка курса {:.1f}°, от линии {:.1f} мм".format(
        distance, robot.distance() - start, -psi_end, y))
    return ok


def _straight_gains(v):
    """Коэффициенты LQR для скорости v (линейная интерполяция по таблице STRAIGHT_LQR_V)."""
    vs = STRAIGHT_LQR_V
    ks = STRAIGHT_LQR_K
    if v <= vs[0] or len(ks) == 1:
        return ks[0]
    for i in range(1, len(vs)):
        if v <= vs[i]:
            f = (v - vs[i - 1]) / (vs[i] - vs[i - 1])
            a = ks[i - 1]
            b = ks[i]
            return [a[j] + f * (b[j] - a[j]) for j in range(len(a))]
    return ks[-1]


# =====================================================================
# 5. ПОВОРОТЫ (по гироскопу)
# =====================================================================

def _lqr_plan(D, w_max, a, v_end, ad=None):
    """Времена профиля: разгон (a) → постоянная → торможение (ad, по умолчанию = a) до v_end (ровно в D), затем v_end."""
    if ad is None:
        ad = a
    v_end = min(v_end, w_max)
    if D <= 0:
        return (0.0, 0.0, 0.0, v_end, v_end, 0.0, 0.0, ad)
    if ad == a:
        w_sq = a * D + v_end * v_end / 2
    else:
        w_sq = (D + v_end * v_end / (2 * ad)) / (1 / (2 * a) + 1 / (2 * ad))
    if w_sq <= v_end * v_end:                      # очень коротко: только разгоняемся, скорость ≤ v_end
        w = (2 * a * D) ** 0.5
        return (w / a, 0.0, 0.0, w, w, w / a, D, ad)
    w = min(w_max, w_sq ** 0.5)
    ta = w / a
    td = (w - v_end) / ad
    tc = (D - w * w / (2 * a) - (w * w - v_end * v_end) / (2 * ad)) / w
    return (ta, tc, td, w, v_end, ta + tc + td, D, ad)


def _lqr_profile(t, s, a, P):
    """(угол, скорость, ускорение) профиля в момент t секунд, s — знак направления."""
    ta, tc, td, w, ve, T, D, ad = P
    if t < ta:
        return s * 0.5 * a * t * t, s * a * t, s * a
    if t < ta + tc:
        return s * (0.5 * a * ta * ta + w * (t - ta)), s * w, 0.0
    if t < T:
        r = t - ta - tc
        return s * (0.5 * a * ta * ta + w * tc + w * r - 0.5 * ad * r * r), s * (w - ad * r), -s * ad
    return s * (D + ve * (t - T)), s * ve, 0.0


def _spin(u):
    """Вращать робота на месте со скоростью u °/с (положительная — по часовой стрелке)."""
    m = u * SPIN_K
    left_motor.run(m)
    right_motor.run(-m)


def _motor_angle():
    """Угол робота по моторам, «в единицах команды» (°)."""
    return (left_motor.angle() - right_motor.angle()) / 2 / SPIN_K


def _stop_motors(then, pivot=None):
    if then == Stop.BRAKE:
        left_motor.brake()
        right_motor.brake()
    elif then == Stop.COAST:
        left_motor.stop()
        right_motor.stop()
    elif pivot is not None:
        _hold_motor(pivot[0])                      # опорное колесо и так стоит в hold
    else:
        _hold_motor(left_motor)
        _hold_motor(right_motor)


def _turn_lqr(heading, w_max, accel, then, timeout, tries=None, v_end=None, pivot=None):
    """
    LQR-поворот (этапы описаны в блоке констант). Каждые LOOP_MS:
      профиль (угол, скорость, ускорение); опережение цели мотора с учётом трения
      L_ff = (ускорение + трение)/KP (сглаженное, feedforward); состояние — ошибка угла (гироскоп),
      ошибка скорости, ошибка опережения цели (наши команды + энкодеры), накопленная ошибка;
      команда = скорость профиля + изменение опережения − LQR_K · состояние,
      затем «потолок» (по оставшемуся углу) и предел LQR_SLEW — без скачков.
    pivot=(движущийся мотор, опорный мотор, знак) — поворот вокруг колеса (wheel_turn): опорное
      колесо стоит в hold, цикл тот же, но модель LQR_PIVOT_*, передача WHEEL_TURN_K и свой STOP_T.
    """
    global _stop_t, _pivot_stop_t
    if tries is None:
        tries = 0 if _rush else LQR_FIX_TRIES
    # rush() + then=Stop.NONE: передаём робота следующему движению на ходу; handover_a — turn_acceleration
    # DriveBase, которым straight() погасит оставшееся вращение (0 — обычный режим, отдаём на цели)
    handover_a = 0
    if v_end is None:
        v_end = LQR_V_END
        if _rush and then == Stop.NONE:
            handover_a = _profile["turn_accel"]
            v_end = max(LQR_V_END, min(RUSH_V_END, w_max, (2 * handover_a * RUSH_LEAD_MAX) ** 0.5))
    dt = LOOP_MS / 1000
    robot.stop()                                   # моторы отпускаются: цель начинается с фактического состояния
    if pivot is None:
        K, KP, FK = LQR_GAIN, LQR_SERVO_KP, LQR_FRICTION
        k_e, k_w, k_l, k_z = LQR_K
        stop_t, gear, u_max = _stop_t, SPIN_K, LQR_U_MAX
        drive, motor_angle = _spin, _motor_angle
        preload_v = LQR_PRELOAD_V
        motors = (left_motor, right_motor)
        name = "turn_to({})".format(heading)
    else:
        moving, fixed, sign = pivot
        K, KP, FK = LQR_PIVOT_GAIN, LQR_PIVOT_KP, LQR_PIVOT_FRICTION
        k_e, k_w, k_l, k_z = LQR_PIVOT_K
        # свой STOP_T для каждого направления: опора правое/левое колесо, угол больше/меньше нуля
        k_stop = (0 if sign > 0 else 2) + (0 if heading >= hub.imu.heading() else 1)
        stop_t, gear, u_max = _pivot_stop_t[k_stop], WHEEL_TURN_K, LQR_U_MAX / 2
        _hold_motor(fixed)                         # опорное колесо стоит на месте весь поворот

        def drive(u):                              # °/с робота → движущийся мотор
            moving.run(sign * WHEEL_TURN_K * u)

        def motor_angle():                         # угол робота по энкодеру движущегося мотора
            return sign * moving.angle() / WHEEL_TURN_K
        motors = (moving,)
        preload_v = LQR_PIVOT_PRELOAD_V
        name = "wheel_turn (курс {})".format(heading)
    dist = heading - hub.imu.heading()
    s = 1 if dist >= 0 else -1
    runaway = max(30, abs(dist) / 2 + 20)
    a_ref = motors[0].control.limits()[1] / gear  # предел ускорения цели, в единицах команды

    phi = motor_angle()                            # угол цели (в единицах команды)
    vr = 0.0                                       # скорость цели
    u_prev = 0.0
    # 0) Преднатяг: чтобы стронуть стоящего робота, цель должна опередить его на ≈3,7°
    #    (вокруг колеса меньше: трение там ниже, LQR_PIVOT_PRELOAD_V).
    if abs(dist) > 2:
        pre = StopWatch()
        m0 = motor_angle()
        while pre.time() < LQR_PRELOAD_MS:
            if s * GYRO_RATE_SIGN * hub.imu.angular_velocity(Axis.Z) > LQR_PRELOAD_GO and (
                    pivot is None or s * (motor_angle() - m0) > LQR_PIVOT_PRELOAD_MOVE):
                break
            u_prev = s * preload_v
            drive(u_prev)
            dv = _clamp(u_prev - vr, -a_ref * dt, a_ref * dt)
            phi += (vr + dv / 2) * dt
            vr += dv
            wait(LOOP_MS)
    # Профиль начинаем с ФАКТИЧЕСКОГО состояния робота: после преднатяга робот уже движется
    # со скоростью w0 — сдвигаем время профиля соответственно, иначе LQR будет его тормозить.
    theta = hub.imu.heading()
    w0 = _clamp(s * GYRO_RATE_SIGN * hub.imu.angular_velocity(Axis.Z), 0.0, w_max)
    t0 = w0 / accel
    start = theta - s * 0.5 * accel * t0 * t0      # «виртуальный» старт: профиль и робот совпадают
    d_lock = v_end * stop_t                        # brake срабатывает, когда остаётся столько градусов — профиль
    if handover_a:                                 # rush: здесь робот уходит к следующему движению на v_end
        d_lock = v_end * v_end / (2 * handover_a)
    # торможение вокруг колеса мягче разгона: мотор не успевает тормозить робота так же быстро, как разгоняет
    decel = accel if pivot is None else min(accel, LQR_PIVOT_DECEL_MAX)
    P = _lqr_plan(max(0.0, s * (heading - start) - d_lock), w_max, accel, v_end, decel)   # v_end ровно там
    t0 = min(t0, P[0])
    T = P[5]
    l_f = K * (phi - motor_angle())                # сглаженное опережение (feedforward)
    z = 0.0
    ok = True
    stop_now = False
    stop_at = (0.0, 0.0)
    timer = StopWatch()
    next_t = 0
    t_end = T * 1000 + 1500                        # предел времени на достижение цели
    while True:
        now = timer.time()
        t = now / 1000 + t0
        theta = hub.imu.heading()
        omega = GYRO_RATE_SIGN * hub.imu.angular_velocity(Axis.Z)
        remaining = s * (heading - theta)
        if then != Stop.NONE and remaining <= abs(omega) * stop_t:
            stop_now = True
            stop_at = (remaining, abs(omega))
            break
        if then == Stop.NONE:
            # Обычно — на цели. В rush — раньше: столько робот докрутит, пока DriveBase гасит вращение
            w_now = max(0.0, s * omega)
            if remaining <= (min(RUSH_LEAD_MAX, w_now * w_now / (2 * handover_a)) if handover_a else 0.0):
                break
        pr, vref, aref = _lqr_profile(t, s, accel, P)
        _, v1, a1 = _lqr_profile(t + dt, s, accel, P)
        # Упреждающее значение опережения: меняется плавно даже при скачкообразной смене ускорения
        l_old = l_f
        l_f += ((a1 + FK * s) / KP - l_f) * (dt / LQR_LEAD_TAU)
        lead = K * (phi - motor_angle())           # фактическое опережение (в единицах гироскопа)
        e = theta - (start + pr)
        e_w = omega - vref
        e_l = lead - l_f
        u_ff = (v1 + (l_f - l_old) / dt) / K
        u_lqr = u_ff - (k_e * e + k_w * e_w + k_l * e_l + k_z * z)
        # «Потолок»: максимальная скорость по оставшемуся углу — даже если робот отстаёт, к цели он не подойдёт слишком быстро
        cap = min(u_max, LQR_CAP_MARGIN * (v_end * v_end + 2 * decel * max(0.0, remaining - d_lock)) ** 0.5 / K)
        u = _clamp(u_lqr, u_prev - LQR_SLEW * dt, u_prev + LQR_SLEW * dt)
        u = s * _clamp(s * u, 0.0, cap)            # во время поворота не вращаемся в обратную сторону
        if pivot is not None:
            # Вокруг колеса команда на разгоне не ниже скорости профиля, а в основном повороте (не в поправке) —
            # и не ниже скорости преднатяга. Ниже робот прилипает: после трогания LQR срезал команду с 40 до 15 °/с
            # (и до нуля) — робот замирал на 50–80 мс; в конце полз к цели на 23–35 °/с, где доезд после brake
            # непредсказуем (wheel_turn_test 2026-10-02).
            u_min = s * vref if t < P[0] else 0.0
            if v_end >= preload_v:                 # поправка идёт с v_end = LQR_FIX_V — без этой границы
                u_min = max(u_min, min(preload_v, w_max))   # но не быстрее заданного rate
            u = s * max(s * u, min(u_min, cap))
        if abs(e) < LQR_INT_ZONE and abs(u - u_lqr) < 1:
            z = _clamp(z + e * dt, -LQR_INT_LIMIT, LQR_INT_LIMIT)
        if abs(e) > runaway:
            ok = _fail("LQR: робот отклонился от профиля на {:.0f}° (GYRO_RATE_SIGN?)".format(e))
            break
        drive(u)
        u_prev = u
        # Оценка цели: Pybricks доводит её до u с ускорением a_ref
        dv = _clamp(u - vr, -a_ref * dt, a_ref * dt)
        phi += (vr + dv / 2) * dt
        vr += dv

        if now > timeout or now > t_end:
            ok = _fail("таймаут " + name)
            break
        if now > STALL_GRACE_MS and (motors[0].stalled() or motors[-1].stalled()):
            ok = _fail("упор " + name)
            break

        next_t += LOOP_MS
        # Близко к цели: чтобы не пропустить момент brake, проверяем гироскоп каждую 1 мс
        near = then != Stop.NONE and remaining < abs(omega) * stop_t + abs(omega) * 3 * dt + 1
        while timer.time() < next_t:
            if near:
                th = hub.imu.heading()
                om = GYRO_RATE_SIGN * hub.imu.angular_velocity(Axis.Z)
                r_now = s * (heading - th)
                if r_now <= abs(om) * stop_t:
                    stop_now = True
                    stop_at = (r_now, abs(om))
                    break
            wait(1)
        if stop_now:
            break
        if timer.time() > next_t + LOOP_MS:
            next_t = timer.time()

    if then == Stop.NONE and ok:
        return True                                # моторы продолжают вращаться, их подхватит следующее движение
    if not ok:
        _stop_motors(Stop.HOLD, pivot)
        return False
    # 2) brake: робот быстро останавливается за счёт трения (hold на роботе пружинит назад на 1–3° — проверено)
    for m in motors:                               # при повороте на колесе опорное остаётся в hold
        m.brake()
    if pivot is not None:
        # Под нагрузкой опорное колесо проседает в hold на 2–3 мм, а после остановки мотор тянет его
        # обратно и доворачивает робота на 0,2–0,9° (wheel_turn_test 2026-10-02). Держим его там, где оно сейчас.
        _hold_motor(pivot[1])
    sw = StopWatch()
    still = None
    while sw.time() < 250:
        if abs(hub.imu.angular_velocity(Axis.Z)) < TURN_SETTLE_RATE:
            if still is None:
                still = sw.time()
            elif sw.time() - still >= LQR_SETTLE_MS:
                break
        else:
            still = None
        wait(2)
    if then != Stop.BRAKE or pivot is not None:   # BRAKE на колесе: тормозим и опорное
        _stop_motors(then, pivot)                  # HOLD: удерживаем там, где остановился; COAST: отпускаем
    err = heading - hub.imu.heading()
    if stop_now:
        rem, om = stop_at
        if om >= LQR_STOP_MIN_W:                   # обучение STOP_T (только на стабильных быстрых остановках)
            meas = _clamp((rem - s * err) / om, 0.003, 0.080)
            stop_t += LQR_STOP_ADAPT * (meas - stop_t)
            if pivot is None:
                _stop_t = stop_t
            else:
                st = list(_pivot_stop_t)
                st[k_stop] = stop_t
                _pivot_stop_t = st
    if abs(err) > LQR_FIX_TOL and tries > 0:
        log("   LQR-коррекция {:.2f}°".format(err))
        return _turn_lqr(heading, LQR_FIX_V, min(accel, 300), then, 1500, tries - 1, LQR_FIX_V, pivot)
    return True


def turn_to(heading, rate=None, then=Stop.HOLD, timeout=None):
    """
    Поворот на месте (колёса крутятся в разные стороны) на АБСОЛЮТНЫЙ курс, °.
    rate — °/с (только для этого поворота); если не задано — скорость профиля.
    Поворот контролируется не по времени и градусам мотора, а по гироскопу.
    """
    global _target_heading, _line_carry
    _target_heading = heading
    _line_carry = None            # после поворота прежняя линия уже не актуальна
    w_max = min(abs(rate), MAX_TURN_RATE) if rate else _profile["turn"]
    accel = _profile["turn_accel"]
    if timeout is None:
        timeout = _auto_timeout(heading - hub.imu.heading(), w_max, accel)
    t0 = _clock.time()
    ok = _turn_lqr(heading, w_max, min(accel, LQR_ACCEL_MAX), then, timeout)
    log("turn_to {} -> ошибка {:.1f}° · {} мс{}".format(
        heading, heading - hub.imu.heading(), _clock.time() - t0, " · rush" if _rush else ""))
    return ok


def turn(angle, rate=None, then=Stop.HOLD, timeout=None):
    """Относительный поворот на месте: к целевому курсу прибавляется angle ° (положительный — вправо)."""
    return turn_to(_target_heading + angle, rate, then, timeout)


def wheel_turn(angle, locked=RIGHT, rate=None, then=Stop.HOLD, timeout=None):
    """
    Поворот с одним заблокированным колесом (робот поворачивается вокруг этого колеса).
    angle — относительно целевого курса, положительный — по часовой стрелке.
    locked=RIGHT: правое колесо стоит, левое едет (положительный угол → поворот вперёд).
    locked=LEFT:  левое колесо стоит, правое едет (положительный угол → поворот назад).
    rate — °/с (только для этого поворота); если не задано — скорость профиля
    (не больше MAX_WHEEL_TURN_RATE). Управление — LQR-цикл turn() (_turn_lqr с pivot),
    опорное колесо всё время стоит в hold.
    """
    global _target_heading, _line_carry
    target = _target_heading + angle
    _target_heading = target
    _line_carry = None            # пивот тоже меняет курс — линия straight() больше не подходит
    if locked == RIGHT:
        moving, fixed, sign = left_motor, right_motor, 1
    else:
        moving, fixed, sign = right_motor, left_motor, -1
    w_max = min(abs(rate) if rate else _profile["turn"], MAX_WHEEL_TURN_RATE)
    accel = min(_profile["turn_accel"], LQR_PIVOT_ACCEL_MAX)
    if timeout is None:
        timeout = _auto_timeout(target - hub.imu.heading(), w_max, accel)
    f0 = fixed.angle()
    t0 = _clock.time()
    ok = _turn_lqr(target, w_max, accel, then, timeout, pivot=(moving, fixed, sign))
    # Как «от линии» у straight: насколько сдвинулось опорное колесо (по его энкодеру), мм
    log("wheel_turn {} -> ошибка {:.1f}° · {} мс, опорное колесо {:+.1f} мм{}".format(
        angle, target - hub.imu.heading(), _clock.time() - t0,
        (fixed.angle() - f0) * PI * WHEEL_DIAMETER / 360, " · rush" if _rush else ""))
    return ok


def arc(radius, angle, then=Stop.HOLD, timeout=None, speed=None):
    """
    Езда по дуге (DriveBase.arc, с гироскопом), с таймаутом.
    radius > 0 — вправо, < 0 — влево; angle > 0 — вперёд, < 0 — назад.
    speed — мм/с середины оси (только для этой дуги); если не задано — скорость профиля.
    """
    global _target_heading, _line_carry
    _line_carry = None
    # DriveBase.arc начинает дугу от фактического курса: если робота сильно развернуло (столкновение),
    # сначала выравниваемся на месте, как в straight()
    if abs(_target_heading - hub.imu.heading()) > (RUSH_PREALIGN if _rush else STRAIGHT_PREALIGN):
        turn_to(_target_heading)
    _target_heading += angle if radius > 0 else -angle
    v = min(abs(speed), MAX_DRIVE_SPEED) if speed else _profile["speed"]
    if timeout is None:
        # DriveBase ведёт дугу не быстрее ни straight_speed, ни turn_rate: у крутой дуги время задаёт поворот
        length = abs(angle) * PI / 180 * abs(radius)
        timeout = max(_auto_timeout(length, v, _profile["accel"]),
                      _auto_timeout(angle, _profile["turn"], _profile["turn_accel"]))
    _arc_speed(v)                                  # speed этой дуги или скорость профиля
    robot.arc(radius, angle, then=then, wait=False)
    is_done = robot.done
    if _rush and then == Stop.NONE:
        # rush: с then=Stop.NONE DriveBase заканчивает дугу, ещё вращаясь со скоростью дуги, и следующий straight()
        # гасит это вращение с turn_accel профиля — робот перекрутил бы на ω²/(2·turn_accel). Поэтому отдаём
        # робота заранее, за столько градусов до цели (как у поворотов в rush).
        s = 1 if (radius > 0) == (angle > 0) else -1   # знак изменения курса
        a = _profile["turn_accel"]

        def is_done():
            w = max(0.0, s * GYRO_RATE_SIGN * hub.imu.angular_velocity(Axis.Z))
            return robot.done() or s * (_target_heading - hub.imu.heading()) <= min(RUSH_LEAD_MAX, w * w / (2 * a))
    ok = _wait_done(is_done, timeout, "arc({}, {})".format(radius, angle), _hold_robot)
    log("arc {} {} -> ошибка {:.1f}°{}".format(
        radius, angle, _target_heading - hub.imu.heading(), " · rush" if _rush else ""))
    return ok


def _arc_speed(v):
    """straight_speed для DriveBase.arc перед дугой (меняется, только если отличается от нынешней)."""
    global _arc_v
    v = int(v)
    if v == _arc_v:
        return
    try:
        robot.settings(straight_speed=v)
    except OSError:
        robot.stop()                               # то же ограничение прошивки; дуга всё равно начинается сейчас
        robot.settings(straight_speed=v)
    _arc_v = v


def wall_square(heading, duty=-35, duration=800):
    """
    Выравнивание об стену: оба мотора толкают робота в стену, он встаёт
    параллельно ей, после чего гироскоп устанавливается в `heading`.
    Полностью убирает ошибку, накопленную за длинную миссию. duty < 0 — задом.
    """
    left_motor.dc(duty)
    right_motor.dc(duty)
    wait(duration)
    left_motor.stop()
    right_motor.stop()
    wait(150)
    set_heading(heading)


# =====================================================================
# 6. МОТОРЫ НАВЕСНОГО ОБОРУДОВАНИЯ (все с таймаутом)
# =====================================================================

def set_att_accel(accel):
    """Ускорение обоих моторов навесного оборудования, °/с²."""
    global _att_accel
    _att_accel = accel
    for motor in (att_left, att_right):
        try:
            motor.control.limits(speed=ATT_MAX_SPEED, acceleration=accel)
            _att_pending.discard(id(motor))
        except OSError:
            # Прошивка может не менять настройки, пока мотор работает или держит позицию.
            if motor.done():                       # держит позицию: на миг отпускаем, меняем, держим снова
                motor.stop()
                motor.control.limits(speed=ATT_MAX_SPEED, acceleration=accel)
                _hold_motor(motor)
                _att_pending.discard(id(motor))
            else:                                  # ещё едет (att_run с wait=False) — со следующей команды
                _att_pending.add(id(motor))


def _att_apply_pending(motor):
    """Перед новой командой мотору: ускорение, которое set_att_accel не смог применить на ходу."""
    if id(motor) in _att_pending:
        motor.stop()                               # новая команда всё равно заменит текущую
        motor.control.limits(speed=ATT_MAX_SPEED, acceleration=_att_accel)
        _att_pending.discard(id(motor))


def _att_name(motor):
    return "att_left" if motor is att_left else "att_right"


def att_wait(motor, angle=None):
    """
    Ждать с таймаутом завершения движения, запущенного с wait=False.
    angle — ждать не до конца, а пока мотор не повернётся на столько градусов от начала этого att_run:
    att_wait(att_left, 60) — насадка прошла 60° (из 300), можно ехать. По углу, а не по времени: если
    насадку что-то притормозит, робот всё равно её дождётся.
    """
    remaining = _att_deadline.get(id(motor), 0) - _clock.time()
    is_done = motor.done
    if angle is not None:
        start = _att_start.get(id(motor), motor.angle())

        def is_done():
            return motor.done() or abs(motor.angle() - start) >= abs(angle)
    # Если упёрся — hold(): мотор остаётся на месте и дальше не давит.
    return _wait_done(is_done, max(remaining, 0), _att_name(motor),
                      lambda: _hold_motor(motor))


def att_run(motor, speed, angle, then=Stop.HOLD, wait=True, timeout=None):
    """
    Повернуть мотор навесного оборудования на angle градусов. Упёршийся run_angle() может
    бесконечно ждать, не дойдя до цели, — здесь есть таймаут. wait=False — в фоне (потом att_wait).
    """
    if timeout is None:
        timeout = _auto_timeout(angle, speed, _att_accel)
    _att_deadline[id(motor)] = _clock.time() + timeout
    _att_apply_pending(motor)
    _att_start[id(motor)] = motor.angle()
    motor.run_angle(speed, angle, then=then, wait=False)
    if wait:
        return att_wait(motor)
    return True


def att_run_until_stalled(motor, speed, duty_limit=None, then=Stop.COAST,
                          timeout=ATT_STALL_TIMEOUT_MS):
    """Вращать до упора (с таймаутом). Возвращает угол, на котором мотор упёрся."""
    _att_apply_pending(motor)
    limits = motor.control.limits()
    if duty_limit is not None:
        # Ограничиваем момент — на механизм не передаётся полное усилие. stop() — на случай, если мотор
        # ещё держит позицию после att_run (hold): настройки меняем при неактивном регуляторе.
        motor.stop()
        motor.control.limits(limits[0], limits[1], int(limits[2] * duty_limit / 100))
    motor.run(speed)
    timer = StopWatch()
    try:
        while not (timer.time() > STALL_GRACE_MS and motor.stalled()):
            if timer.time() > timeout:
                _fail("таймаут run_until_stalled " + _att_name(motor))
                break
            wait(10)
        angle = motor.angle()
    finally:
        # Предел момента возвращаем всегда — и при остановке кнопкой или MoveError: reset_start()
        # его не восстанавливает, мотор остался бы ослабленным до конца программы.
        # Сначала stop(): менять настройки безопаснее, пока регулятор мотора не активен.
        if duty_limit is not None:
            motor.stop()
            motor.control.limits(*limits)
    if then == Stop.HOLD:
        _hold_motor(motor)
    elif then == Stop.BRAKE:
        motor.brake()
    else:
        motor.stop()
    return angle


# =====================================================================
# 7. ПОДГОТОВКА К СТАРТУ, БАТАРЕЯ
# =====================================================================

def reset_start():
    """Перед каждым стартом: обнулить счётчики, восстановить профили."""
    global _line_carry
    _line_carry = None            # иначе первая миссия подхватила бы линию предыдущей
    robot.stop()
    wait(250)                     # пусть утихнут колебания от прикосновения рукой
    att_left.reset_angle(0)
    att_right.reset_angle(0)
    set_heading(0)                # координаты поля: текущий курс = 0°
    rush(False)
    set_speed(DEFAULT_PROFILE)
    set_att_accel(ATT_DEFAULT_ACCEL)


def battery_check():
    """Перед стартом предупредить о низком заряде (миссию не блокирует)."""
    mv = hub.battery.voltage()
    if mv < BATTERY_LOW_MV:
        log("Батарея {:.2f} V — низкий заряд, скорость и точность могут упасть!".format(mv / 1000))
        beep(880, 80)
        wait(70)
        beep(880, 80)
    elif mv < BATTERY_WARN_MV:
        log("Батарея {:.2f} V — скоро зарядить".format(mv / 1000))
    return mv


def battery_tick(timer):
    """В меню каждые 25 с подаёт звуковой сигнал, если заряд низкий (из старого кода)."""
    if timer.time() < BATTERY_BEEP_PERIOD_MS:
        return
    timer.reset()
    mv = hub.battery.voltage()
    if mv < BATTERY_LOW_MV:
        beep(880, 80)
        wait(70)
        beep(880, 80)
    elif mv < BATTERY_WARN_MV:
        beep(880, 80)


def stop_drive():
    """Остановить привод и удержать робота на текущем месте."""
    global _line_carry
    _line_carry = None            # остановка обрывает переход: линию продолжать нечем
    _hold_robot()


def release_drive():
    """Остановить привод и отпустить моторы для ручного перемещения робота."""
    global _line_carry
    _line_carry = None
    robot.stop()
    left_motor.stop()
    right_motor.stop()


def stop_all():
    """Остановить моторы и отпустить привод в меню или при выходе."""
    release_drive()
    att_left.stop()
    att_right.stop()
