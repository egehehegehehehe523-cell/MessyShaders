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


def patch(pack: dict[str, bytes]) -> None:
    from patch_clean_colorwheel import apply as apply_colorwheel
    from patch_entity_materials import apply as apply_entity_materials
    config = "shaders/lib/config.glsl"
    props = "shaders/shaders.properties"
    lang = "shaders/lang/en_US.lang"
    fragment = "shaders/common/solid_blocks_fragment.glsl"

    # Preserve the previous stable default: generated materials do not force
    # LabPBR on. Users may enable authored LabPBR via the original E-Lite menu.
    pack[config] += b"\n#define MESSY_AUTO_PBR // Atlas-material fallback; authored maps have priority\n//#define MESSY_PBR_ENTITIES // Opt-in procedural normals for entity models\n#define MESSY_AUTO_PBR_STRENGTH 1.0 // [0.0 0.5 0.75 1.0 1.25 1.5]\n#define MESSY_AUTO_PBR_RESOLUTION 512 // [128 256 512 1024]\n#define MESSY_AUTO_PBR_DISTANCE 56 // [16 24 32 40 48 56 72]\n#define MESSY_VOXY_FOG // Shader-owned distant LOD fog\n#define MESSY_VOXY_FOG_START 128 // [0 64 128 256 512 1024]\n#define MESSY_VOXY_FOG_SPAN 1024 // [256 512 768 1024 1536 2048 4096]\n#define MESSY_VOXY_FOG_STRENGTH 0.75 // [0.0 0.25 0.5 0.75 1.0]\n#define MESSY_UNIFIED_WATER // Same inexpensive surface palette for near and Voxy water\n#define MESSY_UNIFIED_WATER_DARKNESS 0.65 // [0.35 0.5 0.65 0.8 1.0]\n#define MESSY_UNIFIED_WATER_REFLECTION 0.25 // [0.0 0.1 0.2 0.25 0.35 0.5]\n"

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

    # Keep stock E-Lite water as a toggleable fallback. Unified mode replaces
    # both rendered water colors with one inexpensive dark surface model.
    # Actual near/Voxy geometry remains managed by the respective renderers.
    water = "shaders/common/water_voxy_blocks_fragment.glsl"
    near_water = "shaders/common/water_blocks_fragment.glsl"
    unified_near = """    #ifdef MESSY_UNIFIED_WATER
        if (is_water > 0.5) {
            vec3 messyBase = WATER_COLOR * MESSY_UNIFIED_WATER_DARKNESS;
            vec3 messyReflect = sky_color_reflect * visible_sky;
            block_color.rgb = mix(messyBase, messyReflect,
                clamp(fresnel * MESSY_UNIFIED_WATER_REFLECTION, 0.0, 0.5));
            block_color.a = 1.0;
        }
    #endif

"""
    unified_far = """    #ifdef MESSY_UNIFIED_WATER
        if (customId == ENTITY_WATER) {
            vec3 messyBase = WATER_COLOR * MESSY_UNIFIED_WATER_DARKNESS;
            vec3 messyReflect = skyColorReflect * visibleSky;
            blockColor.rgb = mix(messyBase, messyReflect,
                clamp(fresnel * MESSY_UNIFIED_WATER_REFLECTION, 0.0, 0.5));
            blockColor.a = 1.0;
        }
    #endif

"""
    replace_one(pack, near_water, '    #include "/src/finalcolor.glsl"',
                unified_near + '    #include "/src/finalcolor.glsl"')
    replace_one(pack, water, '    #include "/src/finalcolor_voxy.glsl"',
                unified_far + '    #include "/src/finalcolor_voxy.glsl"')

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

    replace_one(pack, props,
                "screen.RENDER_SCREEN= AA_TYPE FXAA FOG_ACTIVE FOG_ADJUST NEAR_FOG FOG_TINT NETHER_FOG_DISTANCE FOLIAGE_V <empty> <empty> PERF_IMPACT",
                "screen.RENDER_SCREEN= AA_TYPE FXAA FOG_ACTIVE FOG_ADJUST NEAR_FOG FOG_TINT NETHER_FOG_DISTANCE FOLIAGE_V [MESSY_VOXY_SCREEN] <empty> PERF_IMPACT\n"
                "screen.MESSY_VOXY_SCREEN= MESSY_VOXY_FOG MESSY_VOXY_FOG_START MESSY_VOXY_FOG_SPAN MESSY_VOXY_FOG_STRENGTH [MESSY_WATER_SCREEN]")
    replace_one(pack, props,
                "screen.LabPBR= LabPBR POM POM_SHADOW LabEMISSIVE POM_DEPTH POM_STEPS SS_SAMPLES",
                "screen.LabPBR= LabPBR POM POM_SHADOW LabEMISSIVE POM_DEPTH POM_STEPS SS_SAMPLES")
    replace_one(pack, props, "[LabPBR] [INFO_SCREEN]",
                "[LabPBR] [MESSY_FEATURES] [INFO_SCREEN]")
    pack[props] += b"\nscreen.MESSY_FEATURES.columns=2\nscreen.MESSY_FEATURES= [MESSY_MATERIALS_SCREEN] [MESSY_VOXY_SCREEN] [MESSY_WATER_SCREEN] PERF_IMPACT\nscreen.MESSY_MATERIALS_SCREEN= MESSY_AUTO_PBR MESSY_PBR_ENTITIES MESSY_AUTO_PBR_STRENGTH MESSY_AUTO_PBR_RESOLUTION MESSY_AUTO_PBR_DISTANCE\nscreen.MESSY_WATER_SCREEN= MESSY_UNIFIED_WATER MESSY_UNIFIED_WATER_DARKNESS MESSY_UNIFIED_WATER_REFLECTION\n"
    replace_one(pack, props, "sliders = ",
                "sliders = MESSY_AUTO_PBR_STRENGTH MESSY_AUTO_PBR_RESOLUTION "
                "MESSY_AUTO_PBR_DISTANCE MESSY_VOXY_FOG_START "
                "MESSY_VOXY_FOG_SPAN MESSY_VOXY_FOG_STRENGTH MESSY_UNIFIED_WATER_DARKNESS MESSY_UNIFIED_WATER_REFLECTION ")
    pack[lang] += b"\nscreen.MESSY_FEATURES=MessyShaders Settings\nscreen.MESSY_MATERIALS_SCREEN=Automatic Materials\nscreen.MESSY_VOXY_SCREEN=Voxy Distance Fog\nscreen.MESSY_WATER_SCREEN=Unified Water\noption.MESSY_UNIFIED_WATER=Unified Simple Water\noption.MESSY_UNIFIED_WATER_DARKNESS=Unified Water Darkness\noption.MESSY_UNIFIED_WATER_REFLECTION=Unified Water Reflection\noption.MESSY_VOXY_FOG=Voxy Distance Fog\noption.MESSY_VOXY_FOG_START=Fog Start Beyond Render Distance (blocks)\noption.MESSY_VOXY_FOG_SPAN=Fog Fade Length (blocks)\noption.MESSY_VOXY_FOG_STRENGTH=Fog Strength\noption.MESSY_AUTO_PBR=Automatic Material Normals\noption.MESSY_PBR_ENTITIES=Apply Automatic Materials to Entities\noption.MESSY_AUTO_PBR_STRENGTH=Automatic Normal Strength\noption.MESSY_AUTO_PBR_RESOLUTION=Automatic Normal Resolution\noption.MESSY_AUTO_PBR_DISTANCE=Automatic Normal Distance\n"

    # E-Lite's Voxy patch manifest refers to a Minecraft 1.21.9 uniform.
    replace_one(pack, "shaders/common/voxy.json", '    "endFlashIntensity",',
                '    #if MC_VERSION >= 12109\n    "endFlashIntensity",\n    #endif')
    replace_one(pack, props,
                "uniform.float.pale_garden = smooth(if(in(biome, BIOME_PALE_GARDEN), 1, 0), 60, 60)",
                "#if MC_VERSION >= 12104\nuniform.float.pale_garden = smooth(if(in(biome, BIOME_PALE_GARDEN), 1, 0), 60, 60)\n#else\nuniform.float.pale_garden = 0.0\n#endif")
    apply_entity_materials(pack)
    apply_colorwheel(pack)


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
