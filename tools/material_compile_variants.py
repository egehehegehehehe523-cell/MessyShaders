#!/usr/bin/env python3
"""Generate standalone GLSL files for material-path CI smoke tests.

The default shader compile does not exercise E-Lite's no-gloss lighting
branch or the native LabPBR branch. These are precisely where missing
generated normals previously remained invisible.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def variants(flattened: Path, output: Path) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    result: list[Path] = []
    names = ("gbuffers_terrain", "gbuffers_block")
    for name in names:
        for stage in ("vert", "frag"):
            input_file = flattened / f"shaders__world0__{name}.{stage}"
            source = input_file.read_text(encoding="utf-8")
            if source.count("#define MATERIAL_GLOSS 1") < 1:
                raise ValueError(f"Missing default material gloss definition: {input_file}")
            for flavor in ("low_gloss", "labpbr", "debug_normals",
                           "rgb_seed", "rgb_diffused", "rgb_history",
                           "rgb_coords", "rgb_live"):
                code = source
                if flavor == "low_gloss":
                    code = code.replace("#define MATERIAL_GLOSS 1", "#define MATERIAL_GLOSS 0")
                elif flavor == "labpbr":
                    code = code.replace("#version 430 compatibility\n",
                                        "#version 430 compatibility\n#define LabPBR 1\n", 1)
                elif flavor == "debug_normals":
                    # Compile the debug branch too: the option is off by
                    # default, so a normal pack build would never test it.
                    code = code.replace("#version 430 compatibility\n",
                                        "#version 430 compatibility\n#define MESSY_AUTO_NORMAL_DEBUG 1\n", 1)
                elif flavor == "rgb_live":
                    if code.count("#define MESSY_RGB_LIVE_FIELD 0") != 1:
                        raise ValueError("Missing live RGB option")
                    code = code.replace("#define MESSY_RGB_LIVE_FIELD 0",
                                        "#define MESSY_RGB_LIVE_FIELD 1", 1)
                else:
                    selected = {"rgb_seed": 1, "rgb_diffused": 2,
                                "rgb_history": 3, "rgb_coords": 4}[flavor]
                    if code.count("#define MESSY_RGB_DEBUG 0") != 1:
                        raise ValueError("Missing RGB diagnostic option")
                    code = code.replace("#define MESSY_RGB_DEBUG 0",
                                        f"#define MESSY_RGB_DEBUG {selected}", 1)
                target = output / f"{name}_{flavor}.{stage}"
                target.write_text(code, encoding="utf-8")
                result.append(target)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("flattened", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    for file in variants(arguments.flattened, arguments.output):
        print(file)
