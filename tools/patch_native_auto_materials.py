"""Conservative automatic materials in E-Lite's native block-shading inputs.

This deliberately does not reactivate the older MESSY_IPBR prototype, create
external LabPBR maps, or modify water/LOD shaders. Authored LabPBR texture
maps remain the authoritative source when LabPBR is selected.
"""
from __future__ import annotations


LIBRARY = r"""

// Automatic material fallback for terrain/block atlas sprites. Iris supplies
// neutral _n / _s pixels where maps are absent, including in mixed atlases.
// These are shading inputs, not fabricated _n/_s image textures.
#ifdef MESSY_AUTO_MATERIALS
vec2 messyAutoSpriteUV(vec2 uv, vec4 sprite, vec2 texel) {
    return clamp(uv, sprite.xy + texel * 0.55,
                sprite.xy + sprite.zw - texel * 0.55);
}

vec3 messyAutoBumpedNormal(sampler2D albedo, vec2 uv, vec3 baseColor,
                           vec4 sprite, mat3 tangentFrame, vec3 flatNormal,
                           vec2 atlasPixels, vec2 uvFootprint,
                           float distanceToCamera, out float detail) {
    detail = 0.0;
    // Preserve existing UVs. This samples on either side of texel borders,
    // so relief appears as fine beveled edges instead of blocky color blobs.
    float footprint = max(uvFootprint.x, uvFootprint.y);
    if (distanceToCamera > 56.0 || footprint >= 1.25 ||
        MESSY_AUTO_NORMAL_STRENGTH <= 0.0) return flatNormal;

    vec2 texel = 1.0 / max(atlasPixels, vec2(16.0));
    float nominalStep = 16.0 / float(MESSY_AUTO_NORMAL_RESOLUTION);
    vec2 sampleStep = max(vec2(nominalStep), uvFootprint);
    vec2 offset = sampleStep * texel;
    vec2 rightUV = messyAutoSpriteUV(uv + vec2(offset.x, 0.0), sprite, texel);
    vec2 leftUV = messyAutoSpriteUV(uv - vec2(offset.x, 0.0), sprite, texel);
    vec2 downUV = messyAutoSpriteUV(uv + vec2(0.0, offset.y), sprite, texel);
    vec2 upUV = messyAutoSpriteUV(uv - vec2(0.0, offset.y), sprite, texel);

    // A narrow local contrast gate suppresses minor color noise while
    // preserving sharp boundaries between adjacent pixels in the sprite.
    float middle = length(baseColor);
    vec4 contrast = vec4(
        middle - length(texture2D(albedo, rightUV).rgb),
        middle - length(texture2D(albedo, leftUV).rgb),
        middle - length(texture2D(albedo, downUV).rgb),
        middle - length(texture2D(albedo, upUV).rgb));
    contrast = sign(contrast) * max(abs(contrast) - 0.05, vec4(0.0));
    contrast = clamp(contrast, vec4(-0.20), vec4(0.20));
    vec2 edge = vec2(contrast.x - contrast.y, contrast.z - contrast.w);

    float confidence = smoothstep(0.025, 0.14, length(edge));
    float mipFade = 1.0 - smoothstep(0.65, 1.25, footprint);
    float distanceFade = 1.0 - smoothstep(32.0, 56.0, distanceToCamera);
    detail = clamp(confidence * mipFade * distanceFade, 0.0, 1.0);

    float resolutionScale = sqrt(float(MESSY_AUTO_NORMAL_RESOLUTION) / 128.0);
    vec2 samplingCompensation = vec2(nominalStep) / sampleStep;
    vec2 slope = clamp(edge * samplingCompensation *
                       (5.0 * MESSY_AUTO_NORMAL_STRENGTH * resolutionScale *
                        mipFade * distanceFade), vec2(-1.10), vec2(1.10));
    vec3 tangentNormal = normalize(vec3(slope, 1.0));
    return normalize(tangentFrame * tangentNormal);
}

float messyAutoDirectRelief(vec3 flatNormal, vec3 bumpedNormal,
                            vec3 lightDirection) {
    // E-Lite already applied the face's N.L in the vertex shader. Correct
    // that existing direct light by the ratio of pixel- and face-normal
    // Lambert terms instead of multiplying by a tiny absolute difference.
    // The bias keeps grazing faces stable. Keep this subtle: large Lambert
    // ratios are visibly blotchy on low-resolution gravel and stone sprites.
    // Ambient, colored blocklight and emissive light stay intact.
    float faceLambert = max(dot(normalize(flatNormal), lightDirection), 0.0);
    float pixelLambert = max(dot(normalize(bumpedNormal), lightDirection), 0.0);
    float correction = clamp((pixelLambert + 0.20) / (faceLambert + 0.20),
                             0.70, 1.30);
    return mix(1.0, correction, 0.80);
}

float messyAutoSkyRelief(vec3 flatNormal, vec3 bumpedNormal,
                         vec3 skyDirection, float daytime) {
    // E-Lite's sky/ambient irradiance is also based on the original face.
    // A small world-up correction makes shallow pixel edges visible in shade,
    // while night lighting and coloured emitters retain their original color.
    float facingDifference = dot(normalize(bumpedNormal), skyDirection) -
                             dot(normalize(flatNormal), skyDirection);
    float correction = clamp(1.0 + facingDifference * 0.40, 0.75, 1.25);
    return mix(1.0, correction, 0.70 * daytime);
}

float messyAutoMaterialRoughness(float textureDetail, float luminance,
                                 float nativeReflectivity, float rainWetness) {
    // Most atlas sprites are stone/wood/earth. Preserve that matte prior;
    // only E-Lite's own reflective material IDs can trigger metal-like gloss.
    float recognizedMetal = step(0.55, nativeReflectivity);
    float polished = smoothstep(0.26, 0.38, nativeReflectivity) * (1.0 - recognizedMetal);
    float rough = clamp(0.88 + 0.055 * textureDetail - 0.11 * luminance,
                        0.68, 0.94);
    // Native reflective/polished IDs are smoother than ordinary stone.
    // Rain slightly reduces roughness instead of applying fake wet albedo.
    rough = mix(rough, 0.55, polished * 0.65);
    rough -= rainWetness * (0.12 + 0.06 * polished) * (1.0 - recognizedMetal);
    return clamp(mix(rough, 0.38, recognizedMetal), 0.30, 0.96);
}
#endif
"""


def replace_one(pack: dict[str, bytes], path: str, old: str, new: str):
    body = pack[path].decode("utf-8")
    count = body.count(old)
    if count != 1:
        raise ValueError(f"Unexpected automatic material anchor {path}: {old!r} ({count})")
    pack[path] = body.replace(old, new, 1).encode("utf-8")


def replace_all(pack: dict[str, bytes], path: str, old: str, new: str):
    body = pack[path].decode("utf-8")
    if old not in body:
        raise ValueError(f"No automatic material anchor {path}: {old!r}")
    pack[path] = body.replace(old, new).encode("utf-8")


def apply_native_auto_materials(pack: dict[str, bytes]) -> dict:
    vertex = "shaders/common/solid_blocks_vertex.glsl"
    fragment = "shaders/common/solid_blocks_fragment.glsl"
    config = "shaders/lib/config.glsl"
    props = "shaders/shaders.properties"
    lang = "shaders/lang/en_US.lang"
    library = "shaders/lib/messy_procedural_pbr.glsl"

    # Keep the original high-strength MESSY_IPBR preview forbidden by
    # patch_safe_materials. Reuse E-Lite's native tangent/atlas varyings.
    for path in (vertex, fragment):
        replace_all(pack, path, "defined LabPBR || defined MESSY_IPBR",
                    "defined LabPBR || defined MESSY_IPBR || defined MESSY_AUTO_MATERIALS")
    replace_one(pack, fragment,
                "#if defined(MESSY_IPBR) || defined(MESSY_COATED_TEXTURES)",
                "#if defined(MESSY_IPBR) || defined(MESSY_COATED_TEXTURES) || defined(MESSY_AUTO_MATERIALS)")

    original_normal = "    #elif defined MESSY_IPBR && !defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)\n        vec3 bumpedNormal = messyGeneratedNormal("
    new_normal = """    #elif defined MESSY_AUTO_MATERIALS && !defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)
        // Reuse E-Lite's normal and reflection inputs; never perturb albedo UVs.
        // Leaves and cutouts retain the face normal to avoid stippled foliage.
        vec3 bumpedNormal = flat_normal;
        // Derivatives must be evaluated before the per-material branch.
        vec2 messyFootprint = fwidth(final_uv * vec2(atlasSize));
        if (foliageData.x < 0.3 && block_type != 1.0) {
            bumpedNormal = messyAutoBumpedNormal(
                tex, final_uv, pure_block_color.rgb, atlas_uv, tbn,
                flat_normal, vec2(atlasSize), messyFootprint,
                length(sub_position3), messyTextureVariation);
        }
    #elif defined MESSY_IPBR && !defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)
        vec3 bumpedNormal = messyGeneratedNormal("""
    replace_one(pack, fragment, original_normal, new_normal)
    replace_one(pack, fragment,
                "    float messyTextureVariation = 0.0;\n    // === PBR auxiliary",
                "    float messyTextureVariation = 0.0;\n"
                "    bool messyAutoMissingMaps = false;\n"
                "    // === PBR auxiliary")

    # E-Lite's zero-gloss path still evaluates spec_energy in the final light
    # sum. Without initialization it can show undefined colored light patches
    # even when there is no specular response to contribute.
    replace_one(pack, fragment,
                "    vec3 spec_energy;\n",
                "    vec3 spec_energy = vec3(0.0);\n")

    # Preserve E-Lite's exact atlas UVs. A synthetic height map made solely
    # from color creates false layers on grass/dirt and distorts sprite edges.
    # Genuine LabPBR _n alpha height maps can still use the native POM path.

    # When LabPBR is enabled but a modded atlas sprite has no _n or _s
    # texture, Iris fills both samplers with neutral values. Respect real maps
    # pixel by pixel and only fall back for the neutral+zero combination.
    # A purposefully flat _n plus black _s is indistinguishable from missing.
    lab_fallback = """    #if defined MESSY_AUTO_MATERIALS && defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)
        vec2 messyFootprint = fwidth(final_uv * vec2(atlasSize));
        vec3 messyNormalProbe = texture2D(normals, texcoord).rgb;
        vec3 messySpecProbe = texture2D(specular, texcoord).rgb;
        messyAutoMissingMaps =
            all(lessThan(abs(messyNormalProbe.rg - vec2(128.0 / 255.0)), vec2(0.012))) &&
            messyNormalProbe.b > 0.97 &&
            max(messySpecProbe.r, max(messySpecProbe.g, messySpecProbe.b)) < 0.007;
        if (messyAutoMissingMaps && block_type != 1.0 && foliageData.x < 0.3) {
            bumpedNormal = messyAutoBumpedNormal(
                tex, final_uv, pure_block_color.rgb, atlas_uv, tbn,
                flat_normal, vec2(atlasSize), messyFootprint,
                length(sub_position3), messyTextureVariation);
        }
    #endif

"""
    shading_header = "    #if !defined NETHER && (defined LabPBR || defined MESSY_IPBR || defined MESSY_AUTO_MATERIALS) && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)"
    replace_one(pack, fragment, shading_header, lab_fallback + shading_header)

    # E-Lite's direct_light_strength already contains the flat face's N.L,
    # so generated normals must correct that term by a bounded Lambert ratio.
    # Keep the original roughness, ambient, RGB lighting and shadow mapping.
    diffuse = """    #if !defined NETHER && (defined LabPBR || defined MESSY_IPBR || defined MESSY_AUTO_MATERIALS) && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)
        float shadow_c_relief;
        if(foliageData.x < 0.3) {  
            vec3 shadowLightDir = mix(-sunPosition, sunPosition, light_mix) * 0.01;
            float diffuseRelief = clamp(dot(bumpedNormal, shadowLightDir), 0.0, 1.0);
            shadow_c_relief = (isGrass < 0.5) ? sqrt(directLight2 * diffuseRelief) : directLight2;
        } else {
            shadow_c_relief = directLight2;
        }
    #else
        float shadow_c_relief = directLight2;
    #endif"""
    diffuse_replacement = """    #if !defined NETHER && (defined LabPBR || defined MESSY_IPBR) && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)
        float shadow_c_relief;
        if(foliageData.x < 0.3) {  
            vec3 shadowLightDir = mix(-sunPosition, sunPosition, light_mix) * 0.01;
            float diffuseRelief = clamp(dot(bumpedNormal, shadowLightDir), 0.0, 1.0);
            shadow_c_relief = (isGrass < 0.5) ? sqrt(directLight2 * diffuseRelief) : directLight2;
        } else {
            shadow_c_relief = directLight2;
        }
    #elif !defined NETHER && defined MESSY_AUTO_MATERIALS && !defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)
        float shadow_c_relief = directLight2;
        if (foliageData.x < 0.3 && isGrass < 0.5) {
            // Select a nonzero direction at sunrise/sunset. The former
            // normalize(mix(-sunPosition, sunPosition, 0.5)) was undefined.
            vec3 direction = normalize(light_mix >= 0.5 ? sunPosition : -sunPosition);
            // Only sunlight: the moon correction made bright local RGB light
            // appear to have dark blue/purple material patches at night.
            float sunRelief = smoothstep(0.58, 0.78, light_mix);
            shadow_c_relief *= mix(1.0,
                messyAutoDirectRelief(flat_normal, bumpedNormal, direction), sunRelief);
        }
    #else
        float shadow_c_relief = directLight2;
    #endif"""
    replace_one(pack, fragment, diffuse, diffuse_replacement)

    lab_diffuse_fallback = """
    #if !defined NETHER && defined LabPBR && defined MESSY_AUTO_MATERIALS && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)
        if (messyAutoMissingMaps && foliageData.x < 0.3 && isGrass < 0.5) {
            vec3 direction = normalize(light_mix >= 0.5 ? sunPosition : -sunPosition);
            float sunRelief = smoothstep(0.58, 0.78, light_mix);
            shadow_c_relief = directLight2 * mix(1.0,
                messyAutoDirectRelief(flat_normal, bumpedNormal, direction), sunRelief);
        }
    #endif
"""
    replace_one(pack, fragment,
                "    #if defined MESSY_IPBR && !defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)\n        // Modify sunlight/moonlight",
                lab_diffuse_fallback + "    #if defined MESSY_IPBR && !defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)\n        // Modify sunlight/moonlight")

    # Normals should also affect E-Lite's diffuse sky fill, which otherwise
    # overwhelms the direct-light correction. Keep local RGB emission and
    # candle light completely unmodified, particularly at night.
    sky_relief = """    vec3 messyAutoOmni = omni_light;
    #if defined MESSY_AUTO_MATERIALS && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)
        bool messyUseAutoSky = foliageData.x < 0.3 && isGrass < 0.5;
        #if defined LabPBR
            messyUseAutoSky = messyUseAutoSky && messyAutoMissingMaps;
        #endif
        if (messyUseAutoSky && light_mix > 0.58) {
            float daylightSky = smoothstep(0.58, 0.78, light_mix);
            vec3 upInView = normalize((gbufferModelView * vec4(0.0, 1.0, 0.0, 0.0)).xyz);
            messyAutoOmni *= messyAutoSkyRelief(flat_normal, bumpedNormal,
                                                upInView, daylightSky);
        }
    #endif

"""
    replace_one(pack, fragment,
                "    // === Block reflection",
                sky_relief + "    // === Block reflection")

    # In the existing ggxSpecular/reflection call, use a restrained roughness
    # estimate. E-Lite's native material IDs still choose actual reflectivity.
    material = """            #if defined MESSY_IPBR && !defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)
                isMetal = step(0.55, reflex_index2);
                currentRoughness = messyAutoRoughness(
                    messyTextureVariation, block_luma, isMetal);
                final_gloss_power = mix(glossParms.g,
                    8.0 + (1.0 - currentRoughness) * 118.0, 0.75);
                block_luma2 *= mix(0.8, 1.3, 1.0 - currentRoughness);
            #endif"""
    material_replacement = material + """
            #if defined MESSY_AUTO_MATERIALS && !defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)
                currentRoughness = messyAutoMaterialRoughness(
                    messyTextureVariation, block_luma, reflex_index2, wetness);
                float recognizedMetal = step(0.55, reflex_index2);
                isMetal = recognizedMetal;
                float targetGloss = mix(5.0 + 28.0 * squarePow(1.0 - currentRoughness),
                                        58.0, recognizedMetal);
                final_gloss_power = mix(glossParms.g, targetGloss, 0.32);
            #endif"""
    replace_one(pack, fragment, material, material_replacement)

    lab_spec_fallback = """            currentRoughness = squarePow(1.0 - smoothness);
            #if defined MESSY_AUTO_MATERIALS && defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)
                if (messyAutoMissingMaps) {
                    // The native zero-filled specular atlas should not make
                    // an otherwise ordinary unmapped modded block unlit.
                    f0_val = reflexIndex;
                    reflex_index2 = f0_val;
                    isMetal = step(0.55, f0_val);
                    currentRoughness = messyAutoMaterialRoughness(
                        messyTextureVariation, block_luma, f0_val, wetness);
                    float targetGloss = mix(6.0 + 32.0 * squarePow(1.0 - currentRoughness),
                                            58.0, isMetal);
                    final_gloss_power = mix(glossParms.g, targetGloss, 0.40);
                    block_luma2 = pow(block_luma * glossParms.b, glossParms.a);
                }
            #endif"""
    replace_one(pack, fragment,
                "            currentRoughness = squarePow(1.0 - smoothness);",
                lab_spec_fallback)

    # The low-performance E-Lite profiles set MATERIAL_GLOSS=0. Their old
    # no-gloss branch bypassed shadow_c_relief entirely, making generated
    # normals visually nonexistent even though normal sampling was active.
    replace_one(pack, fragment,
                """        vec3 real_light = computeRealLight(omni_light, direct_light_color, directLight2, shadow_c, vec3(0.0), candle_color);""",
                """        #if (defined MESSY_AUTO_MATERIALS || defined LabPBR) && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)
            vec3 real_light = computeRealLight(omni_light, direct_light_color, shadow_c_relief, shadow_c, vec3(0.0), candle_color);
        #else
            vec3 real_light = computeRealLight(omni_light, direct_light_color, directLight2, shadow_c, vec3(0.0), candle_color);
        #endif""")
    replace_all(pack, fragment,
                "computeRealLight(omni_light, direct_light_color,",
                "computeRealLight(messyAutoOmni, direct_light_color,")

    # An in-game diagnostic is essential when users report completely flat
    # normals. Blue = flat face / no relief; yellow = generated or authored
    # relief. The visible blue baseline also proves that this shader branch
    # actually ran. This writes *after* the ordinary final color pipeline and is off
    # by default, costing nothing unless explicitly enabled in the menu.
    replace_one(pack, fragment,
                '    #include "/src/writebuffers.glsl"',
                """    #ifdef MESSY_AUTO_NORMAL_DEBUG
    #if defined MESSY_AUTO_MATERIALS && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)
        float messyBumpAmount = length(normalize(bumpedNormal) - normalize(flat_normal));
        block_color.rgb = mix(vec3(0.05, 0.10, 0.22),
                              vec3(1.0, 0.90, 0.45),
                              clamp(messyBumpAmount * 5.0, 0.0, 1.0));
    #endif
    #endif
    #include "/src/writebuffers.glsl"
"""
    )

    pack[library] += LIBRARY.encode("utf-8")
    # New independent option is deliberately not subject to the old unsafe
    # preview guard, even with a persisted Iris profile containing MESSY_IPBR.
    pack[config] += ("\n// Conservative fallback for block atlas textures; water untouched.\n"
                     "// Native LabPBR takes priority for non-neutral _n/_s atlas pixels.\n"
                     "#define MESSY_AUTO_MATERIALS\n"
                     "#define MESSY_AUTO_NORMAL_STRENGTH 1.0 // [0.0 0.5 0.75 1.0 1.25 1.5 2.0]\n"
                     "#define MESSY_AUTO_NORMAL_RESOLUTION 512 // [128 256 512 1024]\n"
                     "//#define MESSY_AUTO_NORMAL_DEBUG\n").encode()
    replace_one(pack, props,
                "screen.MESSY_FEATURES= MESSY_DYNAMIC_EMITTERS <empty> PERF_IMPACT",
                "screen.MESSY_FEATURES= MESSY_DYNAMIC_EMITTERS MESSY_AUTO_MATERIALS MESSY_AUTO_NORMAL_STRENGTH MESSY_AUTO_NORMAL_RESOLUTION MESSY_AUTO_NORMAL_DEBUG <empty> PERF_IMPACT")
    replace_one(pack, props,
                "sliders = ",
                "sliders = MESSY_AUTO_NORMAL_STRENGTH MESSY_AUTO_NORMAL_RESOLUTION ")
    pack[lang] += ("\noption.MESSY_AUTO_MATERIALS=Automatic Block Materials\n"
                   "option.MESSY_AUTO_MATERIALS.comment=Sprite-generated normals and roughness, including atlas sprites missing both LabPBR maps. Authored map pixels take priority.\n"
                   "option.MESSY_AUTO_NORMAL_STRENGTH=Automatic Normal Detail\n"
                   "option.MESSY_AUTO_NORMAL_STRENGTH.comment=Intensity of generated pixel-edge normals. 1.0 gives strong fine relief; zero keeps block faces flat.\n"
                   "option.MESSY_AUTO_NORMAL_RESOLUTION=Automatic Normal Resolution\n"
                   "option.MESSY_AUTO_NORMAL_RESOLUTION.comment=Sub-texel sample precision for raised-looking pixel edges. 512 is the intended detail; lower values soften it. No texture displacement.\n"
                   "option.MESSY_AUTO_NORMAL_DEBUG=Visualize Normal Relief\n"
                   "option.MESSY_AUTO_NORMAL_DEBUG.comment=Diagnostic mode: blue means flat or missing normals; brighter yellow means more relief. Turn off after testing.\n").encode()
    return {
        "default": "conservative automatic normal and roughness shading for terrain and blocks",
        "native_material_classification": True,
        "diffuse_normal_lighting": "per-pixel Lambert correction plus day-gated ambient skylight response; RGB emitters and candle fill unmodified",
        "uninitialized_specular_fixed": True,
        "texture_depth": "no fabricated height displacement; original atlas UVs preserved; authored LabPBR POM remains supported",
        "weather_response": "lightly lower roughness for wet stone/polished IDs; no new texture reads",
        "labpbr_precedence": "autofallback only when normal atlas pixel is neutral and specular atlas pixel is zero",
        "texture_reads": "up to four sprite-local normal probes near the camera; two map probes in LabPBR mode",
        "water_lod_changes": False,
        "limits": "not actual per-texture LabPBR files; deliberately flat/black authored pixels indistinguishable from absent maps",
    }
