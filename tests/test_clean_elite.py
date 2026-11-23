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
            "shaders/common/skytextured_fragment.glsl",
            "shaders/common/deferred_fragment.glsl",
            "shaders/common/clouds_blocks_fragment.glsl",
            "shaders/lib/volumetric_clouds.glsl",
            "shaders/lib/water.glsl",
            "shaders/lib/water_voxy.glsl",
            "shaders/lib/messy_water_composite.glsl",
            "shaders/src/finalcolor_voxy.glsl",
            "shaders/src/finalcolor.glsl",
            "shaders/common/shadow_vertex.glsl",
            "shaders/common/voxy.json",
            "shaders/clrwl_gbuffers.vsh", "shaders/clrwl_gbuffers.fsh",
            "shaders/clrwl_shadow.vsh", "shaders/clrwl_shadow.fsh",
            "shaders/colorwheel.properties",
            "shaders/world0/voxy_opaque_lite.glsl",
            "shaders/world0/voxy_translucent_lite.glsl",
            "shaders/world-1/voxy_opaque_lite.glsl",
            "shaders/world-1/voxy_translucent_lite.glsl",
            "shaders/world1/voxy_opaque_lite.glsl",
            "shaders/world1/voxy_translucent_lite.glsl",
            "shaders/voxy_opaque_lite.glsl",
            "shaders/voxy_translucent_lite.glsl",
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
        # Iris intentionally ignores #if defined(...) when determining
        # whether to expose a Boolean shader option. Guard with #ifdef.
        self.assertIn(b"//#define MESSY_PBR_ENTITIES", pack["shaders/lib/config.glsl"])
        self.assertEqual(fragment.count("#ifdef MESSY_PBR_ENTITIES"), 2)
        self.assertNotIn("#if defined MESSY_PBR_ENTITIES", fragment)
        props = pack["shaders/shaders.properties"]
        self.assertIn(b"screen.MESSY_MATERIALS_SCREEN= MESSY_AUTO_PBR MESSY_PBR_ENTITIES", props)
        self.assertIn(b"screen.LabPBR= LabPBR POM POM_SHADOW LabEMISSIVE MESSY_PBR_ENTITIES", props)
        self.assertIn(b"option.MESSY_PBR_ENTITIES=IntegratedPBR on Entities", pack["shaders/lang/en_US.lang"])
        # Emissive ores/materials are a separate E-Lite feature and must not
        # be accidentally reset while making the entity toggle discoverable.
        config = pack["shaders/lib/config.glsl"]
        self.assertIn(b"#define EMISSIVE_ORE", config)
        self.assertIn(b"#define EMISSIVE_MATERIAL", config)
        self.assertIn(b"//#define LabEMISSIVE", config)
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
        self.assertIn(b"MESSY_WATER_DEFERRED MESSY_WATER_LIGHT_HANDOFF MESSY_WATER_DEBUG", pack["shaders/shaders.properties"])
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
        fog = pack["shaders/src/finalcolor_voxy.glsl"].decode()
        self.assertIn("if (customId == ENTITY_WATER)", fog)
        self.assertIn("messyWaterSceneFog(gaux4, gl_FragCoord.xy", fog)
        self.assertNotIn("messyNightMoment", fog)
        self.assertIn("saturate(vec3(0.592, 0.888, 1.233), 0.5)", fog)
        self.assertIn("MESSY_VOXY_CONTACT_SHADOWS", pack["shaders/lib/config.glsl"].decode())
        solid = pack["shaders/common/solid_voxy_blocks_fragment.glsl"].decode()
        self.assertNotIn("MESSY_VOXY_SHADOW_CONTRAST", solid)
        deferred = pack["shaders/common/deferred_fragment.glsl"].decode()
        self.assertIn("messySampleDepth = texture2DLod(vxDepthTexOpaque", deferred)
        self.assertIn("for (int messyI = 0; messyI < MESSY_VOXY_SHADOW_STEPS", deferred)
        self.assertIn("d3 >= messyDepth", deferred)
        self.assertIn("messyReceiverStability", deferred)
        self.assertIn("messyCaster = texture2DLod(colortex17", deferred)
        self.assertIn("min(messyThisHit, messyPreviousHit)", deferred)
        self.assertIn("block_color.rgb *= 1.0 - 0.7 *", deferred)
        self.assertIn(b"MESSY_VOXY_SHADOW_STEPS [MESSY_WATER_SCREEN]", pack["shaders/shaders.properties"])
        for world in ("world0", "world-1", "world1", ""):
            root = f"shaders/{world}/" if world else "shaders/"
            for surface in ("opaque", "translucent"):
                lite = pack[f"{root}voxy_{surface}_lite.glsl"]
                self.assertIn(b"VOXY_LITE_CONTRACT api=1;", lite)
                self.assertIn(b"transition=pack-distance-fade", lite)
                self.assertIn(b"#define MESSY_VOXY_LITE", lite)
        self.assertIn("messyLiteGlossWeight > 0.001", solid)

    def test_water_fog_tracks_actual_scene_sky_in_both_renderers(self):
        pack = read_source(SOURCE)
        patch(pack)
        near = pack["shaders/src/finalcolor.glsl"].decode()
        far = pack["shaders/src/finalcolor_voxy.glsl"].decode()
        shared = pack["shaders/lib/messy_water_composite.glsl"].decode()
        self.assertIn("vec3 messyWaterSceneFog(sampler2D sceneSky, vec2 uv)", shared)
        self.assertIn("texture2DLod(sceneSky, uv, 0.0).rgb", shared)
        self.assertNotIn("messyWaterNightFogWeight", shared)
        self.assertNotIn("messyNightFog", near + far)
        self.assertIn("vec4 messyWaterFogAfterBlend(vec4 source", shared)
        self.assertNotIn("messyWaterNightHandoff", shared)
        self.assertIn("f + (1.0 - f) * source.a", shared)
        self.assertIn("#define MESSY_WATER_FINALCOLOR", pack["shaders/common/water_blocks_fragment.glsl"].decode())
        self.assertIn("#define MESSY_WATER_FINALCOLOR_VOXY", pack["shaders/common/water_voxy_blocks_fragment.glsl"].decode())
        self.assertEqual(near.count("messyWaterFogAfterBlend(block_color"), 2)
        self.assertEqual(far.count("messyWaterFogAfterBlend(blockColor"), 2)
        self.assertIn("messyWaterSceneFog(gaux4, gl_FragCoord.xy", near)
        self.assertIn("messyWaterSceneFog(gaux4, gl_FragCoord.xy", far)

    def test_voxy_translucency_is_depth_composited_in_deferred(self):
        pack = read_source(SOURCE)
        patch(pack)
        config = pack["shaders/lib/config.glsl"].decode()
        manifest = pack["shaders/common/voxy.json"].decode()
        deferred = pack["shaders/common/deferred_fragment.glsl"].decode()
        self.assertIn("#define MESSY_WATER_DEFERRED", config)
        self.assertIn("const int colortex16Format = RGBA16F;", config)
        self.assertIn('"translucentDrawBuffers": [16]', manifest)
        self.assertIn('0: "off"', manifest)
        self.assertIn("uniform sampler2D colortex16;", deferred)
        self.assertIn("texture2DLod(colortex16, messyWaterUv, 0)", deferred)
        self.assertIn("vxProjInv * vec4(", deferred)
        self.assertIn("gbufferProjectionInverse * vec4(", deferred)
        self.assertIn("messyVanillaDistance - messyVoxyDistance", deferred)
        self.assertIn("messyFarWater.rgb, messyVoxyAlpha", deferred)

    def test_water_source_over_fog_identity_for_any_environment_brightness(self):
        from math import isclose

        def composite(source, alpha, backdrop):
            return alpha * source + (1.0 - alpha) * backdrop

        for alpha in (0.24, 0.5, 0.85):
            for fog in (0.0, 0.1, 0.5, 0.85, 1.0):
                for source, backdrop, fog_color in (
                    (0.25, 0.01, 0.16),
                    (0.82, 0.3, 0.33),
                    (0.02, 0.9, 0.45),
                ):
                    # Fog AFTER source-over is colour-independent. Both
                    # renderers use the actual sky buffer for fog_color.
                    corrected_alpha = fog + (1.0 - fog) * alpha
                    corrected_source = ((1.0 - fog) * alpha * source +
                                        fog * fog_color) / corrected_alpha
                    output = composite(corrected_source, corrected_alpha, backdrop)
                    expected = (1.0 - fog) * composite(source, alpha, backdrop) + fog * fog_color
                    self.assertTrue(isclose(output, expected, abs_tol=1e-8))

    def test_voxy_shadows_receive_material_tags_and_are_toggleable(self):
        pack = read_source(SOURCE)
        patch(pack)
        config = pack["shaders/lib/config.glsl"].decode()
        self.assertIn("#define MESSY_VOXY_CONTACT_SHADOWS", config)
        self.assertIn("const int colortex17Format = RGBA8", config)
        self.assertIn("layout(location = 2) out vec4 gbufferData2;",
                      pack["shaders/common/solid_voxy_blocks_fragment.glsl"].decode())
        self.assertIn("gbufferData2 = vec4(isFoliageEntity ? 1.0 : 0.0",
                      pack["shaders/common/solid_voxy_blocks_fragment.glsl"].decode())
        solid = pack["shaders/common/solid_voxy_blocks_fragment.glsl"].decode()
        self.assertIn("customId == ENTITY_EMMISIVE", solid)
        self.assertIn("customId == ENTITY_S_EMMISIVE", solid)
        self.assertIn("customId == ENTITY_F_EMMISIVE", solid)
        self.assertIn('"opaqueDrawBuffers": [1, 4, 17]',
                      pack["shaders/common/voxy.json"].decode())
        self.assertIn("#if defined VOXY && defined MESSY_VOXY_CONTACT_SHADOWS",
                      pack["shaders/common/deferred_fragment.glsl"].decode())
        self.assertIn("messySoftShadow *= 1.0 - clamp(messyFogFade",
                      pack["shaders/common/deferred_fragment.glsl"].decode())

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

    def test_custom_sky_suppression_and_moon_glint(self):
        pack = read_source(SOURCE)
        patch(pack)
        config = pack["shaders/lib/config.glsl"]
        props = pack["shaders/shaders.properties"]
        lang = pack["shaders/lang/en_US.lang"]
        sky = pack["shaders/common/skytextured_fragment.glsl"]
        self.assertIn(b"#define MESSY_HIDE_CUSTOM_SKY", config)
        self.assertIn(b"#define MESSY_MOON_REFLECTION 1 // [0 1 2]", config)
        self.assertIn(b"#ifdef MESSY_HIDE_CUSTOM_SKY", sky)
        self.assertIn(b"renderStage == MC_RENDER_STAGE_CUSTOM_SKY", sky)
        self.assertIn(b"MESSY_HIDE_CUSTOM_SKY", props)
        self.assertIn(b"screen.MESSY_WATER_SCREEN= MESSY_MOON_REFLECTION", props)
        self.assertIn(b"option.MESSY_MOON_REFLECTION=Moon Reflection on Water", lang)
        self.assertNotIn(b"MESSY_HIDE_VANILLA_CELESTIALS", config)
        self.assertNotIn(b"MESSY_HIDE_VANILLA_CELESTIALS", props)
        self.assertNotIn(b"MESSY_HIDE_VANILLA_CELESTIALS", lang)
        for water, matrix in (
            ("shaders/lib/water.glsl", "gbufferModelViewInverse"),
            ("shaders/lib/water_voxy.glsl", "vxModelViewInv"),
        ):
            body = pack[water].decode()
            self.assertIn("#if SUN_REFLECTION > 0 || MESSY_MOON_REFLECTION > 0", body)
            self.assertIn(f"mat3({matrix}) * astro_pos", body)
            self.assertNotIn(f"mat3({matrix}) * sunPosition", body)
            self.assertIn("float(MESSY_MOON_REFLECTION) * 0.5", body)
            self.assertIn("if (worldTime <= 13200) messyAstroStrength = 0.0;", body)
        self.assertIn(b"vec4 messyWaterCompose", pack["shaders/lib/messy_water_composite.glsl"])

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
