import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_elite_materials_voxy import patch, SOURCE, read_source


class CleanEliteTest(unittest.TestCase):
    def test_clean_base_with_materials_and_voxy_fog(self):
        base = read_source(SOURCE)
        pack = dict(base)
        patch(pack)
        changed = {path for path, data in pack.items() if data != base.get(path)}
        self.assertEqual(changed, {
            "shaders/lib/config.glsl", "shaders/shaders.properties",
            "shaders/lang/en_US.lang", "shaders/common/solid_blocks_fragment.glsl",
            "shaders/common/solid_blocks_vertex.glsl",
            "shaders/common/solid_voxy_blocks_fragment.glsl",
            "shaders/common/water_voxy_blocks_fragment.glsl",
            "shaders/common/voxy.json",
            "shaders/lib/water_voxy.glsl",
            "shaders/clrwl_gbuffers.vsh", "shaders/clrwl_gbuffers.fsh",
            "shaders/clrwl_shadow.vsh", "shaders/clrwl_shadow.fsh",
            "shaders/colorwheel.properties",
        })
        self.assertNotIn("messyRgb", b"".join(pack.values()).decode("utf-8", "ignore"))
        for path in ("shaders/common/solid_voxy_blocks_fragment.glsl",
                     "shaders/common/water_voxy_blocks_fragment.glsl"):
            self.assertIn(b"MESSY_VOXY_FOG_START", pack[path])
            self.assertIn(b"MESSY_VOXY_FOG_SPAN", pack[path])
        self.assertIn(b"MESSY_AUTO_PBR", pack["shaders/common/solid_blocks_fragment.glsl"])
        fragment = pack["shaders/common/solid_blocks_fragment.glsl"].decode()
        self.assertNotIn("omni_light *=", fragment)
        self.assertEqual(fragment.count("computeRealLight(messyOmniLight,"), 3)
        self.assertIn(b"screen.MESSY_FEATURES", pack["shaders/shaders.properties"])
        self.assertIn(b"water_absortion *= water_absortion;", pack["shaders/lib/water_voxy.glsl"])


if __name__ == "__main__":
    unittest.main()
