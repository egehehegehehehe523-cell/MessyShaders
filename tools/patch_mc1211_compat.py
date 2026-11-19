"""Keep the 1.21.1 shader option parser and biome uniforms compatible."""
from __future__ import annotations


def apply_mc1211_compat(pack: dict[str, bytes]) -> dict:
    path = "shaders/shaders.properties"
    source = pack[path].decode("utf-8")
    original = "uniform.float.pale_garden = smooth(if(in(biome, BIOME_PALE_GARDEN), 1, 0), 60, 60)"
    if source.count(original) != 1:
        raise ValueError("Unexpected E-Lite pale garden uniform")
    source = source.replace(original,
        "#if MC_VERSION >= 12104\n" + original +
        "\n#else\nuniform.float.pale_garden = 0.0\n#endif", 1)
    pack[path] = source.encode("utf-8")

    # Iris's pack option collector recognizes direct #ifdef guards. The
    # previous combined #if defined() expression was shading correctly but
    # the bare MESSY_COATED_TEXTURES UI toggle could not be resolved.
    path = "shaders/common/solid_blocks_fragment.glsl"
    source = pack[path].decode("utf-8")
    first = "    #if defined MESSY_COATED_TEXTURES && (defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK)"
    last = "(messyGrain - 0.5) * MESSY_COAT_STRENGTH * messyContrast * messyMipFade;\n    #endif"
    if source.count(first) != 1 or source.count(last) != 1:
        raise ValueError("Missing coated-texture guards")
    source = source.replace(first,
        "    #ifdef MESSY_COATED_TEXTURES\n    #if defined GBUFFER_TERRAIN || defined GBUFFER_BLOCK", 1)
    source = source.replace(last, last + "\n    #endif", 1)
    pack[path] = source.encode("utf-8")
    return {"pale_garden": "fixed zero on 1.21.1, available on 1.21.4+",
            "coated_textures_menu": "direct preprocessor option guard"}
