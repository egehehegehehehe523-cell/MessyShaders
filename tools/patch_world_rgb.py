"""Prototype bounded shader-only coloured *world* light through Iris custom images.

Experimental: re-voxelizes the nearby 48^3 area during the existing shadow
pass, then performs six low-resolution 6-neighbour propagation steps before
the gbuffers render. The first one-block step is fused into source decoding:
one less full-volume dispatch and intermediate image round trip. Variable
guarded jumps cover roughly sixteen blocks. RGB images use 8-bit storage;
the source palette and propagated intensities are bounded to [0, 1].
This gives placed block light surface spill and basic blocking by full blocks,
but it is NOT cached, physically exact or GPU benchmarked.

See docs/RENDERER_ARCHITECTURE.md for constraints and remaining work.
"""
from __future__ import annotations

from typing import Any

SIZE = 48
STEPS = 6
# Retain one-voxel coverage at the source, then use multi-scale jumps.
# This covers >99% of the 16-block Manhattan ball in six passes; every
# intermediate voxel must be tested so a multi-cell jump cannot cross a wall.
PROPAGATION_STRIDES = (1, 1, 2, 3, 4, 5)
assert len(PROPAGATION_STRIDES) == STEPS
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
        // High byte = intensity (255/255 for placed full block emitters),
        // low byte = palette index; enables compact category-scaled moving
        // emitters without allocating a second RGB light volume.
        imageAtomicMax(messyEmitVolume, voxel, (255u << 8u) | uint(blockId - 25999));
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
        # One shared 10x10 XY tile (including cardinal halos) eliminates
        # four redundant global emission-volume reads per interior voxel.
        # Z neighbours remain direct loads. ~1.2 KiB shared memory/group.
        "shared vec3 messySeedTile[10][10];",
        "layout(r32ui) uniform readonly uimage3D messyEmitVolume;",
        "layout(r32ui) uniform readonly uimage3D messyOpaqueVolume;",
        # The first propagation step previously wrote B after a separate
        # palette-decoding pass A. B is now written directly; the remaining
        # five steps alternate B -> A -> B -> A -> B -> A as before.
        "layout(rgba8) uniform writeonly image3D messyRgbB;",
        "vec3 messyPalette(uint id) {",
    ]
    for i, c in enumerate(COLORS, 1):
        lines.append("    if (id == %du) return vec3(%.3f, %.3f, %.3f);" % (i, *c))
    lines += [
        "    return vec3(0.0);",
        "}",
        "vec3 messySeedAt(ivec3 p) {",
        "    if (any(lessThan(p, ivec3(0))) ||",
        "        any(greaterThanEqual(p, ivec3(48)))) return vec3(0.0);",
        "    uint messyPackedVoxel = imageLoad(messyEmitVolume, p).r;",
        "    if (messyPackedVoxel == 0u) return vec3(0.0);",
        "    uint idx = messyPackedVoxel & 255u;",
        "    float lightScale = float((messyPackedVoxel >> 8u) & 255u) / 255.0;",
        "    return messyPalette(idx) * lightScale;",
        "}",
        "void main() {",
        "    ivec3 p = ivec3(gl_GlobalInvocationID);",
        "    ivec2 localXY = ivec2(gl_LocalInvocationID.xy);",
        "    ivec2 tileXY = localXY + ivec2(1);",
        "    messySeedTile[tileXY.x][tileXY.y] = messySeedAt(p);",
        "    if (localXY.x == 0) messySeedTile[0][tileXY.y] = messySeedAt(p - ivec3(1,0,0));",
        "    if (localXY.x == 7) messySeedTile[9][tileXY.y] = messySeedAt(p + ivec3(1,0,0));",
        "    if (localXY.y == 0) messySeedTile[tileXY.x][0] = messySeedAt(p - ivec3(0,1,0));",
        "    if (localXY.y == 7) messySeedTile[tileXY.x][9] = messySeedAt(p + ivec3(0,1,0));",
        "    barrier(); // All threads must populate the shared tile before reading halos.",
        "    vec3 center = messySeedTile[tileXY.x][tileXY.y];",
        "    if (imageLoad(messyOpaqueVolume, p).r != 0u) {",
        "        imageStore(messyRgbB, p, vec4(center, 1.0));",
        "        return;",
        "    }",
        "    vec3 neighbor = max(",
        "        max(messySeedTile[tileXY.x + 1][tileXY.y], messySeedTile[tileXY.x - 1][tileXY.y]),",
        "        max(messySeedTile[tileXY.x][tileXY.y + 1], messySeedTile[tileXY.x][tileXY.y - 1]));",
        "    neighbor = max(neighbor, messySeedAt(p + ivec3(0,0,1)));",
        "    neighbor = max(neighbor, messySeedAt(p - ivec3(0,0,1)));",
        "    imageStore(messyRgbB, p, vec4(max(center, neighbor * 0.88), 1.0));",
        "}",
        "",
    ]
    return "\n".join(lines)


def diffusion_source(input_field: str, output_field: str, stride: int) -> str:
    # All invocations only read previous-field values; each destination voxel
    # has a single writer per pass. No racing imageStore writes.
    # The former 0.83 per-cell loss removed most useful colour by block 10.
    # This is still attenuated each *actual* traversed block, not each pass.
    attenuation = 0.88 ** stride
    return f"""#version 430
layout(local_size_x = 8, local_size_y = 8, local_size_z = 1) in;
const ivec3 workGroups = ivec3(6, 6, 48);
const int messyStride = {stride};
layout(rgba8) uniform readonly image3D {input_field};
layout(rgba8) uniform writeonly image3D {output_field};
layout(r32ui) uniform readonly uimage3D messyOpaqueVolume;

vec3 sampleFrom(ivec3 p) {{
    if (any(lessThan(p, ivec3(0))) || any(greaterThanEqual(p, ivec3(48))))
        return vec3(0.0);
    return imageLoad({input_field}, p).rgb;
}}

vec3 sampleThrough(ivec3 p, ivec3 offset) {{
    ivec3 target = p + offset;
    if (any(lessThan(target, ivec3(0))) ||
        any(greaterThanEqual(target, ivec3(48)))) return vec3(0.0);
    vec3 candidate = sampleFrom(target);
    // Most volume cells are dark. Avoid occupancy reads on those paths.
    if (all(lessThanEqual(candidate, vec3(0.0)))) return candidate;
    ivec3 direction = offset / messyStride;
    for (int stepIndex = 1; stepIndex < messyStride; ++stepIndex) {{
        if (imageLoad(messyOpaqueVolume, p + direction * stepIndex).r != 0u)
            return vec3(0.0);
    }}
    return candidate;
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
        max(sampleThrough(p, ivec3( messyStride, 0, 0)), sampleThrough(p, ivec3(-messyStride, 0, 0))),
        max(sampleThrough(p, ivec3(0, messyStride, 0)), sampleThrough(p, ivec3(0,-messyStride, 0))));
    fromNearby = max(fromNearby, sampleThrough(p, ivec3(0,0, messyStride)));
    fromNearby = max(fromNearby, sampleThrough(p, ivec3(0,0,-messyStride)));
    // Attenuation depends on actual distance, not number of compute steps.
    imageStore({output_field}, p, vec4(max(center, fromNearby * {attenuation:.6f}), 1.0));
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
    # compute passes before gbuffers. RGBA8 halves light field bandwidth
    # relative to RGBA16F; channel values never exceed one before lighting.
    props = """
# MessyShaders bounded first-generation RGB world lighting.
iris.features.required = CUSTOM_IMAGES COMPUTE_SHADERS
image.messyEmitVolume = messyEmitSampler red_integer r32ui unsigned_int true false 48 48 48
image.messyOpaqueVolume = messyOpaqueSampler red_integer r32ui unsigned_int true false 48 48 48
image.messyRgbA = messyRgbASampler rgba rgba8 float true false 48 48 48
image.messyRgbB = messyRgbBSampler rgba rgba8 float true false 48 48 48
"""
    pack[properties] = (current.rstrip() + "\n" + props).encode("utf-8")
    put(pack, "shaders/lib/messy_voxel_vertex.glsl", shadow_vertex_source())
    patch_shadow(pack)
    patch_gbuffers(pack)
    for dimension in ("world0", "world-1", "world1"):
        prefix = f"shaders/{dimension}/prepare"
        put(pack, prefix + ".csh", seed_source())
        # Propagation step 0 (stride=1) was fused with palette decoding into
        # prepare.csh. All remaining passes use the same guarded diffusion.
        for index in range(1, STEPS):
            suffix = chr(ord("a") + index - 1)
            source_field = "messyRgbB" if index % 2 == 1 else "messyRgbA"
            target_field = "messyRgbA" if index % 2 == 1 else "messyRgbB"
            put(pack, f"{prefix}_{suffix}.csh",
                diffusion_source(source_field, target_field, PROPAGATION_STRIDES[index]))
    return {
        "mode": "Iris 48^3 voxel emission + shared-tile fused seed + 5 standalone passes, guarded 16-block reach, RGBA8",
        "max_propagation_reach": sum(PROPAGATION_STRIDES),
        "gpu_measured": False,
        "irradiance_occlusion": "basic block-based voxel occupancy; not per-face exact",
        "frame_cache": False,
        "supports_placed_block_light_spill": True,
        "supports_independent_coloured_dynamic_entities": False,
        "texture_bytes_approx": SIZE ** 3 * (4 + 4 + 4 + 4),
        "light_storage": "RGBA8 normalized; bounded [0,1] RGB sources",
    }
