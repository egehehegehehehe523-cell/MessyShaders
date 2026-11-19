"""Independent dynamic emissive entity/item + procedural texture PBR prototype.

No Complementary code. Dynamic lights feed the existing world-space light
volume via Iris shadow-pass entity/item uniforms. Procedural normals are
computed per-fragment from the texture atlas (2 extra texel reads) and are
automatically applicable to modded textures. This is experimental.
"""
from __future__ import annotations

ENTITY_COLORS = {
    26200: ("orange", "minecraft:blaze"),
    26201: ("cyan", "minecraft:glow_squid"),
    26202: ("purple", "minecraft:end_crystal"),
    26203: ("orange", "minecraft:fireball minecraft:small_fireball"),
    26204: ("purple", "minecraft:dragon_fireball"),
    26205: ("white", "minecraft:firework_rocket"),
    26206: ("red", "minecraft:magma_cube"),
    26207: ("yellow", "minecraft:glow_item_frame"),
}

PALETTE_INDEX = {
    "white": 1, "brown": 2, "red": 3, "orange": 4, "yellow": 5,
    "lime": 6, "green": 7, "cyan": 8, "light_blue": 9, "blue": 10,
    "purple": 11, "magenta": 12, "pink": 13,
}

def patch_one(files: dict[str, bytes], path: str, old: str, new: str):
    body = files[path].decode("utf-8")
    if body.count(old) != 1:
        raise ValueError(f"Expected exactly one shader patch anchor in {path}: {old!r}, found {body.count(old)}")
    files[path] = body.replace(old, new, 1).encode("utf-8")

def procedural_library():
    return r"""// Original MessyShaders-generated normals and roughness, independent GLSL.
#ifdef MESSY_IPBR
// Two neighboring texels, not a per-material texture cache or another pass.
// Stay inside the current atlas sprite to avoid bleeding from adjacent mods.
vec2 messySafeUV(vec2 uv, vec4 sprite, vec2 texel) {
    return clamp(uv, sprite.xy + texel * 0.55,
                sprite.xy + sprite.zw - texel * 0.55);
}

vec3 messyGeneratedNormal(sampler2D albedo, vec2 uv, vec3 baseColor,
                          vec4 sprite, mat3 tangentFrame, vec2 atlasPixels,
                          out float textureVariation) {
    vec2 texel = 1.0 / max(atlasPixels, vec2(16.0));
    vec2 uvX = messySafeUV(uv + vec2(texel.x, 0.0), sprite, texel);
    vec2 uvY = messySafeUV(uv + vec2(0.0, texel.y), sprite, texel);
    float height = dot(baseColor, vec3(0.2126, 0.7152, 0.0722));
    float dx = dot(texture2D(albedo, uvX).rgb, vec3(0.2126, 0.7152, 0.0722)) - height;
    float dy = dot(texture2D(albedo, uvY).rgb, vec3(0.2126, 0.7152, 0.0722)) - height;
    textureVariation = clamp(3.0 * (abs(dx) + abs(dy)), 0.0, 1.0);
    // Albedo luminance is not a height map. Suppress compression noise
    // and harsh pixel edges before constructing a shallow bump normal.
    vec2 gradient = sign(vec2(dx, dy)) *
        max(abs(vec2(dx, dy)) - vec2(0.035), vec2(0.0));
    gradient = clamp(gradient, vec2(-0.16), vec2(0.16));
    float strength = MESSY_IPBR_NORMAL_STRENGTH * 0.24;
    vec3 n = normalize(vec3(-gradient * strength, 1.0));
    return normalize(tangentFrame * n);
}

float messyAutoRoughness(float variation, float luminosity, float materialMetalness) {
    // Rough by default; smoothness grows for low-detail, brighter surfaces.
    // Metallic materials remain ID-driven, never inferred from light texture colors.
    float rough = clamp(0.72 + 0.22 * variation - 0.14 * luminosity, 0.30, 0.98);
    return mix(rough, max(0.22, rough * 0.65), materialMetalness);
}
#endif
"""

def add_dynamic_lights(files: dict[str, bytes]) -> dict:
    path = "shaders/common/shadow_vertex.glsl"
    if "messyWriteDynamicVoxel" in files[path].decode():
        raise ValueError("Dynamic emitters already installed")
    palette = "\n".join(
        f"    if (entity == {eid}) return {PALETTE_INDEX[color]}u;"
        for eid, (color, _) in ENTITY_COLORS.items()
    )
    extra = f"""
// Iris supplies the identity of an entity / rendered dropped-item in shadows.
uniform int entityId;
uniform int currentRenderedItemId;

uint messyEntityColorIndex(int entity) {{
{palette}
    // E-Lite already maps lightning to 10101. Retain its classification.
    if (entity == 10101) return 1u;
    return 0u;
}}

void messyWriteDynamicVoxel(vec3 worldRelative) {{
#ifdef MESSY_DYNAMIC_EMITTERS
    // Use the same camera-relative integer cell as placed block emitters.
    ivec3 voxel = ivec3(floor(worldRelative + fract(cameraPosition) + 24.0));
    if (any(lessThan(voxel, ivec3(0))) ||
        any(greaterThanEqual(voxel, ivec3(48)))) return;

    uint index = 0u;
    if (currentRenderedItemId >= 26100 && currentRenderedItemId <= 26112)
        index = uint(currentRenderedItemId - 26099);
    else
        index = messyEntityColorIndex(entityId);
    if (index > 0u)
        imageAtomicMax(messyEmitVolume, voxel, index);
#endif
}}
"""
    # Appending to the same shared shadow-source file avoids changing
    # the existing emitter-seeding and occlusion path.
    files["shaders/lib/messy_voxel_vertex.glsl"] += extra.encode("utf-8")
    patch_one(files,path,
              '    messyWriteVoxel(positions.xyz + at_midBlock.xyz / 64.0, int(mc_Entity.x));',
              '    messyWriteVoxel(positions.xyz + at_midBlock.xyz / 64.0, int(mc_Entity.x));\n'
              '    messyWriteDynamicVoxel(positions.xyz);')

    # Existing E-Lite IDs are preserved, notably the lightning classification.
    entity_path = "shaders/entity.properties"
    entity_text = files[entity_path].decode("utf-8")
    for eid, (_, entities) in ENTITY_COLORS.items():
        if f"entity.{eid}" in entity_text:
            raise ValueError("Dynamic-light entity ID collision")
        entity_text += f"\nentity.{eid} = {entities}"
    files[entity_path] = (entity_text + "\n").encode("utf-8")

    # Shadow entity rendering costs CPU/GPU work; tie it to the new toggle.
    properties_path = "shaders/shaders.properties"
    patch_one(files, properties_path, "#ifdef SHADOW_ENTITIES\n    shadowEntities = true",
              "#if defined(SHADOW_ENTITIES) || defined(MESSY_DYNAMIC_EMITTERS)\n    shadowEntities = true")
    return {"enabled_by_default": True,
            "source": "Iris currentRenderedItemId + entityId in shadow pass",
            "categories": list(ENTITY_COLORS),
            "limitations": ["Only objects drawn in shadow pass",
                            "Entity geometry, not entity centers, seeds nearby cells",
                            "Voxel priority collision picks one palette index",
                            "Fire on arbitrary entities requires dedicated detection"]}

def replace_all_checked(files: dict[str, bytes], path: str, old: str, new: str, minimum: int = 1):
    data = files[path].decode("utf-8")
    found = data.count(old)
    if found < minimum:
        raise ValueError(f"No shader branch to patch: {path}, {old!r}")
    files[path] = data.replace(old, new).encode("utf-8")
    return found

def add_procedural_ipbr(files: dict[str, bytes]) -> dict:
    files["shaders/lib/messy_procedural_pbr.glsl"] = procedural_library().encode("utf-8")

    vertex = "shaders/common/solid_blocks_vertex.glsl"
    fragment = "shaders/common/solid_blocks_fragment.glsl"
    cond = "defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)"
    either = "(defined LabPBR || defined MESSY_IPBR) && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)"
    # Share sprite-local tangent/atlas coords with generated normal path.
    replace_all_checked(files, vertex, cond, either)
    replace_all_checked(files, vertex, "#if WAVING == 1 || defined LabPBR",
                        "#if WAVING == 1 || defined LabPBR || defined MESSY_IPBR")
    replace_all_checked(files, vertex,
                        "|| defined LabPBR || defined SHADOW_CASTING || defined EMISSIVE_MATERIAL",
                        "|| defined LabPBR || defined MESSY_IPBR || defined SHADOW_CASTING || defined EMISSIVE_MATERIAL")
    replace_all_checked(files, vertex, "|| defined LabPBR || defined SHADOW_CASTING",
                        "|| defined LabPBR || defined MESSY_IPBR || defined SHADOW_CASTING")
    replace_all_checked(files, vertex,
                        "|| defined LabPBR\n        sub_position3 = sub_position.xyz;",
                        "|| defined LabPBR || defined MESSY_IPBR\n        sub_position3 = sub_position.xyz;")

    # Only share the varying declaration, do not read a LabPBR texture in
    # generated-PBR mode: it must still work without resource-pack maps.
    patch_one(files, fragment, "#if defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)\n    #ifdef POM",
              "#if " + either + "\n    #ifdef POM")
    replace_all_checked(files, fragment,
                        "|| defined LabPBR || defined SHADOW_CASTING || defined EMISSIVE_MATERIAL",
                        "|| defined LabPBR || defined MESSY_IPBR || defined SHADOW_CASTING || defined EMISSIVE_MATERIAL")
    replace_all_checked(files, fragment, "|| defined LabPBR || defined SHADOW_CASTING",
                        "|| defined LabPBR || defined MESSY_IPBR || defined SHADOW_CASTING")
    patch_one(files,fragment,
              '#include "/lib/luma.glsl"',
              '#include "/lib/luma.glsl"\n#include "/lib/messy_procedural_pbr.glsl"\n#ifdef MESSY_IPBR\nuniform ivec2 atlasSize;\n#endif')

    # Construct normals from each modded texture's *own* neighboring texels.
    normal_anchor = """    #else
        #if MATERIAL_GLOSS < 1
            vec3 bumpedNormal = vec3(1.0);"""
    normal_new = """    #elif defined MESSY_IPBR && !defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)
        vec3 bumpedNormal = messyGeneratedNormal(
            tex, final_uv, pure_block_color.rgb, atlas_uv, tbn, vec2(atlasSize),
            messyTextureVariation);
    #else
        #if MATERIAL_GLOSS < 1
            vec3 bumpedNormal = vec3(1.0);"""
    patch_one(files, fragment, normal_anchor, normal_new)
    # Remove the incorrect luminance-to-parallax atlas shift and the
    # extra, nearly block-wide voxel-light sampling offset. Use actual
    # generated normals for small-scale local shading instead.
    patch_one(files, fragment,
              "        vec3 messyRGB = texture3D(messyRgbASampler, messyLightUVW).rgb;",
              """        vec3 messyRGB = texture3D(messyRgbASampler, messyLightUVW).rgb;
        #if defined MESSY_IPBR && !defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)
            vec3 messyN = normalize(bumpedNormal);
            vec3 messyFlatN = normalize(flat_normal);
            vec3 messyLightDir = normalize(vec3(0.35, 0.82, 0.40));
            float messySurfaceRelief = clamp(
                dot(messyN - messyFlatN, messyLightDir), -0.35, 0.35);
            messyRGB *= (1.0 + 0.35 * messySurfaceRelief);
        #endif""")
    patch_one(files, fragment, "    // === PBR auxiliary",
              "    float messyTextureVariation = 0.0;\n    // === PBR auxiliary")
    patch_one(files,fragment,
              "#if !defined NETHER && defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)",
              "#if !defined NETHER && (defined LabPBR || defined MESSY_IPBR) && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)")
    # In E-Lite's existing gloss path, replace only fallback roughness,
    # preserving LabPBR specular/normal workflow entirely.
    material_anchor="""            float final_gloss_power = glossParms.g;
            float block_luma2 = pow(block_luma * glossParms.b, glossParms.a);
            float isMetal = 0.0;
            f0_val = reflex_index2;"""
    material_new="""            float final_gloss_power = glossParms.g;
            float block_luma2 = pow(block_luma * glossParms.b, glossParms.a);
            float isMetal = 0.0;
            f0_val = reflex_index2;
            #if defined MESSY_IPBR && !defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)
                isMetal = step(0.55, reflex_index2);
                currentRoughness = messyAutoRoughness(
                    messyTextureVariation, block_luma, isMetal);
                final_gloss_power = mix(glossParms.g,
                    8.0 + (1.0 - currentRoughness) * 118.0, 0.75);
                block_luma2 *= mix(0.8, 1.3, 1.0 - currentRoughness);
            #endif"""
    patch_one(files,fragment,material_anchor,material_new)

    # User can disable auto-generated normal+roughness without affecting LabPBR.
    config_path="shaders/lib/config.glsl"
    config=files[config_path].decode("utf-8")
    files[config_path]=(
        "// Procedural PBR (also works on new modded atlas textures). \n"
        "// Two extra atlas samples/fragment; disables automatically for LabPBR. \n"
        "#define MESSY_IPBR\n"
        "#define MESSY_IPBR_NORMAL_STRENGTH 2.5 // [0.0 1.0 1.5 2.5 4.0]\n"

        "#define MESSY_DYNAMIC_EMITTERS\n"
        + config).encode("utf-8")
    # Small test menu: toggle expensive procedural sampling and entity draws
    # independently when comparing GPU frame times against the base shader.
    props_path = "shaders/shaders.properties"
    props = files[props_path].decode("utf-8")
    props = props.replace("[LabPBR] [INFO_SCREEN]", "[LabPBR] [MESSY_FEATURES] [INFO_SCREEN]")
    props += (
        "\n# MessyShaders experimental feature switches.\n"
        "screen.MESSY_FEATURES.columns=2\n"
        "screen.MESSY_FEATURES= MESSY_DYNAMIC_EMITTERS MESSY_IPBR "
        "MESSY_IPBR_NORMAL_STRENGTH <empty> PERF_IMPACT\n"
    )
    files[props_path] = props.encode("utf-8")
    return {
        "enabled_by_default": True,
        "terrain_block_textures": True,
        "texture_fetches_extra": "two neighboring albedo samples for conservative normals; no parallax or extra RGB-volume read",
        "single_step_parallax": False,
        "labpbr_priority": True,
        "limitations": ["Procedural approximate normals/roughness, not full Complementary IPBR+ parity",
                        "No auto-metal detection from arbitrary textures",
                        "No generated entity or Voxy LOD normal maps yet"]}

def apply_dynamic_ipbr(files: dict[str, bytes]) -> dict:
    return {
        "dynamic_emitters": add_dynamic_lights(files),
        "procedural_pbr": add_procedural_ipbr(files),
    }
