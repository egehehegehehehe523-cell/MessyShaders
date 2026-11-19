"""Match E-Lite's near and Voxy water treatments at the chunk/LOD boundary.

Complementary's independently implemented LOD path is a useful reference:
keep water depth aware and gradually remove screen-space detail at the
handoff. No Complementary shader source is copied into this LGPL shader pack.
"""
from __future__ import annotations


def replace_once(pack: dict[str, bytes], path: str, old: str, new: str) -> None:
    source = pack[path].decode("utf-8")
    count = source.count(old)
    if count != 1:
        raise ValueError(f"Water LOD anchor missing/ambiguous: {path}: {count}")
    pack[path] = source.replace(old, new, 1).encode("utf-8")


def apply_water_lod(pack: dict[str, bytes]) -> dict:
    near = "shaders/common/water_blocks_fragment.glsl"
    far = "shaders/common/water_voxy_blocks_fragment.glsl"
    near_lib = "shaders/lib/water.glsl"
    far_lib = "shaders/lib/water_voxy.glsl"

    # The default E-Lite near-water refraction queried the *translucent*
    # distant depth; for water thickness we need the opaque ground underneath.
    # Its own nearby ground continues to be handled by depthtex1.
    replace_once(pack, near,
                 "    uniform sampler2D vxDepthTexTrans;",
                 "    uniform sampler2D vxDepthTexOpaque;\n    uniform int vxRenderDistance;")
    replace_once(pack, near_lib,
                 "float earth_distance_vx = texture2D(vxDepthTexTrans, pos.xy).r;",
                 "float earth_distance_vx = texture2D(vxDepthTexOpaque, pos.xy).r;")

    # Voxy's water used a *linear* absorption gap and a different tint,
    # while E-Lite near water squares that gap. Using the same attenuation
    # curve and tint removes one large source of a hard diagonal ocean seam.
    replace_once(pack, far_lib,
                 "float earth_distance = texture2D(vxDepthTexTrans, pos.xy).x;",
                 "float earth_distance = texture2D(vxDepthTexOpaque, pos.xy).x;")
    replace_once(pack, far_lib,
                 """        water_absortion = max(earth_distance - water_distance, 0.0);
        water_absortion = (1.0 / -((water_absortion * WATER_ABSORPTION) + 1.33)) + 1.0;""",
                 """        water_absortion = max(earth_distance - water_distance, 0.0);
        water_absortion *= water_absortion;
        water_absortion = (1.0 / -((water_absortion * WATER_ABSORPTION) + 1.33)) + 1.0;""")
    replace_once(pack, far_lib,
                 "mix(vec3(0.9, 1.0, 1.0), vec3(0.8, 1.3, 1.6) * 0.9, water_absortion)",
                 "mix(vec3(0.95, 1.0, 1.0), vec3(0.8, 1.1, 1.4) * 0.9, water_absortion)")

    # Match the surface-normal basis and baseline rain turbulence. The near
    # renderer additionally attenuates rain waves in obstructed skylight.
    replace_once(pack, far_lib,
                 "rainStrength * 0.6 * WATER_TURBULENCE",
                 "rainStrength * 0.333 * WATER_TURBULENCE")
    replace_once(pack, far_lib,
                 "bump *= vec3(NdotE) + vec3(0.0, 0.0, 1.0 - NdotE);",
                 "bump *= vec3(NdotE) + vec3(0.05, 0.1, 1.0 - NdotE);")

    # The near water's detailed animated normals end gradually at the
    # near-chunk limit; Voxy's detail starts from that same flat normal and
    # ramps back over the first 64 LOD blocks. Distance is Chebyshev (XZ),
    # because Minecraft's chunk load boundary is square, not spherical.
    # This costs only ALU and avoids opacity dithering / disappearing water.
    replace_once(pack, near,
                 "        vec3 water_normal_base = normal_waves(worldposition.xzy);",
                 """        vec3 water_normal_base = normal_waves(worldposition.xzy);
        #ifdef VOXY
            float messyWaterEdge = float(vxRenderDistance * 16);
            float messyWaterXZ = max(abs(worldposition.x - cameraPosition.x),
                                     abs(worldposition.z - cameraPosition.z));
            float messyNearWave = 1.0 - smoothstep(
                max(0.0, messyWaterEdge - 64.0), messyWaterEdge, messyWaterXZ);
            water_normal_base = normalize(mix(vec3(0.0, 0.0, 1.0),
                                              water_normal_base, messyNearWave));
        #endif""")
    replace_once(pack, far,
                 "        vec3 waterNormalBase = normal_waves_voxy(worldposition.xzy);",
                 """        vec3 waterNormalBase = normal_waves_voxy(worldposition.xzy);
        float messyWaterEdge = float(vxRenderDistance * 16);
        float messyWaterXZ = max(abs(worldposition.x - cameraPosition.x),
                                 abs(worldposition.z - cameraPosition.z));
        float messyFarWave = smoothstep(
            messyWaterEdge, messyWaterEdge + 64.0, messyWaterXZ);
        waterNormalBase = normalize(mix(vec3(0.0, 0.0, 1.0),
                                        waterNormalBase, messyFarWave));""")

    # Voxy supplies and binds this texture under its built-in sampler names;
    # declaring it in the patch JSON is required for the shader to compile.
    meta = "shaders/common/voxy.json"
    replace_once(pack, meta,
                 '    "vxDepthTexTrans": "sampler2D"',
                 '    "vxDepthTexTrans": "sampler2D",\n    "vxDepthTexOpaque": "sampler2D"')

    return {
        "water_depth": "opaque LOD depth; near and far square the absorption gap",
        "water_normals": "matched normal basis and rain turbulence, 64-block near/far wave handoff",
        "extra_texture_reads": "none; switches from translucent to opaque depth",
        "caveats": ["Requires in-game screenshot comparison at LOD boundary",
                    "Voxy fluid geometry and biome tinting are managed by Neo-Voxy"],
    }
