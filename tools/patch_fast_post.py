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

    reflection = "shaders/lib/reflections_engine.glsl"
    old_projection = """        float useFallback = float(infinite > 0.5);
        vec2 ssr_uv;

        vec3 view_pos = screen_to_camera(march_result);
        vec3 curr_world_pos = mat3(gbufferModelViewInverse) * view_pos + gbufferModelViewInverse[3].xyz;
        vec3 prev_world_pos = curr_world_pos + (cameraPosition - previousCameraPosition);
        vec3 prev_view_pos = mat3(gbufferPreviousModelView) * prev_world_pos + gbufferPreviousModelView[3].xyz;

        vec2 prev_proj = vec2(
            gbufferPreviousProjection[0].x,
            gbufferPreviousProjection[1].y
        ) * prev_view_pos.xy + gbufferPreviousProjection[3].xy;

        ssr_uv = (prev_proj / -prev_view_pos.z) * 0.5 + 0.5;

        vec2 fallback_uv = fallback.xy;

        final_uv = mix(ssr_uv, fallback_uv, useFallback);
"""
    new_projection = """        // Failed ray marches do not need the unused hit's reprojection.
        if (infinite > 0.5) {
            final_uv = fallback.xy;
        } else {
            vec3 view_pos = screen_to_camera(march_result);
            vec3 curr_world_pos = mat3(gbufferModelViewInverse) * view_pos + gbufferModelViewInverse[3].xyz;
            vec3 prev_world_pos = curr_world_pos + (cameraPosition - previousCameraPosition);
            vec3 prev_view_pos = mat3(gbufferPreviousModelView) * prev_world_pos + gbufferPreviousModelView[3].xyz;
            vec2 prev_proj = vec2(
                gbufferPreviousProjection[0].x,
                gbufferPreviousProjection[1].y
            ) * prev_view_pos.xy + gbufferPreviousProjection[3].xy;
            final_uv = (prev_proj / -prev_view_pos.z) * 0.5 + 0.5;
        }
"""
    replace_exact(pack, reflection, old_projection, new_projection)
    replace_exact(pack, reflection,
        "    float border = min(border_x, border_y);\n    \n",
        """    float border = min(border_x, border_y);
    // The caller blends this reflection with exactly border alpha.
    // A zero-alpha reflection never needs three RGB texture fetches.
    if (border <= 0.0) return vec4(0.0);

""")
    return {
        "bloom": "incremental golden-angle rotation; same symmetric taps",
        "reflections": "zero-alpha sample skip and failed-ray reprojection skip",
        "default_profile_changed": False,
        "gpu_measured": False,
    }
