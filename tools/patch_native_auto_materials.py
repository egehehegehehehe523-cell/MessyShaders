"""Conservative automatic materials in E-Lite's native block-shading inputs.

This deliberately does not reactivate the older MESSY_IPBR prototype, create
external LabPBR maps, or modify water/LOD shaders. Authored LabPBR texture
maps remain the authoritative source when LabPBR is selected.
"""
from __future__ import annotations


LIBRARY = r"""

// Automatic material fallback for terrain/block atlas sprites without LabPBR.
// These are shading inputs, not fabricated _n/_s image textures.
#if defined MESSY_AUTO_MATERIALS && !defined LabPBR
vec2 messyAutoSpriteUV(vec2 uv, vec4 sprite, vec2 texel) {
    return clamp(uv, sprite.xy + texel * 0.55,
                sprite.xy + sprite.zw - texel * 0.55);
}

vec3 messyAutoBumpedNormal(sampler2D albedo, vec2 uv, vec3 baseColor,
                           vec4 sprite, mat3 tangentFrame, vec3 flatNormal,
                           vec2 atlasPixels, vec2 uvFootprint,
                           float distanceToCamera, out float detail) {
    detail = 0.0;
    // Distant or minified texture gradients shimmer, and needlessly sample
    // another pair of texels. Skip before fetching any neighboring colors.
    float footprint = max(uvFootprint.x, uvFootprint.y);
    if (distanceToCamera > 48.0 || footprint >= 1.8 ||
        MESSY_AUTO_NORMAL_STRENGTH <= 0.0) return flatNormal;

    vec2 texel = 1.0 / max(atlasPixels, vec2(16.0));
    vec2 rightUV = messyAutoSpriteUV(uv + vec2(texel.x, 0.0), sprite, texel);
    vec2 belowUV = messyAutoSpriteUV(uv + vec2(0.0, texel.y), sprite, texel);
    const vec3 luminosity = vec3(0.2126, 0.7152, 0.0722);
    float baseHeight = dot(baseColor, luminosity);
    vec2 delta = vec2(dot(texture2D(albedo, rightUV).rgb, luminosity),
                      dot(texture2D(albedo, belowUV).rgb, luminosity)) - baseHeight;

    // Albedo is not a true height map. Reject subtle filtering noise AND
    // sharp checkerboard/gravel contrast instead of interpreting it as cliffs.
    float contrast = abs(delta.x) + abs(delta.y);
    float confidence = smoothstep(0.018, 0.075, contrast) *
                       (1.0 - smoothstep(0.17, 0.39, contrast));
    float mipFade = 1.0 - smoothstep(0.75, 1.8, footprint);
    float distanceFade = 1.0 - smoothstep(26.0, 48.0, distanceToCamera);
    detail = clamp(confidence * mipFade * distanceFade, 0.0, 1.0);

    vec2 slope = clamp(delta, vec2(-0.12), vec2(0.12)) *
                 (1.2 * MESSY_AUTO_NORMAL_STRENGTH * detail);
    vec3 tangentNormal = normalize(vec3(-slope, 1.0));
    return normalize(tangentFrame * tangentNormal);
}

float messyAutoMaterialRoughness(float textureDetail, float luminance,
                                 float nativeReflectivity) {
    // Most atlas sprites are stone/wood/earth. Preserve that matte prior;
    // only E-Lite's own reflective material IDs can trigger metal-like gloss.
    float recognizedMetal = step(0.55, nativeReflectivity);
    float rough = clamp(0.88 + 0.055 * textureDetail - 0.11 * luminance,
                        0.68, 0.94);
    return mix(rough, 0.38, recognizedMetal);
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
    # patch_safe_materials. Reuse only the native tangent/atlas varyings.
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
            shadow_c_relief *= clamp(1.0 + 0.70 * (adjusted - baseline), 0.88, 1.12);
        }
    #else
        float shadow_c_relief = directLight2;
    #endif"""
    replace_one(pack, fragment, diffuse, diffuse_replacement)

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
                    messyTextureVariation, block_luma, reflex_index2);
                float recognizedMetal = step(0.55, reflex_index2);
                isMetal = recognizedMetal;
                float targetGloss = mix(5.0 + 28.0 * squarePow(1.0 - currentRoughness),
                                        58.0, recognizedMetal);
                final_gloss_power = mix(glossParms.g, targetGloss, 0.32);
            #endif"""
    replace_one(pack, fragment, material, material_replacement)

    pack[library] += LIBRARY.encode("utf-8")
    # New independent option is deliberately not subject to the old unsafe
    # preview guard, even with a persisted Iris profile containing MESSY_IPBR.
    pack[config] += ("\n// Conservative fallback for block atlas textures; water untouched.\n"
                     "// With LabPBR enabled, authored _n/_s maps win entirely.\n"
                     "#define MESSY_AUTO_MATERIALS\n"
                     "#define MESSY_AUTO_NORMAL_STRENGTH 0.75 // [0.0 0.35 0.5 0.75 1.0 1.25]\n").encode()
    replace_one(pack, props,
                "screen.MESSY_FEATURES= MESSY_DYNAMIC_EMITTERS <empty> PERF_IMPACT",
                "screen.MESSY_FEATURES= MESSY_DYNAMIC_EMITTERS MESSY_AUTO_MATERIALS MESSY_AUTO_NORMAL_STRENGTH <empty> PERF_IMPACT")
    replace_one(pack, props,
                "sliders = ",
                "sliders = MESSY_AUTO_NORMAL_STRENGTH ")
    pack[lang] += ("\noption.MESSY_AUTO_MATERIALS=Automatic Block Materials\n"
                   "option.MESSY_AUTO_MATERIALS.comment=Gentle sprite-generated normals and roughness for blocks without a PBR resource pack. LabPBR maps take priority.\n"
                   "option.MESSY_AUTO_NORMAL_STRENGTH=Automatic Normal Detail\n"
                   "option.MESSY_AUTO_NORMAL_STRENGTH.comment=Strength of generated surface relief. Zero keeps block faces flat.\n").encode()
    return {
        "default": "conservative automatic normal and roughness shading for terrain and blocks",
        "native_material_classification": True,
        "labpbr_precedence": "authored LabPBR _n/_s when LabPBR is selected",
        "texture_reads": "up to two additional sprite-local albedo reads, skipped at distance/minification",
        "water_lod_changes": False,
        "limits": "not actual per-texture LabPBR files; arbitrary albedo cannot identify true material composition",
    }
