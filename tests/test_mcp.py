"""Run with python -m unittest discover -s tests -v; no game installation required."""
import json
import tempfile
import unittest
from pathlib import Path

from mcp_client import PROTOCOL, content, run_session


class MCPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        root = Path(tmp.name)
        saves = root / "saves"
        saves.mkdir()
        cls.state = root / "state"
        game = root / "game"
        game.mkdir()
        preview = {"slotId": 0, "dayCount": 1, "credit": 20, "startName": "fixture", "version": "test"}
        index = {"preview_0": {"__type": "fixture", "value": preview}}
        data = {"playerStore": {"playerCash": 20, "dayUntilRent": 6}, "storeStation": {"dayCounter": 1}}
        data["playerStore"]["mainInvJSON"] = "x" * 70000
        (saves / "saves_index.es3").write_text(json.dumps(index), encoding="utf-8")
        (saves / "save_0.es3").write_text(json.dumps(data), encoding="utf-8")
        env = {"PS_STATE_DIR": str(cls.state), "PS_SAVE_DIR": str(saves), "PS_GAME_DIR": str(game)}
        calls = [
            ("saves", {}), ("save_get", {"path": "playerStore.playerCash"}),
            ("unknown_tool", {}),
            ("kb_add_seed", {"file": "测试", "title": "测试主题", "text": "本地笔记"}),
            ("kb_add_seed", {"file": "子目录/笔记", "title": "测试", "text": "测试"}),
            ("overview", {}),
        ]
        cls.replies = run_session(root, env, calls, version="unsupported-test-version")
        cls.saves = saves

    def test_initialize_and_ping(self):
        self.assertEqual(self.replies[0]["protocolVersion"], PROTOCOL)
        self.assertIn("tools", self.replies[0]["capabilities"])
        self.assertEqual(self.replies[1], {})

    def test_tool_discovery(self):
        tools = self.replies[2]["tools"]
        names = {tool["name"] for tool in tools}
        self.assertEqual(len(tools), len(names))
        self.assertEqual(len(names), 12)
        self.assertTrue({"saves", "kb_search", "kb_get", "weekly_report"} <= names)
        for tool in tools:
            self.assertEqual(tool["inputSchema"]["type"], "object")

    def test_reads_fixture_save(self):
        self.assertEqual(content(self.replies[3])["saves"][0]["slot"], 0)
        self.assertEqual(content(self.replies[4])["value"], 20)

    def test_overview_summarizes_large_inventory_strings(self):
        summary = content(self.replies[8])
        self.assertEqual(summary["day"], 1)
        self.assertEqual(summary["player"]["playerCash"], 20)
        self.assertIn("70000", summary["player"]["mainInvJSON"])
        self.assertLess(len(summary["player"]["mainInvJSON"]), 100)

    def test_unknown_tool(self):
        self.assertTrue(self.replies[5]["isError"])

    def test_notes_are_private_to_the_state_directory(self):
        note = Path(content(self.replies[6])["appended_to"])
        self.assertEqual(note, self.state / "kb_seeds" / "测试.md")
        self.assertIn("本地笔记", note.read_text(encoding="utf-8"))
        self.assertTrue(self.replies[7]["isError"])
        self.assertFalse((self.state / "kb_seeds" / "子目录").exists())


if __name__ == "__main__":
    unittest.main()
