"""Bring E-Lite's far-water and far-terrain lighting closer to its near path.

No depth-buffer substitution, absorption curve rewrite, alpha/dither
crossfade, or Voxy/Minecraft mixin. Those approaches previously broke water.
"""
from __future__ import annotations


def patch_once(pack: dict[str, bytes], path: str, old: str, new: str):
    data = pack[path].decode("utf-8")
    if data.count(old) != 1:
        raise ValueError(f"Missing or ambiguous LOD shading anchor {path}: {old!r}")
    pack[path] = data.replace(old, new, 1).encode("utf-8")


def apply_lod_shading(pack: dict[str, bytes]) -> dict:
    water_fragment = "shaders/common/water_voxy_blocks_fragment.glsl"
    water_lib = "shaders/lib/water_voxy.glsl"
    light = "shaders/src/voxy_position_light.glsl"

    # E-Lite's original far-water horizon fog reaches 100% *at the first
    # Voxy ring*. The far opaque renderer divides the same normalized
    # distance by 32. Match that normalization and preserve the rest of
    # the water fog curve and all depth/refraction math.
    patch_once(pack, water_fragment,
               "clamp(fogFragCoord / float(vxRenderDistance * 16), 0.0, 1.0)",
               "clamp(fogFragCoord / float(vxRenderDistance * 16) / 32.0, 0.0, 1.0)")

    # Match the native terrain sky-light conversion; previously the LOD
    # version omitted the negative bias and illuminated enclosed geometry
    # more strongly than otherwise identical near block faces.
    patch_once(pack, light,
               "float visibleSky = clamp(illumination.y, 0.0, 1.0);",
               "float visibleSky = clamp(illumination.y - 0.0695, 0.0, 1.0);")

    # E-Lite's Voxy water uses noticeably bluer absorption tint and steeper
    # rain normals than its near-water code. Matching those constants is
    # safe: the sampler selection, depth linearization, and absorption
    # formula remain exactly as in E-Lite's original Voxy implementation.
    patch_once(pack, water_lib,
               "rainStrength * 0.6 * WATER_TURBULENCE",
               "rainStrength * 0.333 * WATER_TURBULENCE")
    patch_once(pack, water_lib,
               "bump *= vec3(NdotE) + vec3(0.0, 0.0, 1.0 - NdotE);",
               "bump *= vec3(NdotE) + vec3(0.05, 0.1, 1.0 - NdotE);")
    patch_once(pack, water_lib,
               "mix(vec3(0.9, 1.0, 1.0), vec3(0.8, 1.3, 1.6) * 0.9, water_absortion)",
               "mix(vec3(0.95, 1.0, 1.0), vec3(0.8, 1.1, 1.4) * 0.9, water_absortion)")

    return {
        "water_horizon_fog": "matched to existing Voxy opaque /32 distance scale",
        "sky_light": "LOD sky visibility now uses near-terrain's -0.0695 bias",
        "water_normals": "rain-wave response and eye-angle tangent bias matched to E-Lite near water",
        "water_tint": "shallow/deep refraction tint matched to E-Lite near water",
        "water_depth_refraction_formula_changed": False,
        "overlap_crossfade": False,
        "note": "Seam reduction, not a geometry-level transition; runtime comparison required",
    }
