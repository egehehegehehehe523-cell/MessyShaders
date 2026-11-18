"""Fast RGB builder tests: ZIP integrity, classification and patch anchors."""
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from tools.build_fast_rgb import (
    apply_overrides, build, emitter_entries, parse_properties,
    rewrite_property_table, BLOCK_IDS, ITEM_IDS,
)

class FastRgbTests(unittest.TestCase):
    def test_multiline_properties(self):
        table = parse_properties("block.21004 = mod:red_lamp \\\n mod:red_torch \\\n mod:red_candle\n# comment\nblock.22 = dirt\n")
        self.assertEqual(table[21004], ["mod:red_lamp", "mod:red_torch", "mod:red_candle"])

    def test_collision_removed_from_old_id(self):
        old = "item.11001 = minecraft:torch minecraft:stone\nitem.11002 = minecraft:soul_torch\n"
        s, n = rewrite_property_table(old, {"orange": {"minecraft:torch"}}, "item")
        self.assertEqual(n, 1)
        self.assertEqual(parse_properties(s)[11001], ["minecraft:stone"])
        self.assertEqual(parse_properties(s)[ITEM_IDS["orange"]], ["minecraft:torch"])

    def test_euphoria_mit_catalog(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            folder = root / "blockProperties" / "1.13+"
            folder.mkdir(parents=True)
            (folder / "block.10944-21044.properties").write_text(
                "# MIT\nblock.21004 = example:red_lamp \\\n example:red_beacon\n"
                "block.21018 = example:blue_lamp\n", encoding="utf-8")
            (root / "item.properties").write_text(
                "# Modded Light Source - Red\n"
                "item.44055 = example:red_lamp \\\n example:red_beacon\n"
                "# Another heading\n"
                "# Modded Light Source - Blue\n"
                "item.44075 = example:blue_lamp\n", encoding="utf-8")
            blocks = emitter_entries(root, "block")
            items = emitter_entries(root, "item")
            self.assertIn("example:red_lamp", blocks["red"])
            self.assertIn("example:blue_lamp", blocks["blue"])
            self.assertIn("example:red_beacon", items["red"])
            self.assertIn("example:blue_lamp", items["blue"])

    def test_zip_build(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            zsource = root / "source.zip"
            zout = root / "result.zip"
            src = {
                "shaders/shaders.properties": "# test\n",
                "shaders/src/light_vertex.glsl":
                    "start\n#ifdef DYN_HAND_LIGHT\nold\n#endif\n"
                    "#if defined GBUFFER_HAND\nend\n",
                "shaders/common/solid_blocks_vertex.glsl":
                    '#include "/lib/basic_utils.glsl"\nvoid main() {}\n',
                "shaders/common/final_fragment.glsl":
                    "block_color = pow(block_color.rgb, vec3(1 / GAMMA));\n",
                "shaders/lib/config.glsl": "#define DYN_HAND_LIGHT\n",
                "shaders/item.properties": "item.11001 = minecraft:torch minecraft:stone\n",
                "shaders/block.properties": "block.123 = minecraft:torch minecraft:stone\n",
            }
            with ZipFile(zsource, "w") as z:
                for key, val in src.items():
                    z.writestr("E-Lite-archive/" + key, val)
            info = build(zsource, zout, None)
            self.assertGreater(info["item_classified"], 5)
            self.assertGreater(info["block_classified"], 5)
            with ZipFile(zout) as z:
                self.assertIsNone(z.testzip())
                self.assertIn("shaders/lib/messy_fast_lights.glsl", z.namelist())
                self.assertNotIn("E-Lite-archive/shaders/shaders.properties", z.namelist())
                self.assertIn("26100", z.read("shaders/lib/messy_fast_lights.glsl").decode())
                self.assertIn("MESSY_TONE", z.read("shaders/lib/config.glsl").decode())
                self.assertIn("no multi-source RGB propagation",
                              z.read("MESSYSHADERS_BUILD.json").decode())
                self.assertEqual(json.loads(z.read("MESSYSHADERS_BUILD.json"))["euphoria_mit_catalog"], False)

if __name__ == "__main__":
    unittest.main()
