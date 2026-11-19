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
    // Distant or minified texture gradients shimmer. Skip extra fetches.
    float footprint = max(uvFootprint.x, uvFootprint.y);
    if (distanceToCamera > 56.0 || footprint >= 1.8 ||
        MESSY_AUTO_NORMAL_STRENGTH <= 0.0) return flatNormal;

    vec2 texel = 1.0 / max(atlasPixels, vec2(16.0));
    vec2 rightUV = messyAutoSpriteUV(uv + vec2(texel.x, 0.0), sprite, texel);
    vec2 leftUV = messyAutoSpriteUV(uv - vec2(texel.x, 0.0), sprite, texel);
    vec2 downUV = messyAutoSpriteUV(uv + vec2(0.0, texel.y), sprite, texel);
    vec2 upUV = messyAutoSpriteUV(uv - vec2(0.0, texel.y), sprite, texel);
    const vec3 luminosity = vec3(0.2126, 0.7152, 0.0722);
    vec2 delta = vec2(
        dot(texture2D(albedo, leftUV).rgb, luminosity) -
        dot(texture2D(albedo, rightUV).rgb, luminosity),
        dot(texture2D(albedo, upUV).rgb, luminosity) -
        dot(texture2D(albedo, downUV).rgb, luminosity));

    // Central differences cancel alternating checkerboard texels naturally.
    // Keep real stone/gravel relief; only damp exceptional high-contrast edges.
    float contrast = abs(delta.x) + abs(delta.y);
    float confidence = smoothstep(0.012, 0.065, contrast) *
                       (1.0 - 0.60 * smoothstep(0.42, 0.90, contrast));
    float mipFade = 1.0 - smoothstep(1.0, 1.8, footprint);
    float distanceFade = 1.0 - smoothstep(32.0, 56.0, distanceToCamera);
    detail = clamp(confidence * mipFade * distanceFade, 0.0, 1.0);

    vec2 slope = clamp(delta, vec2(-0.24), vec2(0.24)) *
                 (0.95 * MESSY_AUTO_NORMAL_STRENGTH * detail);
    vec3 tangentNormal = normalize(vec3(slope, 1.0));
    return normalize(tangentFrame * tangentNormal);
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

    # For generated data, preserve E-Lite's flat diffuse baseline and apply
    # only a bounded native shadow_c_relief adjustment. This replaces the old
    # prototype's severe 0.60..1.50 multiplier (which remains disabled).
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
            vec3 direction = normalize(mix(-sunPosition, sunPosition, light_mix));
            float baseline = max(dot(flat_normal, direction), 0.0);
            float adjusted = max(dot(bumpedNormal, direction), 0.0);
            shadow_c_relief *= clamp(1.0 + 0.90 * (adjusted - baseline), 0.82, 1.18);
        }
    #else
        float shadow_c_relief = directLight2;
    #endif"""
    replace_one(pack, fragment, diffuse, diffuse_replacement)

    lab_diffuse_fallback = """
    #if !defined NETHER && defined LabPBR && defined MESSY_AUTO_MATERIALS && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)
        if (messyAutoMissingMaps && foliageData.x < 0.3 && isGrass < 0.5) {
            vec3 direction = normalize(mix(-sunPosition, sunPosition, light_mix));
            float baseline = max(dot(flat_normal, direction), 0.0);
            float adjusted = max(dot(bumpedNormal, direction), 0.0);
            shadow_c_relief = directLight2 *
                clamp(1.0 + 0.90 * (adjusted - baseline), 0.82, 1.18);
        }
    #endif
"""
    replace_one(pack, fragment,
                "    #if defined MESSY_IPBR && !defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)\n        // Modify sunlight/moonlight",
                lab_diffuse_fallback + "    #if defined MESSY_IPBR && !defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)\n        // Modify sunlight/moonlight")

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

    # An in-game diagnostic is essential when users report completely flat
    # normals. White = strong generated bump; black = flat face / authored
    # map. This writes *after* the ordinary final color pipeline and is off
    # by default, costing nothing unless explicitly enabled in the menu.
    replace_one(pack, fragment,
                '    #include "/src/writebuffers.glsl"',
                """    #if defined MESSY_AUTO_NORMAL_DEBUG && defined MESSY_AUTO_MATERIALS && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)
        float messyBumpAmount = length(normalize(bumpedNormal) - normalize(flat_normal));
        block_color.rgb = vec3(clamp(messyBumpAmount * 5.0, 0.0, 1.0));
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
                     "// #define MESSY_AUTO_NORMAL_DEBUG\n").encode()
    replace_one(pack, props,
                "screen.MESSY_FEATURES= MESSY_DYNAMIC_EMITTERS <empty> PERF_IMPACT",
                "screen.MESSY_FEATURES= MESSY_DYNAMIC_EMITTERS MESSY_AUTO_MATERIALS MESSY_AUTO_NORMAL_STRENGTH MESSY_AUTO_NORMAL_DEBUG <empty> PERF_IMPACT")
    replace_one(pack, props,
                "sliders = ",
                "sliders = MESSY_AUTO_NORMAL_STRENGTH ")
    pack[lang] += ("\noption.MESSY_AUTO_MATERIALS=Automatic Block Materials\n"
                   "option.MESSY_AUTO_MATERIALS.comment=Sprite-generated normals and roughness, including atlas sprites missing both LabPBR maps. Authored map pixels take priority.\n"
                   "option.MESSY_AUTO_NORMAL_STRENGTH=Automatic Normal Detail\n"
                   "option.MESSY_AUTO_NORMAL_STRENGTH.comment=Strength of generated surface relief. Zero keeps block faces flat.\n"
                   "option.MESSY_AUTO_NORMAL_DEBUG=Visualize Normal Relief\n"
                   "option.MESSY_AUTO_NORMAL_DEBUG.comment=Diagnostic mode: brighter grayscale means stronger bumps; solid black is flat. Turn off after testing.\n").encode()
    return {
        "default": "conservative automatic normal and roughness shading for terrain and blocks",
        "native_material_classification": True,
        "weather_response": "lightly lower roughness for wet stone/polished IDs; no new texture reads",
        "labpbr_precedence": "autofallback only when normal atlas pixel is neutral and specular atlas pixel is zero",
        "texture_reads": "up to four additional sprite-local albedo reads close up; two map probes in LabPBR mode",
        "water_lod_changes": False,
        "limits": "not actual per-texture LabPBR files; deliberately flat/black authored pixels indistinguishable from absent maps",
    }
