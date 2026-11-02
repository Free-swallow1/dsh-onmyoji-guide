# -*- coding: utf-8 -*-
"""本地冒烟测试：用假的 astrbot 模块加载插件，跑指令逻辑。"""
import asyncio
import os
import sys
import types


def make_stub():
    root = os.path.join(os.path.dirname(__file__), "stub")
    root = os.path.abspath(root)
    pkg = os.path.join(root, "astrbot")
    os.makedirs(os.path.join(pkg, "api"), exist_ok=True)

    def w(path, text):
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    w(os.path.join(pkg, "__init__.py"), "")
    w(os.path.join(pkg, "api", "__init__.py"), """
import logging
logger = logging.getLogger("astrbot")
class AstrBotConfig(dict):
    def save_config(self, *a, **k):
        pass
""")
    w(os.path.join(pkg, "api", "event.py"), """
class EventMessageType:
    ALL = "ALL"
class _Filter:
    EventMessageType = EventMessageType
    def command(self, *a, **k):
        def deco(fn): return fn
        return deco
    def command_group(self, *a, **k):
        def deco(fn): return fn
        return deco
    def event_message_type(self, *a, **k):
        def deco(fn): return fn
        return deco
filter = _Filter()
class AstrMessageEvent:
    pass
""")
    w(os.path.join(pkg, "api", "star.py"), """
class Context:
    def get_using_provider(self, umo=None):
        return None
class StarTools:
    @classmethod
    def get_data_dir(cls, name=None):
        import pathlib, tempfile, os
        d = pathlib.Path(tempfile.gettempdir()) / "yys_plugin_data"
        d.mkdir(parents=True, exist_ok=True)
        return d
class Star:
    def __init__(self, context, config=None):
        self.context = context
        self.logger = __import__("logging").getLogger("plugin")
""")
    w(os.path.join(pkg, "api", "message_components.py"), """
class Plain:
    def __init__(self, text=""):
        self.text = text
class Image:
    def __init__(self, file="", url="", path=""):
        self.file = file
        self.url = url
        self.path = path
class At:
    def __init__(self, qq=""):
        self.qq = qq
""")
    return root


class FakeMsg:
    def __init__(self, text="", images=None):
        self.message_str = text
        self.message = images or []


class FakeEvent:
    def __init__(self, text="", group="123456789", images=None, at=False):
        self.message_str = text
        self.message_obj = FakeMsg(text, images)
        self.unified_msg_origin = "aiocqhttp:FriendMessage:1"
        self.is_at_or_wake_command = at
        self._group = group
        self._stopped = False

    def get_group_id(self):
        return self._group

    def get_sender_id(self):
        return "12345"

    def get_sender_name(self):
        return "测试"

    def get_self_id(self):
        return "999"

    def is_admin(self):
        return True

    def plain_result(self, text):
        return ("PLAIN", text)

    def image_result(self, path):
        return ("IMAGE", path)

    def stop_event(self):
        self._stopped = True


async def run():
    stub = make_stub()
    sys.path.insert(0, stub)
    sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    import main as plugin_main

    p = plugin_main.YYSPlugin(None, {"group_whitelist": ["123456789"]})

    async def call(fn, *args):
        out = []
        async for r in fn(*args):
            out.append(r)
        return out

    tests = [
        ("/yys 天照", p.yys_cmd, FakeEvent("天照")),
        ("/yys 技能 天照", p.yys_cmd, FakeEvent("技能 天照")),
        ("/yys 御魂 破势", p.yys_cmd, FakeEvent("御魂 破势")),
        ("/yys 满暴 天照", p.yys_cmd, FakeEvent("满暴 天照")),
        ("/yys 算 攻击8000 暴击95 暴伤260", p.yys_cmd, FakeEvent("算 攻击8000 暴击95 暴伤260")),
        ("/yys 克制", p.yys_cmd, FakeEvent("克制 破势")),
        ("/yys 阴阳师 晴明", p.yys_cmd, FakeEvent("阴阳师 晴明")),
        ("/yys 加群 123456", p.yys_cmd, FakeEvent("加群 123456")),
        ("/yys 帮助", p.yys_cmd, FakeEvent("帮助")),
        ("/yys 阿修罗", p.yys_cmd, FakeEvent("阿修罗")),
    ]
    for name, fn, ev in tests:
        out = await call(fn, ev)
        print("=" * 20, name)
        for r in out:
            print(r[1][:800] if isinstance(r, tuple) else r)

    # 监听器（无 LLM，会走卡片兜底）
    ev = FakeEvent("天照御魂怎么带")
    out = await call(p.on_all_message, ev)
    print("=" * 20, "监听器: 天照御魂怎么带")
    for r in out:
        print(r[1][:800] if isinstance(r, tuple) else r)


if __name__ == "__main__":
    asyncio.run(run())
