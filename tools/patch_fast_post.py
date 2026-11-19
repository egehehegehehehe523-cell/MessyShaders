"""Semantics-preserving GPU hot-path optimizations for E-Lite shaders.

Derived independently from the LGPL E-Lite base (no Luxium renderer code).
"""
from __future__ import annotations


def replace_exact(pack: dict[str, bytes], path: str, needle: str, replacement: str) -> None:
    body = pack[path].decode("utf-8")
    count = body.count(needle)
    if count != 1:
        raise ValueError(f"Unexpected optimization anchor in {path}: {count} occurrences")
    pack[path] = body.replace(needle, replacement, 1).encode("utf-8")


def apply_fast_post(pack: dict[str, bytes]) -> dict:
    bloom = "shaders/lib/bloom.glsl"
    replace_exact(pack, bloom,
        "    float n;\n    vec2 offset;\n    float dither_x;\n",
        """    // Symmetric +/- samples are invariant under a 180-degree axis flip.
    // Incremental golden-angle rotation replaces per-tap trig with one
    // sin/cos pair per pixel, retaining the same taps and bloom strength.
    float firstAngle = fract(dither * 1.6180339887) * 3.141592653589793;
    vec2 axis = vec2(cos(firstAngle), sin(firstAngle));
    const vec2 turn = vec2(-0.362374890, 0.932032424);
    vec2 offset;
""")
    replace_exact(pack, bloom,
        """        dither_x = i + dither;
        n = fract(dither_x * 1.6180339887) * 3.141592653589793;
        offset = vec2(cos(n), sin(n)) * dither_x * blur_radios_factor;

        blur_sample += texture2D(image, coords + offset).rgb;
        blur_sample += texture2D(image, coords - offset).rgb;
""",
        """        float radiusStep = float(i) + dither;
        offset = axis * radiusStep * blur_radios_factor;

        blur_sample += texture2D(image, coords + offset).rgb;
        blur_sample += texture2D(image, coords - offset).rgb;
        axis = vec2(axis.x * turn.x - axis.y * turn.y,
                    axis.x * turn.y + axis.y * turn.x);
""")

    # Keep E-Lite's original ray reprojection after a report of edge warp.
    # Only attenuate reflection alpha near/outside the screen, where the
    # mirrored or clamped off-screen image would otherwise be displayed.
    reflection = "shaders/lib/reflections_engine.glsl"
    replace_exact(pack, reflection,
        "    float border = min(border_x, border_y);\n    \n",
        """    float border = min(border_x, border_y);
    float edgeDistance = min(min(final_uv.x, 1.0 - final_uv.x),
                             min(final_uv.y, 1.0 - final_uv.y));
    border *= smoothstep(0.0, 0.04, edgeDistance);
    if (border <= 0.0) return vec4(0.0);

""")
    # E-Lite originally reflects offscreen water samples horizontally back
    # into the viewport, visibly folding the scene at the edges. Fade into
    # sky/environment reflections instead; never mirror a screen texture.
    water = "shaders/lib/water.glsl"
    old_water_reflection = """    pos.x = abs(pos.x);

    if (pos.x > RENDER_SCALE) {
        pos.x = RENDER_SCALE - (pos.x - RENDER_SCALE);
    }

    return vec4(texture2D(gaux1, pos.xy).rgb, border);
""".replace("\n\n    return", "\n    \n    return")
    replace_exact(pack, water, old_water_reflection,
        """    vec2 screenUV = pos.xy / RENDER_SCALE;
    float edgeDistance = min(min(screenUV.x, 1.0 - screenUV.x),
                             min(screenUV.y, 1.0 - screenUV.y));
    border *= smoothstep(0.0, 0.05, edgeDistance);
    if (border <= 0.0) return vec4(0.0);

    return vec4(texture2D(gaux1, pos.xy).rgb, border);
""")

    # Default to actual E-Lite shader water even if a saved Iris profile
    # requests vanilla water or resource-pack water texture. Users may turn
    # this option off to restore the original E-Lite water configuration.
    config = "shaders/lib/config.glsl"
    pack[config] += b"""
// MessyShaders: prefer shader-simulated near and LOD water over atlas water.
#define MESSY_SHADER_WATER
#ifdef MESSY_SHADER_WATER
    #ifdef VANILLA_WATER
        #undef VANILLA_WATER
    #endif
    #undef WATER_TEXTURE
    #define WATER_TEXTURE 0
#endif
"""
    props = "shaders/shaders.properties"
    replace_exact(pack, props,
        "MESSY_AUTO_NORMAL_DEBUG PERF_IMPACT",
        "MESSY_AUTO_NORMAL_DEBUG MESSY_SHADER_WATER PERF_IMPACT")
    pack["shaders/lang/en_US.lang"] += (
        "\noption.MESSY_SHADER_WATER=Shader Water (No Vanilla Texture)\n"
        "option.MESSY_SHADER_WATER.comment=Keep E-Lite's animated/refraction water even when older Iris profiles request vanilla/resource-pack water. Disable to restore E-Lite's water-mode options.\n"
    ).encode()
    return {
        "bloom": "incremental golden-angle rotation; same symmetric taps",
        "reflections": "water offscreen mirror removed; water and solid reflection edge fade, original ray reprojection retained",
        "water": "shader water on by default; opt-out restores original vanilla/resource texture selection",
        "default_profile_changed": True,
        "gpu_measured": False,
    }
