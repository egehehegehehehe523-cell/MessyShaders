"""Optional automatic normal relief on E-Lite's existing entity shader path.

Unlike terrain, entities do not expose the block sprite atlas bounds or
mc_midTexCoord consistently. Reconstruct the tangent frame from derivatives;
do not alter base colors, geometry, water or the entity's animation pipeline.
"""


def apply(pack: dict[str, bytes]) -> None:
    path = "shaders/common/solid_blocks_fragment.glsl"
    body = pack[path].decode("utf-8")
    anchor = "    #if !defined NETHER && defined MESSY_AUTO_PBR && !defined LabPBR && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)"
    if body.count(anchor) != 1:
        raise ValueError("Missing entity-normal insertion anchor")
    code = r"""
    // Iris recognizes Boolean shader options only when they are referenced
    // by #ifdef/#ifndef, not by "#if defined(...)" alone. Keep this guard
    // explicit so the opt-in setting appears in the shaders menu.
    #ifdef MESSY_PBR_ENTITIES
    #if defined GBUFFER_ENTITIES && MATERIAL_GLOSS > 0
        // Only entities, never block geometry or dropped item render wrappers.
        // Skip atlas texel boundaries and degenerate UV mapping.
        vec2 entTexel = 1.0 / max(vec2(atlasSize), vec2(16.0));
        vec2 entUVPixel = fract(texcoord / entTexel);
        vec2 entDu = dFdx(texcoord);
        vec2 entDv = dFdy(texcoord);
        float entDet = entDu.x * entDv.y - entDu.y * entDv.x;
        float entDistance = length(sub_position3);
        if (abs(entDet) > 1e-8 &&
            all(greaterThan(entUVPixel, vec2(0.08))) &&
            all(lessThan(entUVPixel, vec2(0.92))) &&
            entDistance < float(MESSY_AUTO_PBR_DISTANCE)) {
            vec3 entDx = dFdx(sub_position3);
            vec3 entDy = dFdy(sub_position3);
            vec3 entTangent = normalize((entDx * entDv.y - entDy * entDu.y) * sign(entDet));
            vec3 entBitangent = normalize((-entDx * entDv.x + entDy * entDu.x) * sign(entDet));
            mat3 entTBN = mat3(entTangent, entBitangent, normalize(flat_normal));
            vec2 entStep = max(entTexel * (16.0 / float(MESSY_AUTO_PBR_RESOLUTION)),
                               fwidth(texcoord));
            float entCenter = length(pure_block_color.rgb);
            vec2 entEdge = vec2(
                length(texture2D(tex, texcoord - vec2(entStep.x, 0.0)).rgb) -
                length(texture2D(tex, texcoord + vec2(entStep.x, 0.0)).rgb),
                length(texture2D(tex, texcoord - vec2(0.0, entStep.y)).rgb) -
                length(texture2D(tex, texcoord + vec2(0.0, entStep.y)).rgb));
            entEdge = clamp(sign(entEdge) * max(abs(entEdge) - vec2(0.05), vec2(0.0)),
                            vec2(-0.20), vec2(0.20));
            float entFade = 1.0 - smoothstep(float(MESSY_AUTO_PBR_DISTANCE) * 0.57,
                                              float(MESSY_AUTO_PBR_DISTANCE), entDistance);
            vec3 entNormal = normalize(vec3(entEdge *
                (3.5 * MESSY_AUTO_PBR_STRENGTH * entFade), 1.0));
            bumpedNormal = normalize(entTBN * entNormal);
        }
    #endif
    #endif

"""
    body = body.replace(anchor, code + anchor, 1)
    # The direct-light correction for entities is separate from the existing
    # terrain correction and intentionally skips low-gloss profiles.
    anchor2 = "    // === Block reflection"
    if body.count(anchor2) != 1:
        raise ValueError("Missing entity direct-light anchor")
    code2 = r"""
    #ifdef MESSY_PBR_ENTITIES
    #if defined GBUFFER_ENTITIES && MATERIAL_GLOSS > 0
        vec3 entSun = normalize(light_mix >= 0.5 ? sunPosition : -sunPosition);
        float entFaceLight = max(dot(normalize(flat_normal), entSun), 0.0);
        float entPixelLight = max(dot(normalize(bumpedNormal), entSun), 0.0);
        shadow_c_relief *= mix(1.0, clamp((entPixelLight + 0.20) /
            (entFaceLight + 0.20), 0.70, 1.30), smoothstep(0.58, 0.78, light_mix) * 0.8);
    #endif
    #endif

"""
    body = body.replace(anchor2, code2 + anchor2, 1)
    pack[path] = body.encode("utf-8")
