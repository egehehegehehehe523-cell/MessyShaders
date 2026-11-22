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
            "shaders/common/water_blocks_fragment.glsl",
            "shaders/lib/water.glsl",
            "shaders/common/shadow_fragment.glsl",
            "shaders/common/voxy.json",
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
        self.assertEqual(pack["shaders/lib/water_voxy.glsl"],
                         base["shaders/lib/water_voxy.glsl"])
        self.assertIn(b"MESSY_PBR_ENTITIES", pack["shaders/common/solid_blocks_fragment.glsl"])
        self.assertIn(b"MESSY_UNIFIED_WATER", pack["shaders/common/water_blocks_fragment.glsl"])
        self.assertIn(b"MESSY_UNIFIED_WATER", pack["shaders/common/water_voxy_blocks_fragment.glsl"])
        shadow_vertex = pack["shaders/clrwl_shadow.vsh"].decode()
        shadow_fragment = pack["shaders/clrwl_shadow.fsh"].decode()
        self.assertIn("SHADOW_DIST * messyShadowFalloff", shadow_vertex)
        self.assertIn("out vec2 messyShadowUV;", shadow_vertex)
        self.assertIn("in vec2 messyShadowUV;", shadow_fragment)
        self.assertIn("clrwl_computeFragment", shadow_fragment)
        self.assertNotIn(b"varying float visible_sky;",
                         pack["shaders/common/shadow_fragment.glsl"])
        self.assertIn(b"#define fog_adj messyWaterFog", pack["shaders/common/water_blocks_fragment.glsl"])
        self.assertIn(b"float messyWaterFog = smoothstep(float(MESSY_WATER_FOG_START)",
                      pack["shaders/common/water_voxy_blocks_fragment.glsl"])
        self.assertIn(b'#include "/src/finalcolor_voxy.glsl"',
                      pack["shaders/common/water_voxy_blocks_fragment.glsl"])
        self.assertNotIn(b"block_color.a = 1.0;", pack["shaders/common/water_blocks_fragment.glsl"])
        self.assertNotIn(b"blockColor.a = 1.0;", pack["shaders/common/water_voxy_blocks_fragment.glsl"])


if __name__ == "__main__":
    unittest.main()
