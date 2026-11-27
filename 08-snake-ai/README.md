# AI 贪吃蛇

Pygame 写的贪吃蛇，**带自动寻路 AI**：BFS 最短路 + 生存校验 + 追尾保命。

不是"能跑就行"的作业级实现——它会自己判断这一步走过去会不会被围死。

## 快速开始

```bash
pip install pygame

python snake_ai.py            # AI 自动玩
python snake_ai.py --manual   # 自己玩
```

**按键**：空格暂停 ｜ `R` 重开 ｜ `M` 切换 AI/手动 ｜ `ESC` 退出

## AI 是怎么想的

三层决策，从"想去哪"退到"能活吗"：

| 层 | 做法 | 解决什么 |
|---|---|---|
| 1 | BFS 求蛇头到食物的最短路 | 尽快吃到，别绕远 |
| 2 | 走之前模拟一步，检查蛇头还能不能摸到蛇尾 | 防止钻进死胡同 |
| 3 | 摸不到就朝空地最大的方向走（追尾） | 保命，等空间重新打开 |

只做第 1 层，是新手最容易写的版本——蛇一长就自己把自己关起来。第 2、3 层才是让它能吃到 100 分以上的原因。

## 实测效果

固定随机种子，无窗口跑满：

| 种子 | 分数 | 长度 |
|---|---|---|
| 1 | 48 | 51 |
| 7 | 69 | 72 |
| 42 | **146** | 149 |

棋盘 24×24 共 576 格，146 分意味着蛇占了四分之一还多。

## 截图怎么做

```bash
python snake_ai.py --shot shot.png --steps 2400 --seed 42
```

用 SDL 的 dummy 驱动无窗口渲染，不需要真的开显示器——放在服务器或 CI 里也能出图。

## 结构

```
snake_ai.py
├── SnakeGame    纯逻辑，不依赖 pygame，可以单独测 AI
├── bfs_path     最短路
├── flood_area   空地面积（衡量方向安不安全）
├── SnakeAI      三层决策
└── draw/run     pygame 渲染与主循环
```

逻辑和渲染分开，好处是**测 AI 不用开窗口**：

```python
from snake_ai import SnakeGame, SnakeAI

game, ai = SnakeGame(seed=42), SnakeAI()
while not game.dead:
    game.step(ai.choose(game))
print(game.score)
```

## 已知限制

- 不保证填满棋盘：BFS + 生存校验是启发式，不是最优解，长到 200 以上时仍可能被食物位置困死
- 单文件运行，没有做打包（需要 exe 用 `pyinstaller -F -w snake_ai.py`）
- 分数存在同目录 `highscore.txt`（已加进 .gitignore）