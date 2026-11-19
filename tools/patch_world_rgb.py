"""Prototype bounded shader-only coloured *world* light through Iris custom images.

Experimental: re-voxelizes the nearby 48^3 area during the existing shadow
pass, then performs six low-resolution 6-neighbour diffusion steps before
the gbuffers render.  This gives placed block light real surface spill and
basic blocking by full blocks, at a finite cost. It is NOT cached, not
Luxium's proprietary renderer, not physically based and not GPU benchmarked.

See docs/RENDERER_ARCHITECTURE.md for constraints and remaining work.
"""
from __future__ import annotations

from typing import Any

SIZE = 48
STEPS = 6
COLORS = [
    (1.00, 0.98, 0.93),  # white
    (0.68, 0.34, 0.16),  # brown
    (1.00, 0.20, 0.12),  # red
    (1.00, 0.48, 0.16),  # orange
    (1.00, 0.82, 0.34),  # yellow
    (0.61, 1.00, 0.22),  # lime
    (0.20, 0.92, 0.35),  # green
    (0.15, 0.92, 0.89),  # cyan
    (0.28, 0.70, 1.00),  # light blue
    (0.18, 0.34, 1.00),  # blue
    (0.61, 0.26, 1.00),  # purple
    (1.00, 0.28, 0.80),  # magenta
    (1.00, 0.59, 0.76),  # pink
]


def put(pack: dict[str, bytes], name: str, value: str) -> None:
    if name in pack:
        raise ValueError(f"World-light prototype would overwrite existing file: {name}")
    pack[name] = value.encode("utf-8")


def patch(pack: dict[str, bytes], path: str, needle: str, replacement: str) -> None:
    contents = pack[path].decode("utf-8")
    found = contents.count(needle)
    if found != 1:
        raise ValueError(f"Unexpected E-Lite patch anchor {path} ({found} occurrences): {needle!r}")
    pack[path] = contents.replace(needle, replacement, 1).encode("utf-8")


def shadow_vertex_source() -> str:
    return """// Original MessyShaders source, no code taken from proprietary references.
attribute vec3 at_midBlock;
uniform vec3 cameraPosition;
layout(r32ui) uniform uimage3D messyEmitVolume;
layout(r32ui) uniform uimage3D messyOpaqueVolume;

void messyWriteVoxel(vec3 worldRelative, int blockId) {
    // cameraPosition is absolute; use only its fractional component to
    // retain precision and avoid jitter while the camera moves within a block.
    ivec3 voxel = ivec3(floor(worldRelative + fract(cameraPosition) + 24.0));
    if (any(lessThan(voxel, ivec3(0))) || any(greaterThanEqual(voxel, ivec3(48))))
        return;

    if (blockId >= 26000 && blockId <= 26012) {
        // High byte = intensity tier (15/15 for placed full block emitters),
        // low byte = palette index; enables compact category-scaled moving
        // emitters without allocating a second RGB light volume.
        imageAtomicMax(messyEmitVolume, voxel, (15u << 8u) | uint(blockId - 25999));
    } else if (blockId > 0 && blockId < 26000 &&
               blockId != int(ENTITY_LEAVES) &&
               blockId != int(ENTITY_WHITE_LEAVES) &&
               blockId != int(ENTITY_SMALLGRASS) &&
               blockId != int(ENTITY_LOWERGRASS) &&
               blockId != int(ENTITY_UPPERGRASS)) {
        // Only an approximate solid-block mask. Cutouts, thin geometry
        // and entities need a more exact method later.
        imageAtomicOr(messyOpaqueVolume, voxel, 1u);
    }
}
"""


def seed_source() -> str:
    lines = [
        "#version 430",
        "layout(local_size_x = 8, local_size_y = 8, local_size_z = 1) in;",
        "const ivec3 workGroups = ivec3(6, 6, 48);",
        "layout(r32ui) uniform readonly uimage3D messyEmitVolume;",
        "layout(rgba16f) uniform writeonly image3D messyRgbA;",
        "vec3 messyPalette(uint id) {",
    ]
    for i, c in enumerate(COLORS, 1):
        lines.append("    if (id == %du) return vec3(%.3f, %.3f, %.3f);" % (i, *c))
    lines += [
        "    return vec3(0.0);",
        "}",
        "void main() {",
        "    ivec3 p = ivec3(gl_GlobalInvocationID);",
        "    if (any(greaterThanEqual(p, ivec3(48)))) return;",
        "    uint messyPackedVoxel = imageLoad(messyEmitVolume, p).r;",
        "    uint idx = messyPackedVoxel & 255u;",
        "    float lightScale = float((messyPackedVoxel >> 8u) & 255u) / 15.0;",
        "    imageStore(messyRgbA, p, vec4(messyPalette(idx) * lightScale, 1.0));",
        "}",
        "",
    ]
    return "\n".join(lines)


def diffusion_source(input_field: str, output_field: str) -> str:
    # All invocations only read previous-field values; each destination voxel
    # has a single writer per pass. No racing imageStore writes.
    return f"""#version 430
layout(local_size_x = 8, local_size_y = 8, local_size_z = 1) in;
const ivec3 workGroups = ivec3(6, 6, 48);
layout(rgba16f) uniform readonly image3D {input_field};
layout(rgba16f) uniform writeonly image3D {output_field};
layout(r32ui) uniform readonly uimage3D messyOpaqueVolume;

vec3 sampleFrom(ivec3 p) {{
    if (any(lessThan(p, ivec3(0))) || any(greaterThanEqual(p, ivec3(48))))
        return vec3(0.0);
    return imageLoad({input_field}, p).rgb;
}}

void main() {{
    ivec3 p = ivec3(gl_GlobalInvocationID);
    if (any(greaterThanEqual(p, ivec3(48)))) return;
    vec3 center = sampleFrom(p);
    if (imageLoad(messyOpaqueVolume, p).r != 0u) {{
        // Don't march light through the interior of a solid block.
        imageStore({output_field}, p, vec4(center, 1.0));
        return;
    }}
    vec3 fromNearby = max(
        max(sampleFrom(p + ivec3( 1, 0, 0)), sampleFrom(p + ivec3(-1, 0, 0))),
        max(sampleFrom(p + ivec3( 0, 1, 0)), sampleFrom(p + ivec3( 0,-1, 0))));
    fromNearby = max(fromNearby, sampleFrom(p + ivec3(0,0, 1)));
    fromNearby = max(fromNearby, sampleFrom(p + ivec3(0,0,-1)));
    imageStore({output_field}, p, vec4(max(center, fromNearby * 0.78), 1.0));
}}
"""


def patch_shadow(pack: dict[str, bytes]) -> None:
    p = "shaders/common/shadow_vertex.glsl"
    patch(pack, p, 'attribute vec4 mc_Entity;',
          'attribute vec4 mc_Entity;\n#include "/lib/messy_voxel_vertex.glsl"')
    patch(pack, p,
          '    worldPos = positions.xyz;',
          '    worldPos = positions.xyz;\n'
          '    // Block-centre positions avoid shadow-face dependent voxel holes.\n'
          '    messyWriteVoxel(positions.xyz + at_midBlock.xyz / 64.0, int(mc_Entity.x));')

    # The legacy shadow wrappers need image atomics (GL 4.2+) while keeping
    # gl_FragData, attributes, and varying in the compatibility profile.
    for dimension in ("world0", "world-1", "world1"):
        for ext in ("vsh", "fsh"):
            path = f"shaders/{dimension}/shadow.{ext}"
            # E-Lite disables Nether shadows and omits those wrappers.
            # Don't synthesize a new shadow pass without a separate test.
            if path in pack:
                patch(pack, path, "#version 120", "#version 430 compatibility")


def patch_gbuffers(pack: dict[str, bytes]) -> None:
    path = "shaders/common/solid_blocks_vertex.glsl"
    patch(pack, path, "varying vec3 omni_light;",
          "varying vec3 omni_light;\n"
          "varying vec3 messyWorldLightPos;")
    patch(pack, path, '#include "/src/position_vertex.glsl"',
          '#include "/src/position_vertex.glsl"\n'
          '    messyWorldLightPos = (gbufferModelViewInverse * sub_position).xyz;')
    # E-Lite defines cameraPosition only if waving is enabled; the new world
    # coordinate expression needs it in all cases, and the original include
    # already accesses it for fog when enabled.
    # World-light coordinate is a camera-relative varying; no vertex camera
    # uniform is needed for it.

    path = "shaders/common/solid_blocks_fragment.glsl"
    patch(pack, path, "varying vec3 direct_light_color, candle_color, omni_light;",
          "varying vec3 direct_light_color, candle_color, omni_light;\n"
          "varying vec3 messyWorldLightPos;\n"
          "uniform sampler3D messyRgbASampler;")
    patch(pack, path,
          "    block_color.rgb *= mix(real_light, vec3(1.0), nightVision * 0.125);",
          """    // World-position sample (no screen-space dependency). Trilinear
    // interpolation leaves a gentle spill along solid-air boundaries.
    vec3 messyLightUVW = (messyWorldLightPos + fract(cameraPosition) + vec3(24.0)) / 48.0;
    if (all(greaterThanEqual(messyLightUVW, vec3(0.0))) &&
        all(lessThan(messyLightUVW, vec3(1.0)))) {
        vec3 messyRGB = texture3D(messyRgbASampler, messyLightUVW).rgb;
        // Weak emitters dissipate perceptually within ~1-3 cells, while
        // full-strength placed lights retain their established footprint.
        float messyEnergy = max(messyRGB.r, max(messyRGB.g, messyRGB.b));
        messyRGB *= smoothstep(0.045, 0.15, messyEnergy);
        real_light += messyRGB * 1.2;
    }

    block_color.rgb *= mix(real_light, vec3(1.0), nightVision * 0.125);""")


def apply_world_rgb(pack: dict[str, bytes]) -> dict[str, Any]:
    properties = "shaders/shaders.properties"
    current = pack[properties].decode("utf-8")
    if "image.messyEmitVolume" in current:
        raise ValueError("RGB volume has already been added")
    # Iris supports 3-D custom images, RED_INTEGER/R32UI atomic writes and
    # compute passes before gbuffers. Keep format size small (48^3).
    props = """
# MessyShaders bounded first-generation RGB world lighting.
iris.features.required = CUSTOM_IMAGES COMPUTE_SHADERS
image.messyEmitVolume = messyEmitSampler red_integer r32ui unsigned_int true false 48 48 48
image.messyOpaqueVolume = messyOpaqueSampler red_integer r32ui unsigned_int true false 48 48 48
image.messyRgbA = messyRgbASampler rgba rgba16f float true false 48 48 48
image.messyRgbB = messyRgbBSampler rgba rgba16f float true false 48 48 48
"""
    pack[properties] = (current.rstrip() + "\n" + props).encode("utf-8")
    put(pack, "shaders/lib/messy_voxel_vertex.glsl", shadow_vertex_source())
    patch_shadow(pack)
    patch_gbuffers(pack)
    for dimension in ("world0", "world-1", "world1"):
        prefix = f"shaders/{dimension}/prepare"
        put(pack, prefix + ".csh", seed_source())
        for index in range(STEPS):
            suffix = chr(ord("a") + index)
            source_field = "messyRgbA" if index % 2 == 0 else "messyRgbB"
            target_field = "messyRgbB" if index % 2 == 0 else "messyRgbA"
            put(pack, f"{prefix}_{suffix}.csh", diffusion_source(source_field, target_field))
    return {
        "mode": "Iris camera-relative 48^3 voxel emission + 6 diffusion steps",
        "gpu_measured": False,
        "irradiance_occlusion": "basic block-based voxel occupancy; not per-face exact",
        "frame_cache": False,
        "supports_placed_block_light_spill": True,
        "supports_independent_coloured_dynamic_entities": False,
        "texture_bytes_approx": SIZE ** 3 * (4 + 4 + 8 + 8),
    }
