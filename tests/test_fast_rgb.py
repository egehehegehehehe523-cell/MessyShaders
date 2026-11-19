"""Fast RGB builder tests: ZIP integrity, classification and patch anchors."""
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from tools.patch_coverage_coating import parse_entities, expand_entities
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

    def test_mit_entity_groups_preserve_existing_ids(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "entity.properties").write_text(
                "entity.50020 = blaze \\\n modded:fire_spirit\\\n modded:fire_projectile\n"
                "entity.50048 = glow_squid modded:glow_fish\n"
                "entity.50088 = entity_flame modded:custom_flame\n",
                encoding="utf-8")
            pack = {"shaders/entity.properties": (
                "entity.10101=minecraft:lightning_bolt\n"
                "entity.10201=minecraft:entity_flame\n"
                "entity.26200=blaze\n"
            ).encode()}
            report = expand_entities(pack, root)
            assigned = parse_entities(pack["shaders/entity.properties"].decode())
            self.assertIn("modded:fire_spirit", assigned[26200])
            self.assertIn("modded:glow_fish", assigned[26201])
            self.assertIn("modded:custom_flame", assigned[26221])
            self.assertEqual(assigned[10201], ["minecraft:entity_flame"])
            self.assertNotIn("entity_flame", assigned[26221])
            self.assertEqual(report["mit_entity_groups"], 3)

    def test_zip_build(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            zsource = root / "source.zip"
            zout = root / "result.zip"
            src = {
                "shaders/shaders.properties": "# test\n#ifdef SHADOW_ENTITIES\n    shadowEntities = true\n#else\n    shadowEntities = false\n#endif\n",
                "shaders/src/light_vertex.glsl":
                    "start\n#ifdef DYN_HAND_LIGHT\nold\n#endif\n"
                    "#if defined GBUFFER_HAND\nend\n",
                "shaders/common/solid_blocks_vertex.glsl":
                    '#include "/lib/basic_utils.glsl"\n#include "/lib/luma.glsl"\n'
                    'varying vec3 omni_light;\n'
                    '#if WAVING == 1 || defined LabPBR\n#endif\n'
                    '#if defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)\n#endif\n'
                    '#if (MATERIAL_GLOSS > 0 && !defined NETHER) || MATERIAL_GLOSS > 1 || defined LabPBR || defined SHADOW_CASTING\n#endif\n'
                    '#if (MATERIAL_GLOSS > 0 && !defined NETHER) || MATERIAL_GLOSS > 1 || defined LabPBR || defined SHADOW_CASTING || defined EMISSIVE_MATERIAL\n#endif\n'
                    '#if (MATERIAL_GLOSS > 0 && !defined NETHER) || MATERIAL_GLOSS > 1 || defined LabPBR\n'
                    '        sub_position3 = sub_position.xyz;\n#endif\n'
                    '#include "/src/position_vertex.glsl"\nvoid main() {}\n',
                "shaders/common/water_blocks_vertex.glsl":
                    '#include "/lib/luma.glsl"\n'
                    '#include "/src/light_vertex.glsl"\n',
                "shaders/common/solid_blocks_fragment.glsl":
                    '#include "/lib/luma.glsl"\n'
                    'varying vec3 direct_light_color, candle_color, omni_light;\n'
                    '#if defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)\n'
                    '    #ifdef POM\n    #endif\n#endif\n'
                    '#if (MATERIAL_GLOSS > 0 && !defined NETHER) || MATERIAL_GLOSS > 1 || defined LabPBR || defined SHADOW_CASTING\n#endif\n'
                    '#if (MATERIAL_GLOSS > 0 && !defined NETHER) || MATERIAL_GLOSS > 1 || defined LabPBR || defined SHADOW_CASTING || defined EMISSIVE_MATERIAL\n#endif\n'
                    '    pure_block_color = texture2D(tex, final_uv);\n'
                    '    lowp float block_luma = luma(block_color.rgb);\n'
                    '    // === PBR auxiliary\n'
                    '    #if defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)\n'
                    '        vec3 bumpedNormal;\n'
                    '    #else\n'
                    '        #if MATERIAL_GLOSS < 1\n'
                    '            vec3 bumpedNormal = vec3(1.0);\n'
                    '        #else\n            vec3 bumpedNormal = flat_normal;\n        #endif\n    #endif\n'
                    '    #if !defined NETHER && defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)\n'
                    '    #endif\n'
                    '            float final_gloss_power = glossParms.g;\n'
                    '            float block_luma2 = pow(block_luma * glossParms.b, glossParms.a);\n'
                    '            float isMetal = 0.0;\n'
                    '            f0_val = reflex_index2;\n'
                    '    block_color.rgb *= mix(real_light, vec3(1.0), nightVision * 0.125);\n',
                "shaders/entity.properties": "entity.10101=minecraft:lightning_bolt\n",
                "shaders/common/shadow_vertex.glsl":
                    'attribute vec4 mc_Entity;\n    worldPos = positions.xyz;\n',
                "shaders/world0/shadow.vsh": "#version 120\n",
                "shaders/world0/shadow.fsh": "#version 120\n",
                "shaders/world-1/shadow.vsh": "#version 120\n",
                "shaders/world-1/shadow.fsh": "#version 120\n",
                "shaders/world1/shadow.vsh": "#version 120\n",
                "shaders/world1/shadow.fsh": "#version 120\n",
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
                vertex = z.read("shaders/common/solid_blocks_vertex.glsl").decode()
                self.assertIn('#include "/lib/luma.glsl"\n#include "/lib/messy_fast_lights.glsl"', vertex)
                self.assertLess(vertex.index('#include "/lib/luma.glsl"'),
                                vertex.index('#include "/lib/messy_fast_lights.glsl"'))
                water_vertex = z.read("shaders/common/water_blocks_vertex.glsl").decode()
                self.assertIn('#include "/lib/luma.glsl"\n#include "/lib/messy_fast_lights.glsl"', water_vertex)
                self.assertLess(water_vertex.index('#include "/lib/messy_fast_lights.glsl"'),
                                water_vertex.index('#include "/src/light_vertex.glsl"'))
                self.assertIn("coverage_coating", z.read("MESSYSHADERS_BUILD.json").decode())
                self.assertIn("MESSY_COATED_TEXTURES", z.read("shaders/lib/config.glsl").decode())
                self.assertNotIn("MESSY_IPBR_RELIEF", z.read("shaders/lib/config.glsl").decode())
                self.assertIn("Generated Normal Strength", z.read("shaders/lang/en_US.lang").decode())
                self.assertNotIn("Raised Texture Depth", z.read("shaders/lang/en_US.lang").decode())
                self.assertIn("uint packed = imageLoad(messyEmitVolume, p).r",
                              z.read("shaders/world0/prepare.csh").decode())
                self.assertIn("tier = 2u;  // XP orbs",
                              z.read("shaders/lib/messy_voxel_vertex.glsl").decode())
                self.assertIn("(15u << 8u)", z.read("shaders/lib/messy_voxel_vertex.glsl").decode())
                self.assertNotIn("messyOffsetUVW", z.read("shaders/common/solid_blocks_fragment.glsl").decode())
                self.assertNotIn("messyReliefDelta", z.read("shaders/common/solid_blocks_fragment.glsl").decode())
                self.assertIn("entity.26210", z.read("shaders/entity.properties").decode())
                self.assertIn("if (entity == 10201)", z.read("shaders/lib/messy_voxel_vertex.glsl").decode())
                self.assertIn("Generated Normal Strength", z.read("shaders/lang/en_US.lang").decode())
                self.assertIn("dynamic_ipbr", z.read("MESSYSHADERS_BUILD.json").decode())
                self.assertIn("entity.26201", z.read("shaders/entity.properties").decode())
                self.assertIn("messyWriteDynamicVoxel", z.read("shaders/common/shadow_vertex.glsl").decode())
                self.assertIn("MESSY_IPBR", z.read("shaders/lib/config.glsl").decode())
                self.assertIn("messyGeneratedNormal", z.read("shaders/common/solid_blocks_fragment.glsl").decode())
                self.assertIn("world_rgb", z.read("MESSYSHADERS_BUILD.json").decode())
                self.assertIn("image.messyEmitVolume",
                              z.read("shaders/shaders.properties").decode())
                self.assertIn("imageAtomicMax",
                              z.read("shaders/lib/messy_voxel_vertex.glsl").decode())
                self.assertIn("texture3D(messyRgbASampler",
                              z.read("shaders/common/solid_blocks_fragment.glsl").decode())
                self.assertEqual(len([x for x in z.namelist()
                                      if x.startswith("shaders/world0/prepare")
                                      and x.endswith(".csh")]), 7)
                self.assertEqual(json.loads(z.read("MESSYSHADERS_BUILD.json"))["euphoria_mit_catalog"], False)

if __name__ == "__main__":
    unittest.main()
