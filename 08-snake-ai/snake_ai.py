#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""AI 贪吃蛇：BFS 最短路 + 生存校验 + 追尾保命。

三层决策，解决"蛇一长就把自己憋死"的老问题：

1. 用 BFS 求蛇头到食物的最短路径；
2. 走之前先模拟：走完这一步后，蛇头还能不能摸到蛇尾（能，说明没被围死）；
3. 摸不到就退化成"追尾"——朝空间最大的方向走，保命优先。

用法：
    python snake_ai.py                # AI 自动玩
    python snake_ai.py --manual       # 自己玩，方向键控制
    python snake_ai.py --shot a.png   # 无窗口渲染一张截图（做文档用）

按键：空格暂停 / R 重开 / M 切换 AI 与手动 / ESC 退出
"""

from __future__ import annotations

import argparse
import random
from collections import deque
from pathlib import Path

# ---------------------------------------------------------------- 配置
COLS, ROWS = 24, 24
CELL = 26
MARGIN = 18
HUD_H = 68
WIDTH = COLS * CELL + MARGIN * 2
HEIGHT = ROWS * CELL + MARGIN * 2 + HUD_H

UP, RIGHT, DOWN, LEFT = (0, -1), (1, 0), (0, 1), (-1, 0)
DIRS = [UP, RIGHT, DOWN, LEFT]

BG = (16, 18, 26)
BOARD = (22, 25, 36)
GRID = (30, 34, 47)
HEAD = (126, 231, 135)
BODY_TOP = (52, 199, 89)
BODY_BOT = (28, 122, 60)
FOOD = (255, 107, 107)
TEXT = (232, 238, 250)
DIM = (140, 150, 172)
ACCENT = (255, 210, 63)

HIGH_FILE = Path(__file__).with_name("highscore.txt")


# ---------------------------------------------------------------- 逻辑
class SnakeGame:
    """纯逻辑，不依赖 pygame，方便单独测试 AI。"""

    def __init__(self, cols: int = COLS, rows: int = ROWS, seed: int | None = None):
        self.cols, self.rows = cols, rows
        self.rng = random.Random(seed)
        self.reset()

    def reset(self) -> None:
        cx, cy = self.cols // 2, self.rows // 2
        self.snake: deque[tuple[int, int]] = deque([(cx, cy), (cx - 1, cy), (cx - 2, cy)])
        self.direction = RIGHT
        self.score = 0
        self.dead = False
        self.steps = 0
        self._place_food()

    def in_bounds(self, p: tuple[int, int]) -> bool:
        return 0 <= p[0] < self.cols and 0 <= p[1] < self.rows

    def _place_food(self) -> None:
        taken = set(self.snake)
        free = [(x, y) for y in range(self.rows) for x in range(self.cols) if (x, y) not in taken]
        self.food = self.rng.choice(free) if free else None

    def blocked_cells(self) -> set[tuple[int, int]]:
        """撞不上的格子：尾巴这一步会挪走，所以不算障碍。"""
        return set(list(self.snake)[:-1])

    def step(self, d: tuple[int, int]) -> None:
        if self.dead:
            return
        nxt = (self.snake[0][0] + d[0], self.snake[0][1] + d[1])
        if not self.in_bounds(nxt) or nxt in self.blocked_cells():
            self.dead = True
            return

        self.direction = d
        self.steps += 1
        self.snake.appendleft(nxt)
        if nxt == self.food:
            self.score += 1
            self._place_food()
        else:
            self.snake.pop()


def bfs_path(
    cols: int, rows: int,
    start: tuple[int, int], goal: tuple[int, int] | None,
    blocked: set[tuple[int, int]],
) -> list[tuple[int, int]] | None:
    """最短路搜索，返回从 start 到 goal 的完整路径。"""
    if goal is None:
        return None
    queue = deque([start])
    prev: dict[tuple[int, int], tuple[int, int] | None] = {start: None}

    while queue:
        cur = queue.popleft()
        if cur == goal:
            path: list[tuple[int, int]] = []
            node: tuple[int, int] | None = cur
            while node is not None:
                path.append(node)
                node = prev[node]
            return path[::-1]
        for d in DIRS:
            nxt = (cur[0] + d[0], cur[1] + d[1])
            if nxt in prev:
                continue
            if not (0 <= nxt[0] < cols and 0 <= nxt[1] < rows):
                continue
            if nxt in blocked and nxt != goal:
                continue
            prev[nxt] = cur
            queue.append(nxt)
    return None


def flood_area(
    cols: int, rows: int, start: tuple[int, int],
    blocked: set[tuple[int, int]], cap: int = 400,
) -> int:
    """从某格能走到的空地数量，用来衡量"这个方向安不安全"。"""
    seen = {start}
    queue = deque([start])
    while queue and len(seen) < cap:
        cur = queue.popleft()
        for d in DIRS:
            nxt = (cur[0] + d[0], cur[1] + d[1])
            if nxt in seen or nxt in blocked:
                continue
            if not (0 <= nxt[0] < cols and 0 <= nxt[1] < rows):
                continue
            seen.add(nxt)
            queue.append(nxt)
    return len(seen)


class SnakeAI:
    """三层决策：最短路 → 生存校验 → 追尾保命。"""

    def choose(self, game: SnakeGame) -> tuple[int, int]:
        head = game.snake[0]
        blocked = game.blocked_cells()

        path = bfs_path(game.cols, game.rows, head, game.food, blocked)
        if path and len(path) > 1:
            nxt = path[1]
            if self._safe(game, nxt):
                return (nxt[0] - head[0], nxt[1] - head[1])

        return self._survive(game, blocked)

    def _safe(self, game: SnakeGame, nxt: tuple[int, int]) -> bool:
        """走完这一步之后，蛇头还摸得到蛇尾吗？"""
        eats = nxt == game.food
        snake = list(game.snake)
        new_snake = [nxt] + (snake if eats else snake[:-1])
        tail = new_snake[-1]
        blocked = set(new_snake[:-1])
        return bfs_path(game.cols, game.rows, nxt, tail, blocked) is not None

    def _survive(self, game: SnakeGame, blocked: set[tuple[int, int]]) -> tuple[int, int]:
        """追尾保命：找一块最大的空地钻进去。"""
        head = game.snake[0]
        best_dir, best_area = None, -1

        for d in DIRS:
            nxt = (head[0] + d[0], head[1] + d[1])
            if not game.in_bounds(nxt) or nxt in blocked:
                continue
            area = flood_area(game.cols, game.rows, nxt, blocked | {nxt})
            if area > best_area:
                best_area, best_dir = area, d

        if best_dir is not None:
            return best_dir

        for d in DIRS:
            nxt = (head[0] + d[0], head[1] + d[1])
            if game.in_bounds(nxt) and nxt not in blocked:
                return d

        return game.direction


# ---------------------------------------------------------------- 渲染
def load_fonts():
    import os

    import pygame

    font_files = [
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ]

    def pick(size: int, bold: bool = True):
        for path in font_files:
            if os.path.exists(path):
                try:
                    return pygame.font.Font(path, size)
                except Exception:
                    continue
        for name in ("microsoftyahei", "simhei", "notosanscjksc", "arial"):
            try:
                return pygame.font.SysFont(name, size, bold=bold)
            except Exception:
                continue
        return pygame.font.Font(None, size + 6)

    return pick(26), pick(18), pick(34)


def draw(surface, game: SnakeGame, fonts, high: int, mode: str) -> None:
    import pygame

    big, small, title = fonts
    surface.fill(BG)

    # 顶部信息
    pygame.draw.rect(surface, (20, 23, 33), (0, 0, WIDTH, HUD_H))
    surface.blit(title.render("AI 贪吃蛇", True, TEXT), (MARGIN, 16))
    surface.blit(small.render(f"BFS + 生存校验 + 追尾", True, DIM), (MARGIN, 46))

    stats = [("分数", str(game.score), ACCENT), ("最高", str(high), TEXT),
             ("长度", str(len(game.snake)), TEXT), ("模式", mode, HEAD)]
    x = WIDTH - MARGIN - 4 * 96
    for label, value, color in stats:
        surface.blit(small.render(label, True, DIM), (x, 18))
        surface.blit(big.render(value, True, color), (x, 38))
        x += 96

    # 棋盘
    top = HUD_H + MARGIN
    pygame.draw.rect(surface, BOARD, (MARGIN, top, COLS * CELL, ROWS * CELL), border_radius=10)
    for i in range(1, COLS):
        pygame.draw.line(surface, GRID, (MARGIN + i * CELL, top),
                         (MARGIN + i * CELL, top + ROWS * CELL))
    for j in range(1, ROWS):
        pygame.draw.line(surface, GRID, (MARGIN, top + j * CELL),
                         (MARGIN + COLS * CELL, top + j * CELL))

    ox, oy = MARGIN + CELL // 2, top + CELL // 2

    # 食物
    if game.food:
        fx, fy = ox + game.food[0] * CELL, oy + game.food[1] * CELL
        pygame.draw.circle(surface, (255, 107, 107, 60), (fx, fy), CELL // 2 - 1)
        pygame.draw.circle(surface, FOOD, (fx, fy), CELL // 3)
        pygame.draw.circle(surface, (255, 190, 190), (fx - 2, fy - 3), 2)

    # 蛇身：从头到尾做渐变
    total = max(len(game.snake) - 1, 1)
    for idx, (cx, cy) in enumerate(game.snake):
        t = idx / total
        color = tuple(int(BODY_TOP[i] + (BODY_BOT[i] - BODY_TOP[i]) * t) for i in range(3))
        if idx == 0:
            color = HEAD
        rect = (ox + cx * CELL - CELL // 2 + 2, oy + cy * CELL - CELL // 2 + 2,
                CELL - 4, CELL - 4)
        pygame.draw.rect(surface, color, rect, border_radius=7)

    # 蛇头眼睛
    hx, hy = ox + game.snake[0][0] * CELL, oy + game.snake[0][1] * CELL
    dx, dy = game.direction
    for sign in (-1, 1):
        ex = hx + dx * 5 + (0 if dx else sign * 5)
        ey = hy + dy * 5 + (0 if dy else sign * 5)
        pygame.draw.circle(surface, (16, 18, 26), (ex, ey), 2)


def render_shot(path: Path, steps: int, seed: int) -> tuple[int, int]:
    """无窗口跑一段 AI，渲染一帧存图。"""
    import os

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    import pygame

    pygame.init()
    pygame.font.init()
    game = SnakeGame(seed=seed)
    ai = SnakeAI()
    for _ in range(steps):
        if game.dead:
            break
        game.step(ai.choose(game))

    surface = pygame.Surface((WIDTH, HEIGHT))
    draw(surface, game, load_fonts(), game.score, "AI")
    pygame.image.save(surface, str(path))
    pygame.quit()
    return game.score, len(game.snake)


# ---------------------------------------------------------------- 交互
def run(manual: bool, fps: int, seed: int | None) -> None:
    import pygame

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("AI 贪吃蛇 · BFS + 生存校验")
    clock = pygame.time.Clock()
    fonts = load_fonts()

    high = 0
    if HIGH_FILE.exists():
        try:
            high = int(HIGH_FILE.read_text(encoding="utf-8").strip() or 0)
        except ValueError:
            high = 0

    game = SnakeGame(seed=seed)
    ai = SnakeAI()
    use_ai = not manual
    paused = False
    interval, acc = 130.0, 0.0

    running = True
    while running:
        dt = clock.tick(60)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    paused = not paused
                elif event.key == pygame.K_m:
                    use_ai = not use_ai
                elif event.key == pygame.K_r:
                    game.reset()
                    paused = False
                elif not use_ai:
                    keymap = {pygame.K_UP: UP, pygame.K_w: UP, pygame.K_RIGHT: RIGHT,
                              pygame.K_d: RIGHT, pygame.K_DOWN: DOWN, pygame.K_s: DOWN,
                              pygame.K_LEFT: LEFT, pygame.K_a: LEFT}
                    if event.key in keymap:
                        d = keymap[event.key]
                        if (d[0] + game.direction[0], d[1] + game.direction[1]) != (0, 0):
                            game.direction = d

        if not paused and not game.dead:
            acc += dt
            interval = max(55.0, 130.0 - game.score * 3.2)
            if acc >= interval:
                acc = 0.0
                game.step(ai.choose(game) if use_ai else game.direction)

        if game.dead and game.score > high:
            high = game.score
            HIGH_FILE.write_text(str(high), encoding="utf-8")

        draw(screen, game, fonts, high, "AI" if use_ai else "手动")
        pygame.display.flip()

    pygame.quit()


def main() -> None:
    parser = argparse.ArgumentParser(description="AI 贪吃蛇")
    parser.add_argument("--manual", action="store_true", help="手动模式，方向键控制")
    parser.add_argument("--shot", type=Path, default=None, help="渲染一张截图后退出")
    parser.add_argument("--steps", type=int, default=260, help="截图前先跑多少步")
    parser.add_argument("--seed", type=int, default=7, help="随机种子")
    args = parser.parse_args()

    if args.shot:
        score, length = render_shot(args.shot, args.steps, args.seed)
        print(f"已截图：{args.shot}（分数 {score}，长度 {length}）")
        return

    run(args.manual, 60, args.seed)


if __name__ == "__main__":
    main()