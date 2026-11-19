"""Fast RGB builder tests: ZIP integrity, classification and patch anchors."""
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from tools.patch_coverage_coating import parse_entities, expand_entities
from tools.patch_world_rgb import PROPAGATION_STRIDES, diffusion_source
from tools.build_fast_rgb import (
    SOURCE, read_source, apply_overrides, build, emitter_entries, parse_properties,
    rewrite_property_table, BLOCK_IDS, ITEM_IDS,
)

class FastRgbTests(unittest.TestCase):
    def test_water_depth_and_near_shader_remain_stable(self):
        base = read_source(SOURCE)
        generated = dict(base)
        apply_overrides(generated, None)
        self.assertEqual(generated["shaders/lib/water.glsl"],
                         base["shaders/lib/water.glsl"])
        far = generated["shaders/lib/water_voxy.glsl"].decode()
        # Only the three shading constants change in Voxy's library; the
        # sensitive water depth and refraction code is byte-for-byte intact.
        far = far.replace("rainStrength * 0.333 * WATER_TURBULENCE",
                          "rainStrength * 0.6 * WATER_TURBULENCE")
        far = far.replace("bump *= vec3(NdotE) + vec3(0.05, 0.1, 1.0 - NdotE);",
                          "bump *= vec3(NdotE) + vec3(0.0, 0.0, 1.0 - NdotE);")
        far = far.replace("mix(vec3(0.95, 1.0, 1.0), vec3(0.8, 1.1, 1.4) * 0.9, water_absortion)",
                          "mix(vec3(0.9, 1.0, 1.0), vec3(0.8, 1.3, 1.6) * 0.9, water_absortion)")
        self.assertEqual(far.encode(), base["shaders/lib/water_voxy.glsl"])

    def test_rgb_propagation_range_keeps_six_dispatches_and_checks_walls(self):
        self.assertEqual(len(PROPAGATION_STRIDES), 6)
        self.assertEqual(sum(PROPAGATION_STRIDES), 10)
        code = diffusion_source("messyRgbA", "messyRgbB", 2)
        self.assertIn("const int messyStride = 2;", code)
        self.assertIn("p + offset / 2", code)
        self.assertIn("imageLoad(messyOpaqueVolume", code)

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
                "shaders/shaders.properties": "# test\n#ifdef SHADOW_ENTITIES\n    shadowEntities = true\n#else\n    shadowEntities = false\n#endif\nuniform.float.pale_garden = smooth(if(in(biome, BIOME_PALE_GARDEN), 1, 0), 60, 60)\nsliders = MATERIAL_GLOSS\n",
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
                    '        float shadow_c_relief;\n'
                    '        if(foliageData.x < 0.3) {  \n'
                    '            vec3 shadowLightDir = mix(-sunPosition, sunPosition, light_mix) * 0.01;\n'
                    '            float diffuseRelief = clamp(dot(bumpedNormal, shadowLightDir), 0.0, 1.0);\n'
                    '            shadow_c_relief = (isGrass < 0.5) ? sqrt(directLight2 * diffuseRelief) : directLight2;\n'
                    '        } else {\n'
                    '            shadow_c_relief = directLight2;\n'
                    '        }\n'
                    '    #else\n'
                    '        float shadow_c_relief = directLight2;\n'
                    '    #endif\n'
                    '            currentRoughness = squarePow(1.0 - smoothness);\n'
                    '            float final_gloss_power = glossParms.g;\n'
                    '            float block_luma2 = pow(block_luma * glossParms.b, glossParms.a);\n'
                    '            float isMetal = 0.0;\n'
                    '            f0_val = reflex_index2;\n'
                    '    #if defined LabPBR && defined POM && defined POM_SHADOW && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)\n'
                    '        vec3 gloss;\n        if(block_type != 1.0){\n'
                    '        }\n'
                    '        vec3 real_light = computeRealLight(omni_light, direct_light_color, directLight2, shadow_c, vec3(0.0), candle_color);\n'
                    '    block_color.rgb *= mix(real_light, vec3(1.0), nightVision * 0.125);\n'
                    '    #include "/src/writebuffers.glsl"\n',
                "shaders/common/solid_voxy_blocks_fragment.glsl":
                    '#include "/lib/luma.glsl"\n'
                    '        float material_gloss_factor = materialGloss(reflect(viewPositionNormalized, normal), lmcoord, glossPower, normal) * glossFactor;\n'
                    '    blockColor.rgb *= mix(realLight, vec3(1.0), nightVision * 0.125);\n',
                "shaders/common/water_voxy_blocks_fragment.glsl":
                    '#include "/lib/luma.glsl"\n'
                    '            clamp(fogFragCoord / float(vxRenderDistance * 16), 0.0, 1.0),\n'
                    '    vec4 worldPos = vxModelViewInv * viewSpacePos4D;\n'
                    '        vec3 waterNormalBase = normal_waves_voxy(worldposition.xzy);\n'
                    '    realLight = vec3(0.0) +\n                candleColor;\n'
                    '    realLight = vec3(0.0) +\n                candleColor;\n'
                    '    realLight = vec3(0.0) +\n                candleColor;\n',
                "shaders/common/voxy.json":
                    '    "endFlashIntensity",\n"frameTimeCounter",\n"noisetex": "sampler2D",\n'
                    '    "vxDepthTexTrans": "sampler2D"\n',
                "shaders/common/water_blocks_fragment.glsl":
                    '    uniform sampler2D vxDepthTexTrans;\n'
                    '        vec3 water_normal_base = normal_waves(worldposition.xzy);\n',
                "shaders/lib/water.glsl":
                    'float earth_distance_vx = texture2D(vxDepthTexTrans, pos.xy).r;\n',
                "shaders/lib/water_voxy.glsl":
                    'rainStrength * 0.6 * WATER_TURBULENCE\n'
                    'bump *= vec3(NdotE) + vec3(0.0, 0.0, 1.0 - NdotE);\n'
                    'float earth_distance = texture2D(vxDepthTexTrans, pos.xy).x;\n'
                    '        water_absortion = max(earth_distance - water_distance, 0.0);\n'
                    '        water_absortion = (1.0 / -((water_absortion * WATER_ABSORPTION) + 1.33)) + 1.0;\n'
                    'mix(vec3(0.9, 1.0, 1.0), vec3(0.8, 1.3, 1.6) * 0.9, water_absortion)\n',
                "shaders/src/voxy_position_light.glsl":
                    'float visibleSky = clamp(illumination.y, 0.0, 1.0);\n',
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
            # Lite LOD pairs are loaded by Neo-Voxy from every available
            # dimension directory and share the same runtime contract.
            for dim in ("world0", "world-1", "world1", ""):
                prefix = f"shaders/{dim}/" if dim else "shaders/"
                src[prefix + "voxy_opaque.glsl"] = (
                    '#define VOXY_BLOCK\n#include "/common/solid_voxy_blocks_fragment.glsl"\n')
                src[prefix + "voxy_translucent.glsl"] = (
                    '#define VOXY_WATER\n#include "/common/water_voxy_blocks_fragment.glsl"\n')
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
                seed = z.read("shaders/world0/prepare.csh").decode()
                self.assertIn("uint messyPackedVoxel = imageLoad(messyEmitVolume, p).r", seed)
                self.assertIn("uint idx = messyPackedVoxel & 255u;", seed)
                self.assertIn("(messyPackedVoxel >> 8u)", seed)
                # 'packed' is a GLSL layout qualifier, not a safe variable.
                self.assertNotRegex(seed, r"\b(?:uint|int|float)\s+packed\b")
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
                config = z.read("shaders/lib/config.glsl").decode()
                self.assertIn("#undef MESSY_IPBR", config)
                self.assertIn("#undef MESSY_COATED_TEXTURES", config)
                self.assertIn("#ifndef MESSY_UNSAFE_MATERIAL_PREVIEW", config)
                self.assertGreater(config.index("#undef MESSY_IPBR"),
                                   config.index("// #define MESSY_IPBR"))
                self.assertIn("#define MESSY_AUTO_MATERIALS\n", config)
                self.assertIn("#define MESSY_AUTO_NORMAL_STRENGTH 1.0", config)
                self.assertGreater(config.index("#define MESSY_AUTO_MATERIALS"),
                                   config.index("#undef MESSY_IPBR"))
                fragment = z.read("shaders/common/solid_blocks_fragment.glsl").decode()
                vertex = z.read("shaders/common/solid_blocks_vertex.glsl").decode()
                auto_lib = z.read("shaders/lib/messy_procedural_pbr.glsl").decode()
                self.assertIn("#elif defined MESSY_AUTO_MATERIALS && !defined LabPBR", fragment)
                self.assertIn("bumpedNormal = messyAutoBumpedNormal(", fragment)
                self.assertIn("currentRoughness = messyAutoMaterialRoughness(", fragment)
                self.assertIn("messyAutoMissingMaps", fragment)
                self.assertIn("texture2D(normals, texcoord)", fragment)
                self.assertIn("texture2D(specular, texcoord)", fragment)
                self.assertIn("shadow_c_relief, shadow_c, vec3(0.0), candle_color", fragment)
                self.assertIn("block_color.rgb = vec3(clamp(messyBumpAmount * 5.0", fragment)
                self.assertIn("defined LabPBR || defined MESSY_IPBR || defined MESSY_AUTO_MATERIALS", vertex)
                self.assertIn("texture2D(albedo, rightUV)", auto_lib)
                self.assertIn("texture2D(albedo, leftUV)", auto_lib)
                self.assertIn("texture2D(albedo, upUV)", auto_lib)
                self.assertIn("texture2D(albedo, downUV)", auto_lib)
                self.assertIn("distanceToCamera > 56.0", auto_lib)
                self.assertIn("rainWetness * (0.12 + 0.06 * polished)", auto_lib)
                self.assertIn("Automatic Block Materials", z.read("shaders/lang/en_US.lang").decode())
                self.assertIn("Visualize Normal Relief", z.read("shaders/lang/en_US.lang").decode())
                props = z.read("shaders/shaders.properties").decode()
                self.assertIn("MESSY_AUTO_MATERIALS MESSY_AUTO_NORMAL_STRENGTH", props)
                self.assertIn("sliders = MESSY_AUTO_NORMAL_STRENGTH ", props)
                self.assertFalse(info["dynamic_ipbr"]["procedural_pbr"]["enabled_by_default"])
                self.assertFalse(info["native_auto_materials"]["water_lod_changes"])
                self.assertFalse(info["lod_shading"]["water_depth_refraction_formula_changed"])
                self.assertIn("/ 32.0", z.read("shaders/common/water_voxy_blocks_fragment.glsl").decode())
                self.assertIn("illumination.y - 0.0695", z.read("shaders/src/voxy_position_light.glsl").decode())
                self.assertIn("max_propagation_reach", z.read("MESSYSHADERS_BUILD.json").decode())
                self.assertIn("world_rgb", z.read("MESSYSHADERS_BUILD.json").decode())
                self.assertIn("image.messyEmitVolume",
                              z.read("shaders/shaders.properties").decode())
                self.assertIn("imageAtomicMax",
                              z.read("shaders/lib/messy_voxel_vertex.glsl").decode())
                self.assertIn("messyAppliedRGB(messyLightUVW, frameCounter)",
                              z.read("shaders/common/solid_blocks_fragment.glsl").decode())
                self.assertIn("messyDiffuseFactor",
                              z.read("shaders/common/solid_blocks_fragment.glsl").decode())
                self.assertIn("shadow_c_relief = directLight2 * messyDiffuseFactor",
                              z.read("shaders/common/solid_blocks_fragment.glsl").decode())
                self.assertNotIn("real_light *= messyDiffuseFactor",
                                 z.read("shaders/common/solid_blocks_fragment.glsl").decode())
                self.assertIn("vec3 gloss = vec3(0.0);",
                              z.read("shaders/common/solid_blocks_fragment.glsl").decode())
                self.assertIn("image.messyRgbHistoryA", z.read("shaders/shaders.properties").decode())
                self.assertIn("image.messyRgbHistoryB", z.read("shaders/shaders.properties").decode())
                self.assertIn("vec3 oldLight", z.read("shaders/world0/prepare_g.csh").decode())
                self.assertIn("messyRgbHistoryASampler",
                              z.read("shaders/common/voxy.json").decode())
                rgb_lib = z.read("shaders/lib/messy_rgb_sample.glsl").decode()
                self.assertIn("#if !defined(VOXY_BLOCK) && !defined(VOXY_WATER)", rgb_lib)
                self.assertIn("return texture(sourceField, uv).rgb;", rgb_lib)
                self.assertIn("return texture3D(sourceField, uv).rgb;", rgb_lib)
                lite_meta = z.read("shaders/common/voxy.json").decode()
                self.assertIn("#if MC_VERSION >= 12109", lite_meta)
                self.assertIn("messyLiteGlossWeight",
                              z.read("shaders/common/solid_voxy_blocks_fragment.glsl").decode())
                for dim in ("world0", "world-1", "world1", ""):
                    prefix = f"shaders/{dim}/" if dim else "shaders/"
                    for kind in ("opaque", "translucent"):
                        lite = z.read(prefix + f"voxy_{kind}_lite.glsl").decode()
                        self.assertIn("VOXY_LITE_CONTRACT api=1;", lite)
                        self.assertIn("transition=pack-distance-fade", lite)
                        self.assertIn("#define MESSY_VOXY_LITE", lite)
                self.assertIn("messyAppliedRGB(messyVoxyUVW, frameCounter)",
                              z.read("shaders/common/solid_voxy_blocks_fragment.glsl").decode())
                water_voxy = z.read("shaders/common/water_voxy_blocks_fragment.glsl").decode()
                self.assertIn("messyWaterRGB", water_voxy)
                self.assertNotIn("messyFarWave", water_voxy)
                self.assertNotIn("messyNearWave", z.read("shaders/common/water_blocks_fragment.glsl").decode())
                self.assertNotIn("water_absortion *= water_absortion;",
                                 z.read("shaders/lib/water_voxy.glsl").decode())
                self.assertNotIn("vxDepthTexOpaque", lite_meta)
                self.assertIn("uniform.float.pale_garden = 0.0",
                              z.read("shaders/shaders.properties").decode())
                self.assertIn("#ifdef MESSY_COATED_TEXTURES",
                              z.read("shaders/common/solid_blocks_fragment.glsl").decode())
                self.assertEqual(water_voxy.count("candleColor + messyWaterRGB;"), 3)
                self.assertIn("clrwl_computeFragment", z.read("shaders/clrwl_gbuffers.fsh").decode())
                self.assertIn("clrwl_computeFragment", z.read("shaders/clrwl_shadow.fsh").decode())
                self.assertIn("oit.gbuffers.colortex1 = 0",
                              z.read("shaders/colorwheel.properties").decode())
                self.assertEqual(len([x for x in z.namelist()
                                      if x.startswith("shaders/world0/prepare")
                                      and x.endswith(".csh")]), 8)
                self.assertEqual(json.loads(z.read("MESSYSHADERS_BUILD.json"))["euphoria_mit_catalog"], False)

if __name__ == "__main__":
    unittest.main()
