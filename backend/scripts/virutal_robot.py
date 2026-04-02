#!/usr/bin/env python3
"""
多线程模拟机器狗脚本
- WebSocket 在子线程中接收命令
- 主线程运行 turtle 事件循环并执行绘图命令
- 使用队列进行线程间通信
"""

import json
import threading
import queue
import time
import urllib.parse
from typing import Any, List, Optional
import turtle
from websockets.sync.client import connect

# ---------- 数据模型（与后端一致）----------
class Parameter:
    def __init__(self, name: str, type: str, is_required: bool):
        self.name = name
        self.type = type
        self.is_required = is_required

    def to_dict(self):
        return {"name": self.name, "type": self.type, "is_required": self.is_required}

class API:
    def __init__(self, type: str, name: str, description: Optional[str] = None,
                 parameters: Optional[List[Parameter]] = None, return_type: Optional[str] = None):
        self.type = type
        self.name = name
        self.description = description
        self.parameters = parameters
        self.return_type = return_type

    def to_dict(self):
        return {
            "type": self.type,
            "name": self.name,
            "description": self.description,
            "parameters": [p.to_dict() for p in self.parameters] if self.parameters else None,
            "return_type": self.return_type
        }

class InitResponse:
    def __init__(self, robot_id: str, robot_name: str, apis: List[API]):
        self.robot_id = robot_id
        self.robot_name = robot_name
        self.apis = apis

    def to_dict(self):
        return {
            "robot_id": self.robot_id,
            "robot_name": self.robot_name,
            "apis": [api.to_dict() for api in self.apis]
        }

class CommandRequest:
    def __init__(self, id: str, name: str, parameter: List[Any]):
        self.id = id
        self.name = name
        self.parameter = parameter

class CommandResponse:
    def __init__(self, id: str, success: bool, return_data: Any):
        self.id = id
        self.success = success
        self.return_data = return_data

    def to_dict(self):
        return {"id": self.id, "success": self.success, "return_data": self.return_data}

# ---------- 机器人配置 ----------
ROBOT_ID = "simulated-robot-001"
ROBOT_NAME = "Turtle Robot"

APIS = [
    API(type="action", name="move_forward", description="向前移动",
        parameters=[Parameter("distance", "float", True)]),
    API(type="action", name="move_backward", description="向后移动",
        parameters=[Parameter("distance", "float", True)]),
    API(type="action", name="turn_left", description="左转",
        parameters=[Parameter("angle", "float", True)]),
    API(type="action", name="turn_right", description="右转",
        parameters=[Parameter("angle", "float", True)]),
    API(type="action", name="pen_up", description="抬笔"),
    API(type="action", name="pen_down", description="落笔"),
    API(type="action", name="set_color", description="设置画笔颜色",
        parameters=[Parameter("color", "str", True)]),
    API(type="action", name="draw_circle", description="画圆",
        parameters=[Parameter("radius", "float", True)]),
    API(type="action", name="clear_screen", description="清屏"),
    API(type="query", name="get_position", description="获取当前位置"),
    API(type="query", name="get_heading", description="获取朝向"),
]

# ---------- Turtle 机器人（运行在主线程）----------
class TurtleRobot:
    def __init__(self):
        self.screen = turtle.Screen()
        self.screen.title("模拟机器狗 - Turtle")
        self.screen.bgcolor("white")
        self.t = turtle.Turtle()
        self.t.speed(5)
        self.t.pensize(2)

    def execute(self, req: CommandRequest):
        name = req.name
        params = req.parameter
        try:
            if name == "move_forward":
                self.t.forward(params[0])
                return {"success": True, "data": None}
            elif name == "move_backward":
                self.t.backward(params[0])
                return {"success": True, "data": None}
            elif name == "turn_left":
                self.t.left(params[0])
                return {"success": True, "data": None}
            elif name == "turn_right":
                self.t.right(params[0])
                return {"success": True, "data": None}
            elif name == "pen_up":
                self.t.penup()
                return {"success": True, "data": None}
            elif name == "pen_down":
                self.t.pendown()
                return {"success": True, "data": None}
            elif name == "set_color":
                self.t.pencolor(params[0])
                return {"success": True, "data": None}
            elif name == "draw_circle":
                self.t.circle(params[0])
                return {"success": True, "data": None}
            elif name == "clear_screen":
                self.t.clear()
                return {"success": True, "data": None}
            elif name == "get_position":
                pos = self.t.position()
                return {"success": True, "data": {"x": pos[0], "y": pos[1]}}
            elif name == "get_heading":
                return {"success": True, "data": self.t.heading()}
            else:
                return {"success": False, "data": f"未知命令: {name}"}
        except Exception as e:
            return {"success": False, "data": str(e)}

# ---------- WebSocket 客户端（运行在子线程）----------
def websocket_thread(cmd_queue: queue.Queue, resp_queue: queue.Queue, stop_event: threading.Event):
    init = InitResponse(ROBOT_ID, ROBOT_NAME, APIS)
    init_json = json.dumps(init.to_dict())
    init_encoded = urllib.parse.quote(init_json)
    ws_url = f"ws://localhost:8000/ws/robot?init={init_encoded}"

    while not stop_event.is_set():
        try:
            with connect(ws_url) as ws:
                print("✅ WebSocket 已连接，等待命令...")
                while not stop_event.is_set():
                    try:
                        msg = ws.recv(timeout=1)
                        data = json.loads(msg)
                        req = CommandRequest(data["id"], data["name"], data["parameter"])
                        cmd_queue.put(req)          # 将命令发送给主线程
                        resp = resp_queue.get()     # 等待主线程执行结果
                        ws.send(json.dumps(resp.to_dict()))
                    except TimeoutError:
                        continue
                    except Exception as e:
                        print(f"WebSocket 错误: {e}")
                        break
        except Exception as e:
            print(f"连接失败: {e}，5秒后重连...")
            time.sleep(5)

# ---------- 主线程 ----------
def main():
    cmd_queue = queue.Queue()
    resp_queue = queue.Queue()
    stop_event = threading.Event()

    # 启动 WebSocket 子线程
    ws_thread = threading.Thread(target=websocket_thread, args=(cmd_queue, resp_queue, stop_event), daemon=True)
    ws_thread.start()

    # 创建 turtle 机器人
    robot = TurtleRobot()
    screen = robot.screen

    # 定期检查命令队列
    def process_commands():
        try:
            req = cmd_queue.get_nowait()
        except queue.Empty:
            screen.ontimer(process_commands, 50)
            return

        result = robot.execute(req)
        resp = CommandResponse(req.id, result["success"], result["data"])
        resp_queue.put(resp)
        screen.ontimer(process_commands, 50)

    screen.ontimer(process_commands, 50)
    print("Turtle 窗口已打开，等待命令...")
    turtle.done()  # 进入 turtle 事件循环

    stop_event.set()
    ws_thread.join()

if __name__ == "__main__":
    main()