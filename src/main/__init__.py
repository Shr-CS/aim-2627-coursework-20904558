# -*- coding: utf-8 -*-
"""AIM 2627 Python Coursework —— 哨兵 Sentry 控制模块（学生骨架）。

你的全部作业都在本文件里：按题面（题面.pdf）各题的规范补全每个标有 TODO 的函数。
- 骨架已提供：Facing / SentryState 枚举、SentryGrid 的构造与只读属性、
  渲染函数 render_frame（demo 用，不进测试）。
- 你要实现：Q1-Q6 与 Bonus 的全部 TODO，以及 SentryGrid 的
  四个方法（current_pos 的 setter、move_forward、turn_left、turn_right）。
- 未实现的函数 raise NotImplementedError：可见测试会自动 skip，
  CI 一开始就是绿的；实现一个，对应测试亮一个。
- `python main.py`（或 PYTHONPATH=src python -m main）可看 ASCII 演示。
"""
import json
from collections import deque
from enum import Enum


# ---------------------------------------------------------------------------
# 仿真世界基础（已提供，勿改）
# ---------------------------------------------------------------------------
class Facing(Enum):
    """朝向枚举。世界坐标 (x, y)：x 向右增长，y 向上增长（数学系）。"""

    UP = (0, 1)
    DOWN = (0, -1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)

    @property
    def delta(self):
        """该朝向的单位位移向量 (dx, dy)。"""
        return self.value[0], self.value[1]


# ---------------------------------------------------------------------------
# Q1 机器人自检（题面 Q1·自检状态计算与报告生成）
# ---------------------------------------------------------------------------
def hp_ratio(hp, max_hp):
    """TODO(Q1)：血量百分比，返回 0-100 的 int；计算与边界规则见题面 Q1 规范。"""
    if hp < 0 or max_hp <= 0:
        return 0
    elif hp > max_hp:
        return 100
    #要考虑浮点误差
    denominator = int(max_hp)
    if denominator <= 0:
        return 0
    return int(hp) * 100 // denominator


def status_report(name, robot_type, hp, max_hp, battery):
    """TODO(Q1)：一行自检报告字符串；档位判定与逐字符格式见题面 Q1 规范。"""
    pct = hp_ratio(hp, max_hp)  # 档位计算
    if battery >= 60:
        tier = "OK"
    elif battery >= 20:
        tier = "WARNING"
    else:
        tier = "LOW"
    return f"{name:<10}|{robot_type:^10}|HP {pct:>3}%|BAT {battery:>3}%|{tier}"

# ---------------------------------------------------------------------------
# Q2 战斗日志分析（题面 Q2·多源日志解析与统计）
# ---------------------------------------------------------------------------


def _positive_int(text):
    """严格解析十进制正整数；不是合法正整数时返回 None。

    不能只用 str.isdigit()：'²' 这类字符 isdigit() 为真但 int() 会抛 ValueError，
    题面 Q2 要求解析全程不得抛异常，所以额外要求 ASCII 字符集。
    """
    if not text or not text.isascii() or not text.isdigit():
        return None
    value = int(text)
    return value if value > 0 else None


def _parse_line(line):
    """解析一行，合法返回 [(armor, damage), ...]，脏行返回 None。"""
    if not isinstance(line, str):      # 非字符串一律按脏行处理，不得抛异常
        return None
    line = line.strip()

    # 空行 / 注释
    if not line or line.startswith("#"):
        return None

    # ---- 先尝试 JSON 行 ----
    if line.startswith("{"):
        try:
            data = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        armor = data.get("armor")
        damage = data.get("damage")
        if armor not in ("front", "left", "right"):
            return None
        # 严格正整数；排除 bool（True/False 也是 int）
        if not isinstance(damage, int) or isinstance(damage, bool) or damage <= 0:
            return None
        return [(armor, damage, data.get("id"))]
    # ---- 再尝试传感器行 ----
    result = []
    for part in line.split(","):
        key, sep, value = part.partition(":")
        if sep != ":" or not key or not value:
            return None
        if key not in ("F", "L", "R"):
            return None
        damage = _positive_int(value)
        if damage is None:
            return None
        armor = {"F": "front", "L": "left", "R": "right"}[key]
        result.append((armor, damage, None))
    return result if result else None


def analyze_damage_log(lines):
    """TODO(Q2)：解析混合格式伤害日志，返回固定契约的统计 dict；
    行格式、去重与统计口径见题面 Q2 规范。"""
    by_armor = {"front": 0, "left": 0, "right": 0}
    total = 0
    event_count = 0
    seen_ids = set()
    for line in (lines or ()):
        parsed = _parse_line(line)
        if parsed is None:
            continue

        # parsed 形如 [(armor, damage, id), ...]
        event_id = parsed[0][2]
        if event_id is not None:
            try:
                duplicated = event_id in seen_ids
            except TypeError:
                # id 不是可哈希的标量 → 该行字段非法，按脏行跳过
                continue
            if duplicated:
                continue
            seen_ids.add(event_id)

        event_count += 1
        for armor, damage, _ in parsed:
            by_armor[armor] += damage
            total += damage

    if event_count == 0:
        most_hit, avg = None, 0.0
    else:
        most_hit = None
        best = -1
        for name in ("front", "left", "right"):
            if by_armor[name] > best:
                best = by_armor[name]
                most_hit = name
        avg = round(total / event_count, 2)

    return {"total": total, "by_armor": by_armor,
            "most_hit": most_hit, "avg": avg}

# ---------------------------------------------------------------------------
# Q3 SentryGrid（题面 Q3·载体物理规则）
# ---------------------------------------------------------------------------


class SentryGrid:
    """哨兵仿真载体（构造与只读属性已提供；四个 TODO 方法由你实现）。"""

    def __init__(self, width, height, obstacles, enemy_pos,
                 start_pos=(0, 0), facing=Facing.UP, fuel=100):
        self._width = int(width)
        self._height = int(height)
        if self._width <= 0 or self._height <= 0:
            raise ValueError("地图尺寸必须为正")
        # 障碍坐标存入 set，查询 O(1)——已有实现，勿改。
        self._obstacles = set()
        for ob in obstacles:
            x, y = ob
            self._obstacles.add((int(x), int(y)))
        if not isinstance(enemy_pos, (tuple, list)) or len(enemy_pos) != 2:
            raise TypeError("enemy_pos 需要长度为 2 的 tuple/list")
        self._enemy_pos = self._clamp_cell(enemy_pos)
        if self._enemy_pos in self._obstacles:
            raise ValueError("enemy_pos 不能位于障碍物上")
        if not isinstance(facing, Facing):
            facing = Facing.UP
        self._facing = facing
        self._fuel = int(fuel)
        self._collision_count = 0
        self.current_pos = start_pos

    def _clamp_cell(self, cell):
        """已提供：元素转 int 并夹回地图范围（供 __init__ 使用）。"""
        x = int(cell[0])
        y = int(cell[1])
        x = max(0, min(self._width - 1, x))
        y = max(0, min(self._height - 1, y))
        return (x, y)

    # -- 只读属性（已提供，勿改） ------------------------------------------
    @property
    def width(self):
        return self._width

    @property
    def height(self):
        return self._height

    @property
    def enemy_pos(self):
        return self._enemy_pos

    @property
    def facing(self):
        return self._facing

    @property
    def fuel(self):
        return self._fuel

    @property
    def collision_count(self):
        return self._collision_count

    @property
    def obstacles(self):
        """障碍集合的只读视图（内部 set 引用，不要修改它）。"""
        return self._obstacles

    @property
    def found_enemy(self):
        return self._pos == self._enemy_pos

    def is_blocked(self, x, y):
        """已提供：坐标是否为障碍或越界（O(1)）。"""
        return ((x, y) in self._obstacles
                or not (0 <= x < self._width and 0 <= y < self._height))

    # -- 你要实现的部分 ------------------------------------------------------
    @property
    def current_pos(self):
        """当前位置 (x, y) 的 tuple。"""
        return self._pos

    @current_pos.setter
    def current_pos(self, value):
        """TODO(Q3)：位置 setter；三重输入校验见题面 Q3 规范第 1 条。"""
        if not isinstance(value, (tuple, list)):
            raise TypeError("current_pos 必须为 tuple/list")
        if len(value) != 2:
            raise TypeError("current_pos 必须为长度为 2 的 tuple/list")
        value = tuple(value)
        self._pos = self._clamp_cell(value)
        if self._pos in self._obstacles:
            raise ValueError("current_pos 不能位于障碍物上")
        return self._pos

    def move_forward(self):
        """TODO(Q3)：朝当前 facing 前进一格，返回执行后的位置；
        碰撞、耗电与断电语义见题面 Q3 规范。"""
        if self._fuel <= 0:
            return self._pos
        dx, dy = self._facing.delta
        new_x = self._pos[0] + dx
        new_y = self._pos[1] + dy
        if self.is_blocked(new_x, new_y):
            self._collision_count += 1
            self._fuel -= 1
            return self._pos
        else:
            self._pos = (new_x, new_y)
            self._fuel -= 1
            return self._pos

    def turn_left(self):
        """TODO(Q3)：原地左转 90°，返回新的 Facing（不耗电）。"""
        if self._facing == Facing.UP:
            self._facing = Facing.LEFT
        elif self._facing == Facing.LEFT:
            self._facing = Facing.DOWN
        elif self._facing == Facing.DOWN:
            self._facing = Facing.RIGHT
        elif self._facing == Facing.RIGHT:
            self._facing = Facing.UP
        return self._facing

    def turn_right(self):
        """TODO(Q3)：原地右转 90°，返回新的 Facing（不耗电）。"""
        if self._facing == Facing.UP:
            self._facing = Facing.RIGHT
        elif self._facing == Facing.RIGHT:
            self._facing = Facing.DOWN
        elif self._facing == Facing.DOWN:
            self._facing = Facing.LEFT
        elif self._facing == Facing.LEFT:
            self._facing = Facing.UP
        return self._facing


# ---------------------------------------------------------------------------
# Q4 贪心导航（题面 Q4·单步贪心导航策略）
# ---------------------------------------------------------------------------
def next_step_toward(pos, target, obstacles, current_facing=Facing.UP):
    """TODO(Q4)：返回下一步应朝向的 Facing；
    候选判定、优先级与回退规则见题面 Q4 规范。"""
    x, y = pos
    tx, ty = target
    dx = tx - x
    dy = ty - y
    cur_dist = abs(dx) + abs(dy)

    def is_candidate(facing):
        """候选方向 = 相邻格非障碍 且 移动后曼哈顿距离严格减小。"""
        nx = x + facing.delta[0]
        ny = y + facing.delta[1]
        if (nx, ny) in obstacles:
            return False
        return abs(tx - nx) + abs(ty - ny) < cur_dist

    # 优先轴 = 与目标绝对坐标差较大的轴；
    # 候选只可能出现在两个轴向的"朝目标"方向上，故检查这两个即可
    if abs(dx) > abs(dy):
        primary = Facing.RIGHT if dx > 0 else Facing.LEFT
        secondary = Facing.UP if dy > 0 else Facing.DOWN
    else:
        primary = Facing.UP if dy > 0 else Facing.DOWN
        secondary = Facing.RIGHT if dx > 0 else Facing.LEFT

    for facing in (primary, secondary):
        if is_candidate(facing):
            return facing

    # 不存在任何严格减距的候选（含 pos == target 的退化情形）→ 保持当前朝向
    return current_facing

# ---------------------------------------------------------------------------
# Q5 哨兵决策机（题面 Q5·裁判系统决策规则表）
# ---------------------------------------------------------------------------


class SentryState(Enum):
    """哨兵状态机（已提供，勿改）。"""

    PATROL = "PATROL"
    SUSPECT = "SUSPECT"
    ENGAGE = "ENGAGE"
    RETREAT = "RETREAT"
    RETURN = "RETURN"


def decide(sensor, state, hp, heat):
    """TODO(Q5)：纯函数决策，返回 (action: str, new_state: SentryState)；
    sensor 字段契约、R1-R7 规则表与非法输入处理见题面 Q5 规范。"""
    # 数据校验
    # ---- 输入契约校验：违反任一契约一律 ValueError ----
    if not isinstance(sensor, dict):
        raise ValueError("sensor 必须为 dict")

    required = ("enemy_frames", "enemy_dist", "robot_type", "max_hp")
    if any(key not in sensor for key in required):
        raise ValueError("sensor 缺少必需字段")

    frames = sensor["enemy_frames"]
    if not isinstance(frames, (tuple, list)) or not (1 <= len(frames) <= 6):
        raise ValueError("enemy_frames 必须是长度 1-6 的 tuple/list")

    if not isinstance(state, SentryState):
        raise ValueError("state 必须为 SentryState 成员")

    hp_pct = hp_ratio(hp, sensor["max_hp"])
    if hp_pct <= 30:  # R1
        return ("RETREAT", SentryState.RETREAT)

    elif state == SentryState.RETREAT:  # R2
        if hp_pct > 30:
            return ("RETURN", SentryState.RETURN)
        else:
            return ("RETREAT", SentryState.RETREAT)

    elif state == SentryState.RETURN:  # R3
        return ("MOVE_BASE", SentryState.PATROL)

    frames = [bool(x) for x in sensor["enemy_frames"]]
    visible = frames[-1]
    dist = sensor["enemy_dist"]
    # dist 合法形态是 int 或 None；None / 非法值按"远"处理，不参与贴脸判定
    close = isinstance(dist, int) and not isinstance(dist, bool) and dist <= 3

    if state == SentryState.ENGAGE and visible:  # R4
        if close:
            return ("SHOOT", SentryState.ENGAGE)
        elif sensor["robot_type"] == "HERO":
            return ("MOVE_RIGHT", SentryState.ENGAGE)
        else:
            return ("MOVE_LEFT", SentryState.ENGAGE)

    elif state == SentryState.ENGAGE and not visible:  # R5
        # 走到 R5 时 frames[-1] 已经是 False（不可见）
        if len(frames) >= 2 and frames[-2]:
            # 前一帧还看得到敌人，只有当前这一帧丢了 → 短暂丢失
            return ("HOLD_FIRE", SentryState.ENGAGE)
        else:
            # 前一帧也看不到（或历史不足以证明刚丢失）→ 持续丢失
            return ("SCAN", SentryState.SUSPECT)

    elif (state == SentryState.PATROL or state == SentryState.SUSPECT) and visible:  # R6
        if len(frames) >= 2 and frames[-2] and frames[-1]:
            if close:
                return ("SHOOT", SentryState.ENGAGE)
            elif sensor["robot_type"] == "HERO":
                return ("MOVE_RIGHT", SentryState.ENGAGE)
            else:
                return ("MOVE_LEFT", SentryState.ENGAGE)
        else:
            return ("SCAN", SentryState.SUSPECT)

    elif (state == SentryState.PATROL or state == SentryState.SUSPECT) and not visible:  # R7
        if state == SentryState.PATROL:
            return ("PATROL_MOVE", SentryState.PATROL)
        else:
            return ("SCAN", SentryState.SUSPECT)


# ---------------------------------------------------------------------------
# Q6 巡逻任务（题面 Q6·巡逻契约与验收阈值）
# ---------------------------------------------------------------------------
# 模块级常量：沿墙走的转向表（左手规则）
_LEFT = {Facing.UP: Facing.LEFT, Facing.LEFT: Facing.DOWN,
         Facing.DOWN: Facing.RIGHT, Facing.RIGHT: Facing.UP}
_RIGHT = {v: k for k, v in _LEFT.items()}
_BACK = {f: _RIGHT[_RIGHT[f]] for f in Facing}


def _manhattan(p, t):
    return abs(p[0] - t[0]) + abs(p[1] - t[1])


def _walkable(grid, pos, facing):
    """facing 方向的下一格是否可走，返回 (bool, 下一格坐标)。"""
    dx, dy = facing.delta
    nxt = (pos[0] + dx, pos[1] + dy)
    return not grid.is_blocked(nxt[0], nxt[1]), nxt


def _align_facing(grid, desired):
    """用最少的左右转把 facing 对齐到 desired（不耗电）。"""
    order = [Facing.UP, Facing.RIGHT, Facing.DOWN, Facing.LEFT]
    diff = (order.index(desired) - order.index(grid.facing)) % 4
    if diff <= 2:
        for _ in range(diff):
            grid.turn_right()
    else:
        for _ in range(4 - diff):
            grid.turn_left()


def _wall_follow_facing(grid, hand="L", avoid=()):
    """贴墙走：按所选手侧的顺序取第一个可走方向。

    hand="L"：左转 → 直行 → 右转 → 掉头；hand="R" 完全镜像。
    avoid 是本次脱困已经走过的格子：优先挑没踩过的方向，避免在死角或
    环里来回打转；四个方向都踩过时才退回正常贴墙顺序。
    """
    f = grid.facing
    if hand == "L":
        order = (_LEFT[f], f, _RIGHT[f], _BACK[f])
    else:
        order = (_RIGHT[f], f, _LEFT[f], _BACK[f])
    fallback = None
    for cand in order:
        ok, nxt = _walkable(grid, grid.current_pos, cand)
        if not ok:
            continue
        if nxt not in avoid:
            return cand
        if fallback is None:
            fallback = cand
    return fallback if fallback is not None else f


def _has_candidate(grid, target):
    """四邻域中是否存在"非障碍且严格减距"的方向（题面 Q4 规范 1）。"""
    pos = grid.current_pos
    cur_dist = _manhattan(pos, target)
    for facing in Facing:
        nxt = (pos[0] + facing.delta[0], pos[1] + facing.delta[1])
        if (not grid.is_blocked(nxt[0], nxt[1])
                and _manhattan(nxt, target) < cur_dist):
            return True
    return False


def run_patrol(grid, max_steps=500):
    target = grid.enemy_pos
    visited = {grid.current_pos}
    steps = 0
    mode = "greedy"
    hand = "L"          # 贴墙手：L=左手规则，R=右手规则
    wall_steps = 0      # 本次贴墙已经走了多少步
    entry_dist = 0      # 进入贴墙那一刻到目标的曼哈顿距离
    episode = set()     # 本次贴墙走过的格子（用于防打转）
    limit = grid.width + grid.height   # 绕圈判定阈值（约等于地图尺度）

    while True:
        # ---- 终止条件：到达 / 步数用尽 / 电量耗尽 ----
        if grid.current_pos == target:
            success = True
            break
        if steps >= max_steps or grid.fuel <= 0:
            success = False
            break

        pos = grid.current_pos
        cur_dist = _manhattan(pos, target)

        # Q4 贪心提案，并判断"走这步是否真的更近"
        g = next_step_toward(pos, target, grid.obstacles, grid.facing)
        g_ok, g_nxt = _walkable(grid, pos, g)
        greedy_good = g_ok and _manhattan(g_nxt, target) < cur_dist

        # 贪心失速 → 切沿墙模式，并记住进入时的距离
        if mode == "greedy" and not greedy_good:
            mode, hand, wall_steps = "wall", "L", 0
            entry_dist = cur_dist
            episode = {pos}

        if mode == "greedy":
            desired = g
        else:
            desired = _wall_follow_facing(grid, hand, episode)

        # 先对齐、再前进 → 保证零碰撞
        _align_facing(grid, desired)
        grid.move_forward()
        steps += 1
        visited.add(grid.current_pos)

        # ---- 沿墙模式的退出/换挡判据（按序求值，首条命中即生效） ----
        if mode == "wall":
            episode.add(grid.current_pos)
            wall_steps += 1
            if wall_steps > 3 * limit and hand == "L":
                # 左手绕不出去 → 换右手再试
                hand, wall_steps = "R", 0
            elif wall_steps > 6 * limit:
                # 两只手都绕不动 → 放弃贴墙，回贪心重新尝试
                mode, wall_steps = "greedy", 0
            elif (_has_candidate(grid, target)
                  and _manhattan(grid.current_pos, target) < entry_dist + 1):
                # 已经绕出死角（距离不劣于进入贴墙时）→ 切回贪心
                mode, wall_steps = "greedy", 0

    return {
        "steps": steps,                          # move_forward 的次数
        "collisions": grid.collision_count,
        "visited_count": len(visited),
        "found_enemy": success,                  # 与 success 同义
        "success": success,
    }


def report_to_json(stats):
    """确定性序列化：键排序 + 固定分隔符，保证同输入恒同输出。"""
    return json.dumps(stats, sort_keys=True,
                      separators=(",", ":"), ensure_ascii=False)
# ---------------------------------------------------------------------------
# Bonus：BFS 全局最短路（题面 Bonus·BFS 语义与排行榜）
# ---------------------------------------------------------------------------


def bfs_path_length(start, target, obstacles):
    """BFS 全局最短路步数；返回语义与边界职责见题面 Bonus 规范。"""
    start = tuple(start)
    target = tuple(target)
    blocked = {tuple(o) for o in obstacles}

    if start == target:
        return 0

    directions = ((1, 0), (-1, 0), (0, 1), (0, -1))
    visited = {start}
    queue = deque([(start, 0)])

    while queue:
        (x, y), dist = queue.popleft()
        for dx, dy in directions:
            nxt = (x + dx, y + dy)
            if nxt in visited or nxt in blocked:
                continue
            if nxt == target:
                return dist + 1
            visited.add(nxt)
            queue.append((nxt, dist + 1))

    return -1


# ---------------------------------------------------------------------------
# 渲染（已提供，demo 专用，不进测试）
# ---------------------------------------------------------------------------
def render_frame(grid, trail=()):
    """ASCII 渲染一帧战场；trail 为走过的格子集合。返回 list[str]。"""
    trail = set(trail)
    rows = []
    for y in range(grid.height - 1, -1, -1):
        row = []
        for x in range(grid.width):
            if (x, y) == grid.current_pos:
                row.append("◉")
            elif (x, y) == grid.enemy_pos:
                row.append("▲")
            elif (x, y) in grid.obstacles:
                row.append("█")
            elif (x, y) in trail:
                row.append("·")
            else:
                row.append(".")
        rows.append("".join(row))
    return rows
