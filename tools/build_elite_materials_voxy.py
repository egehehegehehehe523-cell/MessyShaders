#!/usr/bin/env python3
"""Clean E-Lite 5.1.3 with modest atlas-material fallback and Voxy fog.

Does not import the experimental RGB lighting or post-processing patches.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "§lE-LITE shaders 5.1.3.zip"


def read_source(source: Path) -> dict[str, bytes]:
    with ZipFile(source) as archive:
        files = {name: archive.read(name) for name in archive.namelist()
                 if name.startswith("shaders/") and not name.endswith("/")}
    if "shaders/shaders.properties" not in files:
        raise ValueError("E-Lite shaders root not found")
    return files


def replace_one(pack: dict[str, bytes], path: str, old: str, new: str) -> None:
    src = pack[path].decode("utf-8")
    if src.count(old) != 1:
        raise ValueError(f"Expected one anchor in {path}, found {src.count(old)}")
    pack[path] = src.replace(old, new, 1).encode("utf-8")


def patch_custom_sky_and_moon_glint(pack: dict[str, bytes]) -> None:
    """Hide resource sky layers and repair high-quality moon glints on water.

    Only the sun/moon highlight changes in the two water implementations;
    neither the shared water compositor nor the Voxy handoff is touched.
    """
    props = "shaders/shaders.properties"
    replace_one(pack, props,
                "#if ROUND_SUN == 1\n    sun = false\n#else\n    sun = true\n#endif\n\nmoon = true",
                """// Optional compatibility for external celestial renderers (e.g. NTM: Space).
// These Iris flags suppress vanilla discs, not third-party Golem Core skyboxes.
#ifdef MESSY_HIDE_VANILLA_CELESTIALS
    sun = false
    moon = false
#else
    #if ROUND_SUN == 1
        sun = false
    #else
        sun = true
    #endif
    moon = true
#endif""")
    sky = "shaders/common/skytextured_fragment.glsl"
    replace_one(pack, sky, "uniform sampler2D tex;",
                "uniform sampler2D tex;\n#ifdef IS_IRIS\n    uniform int renderStage;\n#endif")
    replace_one(pack, sky,
                "void main() {\n    //if(fragment_cull()) discard;",
                """void main() {
    #if defined IS_IRIS && defined MC_RENDER_STAGE_CUSTOM_SKY
        #ifdef MESSY_HIDE_CUSTOM_SKY
            // FabricSkyBoxes/OptiFine sky layers are a distinct Iris stage;
            // the vanilla sun, moon and stars are left intact.
            if (renderStage == MC_RENDER_STAGE_CUSTOM_SKY) discard;
        #endif
    #endif
    //if(fragment_cull()) discard;""")

    for water, model_view in (
        ("shaders/lib/water.glsl", "gbufferModelViewInverse"),
        ("shaders/lib/water_voxy.glsl", "vxModelViewInv"),
    ):
        replace_one(pack, water,
                    "#if SUN_REFLECTION > 0\n    #if !defined NETHER && !defined THE_END",
                    "#if SUN_REFLECTION > 0 || MESSY_MOON_REFLECTION > 0\n"
                    "    #if !defined NETHER && !defined THE_END")
        replace_one(pack, water,
                    f"vec3 sunDir = normalize(mat3({model_view}) * sunPosition);",
                    f"vec3 sunDir = normalize(mat3({model_view}) * astro_pos);")
        replace_one(pack, water,
                    "            return clamp(\n"
                    "                (reflection - 0.165) *\n"
                    "                clamp(lmcoord.y, 0.0, 1.0) *\n"
                    "                (1.0 - rainStrength) * dayBF(10.0, 10.0, 5.0), 0.0, 100.0);",
                    """            // A separate moon setting controls night glints. With daytime
            // sun reflections disabled, moonlight must not revive them.
            float messyAstroStrength = worldTime > 13200
                ? float(MESSY_MOON_REFLECTION) * 0.5 : 1.0;
            #if SUN_REFLECTION == 0
                if (worldTime <= 13200) messyAstroStrength = 0.0;
            #endif
            return clamp(
                (reflection - 0.165) *
                clamp(lmcoord.y, 0.0, 1.0) *
                (1.0 - rainStrength) * dayBF(10.0, 10.0, 5.0), 0.0, 100.0)
                * messyAstroStrength;""")
        replace_one(pack, water,
                    "    #if SUN_REFLECTION > 0\n        #ifndef NETHER\n"
                    "            #ifndef THE_END\n"
                    "                return mix(color, reflection.rgb, fresnel * REFLEX_INDEX) +",
                    "    #if SUN_REFLECTION > 0 || MESSY_MOON_REFLECTION > 0\n"
                    "        #ifndef NETHER\n            #ifndef THE_END\n"
                    "                return mix(color, reflection.rgb, fresnel * REFLEX_INDEX) +")


def patch_cloud_occlusion(pack: dict[str, bytes]) -> None:
    """Depth-limit clouds against Voxy's opaque LOD surface.

    Vanilla depth deliberately excludes Voxy's LODs. A sky-only test using
    depthtex0 therefore isn't enough: behind-hill cloud samples overwrite
    the already-composited distant geometry. Clip each ray step to Voxy depth,
    keeping legitimate cloud samples *in front* of a distant mountain.
    """
    deferred = "shaders/common/deferred_fragment.glsl"
    replace_one(pack, deferred,
                "#ifdef VOXY\n    uniform sampler2D vxDepthTexTrans;\n#endif",
                "#ifdef VOXY\n    uniform sampler2D vxDepthTexTrans;\n"
                "    uniform sampler2D vxDepthTexOpaque;\n"
                "    uniform mat4 vxProjInv;\n#endif")
    replace_one(pack, deferred,
                "            #else\n                block_color.rgb = get_cloud(view_vector, block_color.rgb, bright, dither, cameraPosition, CLOUD_STEPS_AVG, umbral, cloud_color, dark_cloud_color, dynamicValue, cave_influence);\n            #endif",
                """            #else
                float messyCloudOcclusionDistance = 1.0e7;
                #ifdef VOXY
                    float messyTerrainDepth = texture2DLod(vxDepthTexOpaque,
                        texcoord * RENDER_SCALE, 0).r;
                    if (messyTerrainDepth < 0.999999) {
                        vec4 messyTerrainView = vxProjInv * vec4(
                            texcoord * 2.0 - 1.0, messyTerrainDepth * 2.0 - 1.0, 1.0);
                        messyCloudOcclusionDistance = length(
                            messyTerrainView.xyz / messyTerrainView.w);
                    }
                #endif
                // If the opaque surface is before the cloud layer, skip the
                // entire shader (including its pre-cloud brightness tweak).
                float messyCloudEntry = max(0.0,
                    (CLOUD_PLANE - cameraPosition.y) / max(view_vector.y, 0.0001));
                if (messyCloudOcclusionDistance > messyCloudEntry) {
                    block_color.rgb = get_cloud(view_vector, block_color.rgb, bright,
                        dither, cameraPosition, CLOUD_STEPS_AVG, umbral, cloud_color,
                        dark_cloud_color, dynamicValue, cave_influence,
                        messyCloudOcclusionDistance);
                }
            #endif""")

    clouds = "shaders/lib/volumetric_clouds.glsl"
    replace_one(pack, clouds,
                "float dynamicValue, float cave) {",
                "float dynamicValue, float cave, float maxCloudDistance) {")
    replace_one(pack, clouds,
                "    bool first_contact = true;",
                "    bool first_contact = true;\n    float messyCloudStart;\n"
                "    float messySampleDistance;")
    replace_one(pack, clouds, "    float density;", "    float density = 0.0;")
    replace_one(pack, clouds, "        float density_2;", "        float density_2 = 0.0;")
    replace_one(pack, clouds,
                "        plane_distance = (CLOUD_PLANE - base_pos.y) * view_y_inv;\n"
                "        intersection_pos = (view_vector * plane_distance) + base_pos;",
                "        plane_distance = (CLOUD_PLANE - base_pos.y) * view_y_inv;\n"
                "        messyCloudStart = plane_distance;\n"
                "        intersection_pos = (view_vector * plane_distance) + base_pos;")
    replace_one(pack, clouds,
                "        intersection_pos += (increment * dither);\n\n"
                "        for (int i = 0; i < samples + sample_fix; i++) {",
                "        intersection_pos += (increment * dither);\n"
                "        messySampleDistance = messyCloudStart + increment_dist * dither;\n\n"
                "        for (int i = 0; i < samples + sample_fix; i++) {\n"
                "            if (messySampleDistance >= maxCloudDistance) break;")
    replace_one(pack, clouds,
                "            intersection_pos += increment;\n        }",
                "            intersection_pos += increment;\n"
                "            messySampleDistance += increment_dist;\n        }")
    replace_one(pack, clouds,
                "            plane_distance = (CLOUD_PLANE_2 - base_pos.y) * view_y_inv;\n"
                "            intersection_pos_2 = (view_vector * plane_distance) + base_pos;",
                "            plane_distance = (CLOUD_PLANE_2 - base_pos.y) * view_y_inv;\n"
                "            messyCloudStart = plane_distance;\n"
                "            intersection_pos_2 = (view_vector * plane_distance) + base_pos;")
    replace_one(pack, clouds,
                "            intersection_pos_2 += (increment_2 * dither);\n\n"
                "            for (int i = 0; i < CIRRUS_STEPS_AVG; i++) {",
                "            intersection_pos_2 += (increment_2 * dither);\n"
                "            messySampleDistance = messyCloudStart + increment_dist_2 * dither;\n\n"
                "            for (int i = 0; i < CIRRUS_STEPS_AVG; i++) {\n"
                "                if (messySampleDistance >= maxCloudDistance) break;")
    replace_one(pack, clouds,
                "                intersection_pos_2 += increment_2;\n            }",
                "                intersection_pos_2 += increment_2;\n"
                "                messySampleDistance += increment_dist_2;\n            }")
    replace_one(pack, clouds,
                "                float t = altitude / (max(view_vector.y, 0.05) + 0.05);",
                "                float t = altitude / (max(view_vector.y, 0.05) + 0.05);\n"
                "                if (t >= maxCloudDistance) continue;")
    near = "shaders/common/water_blocks_fragment.glsl"
    replace_one(pack, near,
                "umbral, cloud_color, dark_cloud_color, 1.0, 1.0);",
                "umbral, cloud_color, dark_cloud_color, 1.0, 1.0, 1.0e7);")

    # Vanilla cloud meshes have a separate shader path (V_CLOUDS=0). They
    # need an equivalent depth comparison rather than raymarch clipping.
    vanilla = "shaders/common/clouds_blocks_fragment.glsl"
    replace_one(pack, vanilla,
                "uniform mat4 dhProjectionInverse;",
                "uniform mat4 dhProjectionInverse;\n"
                "#ifdef VOXY\n"
                "    uniform mat4 vxProjInv;\n"
                "    uniform sampler2D vxDepthTexOpaque;\n"
                "#endif")
    replace_one(pack, vanilla,
                "        #ifdef DISTANT_HORIZONS\n"
                "            vec2 screenCoord = gl_FragCoord.xy / vec2(viewWidth, viewHeight);",
                "        #if defined DISTANT_HORIZONS || defined VOXY\n"
                "            vec2 screenCoord = gl_FragCoord.xy / vec2(viewWidth, viewHeight);")
    replace_one(pack, vanilla,
                "            float distDH = mix(length(dhViewPos.xyz), 100000.0, step(1.0, depthDH));\n"
                "        #else\n            float distDH = 100000.0;",
                "            float distDH = mix(length(dhViewPos.xyz), 100000.0, step(1.0, depthDH));\n"
                "        #elif defined VOXY\n"
                "            float depthVoxy = texture2D(vxDepthTexOpaque, screenCoord).r;\n"
                "            vec4 vxClipPos = vec4(screenCoord * 2.0 - 1.0, depthVoxy * 2.0 - 1.0, 1.0);\n"
                "            vec4 vxViewPos = vxProjInv * vxClipPos;\n"
                "            vxViewPos /= vxViewPos.w;\n"
                "            float distDH = mix(length(vxViewPos.xyz), 100000.0, step(1.0, depthVoxy));\n"
                "        #else\n            float distDH = 100000.0;")


def patch(pack: dict[str, bytes]) -> None:
    from patch_clean_colorwheel import apply as apply_colorwheel
    from patch_entity_materials import apply as apply_entity_materials
    config = "shaders/lib/config.glsl"
    props = "shaders/shaders.properties"
    lang = "shaders/lang/en_US.lang"
    fragment = "shaders/common/solid_blocks_fragment.glsl"

    # Preserve the previous stable default: generated materials do not force
    # LabPBR on. Users may enable authored LabPBR via the original E-Lite menu.
    pack[config] += b"\n#define MESSY_AUTO_PBR // Atlas-material fallback; authored maps have priority\n//#define MESSY_PBR_ENTITIES // Opt-in procedural normals for entity models\n#define MESSY_AUTO_PBR_STRENGTH 1.0 // [0.0 0.5 0.75 1.0 1.25 1.5]\n#define MESSY_AUTO_PBR_RESOLUTION 512 // [128 256 512 1024]\n#define MESSY_AUTO_PBR_DISTANCE 56 // [16 24 32 40 48 56 72]\n#define MESSY_VOXY_FOG // Shader-owned distant LOD fog\n#define MESSY_VOXY_FOG_START 128 // [0 64 128 256 512 1024]\n#define MESSY_VOXY_FOG_SPAN 1024 // [256 512 768 1024 1536 2048 4096]\n#define MESSY_VOXY_FOG_STRENGTH 0.75 // [0.0 0.25 0.5 0.75 1.0]\n#define MESSY_WATER_PARITY // Match near and Voxy water absorption, depth and fog\n#define MESSY_WATER_LIGHT_HANDOFF // Blend vanilla water into the same distant lighting used by Voxy\n#define MESSY_WATER_FOG_START 160 // [0 64 128 160 256 384 512]\n#define MESSY_WATER_FOG_SPAN 768 // [256 512 768 1024 1536 2048]\n#define MESSY_WATER_FOG_STRENGTH 0.85 // [0.0 0.25 0.5 0.75 0.85 1.0]\n#define MESSY_WATER_DEBUG 0 // [0 1 2 3 4] 0: Off, 1: Opacity, 2: Surface, 3: Reflection, 4: Render handoff\n"

    pack[config] += (b"#define MESSY_HIDE_CUSTOM_SKY // Hide custom resource-pack sky layers\n"
                     b"#define MESSY_MOON_REFLECTION 1 // [0 1 2] Off, subtle, bright moonlight glint\n")
    pack[config] += (b"//#define MESSY_HIDE_VANILLA_CELESTIALS // Opt-in: suppress vanilla sun/moon discs but keep mod sky passes\n"
                     b"#define MESSY_VOXY_SHADOW_CONTRAST 1.5 // [0.0 0.5 1.0 1.25 1.5 2.0 3.0]\n")

    # Restore the last proven materials algorithm: four symmetric taps,
    # screen-footprint filtering and a distance fade. The previous release's
    # one-sided full-pixel derivative caused hard, layered atlas relief.
    old = "            bumpedNormal = getBumpedNormal(texcoord, flat_normal, normals);"
    new = """            bumpedNormal = getBumpedNormal(texcoord, flat_normal, normals);
            #ifdef MESSY_AUTO_PBR
                vec3 messyMapNormal = texture2D(normals, texcoord).rgb;
                bool messyNeutralNormal =
                    all(lessThan(abs(messyMapNormal.rg - vec2(128.0 / 255.0)), vec2(0.012))) &&
                    messyMapNormal.b > 0.97;
                vec2 messyFootprint = fwidth(final_uv * vec2(atlasSize));
                float messyPixelWidth = max(messyFootprint.x, messyFootprint.y);
                float messyDistance = length(sub_position3);
                if (messyNeutralNormal && foliageData.x < 0.3 &&
                    messyDistance < float(MESSY_AUTO_PBR_DISTANCE) &&
                    messyPixelWidth < 1.25 && MESSY_AUTO_PBR_STRENGTH > 0.0) {
                    vec2 messyTexel = 1.0 / max(vec2(atlasSize), vec2(16.0));
                    vec2 messyMin = atlas_uv.xy + messyTexel * 0.55;
                    vec2 messyMax = atlas_uv.xy + atlas_uv.zw - messyTexel * 0.55;
                    float messyStep = 16.0 / float(MESSY_AUTO_PBR_RESOLUTION);
                    vec2 messySampleStep = max(vec2(messyStep), messyFootprint);
                    vec2 messyOffset = messySampleStep * messyTexel;
                    vec2 messyR = clamp(final_uv + vec2(messyOffset.x, 0.0), messyMin, messyMax);
                    vec2 messyL = clamp(final_uv - vec2(messyOffset.x, 0.0), messyMin, messyMax);
                    vec2 messyD = clamp(final_uv + vec2(0.0, messyOffset.y), messyMin, messyMax);
                    vec2 messyU = clamp(final_uv - vec2(0.0, messyOffset.y), messyMin, messyMax);
                    float messyBase = length(pure_block_color.rgb);
                    vec4 messyDiff = vec4(
                        messyBase - length(texture2D(tex, messyR).rgb),
                        messyBase - length(texture2D(tex, messyL).rgb),
                        messyBase - length(texture2D(tex, messyD).rgb),
                        messyBase - length(texture2D(tex, messyU).rgb));
                    messyDiff = clamp(sign(messyDiff) * max(abs(messyDiff) - 0.05,
                        vec4(0.0)), vec4(-0.20), vec4(0.20));
                    vec2 messyEdge = vec2(messyDiff.x - messyDiff.y,
                                          messyDiff.z - messyDiff.w);
                    float messyFade = (1.0 - smoothstep(0.65, 1.25, messyPixelWidth)) *
                        (1.0 - smoothstep(float(MESSY_AUTO_PBR_DISTANCE) * 0.57,
                            float(MESSY_AUTO_PBR_DISTANCE), messyDistance));
                    vec2 messySlope = clamp(messyEdge * vec2(messyStep) /
                        messySampleStep * (5.0 * MESSY_AUTO_PBR_STRENGTH *
                        sqrt(float(MESSY_AUTO_PBR_RESOLUTION) / 128.0) * messyFade),
                        vec2(-1.1), vec2(1.1));
                    vec3 messyRelief = normalize(vec3(messySlope, 1.0));
                    bumpedNormal = normalize(tbn * messyRelief);
                }
            #endif"""
    replace_one(pack, fragment, old, new)
    # The pre-rollback material fallback worked without an external PBR pack.
    # Expose tangent/atlas geometry independently from LabPBR so this one
    # option does not change how all other E-Lite material IDs are decoded.
    vertex = "shaders/common/solid_blocks_vertex.glsl"
    for path in (vertex, fragment):
        body = pack[path].decode("utf-8")
        body = body.replace("|| defined LabPBR || defined SHADOW_CASTING",
                            "|| defined LabPBR || defined MESSY_AUTO_PBR || defined SHADOW_CASTING")
        body = body.replace("|| defined LabPBR\n", "|| defined LabPBR || defined MESSY_AUTO_PBR\n")
        if path == vertex:
            body = body.replace("#if defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)",
                                "#if (defined LabPBR || defined MESSY_AUTO_PBR) && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)")
        else:
            # First occurrence declares varyings; the later occurrences are
            # E-Lite's *actual* LabPBR sampler/decoder and must stay guarded.
            body = body.replace("#if defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)",
                                "#if (defined LabPBR || defined MESSY_AUTO_PBR) && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)", 1)
        pack[path] = body.encode("utf-8")
    # The same four-tap filtered relief works in native non-LabPBR mode.
    auto_body = new.split("            #ifdef MESSY_AUTO_PBR\n", 1)[1].rsplit("            #endif", 1)[0]
    auto_body = auto_body.replace("vec3 messyMapNormal = texture2D(normals, texcoord).rgb;",
                                  "vec3 messyMapNormal = vec3(128.0 / 255.0, 128.0 / 255.0, 1.0);")
    replace_one(pack, fragment,
                "    #else\n        #if MATERIAL_GLOSS < 1\n            vec3 bumpedNormal = vec3(1.0);",
                "    #elif defined MESSY_AUTO_PBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)\n"
                "        vec3 bumpedNormal = flat_normal;\n" + auto_body +
                "    #else\n        #if MATERIAL_GLOSS < 1\n            vec3 bumpedNormal = vec3(1.0);")
    replace_one(pack, fragment,
                "uniform sampler2D tex, specular, normals, gaux1, gaux3, gaux4, shadowcolor0, depthtex1;",
                "uniform sampler2D tex, specular, normals, gaux1, gaux3, gaux4, shadowcolor0, depthtex1;\n"
                "uniform ivec2 atlasSize;")
    replace_one(pack, fragment, "    vec3 spec_energy;", "    vec3 spec_energy = vec3(0.0);")
    replace_one(pack, fragment,
                "    #if !defined NETHER && defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)\n        float shadow_c_relief;",
                "    #if !defined NETHER && defined MESSY_AUTO_PBR && !defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)\n"
                "        float shadow_c_relief = directLight2;\n"
                "        if (foliageData.x < 0.3 && isGrass < 0.5) {\n"
                "            vec3 messySun = normalize(light_mix >= 0.5 ? sunPosition : -sunPosition);\n"
                "            float messyFace = max(dot(normalize(flat_normal), messySun), 0.0);\n"
                "            float messyPixel = max(dot(normalize(bumpedNormal), messySun), 0.0);\n"
                "            float messyReliefRatio = clamp((messyPixel + 0.20) / (messyFace + 0.20), 0.70, 1.30);\n"
                "            shadow_c_relief *= mix(1.0, messyReliefRatio, smoothstep(0.58, 0.78, light_mix) * 0.8);\n"
                "        }\n"
                "    #elif !defined NETHER && defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)\n        float shadow_c_relief;")
    # The zero-gloss E-Lite path bypasses shadow_c_relief entirely. It made
    # generated normals visually disappear on low/very-low profiles.
    replace_one(pack, fragment,
                "        vec3 real_light = computeRealLight(omni_light, direct_light_color, directLight2, shadow_c, vec3(0.0), candle_color);",
                "        #if defined MESSY_AUTO_PBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)\n"
                "            vec3 real_light = computeRealLight(omni_light, direct_light_color, shadow_c_relief, shadow_c, vec3(0.0), candle_color);\n"
                "        #else\n"
                "            vec3 real_light = computeRealLight(omni_light, direct_light_color, directLight2, shadow_c, vec3(0.0), candle_color);\n"
                "        #endif")
    # Sky fill is substantial in E-Lite. A small bounded relief correction
    # makes the normals visible in shade without changing emissive blocklight.
    replace_one(pack, fragment,
                "    // === Block reflection",
                "    vec3 messyOmniLight = omni_light;\n"
                "    #if defined MESSY_AUTO_PBR && !defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)\n"
                "        if (foliageData.x < 0.3 && isGrass < 0.5 && light_mix > 0.58) {\n"
                "            vec3 messySkyUp = normalize((gbufferModelView * vec4(0.0, 1.0, 0.0, 0.0)).xyz);\n"
                "            float messySkyDiff = dot(normalize(bumpedNormal), messySkyUp) -\n"
                "                dot(normalize(flat_normal), messySkyUp);\n"
                "            messyOmniLight *= clamp(1.0 + messySkyDiff * 0.65 *\n"
                "                smoothstep(0.58, 0.78, light_mix), 0.65, 1.35);\n"
                "        }\n"
                "    #endif\n\n"
                "    // === Block reflection")
    # Fragment varyings are read-only in GLSL. Feed the corrected local copy
    # to all three E-Lite illumination branches instead of assigning to it.
    body = pack[fragment].decode("utf-8")
    if body.count("computeRealLight(omni_light,") != 3:
        raise ValueError("Unexpected native E-Lite illumination branches")
    pack[fragment] = body.replace("computeRealLight(omni_light,",
                                  "computeRealLight(messyOmniLight,").encode("utf-8")

    # Preserve original E-Lite water color, Fresnel and surface reflections.
    # Earlier iterations darkened the input by 0.65 and changed Fresnel; those
    # controls were responsible for loss of parity with ordinary E-Lite water.
    # Only depth, refraction absorption and fog should differ from stock.
    water = "shaders/common/water_voxy_blocks_fragment.glsl"
    near_water = "shaders/common/water_blocks_fragment.glsl"

    # Near E-Lite squares the refraction thickness, while Voxy uses a linear
    # thickness. Both should use the same extinction law across the handoff.
    near_lib = "shaders/lib/water.glsl"
    replace_one(pack, near_lib,
                "        water_absortion *= water_absortion;",
                "        #ifndef MESSY_WATER_PARITY\n"
                "            water_absortion *= water_absortion;\n"
                "        #endif")

    # Complementary uses vxDepthTexOpaque for water thickness, not the
    # translucent depth attachment. E-Lite's old near and Voxy paths treated
    # vxDepthTexTrans as the ocean floor and reconstructed it with hardcoded
    # near/far clipping planes. This makes Voxy water much less transparent
    # than the nearby water over the same underwater terrain and seagrass.
    # Use the actual inverse projection and the opaque depth on both sides.
    replace_one(pack, near_water,
                "    uniform sampler2D vxDepthTexTrans;",
                "    uniform sampler2D vxDepthTexTrans;\n"
                "    uniform sampler2D vxDepthTexOpaque;\n"
                "    uniform mat4 vxProjInv;")
    replace_one(pack, near_lib,
                "        float water_distance =\n"
                "        2.0 * near * far / (far + near - (2.0 * gl_FragCoord.z - 1.0) * (far - near));",
                """        #if defined MESSY_WATER_PARITY && defined VOXY
            float water_distance = length(fragpos);
            float earth_distance = min(
                messyWaterOpaqueDistance(pos.xy, depthtex1, gbufferProjectionInverse),
                messyWaterOpaqueDistance(pos.xy, vxDepthTexOpaque, vxProjInv));
        #else
            float water_distance =
            2.0 * near * far / (far + near - (2.0 * gl_FragCoord.z - 1.0) * (far - near));""")
    replace_one(pack, near_lib,
                "        water_absortion = earth_distance - water_distance;",
                """        #endif
        water_absortion = max(earth_distance - water_distance, 0.0);""")
    # The legacy #elif VOXY branch is guarded by the outer #else above, so
    # it remains available when the unified water option is disabled.
    far_lib = "shaders/lib/water_voxy.glsl"
    # Both renderers previously defined "transparent" differently: regular
    # water precomposited sampled gaux1 into an opaque pixel, whereas Voxy
    # water framebuffer-blended partially transparent pixels. Share the same
    # extinction law and source-over compositor on both geometry paths.
    shared_water = "shaders/lib/messy_water_composite.glsl"
    pack[shared_water] = b"""#ifndef MESSY_WATER_COMPOSITE_GLSL
#define MESSY_WATER_COMPOSITE_GLSL

float messyWaterOpacity(float thickness) {
    return clamp(1.0 - 1.0 / (max(thickness, 0.0) * WATER_ABSORPTION + 1.33),
        0.0, 1.0);
}

// Same projection/depth-to-world-distance code for vanilla and Voxy floors.
// The all-sky sentinel must not be projected; Voxy's distant reversed-Z
// geometry and vanilla's near geometry can each be absent in a pixel.
float messyWaterOpaqueDistance(vec2 uv, sampler2D depthMap, mat4 projectionInv) {
    float depth = texture2D(depthMap, uv).r;
    if (depth >= 0.999999) return 1.0e7;
    vec4 view = projectionInv * vec4(uv * 2.0 - 1.0,
        depth * 2.0 - 1.0, 1.0);
    return length(view.xyz / view.w);
}

float messyWaterDistanceFog(float cameraDistance) {
    return smoothstep(float(MESSY_WATER_FOG_START),
        float(MESSY_WATER_FOG_START + MESSY_WATER_FOG_SPAN),
        cameraDistance) * MESSY_WATER_FOG_STRENGTH;
}

// Vanilla water calculates illumination in light_vertex.glsl; Voxy does it
// later from its LOD voxel light map with different sky/daylight constants.
// The diagnostic isolated this as the last visible chunk-shaped difference.
// This distant-ocean light is camera-independent: both renderers get exactly
// the same value at the handoff, with ordinary near-water light left intact.
vec3 messyWaterDistantLight(int ticks, float rain) {
    float moment = fract(float(ticks) * (1.0 / 24000.0));
    float dayMix = clamp(1.25 - 20.0 * (moment - 0.25) * (moment - 0.25), 0.0, 1.0);
    float nightMix = clamp(3.125 - 50.0 * (moment - 0.75) * (moment - 0.75), 0.0, 1.0);
    float nightTransition = smoothstep(0.45, 0.52, moment);
    vec3 direct = mix(
        mix(LIGHT_SUNSET_COLOR, LIGHT_DAY_COLOR, dayMix),
        mix(LIGHT_SUNSET_COLOR, LIGHT_NIGHT_COLOR, nightMix), nightTransition);
    vec3 zenith = mix(
        mix(ZENITH_SUNSET_COLOR, ZENITH_DAY_COLOR, dayMix),
        mix(ZENITH_SUNSET_COLOR, ZENITH_NIGHT_COLOR, nightMix), nightTransition);
    zenith = mix(zenith, ZENITH_SKY_RAIN_COLOR * luma(zenith), rain);
    direct = mix(direct, ZENITH_SKY_RAIN_COLOR * luma(direct) * 0.6, rain);
    float directStrength = max(dayMix, nightMix);
    #if COLOR_SCHEME == 2 || COLOR_SCHEME == 6
        vec3 omni = mix(zenith * vec3(0.666, 1.0, 1.0) *
            mix(3.5, 4.5, dayMix) * OMNI_MUL,
            direct * mix(2.0, 0.35, dayMix) * OMNI_MUL, OMNI_TINT);
    #elif COLOR_SCHEME == 4
        vec3 omni = direct * (OMNI_MUL + 0.7);
    #else
        vec3 omni = mix(zenith, direct * 0.45, OMNI_TINT) * (OMNI_MUL + 0.7);
    #endif
    return max(omni, vec3(AVOID_DARK_LEVEL * 0.01)) *
        (1.0 + directStrength * 0.05) +
        direct * directStrength * (1.0 - rain * 0.75);
}

// Use one water normal field for both renderers. Voxy and vanilla previously
// differed in their rain attenuation and sky-visibility terms.
vec3 messyWaterWaves(vec3 pos, float visibleSky, float rain,
                     float time, sampler2D noiseMap) {
    float speed = time * 0.04;
    vec2 base = pos.xy - pos.z * 0.2;
    vec2 wave1 = (texture2D(noiseMap,
        base * 0.1 + vec2(speed)).rg - 0.5) * 0.66;
    vec2 wave2 = texture2D(noiseMap,
        base * 0.03125 - speed).rg - 0.5;
    vec2 wave3 = (texture2D(noiseMap,
        base * 0.125 + vec2(speed, -speed)).rg - 0.5) * 1.2;
    return normalize(vec3(wave1 + wave2 + wave3,
        WATER_TURBULENCE * (1.0 - rain * 0.333 * visibleSky)));
}

// E-Lite's unmodified water_shader() linearly combines an absorption-weighted
// surface, a Fresnel reflection and sunlight. Move those contributions into
// an alpha source, leaving the actual background to the framebuffer blend.
vec4 messyWaterCompose(vec3 shaded, vec3 surface, float opacity, float fresnel) {
    float reflection = clamp(fresnel * REFLEX_INDEX, 0.0, 1.0);
    float absorption = clamp(opacity, 0.0, 1.0);
    float alpha = absorption + (1.0 - absorption) * reflection;
    vec3 premultiplied = shaded - (1.0 - reflection) *
        (1.0 - absorption) * surface;
    return vec4(premultiplied / max(alpha, 0.001), alpha);
}

#endif
"""
    replace_one(pack, near_water,
                '#include "/lib/water.glsl"',
                '#include "/lib/messy_water_composite.glsl"\n#include "/lib/water.glsl"')
    replace_one(pack, water,
                '#include "/lib/water_voxy.glsl"',
                '#include "/lib/messy_water_composite.glsl"\n#include "/lib/water_voxy.glsl"')
    replace_one(pack, near_lib,
                "vec3 refraction(vec3 fragpos, vec3 color, vec3 refraction) {",
                "vec3 refraction(vec3 fragpos, vec3 color, vec3 refraction, out float waterAlpha) {")
    replace_one(pack, near_lib,
                "        water_absortion = (1.0 / -((water_absortion * WATER_ABSORPTION) + 1.33)) + 1.0;",
                "        water_absortion = messyWaterOpacity(water_absortion);")
    replace_one(pack, near_water,
                "            block_color = vec4(refraction(fragposition, block_color.rgb, water_normal_base), 1.0);",
                "            float messyWaterAbsorption;\n"
                "            block_color = vec4(refraction(fragposition, block_color.rgb, "
                "water_normal_base, messyWaterAbsorption), 1.0);")
    replace_one(pack, near_water,
                "            block_color.rgb = water_shader(fragposition, surface_normal * normalfactor, block_color.rgb, sky_color_reflect, fresnel, visible_sky, dither, dirLight.rgb);",
                "            #if defined MESSY_WATER_PARITY && defined VOXY\n"
                "                vec3 messyWaterSurface = block_color.rgb;\n"
                "            #endif\n"
                "            block_color.rgb = water_shader(fragposition, surface_normal * normalfactor, block_color.rgb, sky_color_reflect, fresnel, visible_sky, dither, dirLight.rgb);\n"
                "            #if defined MESSY_WATER_PARITY && defined VOXY\n"
                "                block_color = messyWaterCompose(block_color.rgb, "
                "messyWaterSurface, messyWaterAbsorption, fresnel);\n"
                "            #endif")
    replace_one(pack, far_lib,
                "    const float vxNear = 16.0;\n    const float vxFar  = 48000.0;",
                """    #ifndef MESSY_WATER_PARITY
        const float vxNear = 16.0;
        const float vxFar  = 48000.0;
    #endif""")
    replace_one(pack, far_lib,
                "        float water_distance = 2.0 * vxNear * vxFar / (vxFar + vxNear - (2.0 * gl_FragCoord.z - 1.0) * (vxFar - vxNear));",
                """        #ifdef MESSY_WATER_PARITY
            float water_distance = length(fragpos);
            float earth_distance = messyWaterOpaqueDistance(
                pos.xy, vxDepthTexOpaque, vxProjInv);
        #else
            float water_distance = 2.0 * vxNear * vxFar / (vxFar + vxNear - (2.0 * gl_FragCoord.z - 1.0) * (vxFar - vxNear));""")
    replace_one(pack, far_lib,
                "        water_absortion = max(earth_distance - water_distance, 0.0);",
                """        #endif
        water_absortion = max(earth_distance - water_distance, 0.0);""")
    replace_one(pack, far_lib,
                "        water_absortion = (1.0 / -((water_absortion * WATER_ABSORPTION) + 1.33)) + 1.0;",
                "        water_absortion = messyWaterOpacity(water_absortion);")
    # Even with identical optical depth, E-Lite subtly changes the normal
    # basis and wave amplitude at the Voxy handoff. Match the near-water math
    # to prevent a narrow reflection/surface-texture discontinuity.
    replace_one(pack, far_lib,
                "WATER_TURBULENCE - (rainStrength * 0.6 * WATER_TURBULENCE)",
                "WATER_TURBULENCE - (rainStrength * 0.333 * WATER_TURBULENCE)")
    for path, func, visibility in (
        (near_lib, "normal_waves", "visible_sky"),
        (far_lib, "normal_waves_voxy", "messyVisibleSky"),
    ):
        replace_one(pack, path,
                    f"vec3 {func}(vec3 pos) {{",
                    f"vec3 {func}(vec3 pos"
                    + (", float messyVisibleSky" if path == far_lib else "") + ") {\n"
                    "    #ifdef MESSY_WATER_PARITY\n"
                    f"        return messyWaterWaves(pos, {visibility}, rainStrength,\n"
                    "            frameTimeCounter, noisetex);\n"
                    "    #else")
        replace_one(pack, path,
                    "    return normalize(final_wave);\n}",
                    "    return normalize(final_wave);\n    #endif\n}")
    replace_one(pack, water,
                "normal_waves_voxy(worldposition.xzy)",
                "normal_waves_voxy(worldposition.xzy, visibleSky)")
    # In the diagnostic's surface-only mode, sky reflection and opacity were
    # continuous but the raw lit WATER_COLOR had a square Voxy boundary.
    # Near uses vertex-lit E-Lite water; Voxy uses independently reconstructed
    # voxel lights and different colour coefficients. Preserve vanilla lighting
    # near the camera, then fade to an identical camera-independent ocean light
    # well before the chunk handoff. Voxy always uses that exact same light.
    replace_one(pack, near_water,
                "            #if WATER_COLOR_SOURCE == 0\n"
                "                block_color.rgb = water_texture * real_light * WATER_COLOR;",
                """            #if defined MESSY_WATER_PARITY && defined VOXY && defined MESSY_WATER_LIGHT_HANDOFF
                float messyLightingDistance = length(fragposition);
                if (messyLightingDistance > far * 0.5) {
                    float messyHandoff = smoothstep(far * 0.5, far * 0.9,
                        messyLightingDistance);
                    real_light = mix(real_light,
                        messyWaterDistantLight(worldTime, rainStrength), messyHandoff);
                }
            #endif
            #if WATER_COLOR_SOURCE == 0
                block_color.rgb = water_texture * real_light * WATER_COLOR;""")
    replace_one(pack, water,
                "            #if WATER_COLOR_SOURCE == 0\n"
                "                blockColor.rgb = waterTexture * realLight * WATER_COLOR;",
                """            #if defined MESSY_WATER_PARITY && defined MESSY_WATER_LIGHT_HANDOFF
                realLight = messyWaterDistantLight(worldTime, rainStrength);
            #endif
            #if WATER_COLOR_SOURCE == 0
                blockColor.rgb = waterTexture * realLight * WATER_COLOR;""")

    # E-Lite's Voxy finalcolor originally hardcodes a bright daytime fog
    # multiplier, even at midnight, while vanilla water smoothly changes from
    # sunset to much darker night fog. At the 0.85-strength distance fog this
    # produces a very visible dark near-water rectangle at night despite
    # equalized water surface lighting and opacity. Match the fog *colour* law
    # on the water path only; leave terrain and the user's day-water parity.
    far_finalcolor = "shaders/src/finalcolor_voxy.glsl"
    replace_one(pack, far_finalcolor,
                "        #if FOG_TINT == 0\n"
                "            vec3 fogColorMod = mix(saturate(vec3(0.592, 0.888, 1.233), 0.5), vec3(1.0), frogAdjust);\n"
                "        #elif FOG_TINT == 1\n"
                "            vec3 fogColorMod = mix(saturate(vec3(0.592, 0.888, 1.233), 1.0), vec3(1.0), frogAdjust);\n"
                "        #elif FOG_TINT == 2\n"
                "            vec3 fogColorMod = mix(saturate(vec3(0.592, 0.888, 1.233), -0.5), vec3(1.0), frogAdjust);\n"
                "        #endif",
                """        vec3 messyFogBase = vec3(0.592, 0.888, 1.233);
        #ifdef MESSY_WATER_PARITY
            if (customId == ENTITY_WATER) {
                // Same sunset/day/night fog palette as finalcolor.glsl.
                // Keep Voxy's own day interpolation only for its sky state.
                float messyFogSunsetSaturation = dayBlendFloatVoxyN(
                    dayBlendFloatVoxyN(1.0, 1.0, 5.0, dayMixerV, nightMixerV, dayMomentV),
                    1.0,
                    dayBlendFloatVoxyN(5.0, 1.0, 1.0, dayMixerV, nightMixerV, dayMomentV),
                    dayMixerV, nightMixerV, dayMomentV);
                messyFogBase = dayBlendVoxy(
                    saturate(vec3(0.2392, 0.4039, 0.5922), messyFogSunsetSaturation),
                    vec3(0.3, 0.45, 0.615),
                    vec3(0.1647, 0.3725, 0.6157),
                    dayMixerV, nightMixerV, dayMomentV);
            }
        #endif
        #if FOG_TINT == 0
            vec3 fogColorMod = mix(saturate(messyFogBase, 0.5), vec3(1.0), frogAdjust);
        #elif FOG_TINT == 1
            vec3 fogColorMod = mix(saturate(messyFogBase, 1.0), vec3(1.0), frogAdjust);
        #elif FOG_TINT == 2
            vec3 fogColorMod = mix(saturate(messyFogBase, -0.5), vec3(1.0), frogAdjust);
        #endif""")
    replace_one(pack, far_lib,
                "    bump *= vec3(NdotE) + vec3(0.0, 0.0, 1.0 - NdotE);",
                "    bump *= vec3(NdotE) + vec3(0.05, 0.1, 1.0 - NdotE);")
    # Complementary's Medium Voxy path outputs surface RGB with an actual
    # translucent alpha and enables blend mode 0 in voxy.json. E-Lite instead
    # precomposed far-water refraction into an opaque RGB (alpha=1), causing
    # a hard discontinuity where near water meets the Voxy translucent FBO.
    # Under parity mode return the uncomposited water surface and expose the
    # very same absorption factor as alpha. The distant fragment will then
    # preserve the stock sky/sun reflections using an exact blend identity.
    replace_one(pack, far_lib,
                "vec3 refraction_voxy(vec3 fragpos, vec3 color, vec3 refraction) {",
                "vec3 refraction_voxy(vec3 fragpos, vec3 color, vec3 refraction, out float waterAlpha) {")
    replace_one(pack, far_lib,
                "    return mix(texture(gaux1, pos.xy).rgb * mix(vec3(0.9, 1.0, 1.0), vec3(0.8, 1.3, 1.6) * 0.9, water_absortion), color, water_absortion);",
                """    waterAlpha = clamp(water_absortion, 0.0, 1.0);
    #ifdef MESSY_WATER_PARITY
        return color;
    #else
        return mix(texture(gaux1, pos.xy).rgb * mix(vec3(0.9, 1.0, 1.0),
            vec3(0.8, 1.3, 1.6) * 0.9, water_absortion), color, water_absortion);
    #endif""")
    replace_one(pack, water,
                "            blockColor = vec4(refraction_voxy(fragposition, blockColor.rgb, waterNormalBase), 1.0);",
                "            float messyWaterAbsorption;\n"
                "            blockColor = vec4(refraction_voxy(fragposition, blockColor.rgb, "
                "waterNormalBase, messyWaterAbsorption), 1.0);")
    replace_one(pack, water,
                "            blockColor.rgb = water_shader_voxy(fragposition, surfaceNormal * normalfactor, blockColor.rgb, skyColorReflect, fresnel, visibleSky, directLightColor, lmcoord);",
                """            #ifdef MESSY_WATER_PARITY
                vec3 messyWaterSurface = blockColor.rgb;
            #endif
            blockColor.rgb = water_shader_voxy(fragposition, surfaceNormal * normalfactor, blockColor.rgb, skyColorReflect, fresnel, visibleSky, directLightColor, lmcoord);
            #ifdef MESSY_WATER_PARITY
                blockColor = messyWaterCompose(blockColor.rgb, messyWaterSurface,
                    messyWaterAbsorption, fresnel);
            #endif""")

    # A deliberate debug override after postprocessing is much more useful
    # than guessing at a colour correction. Modes 1-3 compare the same stage
    # on both renderers; mode 4 identifies near/far coverage and overlap.
    for path, color, surface, sky, water_check, color_name in (
        (near_water, "vec3(1.0, 0.0, 0.0)",
         "messyWaterSurface", "sky_color_reflect",
         "block_type > 2.9 && block_type < 3.1", "block_color"),
        (water, "vec3(0.0, 1.0, 0.0)",
         "messyWaterSurface", "skyColorReflect",
         "customId == ENTITY_WATER", "blockColor"),
    ):
        if path == near_water:
            replace_one(pack, path, "    vec3 real_light;",
                        "    vec3 real_light;\n"
                        "    vec4 messyWaterDebugValue = vec4(0.0);")
            blend = ("                block_color = messyWaterCompose(block_color.rgb, "
                     "messyWaterSurface, messyWaterAbsorption, fresnel);")
        else:
            replace_one(pack, path, "    vec3 realLight;",
                        "    vec3 realLight;\n"
                        "    vec4 messyWaterDebugValue = vec4(0.0);")
            blend = ("                blockColor = messyWaterCompose(blockColor.rgb, messyWaterSurface,\n"
                     "                    messyWaterAbsorption, fresnel);")
        replace_one(pack, path, blend,
                    blend + "\n"
                    "                #if MESSY_WATER_DEBUG == 1\n"
                    "                    messyWaterDebugValue = vec4(vec3(messyWaterAbsorption), 1.0);\n"
                    "                #elif MESSY_WATER_DEBUG == 2\n"
                    f"                    messyWaterDebugValue = vec4({surface}, 1.0);\n"
                    "                #elif MESSY_WATER_DEBUG == 3\n"
                    f"                    messyWaterDebugValue = vec4({sky}, 1.0);\n"
                    "                #elif MESSY_WATER_DEBUG == 4\n"
                    f"                    messyWaterDebugValue = vec4({color}, 0.5);\n"
                    "                #endif")
        if path == near_water:
            replace_one(pack, path, '    #include "/src/writebuffers.glsl"',
                        "    #if defined MESSY_WATER_PARITY && defined VOXY && MESSY_WATER_DEBUG > 0\n"
                        f"        if ({water_check}) {color_name} = messyWaterDebugValue;\n"
                        "    #endif\n"
                        '    #include "/src/writebuffers.glsl"')
        else:
            replace_one(pack, path, "    gbufferData0 = blockColor;",
                        "    #if defined MESSY_WATER_PARITY && MESSY_WATER_DEBUG > 0\n"
                        f"        if ({water_check}) {color_name} = messyWaterDebugValue;\n"
                        "    #endif\n    gbufferData0 = blockColor;")
    replace_one(pack, near_lib,
                "    return mix(texture2D(gaux1, pos.xy).rgb * mix(vec3(0.95, 1.0, 1.0), vec3(0.8, 1.1, 1.4) * 0.9, water_absortion), color, water_absortion);",
                """    #ifdef MESSY_WATER_PARITY
        return mix(texture2D(gaux1, pos.xy).rgb * mix(vec3(0.9, 1.0, 1.0),
            vec3(0.8, 1.3, 1.6) * 0.9, water_absortion), color, water_absortion);
    #else
        return mix(texture2D(gaux1, pos.xy).rgb * mix(vec3(0.95, 1.0, 1.0),
            vec3(0.8, 1.1, 1.4) * 0.9, water_absortion), color, water_absortion);
    #endif""")
    replace_one(pack, near_lib,
                "    #ifdef MESSY_WATER_PARITY\n        return mix(texture2D(gaux1, pos.xy).rgb * mix(vec3(0.9, 1.0, 1.0),",
                "    waterAlpha = clamp(water_absortion, 0.0, 1.0);\n"
                "    #if defined MESSY_WATER_PARITY && defined VOXY\n"
                "        return color;\n"
                "    #elif defined MESSY_WATER_PARITY\n"
                "        return mix(texture2D(gaux1, pos.xy).rgb * mix(vec3(0.9, 1.0, 1.0),")
    voxy_json = "shaders/common/voxy.json"
    replace_one(pack, voxy_json,
                '    "vxDepthTexTrans": "sampler2D"',
                '    "vxDepthTexTrans": "sampler2D",\n'
                '    "vxDepthTexOpaque": "sampler2D"')
    # The Voxy JSON blending key refers to the output attachment location,
    # not the colortex target ID (E-Lite outputs to location 0, colortex1).
    # Match Complementary Medium's straight-alpha translucent blend mode.
    replace_one(pack, voxy_json,
                '  "opaqueDrawBuffers": [1, 4],',
                '  "excludeLodsFromVanillaDepth": true,\n'
                '  "blending": {\n'
                '    -1: "off",\n'
                '    0: "SRC_ALPHA ONE_MINUS_SRC_ALPHA ONE ONE_MINUS_SRC_ALPHA"\n'
                '  },\n'
                '  "opaqueDrawBuffers": [1, 4],')
    # Complementary enables this same blend rule for both regular
    # gbuffers_water and Voxy translucency. Do not turn it off for vanilla
    # water: the shader also handles glass and ice in this pass.
    replace_one(pack, props,
                'blend.dh_water=SRC_ALPHA ONE_MINUS_SRC_ALPHA ONE ONE_MINUS_SRC_ALPHA',
                'blend.gbuffers_water=SRC_ALPHA ONE_MINUS_SRC_ALPHA ONE ONE_MINUS_SRC_ALPHA\n'
                'blend.dh_water=SRC_ALPHA ONE_MINUS_SRC_ALPHA ONE ONE_MINUS_SRC_ALPHA')

    # E-Lite's caustics.glsl uses visible_sky from shadow_fragment.glsl, but
    # the stock shadow vertex program never writes that varying. Keep the
    # fragment input and supply the missing value from the actual shadow
    # vertex program, including shadow_terrain_cutout and related variants.
    shadow_vertex = "shaders/common/shadow_vertex.glsl"
    replace_one(pack, shadow_vertex,
                "varying float is_water;",
                "varying float is_water;\nvarying float visible_sky;")
    replace_one(pack, shadow_vertex,
                "    texcoord = (gl_TextureMatrix[0] * gl_MultiTexCoord0).xy;",
                "    texcoord = (gl_TextureMatrix[0] * gl_MultiTexCoord0).xy;\n"
                "    visible_sky = clamp(gl_MultiTexCoord1.y / 240.0, 0.0, 1.0);")

    unified_near = ""
    unified_far = ""
    # Keep the camera-distance fog law identical in both water paths. Fog
    # can contribute colour drift but the user's test with it disabled shows
    # it is not the root cause of the geometric water seam.
    unified_near += """    #if defined FOG_ACTIVE && defined MESSY_WATER_PARITY
        float messyWaterFog = mix(fog_adj,
            messyWaterDistanceFog(gl_FogFragCoord), is_water);
        #define fog_adj messyWaterFog
    #endif
    #include "/src/finalcolor.glsl"
    #if defined FOG_ACTIVE && defined MESSY_WATER_PARITY
        #undef fog_adj
    #endif"""
    unified_far += """    #ifdef MESSY_WATER_PARITY
        // Override E-Lite's built-in Voxy horizon fog for water only.
        // The original fog was a function of LOD render distance, not
        // camera distance. It can exaggerate (but does not cause) the seam.
        float messyWaterFog = messyWaterDistanceFog(fogFragCoord);
        if (customId == ENTITY_WATER) frogAdjust = messyWaterFog;
    #endif
    #include "/src/finalcolor_voxy.glsl"
"""
    replace_one(pack, near_water, '    #include "/src/finalcolor.glsl"', unified_near)
    replace_one(pack, water, '    #include "/src/finalcolor_voxy.glsl"', unified_far)

    # Fog is computed in the Voxy fragment shaders, where distant LOD depth
    # is available. No changes to vanilla fog or Minecraft/Voxy mixins.
    for path in ("shaders/common/solid_voxy_blocks_fragment.glsl", water):
        source = pack[path].decode("utf-8")
        anchor = "    #include \"/src/current_sky_color_voxy.glsl\"" if path == water else "    #if !defined NETHER\n        #ifdef SHADOW_CASTING"
        if source.count(anchor) != 1:
            raise ValueError(f"Voxy fog anchor missing or ambiguous: {path}")
        addition = """    #ifdef MESSY_VOXY_FOG
        // Start past the near-chunk boundary and blend into the existing
        // atmosphere, including water, without relying on vanilla fog.
        float messyFogStart = float(vxRenderDistance * 16) + float(MESSY_VOXY_FOG_START);
        float messyFogT = smoothstep(messyFogStart,
            messyFogStart + float(MESSY_VOXY_FOG_SPAN), fogFragCoord);
        frogAdjust = max(frogAdjust, messyFogT * MESSY_VOXY_FOG_STRENGTH);
    #endif

"""
        pack[path] = source.replace(anchor, addition + anchor, 1).encode("utf-8")

    # Voxy LODs do not receive E-Lite's nearby shadow map. Darken existing
    # voxel skylight occlusion rather than tracing expensive long-range rays
    # or touching the Voxy renderer. Exposed surfaces and emissive voxels
    # retain their original lighting.
    far_solid = "shaders/common/solid_voxy_blocks_fragment.glsl"
    replace_one(pack, far_solid,
                "    float block_luma = luma(blockColor.rgb);",
                """    #if !defined NETHER && !defined THE_END
        if (MESSY_VOXY_SHADOW_CONTRAST > 0.0 &&
            customId != ENTITY_EMMISIVE && customId != ENTITY_S_EMMISIVE) {
            float messyOccludedSky = clamp(1.0 - visibleSky, 0.0, 1.0);
            float messyVoxyShadow = clamp(messyOccludedSky *
                MESSY_VOXY_SHADOW_CONTRAST, 0.0, 1.0);
            omniLight *= mix(1.0, 0.52, messyVoxyShadow);
            directLightStrength *= mix(1.0, 0.70, messyVoxyShadow);
        }
    #endif

    float block_luma = luma(blockColor.rgb);""")

    replace_one(pack, props,
                "screen.RENDER_SCREEN= AA_TYPE FXAA FOG_ACTIVE FOG_ADJUST NEAR_FOG FOG_TINT NETHER_FOG_DISTANCE FOLIAGE_V <empty> <empty> PERF_IMPACT",
                "screen.RENDER_SCREEN= AA_TYPE FXAA FOG_ACTIVE FOG_ADJUST NEAR_FOG FOG_TINT NETHER_FOG_DISTANCE FOLIAGE_V [MESSY_VOXY_SCREEN] <empty> PERF_IMPACT\n"
                "screen.MESSY_VOXY_SCREEN= MESSY_VOXY_FOG MESSY_VOXY_FOG_START MESSY_VOXY_FOG_SPAN MESSY_VOXY_FOG_STRENGTH MESSY_VOXY_SHADOW_CONTRAST [MESSY_WATER_SCREEN]")
    replace_one(pack, props,
                "screen.LabPBR= LabPBR POM POM_SHADOW LabEMISSIVE POM_DEPTH POM_STEPS SS_SAMPLES",
                "screen.LabPBR= LabPBR POM POM_SHADOW LabEMISSIVE MESSY_PBR_ENTITIES POM_DEPTH POM_STEPS SS_SAMPLES")
    replace_one(pack, props, "[LabPBR] [INFO_SCREEN]",
                "[LabPBR] [MESSY_FEATURES] [INFO_SCREEN]")
    pack[props] += b"\nscreen.MESSY_FEATURES.columns=2\nscreen.MESSY_FEATURES= [MESSY_MATERIALS_SCREEN] [MESSY_VOXY_SCREEN] [MESSY_WATER_SCREEN] PERF_IMPACT\nscreen.MESSY_MATERIALS_SCREEN= MESSY_AUTO_PBR MESSY_PBR_ENTITIES MESSY_AUTO_PBR_STRENGTH MESSY_AUTO_PBR_RESOLUTION MESSY_AUTO_PBR_DISTANCE\nscreen.MESSY_WATER_SCREEN= MESSY_WATER_LIGHT_HANDOFF MESSY_WATER_DEBUG MESSY_WATER_FOG_START MESSY_WATER_FOG_SPAN MESSY_WATER_FOG_STRENGTH\n"
    replace_one(pack, props, "sliders = ",
                "sliders = MESSY_AUTO_PBR_STRENGTH MESSY_AUTO_PBR_RESOLUTION "
                "MESSY_AUTO_PBR_DISTANCE MESSY_VOXY_FOG_START "
                "MESSY_VOXY_FOG_SPAN MESSY_VOXY_FOG_STRENGTH MESSY_VOXY_SHADOW_CONTRAST MESSY_WATER_FOG_START MESSY_WATER_FOG_SPAN MESSY_WATER_FOG_STRENGTH ")
    pack[lang] += b"\nscreen.MESSY_FEATURES=MessyShaders Settings\nscreen.MESSY_MATERIALS_SCREEN=Automatic Materials\nscreen.MESSY_VOXY_SCREEN=Voxy Distance Lighting and Fog\nscreen.MESSY_WATER_SCREEN=Voxy Water Transition\noption.MESSY_WATER_LIGHT_HANDOFF=Match Distant Water Lighting\noption.MESSY_WATER_DEBUG=Water Handoff Diagnostic\nvalue.MESSY_WATER_DEBUG.0=Off\nvalue.MESSY_WATER_DEBUG.1=Water Opacity\nvalue.MESSY_WATER_DEBUG.2=Pre-Reflection Surface (Lit)\nvalue.MESSY_WATER_DEBUG.3=Sky Reflection\nvalue.MESSY_WATER_DEBUG.4=Renderer Coverage\noption.MESSY_WATER_FOG_START=Water Fog Start Distance\noption.MESSY_WATER_FOG_SPAN=Water Fog Fade Distance\noption.MESSY_WATER_FOG_STRENGTH=Water Fog Strength\noption.MESSY_VOXY_FOG=Voxy Distance Fog\noption.MESSY_VOXY_FOG_START=Fog Start Beyond Render Distance (blocks)\noption.MESSY_VOXY_FOG_SPAN=Fog Fade Length (blocks)\noption.MESSY_VOXY_FOG_STRENGTH=Fog Strength\noption.MESSY_VOXY_SHADOW_CONTRAST=Voxy Shadow Contrast\noption.MESSY_VOXY_SHADOW_CONTRAST.comment=Darken skylight-occluded LOD terrain, with no extra ray tracing. Does not add true cast shadows. 0 restores stock lighting.\noption.MESSY_AUTO_PBR=Automatic Material Normals\noption.MESSY_PBR_ENTITIES=IntegratedPBR on Entities\noption.MESSY_PBR_ENTITIES.comment=Apply automatic texture-detail normals to mobs and other entities. Off by default; may increase GPU cost.\noption.MESSY_AUTO_PBR_STRENGTH=Automatic Normal Strength\noption.MESSY_AUTO_PBR_RESOLUTION=Automatic Normal Resolution\noption.MESSY_AUTO_PBR_DISTANCE=Automatic Normal Distance\n"

    replace_one(pack, props,
                "screen.SKY_SCREEN = COLOR_SCHEME [CUSTOM_COLORS_SCREEN] <empty> <empty> SIMPLE_SKY BIOME_SKY BIOME_FOG SANDSTORM <empty> <empty> STAR_SLIDER END_STARS STARS_BRIGHTNESS STARS_COVERAGE AURORA CUSTOM_SKYFIX",
                "screen.SKY_SCREEN = COLOR_SCHEME [CUSTOM_COLORS_SCREEN] <empty> <empty> SIMPLE_SKY BIOME_SKY BIOME_FOG SANDSTORM <empty> <empty> STAR_SLIDER END_STARS STARS_BRIGHTNESS STARS_COVERAGE AURORA CUSTOM_SKYFIX MESSY_HIDE_CUSTOM_SKY MESSY_HIDE_VANILLA_CELESTIALS")
    replace_one(pack, props,
                "screen.MESSY_WATER_SCREEN= MESSY_WATER_LIGHT_HANDOFF",
                "screen.MESSY_WATER_SCREEN= MESSY_MOON_REFLECTION MESSY_WATER_LIGHT_HANDOFF")
    pack[lang] += (b"option.MESSY_HIDE_CUSTOM_SKY=Hide Resource-Pack Sky Overlays\n"
                   b"option.MESSY_HIDE_CUSTOM_SKY.comment=Suppress Iris custom-sky layers; does not disable Golem Core or other mod sky renderers.\n"
                   b"option.MESSY_HIDE_VANILLA_CELESTIALS=Hide Vanilla Sun and Moon\n"
                   b"option.MESSY_HIDE_VANILLA_CELESTIALS.comment=Try this when NTM Space or another mod draws a second sun and moon. May leave only mod-rendered celestial bodies.\n"
                   b"option.MESSY_MOON_REFLECTION=Moon Reflection on Water\n"
                   b"option.MESSY_MOON_REFLECTION.comment=Independent night-time moon glint strength for nearby and Voxy water.\n"
                   b"value.MESSY_MOON_REFLECTION.0=Off\n"
                   b"value.MESSY_MOON_REFLECTION.1=Subtle\n"
                   b"value.MESSY_MOON_REFLECTION.2=Bright\n")

    # E-Lite's Voxy patch manifest refers to a Minecraft 1.21.9 uniform.
    replace_one(pack, "shaders/common/voxy.json", '    "endFlashIntensity",',
                '    #if MC_VERSION >= 12109\n    "endFlashIntensity",\n    #endif')
    replace_one(pack, props,
                "uniform.float.pale_garden = smooth(if(in(biome, BIOME_PALE_GARDEN), 1, 0), 60, 60)",
                "#if MC_VERSION >= 12104\nuniform.float.pale_garden = smooth(if(in(biome, BIOME_PALE_GARDEN), 1, 0), 60, 60)\n#else\nuniform.float.pale_garden = 0.0\n#endif")
    apply_entity_materials(pack)
    apply_colorwheel(pack)
    patch_cloud_occlusion(pack)
    patch_custom_sky_and_moon_glint(pack)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "MessyShaders-E-Lite-PBR-Voxy.zip")
    args = parser.parse_args()
    pack = read_source(SOURCE)
    patch(pack)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.output, "w", ZIP_DEFLATED, compresslevel=9) as z:
        for name, value in sorted(pack.items()):
            z.writestr(name, value)
    with ZipFile(args.output) as z:
        assert z.testzip() is None
    print(args.output)


if __name__ == "__main__":
    main()
