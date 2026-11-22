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
            "shaders/common/deferred_fragment.glsl",
            "shaders/common/clouds_blocks_fragment.glsl",
            "shaders/lib/volumetric_clouds.glsl",
            "shaders/lib/water.glsl",
            "shaders/lib/water_voxy.glsl",
            "shaders/lib/messy_water_composite.glsl",
            "shaders/common/shadow_vertex.glsl",
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
        self.assertIn(b"vxDepthTexOpaque", pack["shaders/lib/water_voxy.glsl"])
        self.assertIn(b"bump *= vec3(NdotE) + vec3(0.05, 0.1, 1.0 - NdotE)",
                      pack["shaders/lib/water_voxy.glsl"])
        self.assertIn(b"rainStrength * 0.333 * WATER_TURBULENCE",
                      pack["shaders/lib/water_voxy.glsl"])
        self.assertIn(b"vxDepthTexOpaque", pack["shaders/lib/water.glsl"])
        self.assertIn(b"vxProjInv", pack["shaders/lib/water_voxy.glsl"])
        self.assertIn(b'"vxDepthTexOpaque": "sampler2D"',
                      pack["shaders/common/voxy.json"])
        self.assertIn(b'"excludeLodsFromVanillaDepth": true',
                      pack["shaders/common/voxy.json"])
        self.assertIn(b'0: "SRC_ALPHA ONE_MINUS_SRC_ALPHA ONE ONE_MINUS_SRC_ALPHA"',
                      pack["shaders/common/voxy.json"])
        self.assertIn(b"out float waterAlpha", pack["shaders/lib/water_voxy.glsl"])
        self.assertIn(b"blockColor = messyWaterCompose(", pack["shaders/common/water_voxy_blocks_fragment.glsl"])
        self.assertIn(b"block_color = messyWaterCompose(", pack["shaders/common/water_blocks_fragment.glsl"])
        self.assertIn(b"water_absortion = messyWaterOpacity(water_absortion)", pack["shaders/lib/water.glsl"])
        self.assertIn(b"water_absortion = messyWaterOpacity(water_absortion)", pack["shaders/lib/water_voxy.glsl"])
        self.assertIn(b"out float waterAlpha", pack["shaders/lib/water.glsl"])
        self.assertIn(b"float messyWaterOpacity(float thickness)", pack["shaders/lib/messy_water_composite.glsl"])
        self.assertIn(b"float messyWaterOpaqueDistance(vec2 uv, sampler2D depthMap, mat4 projectionInv)",
                      pack["shaders/lib/messy_water_composite.glsl"])
        self.assertIn(b"vec3 messyWaterWaves(vec3 pos, float visibleSky", 
                      pack["shaders/lib/messy_water_composite.glsl"])
        self.assertIn(b"vec3 messyWaterDistantLight(int ticks, float rain)",
                      pack["shaders/lib/messy_water_composite.glsl"])
        self.assertIn(b"float messyWaterDistanceFog(float cameraDistance)",
                      pack["shaders/lib/messy_water_composite.glsl"])
        self.assertIn(b"blend.gbuffers_water=SRC_ALPHA ONE_MINUS_SRC_ALPHA ONE ONE_MINUS_SRC_ALPHA", pack["shaders/shaders.properties"])
        self.assertIn(b"#if defined MESSY_WATER_PARITY && defined VOXY", pack["shaders/common/water_blocks_fragment.glsl"])
        self.assertIn(b"return color;", pack["shaders/lib/water_voxy.glsl"])
        self.assertIn(b"MESSY_PBR_ENTITIES", pack["shaders/common/solid_blocks_fragment.glsl"])
        self.assertIn(b"MESSY_WATER_PARITY", pack["shaders/common/water_blocks_fragment.glsl"])
        self.assertIn(b"MESSY_WATER_PARITY", pack["shaders/common/water_voxy_blocks_fragment.glsl"])
        self.assertNotIn(b"MESSY_UNIFIED_WATER", pack["shaders/lib/config.glsl"])
        self.assertNotIn(b"MESSY_UNIFIED_WATER", pack["shaders/shaders.properties"])
        self.assertNotIn(b"MESSY_UNIFIED_WATER", pack["shaders/lang/en_US.lang"])
        self.assertNotIn(b"MESSY_UNIFIED_WATER_DARKNESS", pack["shaders/common/water_blocks_fragment.glsl"])
        shadow_vertex = pack["shaders/clrwl_shadow.vsh"].decode()
        shadow_fragment = pack["shaders/clrwl_shadow.fsh"].decode()
        self.assertIn("SHADOW_DIST * messyShadowFalloff", shadow_vertex)
        self.assertIn("out vec2 messyShadowUV;", shadow_vertex)
        self.assertIn("in vec2 messyShadowUV;", shadow_fragment)
        self.assertIn("clrwl_computeFragment", shadow_fragment)
        self.assertIn(b"varying float visible_sky;",
                      pack["shaders/common/shadow_fragment.glsl"])
        self.assertIn(b"varying float visible_sky;",
                      pack["shaders/common/shadow_vertex.glsl"])
        self.assertIn(b"visible_sky = clamp(gl_MultiTexCoord1.y / 240.0",
                      pack["shaders/common/shadow_vertex.glsl"])
        self.assertIn(b"#define fog_adj messyWaterFog", pack["shaders/common/water_blocks_fragment.glsl"])
        self.assertIn(b"float messyWaterFog = messyWaterDistanceFog(fogFragCoord)",
                      pack["shaders/common/water_voxy_blocks_fragment.glsl"])
        self.assertIn(b'#include "/src/finalcolor_voxy.glsl"',
                      pack["shaders/common/water_voxy_blocks_fragment.glsl"])
        self.assertNotIn(b"block_color.a = 1.0;", pack["shaders/common/water_blocks_fragment.glsl"])
        self.assertNotIn(b"blockColor.a = 1.0;", pack["shaders/common/water_voxy_blocks_fragment.glsl"])
        self.assertIn(b"#define MESSY_WATER_LIGHT_HANDOFF", pack["shaders/lib/config.glsl"])
        self.assertIn(b"MESSY_WATER_LIGHT_HANDOFF MESSY_WATER_DEBUG", pack["shaders/shaders.properties"])
        self.assertIn(b"value.MESSY_WATER_DEBUG.2=Pre-Reflection Surface (Lit)",
                      pack["shaders/lang/en_US.lang"])
        self.assertIn(b"real_light = mix(real_light,\n                        messyWaterDistantLight(worldTime, rainStrength)",
                      pack["shaders/common/water_blocks_fragment.glsl"])
        self.assertIn(b"realLight = messyWaterDistantLight(worldTime, rainStrength);",
                      pack["shaders/common/water_voxy_blocks_fragment.glsl"])
        # The near curve must finish before the LOD handoff; far water uses the
        # same reference with no separate per-voxel light bias.
        self.assertIn(b"smoothstep(far * 0.5, far * 0.9,",
                      pack["shaders/common/water_blocks_fragment.glsl"])
        self.assertIn(b"#define MESSY_WATER_DEBUG 0", pack["shaders/lib/config.glsl"])
        self.assertIn(b"MESSY_WATER_DEBUG", pack["shaders/shaders.properties"])
        self.assertIn(b"messyWaterDebugValue", pack["shaders/common/water_blocks_fragment.glsl"])
        self.assertIn(b"messyWaterDebugValue", pack["shaders/common/water_voxy_blocks_fragment.glsl"])

    def test_voxy_clouds_obey_distant_terrain_depth(self):
        pack = read_source(SOURCE)
        patch(pack)
        deferred = pack["shaders/common/deferred_fragment.glsl"].decode()
        raymarch = pack["shaders/lib/volumetric_clouds.glsl"].decode()
        vanilla = pack["shaders/common/clouds_blocks_fragment.glsl"].decode()
        self.assertIn("texture2DLod(vxDepthTexOpaque,", deferred)
        self.assertIn("vxProjInv * vec4(", deferred)
        self.assertIn("messyCloudOcclusionDistance > messyCloudEntry", deferred)
        self.assertIn("messyCloudOcclusionDistance);", deferred)
        self.assertIn("if (messySampleDistance >= maxCloudDistance) break;", raymarch)
        self.assertIn("if (t >= maxCloudDistance) continue;", raymarch)
        self.assertIn("float density = 0.0;", raymarch)
        self.assertIn("float density_2 = 0.0;", raymarch)
        self.assertIn("1.0, 1.0, 1.0e7);", pack["shaders/common/water_blocks_fragment.glsl"].decode())
        self.assertIn("float depthVoxy = texture2D(vxDepthTexOpaque, screenCoord).r;", vanilla)
        self.assertIn("float distDH = mix(length(vxViewPos.xyz)", vanilla)

    def test_same_water_compositor_is_mathematically_consistent(self):
        # Verify the shared GLSL source-over decomposition for both pipelines:
        # shader_old = (1-f)*((1-a)*background+a*surface)+f*reflect+sun.
        # shader_new = alpha*source+(1-alpha)*background.
        from math import isclose
        for absorption in (0.2481, 0.33, 0.55, 0.91, 1.0):
            for reflection in (0.0, 0.15, 0.4, 0.9, 1.0):
                opacity = absorption + (1.0 - absorption) * reflection
                for background, surface, reflected, sunlight in (
                    (0.05, 0.6, 0.9, 0.0),
                    (0.8, 0.05, 0.4, 0.06),
                    (0.2, 0.4, 1.4, 0.5),
                ):
                    shaded = (1.0 - reflection) * surface + reflection * reflected + sunlight
                    premultiplied = shaded - (1.0 - reflection) * (1.0 - absorption) * surface
                    source = premultiplied / max(opacity, 0.001)
                    old = (1.0 - reflection) * ((1.0 - absorption) * background + absorption * surface) + reflection * reflected + sunlight
                    new = opacity * source + (1.0 - opacity) * background
                    self.assertTrue(isclose(old, new, abs_tol=1e-7))


if __name__ == "__main__":
    unittest.main()
