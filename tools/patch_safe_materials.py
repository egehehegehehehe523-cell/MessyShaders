"""Default to E-Lite's native materials until generated PBR is reliable.

This runs after the experimental patches so all the existing compile paths
remain available for manual development, but old Iris profile overrides
cannot silently enable the artifacts reported by users.
"""
from __future__ import annotations


def replace_one(pack: dict[str, bytes], path: str, old: str, new: str):
    body = pack[path].decode("utf-8")
    if body.count(old) != 1:
        raise ValueError(f"Unexpected material safety anchor: {path}")
    pack[path] = body.replace(old, new, 1).encode("utf-8")


def apply_safe_materials(pack: dict[str, bytes]) -> dict:
    config = "shaders/lib/config.glsl"
    # Both early MESSY_IPBR and MESSY_COATED_TEXTURES defaults were enabled;
    # the new artifact reports show texture and tangent-space guesses are not
    # safe on every block atlas. The native LabPBR path remains untouched.
    replace_one(pack, config,
                "#define MESSY_COATED_TEXTURES\n",
                "// #define MESSY_COATED_TEXTURES // experimental; off by default\n")
    replace_one(pack, config,
                "#define MESSY_IPBR\n",
                "// #define MESSY_IPBR // experimental; off by default\n")

    # Even an already-saved 'on' shader profile for the previous macro must
    # not silently activate unstable normals/coating on the next release.
    suffix = """\n// E-Lite's authored LabPBR remains selectable without these previews.
// Developers can explicitly define MESSY_UNSAFE_MATERIAL_PREVIEW to test them.
#ifndef MESSY_UNSAFE_MATERIAL_PREVIEW
    #undef MESSY_IPBR
    #undef MESSY_COATED_TEXTURES
#endif
"""
    pack[config] = (pack[config].decode("utf-8") + suffix).encode("utf-8")

    props = "shaders/shaders.properties"
    replace_one(pack, props,
                "MESSY_IPBR_NORMAL_STRENGTH MESSY_COATED_TEXTURES MESSY_COAT_STRENGTH <empty> PERF_IMPACT",
                "<empty> PERF_IMPACT")
    replace_one(pack, props,
                "MESSY_DYNAMIC_EMITTERS MESSY_IPBR <empty> PERF_IMPACT",
                "MESSY_DYNAMIC_EMITTERS <empty> PERF_IMPACT")
    return {
        "default": "native E-Lite material and optional authored LabPBR maps",
        "generated_normals": "disabled even for persisted old Iris profiles",
        "coated_textures": "disabled pending visual validation",
        "manual_override": "MESSY_UNSAFE_MATERIAL_PREVIEW (development only)",
    }
